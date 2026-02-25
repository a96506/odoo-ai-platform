"""
Accounting automations: transaction categorization, bank reconciliation, anomaly detection.
"""

import json
from typing import Any

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert accounting AI assistant integrated with Odoo ERP.
You analyze financial transactions and make precise decisions.
Always provide confidence scores and clear reasoning.
When matching transactions to invoices, consider: amount, date proximity, partner name,
payment reference patterns, and partial payment possibilities."""

CATEGORIZE_TOOLS = [
    {
        "name": "categorize_transaction",
        "description": "Categorize a bank transaction into the correct accounting category based on its description, amount, and partner",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "integer",
                    "description": "The Odoo account.account ID to assign",
                },
                "category": {
                    "type": "string",
                    "description": "Human-readable category name",
                },
                "partner_id": {
                    "type": "integer",
                    "description": "Matched partner ID if identified, 0 if unknown",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score between 0.0 and 1.0",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of the categorization decision",
                },
            },
            "required": ["account_id", "category", "partner_id", "confidence", "reasoning"],
        },
    }
]

RECONCILE_TOOLS = [
    {
        "name": "reconcile_transaction",
        "description": "Match a bank statement line to one or more invoices/bills for reconciliation",
        "input_schema": {
            "type": "object",
            "properties": {
                "matched_move_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of account.move IDs that match this transaction",
                },
                "match_type": {
                    "type": "string",
                    "enum": ["full", "partial", "none"],
                    "description": "Whether the match is full, partial, or no match found",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score between 0.0 and 1.0",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why these invoices/bills match this transaction",
                },
            },
            "required": ["matched_move_ids", "match_type", "confidence", "reasoning"],
        },
    }
]

ANOMALY_TOOLS = [
    {
        "name": "flag_anomaly",
        "description": "Flag a transaction as potentially anomalous or approve it as normal",
        "input_schema": {
            "type": "object",
            "properties": {
                "is_anomaly": {
                    "type": "boolean",
                    "description": "True if the transaction appears anomalous",
                },
                "anomaly_type": {
                    "type": "string",
                    "enum": [
                        "unusual_amount",
                        "unusual_partner",
                        "unusual_timing",
                        "duplicate",
                        "missing_reference",
                        "none",
                    ],
                    "description": "Type of anomaly detected",
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Severity of the anomaly",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score between 0.0 and 1.0",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of why this is or isn't anomalous",
                },
            },
            "required": ["is_anomaly", "anomaly_type", "severity", "confidence", "reasoning"],
        },
    }
]


class AccountingAutomation(BaseAutomation):
    automation_type = "accounting"
    watched_models = ["account.move", "account.bank.statement.line"]

    def on_create_account_bank_statement_line(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a new bank statement line is created, categorize and try to reconcile."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False,
                action="categorize_transaction",
                model=model,
                record_id=record_id,
                reasoning="Record not found",
            )

        categorization = self._categorize_transaction(record)

        if categorization.get("confidence", 0) >= self.settings.default_confidence_threshold:
            reconciliation = self._reconcile_transaction(record)
            if reconciliation.get("match_type") != "none":
                return self._handle_reconciliation(model, record_id, record, reconciliation)

        return self._handle_categorization(model, record_id, categorization)

    def on_create_account_move(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a new invoice/bill is created, check for anomalies."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False,
                action="flag_anomaly",
                model=model,
                record_id=record_id,
                reasoning="Record not found",
            )
        return self._detect_anomaly(model, record_id, record)

    def on_write_account_move(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """Re-check anomalies when an invoice/bill is modified."""
        if "state" in values and values.get("state") == "posted":
            record = self.fetch_record_context(model, record_id)
            if record:
                return self._detect_anomaly(model, record_id, record)

        return AutomationResult(
            success=True,
            action="no_action",
            model=model,
            record_id=record_id,
            reasoning="No anomaly check needed for this update",
        )

    # --- Scheduled scans ---

    def scan_reconcile_transactions(self):
        """Periodically scan unreconciled bank statement lines."""
        unreconciled = self.fetch_related_records(
            "account.bank.statement.line",
            [("is_reconciled", "=", False)],
            fields=["date", "payment_ref", "partner_id", "amount", "journal_id"],
            limit=100,
        )
        logger.info("scanning_unreconciled", count=len(unreconciled))

        for line in unreconciled:
            try:
                result = self._reconcile_transaction(line)
                if result.get("match_type") != "none" and result.get("confidence", 0) >= self.settings.auto_approve_threshold:
                    self._execute_reconciliation(
                        line["id"], result["matched_move_ids"]
                    )
            except Exception as exc:
                logger.error("reconciliation_scan_error", record_id=line["id"], error=str(exc))

    # --- Internal methods ---

    def _categorize_transaction(self, record: dict) -> dict:
        accounts = self.fetch_related_records(
            "account.account",
            [("deprecated", "=", False)],
            fields=["id", "name", "code"],
            limit=100,
        )

        recent_transactions = self.fetch_related_records(
            "account.bank.statement.line",
            [("is_reconciled", "=", True)],
            fields=["payment_ref", "partner_id", "amount"],
            limit=50,
        )

        user_msg = f"""Categorize this bank transaction:

