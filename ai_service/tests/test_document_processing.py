"""Tests for Smart Invoice Processing / IDP (deliverable 1.4)."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock, PropertyMock
import io
import json

import pytest

from app.models.audit import DocumentProcessingJob, ExtractionCorrection, AuditLog
from app.automations.document_processing import DocumentProcessingAutomation


# ---------------------------------------------------------------------------
# Unit tests — extraction pipeline components
# ---------------------------------------------------------------------------


class TestConfidenceScoring:

    def test_overall_confidence_all_high(self):
        field_conf = {
            "vendor": 0.99,
            "invoice_number": 0.98,
            "date": 0.97,
            "total": 0.99,
            "line_items": 0.95,
            "po_reference": 0.90,
        }
        result = DocumentProcessingAutomation._calculate_overall_confidence(field_conf)
        assert result >= 0.95

    def test_overall_confidence_mixed(self):
        field_conf = {
            "vendor": 0.90,
            "invoice_number": 0.80,
            "date": 0.85,
            "total": 0.92,
            "line_items": 0.70,
        }
        result = DocumentProcessingAutomation._calculate_overall_confidence(field_conf)
        assert 0.80 < result < 0.92

    def test_overall_confidence_all_low(self):
        field_conf = {
            "vendor": 0.30,
            "total": 0.40,
        }
        result = DocumentProcessingAutomation._calculate_overall_confidence(field_conf)
        assert result < 0.50

    def test_overall_confidence_empty(self):
        result = DocumentProcessingAutomation._calculate_overall_confidence({})
        assert result == 0.0

    def test_overall_confidence_partial_fields(self):
        field_conf = {"vendor": 0.95, "total": 0.98}
        result = DocumentProcessingAutomation._calculate_overall_confidence(field_conf)
        assert 0.90 < result < 1.0

    def test_overall_confidence_po_reference_low_weight(self):
        """po_reference has only 0.05 weight; low value shouldn't tank overall."""
        high = {"vendor": 0.99, "invoice_number": 0.99, "date": 0.99, "total": 0.99, "line_items": 0.99, "po_reference": 0.10}
        result = DocumentProcessingAutomation._calculate_overall_confidence(high)
        assert result > 0.90


class TestVendorMatching:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
                idp_max_pages=50,
                idp_confidence_threshold=0.90,
            )
            return DocumentProcessingAutomation()

    @patch("app.automations.base.get_odoo_client")
    def test_match_vendor_exact_name(self, mock_odoo_fn):
        mock_odoo = MagicMock()
        mock_odoo.search_read.return_value = [
            {"id": 1, "name": "Acme Corporation", "vat": "VAT123", "email": "info@acme.com"},
            {"id": 2, "name": "Beta Inc", "vat": "", "email": "contact@beta.com"},
        ]
        mock_odoo_fn.return_value = mock_odoo

        automation = self._make_automation()
        result = automation._match_vendor("Acme Corporation")
        assert result["vendor_id"] == 1
        assert result["confidence"] > 0.9

    @patch("app.automations.base.get_odoo_client")
    def test_match_vendor_fuzzy(self, mock_odoo_fn):
        mock_odoo = MagicMock()
        mock_odoo.search_read.return_value = [
            {"id": 1, "name": "Acme Corporation", "vat": "", "email": ""},
            {"id": 2, "name": "Beta Inc", "vat": "", "email": ""},
        ]
        mock_odoo_fn.return_value = mock_odoo

        automation = self._make_automation()
        result = automation._match_vendor("Acme Corporation Ltd")
        assert result["vendor_id"] == 1
        assert result["confidence"] > 0.7

    @patch("app.automations.base.get_odoo_client")
    def test_match_vendor_no_match(self, mock_odoo_fn):
        mock_odoo = MagicMock()
        mock_odoo.search_read.return_value = [
            {"id": 1, "name": "Acme Corporation", "vat": "", "email": ""},
        ]
        mock_odoo_fn.return_value = mock_odoo

        automation = self._make_automation()
        result = automation._match_vendor("Totally Different Company XYZ")
        assert result["vendor_id"] is None

    @patch("app.automations.base.get_odoo_client")
    def test_match_vendor_empty_name(self, mock_odoo_fn):
        automation = self._make_automation()
        result = automation._match_vendor("")
        assert result["vendor_id"] is None

    @patch("app.automations.base.get_odoo_client")
    def test_match_vendor_no_partners(self, mock_odoo_fn):
        mock_odoo = MagicMock()
        mock_odoo.search_read.return_value = []
        mock_odoo_fn.return_value = mock_odoo

        automation = self._make_automation()
        result = automation._match_vendor("Any Vendor")
        assert result["vendor_id"] is None


