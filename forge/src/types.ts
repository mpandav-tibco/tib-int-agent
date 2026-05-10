export interface Agent {
  id: string;
  name: string;
  title: string;
  description: string;
  system_prompt: string;
  collection_name: string;
  llm_provider: string;
  llm_model: string;
  llm_api_key: string;   // masked as "***" in list/get responses
  llm_api_base: string;
  embed_model: string;
  created_at: string;
  updated_at: string;
  status: "draft" | "ingesting" | "ready" | "error";
}

export interface AgentFile {
  name: string;
  size: number;
  modified: string;
}

export interface IngestStatus {
  agent_id: string;
  status: "draft" | "ingesting" | "ready" | "error";
  chunks: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}
