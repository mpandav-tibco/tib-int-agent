import type { Agent, AgentFile, AgentFeedback, AgentUrl, IngestStatus } from "./types";

const BASE = "/api/agents";
const STORAGE_KEY = "forge_api_key";

function authHeaders(): HeadersInit {
  const key = localStorage.getItem(STORAGE_KEY);
  return key ? { Authorization: `Bearer ${key}` } : {};
}

async function json<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    // Key was revoked or expired — clear it so the app redirects to Login
    localStorage.removeItem(STORAGE_KEY);
    window.location.reload();
    throw new Error("401: Unauthorized");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

function get(url: string): Promise<Response> {
  return fetch(url, { headers: authHeaders() });
}

function mutate(url: string, method: string, body?: object): Promise<Response> {
  return fetch(url, {
    method,
    headers: { ...authHeaders(), ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
}

function upload(url: string, fd: FormData): Promise<Response> {
  return fetch(url, { method: "POST", headers: authHeaders(), body: fd });
}

export const listAgents = (): Promise<Agent[]> =>
  get(BASE).then(json<Agent[]>);

export const getAgent = (id: string): Promise<Agent> =>
  get(`${BASE}/${id}`).then(json<Agent>);

export const createAgent = (body: Partial<Agent>): Promise<Agent> =>
  mutate(BASE, "POST", body).then(json<Agent>);

export const updateAgent = (id: string, body: Partial<Agent>): Promise<Agent> =>
  mutate(`${BASE}/${id}`, "PATCH", body).then(json<Agent>);

export const deleteAgent = (id: string): Promise<void> =>
  mutate(`${BASE}/${id}`, "DELETE").then((r) => {
    if (!r.ok && r.status !== 204) throw new Error(`${r.status}: ${r.statusText}`);
  });

export const listFiles = (id: string): Promise<AgentFile[]> =>
  get(`${BASE}/${id}/files`).then(json<AgentFile[]>);

export const uploadFiles = (id: string, files: File[]): Promise<unknown> => {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  return upload(`${BASE}/${id}/files`, fd).then(json);
};

export const deleteFile = (id: string, name: string): Promise<void> =>
  mutate(`${BASE}/${id}/files/${encodeURIComponent(name)}`, "DELETE").then((r) => {
    if (!r.ok && r.status !== 204) throw new Error(`${r.status}: ${r.statusText}`);
  });

export const triggerIngest = (id: string): Promise<{ message: string; collection: string }> =>
  mutate(`${BASE}/${id}/ingest`, "POST").then(json<{ message: string; collection: string }>);

export const getStatus = (id: string): Promise<IngestStatus> =>
  get(`${BASE}/${id}/status`).then(json<IngestStatus>);

export const getChatUrl = (id: string): Promise<{ url: string }> =>
  get(`${BASE}/${id}/chat-url`).then(json<{ url: string }>);

// ── URL sources ───────────────────────────────────────────────────────────────

export const listUrls = (id: string): Promise<AgentUrl[]> =>
  get(`${BASE}/${id}/urls`).then(json<AgentUrl[]>);

export const addUrl = (id: string, url: string, label = ""): Promise<AgentUrl> =>
  mutate(`${BASE}/${id}/urls`, "POST", { url, label }).then(json<AgentUrl>);

export const deleteUrl = (id: string, urlId: string): Promise<void> =>
  mutate(`${BASE}/${id}/urls/${encodeURIComponent(urlId)}`, "DELETE").then((r) => {
    if (!r.ok && r.status !== 204) throw new Error(`${r.status}: ${r.statusText}`);
  });

// ── Feedback ──────────────────────────────────────────────────────────────────

export const getFeedback = (id: string): Promise<AgentFeedback> =>
  get(`${BASE}/${id}/feedback`).then(json<AgentFeedback>);
