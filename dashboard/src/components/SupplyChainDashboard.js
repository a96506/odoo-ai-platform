"use client";

import { useState, useEffect, useCallback } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { fetchApiSafe, fetchApi } from "../lib/api";

const RISK_COLORS = {
  low: "#22c55e",
  watch: "#eab308",
  elevated: "#f97316",
  critical: "#ef4444",
};

const SEVERITY_STYLES = {
  low: "bg-green-100 text-green-800",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
};

function SeverityBadge({ severity }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
        SEVERITY_STYLES[severity] || "bg-gray-100 text-gray-800"
      }`}
    >
      {severity}
    </span>
  );
}

function RiskScoreBar({ score }) {
  const color =
    score >= 80
      ? "bg-green-500"
      : score >= 60
        ? "bg-yellow-500"
        : score >= 40
          ? "bg-orange-500"
          : "bg-red-500";

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-200 rounded-full h-2">
        <div
          className={`h-2 rounded-full ${color}`}
          style={{ width: `${Math.min(score, 100)}%` }}
        />
      </div>
      <span className="text-sm font-medium w-10 text-right">{score}</span>
    </div>
  );
}

export default function SupplyChainDashboard() {
  const [riskScores, setRiskScores] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [singleSource, setSingleSource] = useState([]);
  const [scanning, setScanning] = useState(false);

  const fetchData = useCallback(async () => {
    const [scores, alertsData, preds, ss] = await Promise.all([
      fetchApiSafe("/api/supply-chain/risk-scores?limit=20"),
      fetchApiSafe("/api/supply-chain/alerts?limit=20"),
      fetchApiSafe("/api/supply-chain/predictions?limit=10"),
      fetchApiSafe("/api/supply-chain/single-source?limit=10"),
    ]);
    if (scores) setRiskScores(scores);
    if (alertsData) setAlerts(alertsData);
    if (preds) setPredictions(preds);
    if (ss) setSingleSource(ss);
  }, []);

  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 30000);
    return () => clearInterval(iv);
  }, [fetchData]);

  const triggerScan = async () => {
    setScanning(true);
    try {
      await fetchApi("/api/supply-chain/scan", { method: "POST" });
      setTimeout(() => {
        fetchData();
        setScanning(false);
      }, 3000);
    } catch {
      setScanning(false);
    }
  };

  const resolveAlert = async (alertId) => {
    try {
      await fetchApi(`/api/supply-chain/alerts/${alertId}/resolve`, {
        method: "POST",
      });
      fetchData();
    } catch (err) {
      console.error("Failed to resolve alert:", err);
    }
  };

  const chartData = riskScores
    .slice(0, 15)
    .map((s) => ({
      vendor: `V-${s.vendor_id}`,
      score: s.composite_score,
      classification: s.classification,
    }));

  const summary = {
    total: riskScores.length,
    critical: riskScores.filter((s) => s.classification === "critical").length,
    elevated: riskScores.filter((s) => s.classification === "elevated").length,
    watch: riskScores.filter((s) => s.classification === "watch").length,
    low: riskScores.filter((s) => s.classification === "low").length,
    activeAlerts: alerts.length,
    activePredictions: predictions.length,
    singleSourceCount: singleSource.length,
  };

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg border p-4">
          <p className="text-2xl font-bold text-gray-900">{summary.total}</p>
          <p className="text-xs text-gray-500">Vendors Scored</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-2xl font-bold text-red-600">{summary.critical}</p>
          <p className="text-xs text-gray-500">Critical Risk</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-2xl font-bold text-orange-600">
            {summary.activeAlerts}
          </p>
          <p className="text-xs text-gray-500">Active Alerts</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-2xl font-bold text-yellow-600">
            {summary.singleSourceCount}
          </p>
          <p className="text-xs text-gray-500">Single-Source Risks</p>
        </div>
      </div>

      {/* Risk score chart */}
      {chartData.length > 0 && (
        <div className="bg-white rounded-lg border p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">
            Vendor Risk Scores
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="vendor" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                {chartData.map((entry, idx) => (
                  <Cell
                    key={idx}
                    fill={RISK_COLORS[entry.classification] || "#94a3b8"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active alerts */}
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-gray-700">
              Active Alerts ({alerts.length})
            </h3>
            <button
              onClick={triggerScan}
              disabled={scanning}
              className="text-xs px-3 py-1 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
            >
              {scanning ? "Scanning..." : "Run Scan"}
            </button>
          </div>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {alerts.length === 0 && (
              <p className="text-sm text-gray-500 py-4 text-center">
                No active alerts
              </p>
            )}
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className="border rounded p-3 hover:bg-gray-50"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <SeverityBadge severity={alert.severity} />
                      <span className="text-xs text-gray-400">
                        {alert.alert_type?.replace(/_/g, " ")}
                      </span>
                    </div>
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {alert.title}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">
                      {alert.description}
                    </p>
                  </div>
                  <button
                    onClick={() => resolveAlert(alert.id)}
                    className="text-xs text-indigo-600 hover:text-indigo-800 ml-2 whitespace-nowrap"
                  >
                    Resolve
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Disruption predictions */}
        <div className="bg-white rounded-lg border p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">
            Disruption Predictions ({predictions.length})
          </h3>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {predictions.length === 0 && (
              <p className="text-sm text-gray-500 py-4 text-center">
                No active predictions
              </p>
            )}
            {predictions.map((pred) => (
              <div key={pred.id} className="border rounded p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium">
                    Vendor #{pred.vendor_id}
                  </span>
                  <span className="text-xs text-orange-600 font-medium">
                    {(pred.probability * 100).toFixed(0)}% probability
                  </span>
                </div>
                <p className="text-xs text-gray-600">{pred.estimated_impact}</p>
                {pred.recommended_actions?.length > 0 && (
                  <ul className="mt-1 space-y-0.5">
                    {pred.recommended_actions.slice(0, 2).map((action, i) => (
                      <li key={i} className="text-xs text-gray-500 pl-3 relative">
                        <span className="absolute left-0">-</span>
                        {action}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Risk scores table */}
      {riskScores.length > 0 && (
        <div className="bg-white rounded-lg border p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">
            All Vendor Risk Scores
          </h3>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-2 pr-4">Vendor ID</th>
                  <th className="py-2 pr-4">Score</th>
                  <th className="py-2 pr-4">Classification</th>
                  <th className="py-2">Scored At</th>
                </tr>
              </thead>
              <tbody>
                {riskScores.map((score) => (
                  <tr key={score.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 pr-4 font-medium">
                      #{score.vendor_id}
                    </td>
                    <td className="py-2 pr-4 w-48">
                      <RiskScoreBar score={score.composite_score} />
                    </td>
                    <td className="py-2 pr-4 capitalize">
                      <SeverityBadge
                        severity={
                          score.classification === "low"
                            ? "low"
                            : score.classification === "watch"
                              ? "medium"
                              : score.classification === "elevated"
                                ? "high"
                                : "critical"
                        }
                      />
                    </td>
                    <td className="py-2 text-gray-500 text-xs">
                      {score.scored_at
                        ? new Date(score.scored_at).toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
