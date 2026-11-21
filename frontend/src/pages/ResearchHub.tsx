import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, BookOpenText, Database, FileCheck2, FlaskConical, GitBranch, Play, ShieldAlert, UploadCloud } from 'lucide-react'
import { StatCard } from '../components/hub/StatCard'
import { QuickStartPanel } from '../components/hub/HubPanels'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, SectionHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { getResearchOverview, type ResearchOverview } from '../lib/api'
import type { WorkflowStatus } from '../types/workflow'

const statusLabels: Record<WorkflowStatus, string> = {
  pending: '待启动', running: '执行中', waiting_approval: '等待人工确认', completed: '流程完成', failed: '失败', cancelled: '已取消',
}
const statusTones: Record<WorkflowStatus, BadgeTone> = {
  pending: 'neutral', running: 'cyan', waiting_approval: 'amber', completed: 'green', failed: 'red', cancelled: 'neutral',
}

export function ResearchHub() {
  const [overview, setOverview] = useState<ResearchOverview | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getResearchOverview(controller.signal).then(setOverview).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === 'AbortError') return
      setError(reason instanceof Error ? reason.message : '无法读取科研工作区统计')
    })
    return () => controller.abort()
  }, [])

  const loading = !overview && !error
  const workflows = overview?.workflows.items ?? []
  const running = workflows.filter((item) => item.status === 'running').length
  const waiting = workflows.filter((item) => item.status === 'waiting_approval').length
  const finalized = workflows.filter((item) => item.report_finalized).length

  return (
    <div>
      <PageHeader
        showDemo={false}
        eyebrow="Research operations / Verified overview"
        title="从真实记录开始，复核每一步研究结论。"
        description="首页仅汇总当前后端数据库中的论文、实验、数据审计和工作流状态。模拟与测试记录单独计数；流程完成不代表科学有效或训练复现完成。"
        actions={<><Link to="/papers"><Button icon={<UploadCloud size={15} />}>导入论文</Button></Link><Link to="/workflows"><Button variant="primary" icon={<Play size={15} />}>启动工作流</Button></Link></>}
      />

      {error && <div role="alert" className="mb-5 rounded-xl border border-danger/20 bg-danger/[.06] px-4 py-3 text-xs text-danger">真实 API 读取失败：{error}。请检查后端连接，页面不会用演示数值替代。</div>}
      <section className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="科研工作统计" aria-busy={loading}>
        <StatCard label="论文记录" value={loading ? '—' : overview?.papers.total ?? 0} note="来自 /api/papers · 无记录时显示 0" icon={BookOpenText} path="/papers" color="cyan" bars={[30, 44, 52, 46, 66, 78, 84]} />
        <StatCard label="科研实验记录" value={loading ? '—' : overview?.experiments.research ?? 0} note={loading ? '正在读取真实 API' : `${overview?.experiments.real ?? 0} 条标记真实 · ${overview?.experiments.unknown ?? 0} 条来源待核实 · ${overview?.experiments.demo ?? 0} 条演示隔离`} icon={FlaskConical} path="/insights" color="blue" bars={[42, 32, 58, 68, 52, 82, 72]} delay={50} />
        <StatCard label="复现工作流" value={loading ? '—' : overview?.workflows.total ?? 0} note={`${running} 个执行中 · ${finalized} 份本地定稿报告`} icon={GitBranch} path="/workflows" color="violet" bars={[35, 48, 40, 62, 55, 74, 88]} delay={100} />
        <StatCard label="待人工审批" value={loading ? '—' : waiting} note="审批仅确认继续分析，不自动消除风险" icon={ShieldAlert} path="/workflows" color="amber" bars={[72, 56, 66, 44, 52, 35, 42]} delay={150} />
      </section>

      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12 xl:col-span-8" padded={false}>
          <div className="px-5 pt-5"><SectionHeader title="最近复现工作流" description="执行状态来自 /api/workflows；点击进入节点、审批与证据链" eyebrow="Live workflow records" action={<Badge tone="violet">{workflows.length} RECORDS</Badge>} /></div>
          <div className="mt-4 divide-y divide-white/[.05] border-t border-white/[.05]">
            {!loading && workflows.length === 0 && <div className="px-5 py-12 text-center"><GitBranch size={24} className="mx-auto text-muted" /><p className="mt-3 text-xs text-ink">尚无工作流记录</p><p className="mt-1.5 text-[11px] text-muted">从论文与实验记录创建第一条可复核流程。</p><Link to="/workflows" className="mt-4 inline-flex items-center gap-1.5 text-[11px] text-primary">创建工作流<ArrowRight size={13} /></Link></div>}
            {workflows.slice(0, 6).map((workflow) => (
              <Link key={workflow.id} to="/workflows" className="grid grid-cols-[1fr_auto] items-center gap-4 px-5 py-4 transition hover:bg-white/[.022] md:grid-cols-[minmax(220px,1.5fr)_130px_110px_20px]">
                <div className="min-w-0"><p className="truncate text-xs font-medium text-[#D6DEEB]">{workflow.name}</p><p className="mt-1.5 truncate font-mono text-[9px] text-muted">{workflow.id} · {workflow.workflow_type}</p></div>
                <div className="hidden md:block"><Badge tone={statusTones[workflow.status]} dot>{statusLabels[workflow.status]}</Badge></div>
                <p className="hidden text-right font-mono text-[9px] text-muted md:block">{workflow.progress.completed}/{workflow.progress.total} 节点完成</p>
                <ArrowRight size={14} className="justify-self-end text-muted" />
              </Link>
            ))}
          </div>
        </Card>

        <div className="col-span-12 space-y-5 xl:col-span-4">
          <QuickStartPanel />
          <Card>
            <SectionHeader title="运行口径" description="配置状态与真实调用结果分开呈现" eyebrow="Evidence boundary" />
            <div className="space-y-3 text-[11px]">
              <div className="flex items-center justify-between rounded-xl bg-canvas/40 p-3"><span className="flex items-center gap-2 text-muted"><Database size={14} />数据集 / 已审计</span><span className="font-mono text-ink">{loading ? '—' : `${overview?.datasets.total ?? 0} / ${overview?.datasets.audited ?? 0}`}</span></div>
              <div className="flex items-center justify-between rounded-xl bg-canvas/40 p-3"><span className="flex items-center gap-2 text-muted"><FileCheck2 size={14} />真实 LLM 配置</span><Badge tone={overview?.papers.ai.configured ? 'cyan' : 'neutral'}>{loading ? '读取中' : overview?.papers.ai.configured ? '已配置，待端到端核验' : '未配置'}</Badge></div>
              <p className="leading-5 text-muted">启发式解析、规则审计和确定性统计可离线运行；未配置模型时，不会将模板、模拟结果或历史复用记为真实 LLM 成功。</p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
