import { useState } from "react";
import { LayoutTemplate, Plus } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { listAgents } from "../api";
import AgentCard from "../components/AgentCard";
import TemplateModal from "../components/TemplateModal";

export default function Gallery() {
  const navigate = useNavigate();
  const [showTemplates, setShowTemplates] = useState(false);

  const { data: agents = [], isLoading, error } = useQuery({
    queryKey: ["agents"],
    queryFn: listAgents,
  });

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">AgentForge</h1>
            <p className="text-sm text-gray-500">Build, train, and deploy AI agents</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowTemplates(true)}
              className="flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-900 border border-gray-200 hover:border-gray-400 px-4 py-2 rounded-lg transition-colors"
            >
              <LayoutTemplate size={15} />
              Templates
            </button>
            <button
              onClick={() => navigate("/agents/new")}
              className="flex items-center gap-2 bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              <Plus size={16} />
              New Agent
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {isLoading && (
          <div className="text-center text-gray-400 py-16">Loading agents…</div>
        )}

        {error && (
          <div className="text-center text-red-500 py-16">
            Could not load agents — is the API server running on port 8000?
          </div>
        )}

        {!isLoading && !error && agents.length === 0 && (
          <div className="text-center py-24">
            <div className="text-5xl mb-4">🤖</div>
            <h2 className="text-xl font-semibold text-gray-700 mb-2">No agents yet</h2>
            <p className="text-gray-500 mb-6">Create your first agent or start from a template.</p>
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={() => setShowTemplates(true)}
                className="inline-flex items-center gap-2 border border-gray-300 hover:border-gray-400 text-gray-700 text-sm font-medium px-5 py-2.5 rounded-lg transition-colors"
              >
                <LayoutTemplate size={15} />
                Browse Templates
              </button>
              <button
                onClick={() => navigate("/agents/new")}
                className="inline-flex items-center gap-2 bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors"
              >
                <Plus size={16} />
                Create from Scratch
              </button>
            </div>
          </div>
        )}

        {agents.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {agents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )}
      </main>

      {showTemplates && <TemplateModal onClose={() => setShowTemplates(false)} />}
    </div>
  );
}
