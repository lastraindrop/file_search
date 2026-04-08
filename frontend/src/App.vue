<script setup>
import { ref, onMounted, watch } from 'vue'
import Categorizer from './components/Categorizer.vue'

const workspaces = ref([])
const activeProject = ref(null)
const projConfig = ref({})
const fileTree = ref([])
const stagingList = ref([])
const currentContext = ref('')
const totalTokens = ref(0)
const isLoading = ref(false)
const activeTab = ref('orchestration') // 'orchestration' or 'categorizer'

// API Fetching
const fetchWorkspaces = async () => {
    try {
        const res = await fetch('/api/workspaces')
        workspaces.value = await res.json()
    } catch (e) { console.error('Failed to fetch workspaces', e) }
}

const fetchProjectConfig = async (path) => {
    try {
        const res = await fetch(`/api/project/config?path=${encodeURIComponent(path)}`)
        projConfig.value = await res.json()
        stagingList.value = projConfig.value.staging_list || []
    } catch (e) { console.error('Failed to fetch config', e) }
}

const openProject = async (path) => {
    isLoading.value = true
    try {
        const res = await fetch('/api/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        })
        activeProject.value = await res.json()
        await fetchProjectConfig(path)
        await fetchChildren(path)
    } catch (e) { console.error('Failed to open project', e) }
    isLoading.value = false
}

const fetchChildren = async (path) => {
    try {
        const res = await fetch('/api/fs/children', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        })
        fileTree.value = (await res.json()).children
    } catch (e) { console.error('Failed to fetch children', e) }
}

const generateContext = async () => {
    if (!stagingList.value.length) return
    isLoading.value = true
    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                files: stagingList.value,
                project_path: activeProject.value?.path
            })
        })
        const data = await res.json()
        currentContext.value = data.content
        totalTokens.value = data.tokens
    } catch (e) { console.error('Generation failed', e) }
    isLoading.value = false
}

const handleRefresh = async () => {
    if (activeProject.value) {
        await fetchProjectConfig(activeProject.value.path)
    }
}

onMounted(() => {
    fetchWorkspaces()
})
</script>

<template>
  <div class="app-container">
    <nav>
      <div class="logo">
        <span class="icon">⚛</span> FileCortex <span class="version">v6.0</span>
      </div>
      <div class="nav-tabs">
        <button class="nav-tab" :class="{ active: activeTab === 'orchestration' }" @click="activeTab = 'orchestration'">Orchestration</button>
        <button class="nav-tab" :class="{ active: activeTab === 'categorizer' }" @click="activeTab = 'categorizer'">Categorizer</button>
      </div>
      <div class="nav-actions">
         <button class="btn-primary" @click="fetchWorkspaces">
           <i class="refresh-icon">↻</i> Refresh
         </button>
      </div>
    </nav>

    <main class="main-layout" v-if="activeTab === 'orchestration'">
      <!-- Sidebar: Recent Workspaces -->
      <aside class="sidebar glass-panel">
        <h3>Recent Workspaces</h3>
        <div class="workspace-list">
          <div v-for="ws in workspaces" :key="ws.path" 
               class="workspace-item" 
               :class="{ active: activeProject?.path === ws.path }"
               @click="openProject(ws.path)">
            <div class="ws-info">
              <span class="ws-name">{{ ws.name }}</span>
              <span class="ws-path">{{ ws.path }}</span>
            </div>
            <span v-if="ws.is_pinned" class="pin">📌</span>
          </div>
        </div>
      </aside>

      <!-- Center: File Navigator -->
      <section class="explorer glass-panel">
        <header class="panel-header">
           <h2>Workspace Explorer</h2>
           <span v-if="activeProject" class="target-path">{{ activeProject.name }}</span>
        </header>
        
        <div class="tree-container">
          <div v-if="!activeProject" class="empty-state">
             <p>Select a workspace to begin orchestration</p>
          </div>
          <div v-else class="tree">
             <div v-for="node in fileTree" :key="node.path" class="node-item">
               <span class="node-icon">{{ node.type === 'dir' ? '📁' : '📄' }}</span>
               <span class="node-name">{{ node.name }}</span>
               <span class="node-meta">{{ node.size_fmt }}</span>
             </div>
          </div>
        </div>
      </section>

      <!-- Right: Action & Context -->
      <aside class="actions-panel glass-panel">
        <header class="panel-header">
          <h2>Orchestration</h2>
        </header>

        <div class="action-content">
           <div class="stat-grid">
              <div class="stat-card">
                <span class="label">Staged Files</span>
                <span class="value">{{ stagingList.length }}</span>
              </div>
              <div class="stat-card">
                <span class="label">Est. Tokens</span>
                <span class="value">{{ totalTokens }}</span>
              </div>
           </div>

           <div class="prompt-preview glass-panel">
              <textarea readonly v-model="currentContext" placeholder="Generated context will appear here..."></textarea>
           </div>

           <div class="bottom-actions">
              <button class="btn-primary full-width" @click="generateContext" :disabled="isLoading">
                 {{ isLoading ? 'Generating...' : 'Generate LLM Context' }}
              </button>
           </div>
        </div>
      </aside>
    </main>

    <main class="main-layout categorizer-view" v-else>
       <div v-if="!activeProject" class="empty-selection glass-panel">
          <h2>No Project Selected</h2>
          <p>Please select a project from the Orchestration tab first.</p>
       </div>
       <Categorizer v-else 
                   :projectPath="activeProject.path" 
                   :stagingList="stagingList"
                   @refresh="handleRefresh" />
    </main>
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.nav-tabs {
  display: flex;
  gap: 1rem;
}

