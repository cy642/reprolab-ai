import { API_BASE_URL, downloadApiFile, getDemoAccessCode } from '../lib/api'
import { useCallback, useEffect, useState } from 'react'
import {
  AlertCircle,
  ArrowUp,
  BookOpenText,
  Cpu,
  Download,
  FlaskConical,
  Gauge,
  History,
  LoaderCircle,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  WandSparkles,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, SectionHeader } from '../components/ui/Card'
import { Modal } from '../components/ui/Modal'
import { PageHeader } from '../components/ui/PageHeader'
import { ProgressBar } from '../components/ui/ProgressBar'
import { Toast, type ToastTone } from '../components/ui/Toast'
import { EvidenceModal } from '../components/papers/EvidenceModal'
import { ProtocolFlow } from '../components/protocols/ProtocolFlow'
import { ParameterSourceChain } from '../components/protocols/ParameterSourceChain'
import { ApiError, deleteProtocol, protocolExportPath, generateProtocol, getProtocol, listProtocols, listProtocolVersions, saveProtocolVersion, updateProtocol } from '../lib/protocols'
import { getPaper, getPageText, listPapers } from '../lib/papers'
import type { Evidence, PaperDetail, PaperSummary } from '../types/paper'
import type { ProtocolDetail, ProtocolParameter, ProtocolStep, ProtocolSummary, ProtocolVersion } from '../types/protocol'
import { formatDateTime, INFO_META, PROTOCOL_STATUS, STATUS_META } from '../components/protocols/meta'

interface ToastState { message: string; tone: ToastTone }
const PROTOCOL_NAME_LIMIT = 120

