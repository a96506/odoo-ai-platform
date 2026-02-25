"use client";

export default function StatsCards({ stats }) {
  if (!stats) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/2 mb-3"></div>
            <div className="h-8 bg-gray-200 rounded w-1/3"></div>
          </div>
        ))}
      </div>
    );
  }

  const cards = [
    {
      label: "Total Automations",
      value: stats.total_automations.toLocaleString(),
      sub: `${stats.automations_today} today`,
      color: "text-indigo-600",
      bg: "bg-indigo-50",
    },
    {
      label: "Success Rate",
      value: `${stats.success_rate}%`,
      sub: "of all automations",
      color: "text-green-600",
      bg: "bg-green-50",
    },
    {
      label: "Pending Approvals",
      value: stats.pending_approvals.toString(),
      sub: "need your review",
      color: stats.pending_approvals > 0 ? "text-amber-600" : "text-gray-600",
      bg: stats.pending_approvals > 0 ? "bg-amber-50" : "bg-gray-50",
    },
    {
      label: "Time Saved",
      value: stats.time_saved_minutes >= 60
        ? `${(stats.time_saved_minutes / 60).toFixed(1)}h`
        : `${stats.time_saved_minutes.toFixed(0)}m`,
      sub: "of manual work replaced",
      color: "text-violet-600",
      bg: "bg-violet-50",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
          >
            <p className="text-sm text-gray-500 mb-1">{card.label}</p>
            <p className={`text-3xl font-bold ${card.color}`}>{card.value}</p>
            <p className="text-xs text-gray-400 mt-1">{card.sub}</p>
          </div>
        ))}
      </div>

      {/* By-type breakdown */}
      {stats.by_type && Object.keys(stats.by_type).length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-4">Automations by Module</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {Object.entries(stats.by_type)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <div key={type} className="text-center p-3 rounded-lg bg-gray-50">
                  <p className="text-lg font-semibold text-gray-800">{count}</p>
                  <p className="text-xs text-gray-500 capitalize">{type}</p>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
