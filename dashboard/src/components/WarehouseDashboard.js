"use client";

import { useState, useEffect, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { fetchApiSafe } from "../lib/api";

function KPICard({ label, value, sub, color = "text-indigo-600" }) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

const STATUS_STYLES = {
  critical: { bg: "bg-red-50", dot: "bg-red-500", text: "text-red-700", label: "Critical" },
  low: { bg: "bg-amber-50", dot: "bg-amber-500", text: "text-amber-700", label: "Low Stock" },
  warning: { bg: "bg-yellow-50", dot: "bg-yellow-400", text: "text-yellow-700", label: "Near Reorder" },
};

export default function WarehouseDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const res = await fetchApiSafe("/api/dashboard/warehouse");
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
    return <p className="text-gray-500 text-center py-12">Unable to load Warehouse dashboard data.</p>;
  }

  const sh = data.shipments || {};

  const chartData = (data.stock_alerts || []).slice(0, 12).map((a) => ({
    name: a.product_name?.length > 18 ? a.product_name.slice(0, 16) + "..." : a.product_name,
    qty: a.qty_available,
    reorder: a.reorder_point,
  }));

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard label="Total Products" value={data.total_products || 0} color="text-indigo-600" />
        <KPICard
          label="Below Reorder"
          value={data.below_reorder || 0}
          sub="need attention"
          color={data.below_reorder > 0 ? "text-red-500" : "text-green-600"}
        />
        <KPICard
          label="Incoming Shipments"
          value={sh.incoming_count || 0}
          sub={`${sh.incoming_ready || 0} ready to receive`}
          color="text-blue-600"
        />
        <KPICard
          label="Outgoing Deliveries"
          value={sh.outgoing_count || 0}
          sub={`${sh.outgoing_ready || 0} ready to ship`}
          color="text-violet-600"
        />
      </div>

      {/* Stock Levels Chart */}
      {chartData.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-4">Stock vs Reorder Point</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="qty" fill="#6366f1" name="In Stock" radius={[4, 4, 0, 0]} />
              <Bar dataKey="reorder" fill="#f97316" name="Reorder Point" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Stock Alerts */}
      {data.stock_alerts?.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-4">Reorder Alerts</h3>
          <div className="space-y-2">
            {data.stock_alerts.map((alert) => {
              const style = STATUS_STYLES[alert.status] || STATUS_STYLES.warning;
              return (
                <div key={alert.product_id} className={`flex items-center justify-between p-3 rounded-lg ${style.bg}`}>
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${style.dot}`} />
                    <div>
                      <p className="text-sm font-medium text-gray-800">{alert.product_name}</p>
                      <p className="text-xs text-gray-500">
                        Qty: {alert.qty_available} / Reorder at: {alert.reorder_point}
                      </p>
                    </div>
                  </div>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded ${style.text} ${style.bg}`}>
                    {style.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Recent Automations */}
      <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-700">Inventory/Purchase Automations (7d)</h3>
          <span className="text-2xl font-bold text-indigo-600">{data.recent_automations || 0}</span>
        </div>
      </div>
    </div>
  );
}
