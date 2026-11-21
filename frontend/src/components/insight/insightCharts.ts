import type { EChartsOption } from 'echarts'
import type { ComparisonResult, InsightContent } from '../../types/experiment'

const axisStyle = {
  axisLine: { lineStyle: { color: '#2A354B' } },
  axisTick: { show: false },
  axisLabel: { color: '#77859D', fontSize: 10, fontFamily: 'IBM Plex Mono' },
  splitLine: { lineStyle: { color: 'rgba(255,255,255,.045)' } },
}
const tooltipStyle = { backgroundColor: '#1A2438', borderColor: '#34415A', textStyle: { color: '#E8EDF6', fontSize: 11 } }
const palette = ['#8B5CF6', '#22D3EE', '#34D399', '#FBBF24', '#F472B6', '#60A5FA']

const pct = (v: number | null | undefined) => (v == null ? '-' : `${(v * 100).toFixed(2)}%`)

export function macroF1BarOption(comparison: ComparisonResult): EChartsOption {
  const rows = comparison.metric_comparison
  const methods = rows.map((r) => r.method)
  const values = rows.map((r) => {
    const cell = r.macro_f1 as { mean: number | null } | undefined
    return cell?.mean ?? null
  })
  return {
    animationDuration: 500,
    color: ['#8B5CF6'],
    tooltip: { trigger: 'axis', ...tooltipStyle, valueFormatter: (v: unknown) => pct(v as number) },
    grid: { left: 96, right: 40, top: 16, bottom: 24 },
    xAxis: { type: 'value', min: 0, max: 1, ...axisStyle },
    yAxis: { type: 'category', data: methods, ...axisStyle },
    series: [
      {
        type: 'bar',
        data: values,
        barWidth: 18,
        itemStyle: { color: '#8B5CF6', borderRadius: [0, 6, 6, 0] },
        label: { show: true, position: 'right', color: '#C7D0DF', fontFamily: 'IBM Plex Mono', fontSize: 10, formatter: (p: any) => pct(p.value) },
      },
    ],
  }
}

export function accuracyBarOption(comparison: ComparisonResult): EChartsOption {
  const rows = comparison.metric_comparison
  return {
    animationDuration: 500,
    color: ['#22D3EE'],
    tooltip: { trigger: 'axis', ...tooltipStyle, valueFormatter: (v: unknown) => pct(v as number) },
    grid: { left: 44, right: 16, top: 16, bottom: 36 },
    xAxis: { type: 'category', data: rows.map((r) => r.method), ...axisStyle, axisLabel: { ...axisStyle.axisLabel, interval: 0, rotate: 18 } },
    yAxis: { type: 'value', min: 0, max: 1, ...axisStyle },
    series: [
      {
        type: 'bar',
        data: rows.map((r) => (r.accuracy as { mean: number | null } | undefined)?.mean ?? null),
        barWidth: 28,
        itemStyle: { color: '#22D3EE', borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', color: '#C7D0DF', fontFamily: 'IBM Plex Mono', fontSize: 10, formatter: (p: any) => pct(p.value) },
      },
    ],
  }
}

export function perClassF1Option(comparison: ComparisonResult): EChartsOption {
  const classes = comparison.per_class.classes
  const methods = comparison.methods
  return {
    animationDuration: 500,
    color: palette,
    tooltip: { trigger: 'axis', ...tooltipStyle, valueFormatter: (v: unknown) => pct(v as number) },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 3, textStyle: { color: '#8C99B2', fontSize: 10 } },
    grid: { left: 44, right: 16, top: 34, bottom: 32 },
    xAxis: { type: 'category', data: classes, ...axisStyle },
    yAxis: { type: 'value', min: 0, max: 1, ...axisStyle },
    series: methods.map((method) => ({
      name: method,
      type: 'bar',
      data: classes.map((c) => comparison.per_class.by_method[method]?.[c]?.f1 ?? null),
      barWidth: Math.max(6, 44 / methods.length),
      itemStyle: { borderRadius: [4, 4, 0, 0] },
    })),
  }
}

