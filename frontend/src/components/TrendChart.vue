<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, BarChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({ items: { type: Array, default: () => [] }, threshold: { type: Number, default: 0.12 } })
const element = ref(null)
let chart
let observer

function render() {
  if (!chart) return
  const items = props.items.slice(-12)
  chart.setOption({
    animationDuration: 650,
    grid: { top: 42, right: 20, bottom: 30, left: 46 },
    legend: { top: 4, right: 6, itemWidth: 12, itemHeight: 7, textStyle: { color: '#737373', fontSize: 9 } },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(33, 33, 33, .94)',
      borderWidth: 0,
      textStyle: { color: '#fff', fontSize: 10 },
      extraCssText: 'backdrop-filter: blur(10px); border-radius: 6px;',
      formatter(params) {
        const item = items[params[0]?.dataIndex]
        if (!item) return ''
        return `${item.before_label} → ${item.after_label}<br/>变化率 ${(item.change_ratio * 100).toFixed(2)}%<br/>变化斑块 ${item.region_count}`
      },
    },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.after_label || item.id.slice(0, 6)),
      axisLine: { lineStyle: { color: '#e5e5e5' } },
      axisTick: { show: false },
      axisLabel: { color: '#737373', fontSize: 9, hideOverlap: true },
    },
    yAxis: [
      {
        type: 'value',
        min: 0,
        axisLabel: { color: '#737373', fontSize: 9, formatter: (value) => `${(value * 100).toFixed(0)}%` },
        splitLine: { lineStyle: { color: '#ececec', type: 'dashed' } },
      },
      { type: 'value', min: 0, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    series: [
      {
        name: '变化率',
        type: 'line',
        data: items.map((item) => item.change_ratio),
        smooth: true,
        symbolSize: 6,
        lineStyle: { width: 3, color: '#10a37f' },
        itemStyle: { color: '#10a37f', borderColor: '#fff', borderWidth: 2 },
        areaStyle: { color: 'rgba(16, 163, 127, .08)' },
        markLine: {
          silent: true,
          symbol: 'none',
          label: { color: '#b57418', fontSize: 8, formatter: '预警线' },
          lineStyle: { color: '#e3a13c', type: 'dashed' },
          data: [{ yAxis: props.threshold }],
        },
      },
      {
        name: '斑块数',
        type: 'bar',
        yAxisIndex: 1,
        data: items.map((item) => item.region_count),
        barMaxWidth: 18,
        itemStyle: { color: '#8aa4d6', borderRadius: [3, 3, 0, 0] },
      },
    ],
  }, true)
}

onMounted(() => {
  chart = echarts.init(element.value)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(element.value)
  render()
})
watch(() => [props.items, props.threshold], render, { deep: true })
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template><div ref="element" class="trend-chart" /></template>