export function ProtocolBuilder() {
  const [protocols, setProtocols] = useState<ProtocolSummary[]>([])
  const [papers, setPapers] = useState<PaperSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ProtocolDetail | null>(null)
  const [versions, setVersions] = useState<ProtocolVersion[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [generateLoading, setGenerateLoading] = useState(false)
  const [generatePaperId, setGeneratePaperId] = useState('')
  const [generateName, setGenerateName] = useState('')
  const generateNameTooLong = [...generateName.trim()].length > PROTOCOL_NAME_LIMIT
  const [toast, setToast] = useState<ToastState | null>(null)
  const [dirty, setDirty] = useState(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'workflow' | 'params'>('overview')
  const [workflowView, setWorkflowView] = useState<'dag' | 'list'>('dag')
  const [paperDetail, setPaperDetail] = useState<PaperDetail | null>(null)
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null)
  const [evidencePageText, setEvidencePageText] = useState<string | null>(null)
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [selectedParamId, setSelectedParamId] = useState<string | null>(null)
  const [goalDraft, setGoalDraft] = useState('')
  const [goalSaving, setGoalSaving] = useState(false)
  const [listError, setListError] = useState<string | null>(null)

  const closeToast = useCallback(() => setToast(null), [])

  const refreshList = useCallback(async (silent = false) => {
    if (!silent) setListLoading(true)
    try {
      const [protoResp, paperResp] = await Promise.all([
        listProtocols(),
        listPapers(),
      ])
      setProtocols(protoResp.items)
      setPapers(paperResp.items)
      setListError(null)
    } catch (error) {
      const msg = error instanceof Error ? error.message : '无法加载列表'
      setListError(msg)
      setToast({ message: msg, tone: 'error' })
    } finally {
      if (!silent) setListLoading(false)
    }
  }, [])

  useEffect(() => { void refreshList() }, [refreshList])

  useEffect(() => {
    if (!selectedId) { setDetail(null); setVersions([]); return }
    let cancelled = false
    setDetailLoading(true)
    void getProtocol(selectedId).then((data) => {
      if (cancelled) return
      setDetail(data)
      setDirty(false)
    }).catch((error) => {
      if (cancelled) return
      setToast({ message: error instanceof Error ? error.message : '加载失败', tone: 'error' })
      if (error instanceof ApiError && error.status === 404) void refreshList(true)
    }).finally(() => { if (!cancelled) setDetailLoading(false) })
    return () => { cancelled = true }
  }, [selectedId, refreshList])

  useEffect(() => {
    if (!detail?.id) { setVersions([]); return }
    let cancelled = false
    setVersionsLoading(true)
    void listProtocolVersions(detail.id).then((data) => { if (!cancelled) setVersions(data) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setVersionsLoading(false) })
    return () => { cancelled = true }
  }, [detail?.id, versionsOpen])

  useEffect(() => {
    if (!detail?.paper_id) { setPaperDetail(null); return }
    let cancelled = false
    setGoalDraft(detail.goal ?? '')
    setSelectedParamId(detail.parameters[0]?.id ?? null)
    void getPaper(detail.paper_id).then((paper) => { if (!cancelled) setPaperDetail(paper) })
      .catch((error) => { if (!cancelled) setToast({ message: error instanceof Error ? error.message : '论文证据加载失败', tone: 'error' }) })
    return () => { cancelled = true }
  }, [detail?.id])

  const openEvidence = async (evidenceId: string) => {
    if (!detail || !paperDetail) return
    const evidence = paperDetail.evidence.find((item) => item.id === evidenceId)
    if (!evidence) {
      setToast({ message: '证据不存在或不属于当前论文。', tone: 'error' })
      return
    }
    setSelectedEvidence(evidence)
    setEvidencePageText(null)
    setEvidenceLoading(true)
    try {
      const response = await getPageText(detail.paper_id, evidence.page)
      setEvidencePageText(response.text)
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '原文加载失败', tone: 'error' })
    } finally {
      setEvidenceLoading(false)
    }
  }

  const saveSteps = async (steps: ProtocolStep[]) => {
    if (!detail) return
    try {
      const response = await updateProtocol(detail.id, { steps })
      setDetail(response)
      setDirty(true)
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存失败'
      setToast({ message, tone: 'error' })
      throw error
    }
  }

  const saveGoal = async () => {
    if (!detail || !goalDraft.trim()) return
    setGoalSaving(true)
    try {
      const updated = await updateProtocol(detail.id, { goal: goalDraft.trim() })
      const version = await saveProtocolVersion(detail.id, '更新实验目标')
      const refreshedVersions = await listProtocolVersions(detail.id)
      setDetail({ ...updated, version_no: version.version_no })
      setVersions(refreshedVersions)
      setGoalDraft(updated.goal ?? '')
      setToast({ message: `实验目标已保存至 v${version.version_no}`, tone: 'success' })
      setDirty(false)
      await refreshList(true)
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '目标保存失败', tone: 'error' })
    } finally {
      setGoalSaving(false)
    }
  }

  const updateStepsOrder = async () => {
    if (!detail) return
    const ordered = [...detail.steps].sort((a, b) => a.order_no - b.order_no)
    const payload = ordered.map((step, index) => ({ ...step, order_no: index + 1 }))
    try {
      const response = await updateProtocol(detail.id, { steps: payload })
      setDetail(response)
      setDirty(false)
      setToast({ message: '步骤顺序已保存', tone: 'success' })
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '保存失败', tone: 'error' })
    }
  }

  const toggleStepStatus = async (stepId: string, next: ProtocolStep['status']) => {
    if (!detail) return
    const steps = detail.steps.map((step) => step.id === stepId ? { ...step, status: next } : step)
    try {
      const response = await updateProtocol(detail.id, { steps })
      setDetail(response)
      setDirty(true)
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '保存失败', tone: 'error' })
    }
  }

  const editStepDescription = async (stepId: string, description: string) => {
    if (!detail) return
    const steps = detail.steps.map((step) => step.id === stepId ? { ...step, description } : step)
    try {
      const response = await updateProtocol(detail.id, { steps })
      setDetail(response)
      setDirty(true)
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '保存失败', tone: 'error' })
    }
  }

  const addStep = async () => {
    if (!detail) return
    const newStepId = `manual_${Math.random().toString(36).slice(2, 10)}`
    const newStep: ProtocolStep = {
      id: `ps_manual_${Math.random().toString(36).slice(2, 10)}`,
      step_id: newStepId,
      title: '新步骤',
      description: '待填写执行说明、输入输出和依赖。',
      order_no: detail.steps.length + 1,
      dependencies: [],
      required_inputs: [],
      expected_outputs: [],
      status: 'planned',
      information_type: 'derived_suggestion',
      evidence_refs: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    try {
      const response = await updateProtocol(detail.id, {
        steps: [...detail.steps, newStep].map((step, index) => ({ ...step, order_no: index + 1 })),
      })
      setDetail(response)
      setDirty(true)
      setToast({ message: '已添加新步骤', tone: 'info' })
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '保存失败', tone: 'error' })
    }
  }

  const editParam = async (paramId: string, patch: Partial<ProtocolParameter>) => {
    if (!detail) return
    const params = detail.parameters.map((param) => param.id === paramId ? { ...param, ...patch } : param)
    try {
      const response = await updateProtocol(detail.id, { parameters: params })
      setDetail(response)
      setDirty(true)
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '保存失败', tone: 'error' })
    }
  }

  const restoreParam = async (param: ProtocolParameter) => {
    await editParam(param.id, {
      value: param.original_value,
      modified_value: null,
      modified_at: null,
      confirmed: false,
      note: null,
    })
    setToast({ message: `已恢复「${param.name}」原始值`, tone: 'info' })
  }

  const moveStep = async (stepId: string, direction: -1 | 1) => {
    if (!detail) return
    const steps = [...detail.steps].sort((a, b) => a.order_no - b.order_no)
    const index = steps.findIndex((step) => step.id === stepId)
    if (index < 0) return
    const target = index + direction
    if (target < 0 || target >= steps.length) return
    [steps[index], steps[target]] = [steps[target], steps[index]]
    const reordered = steps.map((step, i) => ({ ...step, order_no: i + 1 }))
    try {
      const response = await updateProtocol(detail.id, { steps: reordered })
      setDetail(response)
      setDirty(true)
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '保存失败', tone: 'error' })
    }
  }

  const saveVersion = async () => {
    if (!detail) return
    try {
      const version = await saveProtocolVersion(detail.id, '用户手动保存')
      setToast({ message: `已保存 v${version.version_no}`, tone: 'success' })
      setDirty(false)
      await refreshList(true)
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '保存失败', tone: 'error' })
    }
  }

  const deleteSelected = async () => {
    if (!detail) return
    try {
      await deleteProtocol(detail.id)
      setDetail(null)
      setSelectedId(null)
      await refreshList()
      setToast({ message: '方案已删除', tone: 'success' })
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '删除失败', tone: 'error' })
    }
  }

  const closeGenerateDialog = () => {
    setGenerateOpen(false)
    setGenerateName('')
    setGeneratePaperId('')
  }

  const handleGenerate = async () => {
    if (!generatePaperId || generateNameTooLong) return
    setGenerateLoading(true)
    try {
      const protocol = await generateProtocol({
        paper_id: generatePaperId,
        name: generateName.trim() || undefined,
      })
      setSelectedId(protocol.id)
      closeGenerateDialog()
      setDirty(false)
      setToast({ message: `已生成「${protocol.name}」`, tone: 'success' })
      await refreshList(true)
    } catch (error) {
      const msg = error instanceof ApiError && error.status === 400
        ? (error.code === 'paper_not_parsed' ? '请先在论文中心完成解析。' : error.message)
        : error instanceof Error ? error.message : '生成失败'
      setToast({ message: msg, tone: 'error' })
    } finally {
      setGenerateLoading(false)
    }
  }

  const downloadProtocol = async (format: 'markdown' | 'json') => {
    if (!detail) return
    const path = protocolExportPath(detail.id, format)
    if (!getDemoAccessCode()) {
      window.open(`${API_BASE_URL}${path}`, '_blank', 'noopener')
      return
    }
    try {
      await downloadApiFile(path, `protocol-${detail.id}.${format === 'json' ? 'json' : 'md'}`)
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : '导出失败。', tone: 'error' })
    }
  }

  const completion = detail ? (detail.steps.filter((step) => step.status === 'done').length / Math.max(detail.steps.length, 1)) * 100 : 0
  const aiUnconfigured = detail && detail.ai_status === 'unconfigured'
  const hasPaperFact = detail ? detail.steps.some((step) => step.information_type === 'paper_fact') : false

  const selectablePapers = papers.filter((paper) => paper.parse_status === 'completed')
  const blockedSteps = detail ? detail.steps.filter((step) => step.status === 'blocked') : []
  const selectedParam = detail?.parameters.find((param) => param.id === selectedParamId) ?? null

  return (
    <div>
      <PageHeader
        eyebrow="Protocol builder / Every research paper is reproducible"
        title="把研究方法，转化为每一步都可验证。"
        description="选择已解析的论文 → Protocol Agent 生成结构化实验步骤和参数 → 可编辑、可追溯、可版本化。"
        actions={(
          <>
            <Button onClick={() => void refreshList()} disabled={listLoading} icon={listLoading ? <LoaderCircle size={15} className="animate-spin" /> : <RefreshCw size={15} />}>刷新</Button>
            <Button variant="primary" onClick={() => setGenerateOpen(true)} icon={<WandSparkles size={15} />}>新建实验方案</Button>
          </>
        )}
      />

      {aiUnconfigured && (
        <Card className="mt-4 border-warning/15 bg-warning/[.03]">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-warning/20 bg-warning/10 text-warning"><Cpu size={17} /></div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-xs font-medium text-ink">Protocol Agent 处于规则驱动模式</p>
                <Badge tone="amber">LOCAL RULES</Badge>
              </div>
              <p className="mt-1 text-[11px] leading-5 text-muted">
                后端未配置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。当前方案来自规则模板：能识别论文标题/作者/摘要等已解析字段，但对未在论文中说明的超参数、训练轮数不会编造，会标记为 <span className="font-mono text-[#F8B87A]">unknown</span> 或 <span className="font-mono text-[#C9B7FA]">derived_suggestion</span>。
              </p>
            </div>
          </div>
        </Card>
      )}

      <div className="mt-5 grid grid-cols-12 gap-5">
        {/* ============ LEFT COLUMN ============ */}
        <div className="col-span-12 space-y-4 xl:col-span-3">
          <Card padded={false}>
            <div className="border-b border-white/[.06] p-4">
              <p className="font-mono text-[10px] uppercase tracking-[.16em] text-primary">Sources</p>
              <p className="mt-1.5 text-xs text-muted">已解析论文（{selectablePapers.length}/{papers.length}）</p>
            </div>
            <div className="max-h-[280px] space-y-1.5 overflow-y-auto p-3">
              {selectablePapers.length === 0 && (
                <div className="p-4 text-center">
                  <BookOpenText size={22} className="mx-auto text-[#526078]" />
                  <p className="mt-2 text-xs text-muted">暂无已解析论文</p>
                  <p className="mt-1 text-[10px] leading-5 text-[#65728B]">上传并解析 PDF 后，可在这里选取论文生成实验方案。</p>
                </div>
              )}
              {selectablePapers.map((paper) => (
                <button
                  key={paper.id}
                  onClick={() => { setGeneratePaperId(paper.id); setGenerateName(''); setGenerateOpen(true) }}
                  className="w-full rounded-lg border border-transparent p-2.5 text-left transition hover:border-primary/20 hover:bg-white/[.025]"
                >
                  <div className="flex items-center gap-2">
                    <Badge tone="green">已解析</Badge>
                    <span className="ml-auto font-mono text-[9px] text-muted">{paper.page_count}P</span>
                  </div>
                  <p className="mt-1.5 truncate text-[11px] font-medium leading-5 text-[#D0D9E7]">{paper.title}</p>
                  <p className="mt-0.5 truncate font-mono text-[9px] text-muted">{paper.filename}</p>
                </button>
              ))}
            </div>
          </Card>

          <Card padded={false}>
            <div className="flex items-center justify-between border-b border-white/[.06] p-4">
              <p className="font-mono text-[10px] uppercase tracking-[.16em] text-primary">Protocols</p>
              <span className="font-mono text-[9px] text-muted">{protocols.length}</span>
            </div>
            <div className="max-h-[320px] space-y-1.5 overflow-y-auto p-3">
              {listError && (
                <div className="p-4 text-center">
                  <AlertCircle size={20} className="mx-auto text-danger" />
                  <p className="mt-2 text-xs text-muted">{listError}</p>
                  <button onClick={() => void refreshList()} className="mt-2 text-[11px] text-primary">重新加载</button>
                </div>
              )}
              {listLoading && !protocols.length && (
                <div className="space-y-2 p-3">
                  {[0, 1, 2].map((item) => (
                    <div key={item} className="h-14 animate-pulse rounded-lg bg-white/[.04]" />
                  ))}
                </div>
              )}
              {!listLoading && !listError && protocols.length === 0 && (
                <div className="p-5 text-center">
                  <FlaskConical size={22} className="mx-auto text-[#526078]" />
                  <p className="mt-2 text-xs text-muted">还没有实验方案</p>
                  <p className="mt-1 text-[10px] leading-5 text-[#65728B]">点击上方按钮，从已解析论文生成。</p>
                </div>
              )}
              {!listLoading && protocols.map((protocol) => {
                const isSelected = selectedId === protocol.id
                const badge_meta = PROTOCOL_STATUS[protocol.status] ?? PROTOCOL_STATUS.generated
                return (
                  <button
                    key={protocol.id}
                    onClick={() => setSelectedId(protocol.id)}
                    className={`w-full rounded-lg border p-3 text-left transition ${
                      isSelected ? 'border-primary/25 bg-primary/[.065]' : 'border-transparent hover:border-white/[.06] hover:bg-white/[.025]'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Badge tone={badge_meta.tone}>{badge_meta.label}</Badge>
                      {protocol.ai_status === 'success' && <Badge tone="violet">AI</Badge>}
                      {(protocol.ai_status === 'unconfigured' || protocol.ai_status === 'not_used') && <Badge tone="amber">规则</Badge>}
                      <span className="ml-auto font-mono text-[9px] text-muted">v{protocol.version_no}</span>
                    </div>
                    <p className="mt-1.5 truncate text-[11px] font-medium leading-5 text-[#D0D9E7]">{protocol.name}</p>
                    <p className="mt-0.5 truncate font-mono text-[9px] text-muted">← {protocol.paper_title}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <ProgressBar value={Math.round((protocol.steps_count / 8) * 100)} className="h-1 flex-1" />
                      <span className="font-mono text-[9px] text-muted">{protocol.steps_count}S</span>
                    </div>
                  </button>
                )
              })}
            </div>
          </Card>
        </div>

        {/* ============ CENTER COLUMN ============ */}
        <Card className="col-span-12 xl:col-span-6" padded={false}>
          {detailLoading && !detail ? (
            <div className="p-6 space-y-4">
              <div className="h-4 w-40 animate-pulse rounded bg-white/[.06]" />
              <div className="h-6 w-3/4 animate-pulse rounded bg-white/[.06]" />
              <div className="h-40 animate-pulse rounded-xl bg-white/[.04]" />
            </div>
          ) : !detail ? (
            <div className="status-grid flex min-h-[560px] flex-col items-center justify-center p-10 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary"><FlaskConical size={24} /></div>
              <h2 className="mt-5 font-display text-lg font-semibold text-ink">生成或选择一个实验方案开始</h2>
              <p className="mt-2 max-w-md text-xs leading-6 text-muted">
                Protocol Agent 会从已解析的论文中抽取研究方法、模型架构、数据集和超参数，编排为可执行的工作流；对于论文没有说明的部分，会标记为 <span className="font-mono">unknown</span> 并提示待确认。
              </p>
            </div>
          ) : (
            <>
              <div className="border-b border-white/[.06] p-6">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={PROTOCOL_STATUS[detail.status]?.tone ?? 'neutral'}>{PROTOCOL_STATUS[detail.status]?.label ?? detail.status}</Badge>
                  <Badge tone={detail.agent_method === 'hybrid' ? 'violet' : 'amber'}>
                    {detail.agent_method === 'hybrid' ? 'AI + 规则' : '规则模板'}
                  </Badge>
                  <span className="ml-auto font-mono text-[9px] text-muted">
                    v{detail.version_no} · {formatDateTime(detail.updated_at)}
                    {dirty && <span className="ml-2 text-warning">· 未保存</span>}
                  </span>
                </div>
                <h2 className="mt-3 text-[20px] font-semibold tracking-tight text-ink">{detail.name}</h2>
                <p className="mt-1.5 text-xs text-muted">← {detail.paper_title}</p>

                <div className="mt-5 grid grid-cols-3 gap-3">
                  <StatCard label="READY" value={`${completion}%`} />
                  <StatCard label="STEPS" value={`${detail.steps.length}`} sub={`${detail.steps.filter((s) => s.status === 'done').length} 已完成`} />
                  <StatCard label="PARAMS" value={`${detail.parameters.length}`} sub={`${detail.parameters.filter((p) => p.source_type === 'unknown').length} 待定`} />
                </div>

                <div className="mt-5 flex flex-wrap gap-2">
                  <Button variant="primary" onClick={() => { void saveVersion() }} icon={<Save size={15} />} disabled={!dirty}>保存版本</Button>
                  <Button onClick={() => setVersionsOpen(true)} icon={<History size={15} />}>版本历史</Button>
                  <Button onClick={() => void downloadProtocol('markdown')} icon={<Download size={15} />}>导出 MD</Button>
                  <Button onClick={() => void downloadProtocol('json')} icon={<Download size={15} />}>导出 JSON</Button>
                  <Button variant="danger" onClick={() => { void deleteSelected() }} icon={<Trash2 size={15} />}>删除</Button>
                </div>
              </div>

              <div className="flex gap-6 border-b border-white/[.06] px-6">
                {([
                  ['overview', '概览'],
                  ['workflow', '步骤工作流'],
                  ['params', '参数表'],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setActiveTab(value)}
                    className={`relative py-3.5 text-xs transition ${
                      activeTab === value
                        ? 'text-ink after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-primary'
                        : 'text-muted hover:text-ink'
                    }`}
                  >{label}</button>
                ))}
              </div>

              <div className="p-6">
                {activeTab === 'overview' && (
                  <div className="animate-fade-up space-y-4">
                    <div className="rounded-xl border border-primary/15 bg-primary/[.04] p-4">
                      <p className="font-mono text-[10px] uppercase tracking-[.16em] text-[#C1ADF8]">EXPERIMENT GOAL</p>
                      <textarea
                        value={goalDraft}
                        onChange={(event) => setGoalDraft(event.target.value)}
                        placeholder="填写实验目标"
                        className="mt-2 min-h-24 w-full resize-y rounded-lg border border-white/[.06] bg-canvas/40 p-2.5 text-[13px] leading-7 text-[#D9CEFF] outline-none focus:border-primary/40"
                      />
                      <div className="mt-3 flex justify-end">
                        <Button size="sm" variant="primary" onClick={() => void saveGoal()} disabled={goalSaving || !goalDraft.trim()} icon={goalSaving ? <LoaderCircle size={13} className="animate-spin" /> : <Save size={13} />}>
                          {goalSaving ? '保存中…' : '保存目标并记录版本'}
                        </Button>
                      </div>
                    </div>
                    {detail.summary && (
                      <p className="text-[12px] leading-7 text-muted">{detail.summary}</p>
                    )}
                    <div className="flex items-center gap-3">
                      <Gauge size={16} className="text-primary" />
                      <span className="text-[11px] text-muted">
                        论文事实 {detail.steps.filter((s) => s.information_type === 'paper_fact').length} 条 ·
                        AI 建议 {detail.steps.filter((s) => s.information_type === 'derived_suggestion').length} 条 ·
                        待确认 {detail.steps.filter((s) => s.information_type === 'unknown').length} 条
                      </span>
                    </div>
                    {blockedSteps.length > 0 && (
                      <div className="rounded-xl border border-danger/20 bg-danger/[.04] p-4">
                        <p className="flex items-center gap-2 text-[11px] font-medium text-danger"><AlertCircle size={14} />当前有 {blockedSteps.length} 个步骤被标记为阻塞</p>
                        {blockedSteps.map((step) => (
                          <p key={step.id} className="mt-2 text-[11px] leading-6 text-muted">· {step.title}</p>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'workflow' && (
                  <div className="animate-fade-up space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-mono text-[10px] uppercase tracking-[.16em] text-muted">EXECUTION ORDER</p>
                      <div className="flex flex-wrap gap-2">
                        <div className="flex rounded-lg border border-white/[.06] bg-canvas/40 p-0.5">
                          {(['dag', 'list'] as const).map((view) => (
                            <button
                              key={view}
                              onClick={() => setWorkflowView(view)}
                              className={`rounded-md px-2.5 py-1.5 text-[10px] transition ${workflowView === view ? 'bg-primary/15 text-primary' : 'text-muted hover:text-ink'}`}
                            >{view === 'dag' ? 'DAG' : '列表'}</button>
                          ))}
                        </div>
                        <Button size="sm" onClick={() => { void moveStep(detail.steps[0]?.id ?? '', -1) }} disabled={detail.steps.length === 0} icon={<ArrowUp size={12} />} />
                        <Button size="sm" onClick={updateStepsOrder} variant="secondary" icon={<Save size={12} />}>保存排序</Button>
                        <Button size="sm" onClick={addStep} variant="primary" icon={<Plus size={12} />}>添加步骤</Button>
                      </div>
                    </div>
                    {workflowView === 'dag' ? (
                      <ProtocolFlow steps={detail.steps} onSaveSteps={saveSteps} onOpenEvidence={openEvidence} />
                    ) : (
                      <>
                    {detail.steps.length === 0 && (
                      <div className="flex h-32 items-center justify-center rounded-xl border border-white/[.06] bg-canvas/30 text-xs text-muted">
                        暂无步骤
                      </div>
                    )}
                    {[...detail.steps].sort((a, b) => a.order_no - b.order_no).map((step, index) => {
                      const info = INFO_META[step.information_type]
                      const stat = STATUS_META[step.status]
                      const canMoveUp = index > 0
                      const canMoveDown = index < detail.steps.length - 1
                      const needsInput = step.information_type === 'unknown'
                      return (
                        <div key={step.id} className={`rounded-xl border p-4 transition hover:border-white/[.12] ${
                          step.status === 'done' ? 'border-success/10 bg-success/[.025]' :
                          step.status === 'blocked' ? 'border-danger/15 bg-danger/[.04]' :
                          step.information_type === 'paper_fact' ? 'border-white/[.08] bg-canvas/30' :
                          'border-white/[.05] bg-canvas/25'
                        }`}>
                          <div className="flex items-center gap-3">
                            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 font-mono text-[10px] text-primary">{step.order_no}</div>
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className={`text-[13px] font-medium leading-5 ${step.status === 'done' ? 'text-[#75839B] line-through' : 'text-ink'}`}>{step.title}</p>
                                <Badge tone={info.tone}>{info.label}</Badge>
                                <Badge tone={stat.tone}>{stat.label}</Badge>
                                {step.evidence_refs.length > 0 && <Badge tone="cyan">{step.evidence_refs.length} 条证据</Badge>}
                                {needsInput && <Badge tone="amber">待补</Badge>}
                                <span className="ml-auto font-mono text-[9px] text-muted">{step.step_id}</span>
                              </div>
                            </div>
                          </div>
                          <div className="mt-2.5 flex gap-3">
                            <button onClick={() => toggleStepStatus(step.id, 'planned')} className={`rounded border px-2 py-1 text-[10px] transition ${step.status === 'planned' ? 'border-primary/40 bg-primary/10 text-[#C9B7FA]' : 'border-white/[.06] text-muted hover:text-ink'}`}>待执行</button>
                            <button onClick={() => toggleStepStatus(step.id, 'running')} className={`rounded border px-2 py-1 text-[10px] transition ${step.status === 'running' ? 'border-accent/40 bg-accent/10 text-accent' : 'border-white/[.06] text-muted hover:text-ink'}`}>执行中</button>
                            <button onClick={() => toggleStepStatus(step.id, 'done')} className={`rounded border px-2 py-1 text-[10px] transition ${step.status === 'done' ? 'border-success/40 bg-success/10 text-success' : 'border-white/[.06] text-muted hover:text-ink'}`}>已完成</button>
                            <button onClick={() => toggleStepStatus(step.id, 'blocked')} className={`rounded border px-2 py-1 text-[10px] transition ${step.status === 'blocked' ? 'border-danger/40 bg-danger/10 text-danger' : 'border-white/[.06] text-muted hover:text-ink'}`}>阻塞</button>
                            <div className="ml-auto flex gap-1">
                              <button onClick={() => void moveStep(step.id, -1)} disabled={!canMoveUp} className="rounded border border-white/[.06] p-1 text-muted hover:text-ink disabled:opacity-30" title="上移"><ArrowUp size={12} /></button>
                              <button onClick={() => void moveStep(step.id, 1)} disabled={!canMoveDown} className="rounded border border-white/[.06] p-1 text-muted hover:text-ink disabled:opacity-30" title="下移"><ArrowUp size={12} className="rotate-180" /></button>
                            </div>
                          </div>
                          <textarea
                            value={step.description ?? ''}
                            onChange={(event) => editStepDescription(step.id, event.target.value)}
                            className="mt-3 min-h-[48px] w-full resize-none rounded-lg border border-white/[.06] bg-canvas/40 p-2.5 text-[11px] leading-6 text-[#B7C2D3] outline-none focus:border-primary/40"
                          />
                          {(step.required_inputs.length > 0 || step.expected_outputs.length > 0) && (
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {step.required_inputs.map((input, index) => (
                                <span key={`in-${index}`} className="rounded border border-white/[.06] bg-white/[.03] px-1.5 py-0.5 font-mono text-[9px] text-muted">→ {input}</span>
                              ))}
                              {step.expected_outputs.map((output, index) => (
                                <span key={`out-${index}`} className="rounded border border-success/15 bg-success/[.05] px-1.5 py-0.5 font-mono text-[9px] text-success">{output} →</span>
                              ))}
                            </div>
                          )}
                          {step.evidence_refs.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {step.evidence_refs.map((reference) => (
                                <button key={reference} onClick={() => void openEvidence(reference)} className="flex items-center gap-1 rounded border border-accent/15 bg-accent/[.04] px-1.5 py-0.5 font-mono text-[9px] text-accent hover:border-accent/35">
                                  <BookOpenText size={10} />{reference}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    })}
                      </>
                    )}
                  </div>
                )}

                {activeTab === 'params' && (
                  <div className="animate-fade-up space-y-2">
                    <div className="rounded-xl border border-white/[.06] bg-canvas/30 overflow-hidden">
                      <div className="grid grid-cols-12 gap-2 border-b border-white/[.06] px-4 py-2.5 font-mono text-[9px] uppercase tracking-[.12em] text-muted">
                        <div className="col-span-3">参数</div>
                        <div className="col-span-3">值</div>
                        <div className="col-span-2">来源</div>
                        <div className="col-span-1">页码</div>
                        <div className="col-span-1">确认</div>
                        <div className="col-span-2 text-right">操作</div>
                      </div>
                      {detail.parameters.length === 0 && (
                        <div className="p-8 text-center text-xs text-muted">暂无参数</div>
                      )}
                      {detail.parameters.map((param) => (
                        <ParamRow
                          key={param.id}
                          param={param}
                          selected={selectedParamId === param.id}
                          onSelect={() => setSelectedParamId(param.id)}
                          onEdit={(patch) => void editParam(param.id, patch)}
                          onRestore={() => void restoreParam(param)}
                        />
                      ))}
                    </div>
                    {selectedParam && (
                      <div className="rounded-xl border border-white/[.06] bg-canvas/30 p-4">
                        <SectionHeader title={selectedParam.name} eyebrow="Parameter source chain" />
                        <ParameterSourceChain parameter={selectedParam} paper={paperDetail} onOpenEvidence={openEvidence} onRestore={(param) => void restoreParam(param)} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </Card>

        {/* ============ RIGHT COLUMN ============ */}
        <div className="col-span-12 space-y-4 xl:col-span-3">
          {detail && (
            <>
              <Card>
                <SectionHeader title="Protocol Agent" eyebrow="Agent info" action={<Sparkles size={15} className="text-muted" />} />
                <div className="mt-3 space-y-2 text-[11px] leading-6 text-muted">
                  <div className="flex items-center justify-between border-b border-white/[.05] pb-2"><span className="font-mono text-[9px] uppercase tracking-[.16em] text-muted">METHOD</span><span className="text-[#D0D9E7]">{detail.agent_method}</span></div>
                  <div className="flex items-center justify-between border-b border-white/[.05] pb-2"><span className="font-mono text-[9px] uppercase tracking-[.16em] text-muted">AI STATUS</span><span className={detail.ai_status === 'success' ? 'text-success' : detail.ai_status === 'failed' ? 'text-danger' : 'text-warning'}>{detail.ai_status}</span></div>
                  <div className="flex items-center justify-between border-b border-white/[.05] pb-2"><span className="font-mono text-[9px] uppercase tracking-[.16em] text-muted">SOURCE FIELDS</span><span className="text-[#D0D9E7]">{detail.source_fields.length}</span></div>
                  {detail.ai_error && (
                    <div className="rounded-lg border border-danger/20 bg-danger/[.04] p-2.5 text-[10px] leading-5 text-danger/90">
                      {detail.ai_error}
                    </div>
                  )}
                  <p className="pt-1 text-[10px] leading-5 text-[#75839B]">
                    信息类型三档：<span className="text-[#7EE0B2]">论文事实</span>、<span className="text-[#C9B7FA]">AI 建议</span>、<span className="text-[#F0B96E]">待确认</span>。AI 建议不伪装为论文原文。
                  </p>
                </div>
              </Card>

              {detail.open_questions.length > 0 && (
                <Card>
                  <SectionHeader title="待确认问题" eyebrow="To verify" action={<AlertCircle size={15} className="text-muted" />} />
                  <div className="mt-3 space-y-2">
                    {detail.open_questions.map((q, index) => (
                      <div key={index} className="rounded-lg border border-warning/15 bg-warning/[.035] p-3">
                        <div className="flex items-center gap-2">
                          <Badge tone="amber">{q.field || '—'}</Badge>
                        </div>
                        <p className="mt-1.5 text-[11px] leading-6 text-[#D8B27A]">{q.question}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {hasPaperFact && (
                <Card>
                  <SectionHeader title="来自论文的事实" eyebrow="Paper facts" action={<BookOpenText size={15} className="text-muted" />} />
                  <div className="mt-3 max-h-[240px] space-y-2 overflow-y-auto">
                    {detail.steps.filter((s) => s.information_type === 'paper_fact').map((step) => (
                      <div key={step.id} className="rounded-lg border border-success/15 bg-success/[.025] p-3">
                        <p className="text-[11px] font-medium text-success">{step.title}</p>
                        <p className="mt-1 text-[10px] leading-5 text-muted">{step.description ?? ''}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </>
          )}
        </div>
      </div>

      {/* Generate modal */}
      <Modal open={generateOpen} onClose={() => { if (!generateLoading) closeGenerateDialog() }} title="从已解析论文生成实验方案" description="选择论文后点击生成，Protocol Agent 会基于已抽取的结构化字段创建可追溯的工作流。">
        <form onSubmit={(event) => { event.preventDefault(); void handleGenerate() }} className="space-y-5">
          <label className="block">
            <span className="text-xs font-medium text-ink">来源论文</span>
            <select value={generatePaperId} onChange={(event) => setGeneratePaperId(event.target.value)} className="field mt-2">
              <option value="" disabled>选择已解析论文…</option>
              {selectablePapers.map((paper) => (
                <option key={paper.id} value={paper.id}>{paper.title}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink">方案名称（可选）</span>
            <input value={generateName} onChange={(event) => setGenerateName(event.target.value)} className="field mt-2" placeholder="留空则根据论文标题自动命名" aria-invalid={generateNameTooLong} aria-describedby="protocol-generate-name-help" />
            <span id="protocol-generate-name-help" className={`mt-2 block text-xs ${generateNameTooLong ? 'text-danger' : 'text-muted'}`}>
              {generateNameTooLong ? `方案名称最多 ${PROTOCOL_NAME_LIMIT} 个字符，请缩短后再生成。` : `自定义名称最多 ${PROTOCOL_NAME_LIMIT} 个字符。`}
            </span>
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={closeGenerateDialog} disabled={generateLoading}>取消</Button>
            <Button type="submit" variant="primary" disabled={!generatePaperId || generateNameTooLong || generateLoading} icon={generateLoading ? <LoaderCircle size={14} className="animate-spin" /> : <WandSparkles size={14} />}>
              {generateLoading ? '生成中…' : '生成实验方案'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Versions modal */}
      <Modal open={versionsOpen} onClose={() => setVersionsOpen(false)} title="版本历史" description="每次手动保存或初始生成都会创建一个版本快照。" className="max-w-lg">
        <div className="space-y-2">
          {versionsLoading && <LoaderCircle size={16} className="mx-auto animate-spin text-accent" />}
          {!versionsLoading && versions.length === 0 && <p className="p-4 text-center text-xs text-muted">暂无版本</p>}
          {versions.map((version, index) => (
            <div key={version.id} className={`flex items-center gap-3 rounded-lg border p-3 ${index === 0 ? 'border-primary/25 bg-primary/[.05]' : 'border-white/[.06] bg-canvas/30'}`}>
              <div className="flex h-7 w-7 items-center justify-center rounded-md border border-white/[.06] bg-canvas/50 font-mono text-[10px] text-muted">v{version.version_no}</div>
              <div className="flex-1">
                <p className="text-[11px] font-medium text-ink">{version.message ?? '保存'}</p>
                <p className="mt-0.5 font-mono text-[9px] text-muted">{formatDateTime(version.created_at)}</p>
              </div>
              {index === 0 && <Badge tone="green">最新</Badge>}
            </div>
          ))}
        </div>
      </Modal>

      <EvidenceModal
        evidence={selectedEvidence}
        label={selectedEvidence?.field ?? ''}
        pageText={evidencePageText}
        loading={evidenceLoading}
        paperId={detail?.paper_id}
        onClose={() => { setSelectedEvidence(null); setEvidencePageText(null) }}
      />

      {toast && <Toast message={toast.message} tone={toast.tone} onClose={closeToast} />}
    </div>
  )
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-canvas/45 p-3">
      <p className="font-mono text-[9px] uppercase tracking-[.12em] text-muted">{label}</p>
      <p className="mt-1.5 font-display text-lg font-semibold text-ink">{value}</p>
      {sub && <p className="mt-0.5 text-[10px] text-muted">{sub}</p>}
    </div>
  )
}

function ParamRow({ param, selected, onSelect, onEdit, onRestore }: {
  param: ProtocolParameter
  selected: boolean
  onSelect: () => void
  onEdit: (patch: Partial<ProtocolParameter>) => void
  onRestore: () => void
}) {
  const info = INFO_META[param.source_type]
  const modified = param.value !== param.original_value
  return (
    <div onClick={onSelect} className={`grid cursor-pointer grid-cols-12 gap-2 border-b border-white/[.05] px-4 py-2.5 text-[11px] transition ${selected ? 'bg-primary/[.06]' : 'hover:bg-white/[.025]'}`}>
      <div className="col-span-3 flex items-center gap-1.5 truncate">
        <span className="font-mono text-[10px] text-ink">{param.name}</span>
        {modified && <span className="rounded border border-warning/25 bg-warning/[.06] px-1 font-mono text-[8px] text-warning">EDITED</span>}
      </div>
      <div className="col-span-3">
        <input
          key={`${param.id}-${param.updated_at}`}
          defaultValue={param.value ?? ''}
          onBlur={(event) => {
            const next = event.target.value.trim() || null
            if (next !== param.value) onEdit({ value: next })
          }}
          placeholder={param.original_value ?? '—'}
          className="w-full rounded border border-white/[.06] bg-canvas/50 px-2 py-1 font-mono text-[10px] text-[#D0D9E7] outline-none focus:border-primary/40"
        />
      </div>
      <div className="col-span-2 flex items-center">
        <Badge tone={info.tone}>{info.label}</Badge>
      </div>
      <div className="col-span-1 flex items-center">
        <span className="font-mono text-[10px] text-muted">{param.page_number ? `P.${param.page_number}` : '—'}</span>
      </div>
      <div className="col-span-1 flex items-center">
        <label className="flex cursor-pointer items-center gap-1 text-muted">
          <input type="checkbox" defaultChecked={param.confirmed} onChange={(event) => onEdit({ confirmed: event.target.checked })} className="accent-primary" />
        </label>
      </div>
      <div className="col-span-2 flex items-center justify-end gap-1">
        <button onClick={() => onEdit({ note: prompt('备注', param.note ?? '') ?? null })} className="rounded border border-white/[.06] p-1 text-muted hover:text-ink" title="备注">📝</button>
        {modified && (
          <button onClick={onRestore} className="rounded border border-white/[.06] px-1.5 py-0.5 text-[10px] text-muted hover:text-warning" title="恢复原始值">恢复</button>
        )}
      </div>
    </div>
  )
}
