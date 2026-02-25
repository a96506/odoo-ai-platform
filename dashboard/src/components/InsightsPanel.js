"use client";

import { useState } from "react";

const CATEGORY_STYLES = {
  opportunity: { bg: "bg-green-50", text: "text-green-700", border: "border-green-200" },
  risk: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200" },
  efficiency: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200" },
  trend: { bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-200" },
  anomaly: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" },
};

const SEVERITY_DOTS = {
  info: "bg-blue-400",
  warning: "bg-amber-400",
  critical: "bg-red-500",
};

export default function InsightsPanel({ apiUrl }) {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchInsights = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/api/insights`);
      if (res.ok) {
        setInsights(await res.json());
      } else {
        setError("Failed to fetch insights");
      }
    } catch (err) {
      setError("Cannot connect to AI service");
    }
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-800">
            Cross-App Intelligence
          </h2>
          <p className="text-sm text-gray-500">
            AI analyzes data across all modules to surface insights humans might miss
          </p>
        </div>
        <button
          onClick={fetchInsights}
          disabled={loading}
          className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Analyzing..." : insights ? "Refresh Analysis" : "Run Analysis"}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 rounded-xl p-4 text-sm border border-red-200">
          {error}
        </div>
      )}

      {loading && (
        <div className="bg-white rounded-xl p-12 shadow-sm border border-gray-100 text-center">
          <div className="animate-spin w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-sm text-gray-500">
            Analyzing data across all modules...
          </p>
          <p className="text-xs text-gray-400 mt-1">
            This may take 15-30 seconds
          </p>
        </div>
      )}

      {insights && !loading && (
        <div className="space-y-6">
          {/* Executive summary */}
          <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
            <h3 className="text-sm font-medium text-gray-700 mb-2">
              Executive Summary
            </h3>
            <p className="text-sm text-gray-600 leading-relaxed">
              {insights.executive_summary}
            </p>
          </div>

          {/* Insights grid */}
          {insights.insights && insights.insights.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {insights.insights.map((insight, i) => {
                const style = CATEGORY_STYLES[insight.category] || CATEGORY_STYLES.trend;
                return (
                  <div
                    key={i}
                    className={`rounded-xl p-5 border ${style.bg} ${style.border}`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-2 h-2 rounded-full ${
                            SEVERITY_DOTS[insight.severity] || SEVERITY_DOTS.info
                          }`}
                        />
                        <span className={`text-xs font-medium uppercase ${style.text}`}>
                          {insight.category}
                        </span>
                      </div>
                      {insight.affected_modules && (
                        <div className="flex gap-1 flex-wrap">
                          {insight.affected_modules.map((m) => (
                            <span
                              key={m}
                              className="text-[10px] bg-white/60 text-gray-600 px-1.5 py-0.5 rounded"
                            >
                              {m}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <h4 className={`text-sm font-semibold mb-1 ${style.text}`}>
                      {insight.title}
                    </h4>
                    <p className="text-sm text-gray-600 mb-3">
                      {insight.description}
                    </p>
                    {insight.recommended_action && (
                      <div className="bg-white/50 rounded-lg p-2">
                        <p className="text-xs text-gray-500">
                          <span className="font-medium">Recommended:</span>{" "}
                          {insight.recommended_action}
                        </p>
                      </div>
                    )}
                    {insight.estimated_impact && (
                      <p className="text-xs text-gray-400 mt-2">
                        Impact: {insight.estimated_impact}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {!insights && !loading && !error && (
        <div className="bg-white rounded-xl p-12 shadow-sm border border-gray-100 text-center">
          <div className="w-16 h-16 rounded-full bg-indigo-50 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <p className="text-sm text-gray-500 mb-1">
            Click &quot;Run Analysis&quot; to get AI-powered cross-module insights
          </p>
          <p className="text-xs text-gray-400">
            The AI will analyze your sales pipeline, invoices, stock levels,
            projects, and HR data together
          </p>
        </div>
      )}
    </div>
  );
}