Transaction:
- Reference: {record.get('payment_ref', 'N/A')}
- Amount: {record.get('amount', 0)}
- Date: {record.get('date', 'N/A')}
- Partner: {record.get('partner_id', 'Unknown')}
- Journal: {record.get('journal_id', 'N/A')}

Available accounts:
{json.dumps(accounts[:50], indent=2, default=str)}

Recent categorized transactions for reference:
{json.dumps(recent_transactions[:20], indent=2, default=str)}"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, CATEGORIZE_TOOLS)
        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]
        return {"confidence": 0, "reasoning": "No categorization produced"}

    def _reconcile_transaction(self, record: dict) -> dict:
        amount = record.get("amount", 0)
        abs_amount = abs(amount) if amount else 0
        tolerance = abs_amount * 0.02

        domain = [
            ("state", "=", "posted"),
            ("payment_state", "in", ["not_paid", "partial"]),
            ("amount_residual", ">", 0),
        ]
        if amount > 0:
            domain.append(("move_type", "in", ["out_invoice", "out_refund"]))
        else:
            domain.append(("move_type", "in", ["in_invoice", "in_refund"]))

        candidates = self.fetch_related_records(
            "account.move",
            domain,
            fields=[
                "name", "partner_id", "amount_total", "amount_residual",
                "invoice_date", "ref", "move_type",
            ],
            limit=50,
        )

        user_msg = f"""Match this bank transaction to the correct invoice(s):

Transaction:
- Reference: {record.get('payment_ref', 'N/A')}
- Amount: {amount}
- Date: {record.get('date', 'N/A')}
- Partner: {record.get('partner_id', 'Unknown')}

Candidate invoices/bills:
{json.dumps(candidates, indent=2, default=str)}

Rules:
- Amount tolerance: +/- {tolerance:.2f}
- Consider partial matches if amounts don't match exactly
- Match on partner name, reference number patterns, and amount proximity
- If no good match exists, return match_type "none" """

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, RECONCILE_TOOLS)
        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]
        return {"match_type": "none", "matched_move_ids": [], "confidence": 0}

    def _detect_anomaly(self, model: str, record_id: int, record: dict) -> AutomationResult:
        partner_id = record.get("partner_id")
        if isinstance(partner_id, (list, tuple)):
            partner_id = partner_id[0]

        historical = []
        if partner_id:
            historical = self.fetch_related_records(
                "account.move",
                [
                    ("partner_id", "=", partner_id),
                    ("state", "=", "posted"),
                    ("id", "!=", record_id),
                ],
                fields=["amount_total", "invoice_date", "move_type"],
                limit=20,
            )

        user_msg = f"""Analyze this invoice/bill for anomalies:

Current transaction:
- Type: {record.get('move_type', 'N/A')}
- Partner: {record.get('partner_id', 'Unknown')}
- Amount: {record.get('amount_total', 0)}
- Date: {record.get('invoice_date', 'N/A')}
- Reference: {record.get('ref', 'N/A')}
- State: {record.get('state', 'N/A')}

Historical transactions with this partner:
{json.dumps(historical, indent=2, default=str)}

Check for:
- Unusual amount (significantly different from historical average)
- Unusual timing (outside normal patterns)
- Potential duplicates (same amount + partner + close dates)
- Missing required references"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, ANOMALY_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            is_anomaly = tool_result.get("is_anomaly", False)
            confidence = tool_result.get("confidence", 0)

            if is_anomaly and confidence >= self.settings.default_confidence_threshold:
                self.update_record(model, record_id, {
                    "narration": f"⚠️ AI ANOMALY DETECTED [{tool_result.get('severity', 'medium').upper()}]: "
                    f"{tool_result.get('anomaly_type', 'unknown')} — {tool_result.get('reasoning', '')}"
                })

            return AutomationResult(
                success=True,
                action="flag_anomaly",
                model=model,
                record_id=record_id,
                confidence=confidence,
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=is_anomaly and self.needs_approval(confidence),
            )

        return AutomationResult(
            success=False,
            action="flag_anomaly",
            model=model,
            record_id=record_id,
            reasoning="Anomaly detection produced no result",
        )

    def _handle_categorization(
        self, model: str, record_id: int, categorization: dict
    ) -> AutomationResult:
        confidence = categorization.get("confidence", 0)
        changes: dict[str, Any] = {}

        if self.should_auto_execute(confidence):
            if categorization.get("partner_id"):
                changes["partner_id"] = categorization["partner_id"]
            self.update_record(model, record_id, changes)

        return AutomationResult(
            success=True,
            action="categorize_transaction",
            model=model,
            record_id=record_id,
            confidence=confidence,
            reasoning=categorization.get("reasoning", ""),
            changes_made=categorization,
            needs_approval=self.needs_approval(confidence),
        )

    def _handle_reconciliation(
        self, model: str, record_id: int, record: dict, reconciliation: dict
    ) -> AutomationResult:
        confidence = reconciliation.get("confidence", 0)

        if self.should_auto_execute(confidence) and reconciliation.get("matched_move_ids"):
            self._execute_reconciliation(record_id, reconciliation["matched_move_ids"])

        return AutomationResult(
            success=True,
            action="reconcile_transaction",
            model=model,
            record_id=record_id,
            confidence=confidence,
            reasoning=reconciliation.get("reasoning", ""),
            changes_made=reconciliation,
            needs_approval=self.needs_approval(confidence),
        )

    def _execute_reconciliation(self, statement_line_id: int, move_ids: list[int]):
        """Execute the actual reconciliation in Odoo via the statement line's reconcile method."""
        try:
            for move_id in move_ids:
                move = self.odoo.get_record("account.move", move_id, ["line_ids"])
                if move and move.get("line_ids"):
                    receivable_payable_lines = self.odoo.search_read(
                        "account.move.line",
                        [
                            ("id", "in", move["line_ids"]),
                            ("account_id.reconcile", "=", True),
                            ("reconciled", "=", False),
                        ],
                        fields=["id"],
                        limit=1,
                    )
                    if receivable_payable_lines:
                        self.odoo.execute_method(
                            "account.bank.statement.line",
                            "reconcile",
                            [statement_line_id],
                            [{"id": line["id"]} for line in receivable_payable_lines],
                        )
                    logger.info(
                        "reconciliation_executed",
                        statement_line_id=statement_line_id,
                        move_id=move_id,
                    )
        except Exception as exc:
            logger.error("reconciliation_execution_failed", error=str(exc))
