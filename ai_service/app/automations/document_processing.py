"""
Smart Invoice Processing (IDP) — Vision-LLM document extraction pipeline.

Processes uploaded PDF/image invoices through:
1. Text extraction (pdfplumber for text PDFs, Vision API for scanned/images)
2. Claude-powered field extraction with structured tool output
3. Fuzzy vendor matching against Odoo res.partner
4. PO line-item cross-validation
5. Confidence-gated auto-creation of draft bills in Odoo
6. Learning loop via stored corrections
"""

import base64
import io
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

EXTRACTION_PROMPT = """You are an intelligent document processing system for an ERP platform.
Extract all relevant fields from this invoice/document with high accuracy.
Pay close attention to:
- Vendor/supplier name and VAT/tax ID
- Invoice number and dates (issue date, due date)
- Currency and all monetary amounts (subtotal, tax, total)
- Line items with descriptions, quantities, unit prices, and amounts
- PO/purchase order reference numbers
- Payment terms

For Arabic text, transliterate vendor names accurately.
If a field is not present or unclear, set its confidence to 0.0.
Return structured extraction via the extract_invoice_data tool."""

EXTRACTION_TOOLS = [
    {
        "name": "extract_invoice_data",
        "description": "Extract structured data from an invoice document",
        "input_schema": {
            "type": "object",
            "properties": {
                "vendor_name": {"type": "string", "description": "Vendor/supplier company name"},
                "vendor_vat": {"type": "string", "description": "Vendor VAT/tax ID number"},
                "invoice_number": {"type": "string", "description": "Invoice number/reference"},
                "invoice_date": {"type": "string", "description": "Invoice date (YYYY-MM-DD)"},
                "due_date": {"type": "string", "description": "Payment due date (YYYY-MM-DD)"},
                "currency": {"type": "string", "description": "Currency code (e.g. USD, EUR, KWD)"},
                "subtotal": {"type": "number", "description": "Subtotal before tax"},
                "tax_amount": {"type": "number", "description": "Total tax amount"},
                "total": {"type": "number", "description": "Grand total including tax"},
                "po_reference": {"type": "string", "description": "Purchase order reference if present"},
                "payment_terms": {"type": "string", "description": "Payment terms (e.g. Net 30)"},
                "notes": {"type": "string", "description": "Any additional notes"},
                "line_items": {
                    "type": "array",
                    "description": "Individual line items on the invoice",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                            "amount": {"type": "number"},
                            "product_code": {"type": "string"},
                        },
                        "required": ["description", "quantity", "unit_price", "amount"],
                    },
                },
                "field_confidences": {
                    "type": "object",
                    "description": "Confidence 0.0-1.0 for each extracted field",
                    "properties": {
                        "vendor": {"type": "number"},
                        "invoice_number": {"type": "number"},
                        "date": {"type": "number"},
                        "total": {"type": "number"},
                        "line_items": {"type": "number"},
                        "po_reference": {"type": "number"},
                    },
                },
                "document_type": {
                    "type": "string",
                    "enum": ["invoice", "credit_note", "debit_note", "receipt", "unknown"],
                    "description": "Classified document type",
                },
            },
            "required": [
                "vendor_name", "invoice_number", "invoice_date", "total",
                "line_items", "field_confidences", "document_type",
            ],
        },
    }
]

AMOUNT_TOLERANCE_PCT = 0.02
AMOUNT_TOLERANCE_ABS = 1.0
VENDOR_MATCH_THRESHOLD = 70


