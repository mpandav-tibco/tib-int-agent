import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import Gallery from "./pages/Gallery";
import Editor from "./pages/Editor";
import Login from "./pages/Login";

// SERVER_AUTH_REQUIRED is injected at build time via Vite define, or detected at runtime.
// When FORGE_API_KEY is set on the server, the server returns 401 on the first request,
// and api.ts reloads the page — but we also want to show the Login page proactively
// when the user has no stored key and the server requires one.
//
// We rely on a simple heuristic: if the user has a key stored, try to use it;
// if they don't, show login. The api.ts 401 handler will clear a bad key and reload.

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  // If we have no key at all, check if auth is actually required by pinging the API.
  // We do this lazily — show the app optimistically; if the server rejects, api.ts
  // clears the key and reloads, which brings the user back here showing Login.
  // Show Login immediately only when we definitely have no key stored.
  //
  // To ALWAYS require login (even in open dev mode), set FORGE_API_KEY="" on the server
  // and the gallery page will load fine with no auth header (server allows it).
  // So: only block if there's no stored key AND the server actually requires auth.
  // We can't know the latter without a network request, so we let the app load and
  // rely on the 401→reload cycle in api.ts. Exception: if VITE_REQUIRE_AUTH=true is set.
  const requireAuth = import.meta.env.VITE_REQUIRE_AUTH === "true";
  if (requireAuth && !isAuthenticated) {
    return <Login />;
  }

  return (
    <Routes>
      <Route path="/" element={<Gallery />} />
      <Route path="/agents/new" element={<Editor />} />
      <Route path="/agents/:id" element={<Editor />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
