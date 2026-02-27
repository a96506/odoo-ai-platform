"""
Anomaly detection for financial transactions.

Two detection methods:
1. Benford's Law — tests whether leading-digit distribution of transaction
   amounts matches the expected logarithmic distribution.
2. Z-score — flags individual transactions whose amounts deviate significantly
   from the mean of their category/journal.

Used by MonthEndCloseAgent and standalone continuous-close scans.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import structlog

from app.config import get_settings
from app.odoo_client import get_odoo_client

logger = structlog.get_logger()

BENFORD_EXPECTED = {
    1: 0.301,
    2: 0.176,
    3: 0.125,
    4: 0.097,
    5: 0.079,
    6: 0.067,
    7: 0.058,
    8: 0.051,
    9: 0.046,
}


class AnomalyDetector:
    """Statistical anomaly detection for ERP financial data."""

    def __init__(self):
        self.settings = get_settings()
        self._odoo = None

    @property
    def odoo(self):
        if self._odoo is None:
            self._odoo = get_odoo_client()
        return self._odoo

    def detect_anomalies(self, period: str) -> list[dict[str, Any]]:
        """Run all anomaly detection methods for a given period (YYYY-MM).

        Returns a list of anomaly dicts with type, score, and details.
        """
        anomalies: list[dict[str, Any]] = []

        try:
            transactions = self._fetch_transactions(period)
        except Exception as exc:
            logger.warning("anomaly_fetch_failed", period=period, error=str(exc))
            return anomalies

        if not transactions:
            return anomalies

        amounts = [abs(t.get("amount_total", 0)) for t in transactions if t.get("amount_total")]

        benford_results = self.benford_analysis(amounts)
        if benford_results.get("is_anomalous"):
            anomalies.append({
                "type": "benford_deviation",
                "score": benford_results["chi_squared"],
                "details": benford_results,
                "description": (
                    f"Leading-digit distribution deviates from Benford's Law "
                    f"(chi-squared: {benford_results['chi_squared']:.2f}, "
                    f"threshold: {benford_results['threshold']:.2f})"
                ),
            })

        zscore_anomalies = self.zscore_analysis(transactions)
        for za in zscore_anomalies:
            anomalies.append({
                "type": "zscore_outlier",
                "score": abs(za["zscore"]),
                "details": za,
                "description": (
                    f"Transaction {za.get('move_name', '')} amount {za['amount']:.2f} "
                    f"is {abs(za['zscore']):.1f} standard deviations from mean"
                ),
            })

        return anomalies

    # ------------------------------------------------------------------
    # Benford's Law analysis
    # ------------------------------------------------------------------

    @staticmethod
    def benford_analysis(
        amounts: list[float],
        significance_level: float = 0.05,
    ) -> dict[str, Any]:
        """Test leading-digit distribution against Benford's Law using chi-squared.

        Returns dict with observed/expected distributions, chi-squared statistic,
        threshold, and whether the distribution is anomalous.
        """
        if len(amounts) < 50:
            return {
                "is_anomalous": False,
                "reason": "insufficient_data",
                "sample_size": len(amounts),
            }

        leading_digits = []
        for amount in amounts:
            if amount <= 0:
                continue
            first_digit = int(str(amount).lstrip("0").lstrip(".").lstrip("0")[0:1] or "0")
            if 1 <= first_digit <= 9:
                leading_digits.append(first_digit)

        if len(leading_digits) < 50:
            return {
                "is_anomalous": False,
                "reason": "insufficient_valid_digits",
                "sample_size": len(leading_digits),
            }

        n = len(leading_digits)
        counts = Counter(leading_digits)

        observed = {d: counts.get(d, 0) / n for d in range(1, 10)}

        chi_squared = sum(
            ((observed.get(d, 0) - BENFORD_EXPECTED[d]) ** 2) / BENFORD_EXPECTED[d]
            for d in range(1, 10)
        ) * n

        # df=8 (9 digits - 1), critical values at common significance levels
        chi_sq_thresholds = {
            0.10: 13.36,
            0.05: 15.51,
            0.01: 20.09,
        }
        threshold = chi_sq_thresholds.get(significance_level, 15.51)

        return {
            "is_anomalous": chi_squared > threshold,
            "chi_squared": round(chi_squared, 4),
            "threshold": threshold,
            "significance_level": significance_level,
            "sample_size": n,
            "observed_distribution": {str(k): round(v, 4) for k, v in observed.items()},
            "expected_distribution": {str(k): round(v, 4) for k, v in BENFORD_EXPECTED.items()},
        }

    # ------------------------------------------------------------------
    # Z-score outlier detection
    # ------------------------------------------------------------------

    @staticmethod
    def zscore_analysis(
        transactions: list[dict[str, Any]],
        threshold: float = 3.0,
    ) -> list[dict[str, Any]]:
        """Flag transactions with amounts more than `threshold` std devs from mean.

        Groups by journal_id for category-specific baselines.
        """
        from collections import defaultdict

        by_journal: dict[Any, list[dict]] = defaultdict(list)
        for txn in transactions:
            journal = txn.get("journal_id")
            journal_key = journal[0] if isinstance(journal, (list, tuple)) else journal
            by_journal[journal_key].append(txn)

        outliers = []

        for journal_key, group in by_journal.items():
            amounts = [abs(t.get("amount_total", 0)) for t in group if t.get("amount_total")]
            if len(amounts) < 10:
                continue

            mean = sum(amounts) / len(amounts)
            variance = sum((a - mean) ** 2 for a in amounts) / len(amounts)
            std_dev = math.sqrt(variance) if variance > 0 else 0

            if std_dev == 0:
                continue

            for txn in group:
                amount = abs(txn.get("amount_total", 0))
                if amount == 0:
                    continue
                zscore = (amount - mean) / std_dev
                if abs(zscore) > threshold:
                    outliers.append({
                        "move_id": txn.get("id"),
                        "move_name": txn.get("name", ""),
                        "amount": txn.get("amount_total", 0),
                        "journal_id": journal_key,
                        "zscore": round(zscore, 2),
                        "mean": round(mean, 2),
                        "std_dev": round(std_dev, 2),
                    })

        outliers.sort(key=lambda x: abs(x["zscore"]), reverse=True)
        return outliers

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def _fetch_transactions(self, period: str) -> list[dict[str, Any]]:
        """Fetch posted journal entries for the given period from Odoo."""
        year, month = period.split("-")
        date_from = f"{year}-{month}-01"

        next_month = int(month) + 1
        next_year = int(year)
        if next_month > 12:
            next_month = 1
            next_year += 1
        date_to = f"{next_year}-{next_month:02d}-01"

        return self.odoo.search_read(
            "account.move",
            [
                ("date", ">=", date_from),
                ("date", "<", date_to),
                ("state", "=", "posted"),
            ],
            fields=["id", "name", "amount_total", "journal_id", "date", "partner_id"],
            limit=5000,
        )
