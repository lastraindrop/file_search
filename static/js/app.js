const App = {
    state: {
        projectPath: "",
        staging: new Set(),
        currentFile: null,
        socket: null,
        isEditing: false,
        rawContent: "",
        selectedFiles: new Set(),
        searchResults: [],
        projConfig: {},
        isSidebarExpanded: false
    },

    escapeHtml: (str) => {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },

    // Helper for robust error handling
    _fetch: async (url, options = {}) => {
        const res = await fetch(url, options);
        if (!res.ok) {
            let detail = "Unknown error";
            try {
                const data = await res.json();
                detail = data.detail || detail;
            } catch (e) {
                detail = await res.text();
            }
            throw new Error(detail);
        }
        return res;
    },

    showToast: (message, type = 'success') => {
        const container = document.querySelector('.toast-container');
        const toastEl = document.createElement('div');
        toastEl.className = `toast align-items-center text-bg-${type} border-0 animate-in mb-2`;
        toastEl.setAttribute('role', 'alert');
        toastEl.setAttribute('aria-live', 'assertive');
        toastEl.setAttribute('aria-atomic', 'true');
        toastEl.innerHTML = `
            <div class="d-flex">
                <div class="toast-body fw-bold">${App.escapeHtml(message)}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        `;
        container.appendChild(toastEl);
        const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
        toast.show();
        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    },

    init: async () => {
        App.loadWorkspaces();
        document.getElementById('searchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                App.startSearch();
            }
        });
        
        // Restore search settings from localStorage
        const savedExcludes = localStorage.getItem('searchExcludes');
        const excludeIn = document.getElementById('excludeInput');
        if (savedExcludes && excludeIn) excludeIn.value = savedExcludes;
        const savedMode = localStorage.getItem('searchMode');
        if (savedMode) document.getElementById('searchMode').value = savedMode;
        
        // Restore sidebar state
        const sidebarState = localStorage.getItem('sidebarExpanded');
        if (sidebarState === 'true') App.toggleSidebar();
        
        // Auto-load last project if exists
        const lastProj = localStorage.getItem('lastProjectPath');
        if (lastProj) {
            document.getElementById('projectPath').value = lastProj;
            App.openProject();
        }
    },

    // --- Workspace Logic ---
    toggleSidebar: () => {
        const sb = document.getElementById('workspaceSidebar');
        App.state.isSidebarExpanded = !App.state.isSidebarExpanded;
        sb.style.width = App.state.isSidebarExpanded ? '210px' : '60px';
        localStorage.setItem('sidebarExpanded', App.state.isSidebarExpanded);
    },

    loadWorkspaces: async () => {
        try {
            const res = await fetch('/api/workspaces');
            const data = await res.json();
            App.renderWorkspaces(data);
        } catch (e) { console.error("Failed to load workspaces", e); }
    },

    renderWorkspaces: (data) => {
        const renderList = (list, containerId) => {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = '';
            list.forEach(item => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-outline-info btn-sm text-truncate w-100 mb-1';
                btn.style.height = '32px';
                btn.innerText = App.state.isSidebarExpanded ? item.name : item.name[0].toUpperCase();
                btn.title = item.path;
                btn.onclick = () => {
                    document.getElementById('projectPath').value = item.path;
                    App.openProject();
                };
                container.appendChild(btn);
            });
        };
        renderList(data.pinned, 'pinnedProjectsList');
        renderList(data.recent, 'recentProjectsList');
        
        const isPinned = data.pinned.some(p => p.path === App.state.projectPath);
        App.updatePinUI(isPinned);
    },

    updatePinUI: (isPinned) => {
        const btn = document.getElementById('btnPin');
        if (btn) {
            btn.innerText = isPinned ? '⭐' : '☆';
            btn.classList.toggle('btn-warning', isPinned);
            btn.classList.toggle('btn-outline-warning', !isPinned);
        }
    },

    togglePin: async () => {
        if (!App.state.projectPath) return;
        try {
            const res = await App._fetch('/api/workspaces/pin', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ path: App.state.projectPath })
            });
            const data = await res.json();
            App.updatePinUI(data.is_pinned);
            await App.loadWorkspaces();
        } catch (e) { App.showToast("Pin failed: " + e.message, 'danger'); }
    },

    openProject: async (path = null) => {
        const p = path || document.getElementById('projectPath').value.trim();
        if (!p) return;

        try {
            const res = await App._fetch('/api/open', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ path: p })
            });
            const data = await res.json();
            
            App.state.projectPath = p;
            document.getElementById('projectPath').value = p;
            localStorage.setItem('lastProjectPath', p);
            
            const configRes = await App._fetch(`/api/project/config?path=${encodeURIComponent(p)}`);
            App.state.projConfig = await configRes.json();
            
            // Restore UI Settings from Config
            if (App.state.projConfig.excludes) {
                document.getElementById('excludeInput').value = App.state.projConfig.excludes;
            }
            if (App.state.projConfig.search_settings) {
                document.getElementById('searchMode').value = App.state.projConfig.search_settings.mode || 'smart';
            }
            
            App.updateTemplateList();
            if (App.state.projConfig.staging_list) {
                App.state.staging = new Set(App.state.projConfig.staging_list);
                App.renderStaging();
            }

            const rootContainer = document.getElementById('fileTreeRoot');
            rootContainer.innerHTML = '';
            rootContainer.appendChild(App.renderTree(data));
            App.renderFavorites();
            App.renderActions();
            App.loadWorkspaces();

            App.showToast(`Opened project: ${data.name}`);
        } catch (e) { App.showToast("Error: " + e.message, 'danger'); }
    },

    refreshProject: async () => {
        if (!App.state.projectPath) return;
        await App.saveSettings();
        await App.openProject(App.state.projectPath);
    },

    saveSettings: async () => {
        if (!App.state.projectPath) return;
        try {
            await App._fetch('/api/project/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    excludes: document.getElementById('excludeInput').value,
                    search_settings: {
                        mode: document.getElementById('searchMode').value
                    }
                })
            });
        } catch (e) { console.warn("Auto-save settings failed", e); }
    },

    // --- File Tree Rendering ---
    renderTree: (node) => {
        const container = document.createElement('div');
        container.className = 'ms-1';
        const header = document.createElement('div');
        header.className = 'tree-node d-flex align-items-center text-truncate animate-in';
        header.setAttribute('data-path', node.path);
        
        // Add Checkbox for files (and maybe dirs if requested, but plan said files)
        if (node.type === 'file') {
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.className = 'form-check-input me-2 x-small';
            cb.style.width = '0.8rem';
            cb.style.height = '0.8rem';
            cb.checked = App.state.selectedFiles.has(node.path);
            cb.onclick = (e) => {
                e.stopPropagation();
                if (cb.checked) App.state.selectedFiles.add(node.path);
                else App.state.selectedFiles.delete(node.path);
                App.updateBulkUI();
            };
            header.appendChild(cb);
        }

        const icon = node.type === 'dir' ? '📁' : '📄';
        const metaInfo = node.type === 'file' ? ` (${node.size_fmt})` : '';
        const nameSpan = document.createElement('span');
        nameSpan.className = 'flex-grow-1 text-truncate';
        nameSpan.innerHTML = `<span class="me-1">${icon}</span><span>${App.escapeHtml(node.name)}</span>
                             <span class="ms-2 text-muted x-small d-none d-lg-inline" style="font-size:0.7rem">${node.mtime_fmt || ''}${metaInfo}</span>`;
        header.appendChild(nameSpan);
        container.appendChild(header);

        if (node.type === 'dir') {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'tree-children';
            childrenContainer.style.display = 'none';
            container.appendChild(childrenContainer);

            let loaded = false;
            header.onclick = async (e) => {
                e.stopPropagation();
                const isHidden = childrenContainer.style.display === 'none';
                if (isHidden && !loaded) {
                    try {
                        const res = await fetch('/api/fs/children', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ path: node.path })
                        });
                        const data = await res.json();
                        childrenContainer.innerHTML = '';
                        data.children.forEach(child => childrenContainer.appendChild(App.renderTree(child)));
                        loaded = true;
                    } catch (err) { console.error(err); }
                }
                childrenContainer.style.display = isHidden ? 'block' : 'none';
            };
        } else {
            header.onclick = (e) => {
                e.stopPropagation();
                document.querySelectorAll('.tree-node').forEach(n => n.classList.remove('active'));
                header.classList.add('active');
                App.previewFile(node.path);
            };
        }
        return container;
    },

    // --- File Operations ---
    previewFile: async (path) => {
        App.state.currentFile = path;
        App.state.isEditing = false;
        document.getElementById('fileControls').style.display = 'inline-flex';
        document.getElementById('btnEditSave').innerText = 'Edit';
        document.getElementById('codeEditor').style.display = 'none';
        document.getElementById('preBlock').style.display = 'block';

        const fileName = path.split(/[\\\/]/).pop();
        document.getElementById('currentFileName').innerText = fileName;
        App.updateFileMetaUI(path);

        const codeEl = document.getElementById('codePreview');
        codeEl.innerText = "Loading...";
        
        try {
            const res = await App._fetch(`/api/content?path=${encodeURIComponent(path)}`);
            const data = await res.json();
            App.state.rawContent = data.content;
            codeEl.innerText = data.content;
            hljs.highlightElement(codeEl);
        } catch (e) { codeEl.innerText = "Error loading file."; }
    },

    copyPath: async () => {
        if (!App.state.currentFile) return;
        try {
            await navigator.clipboard.writeText(App.state.currentFile);
            const btn = document.querySelector('[onclick="App.copyPath()"]');
            btn.innerText = "✅";
            setTimeout(() => btn.innerText = "🔗", 1000);
            App.showToast("✅ Path copied!", 'success');
        } catch (e) { App.showToast("Failed to copy path", 'danger'); }
    },

    updateFileMetaUI: (path) => {
        const tagContainer = document.getElementById('fileTags');
        tagContainer.innerHTML = '';
        const tags = App.state.projConfig.tags[path] || [];
        tags.forEach(tag => {
            const span = document.createElement('span');
            span.className = 'badge bg-info text-dark small';
            span.innerText = tag;
            tagContainer.appendChild(span);
        });
    },

    showFileNote: () => {
        if (!App.state.currentFile) return;
        const note = App.state.projConfig.notes[App.state.currentFile] || "";
        document.getElementById('noteInput').value = note;
        document.getElementById('noteOverlay').style.display = 'block';
    },

    hideFileNote: () => { document.getElementById('noteOverlay').style.display = 'none'; },

    saveFileNote: async () => {
        const note = document.getElementById('noteInput').value.trim();
        try {
            await App._fetch('/api/project/note', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    file_path: App.state.currentFile,
                    note: note
                })
            });
            App.state.projConfig.notes[App.state.currentFile] = note;
            App.hideFileNote();
        } catch (e) { alert("Save failed"); }
    },

    archiveStaging: async () => {
        if (App.state.staging.size === 0) return alert("Select files first.");
        const name = prompt("Archive Name:", "context_backup.zip");
        if (!name) return;
        
        const btn = document.querySelector('[onclick="App.archiveStaging()"]');
        const originalText = btn.innerText;
        btn.innerText = "📦 Archiving...";
        btn.disabled = true;

        try {
            await App._fetch('/api/fs/archive', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    paths: Array.from(App.state.staging),
                    output_name: name,
                    project_root: App.state.projectPath
                })
            });
            App.showToast(`✅ Archived to ${name}`, 'success');
        } catch (e) { App.showToast(e.message, 'danger'); }
        finally {
            btn.innerText = originalText;
            btn.disabled = false;
        }
    },

    updateTemplateList: () => {
        const select = document.getElementById('promptTemplate');
        if (!select) return;
        const templates = App.state.projConfig.prompt_templates || {};
        select.innerHTML = '<option value="">None (Standard)</option>';
        Object.keys(templates).forEach(name => {
            const opt = document.createElement('option');
            opt.value = name; opt.innerText = name;
            select.appendChild(opt);
        });
    },

    renameFile: async () => {
        if (!App.state.currentFile) return;
        const oldName = App.state.currentFile.split(/[\\\/]/).pop();
        const newName = prompt("New name:", oldName);
        if (!newName || newName === oldName) return;
        
        try {
            await App._fetch('/api/fs/rename', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    project_path: App.state.projectPath, 
                    path: App.state.currentFile, 
                    new_name: newName 
                })
            });
            App.showToast("Renamed successfully");
            App.openProject(); // Refresh tree
            App.state.currentFile = null;
            document.getElementById('fileControls').style.display = 'none';
        } catch (e) { App.showToast("Rename failed: " + e.message, 'danger'); }
    },

    deleteFile: async () => {
        if (!App.state.currentFile || !confirm("Are you sure?")) return;
        try {
            await App._fetch('/api/fs/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ project_path: App.state.projectPath, paths: [App.state.currentFile] })
            });
            App.openProject();
            App.state.currentFile = null;
            document.getElementById('fileControls').style.display = 'none';
        } catch (e) { alert("Delete failed"); }
    },
    startSearch: () => {
        if (!App.state.projectPath) return;
        const query = document.getElementById('searchInput').value;
        const mode = document.getElementById('searchMode').value;
        localStorage.setItem('searchMode', mode);
        const tab = new bootstrap.Tab(document.getElementById('tab-search'));
        tab.show();

        const resultsDiv = document.getElementById('searchResultsList');
        resultsDiv.innerHTML = '<div class="text-center p-3">Searching...</div>';

        const wsUrl = `ws://${window.location.host}/ws/search?path=${encodeURIComponent(App.state.projectPath)}&query=${encodeURIComponent(query)}&mode=${mode}`;
        App.state.socket = new WebSocket(wsUrl);
        
        App.state.socket.onopen = () => { resultsDiv.innerHTML = ''; };
        App.state.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.status === "DONE") return App.state.socket.close();
            App.renderSearchResultItem(data);
        };
    },

    renderSearchResultItem: (data) => {
        const list = document.getElementById('searchResultsList');
        const item = document.createElement('div');
        item.className = 'list-group-item bg-transparent text-white border-0 animate-in p-2 cursor-pointer';
        item.setAttribute('data-path', data.path);
        item.style.cursor = 'pointer';
        item.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div class="fw-bold text-info">${App.escapeHtml(data.name)}</div>
                <div class="text-muted x-small" style="font-size:0.7rem">${data.mtime_fmt || ''}</div>
            </div>
            <div class="small text-muted text-truncate">${App.escapeHtml(data.path)}</div>
        `;
        item.onclick = () => App.previewFile(data.path);
        item.oncontextmenu = (e) => {
            e.preventDefault();
            App.showPathCollector([data.path]);
        };
        list.appendChild(item);
    },

    // --- FileCortex Actions ---
    renderActions: () => {
        const catContainer = document.getElementById('categoriesContainer');
        const toolContainer = document.getElementById('toolsContainer');
        const section = document.getElementById('quickActionsSection');
        
        catContainer.innerHTML = '';
        toolContainer.innerHTML = '';
        
        const cats = App.state.projConfig.quick_categories || {};
        const tools = App.state.projConfig.custom_tools || {};
        
        const catKeys = Object.keys(cats);
        const toolKeys = Object.keys(tools);
        
        if (catKeys.length === 0 && toolKeys.length === 0) {
            section.style.display = 'none';
            return;
        }
        
        section.style.display = 'block';
        
        catKeys.forEach(name => {
            const btn = document.createElement('button');
            btn.className = 'btn btn-outline-info btn-xs py-0 px-1 x-small';
            btn.innerText = name;
            btn.onclick = () => App.categorizeStaged(name);
            catContainer.appendChild(btn);
        });
        
        toolKeys.forEach(name => {
            const btn = document.createElement('button');
            btn.className = 'btn btn-outline-warning btn-xs py-0 px-1 x-small';
            btn.innerText = name;
            btn.onclick = () => App.executeToolOnStaged(name);
            toolContainer.appendChild(btn);
        });
    },

    categorizeStaged: async (catName) => {
        if (App.state.staging.size === 0) return App.showToast("Add files to staging first.", 'warning');
        const btn = document.querySelector(`[onclick="App.categorizeStaged('${catName}')"]`);
        const originalText = btn ? btn.innerText : catName;
        if (btn) { btn.innerText = "..."; btn.disabled = true; }

        try {
            const res = await App._fetch('/api/actions/categorize', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    paths: Array.from(App.state.staging),
                    category_name: catName
                })
            });
            const data = await res.json();
            App.showToast(`✅ Successfully moved ${data.moved_count} files to ${catName}`, 'success');
            App.state.staging.clear();
            App.renderStaging();
            App.syncStagingToBackend();
            App.refreshProject();
        } catch (e) { App.showToast("Error: " + e.message, 'danger'); }
        finally { if (btn) { btn.innerText = originalText; btn.disabled = false; } }
    },

    executeToolOnStaged: async (toolName) => {
        if (App.state.staging.size === 0) return App.showToast("Add files to staging first.", 'warning');
        const btn = document.querySelector(`[onclick="App.executeToolOnStaged('${toolName}')"]`);
        const originalText = btn ? btn.innerText : toolName;
        if (btn) { btn.innerText = "Running..."; btn.disabled = true; }

        try {
            const res = await App._fetch('/api/actions/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    paths: Array.from(App.state.staging),
                    tool_name: toolName
                })
            });
            const data = await res.json();
            const modalWrapper = document.getElementById('toolResultModal');
            const modalBody = document.getElementById('toolResultModalBody');
            modalBody.innerHTML = '';
            
            data.results.forEach(r => {
                const block = document.createElement('div');
                block.className = 'border-bottom border-secondary p-3';
                const color = r.exit_code === 0 ? 'text-success' : 'text-danger';
                block.innerHTML = `
                    <div class="fw-bold mb-2">${App.escapeHtml(r.path)} <span class="badge bg-secondary ms-2 align-middle">Exit: <span class="${color}">${r.exit_code}</span></span></div>
                    <pre class="m-0 p-2 rounded" style="background:#000; color:#ccc; font-size:0.85rem;"><code>${App.escapeHtml(r.stdout || 'No output')}</code></pre>
                    ${r.error ? `<div class="text-danger small mt-2">Error: ${App.escapeHtml(r.error)}</div>` : ''}
                `;
                modalBody.appendChild(block);
            });
            
            const bsModal = new bootstrap.Modal(modalWrapper);
            bsModal.show();
            
            App.state.staging.clear();
            App.renderStaging();
            App.syncStagingToBackend();
        } catch (e) { App.showToast("Error: " + e.message, 'danger'); }
        finally { if (btn) { btn.innerText = originalText; btn.disabled = false; } }
    },

    // --- Staging & Generation ---
    addToStaging: () => {
        if (!App.state.currentFile) return;
        App.state.staging.add(App.state.currentFile);
        App.renderStaging();
        App.syncStagingToBackend();
    },

    renderStaging: () => {
        const list = document.getElementById('stagingList');
        list.innerHTML = '';
        App.state.staging.forEach(path => {
            const item = document.createElement('div');
            item.className = 'list-group-item d-flex justify-content-between p-1 bg-transparent border-0 text-white animate-in';
            const nameSpan = document.createElement('span');
            nameSpan.className = 'text-truncate small cursor-pointer';
            nameSpan.title = path;
            nameSpan.innerText = path.split(/[\\\/]/).pop();
            nameSpan.onclick = () => App.previewFile(path);

            const removeBtn = document.createElement('button');
            removeBtn.className = 'btn btn-sm btn-link text-danger p-0 ms-2';
            removeBtn.innerHTML = '&times;';
            removeBtn.onclick = (e) => { e.stopPropagation(); App.removeFromStaging(path); };

            item.appendChild(nameSpan);
            item.appendChild(removeBtn);
            list.appendChild(item);
        });
        App.updateStats();
    },

    removeFromStaging: (path) => {
        App.state.staging.delete(path);
        App.renderStaging();
        App.syncStagingToBackend();
    },

    syncStagingToBackend: async () => {
        if (!App.state.projectPath) return;
        try {
            await App._fetch('/api/project/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    settings: { "staging_list": Array.from(App.state.staging) }
                })
            });
        } catch (e) { console.warn("Staging sync failed", e); }
    },

    renderFavorites: () => {
        const list = document.getElementById('favoritesList');
        const select = document.getElementById('favGroupSelect');
        list.innerHTML = '';
        
        if (!App.state.projConfig || !App.state.projConfig.groups) return;

        const groups = Object.keys(App.state.projConfig.groups);
        
        // Update group selector if empty
        if (select.options.length === 0) {
            groups.forEach(g => {
                const opt = document.createElement('option');
                opt.value = g; opt.innerText = g;
                select.appendChild(opt);
            });
            select.value = App.state.projConfig.current_group || "Default";
        }

        const currentGroup = select.value || "Default";
        const files = App.state.projConfig.groups[currentGroup] || [];
        
        if (files.length === 0) {
            list.innerHTML = '<div class="text-muted p-2 small">No favorites in this group.</div>';
            return;
        }

        files.forEach(path => {
            const item = document.createElement('div');
            item.className = 'list-group-item bg-transparent text-white border-0 p-2 cursor-pointer hover-bg d-flex justify-content-between align-items-center';
            
            const infoDiv = document.createElement('div');
            infoDiv.className = 'text-truncate flex-grow-1';
            infoDiv.innerHTML = `
                <div class="fw-bold text-info small">${App.escapeHtml(path.split(/[\\\/]/).pop())}</div>
                <div class="text-muted" style="font-size:0.75rem">${App.escapeHtml(path)}</div>
            `;
            infoDiv.onclick = () => App.previewFile(path);

            const removeBtn = document.createElement('button');
            removeBtn.className = 'btn btn-sm btn-link text-danger p-0';
            removeBtn.title = 'Unfavorite';
            removeBtn.innerHTML = '&times;';
            removeBtn.onclick = (e) => { e.stopPropagation(); App.toggleFavorite(path, 'remove'); };

            item.appendChild(infoDiv);
            item.appendChild(removeBtn);
            list.appendChild(item);
        });
    },

    addToFavorites: async () => {
        if (!App.state.currentFile) return;
        const group = document.getElementById('favGroupSelect').value || "Default";
        await App.toggleFavorite(App.state.currentFile, 'add', group);
    },

    toggleFavorite: async (path, action, group = null) => {
        if (!group) group = document.getElementById('favGroupSelect').value || "Default";
        try {
            await App._fetch('/api/project/favorites', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    group_name: group,
                    file_paths: [path],
                    action: action
                })
            });
            
            // Hot update local config for instant UI feedback
            if (!App.state.projConfig.groups[group]) App.state.projConfig.groups[group] = [];
            if (action === 'add') {
                if (!App.state.projConfig.groups[group].includes(path)) App.state.projConfig.groups[group].push(path);
                App.showToast("⭐ Added to favorites");
            } else {
                App.state.projConfig.groups[group] = App.state.projConfig.groups[group].filter(p => p !== path);
                App.showToast("Removed from favorites");
            }
            App.renderFavorites();
        } catch (e) { App.showToast(e.message, 'danger'); }
    },

    _statsTimer: null,

    updateStats: async () => {
        // Debounce: cancel pending update, schedule new one after 300ms
        if (App._statsTimer) clearTimeout(App._statsTimer);
        App._statsTimer = setTimeout(App._updateStatsImpl, 300);
    },

    _updateStatsImpl: async () => {
        const count = App.state.staging.size;
        const label = document.getElementById('tokenEstimate');
        if (!label) return;
        
        if (count === 0) {
            label.innerText = " 清单: 0 项 | 0 Tokens";
            return;
        }

        try {
            const res = await App._fetch('/api/project/stats', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ paths: Array.from(App.state.staging) })
            });
            const data = await res.json();
            label.innerText = ` 清单: ${count} 项 | 估算 ${data.total_tokens} Tokens`;
        } catch (e) {
            label.innerText = `${count} Files`;
        }
    },

    generateContext: async () => {
        if (App.state.staging.size === 0) return;
        const templateName = document.getElementById('promptTemplate').value;
        const btn = document.querySelector('[onclick="App.generateContext()"]');
        const originalText = btn.innerText;
        btn.innerText = "🚀 Generating...";
        btn.disabled = true;

        try {
            const res = await App._fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    files: Array.from(App.state.staging),
                    project_path: App.state.projectPath,
                    template_name: templateName
                })
            });
            const data = await res.json();
            await navigator.clipboard.writeText(data.content);
            App.showToast("✅ Context copied!", 'success');
        } catch (e) { App.showToast("Failed to generate context: " + e.message, 'danger'); }
        finally {
            btn.innerText = originalText;
            btn.disabled = false;
        }
    },

    toggleEdit: async () => {
        if (!App.state.currentFile) return;
        const editor = document.getElementById('codeEditor');
        const preview = document.getElementById('preBlock');
        const btn = document.getElementById('btnEditSave');

        if (!App.state.isEditing) {
            App.state.isEditing = true;
            editor.value = App.state.rawContent;
            editor.style.display = 'block';
            preview.style.display = 'none';
            btn.innerText = 'Save';
        } else {
            try {
                await App._fetch('/api/fs/save', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ path: App.state.currentFile, content: editor.value })
                });
                App.state.isEditing = false;
                editor.style.display = 'none';
                preview.style.display = 'block';
                btn.innerText = 'Edit';
                App.previewFile(App.state.currentFile);
                App.showToast("File saved", 'success');
            } catch (e) { App.showToast("Save failed: " + e.message, 'danger'); }
        }
    },

    // --- Bulk Operations (Impl) ---
    toggleSelectAll: (checked) => {
        App.state.selectedFiles.clear();
        if (checked) {
            // This would normally select all visible files in the tree or search results
            // For now, we'll just handle the state and count.
            // Full implementation would require a recursive tree traversal or search result mapping.
            const allItems = document.querySelectorAll('.tree-node[data-path], .list-group-item[data-path]');
            allItems.forEach(item => {
                const path = item.getAttribute('data-path');
                if (path) App.state.selectedFiles.add(path);
            });
        }
        App.updateBulkUI();
    },

    updateBulkUI: () => {
        const count = App.state.selectedFiles.size;
        document.getElementById('selectedCount').innerText = count;
        const bulkActions = document.getElementById('bulkActions');
        if (count > 0) {
            bulkActions.style.setProperty('display', 'flex', 'important');
        } else {
            bulkActions.style.setProperty('display', 'none', 'important');
        }
    },

    bulkStage: () => {
        if (App.state.selectedFiles.size === 0) return;
        App.state.selectedFiles.forEach(path => App.state.staging.add(path));
        document.getElementById('selectAllCb').checked = false;
        App.renderStaging();
        App.syncStagingToBackend();
        App.state.selectedFiles.clear();
        App.updateBulkUI();
        App.showToast("✅ Added selected items to staging");
    },

    bulkDelete: async () => {
        if (App.state.selectedFiles.size === 0 || !confirm(`Delete ${App.state.selectedFiles.size} files forever?`)) return;
        try {
            await App._fetch('/api/fs/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    project_path: App.state.projectPath, 
                    paths: Array.from(App.state.selectedFiles) 
                })
            });
            App.state.selectedFiles.clear();
            App.updateBulkUI();
            App.openProject();
            App.showToast("Batch delete successful.");
        } catch (e) { App.showToast("Bulk delete failed: " + e.message, 'danger'); }
    },

    bulkMove: async () => {
        if (App.state.selectedFiles.size === 0) return;
        const dstDir = prompt("Enter destination directory path (within project root):");
        if (!dstDir) return;
        
        try {
            const res = await App._fetch('/api/fs/move', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    src_paths: Array.from(App.state.selectedFiles),
                    dst_dir: dstDir
                })
            });
            const data = await res.json();
            App.showToast(`Batch Move: ${data.new_paths.length} items moved.`);
            App.state.selectedFiles.clear();
            App.updateBulkUI();
            App.openProject(); 
        } catch (e) { App.showToast("Move failed: " + e.message, 'danger'); }
    },

    // --- Path Collection ---
    showPathCollector: (paths = null) => {
        App._currentCollectionPaths = paths || Array.from(App.state.staging);
        if (!App._currentCollectionPaths || App._currentCollectionPaths.length === 0) {
            App.showToast("No files selected or staged!", "warning");
            return;
        }
        const modal = new bootstrap.Modal(document.getElementById('pathCollectorModal'));
        modal.show();
    },

    collectPaths: async () => {
        const paths = App._currentCollectionPaths;
        const mode = document.querySelector('input[name="pathMode"]:checked').value;
        const separator = document.getElementById('pathSep').value;
        const project_root = App.state.projectPath;

        try {
            const res = await App._fetch('/api/fs/collect_paths', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    paths: paths,
                    project_root: project_root,
                    mode: mode,
                    separator: separator
                })
            });
            const data = await res.json();
            if (data.result) {
                await navigator.clipboard.writeText(data.result);
                App.showToast(`✅ ${paths.length} paths copied to clipboard!`, "success");
                const modalEl = document.getElementById('pathCollectorModal');
                bootstrap.Modal.getInstance(modalEl).hide();
            }
        } catch (e) {
            App.showToast("Collection failed: " + e.message, "danger");
        }
    }
};

// Initialize App
document.addEventListener('DOMContentLoaded', () => App.init());
