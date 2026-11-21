import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { BarChart3, BrainCircuit, CheckCircle2, Database, Download, FlaskConical, Layers, Play, Plus, ShieldAlert, Sparkles, UploadCloud, X } from 'lucide-react'
import type { EChartsOption } from 'echarts'
import { EChart } from '../components/charts/EChart'
import { accuracyBarOption, confusionHeatmapOption, macroF1BarOption, perClassF1Option, seedTrendOption, stabilityErrorBarOption } from '../components/insight/insightCharts'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, SectionHeader } from '../components/ui/Card'
import { Modal } from '../components/ui/Modal'
import { PageHeader } from '../components/ui/PageHeader'
import { Toast } from '../components/ui/Toast'
import { analyzeExperiments, compareExperiments, comparisonMetricCell, confirmImport, exportInsight, listDatasetOptions, listExperiments, listProtocolOptions, previewImportFile, previewImportJson, seedDemoExperiments } from '../lib/experiments'
import type { ComparisonOut, ExperimentRecord, ImportPreviewResponse, InsightOut } from '../types/experiment'

const claimTone: Record<string, BadgeTone> = {
  observed_fact: 'green',
  statistical_finding: 'cyan',
  hypothesis: 'amber',
  recommendation: 'violet',
}
const claimLabel: Record<string, string> = { observed_fact: '实验事实', statistical_finding: '统计发现', hypothesis: '待验假设', recommendation: '下一步建议' }
const severityTone: Record<string, BadgeTone> = { critical: 'red', high: 'red', medium: 'amber', low: 'blue', info: 'neutral' }
const sourceTone: Record<string, BadgeTone> = { real: 'green', simulated: 'amber', test: 'amber', unknown: 'neutral' }
const sourceLabel: Record<string, string> = { real: '声明真实', simulated: '模拟', test: '测试', unknown: '来源未知' }

