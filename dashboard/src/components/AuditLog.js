"use client";

const STATUS_STYLES = {
  pending: "bg-amber-100 text-amber-800",
  approved: "bg-blue-100 text-blue-800",
  executed: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  failed: "bg-red-100 text-red-800",
};

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

export default function AuditLog({ logs, compact = false }) {
  if (!logs || logs.length === 0) {
    return (
      <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <h3 className="text-sm font-medium text-gray-700 mb-4">
          {compact ? "Recent Activity" : "Audit Log"}
        </h3>
        <p className="text-gray-400 text-sm">No automation activity yet.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100">
        <h3 className="text-sm font-medium text-gray-700">
          {compact ? "Recent Activity" : `Audit Log (${logs.length} entries)`}
        </h3>
      </div>
      <div className="divide-y divide-gray-50">
        {logs.map((log) => (
          <div key={log.id} className="px-6 py-3 hover:bg-gray-50 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3 min-w-0">
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                    STATUS_STYLES[log.status] || "bg-gray-100 text-gray-800"
                  }`}
                >
                  {log.status}
                </span>
                <span className="text-xs font-medium text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">
                  {TYPE_LABELS[log.automation_type] || log.automation_type}
                </span>
                <span className="text-sm text-gray-700 truncate">
                  {log.action_name.replace(/_/g, " ")}
                </span>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0">
                {log.confidence !== null && (
                  <span className="text-xs text-gray-400">
                    {(log.confidence * 100).toFixed(0)}% conf
                  </span>
                )}
                <span className="text-xs text-gray-400">
                  {new Date(log.timestamp).toLocaleString()}
                </span>
              </div>
            </div>
            {!compact && log.ai_reasoning && (
              <p className="text-xs text-gray-500 mt-1 ml-20 truncate">
                {log.ai_reasoning}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
