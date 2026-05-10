import { ExternalLink, Pencil, Trash2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { deleteAgent, getChatUrl } from "../api";
import type { Agent } from "../types";

const STATUS_STYLES: Record<string, string> = {
  ready:     "bg-green-100 text-green-800",
  ingesting: "bg-yellow-100 text-yellow-800",
  error:     "bg-red-100 text-red-800",
  draft:     "bg-gray-100 text-gray-600",
};

export default function AgentCard({ agent }: { agent: Agent }) {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const removeMutation = useMutation({
    mutationFn: () => deleteAgent(agent.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });

  const handleChat = async () => {
    const { url } = await getChatUrl(agent.id);
    window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex flex-col gap-3 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 truncate">{agent.name}</h3>
          {agent.title && (
            <p className="text-sm text-gray-500 truncate">{agent.title}</p>
          )}
        </div>
        <span
          className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_STYLES[agent.status] ?? STATUS_STYLES.draft}`}
        >
          {agent.status}
        </span>
      </div>

      {agent.description && (
        <p className="text-sm text-gray-600 line-clamp-2">{agent.description}</p>
      )}

      <div className="text-xs text-gray-400">
        {agent.llm_provider} · {agent.llm_model || "default model"}
      </div>

      <div className="flex gap-2 mt-auto pt-2 border-t border-gray-100">
        <button
          onClick={() => navigate(`/agents/${agent.id}`)}
          className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
        >
          <Pencil size={14} /> Edit
        </button>

        <button
          onClick={handleChat}
          disabled={agent.status !== "ready"}
          className="flex items-center gap-1 text-sm px-2 py-1 rounded transition-colors
            disabled:opacity-40 disabled:cursor-not-allowed
            enabled:text-brand-600 enabled:hover:bg-brand-50 enabled:hover:text-brand-700"
        >
          <ExternalLink size={14} /> Chat to Test
        </button>

        <button
          onClick={() => {
            if (confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) {
              removeMutation.mutate();
            }
          }}
          className="flex items-center gap-1 text-sm text-red-400 hover:text-red-600 px-2 py-1 rounded hover:bg-red-50 transition-colors ml-auto"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}