export function ExperimentInsight() {
  const [records, setRecords] = useState<ExperimentRecord[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null)
  const [metricsScale, setMetricsScale] = useState<'' | 'percent' | 'fraction'>('')
  const [sourceScope, setSourceScope] = useState<'research' | 'demo' | 'all'>('research')
  const [comparison, setComparison] = useState<ComparisonOut | null>(null)
  const [insight, setInsight] = useState<InsightOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [comparing, setComparing] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [manualText, setManualText] = useState('')
  const [protocolOptions, setProtocolOptions] = useState<Array<{ id: string; name: string }>>([])
  const [datasetOptions, setDatasetOptions] = useState<Array<{ id: string; filename: string }>>([])
  const [protocolId, setProtocolId] = useState('')
  const [datasetId, setDatasetId] = useState('')
  const [confusionMethod, setConfusionMethod] = useState<string>('')
  const [toast, setToast] = useState<string | null>(null)
  const [expandedClaim, setExpandedClaim] = useState<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const refreshRequestRef = useRef(0)

  const refresh = useCallback(async () => {
    const requestId = ++refreshRequestRef.current
    setLoading(true)
    try {
      const [list, protocols, datasets] = await Promise.all([listExperiments(undefined, undefined, sourceScope), listProtocolOptions(), listDatasetOptions()])
      if (requestId !== refreshRequestRef.current) return
      setRecords(list.items)
      setProtocolOptions(protocols)
      setDatasetOptions(datasets)
    } catch (error) {
      if (requestId === refreshRequestRef.current) setToast(error instanceof Error ? error.message : '实验记录加载失败')
    } finally {
      if (requestId === refreshRequestRef.current) setLoading(false)
    }
  }, [sourceScope])

  useEffect(() => {
    void refresh()
    return () => { refreshRequestRef.current += 1 }
  }, [refresh])

  const closeToast = useCallback(() => setToast(null), [])
  const notify = useCallback((message: string) => setToast(message), [])

  const handleFile = async (file: File) => {
    try {
      const result = await previewImportFile(file)
      setMetricsScale('')
      setPreview(result)
      notify(`预览解析完成：${result.row_count} 行，错误 ${result.errors.length} 条`)
    } catch (error) {
      notify(error instanceof Error ? error.message : '预览失败')
    }
  }

  const handleManualPreview = async () => {
    try {
      const parsed = JSON.parse(manualText)
      const records = Array.isArray(parsed) ? parsed : parsed?.records
      if (!Array.isArray(records)) throw new Error('请输入记录数组或包含 records 的对象')
      const result = await previewImportJson(records)
      setMetricsScale('')
      setPreview(result)
      setManualOpen(false)
      notify(`预览解析完成：${result.row_count} 行，错误 ${result.errors.length} 条`)
    } catch (error) {
      notify(error instanceof Error ? error.message : 'JSON 解析失败')
    }
  }

  const confirmPreview = async () => {
    if (!preview || !previewCanConfirm) return
    try {
      await confirmImport({
        records: preview.records as unknown as Array<Record<string, unknown>>,
        source_format: preview.source_format,
        metrics_scale: metricsScale || null,
        data_source: 'unknown',
      })
      setPreview(null)
      setMetricsScale('')
      await refresh()
      notify(`已导入 ${preview.row_count} 条实验记录；未声明真实来源，标记为未知`)
    } catch (error) {
      notify(error instanceof Error ? error.message : '导入失败')
    }
  }

  const loadDemo = async () => {
    try {
      await seedDemoExperiments()
      if (sourceScope === 'demo') await refresh()
      else setSourceScope('demo')
      notify('已载入 ECG 六分类模拟演示数据（标记为模拟，不纳入默认科研统计）')
    } catch (error) {
      notify(error instanceof Error ? error.message : '载入演示数据失败')
    }
  }

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const selectAll = () => setSelected(new Set(records.map((r) => r.id)))
  const clearSelection = () => setSelected(new Set())

  const runCompare = async () => {
    if (selected.size < 2) {
      notify('请至少选择 2 条实验记录进行对比')
      return
    }
    setComparing(true)
    try {
      const result = await compareExperiments([...selected])
      setComparison(result)
      setConfusionMethod(result.result.baseline || result.result.methods[0] || '')
      notify('实验对比完成')
    } catch (error) {
      notify(error instanceof Error ? error.message : '对比失败')
    } finally {
      setComparing(false)
    }
  }

  const runAnalyze = async () => {
    if (selected.size < 1) {
      notify('请至少选择 1 条实验记录生成洞察')
      return
    }
    setAnalyzing(true)
    try {
      const result = await analyzeExperiments({
        experiment_ids: [...selected],
        protocol_id: protocolId || null,
        dataset_ref_id: datasetId || null,
        use_llm: false,
      })
      setInsight(result)
      notify('AI 洞察生成完成（确定性引擎，未编造指标）')
    } catch (error) {
      notify(error instanceof Error ? error.message : '洞察生成失败')
    } finally {
      setAnalyzing(false)
    }
  }

  const selectedRecords = useMemo(() => records.filter((r) => selected.has(r.id)), [records, selected])
  const simulatedCount = records.filter((r) => r.is_simulated || r.data_source === 'test').length
  const methodCount = new Set(records.map((r) => r.method)).size
  const datasetCount = new Set(records.map((r) => r.dataset)).size

  const macroF1Option = useMemo<EChartsOption | null>(() => (comparison ? macroF1BarOption(comparison.result) : null), [comparison])
  const accuracyOption = useMemo<EChartsOption | null>(() => (comparison ? accuracyBarOption(comparison.result) : null), [comparison])
  const perClassOption = useMemo<EChartsOption | null>(() => (comparison ? perClassF1Option(comparison.result) : null), [comparison])
  const trendOption = useMemo<EChartsOption>(() => seedTrendOption(selectedRecords.map((r) => ({ method: r.method, seed: r.seed, macro_f1: r.macro_f1 }))), [selectedRecords])
  const confusionOption = useMemo<EChartsOption | null>(() => {
    if (!comparison) return null
    const matrix = comparison.result.confusion.matrices[confusionMethod] || null
    return confusionHeatmapOption(matrix, comparison.result.confusion.labels[confusionMethod] || [])
  }, [comparison, confusionMethod])
  const stabilityOption = useMemo<EChartsOption | null>(() => (insight ? stabilityErrorBarOption(insight.content.stability_analysis) : null), [insight])
  const previewCanConfirm = Boolean(preview && (
    preview.ok || (
      preview.errors.length > 0
      && preview.errors.every((item) => item.code === 'metrics_scale_confirmation_required')
      && metricsScale
    )
  ))

  return (
    <div>
      <PageHeader
        eyebrow="Experiment insight / Deterministic metrics"
        title="把多组实验，读成可复核的结论。"
        description="导入 CSV/JSON/手动录入，由 Python 确定性引擎完成对比、稳定性、消融与数据质量联动；AI 只解释，不编造指标。"
        actions={
          <>
            <Button onClick={loadDemo} icon={<Sparkles size={15} />} data-testid="load-demo">
              载入演示数据
            </Button>
            <Button onClick={() => fileInputRef.current?.click()} icon={<UploadCloud size={15} />} data-testid="upload-experiment">
              上传 CSV/JSON
            </Button>
            <Button onClick={() => setManualOpen(true)} icon={<Plus size={15} />} variant="ghost" data-testid="manual-entry">
              手动录入
            </Button>
            <input ref={fileInputRef} type="file" accept=".csv,.json" className="hidden" onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
          </>
        }
      />

      <section className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Metric label="实验记录" value={String(records.length)} note="RECORDS PERSISTED" icon={<Database size={18} />} />
        <Metric label="方法数" value={String(methodCount)} note="METHODS" icon={<Layers size={18} />} />
        <Metric label="数据集" value={String(datasetCount)} note="DATASETS" icon={<BarChart3 size={18} />} />
        <Metric label="模拟 / 测试" value={String(simulatedCount)} note={simulatedCount ? 'DEMO · EXCLUDED BY DEFAULT' : 'NO DEMO DATA'} icon={<FlaskConical size={18} />} accent={simulatedCount ? 'warning' : 'success'} />
      </section>

      {preview && (
        <Card className="mb-5" data-testid="import-preview">
          <SectionHeader
            title="导入预览与校验"
            description={`来源：${preview.source_format} · 共 ${preview.row_count} 行 · 确定性引擎解析`}
            eyebrow="Import preview"
            action={
              <div className="flex items-center gap-2">
                <Badge tone={preview.ok ? 'green' : 'red'} dot>{preview.ok ? '校验通过' : '存在错误'}</Badge>
                <Button onClick={confirmPreview} disabled={!previewCanConfirm} icon={<CheckCircle2 size={15} />} data-testid="confirm-import">
                  确认导入
                </Button>
                <Button onClick={() => setPreview(null)} variant="ghost" icon={<X size={15} />}>关闭</Button>
              </div>
            }
          />
          {preview.errors.some((item) => item.code === 'metrics_scale_confirmation_required') && (
            <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-warning/20 bg-warning/[.05] p-3 text-[10px] text-warning">
              <span>指标值 1 的单位不明确，请明确选择后再导入：</span>
              <select value={metricsScale} onChange={(event) => setMetricsScale(event.target.value as 'percent' | 'fraction')} className="field h-8 w-auto py-0 text-[10px]" aria-label="确认指标单位">
                <option value="">请选择单位</option>
                <option value="fraction">比例（1.0 = 100%）</option>
                <option value="percent">百分数（1 = 1%）</option>
              </select>
            </div>
          )}
          {preview.warnings.length > 0 && (
            <div className="mb-3 rounded-xl border border-warning/20 bg-warning/[.05] p-3">
              <p className="text-[10px] font-medium text-warning">警告 {preview.warnings.length} 条</p>
              <ul className="mt-1.5 space-y-1 text-[10px] leading-5 text-[#B9C4D5]">{preview.warnings.slice(0, 8).map((w, i) => <li key={i}>[{w.code}] {w.message}</li>)}</ul>
            </div>
          )}
          {preview.errors.length > 0 && (
            <div className="mb-3 rounded-xl border border-danger/20 bg-danger/[.06] p-3">
              <p className="text-[10px] font-medium text-danger">错误 {preview.errors.length} 条（无法导入）</p>
              <ul className="mt-1.5 space-y-1 text-[10px] leading-5 text-[#D7B4B4]">{preview.errors.map((w, i) => <li key={i}>[{w.code}] {w.message}</li>)}</ul>
            </div>
          )}
          <div className="overflow-x-auto rounded-xl border border-white/[.06]">
            <table className="w-full min-w-[760px] text-left">
              <thead><tr className="bg-canvas/60 font-mono text-[9px] uppercase text-muted">{['实验ID', '方法', '模型', '数据集', 'Seed', 'Accuracy', 'Macro-F1', '口径'].map((h) => <th key={h} className="px-3 py-2.5 font-normal">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-white/[.05]">
                {preview.preview.map((row, i) => (
                  <tr key={i} className="text-[10px] text-[#B9C4D5]">
                    <td className="px-3 py-2 font-mono text-accent">{String(row.experiment_id)}</td>
                    <td className="px-3 py-2">{String(row.method)}</td>
                    <td className="px-3 py-2">{String(row.model_name || '—')}</td>
                    <td className="px-3 py-2">{String(row.dataset)}</td>
                    <td className="px-3 py-2 font-mono">{String(row.seed || '—')}</td>
                    <td className="px-3 py-2 font-mono">{row.accuracy == null ? '—' : String(row.accuracy)}</td>
                    <td className="px-3 py-2 font-mono">{row.macro_f1 == null ? '—' : String(row.macro_f1)}</td>
                    <td className="px-3 py-2 font-mono text-[9px]">{String(row.original_metrics_scale || 'unknown')} → {String(row.metrics_scale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card className="mb-5" padded={false} data-testid="experiment-records">
        <div className="flex flex-wrap items-center justify-between gap-3 p-5">
          <SectionHeader
            title="实验记录"
            description="默认排除明确模拟/测试数据；未知来源不自动视为真实"
            eyebrow="Experiment ledger"
            action={
              <select
                value={sourceScope}
                onChange={(event) => {
                  setSourceScope(event.target.value as 'research' | 'demo' | 'all')
                  setSelected(new Set())
                  setComparison(null)
                  setInsight(null)
                }}
                className="field h-9 w-auto py-0 text-[10px]"
                aria-label="数据来源筛选"
              >
                <option value="research">科研记录（排除模拟/测试）</option>
                <option value="demo">演示与测试记录</option>
                <option value="all">全部记录</option>
              </select>
            }
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={selectAll} variant="ghost" size="sm">全选</Button>
            <Button onClick={clearSelection} variant="ghost" size="sm">清空</Button>
            <Button onClick={runCompare} disabled={comparing || selected.size < 2} icon={<Play size={14} />} data-testid="run-compare">{comparing ? '对比中…' : '运行对比'}</Button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left">
            <thead><tr className="border-y border-white/[.055] bg-canvas/30 font-mono text-[9px] uppercase tracking-wide text-muted">{['', '方法', '数据集', 'Seed', 'Acc', 'Macro-F1', 'Weighted-F1', '来源', '标记'].map((h) => <th key={h} className="px-4 py-3 font-normal">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-white/[.05]">
              {records.map((record) => (
                <tr key={record.id} className={selected.has(record.id) ? 'bg-primary/[.05]' : ''}>
                  <td className="px-4 py-3"><input type="checkbox" checked={selected.has(record.id)} onChange={() => toggle(record.id)} className="h-4 w-4 accent-violet-500" aria-label={`选择 ${record.experiment_id}`} /></td>
                  <td className="px-4 py-3"><span className="text-[11px] text-[#C8D1DF]">{record.method}</span><span className="mt-0.5 block font-mono text-[9px] text-muted">{record.model_name || '—'}</span></td>
                  <td className="px-4 py-3 text-[10px] text-[#B9C4D5]">{record.dataset}</td>
                  <td className="px-4 py-3 font-mono text-[10px] text-accent">{record.seed || '—'}</td>
                  <td className="px-4 py-3 font-mono text-[10px]">{record.accuracy?.toFixed(4) ?? '—'}</td>
                  <td className="px-4 py-3 font-mono text-[10px]">{record.macro_f1?.toFixed(4) ?? '—'}</td>
                  <td className="px-4 py-3 font-mono text-[10px]">{record.weighted_f1?.toFixed(4) ?? '—'}</td>
                  <td className="px-4 py-3 font-mono text-[9px] text-muted">{record.source_format}</td>
                  <td className="px-4 py-3"><Badge tone={sourceTone[record.data_source] || 'neutral'} dot>{sourceLabel[record.data_source] || '来源未知'}</Badge></td>
                </tr>
              ))}
              {records.length === 0 && <tr><td colSpan={9} className="px-4 py-10 text-center text-xs text-muted">{loading ? '加载中…' : '暂无实验记录，可上传文件或载入演示数据'}</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between px-4 py-3 font-mono text-[9px] text-muted"><span>{records.length} RECORDS · DETERMINISTIC ENGINE</span><span>已选 {selected.size} 条</span></div>
      </Card>

      {comparison && (
        <section className="mb-5" data-testid="comparison-panel">
          <Card className="mb-5">
            <SectionHeader title="实验组对比" description={`baseline = ${comparison.result.baseline} · 主指标 ${comparison.result.primary_metric} · 汇总值由 Python 计算`} eyebrow="Comparison" action={<Badge tone={comparison.result.comparability.status === 'incompatible' ? 'red' : 'amber'} dot>{comparison.result.comparability.status === 'incompatible' ? '不可混合排名' : '可比性未核实'}</Badge>} />
            <div className="mb-3 rounded-xl border border-warning/20 bg-warning/[.04] px-3 py-2 text-[10px] leading-5 text-[#B9C4D5]">
              {comparison.result.comparability.reasons.map((reason) => <p key={reason}>{reason}</p>)}
              <p>{comparison.result.comparability.note}</p>
            </div>
            <div className="overflow-x-auto rounded-xl border border-white/[.06]">
              <table className="w-full min-w-[720px] text-left">
                <thead><tr className="bg-canvas/60 font-mono text-[9px] uppercase text-muted">{['方法', 'Accuracy', 'Macro-F1', 'Weighted-F1', 'Precision', 'Recall'].map((h) => <th key={h} className="px-3 py-2.5 font-normal">{h}</th>)}</tr></thead>
                <tbody className="divide-y divide-white/[.05]">
                  {comparison.result.metric_comparison.map((row) => (
                    <tr key={row.method} className="text-[10px]">
                      <td className="px-3 py-2.5"><span className="text-[#D0D9E6]">{row.method}</span>{row.is_baseline && <Badge tone="violet" className="ml-2">baseline</Badge>}</td>
                      {['accuracy', 'macro_f1', 'weighted_f1', 'precision', 'recall'].map((metric) => {
                        const cell = comparisonMetricCell(row, metric)
                        return <td key={metric} className="px-3 py-2.5 font-mono"><span className="text-[#C8D1DF]">{cell.mean?.toFixed(4) ?? '—'}</span>{cell.delta_vs_baseline_pp != null && !row.is_baseline && <span className={`ml-1.5 text-[9px] ${cell.delta_vs_baseline_pp >= 0 ? 'text-success' : 'text-danger'}`}>{cell.delta_vs_baseline_pp >= 0 ? '+' : ''}{cell.delta_vs_baseline_pp.toFixed(2)}pp</span>}</td>
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="font-mono text-[9px] uppercase text-muted">排名：</span>
              {comparison.result.rankings.map((r) => <Badge key={r.method} tone="neutral">#{r.rank} {r.method} {r.value.toFixed(4)}</Badge>)}
              {comparison.result.rankings.length === 0 && <span className="text-[10px] text-danger">已禁止混合排名，仅保留描述性指标。</span>}
            </div>
          </Card>
          <div className="grid grid-cols-12 gap-5">
            <Card className="col-span-12 lg:col-span-6"><SectionHeader title="逐 run 导入 Macro-F1 均值" eyebrow="Macro-F1 · run-level mean" /><EChart option={macroF1Option!} className="h-[300px] w-full" label="Macro-F1横向对比图" /></Card>
            <Card className="col-span-12 lg:col-span-6"><SectionHeader title="Accuracy 对比" eyebrow="Accuracy" /><EChart option={accuracyOption!} className="h-[300px] w-full" label="Accuracy对比图" /></Card>
            <Card className="col-span-12 lg:col-span-7"><SectionHeader title="类别级 F1 对比" eyebrow="Per-class F1" /><EChart option={perClassOption!} className="h-[320px] w-full" label="类别级F1对比图" /></Card>
            <Card className="col-span-12 lg:col-span-5">
              <SectionHeader title="混淆矩阵" eyebrow="Confusion matrix" action={<select value={confusionMethod} onChange={(e) => setConfusionMethod(e.target.value)} className="field h-8 w-auto py-0 text-[10px]" aria-label="选择方法">{comparison.result.methods.map((m) => <option key={m} value={m}>{m}</option>)}</select>} />
              <EChart option={confusionOption!} className="h-[320px] w-full" label="混淆矩阵热力图" />
              <p className="mt-2 font-mono text-[9px] leading-4 text-muted">汇总矩阵 Macro-F1：{comparison.result.confusion.macro_f1_from_confusion[confusionMethod]?.toFixed(6) ?? '—'}；与逐 run 均值口径不混用。</p>
            </Card>
            <Card className="col-span-12"><SectionHeader title="随机种子指标趋势" description={`已选 ${selectedRecords.length} 条记录的 Macro-F1 随种子变化`} eyebrow="Seed trend" /><EChart option={trendOption} className="h-[300px] w-full" label="随机种子趋势图" /></Card>
          </div>
        </section>
      )}

      <Card className="mb-5">
        <SectionHeader
          title="生成科研洞察"
          description="可选关联已有 Protocol 与 Data Guardian 数据集审计；AI 仅基于真实计算结果解释"
          eyebrow="Insight agent"
          action={
            <div className="flex flex-wrap items-center gap-2">
              <select value={protocolId} onChange={(e) => setProtocolId(e.target.value)} className="field h-9 w-auto py-0 text-[10px]" aria-label="关联协议"><option value="">不关联协议</option>{protocolOptions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
              <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)} className="field h-9 w-auto py-0 text-[10px]" aria-label="关联数据集"><option value="">不关联数据审计</option>{datasetOptions.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}</select>
              <Button onClick={runAnalyze} disabled={analyzing || selected.size < 1} icon={<BrainCircuit size={14} />} data-testid="run-analyze">{analyzing ? '生成中…' : '生成洞察'}</Button>
            </div>
          }
        />
        {insight ? (
          <InsightPanel insight={insight} stabilityOption={stabilityOption!} expanded={expandedClaim} onToggle={setExpandedClaim} />
        ) : (
          <p className="py-10 text-center text-xs text-muted">选择实验记录后点击“生成洞察”，将输出结构化结论、稳定性、消融与数据质量联动。</p>
        )}
      </Card>

      {toast && <Toast message={toast} onClose={closeToast} />}

      <Modal open={manualOpen} onClose={() => setManualOpen(false)} title="手动录入实验记录" description="粘贴 JSON 记录数组（或包含 records 的对象），先预览校验再确认导入" className="max-w-3xl">
        <textarea value={manualText} onChange={(e) => setManualText(e.target.value)} spellCheck={false} placeholder={'[\n  {"experiment_id":"exp_1","method":"Central-BSM","dataset":"ECG","seed":42,"accuracy":0.86,"macro_f1":0.81}\n]'} className="field h-72 w-full font-mono text-[11px]" />
        <div className="mt-3 flex justify-end gap-2">
          <Button onClick={() => setManualOpen(false)} variant="ghost">取消</Button>
          <Button onClick={handleManualPreview} icon={<Sparkles size={14} />}>预览校验</Button>
        </div>
      </Modal>
    </div>
  )
}

function InsightPanel({ insight, stabilityOption, expanded, onToggle }: { insight: InsightOut; stabilityOption: EChartsOption; expanded: number | null; onToggle: (i: number | null) => void }) {
  const content = insight.content
  return (
    <div className="space-y-5" data-testid="insight-panel">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <MiniStat label="结论数" value={String(content.key_observations.length)} icon={<BrainCircuit size={16} />} />
        <MiniStat label="方法" value={content.experimental_summary.methods.join(', ')} icon={<Layers size={16} />} small />
        <MiniStat label="数据质量风险" value={String(content.data_quality_warnings.length)} icon={<ShieldAlert size={16} />} accent={content.data_quality_warnings.length ? 'warning' : 'success'} />
        <MiniStat label="AI 状态" value={insight.ai_status === 'not_used' ? '未启用' : insight.ai_status} icon={<Sparkles size={16} />} accent={insight.ai_status === 'not_used' ? 'success' : 'violet'} />
      </div>

      {content.narrative && <div className="rounded-xl border border-primary/15 bg-primary/[.05] p-4 text-[12px] leading-6 text-[#C7D0DF]"><span className="font-mono text-[9px] uppercase text-primary">AI 叙述</span><p className="mt-1.5">{content.narrative}</p><p className="mt-1 text-[9px] text-muted">{content.ai_note}</p></div>}

      <Card padded={false}>
        <div className="p-5"><SectionHeader title="结构化结论" description="每条结论含 claim / evidence / calculation / confidence / limitation，严格区分事实与假设" eyebrow="Key observations" /></div>
        <div className="space-y-2 px-5 pb-5">
          {content.key_observations.map((claim, i) => (
            <article key={i} className="rounded-xl border border-white/[.06] bg-canvas/25">
              <button onClick={() => onToggle(expanded === i ? null : i)} className="flex w-full items-center gap-3 p-3 text-left">
                <Badge tone={claimTone[claim.claim_type] || 'neutral'}>{claimLabel[claim.claim_type] || claim.claim_type}</Badge>
                <span className="flex-1 text-[12px] text-[#D0D9E6]">{claim.claim}</span>
                <Badge tone={claim.confidence_level === 'high' ? 'green' : claim.confidence_level === 'medium' ? 'cyan' : 'amber'}>{claim.confidence_level}</Badge>
              </button>
              {expanded === i && (
                <div className="border-t border-white/[.06] px-4 py-3 text-[10px] leading-5 text-[#AAB6C9]">
                  <p><span className="text-primary">证据：</span>{claim.evidence}</p>
                  <p className="mt-1"><span className="text-primary">计算：</span>{claim.calculation}</p>
                  <p className="mt-1"><span className="text-warning">局限：</span>{claim.limitation}</p>
                </div>
              )}
            </article>
          ))}
        </div>
      </Card>

      {content.data_quality_warnings.length > 0 && (
        <Card padded={false}>
          <div className="p-5"><SectionHeader title="数据质量风险关联" description="来自 Data Guardian 确定性审计，可追溯到 audit_id 与 finding_id" eyebrow="Data Guardian linkage" /></div>
          <div className="overflow-x-auto px-5 pb-5">
            <table className="w-full min-w-[720px] text-left">
              <thead><tr className="bg-canvas/60 font-mono text-[9px] uppercase text-muted">{['严重度', '规则', '标题', 'audit', 'finding'].map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-white/[.05]">
                {content.data_quality_warnings.map((w, i) => (
                  <tr key={i} className="text-[10px]">
                    <td className="px-3 py-2"><Badge tone={severityTone[w.severity] || 'neutral'}>{w.severity}</Badge></td>
                    <td className="px-3 py-2 font-mono text-[9px] text-muted">{w.rule_id}</td>
                    <td className="px-3 py-2 text-[#C8D1DF]">{w.title}</td>
                    <td className="px-3 py-2 font-mono text-[9px] text-accent">{w.audit_id || '—'}</td>
                    <td className="px-3 py-2 font-mono text-[9px]">{w.finding_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card padded={false}>
        <div className="p-5"><SectionHeader title="多随机种子稳定性" description="均值 ± 95% t 置信区间；n<2 不出区间并提示无法评估" eyebrow="Stability" /></div>
        <div className="px-5 pb-5"><EChart option={stabilityOption} className="h-[300px] w-full" label="多种子稳定性误差棒图" /></div>
        <div className="overflow-x-auto px-5 pb-5">
          <table className="w-full min-w-[760px] text-left">
            <thead><tr className="bg-canvas/60 font-mono text-[9px] uppercase text-muted">{['方法', '独立 n / 记录数', '非重复 seeds', 'Macro-F1 mean', 'std', '95% CI', '可评估'].map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-white/[.05]">
              {content.stability_analysis.groups.map((g) => {
                const m = g.metrics.macro_f1
                return (
                  <tr key={g.method} className="text-[10px]">
                    <td className="px-3 py-2 text-[#C8D1DF]">{g.method}</td>
                    <td className="px-3 py-2 font-mono" title={g.note}>{m?.count ?? 0} / {g.run_count}</td>
                    <td className="px-3 py-2 font-mono text-[9px] text-muted" title={g.note}>{g.seeds.join(', ') || '—'}</td>
                    <td className="px-3 py-2 font-mono">{m?.mean?.toFixed(4) ?? '—'}</td>
                    <td className="px-3 py-2 font-mono">{m?.std?.toFixed(4) ?? '—'}</td>
                    <td className="px-3 py-2 font-mono text-[9px]">{m?.confidence_interval ? `[${m.confidence_interval.lower.toFixed(4)}, ${m.confidence_interval.upper.toFixed(4)}]` : '— (n<2)'}</td>
                    <td className="px-3 py-2"><Badge tone={g.can_assess_stability ? 'green' : 'amber'} dot>{g.can_assess_stability ? '是' : '否'}</Badge></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card padded={false}>
        <div className="p-5"><SectionHeader title="消融实验分析" description={`baseline = ${content.ablation_analysis.baseline} · 含组件开关：${content.ablation_analysis.has_component_flags ? '是' : '否'}`} eyebrow="Ablation" /></div>
        <div className="overflow-x-auto px-5 pb-5">
          <table className="w-full min-w-[720px] text-left">
            <thead><tr className="bg-canvas/60 font-mono text-[9px] uppercase text-muted">{['方法', 'Acc Δpp', 'Macro-F1 Δpp', '配置变化'].map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-white/[.05]">
              {content.ablation_analysis.comparisons.map((a, i) => (
                <tr key={i} className="text-[10px]">
                  <td className="px-3 py-2 text-[#C8D1DF]">{a.method}</td>
                  <td className="px-3 py-2 font-mono">{a.deltas.accuracy ? `${a.deltas.accuracy.delta_pp >= 0 ? '+' : ''}${a.deltas.accuracy.delta_pp.toFixed(2)}` : '—'}</td>
                  <td className="px-3 py-2 font-mono">{a.deltas.macro_f1 ? `${a.deltas.macro_f1.delta_pp >= 0 ? '+' : ''}${a.deltas.macro_f1.delta_pp.toFixed(2)}` : '—'}</td>
                  <td className="px-3 py-2 text-[9px] text-muted">{a.config_changes.join('; ') || '—'}</td>
                </tr>
              ))}
              {content.ablation_analysis.comparisons.length === 0 && <tr><td colSpan={4} className="px-3 py-6 text-center text-[10px] text-muted">仅 baseline，无对比方法</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Card><SectionHeader title="局限性" eyebrow="Limitations" /><ul className="mt-3 space-y-2 text-[11px] leading-6 text-[#AAB6C9]">{content.limitations.map((l, i) => <li key={i}>• {l}</li>)}</ul></Card>
        <Card><SectionHeader title="后续实验建议" eyebrow="Recommendations" /><ul className="mt-3 space-y-2 text-[11px] leading-6 text-[#B9C4D5]">{content.recommendations.map((r, i) => <li key={i}>• {r.message}{r.ai_generated && <Badge tone="violet" className="ml-2">AI</Badge>}</li>)}</ul></Card>
      </div>

      <div className="flex flex-wrap justify-end gap-2">
        <Button onClick={() => exportInsight(insight.id, 'markdown')} icon={<Download size={14} />} data-testid="export-markdown">导出 Markdown</Button>
        <Button onClick={() => exportInsight(insight.id, 'json')} variant="ghost" icon={<Download size={14} />} data-testid="export-json">导出 JSON</Button>
      </div>
    </div>
  )
}

function Metric({ label, value, note, icon, accent = 'violet' }: { label: string; value: string; note: string; icon: ReactNode; accent?: 'violet' | 'warning' | 'success' }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between"><p className="truncate text-[10px] text-muted">{label}</p><span className={accent === 'warning' ? 'text-warning' : accent === 'success' ? 'text-success' : 'text-primary'}>{icon}</span></div>
      <p className="metric-number mt-3 truncate font-display text-2xl font-semibold tracking-[-.035em] text-ink">{value}</p>
      <p className="mt-2 truncate font-mono text-[8px] tracking-wide text-muted">{note}</p>
    </Card>
  )
}

function MiniStat({ label, value, icon, accent = 'violet', small = false }: { label: string; value: string; icon: ReactNode; accent?: 'violet' | 'warning' | 'success'; small?: boolean }) {
  return (
    <Card className="p-3.5">
      <div className="flex items-center justify-between"><p className="text-[9px] uppercase tracking-wide text-muted">{label}</p><span className={accent === 'warning' ? 'text-warning' : accent === 'success' ? 'text-success' : 'text-primary'}>{icon}</span></div>
      <p className={`mt-2 font-mono ${small ? 'text-[10px]' : 'text-lg'} text-[#D0D9E6]`}>{value}</p>
    </Card>
  )
}
