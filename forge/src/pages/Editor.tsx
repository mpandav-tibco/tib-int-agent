import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Save, Zap } from "lucide-react";
import {
  createAgent, getChatUrl, getAgent, listFiles, triggerIngest, updateAgent,
} from "../api";
import FileUpload from "../components/FileUpload";
import IngestStatus from "../components/IngestStatus";
import type { Agent } from "../types";

const PROVIDER_HINTS: Record<string, string> = {
  ollama:       "deepseek-r1:latest · llama3.1:8b · mistral:7b",
  openai:       "gpt-4o · gpt-4o-mini · gpt-3.5-turbo",
  anthropic:    "claude-opus-4-7 · claude-sonnet-4-6 · claude-haiku-4-5-20251001",
  groq:         "llama-3.3-70b-versatile · deepseek-r1-distill-llama-70b",
  "ollama-cloud": "llama3.3:70b-instruct-cloud · deepseek-v3.1:671b-cloud",
  custom:       "depends on your provider",
};

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
  name: "",
  title: "",
  description: "",
  system_prompt: "",
  llm_provider: "ollama",
  llm_model: "",
  llm_api_key: "",
  llm_api_base: "",
  embed_model: "",
};

export default function Editor() {
  const { id } = useParams<{ id?: string }>();
  const isNew = !id;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [saved, setSaved] = useState(false);

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
    queryFn: () => import("../api").then((m) => m.getStatus(id!)),
    enabled: !isNew,
  });

  useEffect(() => {
    if (agent) {
      setForm({
        name: agent.name,
        title: agent.title,
        description: agent.description,
        system_prompt: agent.system_prompt,
        llm_provider: agent.llm_provider,
        llm_model: agent.llm_model,
        llm_api_key: "",   // never pre-fill the key
        llm_api_base: agent.llm_api_base,
        embed_model: agent.embed_model,
      });
    }
  }, [agent]);

  const set = (key: keyof FormState) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const saveMutation = useMutation({
    mutationFn: async (): Promise<Agent> => {
      const payload = { ...form };
      if (!payload.llm_api_key) delete (payload as Partial<FormState>).llm_api_key;
      if (isNew) return createAgent(payload);
      return updateAgent(id!, payload);
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

  const handleChat = async () => {
    const { url } = await getChatUrl(id!);
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const isReady = status?.status === "ready" || agent?.status === "ready";

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center gap-4">
          <button
            onClick={() => navigate("/")}
            className="text-gray-400 hover:text-gray-700 transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="flex-1">
            <h1 className="text-xl font-bold text-gray-900">
              {isNew ? "New Agent" : (agent?.name ?? "Edit Agent")}
            </h1>
            {!isNew && agent?.title && (
              <p className="text-sm text-gray-500">{agent.title}</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            {!isNew && isReady && (
              <button
                onClick={handleChat}
                className="flex items-center gap-2 text-sm text-brand-600 hover:text-brand-700 border border-brand-200 hover:border-brand-400 px-3 py-1.5 rounded-lg transition-colors"
              >
                <ExternalLink size={14} /> Chat to Test
              </button>
            )}
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending || !form.name.trim()}
              className="flex items-center gap-2 bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              <Save size={14} />
              {saveMutation.isPending ? "Saving…" : saved ? "Saved ✓" : "Save Agent"}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* ── Left: Configuration ──────────────────────────────────────── */}
        <section className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <h2 className="font-semibold text-gray-800">Identity</h2>

            <Field label="Name *">
              <input
                value={form.name}
                onChange={set("name")}
                placeholder="e.g. Customer Support Bot"
                className="input"
              />
            </Field>

            <Field label="Title / Subtitle">
              <input
                value={form.title}
                onChange={set("title")}
                placeholder="e.g. Friendly helper for billing questions"
                className="input"
              />
            </Field>

            <Field label="Description">
              <input
                value={form.description}
                onChange={set("description")}
                placeholder="One-liner shown on the gallery card"
                className="input"
              />
            </Field>

            <Field label="System Prompt">
              <textarea
                value={form.system_prompt}
                onChange={set("system_prompt")}
                rows={8}
                placeholder={`You are a helpful assistant for Acme Corp.\n\nYou specialise in billing and subscription questions.\nAlways be concise and professional.`}
                className="input resize-none font-mono text-xs leading-relaxed"
              />
              <p className="text-xs text-gray-400 mt-1">
                Defines the agent's persona and rules. Leave blank to use the built-in TARA default.
              </p>
            </Field>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <h2 className="font-semibold text-gray-800">LLM Configuration</h2>

            <Field label="Provider">
              <select value={form.llm_provider} onChange={set("llm_provider")} className="input">
                {["ollama", "openai", "anthropic", "groq", "ollama-cloud", "custom"].map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </Field>

            <Field label="Model">
              <input
                value={form.llm_model}
                onChange={set("llm_model")}
                placeholder={PROVIDER_HINTS[form.llm_provider] ?? "model name"}
                className="input"
              />
            </Field>

            <Field label="API Key">
              <input
                type="password"
                value={form.llm_api_key}
                onChange={set("llm_api_key")}
                placeholder="Leave blank for local Ollama"
                className="input"
              />
            </Field>

            <Field label="API Base URL">
              <input
                value={form.llm_api_base}
                onChange={set("llm_api_base")}
                placeholder="For Groq / custom providers"
                className="input"
              />
            </Field>

            <Field label="Embed Model">
              <input
                value={form.embed_model}
                onChange={set("embed_model")}
                placeholder="nomic-embed-text (default)"
                className="input"
              />
            </Field>
          </div>

          {saveMutation.isError && (
            <p className="text-sm text-red-500">{String(saveMutation.error)}</p>
          )}
        </section>

        {/* ── Right: Knowledge Base ────────────────────────────────────── */}
        <section className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-gray-800">Knowledge Base</h2>
              {isNew && (
                <p className="text-xs text-gray-400">Save the agent first to upload files.</p>
              )}
            </div>

            {!isNew && (
              <>
                <FileUpload agentId={id!} files={files} />

                <IngestStatus agentId={id!} />

                <div className="flex gap-3 pt-2">
                  <button
                    onClick={() => ingestMutation.mutate()}
                    disabled={ingestMutation.isPending || files.length === 0 || status?.status === "ingesting"}
                    className="flex items-center gap-2 bg-gray-800 hover:bg-gray-900 disabled:opacity-40 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                  >
                    <Zap size={14} />
                    {status?.status === "ingesting" ? "Ingesting…" : "Build Knowledge Base"}
                  </button>

                  {isReady && (
                    <button
                      onClick={handleChat}
                      className="flex items-center gap-2 text-sm text-brand-600 hover:text-brand-700 border border-brand-200 px-4 py-2 rounded-lg transition-colors"
                    >
                      <ExternalLink size={14} /> Chat to Test ↗
                    </button>
                  )}
                </div>

                {ingestMutation.isError && (
                  <p className="text-sm text-red-500">{String(ingestMutation.error)}</p>
                )}
              </>
            )}
          </div>

          {!isNew && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-2">
              <h2 className="font-semibold text-gray-800 text-sm">Agent Info</h2>
              <dl className="text-xs text-gray-500 space-y-1">
                <div className="flex gap-2">
                  <dt className="font-medium w-32 shrink-0">ID</dt>
                  <dd className="font-mono truncate">{agent?.id}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="font-medium w-32 shrink-0">Collection</dt>
                  <dd className="font-mono truncate">{agent?.collection_name}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="font-medium w-32 shrink-0">Status</dt>
                  <dd>{agent?.status}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="font-medium w-32 shrink-0">Created</dt>
                  <dd>{agent?.created_at ? new Date(agent.created_at).toLocaleString() : "—"}</dd>
                </div>
              </dl>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-700">{label}</label>
      {children}
    </div>
  );
}
