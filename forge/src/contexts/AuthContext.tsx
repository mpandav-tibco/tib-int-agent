import { createContext, useCallback, useContext, useMemo, useState } from "react";

const STORAGE_KEY = "forge_api_key";

interface AuthCtx {
  apiKey: string;
  setApiKey: (key: string) => void;
  clearApiKey: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [apiKey, setApiKeyState] = useState<string>(
    () => localStorage.getItem(STORAGE_KEY) ?? ""
  );

  const setApiKey = useCallback((key: string) => {
    setApiKeyState(key);
    if (key) {
      localStorage.setItem(STORAGE_KEY, key);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  const clearApiKey = useCallback(() => setApiKey(""), [setApiKey]);

  const value = useMemo(
    () => ({ apiKey, setApiKey, clearApiKey, isAuthenticated: apiKey.length > 0 }),
    [apiKey, setApiKey, clearApiKey]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
