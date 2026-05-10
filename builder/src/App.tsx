import { Routes, Route, Navigate } from 'react-router-dom'
import { AgentGallery } from './pages/AgentGallery'
import { AgentWizard } from './pages/AgentWizard'
import { AgentEditor } from './pages/AgentEditor'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AgentGallery />} />
      <Route path="/agents/new" element={<AgentWizard />} />
      <Route path="/agents/:id" element={<AgentEditor />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