class TestPOValidation:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
                idp_max_pages=50,
                idp_confidence_threshold=0.90,
            )
            return DocumentProcessingAutomation()

    @patch("app.automations.base.get_odoo_client")
    def test_validate_matching_po(self, mock_odoo_fn):
        mock_odoo = MagicMock()
        mock_odoo.search_read.side_effect = [
            [{"id": 42, "name": "PO-0042", "amount_total": 5000.0, "partner_id": [1, "Vendor"], "order_line": [1, 2]}],
            [
                {"id": 1, "name": "Widget A", "product_qty": 10, "price_unit": 250, "price_subtotal": 2500, "product_id": [100, "Widget"]},
                {"id": 2, "name": "Widget B", "product_qty": 5, "price_unit": 500, "price_subtotal": 2500, "product_id": [101, "Widget B"]},
            ],
        ]
        mock_odoo_fn.return_value = mock_odoo

        automation = self._make_automation()
        extraction = {
            "total": 5000.0,
            "line_items": [
                {"description": "Widget A", "quantity": 10, "unit_price": 250, "amount": 2500},
                {"description": "Widget B", "quantity": 5, "unit_price": 500, "amount": 2500},
            ],
        }
        result = automation._validate_against_po("PO-0042", extraction)
        assert result is not None
        assert result["matched"] is True
        assert result["po_id"] == 42
        assert result["total_match"] is True
        assert result["lines_matched"] == 2

    @patch("app.automations.base.get_odoo_client")
    def test_validate_po_not_found(self, mock_odoo_fn):
        mock_odoo = MagicMock()
        mock_odoo.search_read.return_value = []
        mock_odoo_fn.return_value = mock_odoo

        automation = self._make_automation()
        result = automation._validate_against_po("PO-9999", {"total": 100})
        assert result is not None
        assert result["matched"] is False

    @patch("app.automations.base.get_odoo_client")
    def test_validate_po_amount_mismatch(self, mock_odoo_fn):
        mock_odoo = MagicMock()
        mock_odoo.search_read.side_effect = [
            [{"id": 42, "name": "PO-0042", "amount_total": 5000.0, "partner_id": [1, "V"], "order_line": []}],
            [],
        ]
        mock_odoo_fn.return_value = mock_odoo

        automation = self._make_automation()
        extraction = {"total": 6000.0, "line_items": []}
        result = automation._validate_against_po("PO-0042", extraction)
        assert result["matched"] is True
        assert result["total_match"] is False
        assert len(result["discrepancies"]) > 0

    def test_validate_empty_po_reference(self):
        automation = self._make_automation()
        result = automation._validate_against_po("", {})
        assert result is None


