import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, HashRouter } from 'react-router-dom'
import { WorkspaceProvider } from './context/WorkspaceContext'
import App from './App'
import './index.css'

const Router = import.meta.env.MODE === 'pages' ? HashRouter : BrowserRouter

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Router>
      <WorkspaceProvider>
        <App />
      </WorkspaceProvider>
    </Router>
  </StrictMode>,
)
