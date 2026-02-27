# Lessons Learned

Hard-won knowledge from building and deploying the Smart Odoo AI platform. Every section documents an actual error loop, its root cause, and the fix. Read this before deploying or debugging.

---

## 1. Celery Task Registration (3-Attempt Error Loop)

**The goal:** Get Celery workers to discover and run tasks defined in `app/tasks/celery_tasks.py`.

### Attempt 1: `autodiscover_tasks`

```python
celery_app.autodiscover_tasks(["app.tasks"])
```

**What happened:** Worker started, listed zero tasks. `celery -A app.tasks.celery_app inspect registered` returned an empty list.

**Why it failed:** `autodiscover_tasks` looks for a `tasks.py` file inside each listed package. Our module is `app.tasks.celery_tasks`, not `app.tasks.tasks`. The naming convention mismatch means autodiscovery silently finds nothing.

### Attempt 2: `autodiscover_tasks` with `related_name`

```python
celery_app.autodiscover_tasks(["app.tasks"], related_name="celery_tasks")
```

**What happened:** Same result -- zero tasks registered.

**Why it failed:** `related_name` changes what filename autodiscovery looks for, but the import path resolution still failed because autodiscovery runs before the full app context is available in our Docker setup.

### Attempt 3: Explicit `include` (outside `conf.update`)

```python
celery_app = Celery("odoo_ai", broker=..., backend=..., include=["app.tasks.celery_tasks"])
celery_app.conf.update(task_serializer="json", ...)
```

**What happened:** Tasks registered, but `conf.update()` silently **overwrote** the `include` key back to empty because `conf.update()` replaces the entire config namespace.

**Why it failed:** The `Celery()` constructor sets `include` on the config. Then `conf.update()` replaces config values. Since `include` wasn't in the `conf.update()` dict, it got reset to default (empty).

### The Fix (Attempt 4):

```python
celery_app = Celery("odoo_ai", broker=..., backend=...)

celery_app.conf.update(
    include=["app.tasks.celery_tasks"],  # MUST be inside conf.update
    task_serializer="json",
    ...
)
```

**Rule:** Always put `include` inside `conf.update()`, never in the `Celery()` constructor when you also call `conf.update()`.

### Bonus: Worker Init Signal

Even after fixing task registration, the Celery worker couldn't run automations because `init_automations()` and `init_db()` only ran inside FastAPI's lifespan (which the worker doesn't use).

**Fix:** Added a `worker_init` signal handler:

```python
@worker_init.connect
def on_worker_init(**kwargs):
    from app.automations import init_automations
    from app.models.audit import init_db
    init_db()
    init_automations()
```

**Rule:** FastAPI lifespan events don't apply to Celery workers. Always initialize shared resources in both places.

---

## 2. Odoo Controller `type="json"` vs `type="http"`

**The goal:** AI Service sends raw JSON POST requests to Odoo callback endpoints.

### The Error

```python
@http.route("/ai/callback/read", type="json", auth="none", methods=["POST"], csrf=False)
```

Requests from the AI service returned `400 Bad Request` or were silently dropped.

### Root Cause

Odoo's `type="json"` expects a very specific JSON-RPC envelope:

```json
{"jsonrpc": "2.0", "method": "call", "params": {"model": "res.partner", ...}}
```

Our AI service sends plain JSON:

```json
{"model": "res.partner", "record_id": 1, "fields": ["name"]}
```

With `type="json"`, Odoo tries to unwrap the JSON-RPC envelope, finds no `params` key, and returns nothing useful.

### The Fix

```python
@http.route("/ai/callback/read", type="http", auth="none", methods=["POST"], csrf=False)
```

With `type="http"`, Odoo treats the request as raw HTTP. We parse the body manually:

```python
def _get_json_body(self):
    return json.loads(request.httprequest.data or "{}")
```

And return responses manually:

```python
def _json_response(data, status=200):
    return Response(json.dumps(data, default=str), status=status, content_type="application/json")
```

**Rule:** Use `type="http"` for any Odoo endpoint that receives plain JSON POST requests from external services. Use `type="json"` only for Odoo's own web client calls.

---

## 3. Helpdesk Module Conditional Import

**The goal:** `odoo_ai_bridge` module should work on Odoo instances that don't have the Helpdesk module installed (it's an Enterprise-only paid module).

