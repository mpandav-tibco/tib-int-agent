import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BotMessageSquare, Save, MessageSquare } from 'lucide-react'
import { agentsApi } from '../api/agents'
import { KnowledgeUploader } from '../components/KnowledgeUploader'
import { StatusBadge } from '../components/StatusBadge'

const TABS = ['Identity', 'Behaviour', 'Knowledge', 'Test'] as const
type Tab = typeof TABS[number]

const PROVIDERS = ['ollama', 'openai', 'anthropic', 'groq', 'custom']

export function AgentEditor() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('Identity')
  const [form, setForm] = useState<Record<string, string>>({})
  const [chatUrl, setChatUrl] = useState('')

  const { data: agent, isLoading } = useQuery({
    queryKey: ['agent', id],
    queryFn: () => agentsApi.get(id!),
    enabled: !!id,
  })

  useEffect(() => {
    if (agent) setForm({
      name: agent.name, title: agent.title, description: agent.description,
      system_prompt: agent.system_prompt, llm_provider: agent.llm_provider,
      llm_model: agent.llm_model, llm_api_key: '', llm_api_base: agent.llm_api_base,
      embed_model: agent.embed_model,
    })
  }, [agent])

  useEffect(() => {
    if (id && tab === 'Test') {
      agentsApi.chatUrl(id).then(r => setChatUrl(r.url))
    }
  }, [id, tab])

  const save = useMutation({
    mutationFn: () => {
      const payload = { ...form }
      if (!payload.llm_api_key) delete payload.llm_api_key // keep existing key if empty
      return agentsApi.update(id!, payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent', id] })
      qc.invalidateQueries({ queryKey: ['agents'] })
    },
  })

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  if (isLoading || !agent) return <div className="p-8 text-gray-400">Loading…</div>

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-2.5">
        <BotMessageSquare size={22} className="text-indigo-600" />
        <button onClick={() => navigate('/')} className="font-semibold text-gray-900 hover:text-indigo-600">AgentForge</button>
        <span className="text-gray-400 mx-1">/</span>
        <span className="text-gray-700 text-sm font-medium">{agent.name}</span>
        <StatusBadge status={agent.status} />
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => save.mutate()}
            disabled={save.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 text-sm text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-40"
          >
            <Save size={14} /> {save.isPending ? 'Saving…' : 'Save'}
          </button>
          {chatUrl && (
            <a
              href={chatUrl} target="_blank" rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              <MessageSquare size={14} /> Test in chat
            </a>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <div className="bg-white border-b border-gray-200 px-6">
        <div className="flex gap-1">
          {TABS.map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >{t}</button>
          ))}
        </div>
      </div>

      <main className="max-w-2xl mx-auto px-6 py-8">
        <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm space-y-4">

          {tab === 'Identity' && (
            <>
              <h2 className="text-lg font-semibold text-gray-900">Identity</h2>
              {(['name', 'title', 'description'] as const).map(k => (
                <div key={k}>
                  <label className="block text-sm font-medium text-gray-700 mb-1 capitalize">{k}</label>
                  {k === 'description'
                    ? <textarea rows={3} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" value={form[k] ?? ''} onChange={e => set(k, e.target.value)} />
                    : <input className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" value={form[k] ?? ''} onChange={e => set(k, e.target.value)} />}
                </div>
              ))}
            </>
          )}

          {tab === 'Behaviour' && (
            <>
              <h2 className="text-lg font-semibold text-gray-900">Behaviour</h2>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">System Prompt</label>
                <textarea
                  rows={12}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                  value={form.system_prompt ?? ''}
                  onChange={e => set('system_prompt', e.target.value)}
                />
                <p className="text-xs text-gray-400 mt-1">{(form.system_prompt ?? '').length} characters</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
                  <select className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" value={form.llm_provider ?? ''} onChange={e => set('llm_provider', e.target.value)}>
                    {PROVIDERS.map(p => <option key={p}>{p}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                  <input className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" value={form.llm_model ?? ''} onChange={e => set('llm_model', e.target.value)} />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">API Key <span className="text-gray-400 font-normal">(leave blank to keep existing)</span></label>
                <input type="password" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="••••••••" value={form.llm_api_key ?? ''} onChange={e => set('llm_api_key', e.target.value)} />
              </div>
            </>
          )}

          {tab === 'Knowledge' && (
            <>
              <h2 className="text-lg font-semibold text-gray-900">Knowledge Base</h2>
              <p className="text-sm text-gray-500">Collection: <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{agent.collection_name}</code></p>
              <KnowledgeUploader
                agentId={agent.id}
                status={agent.status}
                onStatusChange={_s => qc.invalidateQueries({ queryKey: ['agent', id] })}
              />
            </>
          )}

          {tab === 'Test' && (
            <>
              <h2 className="text-lg font-semibold text-gray-900">Test Your Agent</h2>
              {chatUrl
                ? <iframe src={chatUrl} className="w-full h-[600px] rounded-xl border border-gray-200" title="Agent chat preview" />
                : <div className="h-40 flex items-center justify-center text-gray-400 text-sm">Loading chat URL…</div>
              }
            </>
          )}

        </div>
      </main>
    </div>
  )
}
