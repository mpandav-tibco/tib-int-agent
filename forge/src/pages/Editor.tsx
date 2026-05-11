import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Box, Container, Download, ExternalLink, Globe, Link2, RefreshCw,
  Save, Square, ThumbsDown, ThumbsUp, Trash2, Zap,
} from "lucide-react";
import {
  addUrl, createAgent, deleteUrl, deployAgent, exportAgent, getChatUrl, getAgent,
  getFeedback, getDeployStatus, getStatus, listFiles, listUrls, triggerIngest,
  undeployAgent, updateAgent,
} from "../api";
import FileUpload from "../components/FileUpload";
import IngestStatus from "../components/IngestStatus";
import type { Agent } from "../types";

const PROVIDER_HINTS: Record<string, string> = {
  ollama:         "deepseek-r1:latest · llama3.1:8b · mistral:7b",
  openai:         "gpt-4o · gpt-4o-mini · gpt-3.5-turbo",
  anthropic:      "claude-opus-4-7 · claude-sonnet-4-6 · claude-haiku-4-5-20251001",
  groq:           "llama-3.3-70b-versatile · deepseek-r1-distill-llama-70b",
  "ollama-cloud": "llama3.3:70b-instruct-cloud · deepseek-v3.1:671b-cloud",
  custom:         "depends on your provider",
};

const VDB_URL_PLACEHOLDER: Record<string, string> = {
  weaviate:     "http://localhost:8080",
  chroma:       "http://localhost:8000 (or blank for embedded local storage)",
  qdrant:       "http://localhost:6333 (or blank for in-memory)",
  pinecone:     "https://<index>-<project>.svc.<env>.pinecone.io",
  pgvector:     "postgresql://user:pass@host:5432/dbname",
  activespaces: "tibcosub://hostname:port",
};

const VDB_HELP: Record<string, string> = {
  weaviate:     "Default vector store. Requires a running Weaviate instance.",
  chroma:       "Leave URL blank to use embedded local storage (no server needed).",
  qdrant:       "Leave URL blank for in-memory mode (data lost on restart).",
  pinecone:     "Provide your Pinecone host URL and API key from the Pinecone console.",
  pgvector:     "PostgreSQL with the pgvector extension. Use a full DSN as the URL.",
  activespaces: "Requires the TIBCO ActiveSpaces Python SDK installed separately.",
};

const VDB_NEEDS_KEY = new Set(["pinecone", "activespaces"]);

type RightTab = "kb" | "chat" | "feedback" | "deploy";

interface FormState {
  name: string;
  title: string;
  description: string;
  system_prompt: string;
  llm_provider: string;
  llm_model: string;
  llm_api_key: string;
  llm_api_base: string;
  embed_model: string;
  vector_db: string;
  vector_db_url: string;
  vector_db_api_key: string;
}

const DEFAULTS: FormState = {
  name: "", title: "", description: "", system_prompt: "",
  llm_provider: "ollama", llm_model: "", llm_api_key: "", llm_api_base: "", embed_model: "",
  vector_db: "weaviate", vector_db_url: "", vector_db_api_key: "",
};

