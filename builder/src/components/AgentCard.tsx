import { useNavigate } from 'react-router-dom'
import { MessageSquare, Settings, Trash2 } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type Agent, agentsApi } from '../api/agents'
import { StatusBadge } from './StatusBadge'

interface Props { agent: Agent }

export function AgentCard({ agent }: Props) {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const del = useMutation({
    mutationFn: () => agentsApi.delete(agent.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  })

  const handleChat = async () => {
    const { url } = await agentsApi.chatUrl(agent.id)
    window.open(url, '_blank')
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5 flex flex-col gap-3 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-900 leading-tight">{agent.name}</h2>
          <p className="text-sm text-gray-500 mt-0.5">{agent.title || '—'}</p>
        </div>
        <StatusBadge status={agent.status} />
      </div>

      {agent.description && (
        <p className="text-sm text-gray-600 line-clamp-2">{agent.description}</p>
      )}

      <div className="text-xs text-gray-400 border-t border-gray-100 pt-2">
        {agent.llm_provider} · {agent.llm_model || 'default model'}
      </div>

      <div className="flex gap-2 mt-auto">
        <button
          onClick={() => navigate(`/agents/${agent.id}`)}
          className="flex-1 flex items-center justify-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <Settings size={14} /> Edit
        </button>
        <button
          onClick={handleChat}
          disabled={agent.status !== 'ready' && agent.status !== 'draft'}
          className="flex-1 flex items-center justify-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-40"
        >
          <MessageSquare size={14} /> Test
        </button>
        <button
          onClick={() => { if (confirm(`Delete "${agent.name}"?`)) del.mutate() }}
          className="p-1.5 text-gray-400 hover:text-red-500 transition-colors rounded-lg hover:bg-red-50"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}
