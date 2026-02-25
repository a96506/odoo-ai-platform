#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo ""
echo "=================================================="
echo "  Odoo AI Automation Platform — Deployment"
echo "=================================================="
echo ""

# ---- Prerequisites ----
log "Checking prerequisites..."

command -v docker &>/dev/null || fail "docker is required but not installed"

if docker compose version &>/dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    fail "docker compose (v2) or docker-compose is required"
fi
ok "Docker & Compose available ($COMPOSE)"

# ---- Environment file ----
if [ ! -f .env ]; then
    log "No .env file found — creating from .env.example..."
    cp .env.example .env
    echo ""
    warn "==> .env file created. You MUST edit it before deploying:"
    echo "      - Set ANTHROPIC_API_KEY to your Claude API key"
    echo "      - Set ODOO_URL to your Odoo instance address"
    echo "      - Set POSTGRES_PASSWORD to a strong random password"
    echo "      - Set AI_SECRET_KEY and WEBHOOK_SECRET to random secrets"
    echo "      - Update AI_DATABASE_URL to match your POSTGRES_PASSWORD"
    echo ""
    echo "    Then re-run:  ./scripts/deploy.sh"
    exit 1
fi

# Quick validation: make sure placeholder secrets were changed
source .env 2>/dev/null || true
if [[ "${ANTHROPIC_API_KEY:-}" == "sk-ant-xxxxx" || -z "${ANTHROPIC_API_KEY:-}" ]]; then
    fail "ANTHROPIC_API_KEY is not set in .env — edit it before deploying"
fi
if [[ "${AI_SECRET_KEY:-}" == "changeme-random-secret-32chars" ]]; then
    warn "AI_SECRET_KEY still has the default value — consider changing it"
fi
if [[ "${WEBHOOK_SECRET:-}" == "changeme-webhook-secret-32chars" ]]; then
    warn "WEBHOOK_SECRET still has the default value — consider changing it"
fi
if [[ "${POSTGRES_PASSWORD:-}" == "changeme-db-password" ]]; then
    warn "POSTGRES_PASSWORD still has the default value — consider changing it"
fi
ok ".env file validated"

# ---- External network ----
log "Ensuring dokploy-network exists..."
docker network create dokploy-network 2>/dev/null && ok "Created dokploy-network" || ok "dokploy-network already exists"

# ---- Build & Start ----
echo ""
log "Building and starting all services..."
$COMPOSE up -d --build --remove-orphans

echo ""
log "Waiting for services to become healthy..."

wait_for_health() {
    local name="$1"
    local url="$2"
    local max_attempts="${3:-40}"

    for i in $(seq 1 "$max_attempts"); do
        if curl -sf "$url" >/dev/null 2>&1; then
            ok "$name is healthy"
            return 0
        fi
        printf "  Waiting for %s... (%d/%d)\r" "$name" "$i" "$max_attempts"
        sleep 3
    done
    echo ""
    warn "$name did not become healthy within $((max_attempts * 3))s"
    return 1
}

sleep 5

AI_PORT="${AI_SERVICE_PORT:-8000}"
DASH_PORT="${DASHBOARD_PORT:-3000}"

wait_for_health "AI Service"  "http://localhost:${AI_PORT}/health"
wait_for_health "Dashboard"   "http://localhost:${DASH_PORT}"

# ---- Health summary ----
echo ""
log "Service health:"
HEALTH=$(curl -sf "http://localhost:${AI_PORT}/health" 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "  $HEALTH"
else
    warn "Could not retrieve health endpoint"
fi

# ---- Container status ----
echo ""
log "Container status:"
$COMPOSE ps

# ---- Done ----
echo ""
echo "=================================================="
echo -e "  ${GREEN}Deployment Complete${NC}"
echo "=================================================="
echo ""
echo "  Services:"
echo "    AI Service API:   http://localhost:${AI_PORT}"
echo "    API Docs (Swagger): http://localhost:${AI_PORT}/docs"
echo "    Dashboard:        http://localhost:${DASH_PORT}"
echo ""
echo "  Next steps:"
echo "    1. Copy  odoo_ai_bridge/  into your Odoo addons directory"
echo "    2. Restart Odoo and install the 'AI Bridge' module"
echo "    3. Configure the AI Service URL in Odoo:"
echo "         Settings > AI Platform > Configuration"
echo "    4. Run:  python3 scripts/setup_odoo_webhooks.py"
echo "    5. (Optional) Seed rules:  python3 scripts/seed_automation_rules.py"
echo ""
echo "  Useful commands:"
echo "    View logs:     $COMPOSE logs -f ai-service"
echo "    Worker logs:   $COMPOSE logs -f celery-worker"
echo "    Stop all:      $COMPOSE down"
echo "    Restart:       $COMPOSE restart"
echo ""
