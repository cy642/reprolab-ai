import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Download, FileJson2, FileText, GitBranch, ShieldAlert } from 'lucide-react'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { exportWorkflowReport, getWorkflowReport, listWorkflows } from '../lib/workflows'
import type { WorkflowReport, WorkflowStatus, WorkflowSummary } from '../types/workflow'

const statusLabels: Record<WorkflowStatus, string> = {
  pending: '待启动', running: '执行中', waiting_approval: '等待审批', completed: '流程完成', failed: '失败', cancelled: '已取消',
}
const statusTones: Record<WorkflowStatus, BadgeTone> = {
  pending: 'neutral', running: 'cyan', waiting_approval: 'amber', completed: 'green', failed: 'red', cancelled: 'neutral',
}

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
}

export function ResearchReport() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [report, setReport] = useState<WorkflowReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [reportLoading, setReportLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    listWorkflows(undefined, controller.signal).then((result) => {
      setWorkflows(result.items)
      const first = result.items.find((item) => item.report_finalized) ?? result.items[0]
      if (first) {
        setReportLoading(true)
        setSelectedId(first.id)
      }
    }).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === 'AbortError') return
      setError(reason instanceof Error ? reason.message : '无法读取工作流报告列表')
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    getWorkflowReport(selectedId, controller.signal).then(setReport).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === 'AbortError') return
      setError(reason instanceof Error ? reason.message : '报告尚未生成或读取失败')
    }).finally(() => {
      if (!controller.signal.aborted) setReportLoading(false)
    })
    return () => controller.abort()
  }, [selectedId])

  const selectWorkflow = (id: string) => {
    if (id === selectedId) return
    setReportLoading(true)
    setSelectedId(id)
    setReport(null)
    setError(null)
  }

  const exportReport = async (format: 'markdown' | 'json') => {
    if (!selectedId || !report) return
    setExporting(format)
    setError(null)
    try {
      await exportWorkflowReport(selectedId, format)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '报告导出失败')
    } finally {
      setExporting(null)
    }
  }

  const finalizedCount = workflows.filter((item) => item.report_finalized).length
  const selected = workflows.find((item) => item.id === selectedId)

  return (
    <div>
      <PageHeader
        showDemo={false}
        eyebrow="Research report / Frozen evidence"
        title="报告来自已定稿的运行快照。"
        description="报告中心读取真实工作流 API。论文、协议、审计、实验与洞察均保留运行时的数据版本；流程完成不等于科学有效，本地定稿也不代表上传到外部服务。"
        actions={<><Button disabled={!report || exporting !== null} onClick={() => void exportReport('markdown')} icon={<Download size={15} />}>{exporting === 'markdown' ? '导出中…' : '导出 Markdown'}</Button><Button disabled={!report || exporting !== null} onClick={() => void exportReport('json')} icon={<FileJson2 size={15} />}>导出 JSON</Button></>}
      />

      {error && <div role="alert" className="mb-5 rounded-xl border border-warning/20 bg-warning/[.06] px-4 py-3 text-xs text-warning">{error}</div>}
      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12 xl:col-span-3" padded={false}>
          <div className="border-b border-white/[.06] p-4"><p className="font-mono text-[9px] uppercase tracking-[.16em] text-primary">Workflow report library</p><p className="mt-1.5 text-xs text-muted">{finalizedCount} 份已定稿 · {workflows.length} 条真实流程记录</p></div>
          <div className="space-y-2 p-3">
            {loading && <p className="px-3 py-8 text-center text-xs text-muted">正在读取 /api/workflows…</p>}
            {!loading && workflows.length === 0 && <div className="px-4 py-10 text-center"><FileText size={24} className="mx-auto text-muted" /><p className="mt-3 text-xs text-ink">暂无工作流报告</p><p className="mt-2 text-[10px] leading-5 text-muted">完成实验洞察后，报告才会出现在这里。</p><Link to="/workflows" className="mt-4 inline-flex items-center gap-1 text-[11px] text-primary">进入工作流<ArrowRight size={12} /></Link></div>}
            {workflows.map((workflow) => <button key={workflow.id} onClick={() => selectWorkflow(workflow.id)} className={`w-full rounded-xl border p-4 text-left transition ${selectedId === workflow.id ? 'border-primary/25 bg-primary/[.07]' : 'border-transparent hover:border-white/[.06] hover:bg-white/[.025]'}`}><div className="flex items-center gap-2"><FileText size={15} className={selectedId === workflow.id ? 'text-primary' : 'text-muted'} /><Badge tone={statusTones[workflow.status]} className="ml-auto">{statusLabels[workflow.status]}</Badge></div><p className="mt-3 text-xs font-medium leading-5 text-[#D2DBE8]">{workflow.name}</p><p className="mt-2 truncate font-mono text-[9px] text-muted">{workflow.id}</p><div className="mt-3 flex items-center justify-between font-mono text-[9px] text-muted"><span>{workflow.report_finalized ? '本地已定稿' : '尚未定稿'}</span><span>{formatTime(workflow.updated_at)}</span></div></button>)}
          </div>
        </Card>

        <Card className="col-span-12 overflow-hidden xl:col-span-9" padded={false}>
          {!selectedId && !loading && <div className="flex min-h-[560px] flex-col items-center justify-center p-8 text-center"><GitBranch size={30} className="text-muted" /><p className="mt-4 text-sm text-ink">没有可显示的报告</p><p className="mt-2 max-w-md text-xs leading-6 text-muted">这里不会展示固定演示报告。请先在后端创建并运行工作流。</p></div>}
          {selectedId && reportLoading && <div className="flex min-h-[560px] items-center justify-center text-xs text-muted">正在读取固定报告快照…</div>}
          {selectedId && !reportLoading && !report && <div className="flex min-h-[560px] flex-col items-center justify-center p-8 text-center"><ShieldAlert size={30} className="text-warning" /><p className="mt-4 text-sm text-ink">报告尚不可用</p><p className="mt-2 max-w-lg text-xs leading-6 text-muted">{selected?.status === 'failed' ? `流程真实失败：${selected.error ?? '请查看节点错误'}` : '实验洞察尚未生成，或当前流程尚未到达报告节点。'} 失败流程不会被包装成成功报告。</p><Link to="/workflows" className="mt-5 inline-flex items-center gap-1.5 text-xs text-primary">查看节点与失败原因<ArrowRight size={13} /></Link></div>}
          {report && <>
            <div className="border-b border-white/[.06] p-5 sm:p-6">
              <div className="flex flex-wrap items-center gap-2"><Badge tone="violet">{displayValue(report.workflow.status)}</Badge><Badge tone={report.is_simulated ? 'amber' : 'neutral'}>{report.is_simulated ? '含模拟数据' : `来源：${report.data_source}`}</Badge>{report.data_validation_skipped && <Badge tone="red">数据验证存在缺口</Badge>}<Badge>AI：{report.ai_status}</Badge></div>
              <h1 className="mt-4 font-display text-2xl font-semibold tracking-[-.03em] text-ink">{displayValue(report.workflow.name)}</h1>
              <p className="mt-2 font-mono text-[10px] text-muted">{displayValue(report.workflow.id)} · 快照 {report.snapshot_version ?? '未提供'}</p>
              <p className="mt-3 text-[11px] leading-5 text-muted">流程结束仅表示节点执行完成；报告定稿范围为本地，不会暗示外部发布或训练复现成功。</p>
            </div>

            <div className="grid gap-4 border-b border-white/[.06] p-5 sm:grid-cols-2 sm:p-6">
              <div className="rounded-xl border border-white/[.06] bg-canvas/35 p-4"><p className="font-mono text-[9px] uppercase tracking-[.15em] text-muted">Data sources</p><div className="mt-3 flex flex-wrap gap-2">{(report.data_sources.length ? report.data_sources : [report.data_source]).map((source) => <Badge key={source} tone={source === 'simulated' || source === 'test' ? 'amber' : source === 'unknown' ? 'red' : 'neutral'}>{source}</Badge>)}</div></div>
              <div className="rounded-xl border border-white/[.06] bg-canvas/35 p-4"><p className="font-mono text-[9px] uppercase tracking-[.15em] text-muted">Node execution modes</p><div className="mt-2 space-y-1.5">{Object.entries(report.execution_modes).map(([node, mode]) => <div key={node} className="flex justify-between gap-3 font-mono text-[9px]"><span className="text-muted">{node}</span><span className="text-right text-[#C6D1E1]">{mode}</span></div>)}</div></div>
            </div>

            <article className="custom-scrollbar max-h-[720px] overflow-y-auto bg-[#0E1627]/35 p-5 sm:p-7">
              <div className="mx-auto max-w-4xl space-y-6">
                {report.sections.map((section) => <section key={`${section.title}-${section.kind}`} className="rounded-xl border border-white/[.055] bg-surface/55 p-5"><h2 className="font-display text-lg font-semibold text-ink">{section.title}</h2><div className="mt-3 space-y-2">{section.lines.map((line, index) => <p key={index} className="whitespace-pre-wrap break-words font-mono text-[11px] leading-6 text-[#BBC7D8]">{line}</p>)}</div>{section.refs.length > 0 && <p className="mt-3 break-all border-t border-white/[.05] pt-3 font-mono text-[9px] text-muted">REFS · {section.refs.join(' · ')}</p>}</section>)}
              </div>
            </article>
            <details className="border-t border-white/[.06] px-5 py-4 text-[10px] text-muted sm:px-6"><summary className="cursor-pointer text-[#B8C4D5]">查看风险摘要与关联 ID</summary><div className="mt-4 grid gap-4 md:grid-cols-2"><pre className="custom-scrollbar max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-canvas/50 p-3 font-mono text-[9px] leading-5">{JSON.stringify(report.risk_summary, null, 2)}</pre><pre className="custom-scrollbar max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-canvas/50 p-3 font-mono text-[9px] leading-5">{JSON.stringify(report.references, null, 2)}</pre></div></details>
          </>}
        </Card>
      </div>
    </div>
  )
}
