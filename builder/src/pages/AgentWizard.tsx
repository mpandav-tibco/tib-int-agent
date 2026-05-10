import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { ChevronRight, ChevronLeft, BotMessageSquare } from 'lucide-react'
import { agentsApi, type CreateAgentPayload } from '../api/agents'
import { KnowledgeUploader } from '../components/KnowledgeUploader'

const STARTER_PROMPTS: Record<string, string> = {
  'Support Bot': 'You are a helpful customer support specialist. Answer questions clearly, empathetically, and concisely. If unsure, say so and offer to escalate.',
  'Documentation Assistant': 'You are a documentation expert. Help users find information, understand concepts, and navigate the product. Always cite the relevant section when possible.',
  'Code Reviewer': 'You are a senior software engineer. Review code for correctness, security, performance, and readability. Be specific about issues and provide concrete suggestions.',
  'Sales Assistant': 'You are a knowledgeable sales assistant. Help prospects understand the product, answer questions about features and pricing, and guide them toward a decision.',
  'Domain Expert': 'You are a domain expert with deep knowledge of the subject area. Provide accurate, nuanced answers grounded in the uploaded knowledge base.',
}

const PROVIDERS = ['ollama', 'openai', 'anthropic', 'groq', 'custom']

type Step = 1 | 2 | 3

interface Form extends CreateAgentPayload {}

export function AgentWizard() {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>(1)
  const [form, setForm] = useState<Form>({
    name: '', title: '', description: '', system_prompt: '',
    llm_provider: 'ollama', llm_model: '', llm_api_key: '', llm_api_base: '', embed_model: '',
  })
  const [agentId, setAgentId] = useState<string | null>(null)
  const [agentStatus, setAgentStatus] = useState('draft')

  const create = useMutation({
    mutationFn: (p: Form) => agentsApi.create(p),
    onSuccess: a => { setAgentId(a.id); setStep(3) },
  })

  const set = (k: keyof Form, v: string) => setForm(f => ({ ...f, [k]: v }))

  const goNext = () => {
    if (step === 1) { if (!form.name.trim()) { alert('Name is required'); return }; setStep(2) }
    else if (step === 2) { create.mutate(form) }
  }

  const stepLabel = (n: number) => ['Identity', 'Behaviour & LLM', 'Knowledge Base'][n - 1]

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-2.5">
        <BotMessageSquare size={22} className="text-indigo-600" />
        <span className="font-semibold text-gray-900">AgentForge</span>
        <span className="text-gray-400 mx-1">/</span>
        <span className="text-gray-500 text-sm">New Agent</span>
      </div>

      <main className="max-w-2xl mx-auto px-6 py-10">
        {/* Stepper */}
        <div className="flex items-center gap-2 mb-8">
          {([1, 2, 3] as Step[]).map((n, i) => (
            <div key={n} className="flex items-center gap-2">
              <div className={`size-7 rounded-full flex items-center justify-center text-xs font-semibold ${
                step === n ? 'bg-indigo-600 text-white' : step > n ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
              }`}>{step > n ? '✓' : n}</div>
              <span className={`text-sm ${step === n ? 'text-gray-900 font-medium' : 'text-gray-400'}`}>{stepLabel(n)}</span>
              {i < 2 && <div className="flex-1 h-px bg-gray-200 w-8 mx-1" />}
            </div>
          ))}
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">

          {/* Step 1 — Identity */}
          {step === 1 && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900">Agent Identity</h2>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name *</label>
                <input
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="e.g. HR Assistant"
                  value={form.name}
                  onChange={e => set('name', e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Title / Role</label>
                <input
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="e.g. People & Culture Specialist"
                  value={form.title}
                  onChange={e => set('title', e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Short description</label>
                <textarea
                  rows={2}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                  placeholder="One sentence shown on the agent card"
                  value={form.description}
                  onChange={e => set('description', e.target.value)}
                />
              </div>
            </div>
          )}

          {/* Step 2 — Behaviour & LLM */}
          {step === 2 && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900">Behaviour & LLM</h2>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-sm font-medium text-gray-700">System Prompt</label>
                  <select
                    className="text-xs border border-gray-200 rounded px-2 py-0.5 text-gray-600 focus:outline-none"
                    onChange={e => { if (e.target.value) set('system_prompt', STARTER_PROMPTS[e.target.value]) }}
                    defaultValue=""
                  >
                    <option value="">Starter templates…</option>
                    {Object.keys(STARTER_PROMPTS).map(k => <option key={k}>{k}</option>)}
                  </select>
                </div>
                <textarea
                  rows={8}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                  placeholder="You are a helpful assistant that…"
                  value={form.system_prompt}
                  onChange={e => set('system_prompt', e.target.value)}
                />
                <p className="text-xs text-gray-400 mt-1">{(form.system_prompt || '').length} characters</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">LLM Provider</label>
                  <select
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    value={form.llm_provider}
                    onChange={e => set('llm_provider', e.target.value)}
                  >
                    {PROVIDERS.map(p => <option key={p}>{p}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                  <input
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="e.g. gpt-4o"
                    value={form.llm_model}
                    onChange={e => set('llm_model', e.target.value)}
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
                <input
                  type="password"
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Leave blank for local Ollama"
                  value={form.llm_api_key}
                  onChange={e => set('llm_api_key', e.target.value)}
                />
              </div>
            </div>
          )}

          {/* Step 3 — Knowledge Base */}
          {step === 3 && agentId && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900">Knowledge Base</h2>
              <p className="text-sm text-gray-500">Upload documents that your agent will use to answer questions.</p>
              <KnowledgeUploader
                agentId={agentId}
                status={agentStatus}
                onStatusChange={setAgentStatus}
              />
            </div>
          )}

        </div>

        {/* Navigation */}
        <div className="flex justify-between mt-6">
          <button
            onClick={() => step > 1 ? setStep((s) => (s - 1) as Step) : navigate('/')}
            className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 px-3 py-2 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <ChevronLeft size={16} /> {step === 1 ? 'Cancel' : 'Back'}
          </button>

          {step < 3 && (
            <button
              onClick={goNext}
              disabled={create.isPending}
              className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-40"
            >
              {step === 2 ? 'Create Agent' : 'Next'} <ChevronRight size={16} />
            </button>
          )}

          {step === 3 && (
            <button
              onClick={() => navigate(`/agents/${agentId}`)}
              className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              Go to Agent <ChevronRight size={16} />
            </button>
          )}
        </div>
      </main>
    </div>
  )
}
