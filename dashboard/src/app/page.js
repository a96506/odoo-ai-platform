"use client";

import { useState, useEffect, useCallback } from "react";
import StatsCards from "../components/StatsCards";
import AuditLog from "../components/AuditLog";
import ApprovalQueue from "../components/ApprovalQueue";
import RulesPanel from "../components/RulesPanel";
import ChatInterface from "../components/ChatInterface";
import InsightsPanel from "../components/InsightsPanel";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [logs, setLogs] = useState([]);
  const [pendingApprovals, setPendingApprovals] = useState([]);
  const [rules, setRules] = useState([]);
  const [activeTab, setActiveTab] = useState("overview");
  const [health, setHealth] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, logsRes, pendingRes, rulesRes, healthRes] =
        await Promise.all([
          fetch(`${API_URL}/api/stats`),
          fetch(`${API_URL}/api/audit-logs?limit=50`),
          fetch(`${API_URL}/api/audit-logs?status=pending&limit=20`),
          fetch(`${API_URL}/api/rules`),
          fetch(`${API_URL}/health`),
        ]);

      if (statsRes.ok) setStats(await statsRes.json());
      if (logsRes.ok) setLogs(await logsRes.json());
      if (pendingRes.ok) setPendingApprovals(await pendingRes.json());
      if (rulesRes.ok) setRules(await rulesRes.json());
      if (healthRes.ok) setHealth(await healthRes.json());
    } catch (err) {
      console.error("Failed to fetch data:", err);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleApprove = async (auditLogId, approved) => {
    try {
      await fetch(`${API_URL}/api/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audit_log_id: auditLogId,
          approved,
          approved_by: "admin",
        }),
      });
      fetchData();
    } catch (err) {
      console.error("Approval failed:", err);
    }
  };

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "chat", label: "Chat with ERP" },
    { id: "insights", label: "Intelligence" },
    { id: "approvals", label: `Approvals (${pendingApprovals.length})` },
    { id: "logs", label: "Audit Log" },
    { id: "rules", label: "Automation Rules" },
  ];

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-sm">AI</span>
              </div>
              <h1 className="text-xl font-semibold">
                Odoo AI Automation
              </h1>
            </div>
            <div className="flex items-center gap-4">
              {health && (
                <div className="flex items-center gap-2 text-sm">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      health.status === "healthy"
                        ? "bg-green-500"
                        : "bg-yellow-500"
                    }`}
                  />
                  <span className="text-gray-600">
                    {health.status === "healthy" ? "All systems operational" : "Degraded"}
                  </span>
                </div>
              )}
            </div>
          </div>
          {/* Tabs */}
          <nav className="flex gap-6 -mb-px">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? "border-indigo-600 text-indigo-600"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === "overview" && (
          <div className="space-y-8">
            <StatsCards stats={stats} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <ApprovalQueue
                approvals={pendingApprovals.slice(0, 5)}
                onApprove={handleApprove}
                compact
              />
              <AuditLog logs={logs.slice(0, 10)} compact />
            </div>
          </div>
        )}
        {activeTab === "chat" && <ChatInterface apiUrl={API_URL} />}
        {activeTab === "insights" && <InsightsPanel apiUrl={API_URL} />}
        {activeTab === "approvals" && (
          <ApprovalQueue
            approvals={pendingApprovals}
            onApprove={handleApprove}
          />
        )}
        {activeTab === "logs" && <AuditLog logs={logs} />}
        {activeTab === "rules" && (
          <RulesPanel rules={rules} onRefresh={fetchData} apiUrl={API_URL} />
        )}
      </main>
    </div>
  );
}
