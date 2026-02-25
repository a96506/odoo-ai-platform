"use client";

import { useState } from "react";

const TYPE_LABELS = {
  accounting: "Accounting",
  crm: "CRM",
  sales: "Sales",
  purchase: "Purchase",
  inventory: "Inventory",
  hr: "HR",
  project: "Project",
  helpdesk: "Helpdesk",
  manufacturing: "Manufacturing",
  marketing: "Marketing",
};

export default function RulesPanel({ rules, onRefresh, apiUrl }) {
  const [filter, setFilter] = useState("all");

  const filtered =
    filter === "all"
      ? rules
      : rules.filter((r) => r.automation_type === filter);

  const types = [...new Set(rules.map((r) => r.automation_type))].sort();

  const toggleRule = async (rule) => {
    try {
      await fetch(`${apiUrl}/api/rules/${rule.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...rule, enabled: !rule.enabled }),
      });
      onRefresh();
    } catch (err) {
      console.error("Toggle failed:", err);
    }
  };

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setFilter("all")}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
            filter === "all"
              ? "bg-indigo-600 text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          All ({rules.length})
        </button>
        {types.map((type) => (
          <button
            key={type}
            onClick={() => setFilter(type)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              filter === type
                ? "bg-indigo-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {TYPE_LABELS[type] || type} (
            {rules.filter((r) => r.automation_type === type).length})
          </button>
        ))}
      </div>

      {/* Rules list */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-medium text-gray-700">
            Automation Rules ({filtered.length})
          </h3>
        </div>
        <div className="divide-y divide-gray-50">
          {filtered.map((rule) => (
            <div
              key={rule.id}
              className="px-6 py-4 flex items-center justify-between gap-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">
                    {TYPE_LABELS[rule.automation_type] || rule.automation_type}
                  </span>
                  <span
                    className={`text-sm font-medium ${
                      rule.enabled ? "text-gray-700" : "text-gray-400"
                    }`}
                  >
                    {rule.name}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs text-gray-400">
                  <span>
                    Threshold: {(rule.confidence_threshold * 100).toFixed(0)}%
                  </span>
                  <span>
                    Auto-approve:{" "}
                    {rule.auto_approve
                      ? `>${(rule.auto_approve_threshold * 100).toFixed(0)}%`
                      : "Off"}
                  </span>
                  <span>Action: {rule.action_name.replace(/_/g, " ")}</span>
                </div>
              </div>
              <button
                onClick={() => toggleRule(rule)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  rule.enabled ? "bg-indigo-600" : "bg-gray-300"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    rule.enabled ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
