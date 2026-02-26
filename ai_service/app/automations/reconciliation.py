"""
Enhanced Bank Reconciliation — fuzzy matching, session memory, learned rules.

Uses rapidfuzz for partial reference matching and rounding-tolerant amount comparison.
Sessions persist in the database so users can resume across browser sessions.
Learned rules accumulate per journal and improve matching over time.
"""

import json
from datetime import datetime
from typing import Any

import structlog
from rapidfuzz import fuzz, process as rfprocess

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult, MatchSuggestion

logger = structlog.get_logger()

AMOUNT_TOLERANCE_ABS = 0.50
AMOUNT_TOLERANCE_PCT = 0.02
FUZZY_REF_THRESHOLD = 70
HIGH_CONFIDENCE_THRESHOLD = 0.90

RECONCILIATION_PROMPT = """You are an expert bank reconciliation AI assistant.
Match bank statement lines to accounting entries (invoices, bills, payments).
Consider: exact and partial reference matches, amount proximity, partner name similarity,
date proximity, split payment scenarios, and rounding differences.
Return structured match suggestions with clear reasoning."""

RECONCILIATION_TOOLS = [
    {
        "name": "match_suggestion",
        "description": "Suggest a match between a bank line and an accounting entry",
        "input_schema": {
            "type": "object",
            "properties": {
                "bank_line_id": {
                    "type": "integer",
                    "description": "Bank statement line ID",
                },
                "matched_entry_id": {
                    "type": "integer",
                    "description": "Matched account.move ID (0 if no match)",
                },
                "confidence": {
                    "type": "number",
                    "description": "Match confidence 0.0-1.0",
                },
                "match_type": {
                    "type": "string",
                    "enum": ["exact", "fuzzy", "partial", "learned", "none"],
                    "description": "Type of match",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this match was suggested",
                },
            },
            "required": ["bank_line_id", "matched_entry_id", "confidence", "match_type", "reasoning"],
        },
    }
]


