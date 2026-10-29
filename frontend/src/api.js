const API_BASE = "";

export async function fetchDashboard() {
  const res = await fetch(`${API_BASE}/api/dashboard`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchProjectDetails(id) {
  const res = await fetch(`${API_BASE}/api/projects/${id}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchEntityData({ entity, page = 1, limit = 50, search = "", status = "", projectId = null }) {
  const params = new URLSearchParams({ page, limit });
  if (search) params.append("search", search);
  if (status) params.append("status", status);
  if (projectId) params.append("project_id", projectId);

  const res = await fetch(`${API_BASE}/api/data/${entity}?${params.toString()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchModels() {
  const res = await fetch(`${API_BASE}/api/models`);
  if (!res.ok) return { models: [], default: "" };
  return res.json();
}

export async function triggerSync() {
  const res = await fetch(`${API_BASE}/api/sync`, { method: "POST" });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchSyncStatus() {
  const res = await fetch(`${API_BASE}/api/sync/status`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchMe() {
  const res = await fetch(`${API_BASE}/api/me`);
  if (!res.ok) return { authenticated: false };
  return res.json();
}

export function streamChatQuery({ question, history, model, onSources, onToken, onError, onDone }) {
  const controller = new AbortController();

  fetch(`${API_BASE}/api/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history, model }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const event = JSON.parse(raw);
            if (event.type === "sources" && onSources) {
              onSources(event.sources);
            } else if (event.type === "token" && onToken) {
              onToken(event.token);
            } else if (event.type === "error" && onError) {
              onError(new Error(event.error));
            } else if (event.type === "done" && onDone) {
              onDone();
            }
          } catch (e) {
            console.error("JSON parse error:", e);
          }
        }
      }
      if (onDone) onDone();
    })
    .catch((err) => {
      if (err.name !== "AbortError" && onError) {
        onError(err);
      }
    });

  return controller;
}
