"""
Cross-Entity Deduplication — fuzzy matching for contacts, leads, products, vendors.

Scans Odoo entities in batches, groups duplicates by similarity score,
suggests merges with master record selection, and blocks duplicates on creation.
"""

from datetime import datetime
from typing import Any

import structlog
from rapidfuzz import fuzz

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

ENTITY_CONFIGS: dict[str, dict[str, Any]] = {
    "res.partner": {
        "label": "contacts",
        "match_fields": ["name", "email", "phone", "vat"],
        "fetch_fields": ["name", "email", "phone", "mobile", "vat", "street", "city", "country_id", "is_company", "active", "customer_rank", "supplier_rank"],
        "domain": [("active", "=", True)],
        "weights": {"name": 0.35, "email": 0.30, "phone": 0.20, "vat": 0.15},
    },
    "crm.lead": {
        "label": "leads",
        "match_fields": ["contact_name", "email_from", "phone", "partner_name"],
        "fetch_fields": ["contact_name", "email_from", "phone", "partner_name", "name", "stage_id", "user_id", "active"],
        "domain": [("active", "=", True)],
        "weights": {"contact_name": 0.30, "email_from": 0.35, "phone": 0.20, "partner_name": 0.15},
    },
    "product.template": {
        "label": "products",
        "match_fields": ["name", "default_code", "barcode"],
        "fetch_fields": ["name", "default_code", "barcode", "categ_id", "list_price", "type", "active"],
        "domain": [("active", "=", True)],
        "weights": {"name": 0.40, "default_code": 0.35, "barcode": 0.25},
    },
}

NAME_SIMILARITY_THRESHOLD = 70
EMAIL_SIMILARITY_THRESHOLD = 90
OVERALL_DUPLICATE_THRESHOLD = 0.65
BATCH_SIZE = 500

DEDUP_PROMPT = """You are a data quality AI for Odoo ERP. Analyze a group of potential
duplicate records and recommend the best master record to keep. Consider: record
completeness, creation date, activity history, and data freshness. Return your
recommendation as structured output."""

DEDUP_TOOLS = [
    {
        "name": "dedup_recommendation",
        "description": "Recommend which record to keep as master in a duplicate group",
        "input_schema": {
            "type": "object",
            "properties": {
                "master_record_id": {
                    "type": "integer",
                    "description": "ID of the record to keep as master",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence in dedup recommendation 0.0-1.0",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this record was chosen as master",
                },
                "merge_strategy": {
                    "type": "string",
                    "enum": ["keep_master", "merge_fields", "manual_review"],
                    "description": "How to handle the merge",
                },
            },
            "required": ["master_record_id", "confidence", "reasoning", "merge_strategy"],
        },
    }
]


