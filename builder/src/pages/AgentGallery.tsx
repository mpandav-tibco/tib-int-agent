import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, BotMessageSquare } from 'lucide-react'
import { agentsApi } from '../api/agents'
import { AgentCard } from '../components/AgentCard'

export function AgentGallery() {
  const navigate = useNavigate()
  const { data: agents = [], isLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
    refetchInterval: 5000,
  })

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <BotMessageSquare size={22} className="text-indigo-600" />
          <span className="font-semibold text-gray-900">AgentForge</span>
        </div>
        <button
          onClick={() => navigate('/agents/new')}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          <Plus size={16} /> New Agent
        </button>
      </div>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Your Agents</h1>
          <p className="text-gray-500 text-sm mt-1">Configure, train, and test your AI agents.</p>
        </div>

        {isLoading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="bg-white rounded-2xl border border-gray-200 p-5 h-40 animate-pulse" />
            ))}
          </div>
        )}

        {!isLoading && agents.length === 0 && (
          <div className="text-center py-20">
            <BotMessageSquare size={48} className="mx-auto text-gray-300 mb-4" />
            <h2 className="text-lg font-medium text-gray-700">No agents yet</h2>
            <p className="text-gray-500 text-sm mt-1 mb-6">Create your first agent to get started.</p>
            <button
              onClick={() => navigate('/agents/new')}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              <Plus size={16} /> Create agent
            </button>
          </div>
        )}

        {!isLoading && agents.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {agents.map(a => <AgentCard key={a.id} agent={a} />)}
          </div>
        )}
      </main>
    </div>
  )
}
