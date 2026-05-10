import { useState } from "react";
import { KeyRound } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

export default function Login() {
  const { setApiKey } = useAuth();
  const [value, setValue] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const key = value.trim();
    if (!key) return;
    // Probe the API to verify the key works
    try {
      const res = await fetch("/api/agents", {
        headers: { Authorization: `Bearer ${key}` },
      });
      if (res.status === 401) {
        setError("Invalid API key — please try again.");
        return;
      }
      setError("");
      setApiKey(key);
    } catch {
      setError("Could not reach the AgentForge API — is the server running?");
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg w-full max-w-sm p-8 space-y-6">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-brand-50 mb-3">
            <KeyRound size={22} className="text-brand-600" />
          </div>
          <h1 className="text-xl font-bold text-gray-900">AgentForge</h1>
          <p className="text-sm text-gray-500 mt-1">Enter your API key to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="API key"
            autoFocus
            className="input"
          />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={!value.trim()}
            className="w-full bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white font-medium py-2.5 rounded-lg transition-colors"
          >
            Sign in
          </button>
        </form>

        <p className="text-xs text-center text-gray-400">
          Set <code className="font-mono bg-gray-100 px-1 rounded">FORGE_API_KEY</code> on the
          server to enable authentication.
        </p>
      </div>
    </div>
  );
}
