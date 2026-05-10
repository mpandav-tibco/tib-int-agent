import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1/agents' })

export interface Agent {
  id: string
  name: string
  title: string
  description: string
  system_prompt: string
  collection_name: string
  llm_provider: string
  llm_model: string
  llm_api_key: string
  llm_api_base: string
  embed_model: string
  created_at: string
  updated_at: string
  status: 'draft' | 'ingesting' | 'ready' | 'error'
}

export interface CreateAgentPayload {
  name: string
  title?: string
  description?: string
  system_prompt?: string
  llm_provider?: string
  llm_model?: string
  llm_api_key?: string
  llm_api_base?: string
  embed_model?: string
}

export interface FileInfo {
  name: string
  size: number
  modified: string
}

export interface IngestStatus {
  agent_id: string
  status: string
  chunks: number
  error: string | null
  started_at: string | null
  finished_at: string | null
}

export const agentsApi = {
  list: () => http.get<Agent[]>('/').then(r => r.data),
  get: (id: string) => http.get<Agent>(`/${id}`).then(r => r.data),
  create: (p: CreateAgentPayload) => http.post<Agent>('/', p).then(r => r.data),
  update: (id: string, p: Partial<CreateAgentPayload>) => http.patch<Agent>(`/${id}`, p).then(r => r.data),
  delete: (id: string) => http.delete(`/${id}`),

  listFiles: (id: string) => http.get<FileInfo[]>(`/${id}/files`).then(r => r.data),
  uploadFiles: (id: string, files: File[]) => {
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    return http.post<{ uploaded: { name: string; size: number }[] }>(`/${id}/files`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  deleteFile: (id: string, filename: string) => http.delete(`/${id}/files/${filename}`),

  ingest: (id: string) => http.post(`/${id}/ingest`).then(r => r.data),
  status: (id: string) => http.get<IngestStatus>(`/${id}/status`).then(r => r.data),
  chatUrl: (id: string) => http.get<{ url: string }>(`/${id}/chat-url`).then(r => r.data),
}
