import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  Download,
  FileText,
  GitBranch,
  Layers,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, SectionHeader } from '../components/ui/Card'
import { Modal } from '../components/ui/Modal'
import { PageHeader } from '../components/ui/PageHeader'
import { ProgressBar } from '../components/ui/ProgressBar'
import { Toast } from '../components/ui/Toast'
import {
  cancelWorkflow,
  createWorkflow,
  exportWorkflowReport,
  getWorkflow,
  getWorkflowReport,
  listDatasetOptions,
  listExperimentOptions,
  listPaperOptions,
  listWorkflowEvents,
  listWorkflows,
  retryWorkflowNode,
  seedDemoExperiments,
  startWorkflow,
  submitWorkflowApproval,
} from '../lib/workflows'
import type {
  CreateWorkflowPayload,
  NodeStatus,
  Workflow,
  WorkflowEvent,
  WorkflowNode,
  WorkflowReport,
  WorkflowStatus,
  WorkflowSummary,
} from '../types/workflow'

const ACTIVE_STATUSES: WorkflowStatus[] = ['pending', 'running', 'waiting_approval']

const workflowTone: Record<WorkflowStatus, BadgeTone> = {
  pending: 'neutral',
  running: 'cyan',
  waiting_approval: 'amber',
  completed: 'green',
  failed: 'red',
  cancelled: 'neutral',
}
const workflowLabel: Record<WorkflowStatus, string> = {
  pending: '待启动',
  running: '执行中',
  waiting_approval: '等待人工确认',
  completed: '已完成',
  failed: '已失败',
  cancelled: '已取消',
}
const nodeTone: Record<NodeStatus, BadgeTone> = {
  pending: 'neutral',
  running: 'cyan',
  waiting_approval: 'amber',
  completed: 'green',
  failed: 'red',
  skipped: 'neutral',
}
const nodeLabel: Record<NodeStatus, string> = {
  pending: '待执行',
  running: '执行中',
  waiting_approval: '待确认',
  completed: '已完成',
  failed: '失败',
  skipped: '已跳过',
}
const nodeDot: Record<NodeStatus, string> = {
  pending: 'bg-[#4B5A75]',
  running: 'bg-accent animate-pulse-soft',
  waiting_approval: 'bg-warning',
  completed: 'bg-success',
  failed: 'bg-danger',
  skipped: 'bg-[#4B5A75]',
}
const agentTone: Record<string, BadgeTone> = {
  'Paper Agent': 'violet',
  'Protocol Agent': 'cyan',
  'Data Guardian': 'amber',
  'Insight Agent': 'green',
  'Human Review': 'blue',
}

const workflowTypeLabel: Record<string, string> = {
  full_reproduction: '完整复现',
  analysis_only: '仅分析（声明数据验证缺口）',
}

