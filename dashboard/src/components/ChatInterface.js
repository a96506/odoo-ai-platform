"use client";

import { useState, useRef, useEffect } from "react";

export default function ChatInterface({ apiUrl }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hello! I'm your Odoo AI assistant. Ask me anything about your business data — sales, invoices, inventory, projects, HR — in plain English. I can also take actions like creating records or confirming orders (with your approval).",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState(null);
  const messagesEnd = useRef(null);
  const sessionId = useRef(`session-${Date.now()}`);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    try {
      const res = await fetch(`${apiUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMsg,
          session_id: sessionId.current,
        }),
      });

      const data = await res.json();

      if (data.needs_confirmation) {
        setPendingConfirmation(data.confirmation_details);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.response || "I'd like to make some changes. Please review and confirm:",
            confirmation: data.confirmation_details,
          },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.response },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I couldn't connect to the AI service. Please check if it's running.",
          error: true,
        },
      ]);
    }

    setLoading(false);
  };

  const handleConfirmation = async (confirmed) => {
    setLoading(true);
    setPendingConfirmation(null);

    try {
      const res = await fetch(`${apiUrl}/api/chat/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId.current,
          confirmed,
        }),
      });

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.response,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Failed to process confirmation.", error: true },
      ]);
    }

    setLoading(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 flex flex-col h-[calc(100vh-220px)] min-h-[500px]">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                msg.role === "user"
                  ? "bg-indigo-600 text-white"
                  : msg.error
                  ? "bg-red-50 text-red-700 border border-red-200"
                  : "bg-gray-100 text-gray-800"
              }`}
            >
              <p className="text-sm whitespace-pre-wrap">{msg.content}</p>

              {msg.confirmation && (
                <div className="mt-3 space-y-2">
                  {msg.confirmation.map((action, j) => (
                    <div
                      key={j}
                      className="bg-white/80 rounded-lg p-2 text-xs text-gray-600"
                    >
                      <span className="font-medium">
                        {action.action.replace("odoo_", "")}:
                      </span>{" "}
                      {action.details.description || JSON.stringify(action.details)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl px-4 py-3">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0.1s" }} />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0.2s" }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEnd} />
      </div>

      {/* Confirmation buttons */}
      {pendingConfirmation && (
        <div className="px-4 py-3 border-t border-gray-100 bg-amber-50 flex items-center justify-between">
          <span className="text-sm text-amber-700 font-medium">
            Confirm the changes above?
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => handleConfirmation(true)}
              disabled={loading}
              className="px-4 py-1.5 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg disabled:opacity-50"
            >
              Confirm
            </button>
            <button
              onClick={() => handleConfirmation(false)}
              disabled={loading}
              className="px-4 py-1.5 text-sm font-medium text-gray-600 bg-gray-200 hover:bg-gray-300 rounded-lg disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="p-4 border-t border-gray-100">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your business... (e.g. 'Show me unpaid invoices over $1000')"
            className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none text-sm"
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
          >
            Send
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2 text-center">
          Powered by Claude AI. Write/create actions require your confirmation.
        </p>
      </div>
    </div>
  );
}
