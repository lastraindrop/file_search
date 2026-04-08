<script setup>
import { ref, onMounted, watch } from 'vue'

const props = defineProps(['projectPath', 'stagingList'])
const emit = defineEmits(['refresh'])

const selectedFile = ref(null)
const previewContent = ref('')
const categories = ref({})
const newCatName = ref('')
const newCatPath = ref('')

const fetchConfig = async () => {
    if (!props.projectPath) return
    try {
        const res = await fetch(`/api/project/config?path=${encodeURIComponent(props.projectPath)}`)
        const data = await res.json()
        categories.value = data.quick_categories || {}
    } catch (e) {
        console.error('Failed to fetch project config', e)
    }
}

const fetchPreview = async (path) => {
    try {
        const res = await fetch(`/api/content?path=${encodeURIComponent(path)}`)
        const data = await res.json()
        previewContent.value = data.content
    } catch (e) {
        previewContent.value = 'Error loading preview: ' + e
    }
}

const addCategory = async () => {
    if (!newCatName.value || !newCatPath.value) return
    const updated = { ...categories.value, [newCatName.value]: newCatPath.value }
    try {
        const res = await fetch('/api/project/categories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_path: props.projectPath,
                categories: updated
            })
        })
        if (res.ok) {
            categories.value = updated
            newCatName.value = ''
            newCatPath.value = ''
        }
    } catch (e) {
        console.error('Failed to update categories', e)
    }
}

const categorize = async (catName) => {
    if (!selectedFile.value || !props.projectPath) return
    try {
        const res = await fetch('/api/actions/categorize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_path: props.projectPath,
                paths: [selectedFile.value],
                category_name: catName
            })
        })
        if (res.ok) {
            selectedFile.value = null
            previewContent.value = ''
            emit('refresh') // Notify parent to refresh staging list
        }
    } catch (e) {
        console.error('Categorization failed', e)
    }
}

watch(() => props.projectPath, fetchConfig, { immediate: true })

const selectFile = (path) => {
    selectedFile.value = path
    fetchPreview(path)
}
</script>

<template>
  <div class="categorizer-layout">
    <!-- Left: File Selection -->
    <div class="column file-zone glass-panel">
      <div class="zone-header">Staged Files</div>
      <div class="file-list">
        <div v-if="!stagingList || stagingList.length === 0" class="empty">No files staged</div>
        <div v-for="file in stagingList" :key="file" 
             class="file-item" 
             :class="{ active: selectedFile === file }"
             @click="selectFile(file)">
          <span class="file-icon">📄</span>
          <span class="file-name">{{ file.split(/[\\/]/).pop() }}</span>
        </div>
      </div>
    </div>

    <!-- Middle: Preview -->
    <div class="column preview-zone glass-panel">
      <div class="zone-header">Preview: {{ selectedFile ? selectedFile.split(/[\\/]/).pop() : 'None' }}</div>
      <div class="preview-content">
        <textarea readonly v-model="previewContent" placeholder="Select a file to preview content..."></textarea>
      </div>
    </div>

    <!-- Right: Categories -->
    <div class="column category-zone glass-panel">
      <div class="zone-header">Categories</div>
      <div class="category-buttons">
        <button v-for="(path, name) in categories" :key="name" 
                class="btn-category" 
                @click="categorize(name)">
          <span class="btn-label">{{ name }}</span>
          <span class="btn-path">{{ path }}</span>
        </button>
      </div>

      <div class="add-category glass-panel">
        <h4>New Category</h4>
        <input v-model="newCatName" placeholder="Name (e.g. Scripts)" />
        <input v-model="newCatPath" placeholder="Path (e.g. src/scripts)" />
        <button class="btn-primary" @click="addCategory">+ Add</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.categorizer-layout {
  display: grid;
  grid-template-columns: 280px 1fr 300px;
  gap: 1rem;
  height: 100%;
  overflow: hidden;
}

.column {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.zone-header {
  padding: 1rem;
  font-weight: 600;
  font-size: 0.85rem;
  text-transform: uppercase;
  color: var(--text-muted);
  border-bottom: 1px solid var(--glass-border);
}

.file-list, .category-buttons {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem;
}

.file-item {
  padding: 0.6rem 0.75rem;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.file-item:hover {
  background: var(--glass-hover);
}

.file-item.active {
  background: rgba(99, 102, 241, 0.15);
  border-left: 3px solid var(--primary);
}

.preview-content {
  flex: 1;
  padding: 0;
}

textarea {
  width: 100%;
  height: 100%;
  background: transparent;
  border: none;
  color: #ccc;
  font-family: 'Fira Code', monospace;
  font-size: 0.85rem;
  padding: 1.5rem;
  outline: none;
  resize: none;
}

.btn-category {
  width: 100%;
  padding: 0.85rem;
  margin-bottom: 0.75rem;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  color: var(--text-main);
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-category:hover {
  background: var(--glass-hover);
  transform: translateY(-2px);
  border-color: var(--primary);
}

.btn-label {
  display: block;
  font-weight: 700;
  font-size: 1rem;
}

.btn-path {
  display: block;
  font-size: 0.7rem;
  color: var(--text-muted);
}

.add-category {
  padding: 1rem;
  margin: 1rem;
  background: rgba(255,255,255,0.02);
}

.add-category h4 {
  font-size: 0.8rem;
  margin-bottom: 0.75rem;
  color: var(--text-muted);
}

input {
  width: 100%;
  background: rgba(0,0,0,0.2);
  border: 1px solid var(--glass-border);
  padding: 0.5rem;
  border-radius: 6px;
  color: white;
  margin-bottom: 0.5rem;
  outline: none;
}

input:focus {
  border-color: var(--primary);
}
</style>
