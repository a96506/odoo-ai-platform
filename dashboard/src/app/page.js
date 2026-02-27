"use client";

import { useState, useEffect, useCallback } from "react";
import StatsCards from "../components/StatsCards";
import AuditLog from "../components/AuditLog";
import ApprovalQueue from "../components/ApprovalQueue";
import RulesPanel from "../components/RulesPanel";
import ChatInterface from "../components/ChatInterface";
import InsightsPanel from "../components/InsightsPanel";
import RoleSwitcher from "../components/RoleSwitcher";
import CFODashboard from "../components/CFODashboard";
import SalesDashboard from "../components/SalesDashboard";
import WarehouseDashboard from "../components/WarehouseDashboard";
import AgentDashboard from "../components/AgentDashboard";
import SupplyChainDashboard from "../components/SupplyChainDashboard";
import useWebSocket from "../hooks/useWebSocket";
import { getApiUrl, fetchApiSafe } from "../lib/api";

const API_URL = getApiUrl();

function getInitialRole() {
  if (typeof window !== "undefined") {
    return localStorage.getItem("dashboard_role") || "overview";
  }
  return "overview";
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [logs, setLogs] = useState([]);
  const [pendingApprovals, setPendingApprovals] = useState([]);
  const [rules, setRules] = useState([]);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [activeRole, setActiveRole] = useState(getInitialRole);
  const [health, setHealth] = useState(null);

  const wsRole = activeRole !== "overview" ? activeRole : null;
  const { lastMessage, isConnected } = useWebSocket(wsRole);

  const fetchData = useCallback(async () => {
    try {
      const [statsData, logsData, pendingData, rulesData, healthData] =
        await Promise.all([
          fetchApiSafe("/api/stats"),
          fetchApiSafe("/api/audit-logs?limit=50"),
          fetchApiSafe("/api/audit-logs?status=pending&limit=20"),
          fetchApiSafe("/api/rules"),
          fetch(`${API_URL}/health`).then((r) => r.ok ? r.json() : null).catch(() => null),
        ]);

      if (statsData) setStats(statsData);
      if (logsData) setLogs(logsData);
      if (pendingData) setPendingApprovals(pendingData);
      if (rulesData) setRules(rulesData);
      if (healthData) setHealth(healthData);
    } catch (err) {
      console.error("Failed to fetch data:", err);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (!lastMessage) return;
    if (
      lastMessage.type === "automation_completed" ||
      lastMessage.type === "approval_needed" ||
      lastMessage.type === "forecast_updated" ||
      lastMessage.type === "agent_completed" ||
      lastMessage.type === "alert"
    ) {
      fetchData();
    }
  }, [lastMessage, fetchData]);

  const handleRoleChange = (role) => {
    setActiveRole(role);
    setActiveTab("dashboard");
    if (typeof window !== "undefined") {
      localStorage.setItem("dashboard_role", role);
    }
  };

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
    { id: "dashboard", label: activeRole === "overview" ? "Overview" : `${activeRole.toUpperCase()} Dashboard` },
    { id: "chat", label: "Chat with ERP" },
    { id: "insights", label: "Intelligence" },
    { id: "agents", label: "AI Agents" },
    { id: "supply-chain", label: "Supply Chain" },
    { id: "approvals", label: `Approvals (${pendingApprovals.length})` },
    { id: "logs", label: "Audit Log" },
    { id: "rules", label: "Automation Rules" },
  ];

  const renderDashboard = () => {
    switch (activeRole) {
      case "cfo":
        return <CFODashboard />;
      case "sales":
        return <SalesDashboard />;
      case "warehouse":
        return <WarehouseDashboard />;
      default:
        return (
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
        );
    }
  };

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-sm">AI</span>
              </div>
              <h1 className="text-xl font-semibold">Odoo AI Automation</h1>
            </div>
            <div className="flex items-center gap-4">
              <RoleSwitcher activeRole={activeRole} onRoleChange={handleRoleChange} />
              <div className="flex items-center gap-2 text-sm">
                <div
                  className={`w-2 h-2 rounded-full ${
                    isConnected
                      ? "bg-green-500"
                      : health?.status === "healthy"
                        ? "bg-green-500"
                        : "bg-yellow-500"
                  }`}
                />
                <span className="text-gray-600 hidden sm:inline">
                  {isConnected
                    ? "Live"
                    : health?.status === "healthy"
                      ? "Connected"
                      : "Connecting..."}
                </span>
              </div>
            </div>
          </div>
          <nav className="flex gap-6 -mb-px overflow-x-auto">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
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

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === "dashboard" && renderDashboard()}
        {activeTab === "chat" && <ChatInterface apiUrl={API_URL} />}
        {activeTab === "insights" && <InsightsPanel apiUrl={API_URL} />}
        {activeTab === "agents" && <AgentDashboard />}
        {activeTab === "supply-chain" && <SupplyChainDashboard />}
        {activeTab === "approvals" && (
          <ApprovalQueue approvals={pendingApprovals} onApprove={handleApprove} />
        )}
        {activeTab === "logs" && <AuditLog logs={logs} />}
        {activeTab === "rules" && (
          <RulesPanel rules={rules} onRefresh={fetchData} apiUrl={API_URL} />
        )}
      </main>
    </div>
  );
}
