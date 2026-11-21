import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { AlertTriangle, Check, CheckCircle2, Database, Download, FileSpreadsheet, History, LoaderCircle, Play, Plus, RefreshCw, Save, ShieldCheck, UploadCloud, X } from 'lucide-react'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, SectionHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { Toast } from '../components/ui/Toast'
import { AuditCharts } from '../components/guardian/AuditCharts'
import { FindingList } from '../components/guardian/FindingList'
import { downloadApiFile } from '../lib/api'
import { auditExportPath, getAudit, getDataset, listDatasetAudits, listDatasets, runDatasetAudit, saveDatasetMapping, uploadDataset } from '../lib/datasets'
import type { AuditRunDetail, AuditRunSummary, DatasetDetail, DatasetMappingRequest, DatasetSummary, FindingStatus, Severity } from '../types/dataset'

const emptyMapping: DatasetMappingRequest = { record_id: '', entity_id: null, label: '', split: '', feature_columns: [], split_mapping: {} }
const severityLabels: Record<Severity, string> = { critical: '严重', high: '高', medium: '中', low: '低', info: '信息' }

export function DataGuardian() {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<DatasetDetail | null>(null)
  const [draft, setDraft] = useState<DatasetMappingRequest>(emptyMapping)
  const [draftDirty, setDraftDirty] = useState(false)
  const [history, setHistory] = useState<AuditRunSummary[]>([])
  const [audit, setAudit] = useState<AuditRunDetail | null>(null)
  const [listLoading, setListLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [mappingSaving, setMappingSaving] = useState(false)
  const [auditing, setAuditing] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [severityFilter, setSeverityFilter] = useState<'all' | Severity>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | FindingStatus>('all')
  const [customSplit, setCustomSplit] = useState('')
  const [customTarget, setCustomTarget] = useState('Test')
  const [toast, setToast] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const closeToast = useCallback(() => setToast(null), [])

  const refreshList = useCallback(async () => {
    const response = await listDatasets()
    setDatasets(response.items)
    setSelectedId((current) => current ?? response.items[0]?.id ?? null)
    return response
  }, [])

  useEffect(() => {
    void refreshList().catch((error) => setToast(error instanceof Error ? error.message : '数据集加载失败')).finally(() => setListLoading(false))
  }, [refreshList])

  useEffect(() => {
    if (!selectedId) { setDetail(null); setAudit(null); setHistory([]); return }
    let cancelled = false
    setDetailLoading(true)
    void Promise.all([getDataset(selectedId), listDatasetAudits(selectedId)]).then(async ([dataset, audits]) => {
      if (cancelled) return
      setDetail(dataset)
      const source = dataset.mapping.confirmed ? dataset.mapping : dataset.suggested_mapping
      setDraft({
        record_id: source.record_id ?? '', entity_id: source.entity_id,
        label: source.label ?? '', split: source.split ?? '',
        feature_columns: source.feature_columns, split_mapping: source.split_mapping,
      })
      setDraftDirty(false)
      setHistory(audits.items)
      if (audits.items[0]) {
        const latest = await getAudit(audits.items[0].id)
        if (!cancelled) setAudit(latest)
      } else setAudit(null)
    }).catch((error) => { if (!cancelled) setToast(error instanceof Error ? error.message : '数据集详情加载失败') })
      .finally(() => { if (!cancelled) setDetailLoading(false) })
    return () => { cancelled = true }
  }, [selectedId])

  const handleUpload = async (file: File | undefined) => {
    if (!file) return
    setUploading(true)
    try {
      const uploaded = await uploadDataset(file)
      await refreshList()
      setSelectedId(uploaded.id)
      setAudit(null)
      setToast(`已解析 ${uploaded.row_count} 行 × ${uploaded.column_count} 列，请确认字段映射`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'CSV 上传失败')
    } finally {
      setUploading(false)
      setDragging(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    void handleUpload(event.dataTransfer.files[0])
  }

  const changeDraft = (patch: Partial<DatasetMappingRequest>) => {
    setDraft((current) => ({ ...current, ...patch }))
    setDraftDirty(true)
  }

  const toggleFeature = (name: string) => {
    changeDraft({ feature_columns: draft.feature_columns.includes(name) ? draft.feature_columns.filter((item) => item !== name) : [...draft.feature_columns, name] })
  }

  const saveMapping = async () => {
    if (!selectedId) return
    setMappingSaving(true)
    try {
      const updated = await saveDatasetMapping(selectedId, draft)
      setDetail(updated)
      setDraftDirty(false)
      await refreshList()
      setToast('字段映射已由用户确认并保存；患者级规则现在可以使用指定实体字段')
    } catch (error) {
      setToast(error instanceof Error ? error.message : '字段映射保存失败')
    } finally {
      setMappingSaving(false)
    }
  }

  const runAudit = async () => {
    if (!selectedId || !detail?.mapping.confirmed || draftDirty) return
    setAuditing(true)
    try {
      const result = await runDatasetAudit(selectedId)
      setAudit(result)
      setExpandedId(result.findings[0]?.finding_id ?? null)
      const audits = await listDatasetAudits(selectedId)
      setHistory(audits.items)
      await refreshList()
      setToast(`确定性审计完成：${result.finding_count} 条发现，全部可追溯到真实统计或记录`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : '审计运行失败')
    } finally {
      setAuditing(false)
    }
  }

  const openHistory = async (auditId: string) => {
    try {
      setAudit(await getAudit(auditId))
      setExpandedId(null)
    } catch (error) {
      setToast(error instanceof Error ? error.message : '审计记录加载失败')
    }
  }

  const downloadReport = async (format: 'markdown' | 'json') => {
    if (!audit) return
    try {
      await downloadApiFile(auditExportPath(audit.id, format), `data-guardian-${audit.id}.${format === 'json' ? 'json' : 'md'}`)
      setToast(`已导出 ${format === 'json' ? 'JSON' : 'Markdown'} 审计报告`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : '导出失败。')
    }
  }

  const filteredFindings = useMemo(() => (audit?.findings ?? []).filter((finding) =>
    (severityFilter === 'all' || finding.severity === severityFilter) &&
    (statusFilter === 'all' || finding.status === statusFilter),
  ), [audit, severityFilter, statusFilter])
  const canAudit = Boolean(detail?.mapping.confirmed && !draftDirty && selectedId)
  const criticalCount = (audit?.summary.severity_counts.critical ?? 0) + (audit?.summary.severity_counts.high ?? 0)

  return (
    <div>
      <PageHeader
        eyebrow="Data guardian / Deterministic evidence"
        title="先审计数据，再相信结论。"
        description="上传真实 CSV，由 Python 规则引擎检测重复、泄漏、类别、缺失、划分与特征风险；LLM 不生成审计结果。"
        actions={<>
          <Button onClick={() => downloadReport('markdown')} disabled={!audit} icon={<Download size={15} />}>导出报告</Button>
          <Button data-testid="run-audit" variant="primary" onClick={runAudit} disabled={!canAudit || auditing} icon={auditing ? <LoaderCircle size={15} className="animate-spin" /> : <Play size={15} />}>{auditing ? '规则审计中' : '运行审计'}</Button>
        </>}
      />

      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 space-y-5 xl:col-span-4">
          <Card className="relative overflow-hidden">
            <div className="status-grid absolute inset-0 opacity-20" />
            <div className="relative">
              <SectionHeader title="上传科研数据" description="默认 ≤10MB、≤50,000 行；支持 UTF-8 / GB18030" eyebrow="CSV ingestion" />
              <div
                onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={`flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed p-5 text-center transition ${dragging ? 'border-primary bg-primary/[.08]' : 'border-white/[.12] bg-canvas/35'}`}
              >
                {uploading ? <LoaderCircle size={26} className="animate-spin text-primary" /> : <UploadCloud size={26} className="text-primary" />}
                <p className="mt-3 text-xs text-ink">拖放 CSV 到这里</p>
                <p className="mt-1 text-[10px] leading-5 text-muted">文件只用于真实规则计算，不上传给 LLM</p>
                <Button className="mt-4" size="sm" disabled={uploading} onClick={() => fileInput.current?.click()} icon={<Plus size={13} />}>选择 CSV 文件</Button>
                <input ref={fileInput} data-testid="dataset-upload" type="file" accept=".csv,text/csv" className="hidden" onChange={(event) => void handleUpload(event.target.files?.[0])} />
              </div>
            </div>
          </Card>

          <Card padded={false}>
            <div className="p-5 pb-3"><SectionHeader title="数据集" description="SQLite 持久化，刷新后保留" eyebrow="Dataset registry" action={<button onClick={() => void refreshList()} className="text-muted hover:text-ink" aria-label="刷新数据集"><RefreshCw size={14} /></button>} /></div>
            <div className="custom-scrollbar max-h-72 space-y-2 overflow-y-auto px-3 pb-3">
              {listLoading ? <div className="flex justify-center py-8"><LoaderCircle size={18} className="animate-spin text-primary" /></div> : datasets.map((dataset) => (
                <button data-testid="dataset-item" key={dataset.id} onClick={() => setSelectedId(dataset.id)} className={`w-full rounded-xl border p-3.5 text-left transition ${selectedId === dataset.id ? 'border-primary/30 bg-primary/[.07]' : 'border-transparent hover:bg-white/[.025]'}`}>
                  <span className="flex items-center gap-2"><FileSpreadsheet size={15} className="shrink-0 text-accent" /><span className="truncate text-[11px] text-ink">{dataset.filename}</span><Badge tone={dataset.latest_audit_id ? 'green' : 'neutral'} className="ml-auto">{dataset.latest_audit_id ? '已审计' : '待配置'}</Badge></span>
                  <span className="mt-2 flex font-mono text-[9px] text-muted"><span>{dataset.row_count} ROWS × {dataset.column_count} COLS</span><span className="ml-auto">{dataset.missing_cells} MISSING</span></span>
                </button>
              ))}
              {!listLoading && !datasets.length && <p className="py-8 text-center text-[11px] text-muted">尚未上传数据集</p>}
            </div>
          </Card>
        </div>

        <Card className="col-span-12 xl:col-span-8">
          <SectionHeader title="字段映射" description="自动建议仅供选择，保存后才代表用户确认；患者 ID 不会仅凭名称生效" eyebrow="Human-confirmed mapping" action={detail?.mapping.confirmed && !draftDirty ? <Badge tone="green" dot>已确认</Badge> : <Badge tone="amber" dot>待确认</Badge>} />
          {detailLoading ? <div className="flex h-64 items-center justify-center"><LoaderCircle size={22} className="animate-spin text-primary" /></div> : detail ? <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <MappingSelect label="record_id · 必填" value={draft.record_id} columns={detail.columns.map((column) => column.name)} onChange={(value) => changeDraft({ record_id: value })} />
              <MappingSelect label="entity_id · 可选" value={draft.entity_id ?? ''} columns={detail.columns.map((column) => column.name)} onChange={(value) => changeDraft({ entity_id: value || null })} allowEmpty />
              <MappingSelect label="label · 必填" value={draft.label} columns={detail.columns.map((column) => column.name)} onChange={(value) => changeDraft({ label: value })} />
              <MappingSelect label="split · 必填" value={draft.split} columns={detail.columns.map((column) => column.name)} onChange={(value) => changeDraft({ split: value })} />
            </div>
            <div className="mt-5">
              <div className="mb-2 flex items-center"><p className="text-[10px] text-muted">feature_columns · 点击选择</p><span className="ml-auto font-mono text-[9px] text-primary">{draft.feature_columns.length} SELECTED</span></div>
              <div className="flex flex-wrap gap-2">{detail.columns.filter((column) => ![draft.record_id, draft.entity_id, draft.label, draft.split].includes(column.name)).map((column) => <button key={column.name} onClick={() => toggleFeature(column.name)} className={`rounded-lg border px-2.5 py-1.5 font-mono text-[9px] transition ${draft.feature_columns.includes(column.name) ? 'border-primary/30 bg-primary/10 text-[#C6B4FA]' : 'border-white/[.07] text-muted hover:text-ink'}`}>{draft.feature_columns.includes(column.name) && <Check size={11} className="mr-1 inline" />}{column.name}</button>)}</div>
            </div>
            <div className="mt-5 rounded-xl border border-white/[.055] bg-canvas/30 p-3.5">
              <p className="text-[10px] text-muted">自定义 split 值映射 <span className="ml-2 text-[9px]">原始值 → Train / Validation / Test</span></p>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row"><input value={customSplit} onChange={(event) => setCustomSplit(event.target.value)} placeholder="例如 holdout_2026" className="field h-9 py-0 text-[10px]" /><select value={customTarget} onChange={(event) => setCustomTarget(event.target.value)} className="field h-9 py-0 text-[10px] sm:w-40"><option>Train</option><option>Validation</option><option>Test</option></select><Button size="sm" onClick={() => { if (!customSplit.trim()) return; changeDraft({ split_mapping: { ...draft.split_mapping, [customSplit.trim()]: customTarget } }); setCustomSplit('') }} icon={<Plus size={12} />}>添加映射</Button></div>
              {Object.entries(draft.split_mapping).length > 0 && <div className="mt-3 flex flex-wrap gap-2">{Object.entries(draft.split_mapping).map(([raw, target]) => <span key={raw} className="inline-flex items-center gap-2 rounded-md bg-primary/10 px-2 py-1 font-mono text-[9px] text-primary">{raw} → {target}<button onClick={() => { const next = { ...draft.split_mapping }; delete next[raw]; changeDraft({ split_mapping: next }) }} aria-label={`删除 ${raw} 映射`}><X size={11} /></button></span>)}</div>}
            </div>
            <div className="mt-5 flex items-center gap-3"><Button data-testid="save-mapping" variant="primary" size="sm" onClick={saveMapping} disabled={mappingSaving || !draft.record_id || !draft.label || !draft.split || !draft.feature_columns.length} icon={mappingSaving ? <LoaderCircle size={13} className="animate-spin" /> : <Save size={13} />}>确认并保存映射</Button>{draftDirty && <span className="text-[10px] text-warning">有未保存修改，保存后才能运行审计</span>}</div>
          </> : <div className="flex h-64 flex-col items-center justify-center text-center"><Database size={28} className="text-muted" /><p className="mt-3 text-xs text-muted">上传 CSV 后配置审计字段</p></div>}
        </Card>
      </div>

      {detail && <Card className="mt-5" padded={false}>
        <div className="p-5"><SectionHeader title="字段概览" description={`${detail.filename} · ${detail.encoding} · 真实类型、缺失与唯一值统计`} eyebrow="Schema profile" /></div>
        <div className="custom-scrollbar overflow-x-auto"><table className="w-full min-w-[760px] text-left"><thead><tr className="border-y border-white/[.055] bg-canvas/30 font-mono text-[9px] text-muted"><th className="px-5 py-3 font-normal">字段</th><th className="px-3 py-3 font-normal">推断类型</th><th className="px-3 py-3 font-normal">缺失</th><th className="px-3 py-3 font-normal">唯一值</th><th className="px-5 py-3 font-normal">样例值</th></tr></thead><tbody className="divide-y divide-white/[.05]">{detail.columns.map((column) => <tr key={column.id} className="text-[10px]"><td className="px-5 py-3 font-mono text-[#C8D1DF]">{column.name}</td><td className="px-3 py-3"><Badge tone={column.inferred_type === 'integer' || column.inferred_type === 'number' ? 'cyan' : 'neutral'}>{column.inferred_type}</Badge></td><td className={`px-3 py-3 font-mono ${column.missing_count ? 'text-warning' : 'text-muted'}`}>{column.missing_count} · {(column.missing_rate * 100).toFixed(1)}%</td><td className="px-3 py-3 font-mono text-muted">{column.unique_count}</td><td className="max-w-72 truncate px-5 py-3 font-mono text-muted" title={column.sample_values.join(', ')}>{column.sample_values.join(', ') || '—'}</td></tr>)}</tbody></table></div>
      </Card>}

      {audit ? <div className="mt-5 space-y-5">
        <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <Metric label="审计发现" value={audit.finding_count} note={`${audit.summary.status_counts.confirmed_issue ?? 0} 项规则确认`} tone="violet" />
          <Metric label="高优先级风险" value={criticalCount} note="CRITICAL + HIGH" tone="red" />
          <Metric label="缺失单元格" value={audit.summary.missing_cells} note={`${audit.summary.row_count} 行真实扫描`} tone="amber" />
          <Metric label="完全重复行" value={audit.summary.duplicate_rows} note="PYTHON COMPUTED" tone="cyan" />
        </section>
        <div className="flex items-center gap-2 rounded-xl border border-success/15 bg-success/[.035] px-4 py-3 text-[10px] text-muted"><ShieldCheck size={15} className="text-success" /><span>Python Deterministic Engine v{audit.engine_version}</span><Badge tone="green">规则结果</Badge><span className="ml-auto font-mono text-[9px]">AI: {audit.ai_status.toUpperCase()} · 未调用 LLM</span></div>
        <AuditCharts summary={audit.summary} />

        <Card padded={false}>
          <div className="flex flex-col gap-4 border-b border-white/[.06] p-5 md:flex-row md:items-center"><div><p className="font-mono text-[9px] uppercase tracking-[.16em] text-primary">Finding register</p><h2 className="mt-1.5 text-sm font-medium text-ink">审计发现与真实记录定位</h2></div><div className="flex gap-2 md:ml-auto"><select aria-label="按严重程度筛选" value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value as 'all' | Severity)} className="field h-9 w-auto py-0 text-[10px]"><option value="all">全部严重程度</option>{Object.entries(severityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><select aria-label="按发现类型筛选" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as 'all' | FindingStatus)} className="field h-9 w-auto py-0 text-[10px]"><option value="all">全部发现类型</option><option value="confirmed_issue">规则确认问题</option><option value="potential_risk">潜在风险</option><option value="suggestion">优化建议</option></select></div></div>
          <div className="p-5"><FindingList findings={filteredFindings} expandedId={expandedId} onToggle={(id) => setExpandedId((current) => current === id ? null : id)} /></div>
          <div className="flex items-center border-t border-white/[.06] px-5 py-4 text-[10px] text-muted"><CheckCircle2 size={14} className="mr-2 text-success" />点击任意发现查看 CSV 行号与原始字段值<span className="ml-auto font-mono text-[9px]">{filteredFindings.length} / {audit.findings.length} FINDINGS</span></div>
        </Card>
      </div> : detail && !detailLoading ? <Card className="mt-5"><div className="flex flex-col items-center py-12 text-center"><ShieldCheck size={32} className="text-primary" /><h2 className="mt-4 text-sm text-ink">数据已就绪，等待确定性审计</h2><p className="mt-2 max-w-lg text-[11px] leading-6 text-muted">确认字段映射后点击“运行审计”。系统不会把类别不平衡、划分比例或特征分布差异直接声称为数据泄漏。</p></div></Card> : null}

      {history.length > 0 && <Card className="mt-5"><SectionHeader title="审计历史" description="每次运行独立持久化，可重新查看完整发现" eyebrow="Audit ledger" action={<Button size="sm" onClick={() => downloadReport('json')} disabled={!audit} icon={<Download size={12} />}>导出当前 JSON</Button>} /><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{history.map((item) => <button data-testid="audit-history" key={item.id} onClick={() => void openHistory(item.id)} className={`rounded-xl border p-4 text-left transition ${audit?.id === item.id ? 'border-primary/25 bg-primary/[.055]' : 'border-white/[.06] hover:bg-white/[.025]'}`}><div className="flex items-center"><History size={14} className="text-primary" /><span className="ml-2 font-mono text-[10px] text-ink">{item.id}</span><Badge tone="green" className="ml-auto">{item.status}</Badge></div><p className="mt-3 text-[10px] text-muted">{new Date(item.created_at).toLocaleString('zh-CN')}</p><p className="mt-1 font-mono text-[9px] text-muted">{item.finding_count} FINDINGS · {item.summary.row_count} ROWS</p></button>)}</div></Card>}
      {toast && <Toast message={toast} onClose={closeToast} />}
    </div>
  )
}

function MappingSelect({ label, value, columns, onChange, allowEmpty = false }: { label: string; value: string; columns: string[]; onChange: (value: string) => void; allowEmpty?: boolean }) {
  return <label className="block"><span className="mb-2 block font-mono text-[9px] text-muted">{label}</span><select value={value} onChange={(event) => onChange(event.target.value)} className="field h-10 py-0 text-[11px]">{allowEmpty && <option value="">不启用实体级检测</option>}{!allowEmpty && !value && <option value="">请选择字段</option>}{columns.map((column) => <option key={column} value={column}>{column}</option>)}</select></label>
}

function Metric({ label, value, note, tone }: { label: string; value: number; note: string; tone: 'violet' | 'red' | 'amber' | 'cyan' }) {
  const tones: Record<typeof tone, BadgeTone> = { violet: 'violet', red: 'red', amber: 'amber', cyan: 'cyan' }
  return <Card className="p-4"><div className="flex items-center justify-between"><p className="text-[10px] text-muted">{label}</p><Badge tone={tones[tone]}>{note}</Badge></div><p className="metric-number mt-3 font-display text-2xl font-semibold tracking-[-.035em] text-ink">{value}</p>{tone === 'red' && value > 0 && <AlertTriangle size={14} className="mt-2 text-danger" />}</Card>
}