class ReconciliationAutomation(BaseAutomation):
    """Enhanced bank reconciliation with fuzzy matching and session memory."""

    automation_type = "accounting"
    watched_models = ["account.bank.statement.line"]

    def start_session(
        self, journal_id: int, user_id: str = "admin"
    ) -> dict[str, Any]:
        """
        Start a reconciliation session: load bank lines and candidates,
        run fuzzy matching, return summary.
        """
        bank_lines = self._fetch_unreconciled_lines(journal_id)
        candidates = self._fetch_candidate_entries(journal_id)
        learned_rules = self._load_learned_rules(journal_id)

        suggestions = self._generate_suggestions(bank_lines, candidates, learned_rules)

        auto_matchable = sum(1 for s in suggestions if s.confidence >= HIGH_CONFIDENCE_THRESHOLD)
        needs_review = len(suggestions) - auto_matchable

        return {
            "total_lines": len(bank_lines),
            "auto_matchable": auto_matchable,
            "needs_review": needs_review,
            "suggestions": suggestions,
            "bank_lines": bank_lines,
            "candidates": candidates,
        }

    def get_suggestions(
        self,
        journal_id: int,
        learned_rules: list[dict] | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[MatchSuggestion], int]:
        """Regenerate suggestions for a journal with optional learned rules."""
        bank_lines = self._fetch_unreconciled_lines(journal_id)
        candidates = self._fetch_candidate_entries(journal_id)
        rules = learned_rules or self._load_learned_rules(journal_id)
        suggestions = self._generate_suggestions(bank_lines, candidates, rules)
        total = len(suggestions)
        start = (page - 1) * limit
        return suggestions[start:start + limit], total

    # ------------------------------------------------------------------
    # Core matching engine
    # ------------------------------------------------------------------

    def _generate_suggestions(
        self,
        bank_lines: list[dict],
        candidates: list[dict],
        learned_rules: list[dict],
    ) -> list[MatchSuggestion]:
        """Generate match suggestions using multi-signal scoring."""
        suggestions: list[MatchSuggestion] = []
        used_candidate_ids: set[int] = set()

        for line in bank_lines:
            best = self._find_best_match(line, candidates, learned_rules, used_candidate_ids)
            suggestions.append(best)
            if best.matched_entry_id:
                used_candidate_ids.add(best.matched_entry_id)

        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions

    def _find_best_match(
        self,
        bank_line: dict,
        candidates: list[dict],
        learned_rules: list[dict],
        used_ids: set[int],
    ) -> MatchSuggestion:
        """Score all candidates against a bank line and return the best match."""
        line_id = bank_line.get("id", 0)
        line_ref = str(bank_line.get("payment_ref") or "").strip()
        line_amount = float(bank_line.get("amount") or 0)
        line_partner = self._extract_partner_name(bank_line.get("partner_id"))

        best_score = 0.0
        best_candidate: dict | None = None
        best_type = "none"
        best_reasoning = "No matching entry found"

        for cand in candidates:
            if cand["id"] in used_ids:
                continue

            score, match_type, reasoning = self._score_candidate(
                line_ref, line_amount, line_partner, cand, learned_rules
            )
            if score > best_score:
                best_score = score
                best_candidate = cand
                best_type = match_type
                best_reasoning = reasoning

        if best_candidate and best_score >= 0.3:
            return MatchSuggestion(
                bank_line_id=line_id,
                bank_ref=line_ref,
                bank_amount=line_amount,
                matched_entry_id=best_candidate["id"],
                matched_entry_ref=best_candidate.get("name", ""),
                matched_amount=float(best_candidate.get("amount_residual") or best_candidate.get("amount_total") or 0),
                confidence=round(min(best_score, 1.0), 3),
                match_type=best_type,
                reasoning=best_reasoning,
            )

        return MatchSuggestion(
            bank_line_id=line_id,
            bank_ref=line_ref,
            bank_amount=line_amount,
            confidence=0.0,
            match_type="none",
            reasoning="No matching entry found",
        )

    def _score_candidate(
        self,
        line_ref: str,
        line_amount: float,
        line_partner: str,
        candidate: dict,
        learned_rules: list[dict],
    ) -> tuple[float, str, str]:
        """
        Multi-signal scoring: reference similarity + amount proximity +
        partner match + learned rule bonus.
        Returns (score, match_type, reasoning).
        """
        cand_ref = str(candidate.get("ref") or candidate.get("name") or "").strip()
        cand_amount = abs(float(candidate.get("amount_residual") or candidate.get("amount_total") or 0))
        cand_partner = self._extract_partner_name(candidate.get("partner_id"))
        abs_line = abs(line_amount)

        reasons: list[str] = []

        # --- Reference similarity (0-0.4) ---
        ref_score = 0.0
        if line_ref and cand_ref:
            token_ratio = fuzz.token_sort_ratio(line_ref.lower(), cand_ref.lower())
            if token_ratio == 100:
                ref_score = 0.4
                reasons.append(f"Exact reference match: '{cand_ref}'")
            elif token_ratio >= FUZZY_REF_THRESHOLD:
                ref_score = 0.25 + 0.15 * ((token_ratio - FUZZY_REF_THRESHOLD) / (100 - FUZZY_REF_THRESHOLD))
                reasons.append(f"Fuzzy reference match ({token_ratio}%): '{cand_ref}'")
            if self._ref_contained(line_ref, cand_ref):
                ref_score = max(ref_score, 0.35)
                if not reasons or "reference" not in reasons[-1].lower():
                    reasons.append(f"Reference substring match: '{cand_ref}' in '{line_ref}'")

        # --- Amount proximity (0-0.35) ---
        amount_score = 0.0
        if abs_line > 0 and cand_amount > 0:
            diff = abs(abs_line - cand_amount)
            pct_diff = diff / max(abs_line, cand_amount)
            if diff < 0.01:
                amount_score = 0.35
                reasons.append(f"Exact amount match: {cand_amount:.2f}")
            elif diff <= AMOUNT_TOLERANCE_ABS:
                amount_score = 0.30
                reasons.append(f"Amount within rounding tolerance (diff {diff:.2f})")
            elif pct_diff <= AMOUNT_TOLERANCE_PCT:
                amount_score = 0.28
                reasons.append(f"Amount within {pct_diff*100:.1f}% tolerance")
            elif pct_diff <= 0.10:
                amount_score = 0.15 * (1 - pct_diff / 0.10)
                reasons.append(f"Partial amount match ({pct_diff*100:.1f}% difference)")

        # --- Partner match (0-0.15) ---
        partner_score = 0.0
        if line_partner and cand_partner:
            p_ratio = fuzz.token_sort_ratio(line_partner.lower(), cand_partner.lower())
            if p_ratio >= 85:
                partner_score = 0.15
                reasons.append(f"Partner match: '{cand_partner}'")
            elif p_ratio >= 65:
                partner_score = 0.08
                reasons.append(f"Partial partner match ({p_ratio}%): '{cand_partner}'")

        # --- Learned rule bonus (0-0.10) ---
        learned_bonus = 0.0
        for rule in learned_rules:
            if self._rule_applies(rule, line_ref, line_partner, cand_ref, cand_partner):
                learned_bonus = 0.10
                reasons.append("Matches a previously learned rule")
                break

        total = ref_score + amount_score + partner_score + learned_bonus

        match_type = "none"
        if total >= 0.90:
            match_type = "exact"
        elif learned_bonus > 0 and total >= 0.50:
            match_type = "learned"
        elif ref_score >= 0.25 or amount_score >= 0.28:
            match_type = "fuzzy"
        elif total >= 0.30:
            match_type = "partial"

        reasoning = "; ".join(reasons) if reasons else "Low overall match score"
        return total, match_type, reasoning

    # ------------------------------------------------------------------
    # Learned rules
    # ------------------------------------------------------------------

    def create_learned_rule(
        self,
        bank_ref: str,
        bank_partner: str,
        entry_ref: str,
        entry_partner: str,
    ) -> dict:
        """Create a rule from a manual match to improve future matching."""
        return {
            "bank_ref_pattern": bank_ref.strip().lower() if bank_ref else "",
            "bank_partner_pattern": bank_partner.strip().lower() if bank_partner else "",
            "entry_ref_pattern": entry_ref.strip().lower() if entry_ref else "",
            "entry_partner_pattern": entry_partner.strip().lower() if entry_partner else "",
            "created_at": datetime.utcnow().isoformat(),
        }

    def _rule_applies(
        self,
        rule: dict,
        line_ref: str,
        line_partner: str,
        cand_ref: str,
        cand_partner: str,
    ) -> bool:
        """Check if a learned rule matches the current line+candidate pair."""
        brp = rule.get("bank_ref_pattern", "")
        bpp = rule.get("bank_partner_pattern", "")
        erp = rule.get("entry_ref_pattern", "")
        epp = rule.get("entry_partner_pattern", "")

        ref_match = (
            not brp
            or fuzz.token_sort_ratio(brp, line_ref.lower()) >= 80
        )
        partner_match = (
            not bpp
            or fuzz.token_sort_ratio(bpp, line_partner.lower()) >= 80
        )
        entry_ref_match = (
            not erp
            or fuzz.token_sort_ratio(erp, cand_ref.lower()) >= 80
        )
        entry_partner_match = (
            not epp
            or fuzz.token_sort_ratio(epp, cand_partner.lower()) >= 80
        )
        return ref_match and partner_match and entry_ref_match and entry_partner_match

    def _load_learned_rules(self, journal_id: int) -> list[dict]:
        """Load learned rules from the most recent session for this journal."""
        from app.models.audit import ReconciliationSession, get_db_session

        try:
            with get_db_session() as session:
                prev = (
                    session.query(ReconciliationSession)
                    .filter(
                        ReconciliationSession.journal_id == journal_id,
                        ReconciliationSession.status == "completed",
                    )
                    .order_by(ReconciliationSession.completed_at.desc())
                    .first()
                )
                if prev and prev.learned_rules:
                    return prev.learned_rules
        except Exception as exc:
            logger.warning("load_learned_rules_failed", error=str(exc))
        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_partner_name(partner_field: Any) -> str:
        if isinstance(partner_field, str):
            return partner_field
        if isinstance(partner_field, (list, tuple)) and len(partner_field) >= 2:
            return str(partner_field[1])
        return ""

    @staticmethod
    def _ref_contained(ref_a: str, ref_b: str) -> bool:
        """Check if one reference is a substring of the other (case-insensitive)."""
        a, b = ref_a.lower().strip(), ref_b.lower().strip()
        return len(a) >= 3 and len(b) >= 3 and (a in b or b in a)

    def _fetch_unreconciled_lines(self, journal_id: int) -> list[dict]:
        return self.fetch_related_records(
            "account.bank.statement.line",
            [
                ("journal_id", "=", journal_id),
                ("is_reconciled", "=", False),
            ],
            fields=["date", "payment_ref", "partner_id", "amount", "journal_id"],
            limit=200,
        )

    def _fetch_candidate_entries(self, journal_id: int) -> list[dict]:
        """Fetch open invoices/bills that could match bank lines."""
        return self.fetch_related_records(
            "account.move",
            [
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("amount_residual", ">", 0),
            ],
            fields=[
                "name", "ref", "partner_id", "amount_total", "amount_residual",
                "invoice_date", "move_type",
            ],
            limit=200,
        )