function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function formatDuration(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(2)}s`
}

function primitiveRefs(ref: Record<string, unknown>, limit = 8): Array<[string, string]> {
  const entries: Array<[string, string]> = []
  for (const [key, value] of Object.entries(ref ?? {})) {
    if (value === null || value === undefined) continue
    if (Array.isArray(value)) {
      if (value.length === 0) continue
      if (value.every((item) => typeof item === 'string' || typeof item === 'number')) {
        const text = value.length > 3 ? `${value.length} 项` : value.join(', ')
        entries.push([key, text])
      } else {
        entries.push([key, `${value.length} 项`])
      }
    } else if (typeof value === 'object') {
      continue
    } else if (typeof value === 'string' && value.length > 44) {
      entries.push([key, `${value.slice(0, 44)}…`])
    } else {
      entries.push([key, String(value)])
    }
    if (entries.length >= limit) break
  }
  return entries
}

function eventTone(eventType: string): BadgeTone {
  if (eventType.includes('failed') || eventType.includes('rejected')) return 'red'
  if (eventType.includes('approval')) return 'amber'
  if (eventType.includes('completed') || eventType.includes('created')) return 'green'
  if (eventType.includes('started') || eventType.includes('retried')) return 'cyan'
  return 'neutral'
}

function WorkflowStatusBadge({ status }: { status: WorkflowStatus }) {
  return <Badge tone={workflowTone[status]} dot>{workflowLabel[status]}</Badge>
}

function NodeStatusBadge({ status }: { status: NodeStatus }) {
  return <Badge tone={nodeTone[status]}>{nodeLabel[status]}</Badge>
}

function RefChips({ label, entries }: { label: string; entries: Array<[string, string]> }) {
  if (entries.length === 0) return null
  return (
    <div>
      <p className="mb-1.5 font-mono text-[9px] uppercase tracking-[.14em] text-[#64718A]">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {entries.map(([key, value]) => (
          <span key={key} className="inline-flex max-w-full items-center gap-1 rounded-md border border-white/[.06] bg-white/[.03] px-2 py-1 font-mono text-[9px] text-[#A9B6CC]">
            <span className="text-[#6E7C96]">{key}</span>
            <span className="truncate">{value}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

export function ResearchWorkflow() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Workflow | null>(null)
  const [events, setEvents] = useState<WorkflowEvent[]>([])
  const [report, setReport] = useState<WorkflowReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [createKey, setCreateKey] = useState('')
  const [selectedExperiments, setSelectedExperiments] = useState<string[]>([])
  const [papers, setPapers] = useState<Array<{ id: string; title: string }>>([])
  const [datasets, setDatasets] = useState<Array<{ id: string; filename: string }>>([])
  const [experiments, setExperiments] = useState<Array<{ id: string; experiment_id: string; method: string; seed: string | null; is_simulated: boolean }>>([])
  const [approvalNode, setApprovalNode] = useState<WorkflowNode | null>(null)
  const [approvalDecision, setApprovalDecision] = useState<'approve' | 'reject'>('approve')
  const [approvalComment, setApprovalComment] = useState('')
  const [approvalReviewer, setApprovalReviewer] = useState('researcher')
  const [form, setForm] = useState({
    name: '科研复现工作流',
    workflow_type: 'full_reproduction' as 'full_reproduction' | 'analysis_only',
    paper_id: '',
    dataset_id: '',
    protocol_name: '',
    baseline_method: '',
    primary_metric: 'macro_f1',
    use_llm: false,
    auto_start: true,
  })
  const [toast, setToast] = useState<string | null>(null)
  const eventsRef = useRef<HTMLDivElement>(null)
  const selectedIdRef = useRef<string | null>(null)
  const detailRequestRef = useRef(0)

  const notify = useCallback((message: string) => setToast(message), [])
  const closeToast = useCallback(() => setToast(null), [])
  const activateWorkflow = useCallback((id: string) => {
    detailRequestRef.current += 1
    selectedIdRef.current = id
    setSelectedId(id)
  }, [])

  useEffect(() => () => {
    selectedIdRef.current = null
    detailRequestRef.current += 1
  }, [])

  const refreshList = useCallback(async () => {
    try {
      const data = await listWorkflows()
      setWorkflows(data.items)
      return data.items
    } catch {
      return []
    }
  }, [])

  const loadDetail = useCallback(async (id: string, silent = false) => {
    if (selectedIdRef.current !== id) return
    const requestId = ++detailRequestRef.current
    const isCurrent = () => selectedIdRef.current === id && detailRequestRef.current === requestId
    if (!silent) setDetailLoading(true)
    try {
      const [workflow, eventList] = await Promise.all([getWorkflow(id), listWorkflowEvents(id)])
      if (!isCurrent()) return
      setDetail(workflow)
      setEvents(eventList)
      if (workflow.status === 'completed') {
        try {
          const workflowReport = await getWorkflowReport(id)
          if (isCurrent()) setReport(workflowReport)
        } catch {
          if (isCurrent()) setReport(null)
        }
      } else {
        setReport(null)
      }
    } catch (error) {
      if (isCurrent()) notify(error instanceof Error ? error.message : '加载工作流失败')
    } finally {
      if (!silent && isCurrent()) setDetailLoading(false)
    }
  }, [notify])

  const loadOptions = useCallback(async () => {
    const [paperOptions, datasetOptions, experimentOptions] = await Promise.all([
      listPaperOptions(),
      listDatasetOptions(),
      listExperimentOptions(),
    ])
    setPapers(paperOptions)
    setDatasets(datasetOptions)
    setExperiments(experimentOptions)
  }, [])

  useEffect(() => {
    void (async () => {
      setLoading(true)
      try {
        const items = await refreshList()
        if (items.length > 0) {
          activateWorkflow(items[0].id)
          await loadDetail(items[0].id)
        }
      } finally {
        setLoading(false)
      }
      await loadOptions()
    })()
  }, [activateWorkflow, loadDetail, loadOptions, refreshList])

  const pollingId = detail && ACTIVE_STATUSES.includes(detail.status) ? detail.id : null
  useEffect(() => {
    if (!pollingId) return
    const timer = window.setInterval(() => {
      void loadDetail(pollingId, true)
      void refreshList()
    }, 2000)
    return () => window.clearInterval(timer)
  }, [pollingId, loadDetail, refreshList])

  const selectWorkflow = async (id: string) => {
    activateWorkflow(id)
    setReport(null)
    await loadDetail(id)
  }

  const runAction = async (key: string, action: () => Promise<Workflow>, successMessage: string): Promise<boolean> => {
    detailRequestRef.current += 1
    setBusy(key)
    try {
      const workflow = await action()
      if (selectedIdRef.current === workflow.id) {
        setDetail(workflow)
        const eventList = await listWorkflowEvents(workflow.id)
        if (selectedIdRef.current === workflow.id) setEvents(eventList)
      }
      await refreshList()
      if (selectedIdRef.current === workflow.id && workflow.status === 'completed') {
        try {
          const workflowReport = await getWorkflowReport(workflow.id)
          if (selectedIdRef.current === workflow.id) setReport(workflowReport)
        } catch {
          /* report may not be ready yet */
        }
      }
      notify(successMessage)
      return true
    } catch (error) {
      notify(error instanceof Error ? error.message : '操作失败')
      return false
    } finally {
      setBusy(null)
    }
  }

  const openCreate = () => {
    setCreateKey(typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `wf-${Date.now()}`)
    setCreateOpen(true)
  }

  const submitCreate = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    const payload: CreateWorkflowPayload = {
      name: form.name.trim() || '科研复现工作流',
      workflow_type: form.workflow_type,
      paper_id: form.paper_id || null,
      dataset_id: form.dataset_id || null,
      experiment_ids: selectedExperiments,
      protocol_name: form.protocol_name.trim() || null,
      baseline_method: form.baseline_method.trim() || null,
      primary_metric: form.primary_metric.trim() || 'macro_f1',
      use_llm: form.use_llm,
      auto_start: form.auto_start,
      idempotency_key: createKey || null,
    }
    setBusy('create')
    try {
      const workflow = await createWorkflow(payload)
      setCreateOpen(false)
      await refreshList()
      activateWorkflow(workflow.id)
      setDetail(workflow)
      const eventList = await listWorkflowEvents(workflow.id)
      if (selectedIdRef.current === workflow.id) setEvents(eventList)
      if (selectedIdRef.current === workflow.id && workflow.status === 'completed') {
        try {
          const workflowReport = await getWorkflowReport(workflow.id)
          if (selectedIdRef.current === workflow.id) setReport(workflowReport)
        } catch {
          /* report may not be ready yet */
        }
      }
      notify(workflow.status === 'waiting_approval' ? '工作流已创建并执行至人工确认节点' : '工作流已创建')
    } catch (error) {
      notify(error instanceof Error ? error.message : '创建工作流失败')
    } finally {
      setBusy(null)
    }
  }

  const submitApproval = async () => {
    if (!detail || !approvalNode) return
    const ok = await runAction(
      'approval',
      () => submitWorkflowApproval(detail.id, {
        node_id: approvalNode.id,
        decision: approvalDecision,
        comment: approvalComment.trim() || undefined,
        reviewer: approvalReviewer.trim() || undefined,
      }),
      approvalDecision === 'approve' ? '审批已通过，工作流继续执行' : '拒绝已记录为审核事件，工作流已停止',
    )
    if (ok) {
      setApprovalNode(null)
      setApprovalComment('')
    }
  }

  const handleRetry = async (node: WorkflowNode) => {
    if (!detail) return
    await runAction(`retry-${node.id}`, () => retryWorkflowNode(detail.id, node.id), `已重试节点「${node.title}」`)
  }

  const handleStart = async () => {
    if (!detail) return
    await runAction('start', () => startWorkflow(detail.id), '工作流已启动')
  }

  const handleCancel = async () => {
    if (!detail) return
    if (!window.confirm('确认取消该工作流？未完成节点将标记为已跳过，已生成的业务数据保留。')) return
    await runAction('cancel', () => cancelWorkflow(detail.id), '工作流已取消')
  }

  const handleExport = async (format: 'markdown' | 'json') => {
    if (!detail) return
    try {
      await exportWorkflowReport(detail.id, format)
      notify(`报告已导出为 ${format === 'json' ? 'JSON' : 'Markdown'}`)
    } catch (error) {
      notify(error instanceof Error ? error.message : '导出失败')
    }
  }

  const refreshReport = async () => {
    if (!detail) return
    const workflowId = detail.id
    try {
      const workflowReport = await getWorkflowReport(workflowId)
      if (selectedIdRef.current !== workflowId) return
      setReport(workflowReport)
      notify('科研报告已刷新')
    } catch (error) {
      notify(error instanceof Error ? error.message : '报告尚未就绪')
    }
  }

  const loadDemoExperiments = async () => {
    try {
      await seedDemoExperiments()
      await loadOptions()
      notify('已载入 ECG 六分类模拟实验数据（标记为模拟）')
    } catch (error) {
      notify(error instanceof Error ? error.message : '载入演示数据失败')
    }
  }

  const agentNodes = detail ? detail.nodes.filter((node) => !node.requires_approval) : []
  const progressPercent = detail && detail.progress.total > 0
    ? Math.round(((detail.progress.completed + detail.progress.skipped) / detail.progress.total) * 100)
    : 0

  const toggleExperiment = (id: string) => {
    setSelectedExperiments((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  }

  return (
    <div>
      <PageHeader
        eyebrow="Research workflow / Multi-agent orchestration"
        title="让四个科研 Agent 按依赖顺序协同，并保留每一步证据。"
        description="统一编排 Paper Agent、Protocol Agent、Data Guardian 与 Insight Agent。编排器直接调用已有业务服务并持久化中间结果，关键节点保留人工确认。"
        actions={
          <>
            <Button onClick={() => { void refreshList(); if (selectedId) void loadDetail(selectedId) }} icon={<RefreshCw size={15} />}>刷新</Button>
            <Button variant="primary" onClick={openCreate} icon={<Plus size={15} />} data-testid="workflow-create-open">新建工作流</Button>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12 xl:col-span-3" padded={false}>
          <div className="border-b border-white/[.06] p-4">
            <p className="font-mono text-[9px] uppercase tracking-[.16em] text-primary">Workflow library</p>
            <p className="mt-1.5 text-xs text-muted">{loading ? '加载中…' : `${workflows.length} 个科研工作流`}</p>
          </div>
          <div className="custom-scrollbar max-h-[620px] space-y-2 overflow-y-auto p-3" data-testid="workflow-list">
            {!loading && workflows.length === 0 && (
              <div className="rounded-xl border border-dashed border-white/[.08] p-6 text-center">
                <GitBranch size={20} className="mx-auto text-muted" />
                <p className="mt-3 text-[11px] leading-5 text-muted">尚无工作流。新建后编排器会真实调用已有 Paper / Protocol / Guardian / Insight 服务。</p>
              </div>
            )}
            {workflows.map((workflow) => (
              <button
                key={workflow.id}
                data-testid={`workflow-card-${workflow.id}`}
                onClick={() => void selectWorkflow(workflow.id)}
                className={`w-full rounded-xl border p-3.5 text-left transition ${selectedId === workflow.id ? 'border-primary/25 bg-primary/[.07]' : 'border-transparent hover:border-white/[.06] hover:bg-white/[.025]'}`}
              >
                <div className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-[#D2DBE8]">{workflow.name}</span>
                  <WorkflowStatusBadge status={workflow.status} />
                </div>
                <div className="mt-2 flex items-center justify-between font-mono text-[9px] text-muted">
                  <span>{workflow.progress.completed + workflow.progress.skipped}/{workflow.progress.total} 节点</span>
                  <span>{formatTime(workflow.updated_at)}</span>
                </div>
                <ProgressBar
                  value={workflow.progress.total ? Math.round(((workflow.progress.completed + workflow.progress.skipped) / workflow.progress.total) * 100) : 0}
                  color={workflow.status === 'failed' ? 'amber' : workflow.status === 'completed' ? 'green' : 'violet'}
                  className="mt-2.5 h-1"
                />
              </button>
            ))}
          </div>
          <div className="border-t border-white/[.06] p-4">
            <div className="grid grid-cols-2 gap-2">
              {[
                ['总工作流', workflows.length],
                ['等待确认', workflows.filter((item) => item.status === 'waiting_approval').length],
                ['已完成', workflows.filter((item) => item.status === 'completed').length],
                ['失败', workflows.filter((item) => item.status === 'failed').length],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-lg bg-canvas/40 p-2.5 text-center">
                  <p className="font-display text-sm font-semibold text-ink">{value}</p>
                  <p className="mt-1 text-[9px] text-muted">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <div className="col-span-12 space-y-5 xl:col-span-9">
          {!detail && (
            <Card className="flex min-h-[420px] flex-col items-center justify-center text-center">
              <GitBranch size={26} className="text-primary" />
              <p className="mt-4 font-display text-[15px] font-semibold text-ink">{loading ? '正在加载工作流…' : '选择一个工作流查看执行细节'}</p>
              <p className="mt-2 max-w-md text-xs leading-6 text-muted">工作流会按依赖顺序真实调用已有业务服务，节点状态、执行日志与人工审批记录全部持久化。</p>
              <Button className="mt-5" variant="primary" onClick={openCreate} icon={<Plus size={15} />}>新建工作流</Button>
            </Card>
          )}

          {detail && (
            <>
              <Card>
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="violet">{workflowTypeLabel[detail.workflow_type] ?? detail.workflow_type}</Badge>
                      <WorkflowStatusBadge status={detail.status} />
                      <span className="font-mono text-[9px] text-muted">{detail.id}</span>
                      {detailLoading && <Loader2 size={13} className="animate-spin text-muted" />}
                    </div>
                    <h2 className="mt-3 font-display text-lg font-semibold tracking-[-.02em] text-ink" data-testid="workflow-detail-name">{detail.name}</h2>
                    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-muted">
                      <span className="flex items-center gap-1.5"><Clock size={12} />创建 {formatTime(detail.created_at)}</span>
                      {detail.completed_at && <span>完成 {formatTime(detail.completed_at)}</span>}
                      <span>重试上限 {detail.nodes[0]?.max_retries ?? 2} 次 / 节点</span>
                    </div>
                    {detail.error && (
                      <p className="mt-3 rounded-lg border border-danger/20 bg-danger/[.07] px-3 py-2 text-[11px] leading-5 text-danger" data-testid="workflow-error">
                        {detail.error}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {ACTIVE_STATUSES.includes(detail.status) && (
                      <Button size="sm" variant="primary" onClick={handleStart} disabled={busy === 'start'} icon={busy === 'start' ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} data-testid="workflow-start">推进执行</Button>
                    )}
                    {!['completed', 'failed', 'cancelled'].includes(detail.status) && (
                      <Button size="sm" variant="danger" onClick={handleCancel} disabled={busy === 'cancel'} icon={<X size={13} />} data-testid="workflow-cancel">取消工作流</Button>
                    )}
                    {detail.status === 'completed' && (
                      <Button size="sm" variant="primary" onClick={() => void refreshReport()} icon={<FileText size={13} />} data-testid="workflow-report-open">查看报告</Button>
                    )}
                  </div>
                </div>

                <div className="mt-5">
                  <div className="mb-2 flex items-center justify-between font-mono text-[9px] text-muted">
                    <span>{detail.progress.completed} 完成 · {detail.progress.skipped} 跳过 · {detail.progress.waiting} 待确认 · {detail.progress.failed} 失败</span>
                    <span>{progressPercent}%</span>
                  </div>
                  <ProgressBar value={progressPercent} color={detail.status === 'failed' ? 'amber' : detail.status === 'completed' ? 'green' : 'violet'} />
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
                  {agentNodes.map((node) => (
                    <div key={node.id} className="rounded-xl border border-white/[.06] bg-canvas/35 p-3">
                      <div className="flex items-center justify-between">
                        <Badge tone={agentTone[node.agent_name] ?? 'neutral'}>{node.agent_name}</Badge>
                        <span className={`h-1.5 w-1.5 rounded-full ${nodeDot[node.status]}`} />
                      </div>
                      <p className="mt-2 truncate text-[11px] text-[#C4CEDD]">{node.title}</p>
                      <p className="mt-1 font-mono text-[9px] text-muted">{nodeLabel[node.status]} · {formatDuration(node.duration)}</p>
                    </div>
                  ))}
                </div>
              </Card>

              <Card>
                <SectionHeader eyebrow="Dependency graph" title="节点依赖图" description="箭头表示执行顺序，节点下方的 depends_on 即真实依赖边。" action={<Badge tone="neutral">{detail.nodes.length} 节点</Badge>} />
                <div className="custom-scrollbar -mx-1 flex items-stretch gap-1 overflow-x-auto px-1 pb-2" data-testid="node-graph">
                  {detail.nodes.map((node, index) => (
                    <div key={node.id} className="flex shrink-0 items-center gap-1">
                      {index > 0 && <ArrowRight size={13} className="shrink-0 text-[#3B4A68]" />}
                      <button
                        onClick={() => document.getElementById(`workflow-node-${node.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
                        className={`w-[132px] rounded-xl border p-3 text-left transition ${node.status === 'waiting_approval' ? 'border-warning/30 bg-warning/[.06]' : node.status === 'failed' ? 'border-danger/25 bg-danger/[.05]' : node.status === 'completed' ? 'border-success/20 bg-success/[.05]' : 'border-white/[.06] bg-white/[.02] hover:border-white/[.12]'}`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[9px] text-muted">{String(node.order_no).padStart(2, '0')}</span>
                          <span className={`h-1.5 w-1.5 rounded-full ${nodeDot[node.status]}`} />
                        </div>
                        <p className="mt-2 truncate text-[11px] font-medium text-ink">{node.title}</p>
                        <p className="mt-1 truncate text-[9px] text-muted">{node.agent_name}</p>
                        <p className={`mt-2 font-mono text-[9px] ${node.status === 'failed' ? 'text-danger' : node.status === 'waiting_approval' ? 'text-warning' : node.status === 'completed' ? 'text-success' : 'text-muted'}`}>{nodeLabel[node.status]}</p>
                      </button>
                    </div>
                  ))}
                </div>
              </Card>

              <Card>
                <SectionHeader eyebrow="Node execution" title="节点执行明细" description="每个节点记录输入/输出引用、耗时、错误与重试次数；所有引用均指向已持久化的业务记录。" />
                <div className="space-y-3">
                  {detail.nodes.map((node) => (
                    <div key={node.id} id={`workflow-node-${node.id}`} data-testid={`node-card-${node.node_key}`} className="rounded-xl border border-white/[.06] bg-canvas/30 p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[9px] text-[#64718A]">{String(node.order_no).padStart(2, '0')}</span>
                        <Badge tone={agentTone[node.agent_name] ?? 'neutral'}>{node.agent_name}</Badge>
                        <span className="text-[12px] font-medium text-ink">{node.title}</span>
                        <NodeStatusBadge status={node.status} />
                        {node.requires_approval && <Badge tone="blue">人工确认</Badge>}
                        {node.optional && <Badge tone="neutral">可选</Badge>}
                        <span className="ml-auto flex items-center gap-3 font-mono text-[9px] text-muted">
                          <span>耗时 {formatDuration(node.duration)}</span>
                          <span>重试 {node.retry_count}/{node.max_retries}</span>
                        </span>
                      </div>

                      <p className="mt-2 text-[10px] text-muted">node_id · {node.id} · 依赖 {node.depends_on.length ? node.depends_on.join(' → ') : '无（入口节点）'}</p>

                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <RefChips label="Input ref" entries={primitiveRefs(node.input_ref)} />
                        <RefChips label="Output ref" entries={primitiveRefs(node.output_ref)} />
                      </div>

                      {node.error && (
                        <p className="mt-3 rounded-lg border border-danger/20 bg-danger/[.07] px-3 py-2 text-[11px] leading-5 text-danger">{node.error}</p>
                      )}

                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {node.status === 'waiting_approval' && (
                          <Button size="sm" variant="primary" onClick={() => { setApprovalNode(node); setApprovalDecision('approve'); setApprovalComment('') }} icon={<CheckCircle2 size={13} />} data-testid={`node-approve-${node.node_key}`}>进入审批</Button>
                        )}
                        {node.status === 'failed' && (
                          <Button size="sm" onClick={() => void handleRetry(node)} disabled={busy === `retry-${node.id}`} icon={<RotateCcw size={13} />} data-testid={`node-retry-${node.node_key}`}>重试节点</Button>
                        )}
                        <span className="font-mono text-[9px] text-muted">
                          {node.started_at ? `开始 ${formatTime(node.started_at)}` : '尚未开始'}
                          {node.completed_at ? ` · 结束 ${formatTime(node.completed_at)}` : ''}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </Card>

              <div className="grid grid-cols-12 gap-5">
                <Card className="col-span-12 lg:col-span-7">
                  <SectionHeader eyebrow="Execution log" title="执行日志" description="仅追加事件流，可追溯每次执行、重试与人工决策。" />
                  <div ref={eventsRef} className="custom-scrollbar max-h-[380px] space-y-2 overflow-y-auto pr-1" data-testid="workflow-events">
                    {events.length === 0 && <p className="rounded-lg bg-canvas/40 p-4 text-[11px] text-muted">暂无事件。</p>}
                    {events.map((event) => {
                      const node = detail.nodes.find((item) => item.id === event.node_id)
                      return (
                        <div key={event.id} className="flex gap-3 rounded-lg border border-white/[.05] bg-canvas/30 px-3 py-2.5">
                          <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${eventTone(event.event_type) === 'red' ? 'bg-danger' : eventTone(event.event_type) === 'green' ? 'bg-success' : eventTone(event.event_type) === 'amber' ? 'bg-warning' : eventTone(event.event_type) === 'cyan' ? 'bg-accent' : 'bg-[#4B5A75]'}`} />
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge tone={eventTone(event.event_type)}>{event.event_type}</Badge>
                              {node && <span className="truncate text-[9px] text-muted">{node.title}</span>}
                              <span className="ml-auto shrink-0 font-mono text-[9px] text-[#64718A]">{formatTime(event.created_at)}</span>
                            </div>
                            <p className="mt-1 text-[11px] leading-5 text-[#B9C5D6]">{event.message}</p>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </Card>

                <Card className="col-span-12 lg:col-span-5">
                  <SectionHeader eyebrow="Approvals" title="人工审核记录" description="拒绝与修改均记录为审核事件，不覆盖原始业务数据。" />
                  {detail.approvals.length === 0 && <p className="rounded-lg bg-canvas/40 p-4 text-[11px] leading-5 text-muted">尚无审批记录。实验方案、高风险审计处置和报告发布需要人工确认。</p>}
                  <div className="space-y-2">
                    {detail.approvals.map((approval) => {
                      const node = detail.nodes.find((item) => item.id === approval.node_id)
                      return (
                        <div key={approval.id} className={`rounded-lg border px-3 py-2.5 ${approval.decision === 'approve' ? 'border-success/20 bg-success/[.05]' : 'border-danger/20 bg-danger/[.05]'}`}>
                          <div className="flex items-center gap-2">
                            <Badge tone={approval.decision === 'approve' ? 'green' : 'red'}>{approval.decision === 'approve' ? '通过' : '拒绝'}</Badge>
                            <span className="truncate text-[10px] text-[#C4CEDD]">{node?.title ?? approval.node_id}</span>
                            <span className="ml-auto shrink-0 font-mono text-[9px] text-muted">{formatTime(approval.created_at)}</span>
                          </div>
                          {approval.comment && <p className="mt-1.5 text-[10px] leading-5 text-muted">{approval.comment}</p>}
                          <p className="mt-1 font-mono text-[9px] text-[#64718A]">审核人 {approval.reviewer ?? '—'}</p>
                        </div>
                      )
                    })}
                  </div>
                </Card>
              </div>

              <Card data-testid="workflow-report">
                <SectionHeader
                  eyebrow="Unified report"
                  title="统一科研报告"
                  description="论文证据、协议参数、数据审计、实验指标与洞察均引用已持久化记录；模拟数据与未审计状态会显式标记。"
                  action={
                    <div className="flex flex-wrap items-center gap-2">
                      <Button size="sm" onClick={() => void refreshReport()} icon={<RefreshCw size={13} />}>刷新</Button>
                      <Button size="sm" onClick={() => void handleExport('markdown')} icon={<Download size={13} />} data-testid="workflow-export-md">Markdown</Button>
                      <Button size="sm" onClick={() => void handleExport('json')} icon={<Download size={13} />} data-testid="workflow-export-json">JSON</Button>
                    </div>
                  }
                />
                {!report && (
                  <div className="rounded-xl border border-dashed border-white/[.08] p-6 text-center text-[11px] leading-6 text-muted">
                    报告在 Insight 分析完成并发布后生成。{detail.status === 'completed' ? '可点击“刷新”加载。' : '当前流程尚未到达报告节点。'}
                  </div>
                )}
                {report && (
                  <div className="space-y-5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={report.ai_status === 'not_used' ? 'neutral' : 'cyan'}>
                        {report.ai_status === 'not_used' ? '确定性分析（未启用真实 LLM）' : `LLM 状态：${report.ai_status}`}
                      </Badge>
                      {report.is_simulated && <Badge tone="amber" dot>包含模拟数据</Badge>}
                      {report.data_validation_skipped && <Badge tone="red" dot>数据验证未执行</Badge>}
                    </div>
                    {report.sections.map((section) => (
                      <div key={section.kind} className="rounded-xl border border-white/[.06] bg-canvas/25 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <h3 className="font-display text-[13px] font-semibold text-ink">{section.title}</h3>
                          <span className="shrink-0 font-mono text-[9px] uppercase tracking-[.12em] text-[#64718A]">{section.kind}</span>
                        </div>
                        <div className="mt-2 space-y-1">
                          {section.lines.map((line, index) => (
                            <p key={index} className={`text-[11px] leading-6 ${line.startsWith('⚠️') ? 'text-warning' : 'text-[#B9C5D6]'}`}>
                              {line.startsWith('- ') ? `• ${line.slice(2)}` : line}
                            </p>
                          ))}
                        </div>
                        {section.refs.length > 0 && (
                          <div className="mt-3 flex flex-wrap items-center gap-1.5">
                            <span className="font-mono text-[9px] text-[#64718A]">来源</span>
                            {section.refs.map((ref) => <Badge key={ref} tone="neutral" className="font-mono">{ref}</Badge>)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </>
          )}
        </div>
      </div>

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="新建科研工作流" description="选择任务类型与已有业务资源，编排器会真实调用现有 Agent 服务。" className="max-w-2xl">
        <form onSubmit={submitCreate} className="space-y-5" data-testid="workflow-create-form">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-xs font-medium text-ink">工作流名称
              <input className="field mt-2" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} data-testid="workflow-name" />
            </label>
            <label className="block text-xs font-medium text-ink">任务类型
              <select className="field mt-2" value={form.workflow_type} onChange={(event) => setForm({ ...form, workflow_type: event.target.value as 'full_reproduction' | 'analysis_only' })} data-testid="workflow-type">
                <option value="full_reproduction">完整复现（论文 → 协议 → 审计 → 洞察）</option>
                <option value="analysis_only">仅分析（声明数据验证缺口）</option>
              </select>
            </label>
            <label className="block text-xs font-medium text-ink">关联论文（可选）
              <select className="field mt-2" value={form.paper_id} onChange={(event) => setForm({ ...form, paper_id: event.target.value })} data-testid="workflow-paper">
                <option value="">不关联论文</option>
                {papers.map((paper) => <option key={paper.id} value={paper.id}>{paper.title || paper.id}</option>)}
              </select>
            </label>
            <label className="block text-xs font-medium text-ink">关联数据集（可选）
              <select className="field mt-2" value={form.dataset_id} onChange={(event) => setForm({ ...form, dataset_id: event.target.value })} data-testid="workflow-dataset">
                <option value="">不关联数据集</option>
                {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.filename}</option>)}
              </select>
            </label>
            <label className="block text-xs font-medium text-ink">实验方案名称（可选）
              <input className="field mt-2" value={form.protocol_name} onChange={(event) => setForm({ ...form, protocol_name: event.target.value })} placeholder="默认由 Protocol Agent 生成" />
            </label>
            <label className="block text-xs font-medium text-ink">基线方法（可选）
              <input className="field mt-2" value={form.baseline_method} onChange={(event) => setForm({ ...form, baseline_method: event.target.value })} placeholder="例如 CNN-LSTM" />
            </label>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-medium text-ink">实验记录（Insight Agent 输入）</p>
              <button type="button" onClick={() => void loadDemoExperiments()} className="text-[10px] text-primary hover:underline">载入 ECG 模拟演示数据</button>
            </div>
            <div className="custom-scrollbar max-h-[168px] space-y-1.5 overflow-y-auto rounded-xl border border-white/[.06] bg-canvas/30 p-2">
              {experiments.length === 0 && <p className="p-3 text-[11px] text-muted">暂无实验记录，可在「实验分析」页导入，或载入演示数据。</p>}
              {experiments.map((experiment) => (
                <label key={experiment.id} className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-2.5 py-2 text-[11px] transition ${selectedExperiments.includes(experiment.id) ? 'border-primary/25 bg-primary/[.06]' : 'border-transparent hover:bg-white/[.03]'}`} data-testid={`workflow-experiment-${experiment.id}`}>
                  <input type="checkbox" checked={selectedExperiments.includes(experiment.id)} onChange={() => toggleExperiment(experiment.id)} className="accent-[#8B5CF6]" />
                  <span className="min-w-0 flex-1 truncate text-[#C4CEDD]">{experiment.method}</span>
                  <span className="font-mono text-[9px] text-muted">seed {experiment.seed ?? '—'}</span>
                  {experiment.is_simulated && <Badge tone="amber">模拟</Badge>}
                </label>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-[11px] text-muted">
              <input type="checkbox" checked={form.use_llm} onChange={(event) => setForm({ ...form, use_llm: event.target.checked })} className="accent-[#8B5CF6]" data-testid="workflow-use-llm" />
              尝试用模型解析论文、生成方案和补充洞察
            </label>
            <label className="flex items-center gap-2 text-[11px] text-muted">
              <input type="checkbox" checked={form.auto_start} onChange={(event) => setForm({ ...form, auto_start: event.target.checked })} className="accent-[#8B5CF6]" data-testid="workflow-auto-start" />
              创建后立即执行至人工确认节点
            </label>
          </div>

          <div className="rounded-xl bg-canvas/45 p-3.5 text-[10px] leading-5 text-muted">
            流程：Paper Agent → Protocol Agent → 人工确认方案 → Data Guardian → 人工确认高风险 → Insight Agent → 人工确认发布。缺少必要输入时节点会失败并说明原因，不会伪装完成。
          </div>

          <div className="flex justify-end gap-2">
            <Button onClick={() => setCreateOpen(false)}>取消</Button>
            <Button type="submit" variant="primary" disabled={busy === 'create'} icon={busy === 'create' ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} data-testid="workflow-create-submit">创建并执行</Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={Boolean(approvalNode)}
        onClose={() => setApprovalNode(null)}
        title={approvalNode ? `人工确认 · ${approvalNode.title}` : '人工确认'}
        description="审批决策会写入 workflow_approvals 与 workflow_events；拒绝不会覆盖原始业务数据。"
      >
        <div className="space-y-4" data-testid="workflow-approval-modal">
          {approvalNode && (
            <div className="rounded-xl bg-canvas/45 p-3.5 text-[11px] leading-6 text-muted">
              <p><span className="text-ink">{approvalNode.agent_name}</span> · {approvalNode.node_key}</p>
              {approvalNode.error && <p className="mt-1 text-danger">{approvalNode.error}</p>}
              {primitiveRefs(approvalNode.output_ref, 6).length > 0 && (
                <div className="mt-2"><RefChips label="节点输出" entries={primitiveRefs(approvalNode.output_ref, 6)} /></div>
              )}
            </div>
          )}
          <div className="grid grid-cols-2 gap-2">
            <button type="button" onClick={() => setApprovalDecision('approve')} className={`rounded-xl border px-3 py-3 text-[11px] transition ${approvalDecision === 'approve' ? 'border-success/35 bg-success/[.08] text-success' : 'border-white/[.07] text-muted hover:border-white/[.14]'}`}>通过并继续执行</button>
            <button type="button" onClick={() => setApprovalDecision('reject')} className={`rounded-xl border px-3 py-3 text-[11px] transition ${approvalDecision === 'reject' ? 'border-danger/35 bg-danger/[.08] text-danger' : 'border-white/[.07] text-muted hover:border-white/[.14]'}`}>拒绝并停止流程</button>
          </div>
          <label className="block text-xs font-medium text-ink">审核意见
            <textarea className="field mt-2 min-h-[84px]" value={approvalComment} onChange={(event) => setApprovalComment(event.target.value)} placeholder="记录确认依据或需要修改的内容…" data-testid="approval-comment" />
          </label>
          <label className="block text-xs font-medium text-ink">审核人
            <input className="field mt-2" value={approvalReviewer} onChange={(event) => setApprovalReviewer(event.target.value)} />
          </label>
          {approvalDecision === 'reject' && <p className="rounded-lg border border-warning/20 bg-warning/[.06] px-3 py-2 text-[10px] leading-5 text-warning"><ShieldAlert size={12} className="mr-1 inline" />拒绝后工作流标记为失败；已生成的论文、协议、审计与实验数据不会被删除或覆盖。</p>}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setApprovalNode(null)}>取消</Button>
            <Button variant="primary" onClick={() => void submitApproval()} disabled={busy === 'approval'} icon={busy === 'approval' ? <Loader2 size={14} className="animate-spin" /> : <Layers size={14} />} data-testid="approval-submit">提交决策</Button>
          </div>
        </div>
      </Modal>

      {toast && <Toast message={toast} onClose={closeToast} />}
    </div>
  )
}
