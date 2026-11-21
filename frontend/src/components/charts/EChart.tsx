import { useEffect, useRef } from 'react'
import { init, use as registerECharts, type EChartsType } from 'echarts/core'
import { BarChart, CustomChart, HeatmapChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'

registerECharts([BarChart, CustomChart, HeatmapChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

export function EChart({ option, className = 'h-72', label }: {
  option: EChartsOption
  className?: string
  label: string
}) {
  const elementRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<EChartsType | null>(null)

  useEffect(() => {
    if (!elementRef.current) return
    const chart = init(elementRef.current)
    chartRef.current = chart
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(elementRef.current)
    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    chartRef.current?.setOption(option, true)
  }, [option])

  return <div ref={elementRef} className={className} role="img" aria-label={label} />
}
