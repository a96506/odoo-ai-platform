"use client";

import { useState, useEffect, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, Cell,
} from "recharts";
import { fetchApiSafe } from "../lib/api";

function fmt(n) {
  if (n == null) return "$0";
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

const STAGE_COLORS = [
  "#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe",
  "#e9d5ff", "#f3e8ff", "#faf5ff",
];

function KPICard({ label, value, sub, color = "text-indigo-600" }) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

export default function SalesDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const res = await fetchApiSafe("/api/dashboard/sales");
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
      </div>
    );
  }

  if (!data) {
    return <p className="text-gray-500 text-center py-12">Unable to load Sales dashboard data.</p>;
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard label="Pipeline Value" value={fmt(data.pipeline_value)} color="text-indigo-600" />
        <KPICard label="Win Rate (90d)" value={`${data.win_rate || 0}%`} color="text-green-600" />
        <KPICard label="Closing This Month" value={data.deals_closing_this_month || 0} sub="deals with deadline" color="text-violet-600" />
        <KPICard label="Revenue MTD" value={fmt(data.revenue_this_month)} sub={data.quota_target ? `${data.quota_pct}% of quota` : "this month"} color="text-emerald-600" />
      </div>

      {/* Pipeline by Stage */}
      {data.pipeline_stages?.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-4">Pipeline by Stage</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data.pipeline_stages} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis type="number" tickFormatter={fmt} tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey="stage" width={120} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v) => fmt(v)} />
              <Legend />
              <Bar dataKey="value" name="Value" radius={[0, 4, 4, 0]}>
                {data.pipeline_stages.map((_, i) => (
                  <Cell key={i} fill={STAGE_COLORS[i % STAGE_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Conversion Funnel */}
      {data.conversion_funnel?.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-4">Conversion Funnel (deal count)</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.conversion_funnel}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="stage" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#8b5cf6" name="Deals" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* At-Risk Deals */}
      {data.at_risk_deals?.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-4">At-Risk Deals</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-100">
                  <th className="py-2 pr-4 font-medium">Deal</th>
                  <th className="py-2 pr-4 font-medium">Value</th>
                  <th className="py-2 pr-4 font-medium">Probability</th>
                  <th className="py-2 pr-4 font-medium">Days Stale</th>
                  <th className="py-2 font-medium">Stage</th>
                </tr>
              </thead>
              <tbody>
                {data.at_risk_deals.map((deal) => (
                  <tr key={deal.lead_id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2.5 pr-4 text-gray-800">{deal.name}</td>
                    <td className="py-2.5 pr-4 font-medium">{fmt(deal.value)}</td>
                    <td className="py-2.5 pr-4">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        deal.probability < 30 ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
                      }`}>
                        {deal.probability}%
                      </span>
                    </td>
                    <td className="py-2.5 pr-4">
                      <span className={deal.days_stale > 30 ? "text-red-600 font-medium" : "text-gray-600"}>
                        {deal.days_stale}d
                      </span>
                    </td>
                    <td className="py-2.5 text-gray-500">{deal.stage}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recent Automations */}
      <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-700">CRM/Sales Automations (7d)</h3>
          <span className="text-2xl font-bold text-indigo-600">{data.recent_automations || 0}</span>
        </div>
      </div>
    </div>
  );
}
