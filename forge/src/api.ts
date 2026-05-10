import type { Agent, AgentFile, IngestStatus } from "./types";

const BASE = "/api/agents";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const listAgents = (): Promise<Agent[]> =>
  fetch(BASE).then(json<Agent[]>);

export const getAgent = (id: string): Promise<Agent> =>
  fetch(`${BASE}/${id}`).then(json<Agent>);

export const createAgent = (body: Partial<Agent>): Promise<Agent> =>
  fetch(BASE, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  }).then(json<Agent>);

export const updateAgent = (id: string, body: Partial<Agent>): Promise<Agent> =>
  fetch(`${BASE}/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  }).then(json<Agent>);

export const deleteAgent = (id: string): Promise<void> =>
  fetch(`${BASE}/${id}`, { method: "DELETE" }).then((r) => {
    if (!r.ok && r.status !== 204) throw new Error(`${r.status}: ${r.statusText}`);
  });

export const listFiles = (id: string): Promise<AgentFile[]> =>
  fetch(`${BASE}/${id}/files`).then(json<AgentFile[]>);

export const uploadFiles = (id: string, files: File[]): Promise<unknown> => {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  return fetch(`${BASE}/${id}/files`, { method: "POST", body: fd }).then(json);
};

export const deleteFile = (id: string, name: string): Promise<void> =>
  fetch(`${BASE}/${id}/files/${encodeURIComponent(name)}`, {
    method: "DELETE",
  }).then((r) => {
    if (!r.ok && r.status !== 204) throw new Error(`${r.status}: ${r.statusText}`);
  });

export const triggerIngest = (id: string): Promise<{ message: string; collection: string }> =>
  fetch(`${BASE}/${id}/ingest`, { method: "POST" }).then(
    json<{ message: string; collection: string }>
  );

export const getStatus = (id: string): Promise<IngestStatus> =>
  fetch(`${BASE}/${id}/status`).then(json<IngestStatus>);

export const getChatUrl = (id: string): Promise<{ url: string }> =>
  fetch(`${BASE}/${id}/chat-url`).then(json<{ url: string }>);
