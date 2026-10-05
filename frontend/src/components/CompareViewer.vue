<script setup>
import { ref, watch } from 'vue'
import { Columns2, Layers3, MoveHorizontal } from 'lucide-vue-next'

const props = defineProps({ beforeUrl: String, afterUrl: String, overlayUrl: String })
const position = ref(50)
const mode = ref('after')
const frameAspectRatio = ref('16 / 9')

function updateAspectRatio(event) {
  const { naturalWidth, naturalHeight } = event.currentTarget
  if (naturalWidth && naturalHeight) {
    frameAspectRatio.value = `${naturalWidth} / ${naturalHeight}`
  }
}

watch(() => [props.beforeUrl, props.afterUrl], () => {
  position.value = 50
  mode.value = 'after'
})
</script>

<template>
  <div class="viewer-shell">
    <div class="viewer-toolbar">
      <div class="segmented" aria-label="对比图层">
        <button type="button" :class="{ active: mode === 'after' }" @click="mode = 'after'">
          <Columns2 :size="14" />时相对比
        </button>
        <button type="button" :class="{ active: mode === 'overlay' }" @click="mode = 'overlay'">
          <Layers3 :size="14" />变化叠加
        </button>
      </div>
      <span class="viewer-position"><MoveHorizontal :size="14" />分割位置 <strong>{{ position }}%</strong></span>
    </div>

    <div class="compare-frame" :style="{ aspectRatio: frameAspectRatio }">
      <img :src="mode === 'after' ? afterUrl : overlayUrl" alt="后时相或变化叠加图" @load="updateAspectRatio" />
      <div class="before-layer" :style="{ clipPath: `inset(0 ${100 - position}% 0 0)` }">
        <img :src="beforeUrl" alt="前时相遥感图" />
      </div>
      <div class="divider" :style="{ left: `${position}%` }"><span><MoveHorizontal :size="15" /></span></div>
      <span class="image-label before"><i />T1 前时相</span>
      <span class="image-label after"><i />{{ mode === 'after' ? 'T2 后时相' : '变化叠加图' }}</span>
      <input v-model="position" type="range" min="0" max="100" aria-label="调整时相对比位置" />
    </div>
  </div>
</template>
