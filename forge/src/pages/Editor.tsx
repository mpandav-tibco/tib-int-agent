import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, RefreshCw, Save, Zap } from "lucide-react";
import {
  createAgent, getChatUrl, getAgent, getStatus, listFiles, triggerIngest, updateAgent,
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

type RightTab = "kb" | "chat";

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
}

const DEFAULTS: FormState = {
  name: "", title: "", description: "", system_prompt: "",
  llm_provider: "ollama", llm_model: "", llm_api_key: "", llm_api_base: "", embed_model: "",
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
  const [iframeKey, setIframeKey] = useState(0);  // increment to reload the iframe
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

  // Populate form when agent data arrives
  useEffect(() => {
    if (agent) {
      setForm({
        name: agent.name, title: agent.title, description: agent.description,
        system_prompt: agent.system_prompt, llm_provider: agent.llm_provider,
        llm_model: agent.llm_model, llm_api_key: "",
        llm_api_base: agent.llm_api_base, embed_model: agent.embed_model,
      });
    }
  }, [agent]);

  // Fetch chat URL once agent becomes ready; auto-switch to Test Chat tab
  useEffect(() => {
    if (!id) return;
    const currentStatus = status?.status ?? agent?.status;
    if (currentStatus === "ready" && !chatUrl) {
      getChatUrl(id).then(({ url }) => setChatUrl(url)).catch(() => {});
    }
    // Auto-switch to Test Chat when ingestion just finished
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

  const isReady = status?.status === "ready" || agent?.status === "ready";

  const reloadChat = () => {
    setIframeKey((k) => k + 1);
  };

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

      {/* ── Body: two-column, fills remaining height ────────────────────── */}
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

          {saveMutation.isError && (
            <p className="text-sm text-red-500">{String(saveMutation.error)}</p>
          )}

          {/* Agent meta */}
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

        {/* ── Right: tabbed KB + Chat ──────────────────────────────────── */}
        <main className="flex-1 flex flex-col overflow-hidden">

          {/* Tab bar */}
          <div className="shrink-0 flex items-center gap-1 border-b border-gray-200 bg-white px-4 pt-0">
            <TabButton active={rightTab === "kb"} onClick={() => setRightTab("kb")}>
              Knowledge Base
            </TabButton>
            <TabButton
              active={rightTab === "chat"}
              onClick={() => { setRightTab("chat"); }}
              disabled={isNew}
            >
              Test Chat {isReady ? "●" : "○"}
            </TabButton>

            {/* Reload button shown only in chat tab */}
            {rightTab === "chat" && isReady && (
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
                  <div className="flex gap-3">
                    <button
                      onClick={() => ingestMutation.mutate()}
                      disabled={
                        ingestMutation.isPending ||
                        files.length === 0 ||
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
              {!isReady || !chatUrl ? (
                <div className="flex-1 flex flex-col items-center justify-center gap-4 text-gray-400">
                  <div className="text-4xl">🤖</div>
                  <p className="text-sm font-medium text-gray-500">Agent not ready yet</p>
                  <p className="text-xs text-center max-w-xs">
                    Upload knowledge files and click{" "}
                    <strong>Build Knowledge Base</strong> to make the agent ready for testing.
                  </p>
                  <button
                    onClick={() => setRightTab("kb")}
                    className="text-xs text-brand-600 hover:underline"
                  >
                    Go to Knowledge Base →
                  </button>
                </div>
              ) : (
                <iframe
                  key={iframeKey}
                  src={chatUrl}
                  title={`Chat — ${agent?.name ?? "Agent"}`}
                  className="flex-1 w-full border-0"
                  allow="microphone"
                  // Chainlit must allow iframe embedding — see note in README
                />
              )}
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