class DeduplicationAutomation(BaseAutomation):
    """Cross-entity deduplication with fuzzy matching and AI-powered merge recommendations."""

    automation_type = "deduplication"
    watched_models = ["res.partner", "crm.lead", "product.template"]

    def run_scan(self, scan_type: str) -> dict[str, Any]:
        """
        Run a deduplication scan for a given entity type.
        Returns scan results with duplicate groups.
        """
        config = ENTITY_CONFIGS.get(scan_type)
        if not config:
            return {"error": f"Unknown scan type: {scan_type}", "groups": []}

        records = self._fetch_all_records(scan_type, config)
        if not records:
            return {
                "scan_type": scan_type,
                "total_records": 0,
                "groups": [],
                "duplicates_found": 0,
            }

        groups = self._find_duplicate_groups(records, config)

        return {
            "scan_type": scan_type,
            "total_records": len(records),
            "groups": groups,
            "duplicates_found": sum(len(g["record_ids"]) for g in groups),
        }

    def run_full_scan(self) -> dict[str, Any]:
        """Run dedup scans across all configured entity types."""
        results = {}
        for scan_type in ENTITY_CONFIGS:
            results[scan_type] = self.run_scan(scan_type)
        total_groups = sum(len(r["groups"]) for r in results.values())
        total_dupes = sum(r["duplicates_found"] for r in results.values())
        return {
            "entity_results": results,
            "total_groups": total_groups,
            "total_duplicates": total_dupes,
        }

    def check_duplicate_on_create(
        self, model: str, values: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Real-time duplicate check when a new record is being created.
        Returns a list of potential duplicates with similarity scores.
        """
        config = ENTITY_CONFIGS.get(model)
        if not config:
            return []

        existing = self._fetch_all_records(model, config)
        if not existing:
            return []

        new_record = {"id": 0, **values}
        matches = []

        for record in existing:
            score, matched_fields = self._compute_similarity(new_record, record, config)
            if score >= OVERALL_DUPLICATE_THRESHOLD:
                matches.append({
                    "record_id": record["id"],
                    "record_name": self._get_display_name(record, model),
                    "similarity_score": round(score, 4),
                    "matched_fields": matched_fields,
                })

        matches.sort(key=lambda m: m["similarity_score"], reverse=True)
        return matches[:10]

    def recommend_master(self, group: dict[str, Any]) -> dict[str, Any]:
        """Use AI to recommend the best master record for a duplicate group."""
        records = group.get("records", [])
        if not records:
            return {"error": "No records in group"}

        record_descriptions = []
        for r in records:
            desc = f"Record #{r['id']}: {r.get('name', r.get('contact_name', 'N/A'))}"
            for field, val in r.items():
                if field != "id" and val:
                    desc += f", {field}={val}"
            record_descriptions.append(desc)

        try:
            result = self.analyze_with_tools(
                system_prompt=DEDUP_PROMPT,
                user_message=f"Potential duplicates:\n" + "\n".join(record_descriptions),
                tools=DEDUP_TOOLS,
            )
            return result.get("tool_input", {})
        except Exception as exc:
            logger.warning("dedup_ai_recommendation_failed", error=str(exc))
            return self._heuristic_master_selection(records)

    # ------------------------------------------------------------------
    # Core matching engine
    # ------------------------------------------------------------------

    def _find_duplicate_groups(
        self, records: list[dict], config: dict
    ) -> list[dict[str, Any]]:
        """Find groups of duplicate records using pairwise fuzzy comparison."""
        n = len(records)
        parent: dict[int, int] = {r["id"]: r["id"] for r in records}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        pair_scores: dict[tuple[int, int], tuple[float, list[str]]] = {}

        for i in range(n):
            for j in range(i + 1, n):
                score, matched_fields = self._compute_similarity(records[i], records[j], config)
                if score >= OVERALL_DUPLICATE_THRESHOLD:
                    union(records[i]["id"], records[j]["id"])
                    pair_scores[(records[i]["id"], records[j]["id"])] = (score, matched_fields)

        clusters: dict[int, list[dict]] = {}
        for record in records:
            root = find(record["id"])
            clusters.setdefault(root, []).append(record)

        groups = []
        for root, members in clusters.items():
            if len(members) < 2:
                continue

            record_ids = [m["id"] for m in members]
            best_score = 0.0
            all_match_fields: set[str] = set()

            for i, r1 in enumerate(members):
                for r2 in members[i + 1:]:
                    key = (min(r1["id"], r2["id"]), max(r1["id"], r2["id"]))
                    if key in pair_scores:
                        s, mf = pair_scores[key]
                        best_score = max(best_score, s)
                        all_match_fields.update(mf)

            master_id = self._heuristic_master_selection(members).get("master_record_id", record_ids[0])

            groups.append({
                "odoo_model": config.get("label", "unknown"),
                "record_ids": record_ids,
                "master_record_id": master_id,
                "similarity_score": round(best_score, 4),
                "match_fields": list(all_match_fields),
                "records": members,
            })

        groups.sort(key=lambda g: g["similarity_score"], reverse=True)
        return groups

    def _compute_similarity(
        self, record_a: dict, record_b: dict, config: dict
    ) -> tuple[float, list[str]]:
        """
        Compute similarity between two records using two strategies:
        1. Strong signal: any exact identifier match (email, phone, VAT, code, barcode) = duplicate.
        2. Weighted composite: normalize by weight of fields that passed their threshold.

        Returns (score, list_of_matched_field_names).
        """
        weights = config["weights"]
        matched_weight = 0.0
        matched_score = 0.0
        matched_fields: list[str] = []
        has_comparable_field = False

        for field, weight in weights.items():
            val_a = self._normalize_value(record_a.get(field))
            val_b = self._normalize_value(record_b.get(field))

            if not val_a or not val_b:
                continue

            has_comparable_field = True

            if field in ("email", "email_from"):
                sim = self._email_similarity(val_a, val_b)
            elif field in ("phone", "mobile"):
                sim = self._phone_similarity(val_a, val_b)
            elif field in ("vat", "default_code", "barcode"):
                sim = 1.0 if val_a == val_b else 0.0
            else:
                sim = fuzz.token_sort_ratio(val_a, val_b) / 100.0

            # Strong signal: exact match on any identifier field is enough
            identifier_fields = ("email", "email_from", "phone", "mobile", "vat", "default_code", "barcode")
            if field in identifier_fields and sim >= 0.95:
                return 1.0, [field]

            threshold = EMAIL_SIMILARITY_THRESHOLD / 100.0 if "email" in field else NAME_SIMILARITY_THRESHOLD / 100.0
            if sim >= threshold:
                matched_score += weight * sim
                matched_weight += weight
                matched_fields.append(field)

        if not has_comparable_field or matched_weight == 0:
            return 0.0, []

        normalized_score = matched_score / matched_weight
        return normalized_score, matched_fields

    # ------------------------------------------------------------------
    # Field-specific similarity functions
    # ------------------------------------------------------------------

    @staticmethod
    def _email_similarity(a: str, b: str) -> float:
        a_clean = a.lower().strip()
        b_clean = b.lower().strip()
        if a_clean == b_clean:
            return 1.0
        a_parts = a_clean.split("@")
        b_parts = b_clean.split("@")
        if len(a_parts) == 2 and len(b_parts) == 2:
            if a_parts[1] == b_parts[1]:
                local_sim = fuzz.ratio(a_parts[0], b_parts[0]) / 100.0
                return 0.5 + 0.5 * local_sim
        return fuzz.ratio(a_clean, b_clean) / 100.0

    @staticmethod
    def _phone_similarity(a: str, b: str) -> float:
        a_digits = "".join(c for c in a if c.isdigit())
        b_digits = "".join(c for c in b if c.isdigit())
        if not a_digits or not b_digits:
            return 0.0
        if a_digits == b_digits:
            return 1.0
        if a_digits.endswith(b_digits) or b_digits.endswith(a_digits):
            return 0.95
        if len(a_digits) >= 7 and len(b_digits) >= 7:
            if a_digits[-7:] == b_digits[-7:]:
                return 0.90
        return 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_value(val: Any) -> str:
        if val is None or val is False:
            return ""
        if isinstance(val, (list, tuple)):
            return str(val[1]) if len(val) >= 2 else str(val[0]) if val else ""
        return str(val).strip()

    @staticmethod
    def _get_display_name(record: dict, model: str) -> str:
        if model == "crm.lead":
            return record.get("contact_name") or record.get("partner_name") or record.get("name", "")
        return record.get("name", "")

    @staticmethod
    def _heuristic_master_selection(records: list[dict]) -> dict[str, Any]:
        """Pick the most complete record as master based on field fill rate."""
        best_id = records[0]["id"]
        best_fill = 0

        for record in records:
            fill = sum(1 for v in record.values() if v and v is not False)
            if fill > best_fill:
                best_fill = fill
                best_id = record["id"]

        return {
            "master_record_id": best_id,
            "confidence": 0.7,
            "reasoning": "Selected record with most complete data",
            "merge_strategy": "keep_master",
        }

    def _fetch_all_records(self, model: str, config: dict) -> list[dict]:
        """Fetch records from Odoo for dedup scanning."""
        return self.fetch_related_records(
            model,
            config["domain"],
            fields=config["fetch_fields"],
            limit=BATCH_SIZE,
        )

    # ------------------------------------------------------------------
    # Webhook handlers — real-time duplicate detection on create
    # ------------------------------------------------------------------

    def on_create(self, model: str, record_id: int, values: dict[str, Any]) -> AutomationResult:
        """Check for duplicates when a new record is created."""
        matches = self.check_duplicate_on_create(model, values)
        if matches:
            return AutomationResult(
                success=True,
                action="duplicate_detected",
                model=model,
                record_id=record_id,
                confidence=matches[0]["similarity_score"],
                reasoning=f"Found {len(matches)} potential duplicate(s): {', '.join(str(m['record_id']) for m in matches[:3])}",
                changes_made={"duplicates": matches},
                needs_approval=True,
            )
        return AutomationResult(
            success=True,
            action="no_duplicates",
            model=model,
            record_id=record_id,
            confidence=1.0,
            reasoning="No duplicates found",
        )
