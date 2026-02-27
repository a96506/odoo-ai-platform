"use client";

import { useState, useEffect, useCallback } from "react";
import { fetchApiSafe } from "../lib/api";

const STATUS_COLORS = {
  completed: "bg-green-100 text-green-800",
  running: "bg-blue-100 text-blue-800",
  suspended: "bg-yellow-100 text-yellow-800",
  failed: "bg-red-100 text-red-800",
  pending: "bg-gray-100 text-gray-800",
  cancelled: "bg-gray-100 text-gray-500",
};

function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
        STATUS_COLORS[status] || "bg-gray-100 text-gray-800"
      }`}
    >
      {status}
    </span>
  );
}

function AgentRunCard({ run, onSelect }) {
  return (
    <div
      onClick={() => onSelect(run.run_id)}
      className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow cursor-pointer"
    >
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-medium text-gray-900 capitalize">
          {run.agent_type?.replace(/_/g, " ")}
        </h3>
        <StatusBadge status={run.status} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-sm text-gray-500">
        <div>
          <span className="block text-gray-400 text-xs">Trigger</span>
          {run.trigger_type}
        </div>
        <div>
          <span className="block text-gray-400 text-xs">Steps</span>
          {run.total_steps || 0}
        </div>
        <div>
          <span className="block text-gray-400 text-xs">Tokens</span>
          {run.token_usage?.toLocaleString() || 0}
        </div>
      </div>
      {run.started_at && (
        <p className="text-xs text-gray-400 mt-2">
          {new Date(run.started_at).toLocaleString()}
        </p>
      )}
      {run.error && (
        <p className="text-xs text-red-500 mt-1 truncate">{run.error}</p>
      )}
    </div>
  );
}

function RunDetail({ runId, onClose }) {
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (!runId) return;
    fetchApiSafe(`/api/agents/runs/${runId}`).then(setDetail);
  }, [runId]);

  if (!detail) {
    return (
      <div className="bg-white rounded-lg border p-6 text-center text-gray-500">
        Loading...
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold capitalize">
          {detail.agent_type?.replace(/_/g, " ")} — Run #{detail.run_id}
        </h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 text-sm"
        >
          Close
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div>
          <span className="text-xs text-gray-400">Status</span>
          <div className="mt-1">
            <StatusBadge status={detail.status} />
          </div>
        </div>
        <div>
          <span className="text-xs text-gray-400">Total Steps</span>
          <p className="font-medium">{detail.total_steps}</p>
        </div>
        <div>
          <span className="text-xs text-gray-400">Token Usage</span>
          <p className="font-medium">{detail.token_usage?.toLocaleString()}</p>
        </div>
        <div>
          <span className="text-xs text-gray-400">Duration</span>
          <p className="font-medium">
            {detail.started_at && detail.completed_at
              ? `${Math.round(
                  (new Date(detail.completed_at) - new Date(detail.started_at)) / 1000
                )}s`
              : "—"}
          </p>
        </div>
      </div>

      {detail.error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 mb-4 text-sm text-red-700">
          {detail.error}
        </div>
      )}

      <h4 className="text-sm font-medium text-gray-700 mb-2">
        Execution Steps
      </h4>
      <div className="space-y-1">
        {(detail.steps || []).map((step, i) => (
          <div
            key={i}
            className="flex items-center gap-3 py-2 px-3 rounded hover:bg-gray-50 text-sm"
          >
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                step.status === "completed"
                  ? "bg-green-100 text-green-700"
                  : step.status === "failed"
                    ? "bg-red-100 text-red-700"
                    : "bg-gray-100 text-gray-500"
              }`}
            >
              {step.step_index}
            </div>
            <span className="font-medium text-gray-900 capitalize flex-1">
              {step.step_name?.replace(/_/g, " ")}
            </span>
            <StatusBadge status={step.status} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AgentDashboard() {
  const [runs, setRuns] = useState([]);
  const [types, setTypes] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [filter, setFilter] = useState({ type: "", status: "" });

  const fetchRuns = useCallback(async () => {
    const params = new URLSearchParams();
    if (filter.type) params.set("agent_type", filter.type);
    if (filter.status) params.set("status", filter.status);
    params.set("limit", "20");

    const data = await fetchApiSafe(`/api/agents/runs?${params}`);
    if (data) setRuns(data);
  }, [filter]);

  useEffect(() => {
    fetchApiSafe("/api/agents/types").then((data) => {
      if (data?.agent_types) setTypes(data.agent_types);
    });
  }, []);

  useEffect(() => {
    fetchRuns();
    const iv = setInterval(fetchRuns, 10000);
    return () => clearInterval(iv);
  }, [fetchRuns]);

  const summary = {
    total: runs.length,
    completed: runs.filter((r) => r.status === "completed").length,
    running: runs.filter((r) => r.status === "running").length,
    failed: runs.filter((r) => r.status === "failed").length,
    suspended: runs.filter((r) => r.status === "suspended").length,
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
        {[
          { label: "Total Runs", value: summary.total, color: "text-gray-900" },
          { label: "Completed", value: summary.completed, color: "text-green-600" },
          { label: "Running", value: summary.running, color: "text-blue-600" },
          { label: "Suspended", value: summary.suspended, color: "text-yellow-600" },
          { label: "Failed", value: summary.failed, color: "text-red-600" },
        ].map((card) => (
          <div key={card.label} className="bg-white rounded-lg border p-4 text-center">
            <p className="text-2xl font-bold ${card.color}">{card.value}</p>
            <p className="text-xs text-gray-500 mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      <div className="flex gap-3">
        <select
          value={filter.type}
          onChange={(e) => setFilter((f) => ({ ...f, type: e.target.value }))}
          className="border rounded-md px-3 py-1.5 text-sm"
        >
          <option value="">All Agent Types</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select
          value={filter.status}
          onChange={(e) => setFilter((f) => ({ ...f, status: e.target.value }))}
          className="border rounded-md px-3 py-1.5 text-sm"
        >
          <option value="">All Statuses</option>
          {["completed", "running", "suspended", "failed", "pending"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {selectedRun ? (
        <RunDetail runId={selectedRun} onClose={() => setSelectedRun(null)} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {runs.length === 0 && (
            <p className="text-gray-500 text-sm col-span-2 text-center py-8">
              No agent runs found. Start one from the API or automations.
            </p>
          )}
          {runs.map((run) => (
            <AgentRunCard
              key={run.run_id}
              run={run}
              onSelect={setSelectedRun}
            />
          ))}
        </div>
      )}
    </div>
  );
}
