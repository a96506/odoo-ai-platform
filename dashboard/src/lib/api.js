const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

export function getApiUrl() {
  return API_URL;
}

export function getWsUrl() {
  const wsBase = process.env.NEXT_PUBLIC_WS_URL || API_URL;
  return wsBase.replace(/^http/, "ws");
}

export async function fetchApi(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };
  if (API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }

  return res.json();
}

export async function fetchApiSafe(path, options = {}) {
  try {
    return await fetchApi(path, options);
  } catch {
    return null;
  }
}
