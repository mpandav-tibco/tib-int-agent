import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, AlertCircle, Loader } from "lucide-react";
import { getStatus } from "../api";

interface Props {
  agentId: string;
}

export default function IngestStatus({ agentId }: Props) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["status", agentId],
    queryFn: () => getStatus(agentId),
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "ingesting" ? 3000 : false;
    },
  });

  // When ingestion finishes, refresh the agent list so the card status badge updates.
  useEffect(() => {
    if (data?.status === "ready" || data?.status === "error") {
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["agent", agentId] });
    }
  }, [data?.status, agentId, qc]);

  if (!data || data.status === "draft") return null;

  if (data.status === "ingesting") {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-yellow-50 border border-yellow-200 px-3 py-2 text-sm text-yellow-800">
        <Loader size={16} className="animate-spin shrink-0" />
        <span>Building knowledge base… ({data.chunks} chunks so far)</span>
      </div>
    );
  }

  if (data.status === "ready") {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-800">
        <CheckCircle size={16} className="shrink-0" />
        <span>Knowledge base ready — {data.chunks} chunks indexed.</span>
      </div>
    );
  }

  if (data.status === "error") {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-800">
        <AlertCircle size={16} className="shrink-0" />
        <span>Ingestion failed: {data.error ?? "unknown error"}</span>
      </div>
    );
  }

  return null;
}
