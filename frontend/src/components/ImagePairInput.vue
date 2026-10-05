<script setup>
import { computed, ref } from 'vue'
import { ImagePlus, RefreshCw, Trash2, UploadCloud } from 'lucide-vue-next'

const props = defineProps({ phase: String, label: String, file: File, preview: String })
const emit = defineEmits(['update:file'])
const dragging = ref(false)
const fileName = computed(() => props.file?.name || '未选择文件')
const fileSize = computed(() => {
  if (!props.file) return ''
  const bytes = props.file.size
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`
})

function setFile(file) {
  if (file?.type?.startsWith('image/') || /\.(tif|tiff)$/i.test(file?.name || '')) {
    emit('update:file', file)
  }
}

function choose(event) {
  const [file] = event.target.files
  if (file) setFile(file)
  event.target.value = ''
}

function drop(event) {
  dragging.value = false
  const [file] = event.dataTransfer.files
  if (file) setFile(file)
}
</script>

<template>
  <div class="image-input" :class="{ complete: preview }">
    <div class="input-heading">
      <div class="input-title"><span class="phase-token">{{ phase }}</span><strong>{{ label }}</strong></div>
      <button v-if="file" class="icon-button" type="button" title="移除图像" :aria-label="`移除${label}`" @click="emit('update:file', null)">
        <Trash2 :size="15" />
      </button>
    </div>

    <label
      class="drop-zone"
      :class="{ filled: preview, dragging }"
      @dragenter.prevent="dragging = true"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="drop"
    >
      <img v-if="preview" :src="preview" :alt="`${label}预览`" />
      <span v-if="preview" class="replace-action"><RefreshCw :size="15" />更换</span>
      <span v-else class="drop-placeholder">
        <span class="upload-symbol"><ImagePlus :size="22" /></span>
        <strong>{{ dragging ? '释放以载入' : '选择影像' }}</strong>
        <small><UploadCloud :size="13" /> PNG · JPG · TIFF</small>
      </span>
      <input type="file" accept="image/png,image/jpeg,image/tiff,.tif,.tiff" @change="choose" />
    </label>

    <div class="file-meta" :class="{ muted: !file }">
      <span class="file-name">{{ fileName }}</span><span v-if="file">{{ fileSize }}</span>
    </div>
  </div>
</template>
