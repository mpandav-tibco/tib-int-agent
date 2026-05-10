import { useCallback, useEffect, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, FileText, Trash2, Zap, Loader2 } from 'lucide-react'
import { agentsApi, type FileInfo } from '../api/agents'

interface Props { agentId: string; status: string; onStatusChange: (s: string) => void }

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function KnowledgeUploader({ agentId, status, onStatusChange }: Props) {
  const qc = useQueryClient()
  const [polling, setPolling] = useState(false)

  const { data: files = [], refetch: refetchFiles } = useQuery({
    queryKey: ['files', agentId],
    queryFn: () => agentsApi.listFiles(agentId),
  })

  const { data: ingestStatus } = useQuery({
    queryKey: ['ingest-status', agentId],
    queryFn: () => agentsApi.status(agentId),
    refetchInterval: polling ? 2000 : false,
  })

  useEffect(() => {
    if (!ingestStatus) return
    setPolling(ingestStatus.status === 'ingesting')
    if (ingestStatus.status !== 'ingesting') {
      onStatusChange(ingestStatus.status)
      qc.invalidateQueries({ queryKey: ['agents'] })
    }
  }, [ingestStatus, onStatusChange, qc])

  const upload = useMutation({
    mutationFn: (files: File[]) => agentsApi.uploadFiles(agentId, files),
    onSuccess: () => refetchFiles(),
  })

  const deleteFile = useMutation({
    mutationFn: (name: string) => agentsApi.deleteFile(agentId, name),
    onSuccess: () => refetchFiles(),
  })

  const ingest = useMutation({
    mutationFn: () => agentsApi.ingest(agentId),
    onSuccess: () => { setPolling(true); qc.invalidateQueries({ queryKey: ['ingest-status', agentId] }) },
  })

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted.length > 0) upload.mutate(accepted)
  }, [upload])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt'],
      'text/markdown': ['.md'],
      'application/json': ['.json'],
      'text/html': ['.html'],
    },
  })

  const isIngesting = status === 'ingesting' || polling

  return (
    <div className="space-y-4">
      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          isDragActive ? 'border-indigo-400 bg-indigo-50' : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'
        }`}
      >
        <input {...getInputProps()} />
        <Upload className="mx-auto mb-2 text-gray-400" size={28} />
        <p className="text-sm text-gray-600">
          {isDragActive ? 'Drop files here…' : 'Drag & drop files, or click to browse'}
        </p>
        <p className="text-xs text-gray-400 mt-1">PDF, TXT, MD, JSON, HTML</p>
      </div>

      {upload.isPending && (
        <p className="text-sm text-indigo-600 flex items-center gap-1.5">
          <Loader2 size={14} className="animate-spin" /> Uploading…
        </p>
      )}

      {/* File list */}
      {files.length > 0 && (
        <ul className="divide-y divide-gray-100 border border-gray-200 rounded-xl overflow-hidden">
          {files.map((f: FileInfo) => (
            <li key={f.name} className="flex items-center gap-3 px-4 py-2.5 bg-white hover:bg-gray-50">
              <FileText size={16} className="text-gray-400 shrink-0" />
              <span className="text-sm text-gray-800 flex-1 truncate">{f.name}</span>
              <span className="text-xs text-gray-400">{fmtSize(f.size)}</span>
              <button
                onClick={() => deleteFile.mutate(f.name)}
                className="text-gray-300 hover:text-red-500 transition-colors"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Ingest button + status */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => ingest.mutate()}
          disabled={files.length === 0 || isIngesting}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-40"
        >
          {isIngesting
            ? <><Loader2 size={14} className="animate-spin" /> Building…</>
            : <><Zap size={14} /> Build Knowledge Base</>}
        </button>
        {ingestStatus && (
          <span className="text-sm text-gray-500">
            {ingestStatus.status === 'ready' && `✓ ${ingestStatus.chunks} chunks indexed`}
            {ingestStatus.status === 'error' && `⚠ ${ingestStatus.error}`}
            {ingestStatus.status === 'ingesting' && 'Indexing…'}
          </span>
        )}
      </div>
    </div>
  )
}
