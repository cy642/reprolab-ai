import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'

const ResearchHub = lazy(() => import('./pages/ResearchHub').then((module) => ({ default: module.ResearchHub })))
const ResearchWorkflow = lazy(() => import('./pages/ResearchWorkflow').then((module) => ({ default: module.ResearchWorkflow })))
const PaperIntelligence = lazy(() => import('./pages/PaperIntelligence').then((module) => ({ default: module.PaperIntelligence })))
const ProtocolBuilder = lazy(() => import('./pages/ProtocolBuilder').then((module) => ({ default: module.ProtocolBuilder })))
const DataGuardian = lazy(() => import('./pages/DataGuardian').then((module) => ({ default: module.DataGuardian })))
const ExperimentInsight = lazy(() => import('./pages/ExperimentInsight').then((module) => ({ default: module.ExperimentInsight })))
const ResearchReport = lazy(() => import('./pages/ResearchReport').then((module) => ({ default: module.ResearchReport })))

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<ResearchHub />} />
        <Route path="workflows" element={<ResearchWorkflow />} />
        <Route path="papers" element={<PaperIntelligence />} />
        <Route path="protocols" element={<ProtocolBuilder />} />
        <Route path="guardian" element={<DataGuardian />} />
        <Route path="insights" element={<ExperimentInsight />} />
        <Route path="reports" element={<ResearchReport />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
