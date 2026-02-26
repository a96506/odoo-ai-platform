"""Tests for Enhanced Bank Reconciliation (deliverable 1.3)."""

from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from app.models.audit import ReconciliationSession, AuditLog
from app.automations.reconciliation import ReconciliationAutomation
from app.models.schemas import MatchSuggestion


# ---------------------------------------------------------------------------
# Unit tests — fuzzy matching engine
# ---------------------------------------------------------------------------


class TestFuzzyMatchingEngine:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            return ReconciliationAutomation()

    def test_exact_reference_match(self):
        auto = self._make_automation()
        bank_lines = [{"id": 1, "payment_ref": "INV/2026/0042", "amount": 1500.00, "partner_id": "Acme Corp"}]
        candidates = [{"id": 42, "name": "INV/2026/0042", "ref": "INV/2026/0042", "amount_total": 1500.00, "amount_residual": 1500.00, "partner_id": [1, "Acme Corp"]}]

        suggestions = auto._generate_suggestions(bank_lines, candidates, [])
        assert len(suggestions) == 1
        assert suggestions[0].matched_entry_id == 42
        assert suggestions[0].confidence >= 0.85
        assert suggestions[0].match_type in ("exact", "fuzzy")

    def test_fuzzy_reference_match(self):
        auto = self._make_automation()
        bank_lines = [{"id": 1, "payment_ref": "PMT INV-2026-042", "amount": 1500.00, "partner_id": ""}]
        candidates = [{"id": 42, "name": "INV/2026/0042", "ref": "INV/2026/0042", "amount_total": 1500.00, "amount_residual": 1500.00, "partner_id": [1, "Acme"]}]

        suggestions = auto._generate_suggestions(bank_lines, candidates, [])
        assert len(suggestions) == 1
        assert suggestions[0].matched_entry_id == 42
        assert suggestions[0].confidence > 0.0

    def test_amount_within_rounding_tolerance(self):
        auto = self._make_automation()
        bank_lines = [{"id": 1, "payment_ref": "PMT-99", "amount": 1000.30, "partner_id": ""}]
        candidates = [{"id": 99, "name": "INV/99", "ref": "", "amount_total": 1000.00, "amount_residual": 1000.00, "partner_id": [1, "Test"]}]

        suggestions = auto._generate_suggestions(bank_lines, candidates, [])
        assert len(suggestions) == 1
        assert suggestions[0].confidence > 0.0
        assert suggestions[0].matched_entry_id == 99

    def test_no_match_returns_none_type(self):
        auto = self._make_automation()
        bank_lines = [{"id": 1, "payment_ref": "RANDOM-XYZ", "amount": 999999.99, "partner_id": ""}]
        candidates = [{"id": 50, "name": "INV/001", "ref": "INV/001", "amount_total": 10.00, "amount_residual": 10.00, "partner_id": [2, "Other"]}]

        suggestions = auto._generate_suggestions(bank_lines, candidates, [])
        assert len(suggestions) == 1
        assert suggestions[0].match_type in ("none", "partial")

    def test_partner_matching_boosts_score(self):
        auto = self._make_automation()
        bank_lines = [{"id": 1, "payment_ref": "", "amount": 500.00, "partner_id": [1, "Al Failakawi Trading"]}]
        candidates = [
            {"id": 10, "name": "INV/A", "ref": "", "amount_total": 500.00, "amount_residual": 500.00, "partner_id": [1, "Al Failakawi Trading"]},
            {"id": 11, "name": "INV/B", "ref": "", "amount_total": 500.00, "amount_residual": 500.00, "partner_id": [2, "Other Company"]},
        ]

        suggestions = auto._generate_suggestions(bank_lines, candidates, [])
        assert suggestions[0].matched_entry_id == 10

    def test_learned_rule_boosts_score(self):
        auto = self._make_automation()
        rule = {
            "bank_ref_pattern": "subscription payment",
            "bank_partner_pattern": "saas corp",
            "entry_ref_pattern": "inv/sub/022",
            "entry_partner_pattern": "saas corp",
        }
        bank_lines = [{"id": 1, "payment_ref": "Subscription Payment Feb", "amount": 200.00, "partner_id": [1, "SaaS Corp"]}]
        candidates = [{"id": 20, "name": "INV/SUB/022", "ref": "INV/SUB/022", "amount_total": 200.00, "amount_residual": 200.00, "partner_id": [1, "SaaS Corp"]}]

        suggestions = auto._generate_suggestions(bank_lines, candidates, [rule])
        assert suggestions[0].matched_entry_id == 20
        assert suggestions[0].confidence >= 0.5

    def test_ref_contained_check(self):
        assert ReconciliationAutomation._ref_contained("INV-042", "Payment for INV-042 Feb")
        assert ReconciliationAutomation._ref_contained("Payment for INV-042", "INV-042")
        assert not ReconciliationAutomation._ref_contained("AB", "XY")
        assert not ReconciliationAutomation._ref_contained("", "INV-042")

    def test_extract_partner_name_from_tuple(self):
        assert ReconciliationAutomation._extract_partner_name([1, "Acme Corp"]) == "Acme Corp"
        assert ReconciliationAutomation._extract_partner_name("Direct String") == "Direct String"
        assert ReconciliationAutomation._extract_partner_name(None) == ""
        assert ReconciliationAutomation._extract_partner_name(False) == ""

    def test_create_learned_rule(self):
        auto = self._make_automation()
        rule = auto.create_learned_rule(
            bank_ref="PMT-ABC", bank_partner="Acme",
            entry_ref="INV/001", entry_partner="Acme Corp",
        )
        assert rule["bank_ref_pattern"] == "pmt-abc"
        assert rule["entry_partner_pattern"] == "acme corp"
        assert "created_at" in rule

    def test_multiple_candidates_selects_best(self):
        auto = self._make_automation()
        bank_lines = [{"id": 1, "payment_ref": "INV/2026/0042", "amount": 1500.00, "partner_id": [1, "Acme"]}]
        candidates = [
            {"id": 40, "name": "INV/2026/0040", "ref": "INV/2026/0040", "amount_total": 1500.00, "amount_residual": 1500.00, "partner_id": [2, "Other"]},
            {"id": 42, "name": "INV/2026/0042", "ref": "INV/2026/0042", "amount_total": 1500.00, "amount_residual": 1500.00, "partner_id": [1, "Acme"]},
        ]

        suggestions = auto._generate_suggestions(bank_lines, candidates, [])
        assert suggestions[0].matched_entry_id == 42

    def test_used_candidates_not_reused(self):
        auto = self._make_automation()
        bank_lines = [
            {"id": 1, "payment_ref": "INV/001", "amount": 100.00, "partner_id": ""},
            {"id": 2, "payment_ref": "INV/001", "amount": 100.00, "partner_id": ""},
        ]
        candidates = [
            {"id": 50, "name": "INV/001", "ref": "INV/001", "amount_total": 100.00, "amount_residual": 100.00, "partner_id": [1, "A"]},
        ]

        suggestions = auto._generate_suggestions(bank_lines, candidates, [])
        matched_ids = [s.matched_entry_id for s in suggestions if s.matched_entry_id]
        assert len(matched_ids) <= 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestReconciliationEndpoints:

    def test_start_reconciliation(self, client, auth_headers, db_session):
        with patch(
            "app.routers.reconciliation.ReconciliationAutomation"
        ) as MockRecon:
            instance = MockRecon.return_value
            instance.start_session.return_value = {
                "total_lines": 120,
                "auto_matchable": 85,
                "needs_review": 35,
                "suggestions": [],
                "bank_lines": [],
                "candidates": [],
            }

            resp = client.post(
                "/api/reconciliation/start",
                json={"journal_id": 1, "user_id": "admin"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_lines"] == 120
            assert data["auto_matchable"] == 85
            assert data["needs_review"] == 35
            assert data["session_id"] > 0

    def test_start_reconciliation_resumes_active_session(self, client, auth_headers, db_session):
        existing = ReconciliationSession(
            user_id="admin", journal_id=1, status="active",
            total_lines=100, auto_matched=80, remaining=20,
        )
        db_session.add(existing)
        db_session.commit()

        with patch(
            "app.routers.reconciliation.ReconciliationAutomation"
        ) as MockRecon:
            instance = MockRecon.return_value
            instance.start_session.return_value = {
                "total_lines": 100,
                "auto_matchable": 82,
                "needs_review": 18,
                "suggestions": [],
                "bank_lines": [],
                "candidates": [],
            }

            resp = client.post(
                "/api/reconciliation/start",
                json={"journal_id": 1},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["session_id"] == existing.id

    def test_get_suggestions(self, client, auth_headers, db_session):
        sess = ReconciliationSession(
            user_id="admin", journal_id=1, status="active",
            total_lines=10, auto_matched=5, remaining=5,
        )
        db_session.add(sess)
        db_session.commit()

        mock_suggestion = MatchSuggestion(
            bank_line_id=1, bank_ref="PMT-001", bank_amount=100.0,
            matched_entry_id=42, matched_entry_ref="INV/001",
            matched_amount=100.0, confidence=0.95,
            match_type="exact", reasoning="Exact match",
        )

        with patch(
            "app.routers.reconciliation.ReconciliationAutomation"
        ) as MockRecon:
            instance = MockRecon.return_value
            instance.get_suggestions.return_value = ([mock_suggestion], 1)

            resp = client.get(
                f"/api/reconciliation/{sess.id}/suggestions",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["suggestions"][0]["confidence"] == 0.95

    def test_get_suggestions_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/reconciliation/99999/suggestions",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_match_entries(self, client, auth_headers, db_session):
        sess = ReconciliationSession(
            user_id="admin", journal_id=1, status="active",
            total_lines=10, auto_matched=5, manually_matched=0, remaining=5,
        )
        db_session.add(sess)
        db_session.commit()

        with patch(
            "app.routers.reconciliation.ReconciliationAutomation"
        ) as MockRecon:
            instance = MockRecon.return_value
            instance.fetch_record_context.side_effect = [
                {"id": 1, "payment_ref": "PMT-001", "partner_id": [1, "Acme"], "amount": 100},
                {"id": 42, "name": "INV/001", "ref": "INV/001", "partner_id": [1, "Acme"], "amount_residual": 100},
            ]
            instance.create_learned_rule.return_value = {
                "bank_ref_pattern": "pmt-001",
                "bank_partner_pattern": "acme",
                "entry_ref_pattern": "inv/001",
                "entry_partner_pattern": "acme",
                "created_at": "2026-02-26T00:00:00",
            }
            instance._extract_partner_name = ReconciliationAutomation._extract_partner_name

            resp = client.post(
                f"/api/reconciliation/{sess.id}/match",
                json={"bank_line_id": 1, "entry_id": 42},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["matched"] is True
            assert data["session_progress"]["remaining"] == 4

    def test_skip_line(self, client, auth_headers, db_session):
        sess = ReconciliationSession(
            user_id="admin", journal_id=1, status="active",
            total_lines=10, skipped=0, remaining=5,
        )
        db_session.add(sess)
        db_session.commit()

        resp = client.post(
            f"/api/reconciliation/{sess.id}/skip",
            json={"bank_line_id": 3, "reason": "Need more info"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped"] is True

    def test_match_on_inactive_session(self, client, auth_headers, db_session):
        sess = ReconciliationSession(
            user_id="admin", journal_id=1, status="completed",
            total_lines=10, remaining=0,
        )
        db_session.add(sess)
        db_session.commit()

        resp = client.post(
            f"/api/reconciliation/{sess.id}/match",
            json={"bank_line_id": 1, "entry_id": 42},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_requires_auth(self, client):
        resp = client.post("/api/reconciliation/start", json={"journal_id": 1})
        assert resp.status_code == 401