### Attempt 1: Try/Except Import

```python
try:
    from . import helpdesk_ticket
except ImportError:
    pass
```

**What happened:** Odoo crashed at module loading with `ModuleNotFoundError`, not `ImportError`.

**Why:** Odoo's module loader resolves dependencies at the manifest level before Python imports run. If `helpdesk` is listed in `__manifest__.py` `depends`, Odoo fails before our try/except ever executes.

### Attempt 2: Remove from `__manifest__.py` + Try/Except

Removed `helpdesk` from `depends` list, kept the try/except.

**What happened:** Still crashed. Odoo's ORM tries to resolve the model class `helpdesk.ticket` referenced in `helpdesk_ticket.py` even if the import is in a try/except, because Odoo scans all `.py` files in the `models/` directory at module load time.

### The Fix: `importlib.util.find_spec`

```python
import importlib

if importlib.util.find_spec("odoo.addons.helpdesk"):
    from . import helpdesk_ticket
```

This checks if the helpdesk addon is even installed in the Python environment before attempting the import. If it's not installed, the import is completely skipped -- no model registration, no ORM resolution, no crash.

**Rule:** For optional Odoo module dependencies, always use `importlib.util.find_spec("odoo.addons.<module>")` guard, AND remove the module from `__manifest__.py` `depends`.

---

## 4. Docker `ports:` vs `expose:` on Shared Servers

**The goal:** Run 6 Docker services alongside other services (N8N, Dokploy) on the same Hetzner VPS.

### The Error

```
Bind for 0.0.0.0:8000 failed: port is already allocated
```

Container status: `Created` (never starts).

### Root Cause

`docker-compose.yml` had:

```yaml
ports:
  - "8000:8000"   # ai-service
  - "3000:3000"   # dashboard
```

But port 8000 was already used by N8N and port 3000 by Dokploy's UI on the host.

### The Fix

```yaml
expose:
  - "8000"   # internal only, Traefik routes to it
```

`expose:` makes the port available within the Docker network but does NOT bind to the host. Traefik (running on the host) routes external traffic to containers via the Docker network.

**Rule:** On shared servers with a reverse proxy (Traefik/Nginx), NEVER use `ports:`. Always use `expose:` and let the proxy handle external routing.

---

## 5. Next.js Standalone `HOSTNAME` Binding

**The goal:** Dashboard accessible via Traefik on the Docker overlay network.

### The Error

AI API worked fine through Traefik, but dashboard returned `502 Bad Gateway`.

```bash
# From inside the Traefik container:
wget http://dashboard-container:3000/
# Connection refused
```

### Root Cause

Next.js standalone mode (`output: 'standalone'` in `next.config.js`) binds to the container's hostname by default. The container's `HOSTNAME` env var is set to the container ID (e.g., `bc7d5465669a`). This means Next.js only listens on the loopback interface of that specific hostname -- not on all network interfaces.

When Traefik tries to connect via the overlay network IP (`10.0.1.157:3000`), there's nothing listening on that interface.

The AI service (FastAPI/uvicorn) doesn't have this problem because uvicorn defaults to `0.0.0.0`.

### The Fix

```dockerfile
ENV HOSTNAME=0.0.0.0
```

Forces Next.js standalone to listen on all interfaces.

**Rule:** Next.js standalone + Docker always needs `ENV HOSTNAME=0.0.0.0` in the Dockerfile. This is not documented prominently in Next.js docs but is critical for any multi-network Docker setup.

---

## 6. Docker Compose Project Name in Dokploy

**The goal:** Update running containers managed by Dokploy via SSH.

### The Error

After running `docker compose up -d --force-recreate`, there were suddenly 12 containers instead of 6:

```
code-ai-service-1                              Up 21 seconds
code-dashboard-1                               Up 21 seconds
compose-navigate-haptic-matrix-2qe6ph-ai-service-1   Up 2 hours
compose-navigate-haptic-matrix-2qe6ph-dashboard-1    Up 2 hours
```

### Root Cause

Docker Compose uses the directory name as the default project name. The code lives in `/etc/dokploy/compose/compose-navigate-haptic-matrix-2qe6ph/code/`, so the default project name is `code`. But Dokploy uses `compose-navigate-haptic-matrix-2qe6ph` as the project name.

