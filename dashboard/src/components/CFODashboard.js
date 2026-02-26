"use client";

import { useState, useEffect, useCallback } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { fetchApiSafe } from "../lib/api";

function fmt(n) {
  if (n == null) return "$0";
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

function KPICard({ label, value, sub, color = "text-indigo-600" }) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

export default function CFODashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const res = await fetchApiSafe("/api/dashboard/cfo");
    if (res) setData(res);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 30000);
    return () => clearInterval(iv);
  }, [load]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/2 mb-3" />
              <div className="h-7 bg-gray-200 rounded w-1/3" />
            </div>
          ))}
        </div>
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 h-72 animate-pulse" />
      </div>
    );
  }

  if (!data) {
    return <p className="text-gray-500 text-center py-12">Unable to load CFO dashboard data.</p>;
  }

  const forecastData = (data.cash_forecast || []).map((p) => ({
    date: p.date?.slice(5) || "",
    balance: p.balance,
    low: p.low,
    high: p.high,
  }));

  const agingData = (data.ar_aging || []).map((b, i) => ({
    bucket: b.bucket,
    ar: b.amount,
    ap: data.ap_aging?.[i]?.amount || 0,
  }));

  const cs = data.close_status || {};

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard label="Cash Position" value={fmt(data.cash_position)} color="text-indigo-600" />
        <KPICard label="Total AR" value={fmt(data.total_ar)} sub="accounts receivable" color="text-green-600" />
        <KPICard label="Total AP" value={fmt(data.total_ap)} sub="accounts payable" color="text-red-500" />
        <KPICard
          label="Pending Approvals"
          value={data.pending_approvals}
          sub="need your review"
          color={data.pending_approvals > 0 ? "text-amber-600" : "text-gray-600"}
        />
      </div>

      {/* Cash Flow Forecast Chart */}
      {forecastData.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-4">Cash Flow Forecast (90 days)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={forecastData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={fmt} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v) => fmt(v)} />
              <Legend />
              <Area type="monotone" dataKey="high" stroke="none" fill="#c7d2fe" name="High" />
              <Area type="monotone" dataKey="balance" stroke="#4f46e5" fill="#818cf8" fillOpacity={0.3} name="Forecast" strokeWidth={2} />
              <Area type="monotone" dataKey="low" stroke="none" fill="#e0e7ff" name="Low" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* AR/AP Aging Chart */}
      {agingData.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-4">AR / AP Aging</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={agingData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="bucket" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={fmt} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v) => fmt(v)} />
              <Legend />
              <Bar dataKey="ar" fill="#22c55e" name="AR" radius={[4, 4, 0, 0]} />
              <Bar dataKey="ap" fill="#ef4444" name="AP" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* P&L Summary */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-4">P&L Summary — {data.pl_summary?.period || "Current Month"}</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-600">Revenue</span>
              <span className="font-semibold text-green-600">{fmt(data.pl_summary?.total_revenue)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Expenses</span>
              <span className="font-semibold text-red-500">{fmt(data.pl_summary?.total_expenses)}</span>
            </div>
            <hr className="border-gray-100" />
            <div className="flex justify-between">
              <span className="text-gray-700 font-medium">Net Income</span>
              <span className={`font-bold ${(data.pl_summary?.net_income || 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                {fmt(data.pl_summary?.net_income)}
              </span>
            </div>
          </div>
        </div>

        {/* Month-End Close Status */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-4">Month-End Close — {cs.period || "N/A"}</h3>
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Status</span>
              <span className={`font-medium capitalize ${cs.status === "completed" ? "text-green-600" : cs.status === "in_progress" ? "text-amber-600" : "text-gray-500"}`}>
                {cs.status?.replace(/_/g, " ") || "Not Started"}
              </span>
            </div>
            <div>
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>Progress</span>
                <span>{cs.steps_completed || 0} / {cs.steps_total || 0} steps</span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-2.5">
                <div
                  className="bg-indigo-600 h-2.5 rounded-full transition-all"
                  style={{ width: `${cs.progress_pct || 0}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Anomalies */}
      {data.anomalies?.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Recent Anomalies</h3>
          <div className="space-y-2">
            {data.anomalies.map((a, i) => (
              <div key={i} className={`flex items-start gap-3 p-3 rounded-lg ${
                a.severity === "high" ? "bg-red-50" : a.severity === "medium" ? "bg-amber-50" : "bg-blue-50"
              }`}>
                <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                  a.severity === "high" ? "bg-red-500" : a.severity === "medium" ? "bg-amber-500" : "bg-blue-500"
                }`} />
                <div>
                  <p className="text-sm text-gray-800">{a.description}</p>
                  {a.source && <p className="text-xs text-gray-400 mt-0.5">{a.source}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
