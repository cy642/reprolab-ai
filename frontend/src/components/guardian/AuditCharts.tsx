import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import { BarChart3, Columns3, PieChart } from 'lucide-react'
import { EChart } from '../charts/EChart'
import { Card, SectionHeader } from '../ui/Card'
import type { AuditSummary } from '../../types/dataset'

const axisStyle = {
  axisLine: { lineStyle: { color: '#2A354B' } },
  axisTick: { show: false },
  axisLabel: { color: '#77859D', fontSize: 10 },
  splitLine: { lineStyle: { color: 'rgba(255,255,255,.045)' } },
}
const tooltipStyle = { backgroundColor: '#1A2438', borderColor: '#34415A', textStyle: { color: '#E8EDF6', fontSize: 11 } }

export function AuditCharts({ summary }: { summary: AuditSummary }) {
  const classOption = useMemo<EChartsOption>(() => {
    const distribution = summary.class_distribution ?? {}
    const overall = distribution.overall ?? []
    const splits = Object.keys(distribution.by_split ?? {})
    return {
      animationDuration: 350,
      color: ['#8B5CF6', '#22D3EE', '#34D399', '#FBBF24'],
      tooltip: { trigger: 'axis', ...tooltipStyle },
      legend: splits.length ? { top: 0, right: 0, textStyle: { color: '#8C99B2', fontSize: 9 } } : undefined,
      grid: { left: 40, right: 12, top: splits.length ? 42 : 24, bottom: 28 },
      xAxis: { type: 'category', data: overall.map((item) => item.label), ...axisStyle },
      yAxis: { type: 'value', ...axisStyle },
      series: splits.length
        ? splits.map((split) => ({
            name: split,
            type: 'bar' as const,
            data: overall.map((item) => distribution.by_split?.[split]?.find((entry) => entry.label === item.label)?.count ?? 0),
            barMaxWidth: 22,
          }))
        : [{ name: '样本数', type: 'bar' as const, data: overall.map((item) => item.count), itemStyle: { color: '#8B5CF6', borderRadius: [5, 5, 0, 0] } }],
    }
  }, [summary.class_distribution])

  const missingOption = useMemo<EChartsOption>(() => {
    const columns = (summary.missing_by_column ?? []).filter((item) => item.missing_count > 0)
    return {
      animationDuration: 350,
      tooltip: { trigger: 'axis', ...tooltipStyle },
      grid: { left: 42, right: 14, top: 24, bottom: 56 },
      xAxis: { type: 'category', data: columns.map((item) => item.column), ...axisStyle, axisLabel: { ...axisStyle.axisLabel, rotate: 28 } },
      yAxis: { type: 'value', max: 100, ...axisStyle, axisLabel: { ...axisStyle.axisLabel, formatter: '{value}%' } },
      series: [{
        type: 'bar',
        data: columns.map((item) => Number((item.missing_rate * 100).toFixed(2))),
        itemStyle: { color: '#FB7185', borderRadius: [5, 5, 0, 0] },
        barMaxWidth: 36,
      }],
    }
  }, [summary.missing_by_column])

  const splitOption = useMemo<EChartsOption>(() => ({
    animationDuration: 350,
    color: ['#8B5CF6', '#22D3EE', '#34D399', '#FBBF24'],
    tooltip: { ...tooltipStyle, formatter: '{b}<br/>{c} 行 · {d}%' },
    legend: { bottom: 0, textStyle: { color: '#8C99B2', fontSize: 10 } },
    series: [{
      type: 'pie',
      radius: ['44%', '70%'],
      center: ['50%', '44%'],
      label: { color: '#C7D0DF', fontSize: 10, formatter: '{b}\n{d}%' },
      data: (summary.split_distribution ?? []).map((item) => ({ name: item.split || 'Missing', value: item.count })),
    }],
  }), [summary.split_distribution])

  return (
    <div className="grid grid-cols-12 gap-5">
      <Card className="col-span-12 xl:col-span-5">
        <SectionHeader title="类别分布" description="按真实标签计数，并比较各数据集划分" eyebrow="Class analyzer" action={<BarChart3 size={16} className="text-primary" />} />
        <EChart option={classOption} className="h-[270px] w-full" label="类别样本数量柱状图" />
      </Card>
      <Card className="col-span-12 md:col-span-6 xl:col-span-4">
        <SectionHeader title="缺失值概览" description="仅展示存在缺失的字段" eyebrow="Missing analyzer" action={<Columns3 size={16} className="text-danger" />} />
        {(summary.missing_by_column ?? []).some((item) => item.missing_count > 0)
          ? <EChart option={missingOption} className="h-[270px] w-full" label="各字段缺失比例柱状图" />
          : <div className="flex h-[270px] items-center justify-center text-xs text-muted">未检测到缺失值</div>}
      </Card>
      <Card className="col-span-12 md:col-span-6 xl:col-span-3">
        <SectionHeader title="数据集划分" description="Train / Validation / Test" eyebrow="Split validator" action={<PieChart size={16} className="text-accent" />} />
        <EChart option={splitOption} className="h-[270px] w-full" label="数据集划分比例环形图" />
      </Card>
    </div>
  )
}