Running `docker compose up` without `-p` creates a completely separate stack with different container names, networks, and volumes -- leaving the old Dokploy containers still running.

### The Fix

```bash
# ALWAYS specify the Dokploy project name
docker compose -p compose-navigate-haptic-matrix-2qe6ph up -d --force-recreate

# If you already created duplicates, clean them up:
docker compose -p code down
```

**Rule:** When deploying via SSH on a Dokploy server, always use `-p <dokploy-project-name>`. Find the project name from `docker ps` (it's the container name prefix).

---

## 7. Traefik Routing After Manual Container Recreation

**The goal:** External domains route to the freshly recreated containers.

### The Error

All containers running and healthy. `curl https://odoo-ai-api-*.traefik.me/health` returns `404 page not found` (Traefik's 404, not the backend's).

### Root Cause (Two Issues)

**Issue A: Network.** Traefik's Docker provider is configured to discover services on `dokploy-network` (a Docker Swarm overlay network). When containers are recreated via `docker compose up`, they're only on the compose default network (`compose-navigate-haptic-matrix-2qe6ph_default`). Traefik can't see them.

**Issue B: Labels.** Dokploy normally adds Traefik labels to containers during its deploy process. When deploying via SSH, no labels are added. Traefik's Docker provider has `exposedByDefault: false`, so unlabeled containers are invisible.

### The Fix (Two Parts)

**Part 1: Connect containers to the overlay network:**

```bash
docker network connect dokploy-network compose-navigate-haptic-matrix-2qe6ph-ai-service-1
docker network connect dokploy-network compose-navigate-haptic-matrix-2qe6ph-dashboard-1
```

**Part 2: Create a file-based Traefik dynamic config** (since we can't add labels to running containers):

```bash
cat > /etc/dokploy/traefik/dynamic/odoo-ai-platform.yml << 'EOF'
http:
  routers:
    odoo-ai-api:
      rule: Host(`odoo-ai-api-65-21-62-16.traefik.me`)
      service: odoo-ai-api-service
      entryPoints: [web]
    odoo-ai-api-secure:
      rule: Host(`odoo-ai-api-65-21-62-16.traefik.me`)
      service: odoo-ai-api-service
      entryPoints: [websecure]
      tls: { certResolver: letsencrypt }
  services:
    odoo-ai-api-service:
      loadBalancer:
        servers:
          - url: http://compose-navigate-haptic-matrix-2qe6ph-ai-service-1:8000
EOF
```

Traefik watches this directory and picks up changes automatically (no restart needed).

**Rule:** After SSH deploy, always (1) connect containers to `dokploy-network`, and (2) verify the Traefik dynamic config file exists. This must be done after every `docker compose up --force-recreate`.

---

## 8. Traefik Entrypoints: `web` vs `websecure`

**The goal:** Endpoints accessible via both HTTP and HTTPS.

### The Error

After creating the Traefik config file, `curl http://...` worked but `curl https://...` still returned 404.

### Root Cause

The initial config only specified `entryPoints: [web]` which is port 80 (HTTP). HTTPS traffic arrives on `websecure` (port 443) which had no matching router.

### The Fix

Add separate routers for each entrypoint:

```yaml
routers:
  odoo-ai-api:
    entryPoints: [web]          # HTTP
  odoo-ai-api-secure:
    entryPoints: [websecure]    # HTTPS
    tls:
      certResolver: letsencrypt
```

**Rule:** In Traefik, always define two routers per domain -- one for `web` (80) and one for `websecure` (443) with TLS. A single router can't serve both.

---

## 9. Next.js `NEXT_PUBLIC_*` Build-Time vs Runtime

**The goal:** Dashboard makes API calls to the correct backend URL.

### The Error

Dashboard built successfully, but all API calls went to `http://localhost:8000` instead of the production API URL.

### Root Cause

Next.js `NEXT_PUBLIC_*` environment variables are **inlined at build time**, not read at runtime. Setting them in `docker-compose.yml` `environment:` section has no effect because the build already happened in the Dockerfile.

### The Fix

Pass the URL as a **build argument**:

```dockerfile
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
```

```yaml
# docker-compose.yml
dashboard:
  build:
    args:
      NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}
  environment:
    - NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}  # for any runtime reads
```

**Rule:** `NEXT_PUBLIC_*` vars must be passed as Docker build args (`ARG` + `ENV` in Dockerfile, `args:` in compose). Runtime `environment:` alone is not enough.

---

## 10. Odoo Admin Username Is Not "admin"

**The goal:** AI service connects to Odoo via XML-RPC for automation queries.

### The Error

Every Odoo XML-RPC call returned `<Fault 3: 'Access Denied'>`, even for simple `search_read` calls.

### Root Cause

The `ODOO_USERNAME` was set to `admin` (the Odoo internal username). But this Odoo instance was configured with email-based login. The actual admin username is the email address: `alfailakawi1000@gmail.com`.

Odoo's XML-RPC `authenticate` method requires the login credential that the user types into the login form -- which could be a username or an email depending on the Odoo configuration.

### The Fix

```bash
ODOO_USERNAME=alfailakawi1000@gmail.com  # NOT "admin"
```

**Rule:** Always verify the Odoo admin login credential by checking what you type into the web login form. It's not always `admin`.

---

## 11. SQLAlchemy `AutomationType` Enum Mismatch

**The goal:** Create audit logs for new Phase 1 automation types (month_end, deduplication, etc.).

### The Error

```
DataError: invalid input value for enum automationtype: "MONTH_END"
```

### Root Cause

The PostgreSQL `automationtype` enum was created by the initial migration with only the Phase 0 values (accounting, crm, sales, etc.). Phase 1 added new values to the Python `AutomationType` enum but the Alembic migration to extend the DB enum either hadn't run or had been rolled back when migration 002 failed.

### The Fix

Run migration 001 (which adds the new enum values):

```bash
docker exec <ai-service> alembic upgrade head
```

Or add values directly if migrations are problematic:

```sql
ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'MONTH_END';
ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'DEDUPLICATION';
ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'CREDIT_MANAGEMENT';
ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'FORECASTING';
ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'REPORTING';
ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'DOCUMENT_PROCESSING';
```

**Rule:** When adding values to a Python enum that maps to a PostgreSQL enum, always create a corresponding Alembic migration. PostgreSQL enums are not auto-synced.

---

## 12. Docker Build Exhausts Server Resources

**The goal:** Build Docker images on the Hetzner VPS without crashing other services.

### The Error

During `docker compose build`, all services (Dokploy, Traefik, N8N, even SSH) became unresponsive for several minutes.

### Root Cause

The VPS has limited RAM/CPU. Building multiple Docker images concurrently (especially Node.js `npm install` and Python `pip install`) exhausts memory, causing the OOM killer to intervene or swap to thrash.

### Mitigation

- Build one service at a time: `docker compose build ai-service` then `docker compose build dashboard`
- Use `--no-cache` only when truly needed (cached builds are much faster)
- Create a Hetzner snapshot before deploying (recovery option if build crashes the server)
- Deploy during off-hours
- Consider a larger VPS for production

**Rule:** On resource-constrained servers, never build all images in parallel. Sequential builds with caching are safer.

---

## Summary: Error Prevention Checklist

Before deploying, verify:

- [ ] `celery_app.conf.update()` includes `include=["app.tasks.celery_tasks"]`
- [ ] Odoo callback routes use `type="http"` not `type="json"`
- [ ] Optional Odoo modules guarded with `importlib.util.find_spec()`
- [ ] `docker-compose.yml` uses `expose:` not `ports:` for proxied services
- [ ] Dashboard Dockerfile has `ENV HOSTNAME=0.0.0.0`
- [ ] `NEXT_PUBLIC_*` vars passed as Docker build `args:` not just `environment:`
- [ ] `docker compose -p <dokploy-project-name>` used for SSH deploys
- [ ] Containers connected to `dokploy-network` after recreation
- [ ] Traefik dynamic config exists at `/etc/dokploy/traefik/dynamic/odoo-ai-platform.yml`
- [ ] Traefik config has both `web` and `websecure` entrypoints
- [ ] `ODOO_USERNAME` is the email login, not `admin`
- [ ] Alembic migrations run after deploying schema changes