export default function Editor() {
  const { id } = useParams<{ id?: string }>();
  const isNew = !id;
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [saved, setSaved] = useState(false);
  const [rightTab, setRightTab] = useState<RightTab>("kb");
  const [chatUrl, setChatUrl] = useState<string | null>(null);
  const [iframeKey, setIframeKey] = useState(0);
  const [newUrl, setNewUrl] = useState("");
  const [newUrlLabel, setNewUrlLabel] = useState("");
  const prevStatus = useRef<string | undefined>(undefined);

  const { data: agent } = useQuery({
    queryKey: ["agent", id],
    queryFn: () => getAgent(id!),
    enabled: !isNew,
  });

  const { data: files = [] } = useQuery({
    queryKey: ["files", id],
    queryFn: () => listFiles(id!),
    enabled: !isNew,
    refetchInterval: 5000,
  });

  const { data: status } = useQuery({
    queryKey: ["status", id],
    queryFn: () => getStatus(id!),
    enabled: !isNew,
    refetchInterval: (q) => q.state.data?.status === "ingesting" ? 3000 : 10000,
  });

  const { data: urls = [], refetch: refetchUrls } = useQuery({
    queryKey: ["urls", id],
    queryFn: () => listUrls(id!),
    enabled: !isNew,
  });

  const { data: feedback } = useQuery({
    queryKey: ["feedback", id],
    queryFn: () => getFeedback(id!),
    enabled: !isNew && rightTab === "feedback",
    refetchInterval: rightTab === "feedback" ? 15000 : false,
  });

  useEffect(() => {
    if (agent) {
      setForm({
        name: agent.name, title: agent.title, description: agent.description,
        system_prompt: agent.system_prompt, llm_provider: agent.llm_provider,
        llm_model: agent.llm_model, llm_api_key: "",
        llm_api_base: agent.llm_api_base, embed_model: agent.embed_model,
        vector_db: agent.vector_db ?? "weaviate",
        vector_db_url: agent.vector_db_url ?? "",
        vector_db_api_key: "",
      });
    }
  }, [agent]);

  // Fetch chat URL for saved agents; auto-switch to Test Chat after ingest completes
  useEffect(() => {
    if (!id) return;
    const currentStatus = status?.status ?? agent?.status;
    if (!chatUrl) {
      getChatUrl(id).then(({ url }) => setChatUrl(url)).catch(() => {});
    }
    if (prevStatus.current === "ingesting" && currentStatus === "ready") {
      setRightTab("chat");
      setIframeKey((k) => k + 1);
    }
    prevStatus.current = currentStatus;
  }, [status?.status, agent?.status, id, chatUrl]);

  const set = (key: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value }));

  const saveMutation = useMutation({
    mutationFn: async (): Promise<Agent> => {
      const payload = { ...form };
      if (!payload.llm_api_key) delete (payload as Partial<FormState>).llm_api_key;
      if (!payload.vector_db_api_key) delete (payload as Partial<FormState>).vector_db_api_key;
      return isNew ? createAgent(payload) : updateAgent(id!, payload);
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["agent", saved.id] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      if (isNew) navigate(`/agents/${saved.id}`, { replace: true });
    },
  });

  const ingestMutation = useMutation({
    mutationFn: () => triggerIngest(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["status", id] }),
  });

  const addUrlMutation = useMutation({
    mutationFn: () => addUrl(id!, newUrl.trim(), newUrlLabel.trim()),
    onSuccess: () => {
      setNewUrl("");
      setNewUrlLabel("");
      refetchUrls();
    },
  });

  const deleteUrlMutation = useMutation({
    mutationFn: (urlId: string) => deleteUrl(id!, urlId),
    onSuccess: () => refetchUrls(),
  });

  const deployMutation = useMutation({
    mutationFn: () => deployAgent(id!),
    onSuccess: (updated) => {
      qc.setQueryData(["agent", id], updated);
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  const undeployMutation = useMutation({
    mutationFn: () => undeployAgent(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent", id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  const { data: deployStatus } = useQuery({
    queryKey: ["deploy-status", id],
    queryFn: () => getDeployStatus(id!),
    enabled: !isNew && !!agent?.container_id,
    refetchInterval: agent?.container_id ? 10000 : false,
  });

  function triggerExport(format: "docker-compose" | "kubernetes") {
    exportAgent(id!, format).then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${agent?.name ?? "agent"}-${format}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    }).catch((err) => console.error("Export failed:", err));
  }

  const isReady = status?.status === "ready" || agent?.status === "ready";
  const isIngesting = status?.status === "ingesting" || agent?.status === "ingesting";

  const reloadChat = () => setIframeKey((k) => k + 1);

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="shrink-0 bg-white border-b border-gray-200 px-6 py-3">
        <div className="max-w-full flex items-center gap-4">
          <button
            onClick={() => navigate("/")}
            className="text-gray-400 hover:text-gray-700 transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold text-gray-900 truncate">
              {isNew ? "New Agent" : (agent?.name ?? "Edit Agent")}
            </h1>
            {!isNew && agent?.title && (
              <p className="text-xs text-gray-500 truncate">{agent.title}</p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {!isNew && chatUrl && (
              <a
                href={chatUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-xs text-brand-600 hover:text-brand-700 border border-brand-200 hover:border-brand-400 px-3 py-1.5 rounded-lg transition-colors"
              >
                <ExternalLink size={13} /> Open in new tab
              </a>
            )}
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending || !form.name.trim()}
              className="flex items-center gap-1.5 bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white text-sm font-medium px-4 py-1.5 rounded-lg transition-colors"
            >
              <Save size={14} />
              {saveMutation.isPending ? "Saving…" : saved ? "Saved ✓" : "Save"}
            </button>
          </div>
        </div>
      </header>

      {/* ── Body ────────────────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">

        {/* ── Left: scrollable config form ──────────────────────────────── */}
        <aside className="w-[420px] shrink-0 border-r border-gray-200 bg-white overflow-y-auto p-5 space-y-5">

          {/* Identity */}
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400">Identity</h2>
            <Field label="Name *">
              <input value={form.name} onChange={set("name")}
                placeholder="e.g. Customer Support Bot" className="input" />
            </Field>
            <Field label="Title">
              <input value={form.title} onChange={set("title")}
                placeholder="e.g. Friendly billing helper" className="input" />
            </Field>
            <Field label="Description">
              <input value={form.description} onChange={set("description")}
                placeholder="One-liner shown on the gallery card" className="input" />
            </Field>
            <Field label="System Prompt">
              <textarea
                value={form.system_prompt} onChange={set("system_prompt")} rows={9}
                placeholder={
                  "You are a helpful assistant for Acme Corp.\n\n" +
                  "You specialise in billing and subscription questions.\n" +
                  "Always be concise and professional."
                }
                className="input resize-none font-mono text-xs leading-relaxed"
              />
              <p className="text-xs text-gray-400 mt-0.5">
                Leave blank to use the built-in TARA default.
              </p>
            </Field>
          </section>

          <hr className="border-gray-100" />

          {/* LLM Config */}
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400">LLM</h2>
            <Field label="Provider">
              <select value={form.llm_provider} onChange={set("llm_provider")} className="input">
                {["ollama", "openai", "anthropic", "groq", "ollama-cloud", "custom"].map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </Field>
            <Field label="Model">
              <input value={form.llm_model} onChange={set("llm_model")}
                placeholder={PROVIDER_HINTS[form.llm_provider] ?? "model name"} className="input" />
            </Field>
            <Field label="API Key">
              <input type="password" value={form.llm_api_key} onChange={set("llm_api_key")}
                placeholder="Leave blank for local Ollama" className="input" />
            </Field>
            <Field label="API Base URL">
              <input value={form.llm_api_base} onChange={set("llm_api_base")}
                placeholder="For Groq / custom providers" className="input" />
            </Field>
            <Field label="Embed Model">
              <input value={form.embed_model} onChange={set("embed_model")}
                placeholder="nomic-embed-text (default)" className="input" />
            </Field>
          </section>

          <hr className="border-gray-100" />

          {/* Vector Store Config */}
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400">Vector Store</h2>
            <Field label="Backend">
              <select value={form.vector_db} onChange={set("vector_db")} className="input">
                {["weaviate", "chroma", "qdrant", "pinecone", "pgvector", "activespaces"].map((db) => (
                  <option key={db} value={db}>{db}</option>
                ))}
              </select>
              {VDB_HELP[form.vector_db] && (
                <p className="text-xs text-gray-400 mt-0.5">{VDB_HELP[form.vector_db]}</p>
              )}
            </Field>
            <Field label="URL">
              <input
                value={form.vector_db_url}
                onChange={set("vector_db_url")}
                placeholder={VDB_URL_PLACEHOLDER[form.vector_db] ?? ""}
                className="input"
              />
            </Field>
            {(VDB_NEEDS_KEY.has(form.vector_db)) && (
              <Field label="API Key">
                <input
                  type="password"
                  value={form.vector_db_api_key}
                  onChange={set("vector_db_api_key")}
                  placeholder="Required for this backend"
                  className="input"
                />
              </Field>
            )}
          </section>

          {saveMutation.isError && (
            <p className="text-sm text-red-500">{String(saveMutation.error)}</p>
          )}

          {!isNew && agent && (
            <>
              <hr className="border-gray-100" />
              <section className="space-y-1">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400">Info</h2>
                <dl className="text-xs text-gray-400 space-y-0.5">
                  <Row label="ID"><span className="font-mono">{agent.id}</span></Row>
                  <Row label="Collection"><span className="font-mono">{agent.collection_name}</span></Row>
                  <Row label="Status">{agent.status}</Row>
                  <Row label="Created">{new Date(agent.created_at).toLocaleString()}</Row>
                </dl>
              </section>
            </>
          )}
        </aside>

        {/* ── Right: tabbed KB + Chat + Feedback ──────────────────────────── */}
        <main className="flex-1 flex flex-col overflow-hidden">

          {/* Tab bar */}
          <div className="shrink-0 flex items-center gap-1 border-b border-gray-200 bg-white px-4 pt-0">
            <TabButton active={rightTab === "kb"} onClick={() => setRightTab("kb")}>
              Knowledge Base
            </TabButton>
            <TabButton
              active={rightTab === "chat"}
              onClick={() => setRightTab("chat")}
              disabled={isNew}
            >
              Test Chat {isReady ? "●" : isIngesting ? "◌" : "○"}
            </TabButton>
            <TabButton
              active={rightTab === "feedback"}
              onClick={() => setRightTab("feedback")}
              disabled={isNew}
            >
              Feedback
            </TabButton>
            <TabButton
              active={rightTab === "deploy"}
              onClick={() => setRightTab("deploy")}
              disabled={isNew}
            >
              Deploy
            </TabButton>

            {rightTab === "chat" && chatUrl && (
              <button
                onClick={reloadChat}
                title="Reload chat (start fresh conversation)"
                className="ml-auto flex items-center gap-1 text-xs text-gray-400 hover:text-gray-700 px-2 py-1 rounded transition-colors"
              >
                <RefreshCw size={13} /> Reload
              </button>
            )}
          </div>

          {/* ── KB tab ────────────────────────────────────────────────── */}
          {rightTab === "kb" && (
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              {isNew ? (
                <div className="text-center text-gray-400 py-12 text-sm">
                  Save the agent first to upload knowledge files.
                </div>
              ) : (
                <>
                  <FileUpload agentId={id!} files={files} />
                  <IngestStatus agentId={id!} />

                  {/* URL Sources */}
                  <section className="space-y-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
                      <Globe size={12} /> URL Sources
                    </h3>
                    {urls.length > 0 && (
                      <ul className="space-y-1.5">
                        {urls.map((u) => (
                          <li key={u.id} className="flex items-center gap-2 text-sm bg-gray-50 rounded-lg px-3 py-2">
                            <Link2 size={13} className="shrink-0 text-gray-400" />
                            <div className="flex-1 min-w-0">
                              <p className="truncate text-gray-800">{u.url}</p>
                              {u.label && <p className="text-xs text-gray-400 truncate">{u.label}</p>}
                            </div>
                            <button
                              onClick={() => deleteUrlMutation.mutate(u.id)}
                              className="shrink-0 text-gray-300 hover:text-red-500 transition-colors"
                            >
                              <Trash2 size={13} />
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="space-y-2">
                      <input
                        value={newUrl}
                        onChange={(e) => setNewUrl(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && newUrl.trim() && addUrlMutation.mutate()}
                        placeholder="https://docs.example.com/page"
                        className="input text-sm"
                      />
                      <div className="flex gap-2">
                        <input
                          value={newUrlLabel}
                          onChange={(e) => setNewUrlLabel(e.target.value)}
                          placeholder="Label (optional)"
                          className="input text-sm flex-1"
                        />
                        <button
                          onClick={() => addUrlMutation.mutate()}
                          disabled={!newUrl.trim() || addUrlMutation.isPending}
                          className="shrink-0 flex items-center gap-1.5 bg-gray-100 hover:bg-gray-200 disabled:opacity-40 text-gray-700 text-sm px-3 py-2 rounded-lg transition-colors"
                        >
                          <Globe size={13} /> Add URL
                        </button>
                      </div>
                      {addUrlMutation.isError && (
                        <p className="text-xs text-red-500">{String(addUrlMutation.error)}</p>
                      )}
                    </div>
                  </section>

                  <div className="flex gap-3">
                    <button
                      onClick={() => ingestMutation.mutate()}
                      disabled={
                        ingestMutation.isPending ||
                        (files.length === 0 && urls.length === 0) ||
                        status?.status === "ingesting"
                      }
                      className="flex items-center gap-2 bg-gray-800 hover:bg-gray-900 disabled:opacity-40 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                    >
                      <Zap size={14} />
                      {status?.status === "ingesting" ? "Ingesting…" : "Build Knowledge Base"}
                    </button>
                    {isReady && (
                      <button
                        onClick={() => setRightTab("chat")}
                        className="flex items-center gap-2 text-sm text-brand-600 hover:text-brand-700 border border-brand-200 px-4 py-2 rounded-lg transition-colors"
                      >
                        Test Chat →
                      </button>
                    )}
                  </div>
                  {ingestMutation.isError && (
                    <p className="text-sm text-red-500">{String(ingestMutation.error)}</p>
                  )}
                </>
              )}
            </div>
          )}

          {/* ── Chat tab ──────────────────────────────────────────────── */}
          {rightTab === "chat" && (
            <div className="flex-1 flex flex-col overflow-hidden">
              {!chatUrl ? (
                <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
                  Loading chat…
                </div>
              ) : (
                <>
                  {!isReady && (
                    <div className="shrink-0 bg-amber-50 border-b border-amber-100 px-4 py-2 text-xs text-amber-700 flex items-center gap-2">
                      <span>⚠</span>
                      No knowledge base built yet — the agent will answer from its system prompt only.
                      <button
                        onClick={() => setRightTab("kb")}
                        className="underline hover:no-underline"
                      >
                        Build KB →
                      </button>
                    </div>
                  )}
                  <iframe
                    key={iframeKey}
                    src={chatUrl}
                    title={`Chat — ${agent?.name ?? "Agent"}`}
                    className="flex-1 w-full border-0"
                    allow="microphone"
                  />
                </>
              )}
            </div>
          )}

          {/* ── Feedback tab ──────────────────────────────────────────── */}
          {rightTab === "feedback" && (
            <div className="flex-1 overflow-y-auto p-6">
              {!feedback ? (
                <div className="text-center text-gray-400 py-12 text-sm">Loading feedback…</div>
              ) : (
                <div className="space-y-6">
                  {/* Summary counts */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-green-50 border border-green-100 rounded-xl p-4 flex items-center gap-3">
                      <ThumbsUp size={20} className="text-green-500 shrink-0" />
                      <div>
                        <p className="text-2xl font-bold text-green-700">{feedback.thumbs_up}</p>
                        <p className="text-xs text-green-600">Positive</p>
                      </div>
                    </div>
                    <div className="bg-red-50 border border-red-100 rounded-xl p-4 flex items-center gap-3">
                      <ThumbsDown size={20} className="text-red-400 shrink-0" />
                      <div>
                        <p className="text-2xl font-bold text-red-600">{feedback.thumbs_down}</p>
                        <p className="text-xs text-red-500">Negative</p>
                      </div>
                    </div>
                  </div>

                  {/* Recent rated exchanges */}
                  {feedback.recent.length === 0 ? (
                    <p className="text-sm text-gray-400 text-center py-8">
                      No rated exchanges yet — test the agent and rate some responses.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
                        Recent Rated Exchanges
                      </h3>
                      {feedback.recent.map((entry, i) => (
                        <div key={i} className="bg-white border border-gray-100 rounded-xl p-4 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                              entry.rating === "up"
                                ? "bg-green-100 text-green-700"
                                : "bg-red-100 text-red-600"
                            }`}>
                              {entry.rating === "up" ? "👍 Positive" : "👎 Negative"}
                            </span>
                            <span className="text-xs text-gray-400">
                              {new Date(entry.ts * 1000).toLocaleString()}
                            </span>
                          </div>
                          {entry.question && (
                            <div>
                              <p className="text-xs font-medium text-gray-500 mb-0.5">Question</p>
                              <p className="text-sm text-gray-800 line-clamp-2">{entry.question}</p>
                            </div>
                          )}
                          {entry.response && (
                            <div>
                              <p className="text-xs font-medium text-gray-500 mb-0.5">Response</p>
                              <p className="text-sm text-gray-600 line-clamp-3">{entry.response}</p>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          {/* ── Deploy tab ────────────────────────────────────────────── */}
          {rightTab === "deploy" && (
            <div className="flex-1 overflow-y-auto p-6 space-y-6">

              {/* Docker section */}
              <section className="space-y-4">
                <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
                  <Container size={13} /> Docker
                </h3>
                <p className="text-xs text-gray-400">
                  Image: <span className="font-mono">tibco-ai-agent-chainlit:latest</span>
                  {" "}— build with{" "}
                  <span className="font-mono">docker build -t tibco-ai-agent-chainlit:latest -f Dockerfile .</span>
                </p>

                {agent?.container_id ? (
                  /* Running state */
                  <div className="bg-green-50 border border-green-100 rounded-xl p-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
                      <span className="text-sm font-medium text-green-800">
                        {deployStatus?.status === "running" ? "Running" : (deployStatus?.status ?? "Deployed")}
                      </span>
                    </div>
                    <a
                      href={agent.deployed_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 text-sm text-brand-600 hover:underline"
                    >
                      <ExternalLink size={13} /> {agent.deployed_url}
                    </a>
                    <p className="text-xs text-gray-400 font-mono truncate">
                      Container: {agent.container_id.slice(0, 12)}
                    </p>
                    <button
                      onClick={() => undeployMutation.mutate()}
                      disabled={undeployMutation.isPending}
                      className="flex items-center gap-1.5 bg-red-50 hover:bg-red-100 border border-red-200 text-red-700 text-sm px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                    >
                      <Square size={13} />
                      {undeployMutation.isPending ? "Stopping…" : "Stop Container"}
                    </button>
                    {undeployMutation.isError && (
                      <p className="text-xs text-red-500">{String(undeployMutation.error)}</p>
                    )}
                  </div>
                ) : (
                  /* Not deployed state */
                  <div className="flex gap-3 flex-wrap">
                    <button
                      onClick={() => deployMutation.mutate()}
                      disabled={deployMutation.isPending}
                      className="flex items-center gap-2 bg-gray-800 hover:bg-gray-900 disabled:opacity-40 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                    >
                      <Box size={14} />
                      {deployMutation.isPending ? "Deploying…" : "Deploy to Docker"}
                    </button>
                    <button
                      onClick={() => triggerExport("docker-compose")}
                      className="flex items-center gap-2 text-sm text-gray-700 border border-gray-200 hover:border-gray-400 px-4 py-2 rounded-lg transition-colors"
                    >
                      <Download size={14} /> Export Compose
                    </button>
                  </div>
                )}
                {deployMutation.isError && (
                  <p className="text-sm text-red-500">{String(deployMutation.error)}</p>
                )}
              </section>

              <hr className="border-gray-100" />

              {/* Kubernetes section */}
              <section className="space-y-4">
                <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
                  <Globe size={13} /> Kubernetes
                </h3>
                <p className="text-xs text-gray-400">
                  Downloads a ZIP with <span className="font-mono">deployment.yaml</span>,{" "}
                  <span className="font-mono">service.yaml</span>,{" "}
                  <span className="font-mono">ingress.yaml</span>,{" "}
                  <span className="font-mono">secret.yaml</span>,{" "}
                  <span className="font-mono">configmap.yaml</span>,{" "}
                  <span className="font-mono">kustomization.yaml</span> + README.
                  Apply with <span className="font-mono">kubectl apply -k .</span>
                </p>
                <button
                  onClick={() => triggerExport("kubernetes")}
                  className="flex items-center gap-2 text-sm text-gray-700 border border-gray-200 hover:border-gray-400 px-4 py-2 rounded-lg transition-colors"
                >
                  <Download size={14} /> Export Manifests
                </button>
              </section>

            </div>
          )}

        </main>
      </div>
    </div>
  );
}

// ── Small reusable pieces ─────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-gray-600">{label}</label>
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <dt className="w-24 shrink-0 font-medium">{label}</dt>
      <dd className="truncate">{children}</dd>
    </div>
  );
}

function TabButton({
  active, onClick, disabled, children,
}: {
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors
        ${active
          ? "border-brand-500 text-brand-600"
          : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"}
        disabled:opacity-40 disabled:cursor-not-allowed`}
    >
      {children}
    </button>
  );
}
