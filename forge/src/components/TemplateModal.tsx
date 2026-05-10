import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import { createAgent } from "../api";

interface Template {
  emoji: string;
  name: string;
  title: string;
  description: string;
  system_prompt: string;
  llm_provider: string;
}

const TEMPLATES: Template[] = [
  {
    emoji: "💬",
    name: "Customer Support Bot",
    title: "Friendly support specialist",
    description: "Handles billing, account, and product questions with empathy",
    system_prompt:
      "You are a friendly and professional customer support specialist.\n\n" +
      "Your role:\n" +
      "- Answer questions about products, billing, and account management\n" +
      "- Always be empathetic and patient, especially with frustrated customers\n" +
      "- If you don't know the answer, say so honestly and offer to escalate\n" +
      "- Keep responses concise — 3 sentences max unless detail is needed\n\n" +
      "Tone: warm, professional, solution-focused.",
    llm_provider: "ollama",
  },
  {
    emoji: "👥",
    name: "HR Assistant",
    title: "People & culture guide",
    description: "Answers HR policy, onboarding, and benefits questions",
    system_prompt:
      "You are an HR assistant helping employees navigate company policies, benefits, and processes.\n\n" +
      "Your role:\n" +
      "- Provide accurate, up-to-date information about HR policies from the knowledge base\n" +
      "- Answer questions about onboarding, leave, payroll, and performance reviews\n" +
      "- Be discrete and professional — treat all employee questions with sensitivity\n" +
      "- Always recommend speaking with an HR representative for sensitive or complex matters\n\n" +
      "Tone: helpful, clear, confidential.",
    llm_provider: "ollama",
  },
  {
    emoji: "🔧",
    name: "DevOps Bot",
    title: "Infrastructure & ops assistant",
    description: "Helps with CI/CD, Kubernetes, and incident runbooks",
    system_prompt:
      "You are a DevOps assistant specialising in infrastructure, CI/CD pipelines, and incident response.\n\n" +
      "Your role:\n" +
      "- Help engineers diagnose issues using runbooks and documentation in the knowledge base\n" +
      "- Provide step-by-step guidance for common operations (deployments, rollbacks, scaling)\n" +
      "- Suggest best practices for reliability and observability\n" +
      "- Always recommend following change management processes for production changes\n\n" +
      "Tone: technical, precise, safety-conscious.",
    llm_provider: "ollama",
  },
  {
    emoji: "🔍",
    name: "Code Review Assistant",
    title: "Code quality advisor",
    description: "Reviews code for bugs, style, and best practices",
    system_prompt:
      "You are a senior software engineer specialising in code review.\n\n" +
      "Your role:\n" +
      "- Identify bugs, edge cases, and security vulnerabilities in code snippets\n" +
      "- Suggest improvements for readability, performance, and maintainability\n" +
      "- Reference team coding standards from the knowledge base\n" +
      "- Frame feedback constructively — focus on the code, not the author\n" +
      "- Distinguish between blocking issues (must fix) and suggestions (nice to have)\n\n" +
      "Tone: technical, constructive, educational.",
    llm_provider: "ollama",
  },
  {
    emoji: "🚀",
    name: "Sales Enablement Bot",
    title: "Sales intelligence assistant",
    description: "Surfaces product info, competitive intel, and battlecards",
    system_prompt:
      "You are a sales enablement assistant helping the sales team win deals.\n\n" +
      "Your role:\n" +
      "- Surface product capabilities, pricing, and positioning from the knowledge base\n" +
      "- Provide competitive intelligence and differentiation talking points\n" +
      "- Help craft compelling responses to objections\n" +
      "- Keep answers sharp and business-focused — sales reps need quick answers\n\n" +
      "Tone: confident, punchy, business-savvy.",
    llm_provider: "ollama",
  },
  {
    emoji: "📚",
    name: "Documentation Helper",
    title: "Technical writing assistant",
    description: "Answers questions from product docs and API references",
    system_prompt:
      "You are a documentation assistant for a technical product.\n\n" +
      "Your role:\n" +
      "- Answer questions by referencing the uploaded documentation accurately\n" +
      "- Provide code examples and step-by-step instructions when relevant\n" +
      "- If a feature isn't documented, say so rather than guessing\n" +
      "- Link to relevant sections by name when possible\n\n" +
      "Tone: clear, technical, example-driven.",
    llm_provider: "ollama",
  },
];

interface Props {
  onClose: () => void;
}

export default function TemplateModal({ onClose }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Template | null>(null);

  const createMutation = useMutation({
    mutationFn: (tpl: Template) =>
      createAgent({
        name: tpl.name,
        title: tpl.title,
        description: tpl.description,
        system_prompt: tpl.system_prompt,
        llm_provider: tpl.llm_provider,
      }),
    onSuccess: (agent) => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      navigate(`/agents/${agent.id}`);
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Start from a template</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Pick a starting point — you can customise everything afterwards.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Template grid */}
        <div className="flex-1 overflow-y-auto p-6 grid grid-cols-2 gap-3">
          {TEMPLATES.map((tpl) => (
            <button
              key={tpl.name}
              onClick={() => setSelected(tpl)}
              className={`text-left rounded-xl border-2 p-4 transition-all ${
                selected?.name === tpl.name
                  ? "border-brand-500 bg-brand-50"
                  : "border-gray-100 hover:border-gray-300 bg-gray-50 hover:bg-white"
              }`}
            >
              <div className="text-2xl mb-2">{tpl.emoji}</div>
              <p className="font-semibold text-sm text-gray-900">{tpl.name}</p>
              <p className="text-xs text-gray-500 mt-0.5">{tpl.description}</p>
            </button>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-t border-gray-100">
          <button
            onClick={onClose}
            className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            Cancel
          </button>
          <div className="flex items-center gap-3">
            {createMutation.isError && (
              <p className="text-sm text-red-500">{String(createMutation.error)}</p>
            )}
            <button
              onClick={() => selected && createMutation.mutate(selected)}
              disabled={!selected || createMutation.isPending}
              className="flex items-center gap-2 bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white text-sm font-medium px-5 py-2 rounded-lg transition-colors"
            >
              {createMutation.isPending ? "Creating…" : "Use this template →"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
