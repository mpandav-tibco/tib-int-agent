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
  vector_db: string;
  vector_db_url: string;
  vector_db_api_key: string;  // masked as "***" in list/get responses
  container_id: string;
  deployed_port: number;
  deployed_url: string;
  created_at: string;
  updated_at: string;
  status: "draft" | "ingesting" | "ready" | "error";
  last_ingest_chunks: number;
  last_ingest_at: string;
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

export interface AgentUrl {
  id: string;
  agent_id: string;
  url: string;
  label: string;
  added_at: string;
}

export interface FeedbackEntry {
  ts: number;
  rating: "up" | "down";
  question: string;
  response: string;
}

export interface AgentFeedback {
  agent_id: string;
  thumbs_up: number;
  thumbs_down: number;
  recent: FeedbackEntry[];
}
