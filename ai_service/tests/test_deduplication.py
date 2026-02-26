"""Tests for Cross-Entity Deduplication (deliverable 1.5)."""

from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from app.models.audit import DeduplicationScan, DuplicateGroup, AuditLog
from app.automations.deduplication import DeduplicationAutomation


# ---------------------------------------------------------------------------
# Unit tests — fuzzy matching engine
# ---------------------------------------------------------------------------


class TestDeduplicationMatchingEngine:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            return DeduplicationAutomation()

    def test_exact_name_match_contacts(self):
        auto = self._make_automation()
        records = [
            {"id": 1, "name": "Acme Corporation", "email": "info@acme.com", "phone": "+1234567890", "vat": ""},
            {"id": 2, "name": "Acme Corporation", "email": "contact@acme.com", "phone": "+1234567890", "vat": ""},
        ]
        from app.automations.deduplication import ENTITY_CONFIGS
        config = ENTITY_CONFIGS["res.partner"]
        groups = auto._find_duplicate_groups(records, config)
        assert len(groups) == 1
        assert set(groups[0]["record_ids"]) == {1, 2}
        assert groups[0]["similarity_score"] > 0.6

    def test_fuzzy_name_match(self):
        auto = self._make_automation()
        records = [
            {"id": 1, "name": "Al Failakawi Trading Co.", "email": "", "phone": "", "vat": ""},
            {"id": 2, "name": "Al-Failakawi Trading Company", "email": "", "phone": "", "vat": ""},
        ]
        from app.automations.deduplication import ENTITY_CONFIGS
        config = ENTITY_CONFIGS["res.partner"]
        groups = auto._find_duplicate_groups(records, config)
        assert len(groups) >= 1

    def test_email_exact_match(self):
        auto = self._make_automation()
        records = [
            {"id": 1, "name": "John Smith", "email": "john@example.com", "phone": "", "vat": ""},
            {"id": 2, "name": "J. Smith", "email": "john@example.com", "phone": "", "vat": ""},
        ]
        from app.automations.deduplication import ENTITY_CONFIGS
        config = ENTITY_CONFIGS["res.partner"]
        groups = auto._find_duplicate_groups(records, config)
        assert len(groups) == 1

    def test_phone_similarity_ignores_formatting(self):
        auto = self._make_automation()
        sim = auto._phone_similarity("+1 (555) 123-4567", "15551234567")
        assert sim >= 0.9

    def test_phone_last_7_digits_match(self):
        auto = self._make_automation()
        sim = auto._phone_similarity("+965-1234567", "001234567")
        assert sim >= 0.9

    def test_email_same_domain_different_local(self):
        auto = self._make_automation()
        sim = auto._email_similarity("john.smith@acme.com", "j.smith@acme.com")
        assert sim > 0.5
        assert sim < 1.0

    def test_email_exact(self):
        auto = self._make_automation()
        sim = auto._email_similarity("info@acme.com", "info@acme.com")
        assert sim == 1.0

    def test_no_duplicates_found(self):
        auto = self._make_automation()
        records = [
            {"id": 1, "name": "Alpha Corp", "email": "alpha@example.com", "phone": "111", "vat": "VAT1"},
            {"id": 2, "name": "Beta Inc", "email": "beta@other.com", "phone": "999", "vat": "VAT2"},
        ]
        from app.automations.deduplication import ENTITY_CONFIGS
        config = ENTITY_CONFIGS["res.partner"]
        groups = auto._find_duplicate_groups(records, config)
        assert len(groups) == 0

    def test_vat_exact_match(self):
        auto = self._make_automation()
        records = [
            {"id": 1, "name": "Some Company A", "email": "", "phone": "", "vat": "KW12345678"},
            {"id": 2, "name": "Some Company B", "email": "", "phone": "", "vat": "KW12345678"},
        ]
        from app.automations.deduplication import ENTITY_CONFIGS
        config = ENTITY_CONFIGS["res.partner"]
        score, fields = auto._compute_similarity(records[0], records[1], config)
        assert "vat" in fields

    def test_lead_dedup_by_email(self):
        auto = self._make_automation()
        records = [
            {"id": 1, "contact_name": "Jane Doe", "email_from": "jane@startup.io", "phone": "", "partner_name": "StartupCo"},
            {"id": 2, "contact_name": "Jane D.", "email_from": "jane@startup.io", "phone": "", "partner_name": "Startup Co."},
        ]
        from app.automations.deduplication import ENTITY_CONFIGS
        config = ENTITY_CONFIGS["crm.lead"]
        groups = auto._find_duplicate_groups(records, config)
        assert len(groups) == 1

    def test_product_dedup_by_code(self):
        auto = self._make_automation()
        records = [
            {"id": 1, "name": "Widget A", "default_code": "WDG-001", "barcode": ""},
            {"id": 2, "name": "Widget Type A", "default_code": "WDG-001", "barcode": ""},
        ]
        from app.automations.deduplication import ENTITY_CONFIGS
        config = ENTITY_CONFIGS["product.template"]
        groups = auto._find_duplicate_groups(records, config)
        assert len(groups) == 1

    def test_heuristic_master_selection(self):
        auto = self._make_automation()
        records = [
            {"id": 1, "name": "A", "email": ""},
            {"id": 2, "name": "A", "email": "a@example.com", "phone": "123", "city": "Kuwait"},
        ]
        result = auto._heuristic_master_selection(records)
        assert result["master_record_id"] == 2

    def test_normalize_value(self):
        auto = self._make_automation()
        assert auto._normalize_value(None) == ""
        assert auto._normalize_value(False) == ""
        assert auto._normalize_value("  test  ") == "test"
        assert auto._normalize_value([1, "Acme"]) == "Acme"
        assert auto._normalize_value([42]) == "42"

    def test_three_way_duplicate_cluster(self):
        auto = self._make_automation()
        records = [
            {"id": 1, "name": "Acme Corp", "email": "acme@example.com", "phone": "5551234", "vat": ""},
            {"id": 2, "name": "ACME Corp.", "email": "acme@example.com", "phone": "", "vat": ""},
            {"id": 3, "name": "Acme Corporation", "email": "", "phone": "5551234", "vat": ""},
        ]
        from app.automations.deduplication import ENTITY_CONFIGS
        config = ENTITY_CONFIGS["res.partner"]
        groups = auto._find_duplicate_groups(records, config)
        assert len(groups) == 1
        assert len(groups[0]["record_ids"]) == 3

    def test_check_duplicate_on_create(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.return_value = [
                {"id": 10, "name": "Existing Company", "email": "info@existing.com",
                 "phone": "5559999", "mobile": "", "vat": "", "street": "", "city": "",
                 "country_id": False, "is_company": True, "active": True,
                 "customer_rank": 1, "supplier_rank": 0},
            ]
            matches = auto.check_duplicate_on_create("res.partner", {
                "name": "Existing Company Ltd",
                "email": "info@existing.com",
            })
            assert len(matches) >= 1
            assert matches[0]["record_id"] == 10

    def test_on_create_webhook_with_duplicate(self):
        auto = self._make_automation()
        with patch.object(auto, "check_duplicate_on_create") as mock_check:
            mock_check.return_value = [
                {"record_id": 10, "record_name": "Existing", "similarity_score": 0.85, "matched_fields": ["name", "email"]},
            ]
            result = auto.on_create(model="res.partner", record_id=99, values={"name": "Test"})
            assert result.success
            assert result.action == "duplicate_detected"
            assert result.needs_approval

    def test_on_create_webhook_no_duplicate(self):
        auto = self._make_automation()
        with patch.object(auto, "check_duplicate_on_create") as mock_check:
            mock_check.return_value = []
            result = auto.on_create(model="res.partner", record_id=99, values={"name": "Unique Name"})
            assert result.success
            assert result.action == "no_duplicates"
            assert not result.needs_approval


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestDeduplicationEndpoints:

    def test_run_scan(self, client, auth_headers, db_session):
        with patch(
            "app.routers.deduplication.DeduplicationAutomation"
        ) as MockDedup:
            instance = MockDedup.return_value
            instance.run_scan.return_value = {
                "scan_type": "res.partner",
                "total_records": 100,
                "groups": [
                    {
                        "odoo_model": "contacts",
                        "record_ids": [1, 2],
                        "master_record_id": 1,
                        "similarity_score": 0.92,
                        "match_fields": ["name", "email"],
                        "records": [],
                    }
                ],
                "duplicates_found": 2,
            }

            resp = client.post(
                "/api/dedup/scan",
                json={"scan_type": "res.partner"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_records"] == 100
            assert data["duplicates_found"] == 2
            assert len(data["groups"]) == 1
            assert data["groups"][0]["similarity_score"] == 0.92

    def test_run_scan_invalid_type(self, client, auth_headers, db_session):
        with patch(
            "app.routers.deduplication.DeduplicationAutomation"
        ) as MockDedup:
            instance = MockDedup.return_value
            instance.run_scan.return_value = {"error": "Unknown scan type: invalid.model", "groups": []}

            resp = client.post(
                "/api/dedup/scan",
                json={"scan_type": "invalid.model"},
                headers=auth_headers,
            )
            assert resp.status_code == 400

    def test_list_scans(self, client, auth_headers, db_session):
        scan = DeduplicationScan(
            scan_type="res.partner", status="completed",
            total_records=50, duplicates_found=4, pending_review=2,
        )
        db_session.add(scan)
        db_session.commit()

        resp = client.get("/api/dedup/scans", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["scan_type"] == "res.partner"

    def test_get_group(self, client, auth_headers, db_session):
        scan = DeduplicationScan(
            scan_type="res.partner", status="completed",
            total_records=10, duplicates_found=2,
        )
        db_session.add(scan)
        db_session.flush()

        group = DuplicateGroup(
            scan_id=scan.id, odoo_model="contacts",
            record_ids=[1, 2], master_record_id=1,
            similarity_score=0.88, match_fields=["name"],
            status="pending",
        )
        db_session.add(group)
        db_session.commit()

        resp = client.get(f"/api/dedup/groups/{group.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["record_ids"] == [1, 2]
        assert data["status"] == "pending"

    def test_get_group_not_found(self, client, auth_headers):
        resp = client.get("/api/dedup/groups/99999", headers=auth_headers)
        assert resp.status_code == 404

    def test_merge_group(self, client, auth_headers, db_session):
        scan = DeduplicationScan(
            scan_type="res.partner", status="completed",
            total_records=10, duplicates_found=2, pending_review=1,
        )
        db_session.add(scan)
        db_session.flush()

        group = DuplicateGroup(
            scan_id=scan.id, odoo_model="contacts",
            record_ids=[1, 2, 3], master_record_id=1,
            similarity_score=0.90, match_fields=["name", "email"],
            status="pending",
        )
        db_session.add(group)
        db_session.commit()

        resp = client.post(
            f"/api/dedup/groups/{group.id}/merge",
            json={"master_record_id": 2, "merged_by": "admin"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["merged"] is True
        assert data["master_record_id"] == 2
        assert set(data["merged_record_ids"]) == {1, 3}

    def test_merge_invalid_master(self, client, auth_headers, db_session):
        scan = DeduplicationScan(
            scan_type="res.partner", status="completed",
            total_records=10, duplicates_found=2,
        )
        db_session.add(scan)
        db_session.flush()

        group = DuplicateGroup(
            scan_id=scan.id, odoo_model="contacts",
            record_ids=[1, 2], master_record_id=1,
            similarity_score=0.88, status="pending",
        )
        db_session.add(group)
        db_session.commit()

        resp = client.post(
            f"/api/dedup/groups/{group.id}/merge",
            json={"master_record_id": 999},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_merge_already_merged(self, client, auth_headers, db_session):
        scan = DeduplicationScan(
            scan_type="res.partner", status="completed",
            total_records=10, duplicates_found=2,
        )
        db_session.add(scan)
        db_session.flush()

        group = DuplicateGroup(
            scan_id=scan.id, odoo_model="contacts",
            record_ids=[1, 2], master_record_id=1,
            similarity_score=0.88, status="merged",
        )
        db_session.add(group)
        db_session.commit()

        resp = client.post(
            f"/api/dedup/groups/{group.id}/merge",
            json={"master_record_id": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_dismiss_group(self, client, auth_headers, db_session):
        scan = DeduplicationScan(
            scan_type="res.partner", status="completed",
            total_records=10, duplicates_found=2, pending_review=1,
        )
        db_session.add(scan)
        db_session.flush()

        group = DuplicateGroup(
            scan_id=scan.id, odoo_model="contacts",
            record_ids=[1, 2], master_record_id=1,
            similarity_score=0.70, status="pending",
        )
        db_session.add(group)
        db_session.commit()

        resp = client.post(
            f"/api/dedup/groups/{group.id}/dismiss",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dismissed"] is True

    def test_check_duplicates_realtime(self, client, auth_headers, db_session):
        with patch(
            "app.routers.deduplication.DeduplicationAutomation"
        ) as MockDedup:
            instance = MockDedup.return_value
            instance.check_duplicate_on_create.return_value = [
                {"record_id": 10, "record_name": "Existing Co", "similarity_score": 0.88, "matched_fields": ["name"]},
            ]

            resp = client.post(
                "/api/dedup/check",
                json={"model": "res.partner", "values": {"name": "Existing Company"}},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["has_duplicates"] is True
            assert len(data["matches"]) == 1

    def test_check_no_duplicates(self, client, auth_headers, db_session):
        with patch(
            "app.routers.deduplication.DeduplicationAutomation"
        ) as MockDedup:
            instance = MockDedup.return_value
            instance.check_duplicate_on_create.return_value = []

            resp = client.post(
                "/api/dedup/check",
                json={"model": "res.partner", "values": {"name": "Unique Name"}},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["has_duplicates"] is False

    def test_requires_auth(self, client):
        resp = client.post("/api/dedup/scan", json={"scan_type": "res.partner"})
        assert resp.status_code == 401
