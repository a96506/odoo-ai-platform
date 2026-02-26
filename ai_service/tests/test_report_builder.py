"""Tests for Natural Language Report Builder (deliverable 1.7)."""

import os
import tempfile
from datetime import datetime, date
from unittest.mock import patch, MagicMock

import pytest

from app.models.audit import ReportJob, AuditLog
from app.automations.report_builder import ReportBuilderAutomation, REPORT_DIR


# ---------------------------------------------------------------------------
# Unit tests — report builder engine
# ---------------------------------------------------------------------------


class TestReportBuilderEngine:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            return ReportBuilderAutomation()

    # -- fallback parse tests --

    def test_fallback_parse_sales(self):
        result = ReportBuilderAutomation._fallback_parse("Sales by product category for Q4 2025")
        assert result["model"] == "sale.order.line"
        assert "product_id" in result["fields"]

    def test_fallback_parse_invoices(self):
        result = ReportBuilderAutomation._fallback_parse("Show me all invoices this month")
        assert result["model"] == "account.move"
        assert len(result["domain"]) > 0

    def test_fallback_parse_pipeline(self):
        result = ReportBuilderAutomation._fallback_parse("Pipeline by stage")
        assert result["model"] == "crm.lead"

    def test_fallback_parse_products(self):
        result = ReportBuilderAutomation._fallback_parse("Product catalog with prices")
        assert result["model"] == "product.template"

    def test_fallback_parse_purchases(self):
        result = ReportBuilderAutomation._fallback_parse("Purchase orders this year")
        assert result["model"] == "purchase.order"

    def test_fallback_parse_expenses(self):
        result = ReportBuilderAutomation._fallback_parse("Employee expenses summary")
        assert result["model"] == "hr.expense"

    def test_fallback_parse_customers(self):
        result = ReportBuilderAutomation._fallback_parse("Customer list with contacts")
        assert result["model"] == "res.partner"

    def test_fallback_parse_inventory(self):
        result = ReportBuilderAutomation._fallback_parse("Current inventory stock levels")
        assert result["model"] == "product.product"

    def test_fallback_parse_default(self):
        result = ReportBuilderAutomation._fallback_parse("Something unknown")
        assert result["model"] == "sale.order"

    def test_fallback_parse_ytd(self):
        result = ReportBuilderAutomation._fallback_parse("Sales YTD")
        assert len(result["domain"]) > 0

    def test_fallback_parse_last_month(self):
        result = ReportBuilderAutomation._fallback_parse("Invoices from last month")
        assert len(result["domain"]) == 2

    def test_fallback_parse_group_by_customer(self):
        result = ReportBuilderAutomation._fallback_parse("Sales by customer")
        assert "partner_id" in result["group_by"]

    def test_fallback_parse_group_by_status(self):
        result = ReportBuilderAutomation._fallback_parse("Orders by status")
        assert "state" in result["group_by"]

    # -- normalize domain --

    def test_normalize_domain_lists(self):
        domain = [["state", "=", "sale"], ["amount_total", ">", 100]]
        result = ReportBuilderAutomation._normalize_domain(domain)
        assert len(result) == 2
        assert result[0] == ("state", "=", "sale")

    def test_normalize_domain_empty(self):
        assert ReportBuilderAutomation._normalize_domain([]) == []

    def test_normalize_domain_with_operators(self):
        domain = ["|", ["state", "=", "draft"], ["state", "=", "sale"]]
        result = ReportBuilderAutomation._normalize_domain(domain)
        assert "|" in result

    # -- format records --

    def test_format_records(self):
        records = [
            {"name": "SO001", "amount_total": 5000, "state": "sale"},
            {"name": "SO002", "amount_total": 3000, "state": "draft"},
        ]
        fields = ["name", "amount_total", "state"]
        result = ReportBuilderAutomation._format_records(records, fields)

        assert len(result["columns"]) == 3
        assert result["columns"][0]["label"] == "Name"
        assert len(result["rows"]) == 2

    def test_format_records_empty(self):
        result = ReportBuilderAutomation._format_records([], ["name"])
        assert len(result["rows"]) == 0

    # -- group records --

    def test_group_records(self):
        records = [
            {"state": "sale", "amount_total": 5000},
            {"state": "sale", "amount_total": 3000},
            {"state": "draft", "amount_total": 2000},
        ]
        result = ReportBuilderAutomation._group_records(
            records, ["state"], ["state", "amount_total"]
        )
        assert len(result["rows"]) == 2

        sale_group = next(r for r in result["rows"] if r["state"] == "sale")
        assert sale_group["_count"] == 2
        assert sale_group["amount_total"] == 8000.0

    def test_group_records_many2one(self):
        records = [
            {"partner_id": [1, "Customer A"], "amount_total": 5000},
            {"partner_id": [1, "Customer A"], "amount_total": 3000},
            {"partner_id": [2, "Customer B"], "amount_total": 2000},
        ]
        result = ReportBuilderAutomation._group_records(
            records, ["partner_id"], ["partner_id", "amount_total"]
        )
        assert len(result["rows"]) == 2

    def test_group_records_empty(self):
        result = ReportBuilderAutomation._group_records([], ["state"], ["state", "amount"])
        assert len(result["rows"]) == 0

    # -- cron description --

    def test_parse_cron_weekly(self):
        result = ReportBuilderAutomation._parse_cron_to_description("0 8 * * MON")
        assert "Monday" in result
        assert "8:00" in result

    def test_parse_cron_daily(self):
        result = ReportBuilderAutomation._parse_cron_to_description("0 7 * * *")
        assert "Daily" in result

    def test_parse_cron_monthly(self):
        result = ReportBuilderAutomation._parse_cron_to_description("0 9 1 * *")
        assert "Monthly" in result

    def test_parse_cron_invalid(self):
        result = ReportBuilderAutomation._parse_cron_to_description("invalid")
        assert "Custom" in result

    # -- parse query with Claude --

    def test_parse_query_with_claude(self):
        auto = self._make_automation()
        with patch.object(auto, "analyze_with_tools") as mock_analyze:
            mock_analyze.return_value = {
                "tool_name": "odoo_report_query",
                "tool_input": {
                    "model": "sale.order",
                    "fields": ["name", "partner_id", "amount_total"],
                    "domain": [["state", "=", "sale"]],
                    "group_by": ["partner_id"],
                    "title": "Sales by customer",
                },
            }
            result = auto.parse_query("Sales by customer")

        assert result["model"] == "sale.order"
        assert result["group_by"] == ["partner_id"]

    def test_parse_query_claude_fails(self):
        auto = self._make_automation()
        with patch.object(auto, "analyze_with_tools", side_effect=Exception("API error")):
            result = auto.parse_query("Sales report")

        assert result["model"] == "sale.order"

    def test_parse_query_claude_empty_model(self):
        auto = self._make_automation()
        with patch.object(auto, "analyze_with_tools") as mock_analyze:
            mock_analyze.return_value = {"tool_input": {"model": "", "fields": []}}
            result = auto.parse_query("Something weird")

        assert result["model"] != ""

    # -- execute query --

    def test_execute_query(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.return_value = [
                {"name": "SO001", "amount_total": 5000, "state": "sale"},
                {"name": "SO002", "amount_total": 3000, "state": "sale"},
            ]
            result = auto.execute_query({
                "model": "sale.order",
                "fields": ["name", "amount_total", "state"],
                "domain": [("state", "=", "sale")],
                "limit": 100,
                "title": "Sales",
            })

        assert result["record_count"] == 2
        assert len(result["rows"]) == 2

    def test_execute_query_with_grouping(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.return_value = [
                {"state": "sale", "amount_total": 5000},
                {"state": "sale", "amount_total": 3000},
                {"state": "draft", "amount_total": 2000},
            ]
            result = auto.execute_query({
                "model": "sale.order",
                "fields": ["state", "amount_total"],
                "domain": [],
                "group_by": ["state"],
                "limit": 100,
                "title": "By Status",
            })

        assert result["record_count"] == 3
        assert len(result["rows"]) == 2

    def test_execute_query_error(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records", side_effect=Exception("Connection error")):
            result = auto.execute_query({
                "model": "sale.order",
                "fields": ["name"],
                "domain": [],
                "title": "Error Test",
            })

        assert "error" in result

    # -- generate report full pipeline --

    def test_generate_report(self):
        auto = self._make_automation()
        with patch.object(auto, "parse_query") as mock_parse:
            mock_parse.return_value = {
                "model": "sale.order",
                "fields": ["name", "amount_total"],
                "domain": [],
                "group_by": [],
                "limit": 10,
                "title": "Sales Report",
            }
            with patch.object(auto, "execute_query") as mock_exec:
                mock_exec.return_value = {
                    "columns": [{"name": "name", "label": "Name"}, {"name": "amount_total", "label": "Amount"}],
                    "rows": [{"name": "SO001", "amount_total": 5000}],
                    "title": "Sales Report",
                    "record_count": 1,
                }
                result = auto.generate_report("Show me sales")

        assert result["status"] == "completed"
        assert result["parsed_query"]["model"] == "sale.order"

    # -- export tests --

    def test_export_excel(self):
        auto = self._make_automation()
        data = {
            "title": "Test Report",
            "columns": [
                {"name": "name", "label": "Name"},
                {"name": "amount", "label": "Amount"},
            ],
            "rows": [
                {"name": "Item 1", "amount": 1000},
                {"name": "Item 2", "amount": 2000},
            ],
        }
        file_path = auto.export_excel(data, "test_export.xlsx")
        assert os.path.exists(file_path)
        assert file_path.endswith(".xlsx")
        os.remove(file_path)

    def test_export_pdf(self):
        auto = self._make_automation()
        data = {
            "title": "Test PDF Report",
            "columns": [
                {"name": "name", "label": "Name"},
                {"name": "value", "label": "Value"},
            ],
            "rows": [
                {"name": "Row 1", "value": 100},
                {"name": "Row 2", "value": 200},
            ],
        }
        file_path = auto.export_pdf(data, "test_export.txt")
        assert os.path.exists(file_path)
        with open(file_path) as f:
            content = f.read()
        assert "Test PDF Report" in content
        assert "Row 1" in content
        os.remove(file_path)

    def test_export_excel_empty(self):
        auto = self._make_automation()
        data = {"title": "Empty Report", "columns": [], "rows": []}
        file_path = auto.export_excel(data, "test_empty.xlsx")
        assert os.path.exists(file_path)
        os.remove(file_path)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestReportEndpoints:

    def test_generate_report(self, client, auth_headers, db_session):
        with patch(
            "app.routers.reports.ReportBuilderAutomation"
        ) as MockReport:
            instance = MockReport.return_value
            instance.generate_report.return_value = {
                "parsed_query": {"model": "sale.order", "fields": ["name"], "domain": []},
                "result_data": {
                    "columns": [{"name": "name", "label": "Name"}],
                    "rows": [{"name": "SO001"}],
                    "title": "Sales",
                    "record_count": 1,
                },
                "status": "completed",
                "error_message": None,
            }

            resp = client.post(
                "/api/reports/generate",
                json={"query": "Show me sales", "format": "table"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "completed"
            assert data["job_id"] > 0

    def test_generate_report_excel(self, client, auth_headers, db_session):
        with patch(
            "app.routers.reports.ReportBuilderAutomation"
        ) as MockReport:
            instance = MockReport.return_value
            instance.generate_report.return_value = {
                "parsed_query": {"model": "sale.order"},
                "result_data": {"columns": [], "rows": [], "title": "Test", "record_count": 0},
                "status": "completed",
                "error_message": None,
            }
            instance.export_excel.return_value = "/tmp/test.xlsx"

            resp = client.post(
                "/api/reports/generate",
                json={"query": "Sales report", "format": "excel"},
                headers=auth_headers,
            )
            assert resp.status_code == 200

    def test_generate_report_error(self, client, auth_headers, db_session):
        with patch(
            "app.routers.reports.ReportBuilderAutomation"
        ) as MockReport:
            instance = MockReport.return_value
            instance.generate_report.side_effect = Exception("Claude API error")

            resp = client.post(
                "/api/reports/generate",
                json={"query": "Sales report", "format": "table"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "error"

    def test_get_report(self, client, auth_headers, db_session):
        job = ReportJob(
            request_text="Sales by customer",
            format="table",
            status="completed",
            parsed_query={"model": "sale.order"},
            result_data={
                "columns": [{"name": "name", "label": "Name"}],
                "rows": [{"name": "SO001"}],
            },
        )
        db_session.add(job)
        db_session.commit()

        resp = client.get(f"/api/reports/{job.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["request_text"] == "Sales by customer"
        assert data["status"] == "completed"

    def test_get_report_not_found(self, client, auth_headers, db_session):
        resp = client.get("/api/reports/999", headers=auth_headers)
        assert resp.status_code == 404

    def test_download_report_not_ready(self, client, auth_headers, db_session):
        job = ReportJob(
            request_text="Test",
            format="table",
            status="generating",
        )
        db_session.add(job)
        db_session.commit()

        resp = client.get(f"/api/reports/{job.id}/download?format=excel", headers=auth_headers)
        assert resp.status_code == 400

    def test_download_report_no_data(self, client, auth_headers, db_session):
        job = ReportJob(
            request_text="Test",
            format="table",
            status="completed",
            result_data=None,
        )
        db_session.add(job)
        db_session.commit()

        resp = client.get(f"/api/reports/{job.id}/download?format=excel", headers=auth_headers)
        assert resp.status_code == 400

    def test_download_report_excel(self, client, auth_headers, db_session):
        job = ReportJob(
            request_text="Test",
            format="excel",
            status="completed",
            result_data={
                "title": "Test",
                "columns": [{"name": "name", "label": "Name"}],
                "rows": [{"name": "SO001"}],
            },
        )
        db_session.add(job)
        db_session.commit()

        with patch(
            "app.routers.reports.ReportBuilderAutomation"
        ) as MockReport:
            instance = MockReport.return_value
            test_file = os.path.join(REPORT_DIR, f"report_{job.id}.xlsx")
            os.makedirs(REPORT_DIR, exist_ok=True)
            with open(test_file, "wb") as f:
                f.write(b"fake excel content")
            instance.export_excel.return_value = test_file

            resp = client.get(f"/api/reports/{job.id}/download?format=excel", headers=auth_headers)
            assert resp.status_code == 200

            if os.path.exists(test_file):
                os.remove(test_file)

    def test_schedule_report(self, client, auth_headers, db_session):
        resp = client.post(
            "/api/reports/schedule",
            json={
                "query": "Weekly sales summary",
                "cron": "0 8 * * MON",
                "format": "pdf",
                "deliver_via": "email",
                "recipient": "cfo@company.com",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] > 0
        assert "Monday" in data["schedule"]

    def test_list_reports(self, client, auth_headers, db_session):
        for i in range(3):
            job = ReportJob(
                request_text=f"Report {i}",
                format="table",
                status="completed",
            )
            db_session.add(job)
        db_session.commit()

        resp = client.get("/api/reports/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_list_reports_filter_status(self, client, auth_headers, db_session):
        job1 = ReportJob(request_text="Done", format="table", status="completed")
        job2 = ReportJob(request_text="Pending", format="table", status="generating")
        db_session.add_all([job1, job2])
        db_session.commit()

        resp = client.get("/api/reports/?status=completed", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "completed"

    def test_requires_auth(self, client):
        resp = client.post("/api/reports/generate", json={"query": "test"})
        assert resp.status_code == 401

    def test_schedule_requires_auth(self, client):
        resp = client.post("/api/reports/schedule", json={"query": "test", "cron": "0 8 * * *"})
        assert resp.status_code == 401

    def test_generate_validation_error(self, client, auth_headers, db_session):
        resp = client.post(
            "/api/reports/generate",
            json={"query": "ab", "format": "table"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
