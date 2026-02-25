"use client";

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

export default function ApprovalQueue({
  approvals,
  onApprove,
  compact = false,
}) {
  if (!approvals || approvals.length === 0) {
    return (
      <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <h3 className="text-sm font-medium text-gray-700 mb-4">
          {compact ? "Pending Approvals" : "Approval Queue"}
        </h3>
        <div className="text-center py-8">
          <div className="w-12 h-12 rounded-full bg-green-50 flex items-center justify-center mx-auto mb-3">
            <svg className="w-6 h-6 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <p className="text-gray-400 text-sm">All caught up! No pending approvals.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100">
        <h3 className="text-sm font-medium text-gray-700">
          {compact
            ? `Pending Approvals (${approvals.length})`
            : `Approval Queue (${approvals.length} pending)`}
        </h3>
      </div>
      <div className="divide-y divide-gray-50">
        {approvals.map((item) => (
          <div key={item.id} className="px-6 py-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">
                    {TYPE_LABELS[item.automation_type] || item.automation_type}
                  </span>
                  <span className="text-sm font-medium text-gray-700">
                    {item.action_name.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-xs text-gray-500 mb-1">
                  {item.odoo_model} #{item.odoo_record_id}
                </p>
                {item.ai_reasoning && (
                  <p className="text-xs text-gray-500 line-clamp-2">
                    {item.ai_reasoning}
                  </p>
                )}
                {item.confidence !== null && (
                  <div className="flex items-center gap-2 mt-2">
                    <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden max-w-[120px]">
                      <div
                        className={`h-full rounded-full ${
                          item.confidence >= 0.9
                            ? "bg-green-500"
                            : item.confidence >= 0.8
                            ? "bg-amber-500"
                            : "bg-red-500"
                        }`}
                        style={{ width: `${item.confidence * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-400">
                      {(item.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                )}
              </div>
              <div className="flex gap-2 flex-shrink-0">
                <button
                  onClick={() => onApprove(item.id, true)}
                  className="px-3 py-1.5 text-xs font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg transition-colors"
                >
                  Approve
                </button>
                <button
                  onClick={() => onApprove(item.id, false)}
                  className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
