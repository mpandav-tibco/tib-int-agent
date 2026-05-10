import { useCallback, useState } from "react";
import { Upload, X } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteFile, uploadFiles } from "../api";
import type { AgentFile } from "../types";

function fmt(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface Props {
  agentId: string;
  files: AgentFile[];
}

export default function FileUpload({ agentId, files }: Props) {
  const qc = useQueryClient();
  const [dragging, setDragging] = useState(false);

  const uploadMutation = useMutation({
    mutationFn: (fileList: File[]) => uploadFiles(agentId, fileList),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files", agentId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (name: string) => deleteFile(agentId, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files", agentId] }),
  });

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const dropped = Array.from(e.dataTransfer.files);
      if (dropped.length) uploadMutation.mutate(dropped);
    },
    [uploadMutation]
  );

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    if (selected.length) uploadMutation.mutate(selected);
    e.target.value = "";
  };

  return (
    <div className="space-y-3">
      {files.length > 0 && (
        <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
          {files.map((f) => (
            <li key={f.name} className="flex items-center justify-between px-3 py-2 text-sm">
              <span className="truncate text-gray-700">{f.name}</span>
              <span className="ml-3 shrink-0 text-xs text-gray-400">{fmt(f.size)}</span>
              <button
                onClick={() => deleteMutation.mutate(f.name)}
                className="ml-2 text-gray-400 hover:text-red-500 transition-colors"
                title="Remove file"
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 cursor-pointer transition-colors
          ${dragging ? "border-brand-500 bg-brand-50" : "border-gray-300 hover:border-gray-400 hover:bg-gray-50"}`}
      >
        <Upload size={24} className="text-gray-400" />
        <span className="text-sm text-gray-500">
          Drag files here or <span className="text-brand-600 font-medium">click to browse</span>
        </span>
        <span className="text-xs text-gray-400">PDF, DOCX, TXT, MD, HTML supported</span>
        <input type="file" multiple className="hidden" onChange={handleInput} />
      </label>

      {uploadMutation.isPending && (
        <p className="text-xs text-brand-600 animate-pulse">Uploading…</p>
      )}
      {uploadMutation.isError && (
        <p className="text-xs text-red-500">{String(uploadMutation.error)}</p>
      )}
    </div>
  );
}