class DocumentProcessingAutomation(BaseAutomation):
    """Vision-LLM intelligent document processing for invoice extraction."""

    automation_type = "document_processing"
    watched_models = ["account.move"]

    def process_document(
        self,
        file_content: bytes,
        file_name: str,
        file_type: str,
        uploaded_by: str = "system",
    ) -> dict[str, Any]:
        """
        Main IDP pipeline: extract → match vendor → validate PO → score → persist.
        Returns a dict suitable for building a DocumentJobResponse.
        """
        start_time = time.time()

        text_content, image_data, media_type = self._prepare_content(
            file_content, file_name, file_type
        )

        extraction = self._extract_fields(text_content, image_data, media_type)
        if "error" in extraction:
            return {
                "status": "failed",
                "error_message": extraction["error"],
                "processing_time_ms": int((time.time() - start_time) * 1000),
            }

        field_confidences = extraction.get("field_confidences", {})
        overall_confidence = self._calculate_overall_confidence(field_confidences)

        vendor_match = self._match_vendor(extraction.get("vendor_name", ""))
        po_validation = None
        matched_po_id = None

        po_ref = extraction.get("po_reference", "")
        if po_ref:
            po_validation = self._validate_against_po(po_ref, extraction)
            if po_validation and po_validation.get("po_id"):
                matched_po_id = po_validation["po_id"]

        corrections = self._apply_learned_corrections(
            extraction, vendor_match.get("vendor_id")
        )
        if corrections:
            extraction.update(corrections)

        odoo_record_id = None
        if overall_confidence >= self.settings.auto_approve_threshold:
            odoo_record_id = self._create_bill_in_odoo(
                extraction, vendor_match, matched_po_id
            )

        processing_time_ms = int((time.time() - start_time) * 1000)

        return {
            "status": "completed",
            "document_type": extraction.get("document_type", "invoice"),
            "extraction": {
                "vendor": extraction.get("vendor_name", ""),
                "vendor_vat": extraction.get("vendor_vat", ""),
                "invoice_number": extraction.get("invoice_number", ""),
                "invoice_date": extraction.get("invoice_date", ""),
                "due_date": extraction.get("due_date", ""),
                "currency": extraction.get("currency", ""),
                "subtotal": extraction.get("subtotal", 0),
                "tax_amount": extraction.get("tax_amount", 0),
                "total": extraction.get("total", 0),
                "po_reference": po_ref,
                "line_items": extraction.get("line_items", []),
                "payment_terms": extraction.get("payment_terms", ""),
                "notes": extraction.get("notes", ""),
            },
            "confidence": overall_confidence,
            "field_confidences": field_confidences,
            "matched_vendor_id": vendor_match.get("vendor_id"),
            "matched_vendor_name": vendor_match.get("vendor_name", ""),
            "matched_po_id": matched_po_id,
            "po_validation": po_validation,
            "odoo_record_created": odoo_record_id,
            "processing_time_ms": processing_time_ms,
        }

    # ------------------------------------------------------------------
    # Content preparation
    # ------------------------------------------------------------------

    def _prepare_content(
        self, file_content: bytes, file_name: str, file_type: str
    ) -> tuple[str, str | None, str | None]:
        """
        Extract text and/or prepare image data for Claude.
        Returns (text_content, base64_image_data, media_type).
        """
        text_content = ""
        image_data = None
        media_type = None

        if file_type in ("pdf", "application/pdf"):
            text_content, image_data, media_type = self._process_pdf(file_content)
        elif file_type in ("jpg", "jpeg", "image/jpeg"):
            image_data = base64.b64encode(file_content).decode("utf-8")
            media_type = "image/jpeg"
        elif file_type in ("png", "image/png"):
            image_data = base64.b64encode(file_content).decode("utf-8")
            media_type = "image/png"
        elif file_type in ("webp", "image/webp"):
            image_data = base64.b64encode(file_content).decode("utf-8")
            media_type = "image/webp"
        else:
            image_data = base64.b64encode(file_content).decode("utf-8")
            media_type = "image/jpeg"

        return text_content, image_data, media_type

    def _process_pdf(
        self, file_content: bytes
    ) -> tuple[str, str | None, str | None]:
        """Extract text from PDF; fall back to image conversion for scanned docs."""
        text = ""
        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page in pdf.pages[: self.settings.idp_max_pages]:
                    page_text = page.extract_text() or ""
                    text += page_text + "\n"
        except Exception as exc:
            logger.warning("pdf_text_extraction_failed", error=str(exc))

        if len(text.strip()) > 100:
            return text.strip(), None, None

        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                if pdf.pages:
                    page = pdf.pages[0]
                    img = page.to_image(resolution=200)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    return text.strip(), image_b64, "image/png"
        except Exception as exc:
            logger.warning("pdf_image_conversion_failed", error=str(exc))

        return text.strip(), None, None

    # ------------------------------------------------------------------
    # Field extraction via Claude
    # ------------------------------------------------------------------

    def _extract_fields(
        self,
        text_content: str,
        image_data: str | None,
        media_type: str | None,
    ) -> dict[str, Any]:
        """Send document content to Claude for structured field extraction."""
        try:
            content_blocks: list[dict[str, Any]] = []

            if image_data and media_type:
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                })

            prompt_text = "Extract all fields from this invoice document."
            if text_content:
                prompt_text += f"\n\nExtracted text content:\n{text_content}"

            content_blocks.append({"type": "text", "text": prompt_text})

            response = self.claude.client.messages.create(
                model=self.claude.model,
                max_tokens=4096,
                temperature=0.0,
                system=EXTRACTION_PROMPT,
                messages=[{"role": "user", "content": content_blocks}],
                tools=EXTRACTION_TOOLS,
            )

            for block in response.content:
                if block.type == "tool_use" and block.name == "extract_invoice_data":
                    return block.input

            text_response = ""
            for block in response.content:
                if block.type == "text":
                    text_response += block.text

            return {"error": f"No structured extraction returned: {text_response[:200]}"}

        except Exception as exc:
            logger.error("claude_extraction_failed", error=str(exc))
            return {"error": f"Extraction failed: {str(exc)}"}

    # ------------------------------------------------------------------
    # Vendor matching
    # ------------------------------------------------------------------

    def _match_vendor(self, vendor_name: str) -> dict[str, Any]:
        """Fuzzy match extracted vendor name against Odoo res.partner records."""
        if not vendor_name:
            return {"vendor_id": None, "vendor_name": "", "confidence": 0.0}

        try:
            from rapidfuzz import fuzz, process

            partners = self.fetch_related_records(
                "res.partner",
                [("supplier_rank", ">", 0), ("active", "=", True)],
                fields=["id", "name", "vat", "email"],
                limit=500,
            )

            if not partners:
                return {"vendor_id": None, "vendor_name": vendor_name, "confidence": 0.0}

            partner_names = {p["id"]: p["name"] for p in partners if p.get("name")}
            if not partner_names:
                return {"vendor_id": None, "vendor_name": vendor_name, "confidence": 0.0}

            choices = list(partner_names.values())
            ids = list(partner_names.keys())

            match = process.extractOne(
                vendor_name,
                choices,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=VENDOR_MATCH_THRESHOLD,
            )

            if match:
                matched_name, score, idx = match
                matched_id = ids[idx]
                return {
                    "vendor_id": matched_id,
                    "vendor_name": matched_name,
                    "confidence": score / 100.0,
                }

            return {"vendor_id": None, "vendor_name": vendor_name, "confidence": 0.0}

        except Exception as exc:
            logger.warning("vendor_matching_failed", error=str(exc))
            return {"vendor_id": None, "vendor_name": vendor_name, "confidence": 0.0}

    # ------------------------------------------------------------------
    # PO cross-validation
    # ------------------------------------------------------------------

    def _validate_against_po(
        self, po_reference: str, extraction: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Cross-validate extracted line items against a matched purchase order."""
        if not po_reference:
            return None

        try:
            pos = self.fetch_related_records(
                "purchase.order",
                [("name", "ilike", po_reference), ("state", "in", ["purchase", "done"])],
                fields=["id", "name", "amount_total", "partner_id", "order_line"],
                limit=5,
            )

            if not pos:
                return {"matched": False, "reason": f"PO '{po_reference}' not found"}

            po = pos[0]
            po_id = po["id"]

            po_lines = self.fetch_related_records(
                "purchase.order.line",
                [("order_id", "=", po_id)],
                fields=["id", "name", "product_qty", "price_unit", "price_subtotal", "product_id"],
                limit=100,
            )

            invoice_total = float(extraction.get("total", 0))
            po_total = float(po.get("amount_total", 0))
            total_diff_pct = abs(invoice_total - po_total) / po_total if po_total > 0 else 1.0

            line_matches = []
            invoice_lines = extraction.get("line_items", [])
            unmatched_invoice = list(range(len(invoice_lines)))
            unmatched_po = list(range(len(po_lines)))

            for i, inv_line in enumerate(invoice_lines):
                inv_qty = float(inv_line.get("quantity", 0))
                inv_price = float(inv_line.get("unit_price", 0))

                best_match = None
                best_j = None

                for j in unmatched_po:
                    po_line = po_lines[j]
                    po_qty = float(po_line.get("product_qty", 0))
                    po_price = float(po_line.get("price_unit", 0))

                    qty_match = abs(inv_qty - po_qty) <= max(po_qty * AMOUNT_TOLERANCE_PCT, AMOUNT_TOLERANCE_ABS) if po_qty > 0 else inv_qty == 0
                    price_match = abs(inv_price - po_price) <= max(po_price * AMOUNT_TOLERANCE_PCT, AMOUNT_TOLERANCE_ABS) if po_price > 0 else inv_price == 0

                    if qty_match and price_match:
                        best_match = po_line
                        best_j = j
                        break

                if best_match is not None and best_j is not None:
                    line_matches.append({
                        "invoice_line": i,
                        "po_line_id": best_match["id"],
                        "status": "matched",
                    })
                    unmatched_invoice.remove(i)
                    unmatched_po.remove(best_j)

            discrepancies = []
            if total_diff_pct > AMOUNT_TOLERANCE_PCT:
                discrepancies.append({
                    "field": "total",
                    "invoice_value": invoice_total,
                    "po_value": po_total,
                    "difference_pct": round(total_diff_pct * 100, 2),
                })

            if unmatched_invoice:
                discrepancies.append({
                    "field": "line_items",
                    "description": f"{len(unmatched_invoice)} invoice line(s) unmatched",
                    "unmatched_indices": unmatched_invoice,
                })

            return {
                "matched": True,
                "po_id": po_id,
                "po_name": po.get("name", ""),
                "total_match": total_diff_pct <= AMOUNT_TOLERANCE_PCT,
                "lines_matched": len(line_matches),
                "lines_total": len(invoice_lines),
                "discrepancies": discrepancies,
                "line_details": line_matches,
            }

        except Exception as exc:
            logger.warning("po_validation_failed", po_ref=po_reference, error=str(exc))
            return {"matched": False, "reason": f"PO validation error: {str(exc)}"}

    # ------------------------------------------------------------------
    # Learning loop
    # ------------------------------------------------------------------

    def _apply_learned_corrections(
        self, extraction: dict[str, Any], vendor_id: int | None
    ) -> dict[str, Any] | None:
        """Apply patterns learned from past corrections for this vendor."""
        if not vendor_id:
            return None

        try:
            from app.models.audit import ExtractionCorrection, DocumentProcessingJob, get_db_session

            with get_db_session() as session:
                corrections = (
                    session.query(ExtractionCorrection)
                    .join(DocumentProcessingJob)
                    .filter(DocumentProcessingJob.matched_vendor_id == vendor_id)
                    .order_by(ExtractionCorrection.created_at.desc())
                    .limit(50)
                    .all()
                )

                if not corrections:
                    return None

                field_patterns: dict[str, dict[str, int]] = {}
                for c in corrections:
                    if c.field_name not in field_patterns:
                        field_patterns[c.field_name] = {}
                    key = f"{c.original_value}|{c.corrected_value}"
                    field_patterns[c.field_name][key] = (
                        field_patterns[c.field_name].get(key, 0) + 1
                    )

                applied: dict[str, Any] = {}
                for field, patterns in field_patterns.items():
                    current_value = str(extraction.get(field, ""))
                    for pattern_key, count in patterns.items():
                        if count < 2:
                            continue
                        orig, corrected = pattern_key.split("|", 1)
                        if current_value == orig:
                            applied[field] = corrected
                            logger.info(
                                "applied_learned_correction",
                                field=field,
                                original=orig,
                                corrected=corrected,
                                occurrences=count,
                            )

                return applied if applied else None

        except Exception as exc:
            logger.warning("learned_corrections_failed", error=str(exc))
            return None

    # ------------------------------------------------------------------
    # Confidence scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_overall_confidence(field_confidences: dict[str, float]) -> float:
        """Weighted average of per-field confidences."""
        weights = {
            "vendor": 0.25,
            "invoice_number": 0.15,
            "date": 0.10,
            "total": 0.25,
            "line_items": 0.20,
            "po_reference": 0.05,
        }

        total_weight = 0.0
        weighted_sum = 0.0

        for field, weight in weights.items():
            conf = field_confidences.get(field)
            if conf is not None:
                weighted_sum += conf * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        return round(weighted_sum / total_weight, 4)

    # ------------------------------------------------------------------
    # Odoo bill creation
    # ------------------------------------------------------------------

    def _create_bill_in_odoo(
        self,
        extraction: dict[str, Any],
        vendor_match: dict[str, Any],
        po_id: int | None,
    ) -> int | None:
        """Create a draft vendor bill in Odoo from extracted data."""
        vendor_id = vendor_match.get("vendor_id")
        if not vendor_id:
            return None

        try:
            invoice_lines = []
            for item in extraction.get("line_items", []):
                invoice_lines.append(
                    (0, 0, {
                        "name": item.get("description", ""),
                        "quantity": item.get("quantity", 1),
                        "price_unit": item.get("unit_price", 0),
                        "purchase_order_id": po_id,
                    })
                )

            move_vals = {
                "move_type": "in_invoice",
                "partner_id": vendor_id,
                "invoice_date": extraction.get("invoice_date"),
                "ref": extraction.get("invoice_number", ""),
                "invoice_line_ids": invoice_lines,
            }

            due_date = extraction.get("due_date")
            if due_date:
                move_vals["invoice_date_due"] = due_date

            record_id = self.create_record("account.move", move_vals)
            logger.info(
                "bill_created_in_odoo",
                record_id=record_id,
                vendor_id=vendor_id,
                total=extraction.get("total", 0),
            )
            return record_id

        except Exception as exc:
            logger.error("bill_creation_failed", error=str(exc))
            return None

    # ------------------------------------------------------------------
    # Webhook handler — process incoming vendor bills via attachment
    # ------------------------------------------------------------------

    def on_create_account_move(
        self, model: str, record_id: int, values: dict[str, Any]
    ) -> AutomationResult:
        """When a vendor bill is created, check if it has attachments to process."""
        move_type = values.get("move_type", "")
        if move_type != "in_invoice":
            return AutomationResult(
                success=True,
                action="idp_skipped_not_invoice",
                model=model,
                record_id=record_id,
                reasoning="Not a vendor bill",
            )

        return AutomationResult(
            success=True,
            action="idp_bill_detected",
            model=model,
            record_id=record_id,
            confidence=1.0,
            reasoning="Vendor bill detected; manual upload via /api/documents/process for IDP extraction",
        )