export function confusionHeatmapOption(matrix: number[][] | null, labels: string[]): EChartsOption {
  if (!matrix || !matrix.length) {
    return { title: { text: '该方法无可用混淆矩阵', left: 'center', top: 'middle', textStyle: { color: '#77859D', fontSize: 11 } } }
  }
  const data: Array<[number, number, number]> = []
  let max = 0
  for (let i = 0; i < matrix.length; i++) {
    for (let j = 0; j < matrix[i].length; j++) {
      data.push([j, i, matrix[i][j]])
      max = Math.max(max, matrix[i][j])
    }
  }
  return {
    animationDuration: 400,
    tooltip: { position: 'top', ...tooltipStyle, formatter: (p: any) => `真实=${labels[p.data[1]]} / 预测=${labels[p.data[0]]}：${p.data[2]}` },
    grid: { left: 56, right: 16, top: 16, bottom: 44 },
    xAxis: { type: 'category', data: labels, ...axisStyle, name: '预测', nameTextStyle: { color: '#77859D', fontSize: 9 } },
    yAxis: { type: 'category', data: labels, ...axisStyle, name: '真实', nameTextStyle: { color: '#77859D', fontSize: 9 } },
    visualMap: { min: 0, max, calculable: true, orient: 'vertical', right: 4, top: 'center', inRange: { color: ['#1E293B', '#8B5CF6', '#22D3EE'] }, textStyle: { color: '#77859D', fontSize: 9 } },
    series: [{ type: 'heatmap', data, label: { show: true, color: '#E8EDF6', fontSize: 9, fontFamily: 'IBM Plex Mono' }, emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,.5)' } } }],
  }
}

export function stabilityErrorBarOption(stability: InsightContent['stability_analysis'], metric = 'macro_f1'): EChartsOption {
  const groups = stability.groups.filter((g) => g.metrics[metric]?.confidence_interval)
  const names = groups.map((g) => g.method)
  const means = groups.map((g) => g.metrics[metric].mean)
  const barData = groups.map((g, i) => {
    const ci = g.metrics[metric].confidence_interval!
    return [i, ci.lower, ci.upper, g.metrics[metric].mean]
  })
  return {
    animationDuration: 500,
    color: ['#8B5CF6', '#22D3EE'],
    tooltip: { trigger: 'axis', ...tooltipStyle },
    grid: { left: 44, right: 16, top: 16, bottom: 36 },
    xAxis: { type: 'category', data: names, ...axisStyle, axisLabel: { ...axisStyle.axisLabel, interval: 0, rotate: 16 } },
    yAxis: { type: 'value', min: 0, max: 1, ...axisStyle },
    series: [
      {
        name: `${metric} 均值`,
        type: 'bar',
        data: means,
        barWidth: 22,
        itemStyle: { color: '#8B5CF6', borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', color: '#C7D0DF', fontFamily: 'IBM Plex Mono', fontSize: 9, formatter: (p: any) => pct(p.value) },
      },
      {
        name: '95% CI',
        type: 'custom',
        data: barData,
        renderItem: (_params: unknown, api: any) => {
          const idx = api.value(0) as number
          const lo = api.value(1) as number
          const hi = api.value(2) as number
          const x = api.coord([idx, 0])[0] as number
          const yHi = api.coord([0, hi])[1] as number
          const yLo = api.coord([0, lo])[1] as number
          return {
            type: 'group',
            children: [
              { type: 'line', shape: { x1: x, y1: yHi, x2: x, y2: yLo }, style: { stroke: '#22D3EE', lineWidth: 2 } },
              { type: 'line', shape: { x1: x - 6, y1: yHi, x2: x + 6, y2: yHi }, style: { stroke: '#22D3EE', lineWidth: 2 } },
              { type: 'line', shape: { x1: x - 6, y1: yLo, x2: x + 6, y2: yLo }, style: { stroke: '#22D3EE', lineWidth: 2 } },
            ],
          }
        },
      },
    ],
  }
}

export function seedTrendOption(records: Array<{ method: string; seed: string | null; macro_f1: number | null }>): EChartsOption {
  const seeds = Array.from(new Set(records.map((r) => r.seed).filter((s): s is string => !!s))).sort()
  const methods = Array.from(new Set(records.map((r) => r.method)))
  const series = methods.map((method, mIdx) => ({
    name: method,
    type: 'line',
    data: seeds.map((seed) => {
      const rec = records.find((r) => r.method === method && r.seed === seed)
      return rec?.macro_f1 ?? null
    }),
    smooth: true,
    symbol: 'circle',
    symbolSize: 7,
    lineStyle: { width: 2 },
    itemStyle: { color: palette[mIdx % palette.length] },
  })) as any[]
  return {
    animationDuration: 500,
    color: palette,
    tooltip: { trigger: 'axis', ...tooltipStyle, valueFormatter: (v: unknown) => pct(v as number) },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 3, textStyle: { color: '#8C99B2', fontSize: 10 } },
    grid: { left: 44, right: 16, top: 34, bottom: 32 },
    xAxis: { type: 'category', data: seeds.map((s) => `seed ${s}`), ...axisStyle },
    yAxis: { type: 'value', min: 0, max: 1, ...axisStyle },
    series,
  }
}
