
function resolveApiBase() {
  // 1) explicit env var (for static hosting, not typical here)
  if (typeof process !== 'undefined' && process.env && process.env.NEXT_PUBLIC_AILEY_API) {
    return process.env.NEXT_PUBLIC_AILEY_API.replace(/\/$/, '');
  }
  // 2) If the page is opened from a LAN hostname, use that host with API port 5502
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host && host !== '127.0.0.1' && host !== 'localhost') {
      return `http://${host}:5502`;
    }
    // otherwise, when dev, keep localhost
    return 'http://127.0.0.1:5502';
  }
  return 'http://127.0.0.1:5502';
}

export async function sendAileyMessage(message, user = "Simon") {
  const API_BASE = resolveApiBase();
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, user }),
  });
  const data = await res.json();
  return data;
}
