<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({ result: Object })
const element = ref(null)
let chart
const resizeChart = () => chart?.resize()

function render() {
  if (!chart || !props.result) return
  const regions = props.result.regions || []
  chart.setOption({
    animationDuration: 600,
    animationEasing: 'cubicOut',
    grid: { top: 20, right: 12, bottom: 24, left: 48 },
    xAxis: {
      type: 'category',
      data: regions.slice(0, 6).map((region) => `#${region.region_id}`),
      axisLine: { lineStyle: { color: '#cfdce9' } },
      axisTick: { show: false },
      axisLabel: { color: '#6f8399', fontSize: 9 },
    },
    yAxis: {
      type: 'value',
      name: '像素',
      nameTextStyle: { color: '#7b8fa5', fontSize: 9 },
      axisLabel: { color: '#7b8fa5', fontSize: 9 },
      splitLine: { lineStyle: { color: '#e7eef6', type: 'dashed' } },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(19, 42, 71, .88)',
      borderWidth: 0,
      textStyle: { color: '#fff', fontSize: 10 },
      extraCssText: 'backdrop-filter: blur(10px); border-radius: 6px; box-shadow: 0 8px 24px rgba(18, 46, 80, .18);',
    },
    series: [{
      type: 'bar',
      data: regions.slice(0, 6).map((region) => ({
        value: region.area_pixels,
        itemStyle: {
          color: region.risk_level === 'high' ? '#e15b64' : region.risk_level === 'medium' ? '#e5a13d' : '#2784ea',
          borderRadius: [4, 4, 0, 0],
        },
      })),
      barMaxWidth: 28,
      emphasis: { itemStyle: { shadowBlur: 12, shadowColor: 'rgba(23, 105, 232, .22)' } },
    }],
  })
}

onMounted(() => {
  chart = echarts.init(element.value)
  render()
  window.addEventListener('resize', resizeChart)
})
watch(() => props.result, render, { deep: true })
onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
})
</script>

<template><div ref="element" class="risk-chart" /></template>