.nav-tab {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-family: var(--font-display);
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  transition: all 0.2s;
}

.nav-tab:hover {
  background: var(--glass-hover);
  color: var(--text-main);
}

.nav-tab.active {
  color: var(--primary);
  background: rgba(99, 102, 241, 0.1);
}

.version {
  font-size: 0.7rem;
  background: var(--glass-border);
  padding: 0.2rem 0.5rem;
  border-radius: 20px;
  margin-left: 0.5rem;
  font-weight: 400;
  vertical-align: middle;
}

.main-layout {
  display: grid;
  grid-template-columns: 280px 1fr 350px;
  gap: 1.5rem;
  padding: 1rem 2rem 2rem;
  flex: 1;
  overflow: hidden;
}

.categorizer-view {
  display: block;
}

.empty-selection {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
}

.sidebar, .explorer, .actions-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  padding: 1.25rem;
  border-bottom: 1px solid var(--glass-border);
}

h3, h2 {
  font-family: var(--font-display);
  font-size: 1.1rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.workspace-list {
  padding: 1rem;
  overflow-y: auto;
}

.workspace-item {
  padding: 0.75rem 1rem;
  border-radius: 12px;
  cursor: pointer;
  margin-bottom: 0.5rem;
  transition: all 0.2s;
  border: 1px solid transparent;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.workspace-item:hover {
  background: var(--glass-hover);
  border-color: var(--glass-border);
}

.workspace-item.active {
  background: rgba(99, 102, 241, 0.1);
  border-color: var(--primary);
}

.ws-name {
  display: block;
  font-weight: 600;
  font-size: 0.95rem;
}

.ws-path {
  display: block;
  font-size: 0.75rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.tree-container {
  flex: 1;
  padding: 1rem;
  overflow-y: auto;
}

.node-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
  border-radius: 6px;
  font-size: 0.9rem;
  cursor: pointer;
}

.node-item:hover {
  background: var(--glass-hover);
}

.node-meta {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.action-content {
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  flex: 1;
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.stat-card {
  padding: 1rem;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--glass-border);
  text-align: center;
}

.stat-card .label {
  display: block;
  font-size: 0.7rem;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 0.25rem;
}

.stat-card .value {
  font-family: var(--font-display);
  font-size: 1.2rem;
  font-weight: 700;
}

.prompt-preview {
  flex: 1;
  padding: 0.5rem;
  display: flex;
}

textarea {
  width: 100%;
  height: 100%;
  background: transparent;
  border: none;
  color: var(--text-main);
  font-family: 'Fira Code', monospace;
  font-size: 0.85rem;
  resize: none;
  padding: 0.5rem;
  outline: none;
}

.full-width {
  width: 100%;
  justify-content: center;
}
</style>