class TestContentPreparation:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
                idp_max_pages=50,
                idp_confidence_threshold=0.90,
            )
            return DocumentProcessingAutomation()

    def test_prepare_jpeg(self):
        automation = self._make_automation()
        content = b"\xff\xd8\xff fake jpeg"
        text, img, media = automation._prepare_content(content, "test.jpg", "image/jpeg")
        assert text == ""
        assert img is not None
        assert media == "image/jpeg"

    def test_prepare_png(self):
        automation = self._make_automation()
        content = b"\x89PNG fake png"
        text, img, media = automation._prepare_content(content, "test.png", "image/png")
        assert text == ""
        assert img is not None
        assert media == "image/png"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestDocumentProcessingAPI:

    @patch("app.routers.documents.DocumentProcessingAutomation")
    def test_process_document_success(self, mock_cls, client, auth_headers, db_session):
        mock_instance = MagicMock()
        mock_instance.process_document.return_value = {
            "status": "completed",
            "document_type": "invoice",
            "extraction": {
                "vendor": "Acme Corp",
                "total": 5400.00,
                "line_items": [],
            },
            "confidence": 0.96,
            "field_confidences": {"vendor": 0.99, "total": 0.98},
            "matched_vendor_id": 42,
            "matched_po_id": None,
            "odoo_record_created": 1234,
            "processing_time_ms": 850,
        }
        mock_cls.return_value = mock_instance

        fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")
        response = client.post(
            "/api/documents/process",
            headers=auth_headers,
            files={"file": ("invoice.pdf", fake_pdf, "application/pdf")},
            data={"uploaded_by": "admin"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["job_id"] > 0

    def test_process_document_no_auth(self, client):
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake")
        response = client.post(
            "/api/documents/process",
            files={"file": ("invoice.pdf", fake_pdf, "application/pdf")},
        )
        assert response.status_code == 401

    @patch("app.routers.documents.DocumentProcessingAutomation")
    def test_process_document_empty_file(self, mock_cls, client, auth_headers):
        response = client.post(
            "/api/documents/process",
            headers=auth_headers,
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert response.status_code == 400

    def test_get_job_not_found(self, client, auth_headers):
        response = client.get("/api/documents/999", headers=auth_headers)
        assert response.status_code == 404

    @patch("app.routers.documents.DocumentProcessingAutomation")
    def test_get_job_success(self, mock_cls, client, auth_headers, db_session):
        job = DocumentProcessingJob(
            file_name="test.pdf",
            file_type="pdf",
            document_type="invoice",
            status="completed",
            extraction_result={
                "vendor": "Test Vendor",
                "total": 1000.0,
                "line_items": [],
            },
            overall_confidence=Decimal("0.95"),
            field_confidences={"vendor": 0.99, "total": 0.95},
            processing_time_ms=500,
        )
        db_session.add(job)
        db_session.flush()

        mock_instance = MagicMock()
        mock_instance.fetch_record_context.return_value = None
        mock_cls.return_value = mock_instance

        response = client.get(f"/api/documents/{job.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job.id
        assert data["status"] == "completed"
        assert data["confidence"] == 0.95

    def test_correct_extraction(self, client, auth_headers, db_session):
        job = DocumentProcessingJob(
            file_name="test.pdf",
            file_type="pdf",
            status="completed",
            extraction_result={"vendor": "Acme Corp", "total": 1000},
        )
        db_session.add(job)
        db_session.flush()

        response = client.post(
            f"/api/documents/{job.id}/correct",
            headers=auth_headers,
            json={"field_name": "vendor", "corrected_value": "Acme Corporation Ltd"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["correction_saved"] is True
        assert data["original_value"] == "Acme Corp"
        assert data["corrected_value"] == "Acme Corporation Ltd"

        corrections = db_session.query(ExtractionCorrection).filter_by(job_id=job.id).all()
        assert len(corrections) == 1
        assert corrections[0].field_name == "vendor"

    def test_correct_nonexistent_job(self, client, auth_headers):
        response = client.post(
            "/api/documents/999/correct",
            headers=auth_headers,
            json={"field_name": "vendor", "corrected_value": "Test"},
        )
        assert response.status_code == 404

    def test_list_jobs(self, client, auth_headers, db_session):
        for i in range(3):
            job = DocumentProcessingJob(
                file_name=f"test_{i}.pdf",
                file_type="pdf",
                status="completed" if i < 2 else "failed",
            )
            db_session.add(job)
        db_session.flush()

        response = client.get("/api/documents/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_list_jobs_filter_status(self, client, auth_headers, db_session):
        db_session.add(DocumentProcessingJob(file_name="a.pdf", file_type="pdf", status="completed"))
        db_session.add(DocumentProcessingJob(file_name="b.pdf", file_type="pdf", status="failed"))
        db_session.flush()

        response = client.get("/api/documents/?status=completed", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "completed"


class TestWebhookHandler:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
                idp_max_pages=50,
                idp_confidence_threshold=0.90,
            )
            return DocumentProcessingAutomation()

    def test_on_create_vendor_bill(self):
        automation = self._make_automation()
        result = automation.on_create_account_move(
            model="account.move",
            record_id=1,
            values={"move_type": "in_invoice", "partner_id": 42},
        )
        assert result.success is True
        assert result.action == "idp_bill_detected"

    def test_on_create_non_invoice(self):
        automation = self._make_automation()
        result = automation.on_create_account_move(
            model="account.move",
            record_id=1,
            values={"move_type": "out_invoice"},
        )
        assert result.success is True
        assert result.action == "idp_skipped_not_invoice"
