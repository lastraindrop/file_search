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
        App.loadRecentProjects();
        document.getElementById('searchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') App.startSearch();
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

    loadRecentProjects: async () => {
        try {
            const res = await fetch('/api/recent_projects');
            const data = await res.json();
            const list = document.getElementById('recentProjectsList');
            list.innerHTML = '';
            data.forEach(p => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-outline-info btn-sm text-truncate w-100 mb-1';
                btn.innerText = App.state.isSidebarExpanded ? p.name : p.name[0].toUpperCase();
                btn.title = p.path;
                btn.onclick = () => {
                    document.getElementById('projectPath').value = p.path;
                    App.openProject();
                };
                list.appendChild(btn);
            });
        } catch (e) { console.error("Failed to load recent projects", e); }
    },

    openProject: async () => {
        const path = document.getElementById('projectPath').value.trim();
        if (!path) return;

        try {
            const res = await fetch('/api/open', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ path })
            });
            if (!res.ok) throw new Error((await res.json()).detail);
            
            const data = await res.json();
            App.state.projectPath = path;
            localStorage.setItem('lastProjectPath', path);
            
            // Load Project Configuration (Notes, Tags, etc.)
            const configRes = await fetch(`/api/project/config?path=${encodeURIComponent(path)}`);
            App.state.projConfig = await configRes.json();
            
            // Restore Staging List from config
            if (App.state.projConfig.staging_list) {
                App.state.staging = new Set(App.state.projConfig.staging_list);
                App.renderStaging();
            }

            const rootContainer = document.getElementById('fileTreeRoot');
            rootContainer.innerHTML = '';
            rootContainer.appendChild(App.renderTree(data.root));
            App.renderFavorites();
            App.renderActions();
            App.loadRecentProjects();

            // Sync settings from config if available and UI is empty
            if (App.state.projConfig.excludes && !document.getElementById('excludeInput').value) {
                document.getElementById('excludeInput').value = App.state.projConfig.excludes;
            }
        } catch (e) { alert("Error: " + e.message); }
    },

    refreshProject: async () => {
        if (!App.state.projectPath) return;
        // Save current UI state to backend before refreshing tree
        const excludes = document.getElementById('excludeInput').value;
        const mode = document.getElementById('searchMode').value;
        
        localStorage.setItem('searchExcludes', excludes);
        localStorage.setItem('searchMode', mode);

        try {
            await fetch('/api/project/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    settings: { excludes: excludes }
                })
            });
            App.openProject();
        } catch (e) { App.openProject(); } // Refresh anyway
    },

    // --- File Tree Rendering ---
    renderTree: (node) => {
        const container = document.createElement('div');
        container.className = 'ms-2';
        const header = document.createElement('div');
        header.className = 'tree-node text-truncate animate-in';
        header.setAttribute('data-path', node.path);
        
        const icon = node.type === 'dir' ? '📁' : '📄';
        const metaInfo = node.type === 'file' ? ` (${node.size_fmt})` : '';
        header.innerHTML = `<span class="me-1">${icon}</span><span>${App.escapeHtml(node.name)}</span>
                            <span class="ms-2 text-muted x-small d-none d-lg-inline" style="font-size:0.7rem">${node.mtime_fmt || ''}${metaInfo}</span>`;
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
            const res = await fetch(`/api/content?path=${encodeURIComponent(path)}`);
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
            await fetch('/api/project/note', {
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
        
        try {
            const res = await fetch('/api/fs/archive', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    paths: Array.from(App.state.staging),
                    output_name: name,
                    project_root: App.state.projectPath
                })
            });
            if (!res.ok) throw new Error("Archive failed");
            App.showToast(`✅ Archived to ${name}`, 'success');
        } catch (e) { App.showToast(e.message, 'danger'); }
    },

    renameFile: async () => {
        if (!App.state.currentFile) return;
        const newName = prompt("New name:", App.state.currentFile.split(/[\\\/]/).pop());
        if (!newName) return;
        const oldPath = App.state.currentFile;
        const separator = oldPath.includes('\\') ? '\\' : '/';
        const parts = oldPath.split(/[\\\/]/);
        parts[parts.length - 1] = newName;
        const newPath = parts.join(separator);
        
        try {
            await fetch('/api/fs/rename', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ project_path: App.state.projectPath, path: oldPath, new_name: newName })
            });
            App.openProject(); // Refresh tree
            App.state.currentFile = null;
            document.getElementById('fileControls').style.display = 'none';
        } catch (e) { alert("Rename failed"); }
    },

    deleteFile: async () => {
        if (!App.state.currentFile || !confirm("Are you sure?")) return;
        try {
            await fetch('/api/fs/delete', {
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
        try {
            const res = await fetch('/api/actions/categorize', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    paths: Array.from(App.state.staging),
                    category_name: catName
                })
            });
            const data = await res.json();
            if (res.ok) {
                App.showToast(`✅ Successfully moved ${data.moved_count} files to ${catName}`, 'success');
                App.state.staging.clear();
                App.renderStaging();
                App.syncStagingToBackend();
                App.refreshProject();
            } else throw new Error(data.detail);
        } catch (e) { App.showToast("Error: " + e.message, 'danger'); }
    },

    executeToolOnStaged: async (toolName) => {
        if (App.state.staging.size === 0) return App.showToast("Add files to staging first.", 'warning');
        try {
            const res = await fetch('/api/actions/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    paths: Array.from(App.state.staging),
                    tool_name: toolName
                })
            });
            const data = await res.json();
            if (res.ok) {
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
            } else throw new Error(data.detail);
        } catch (e) { App.showToast("Error: " + e.message, 'danger'); }
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
        await fetch('/api/project/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                project_path: App.state.projectPath,
                settings: { "staging_list": Array.from(App.state.staging) }
            })
        });
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
        const res = await fetch('/api/project/favorites', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                project_path: App.state.projectPath,
                group_name: group,
                file_paths: [path],
                action: action
            })
        });
        
        if (res.ok) {
            // Hot update local config for instant UI feedback
            if (!App.state.projConfig.groups[group]) App.state.projConfig.groups[group] = [];
            if (action === 'add') {
                if (!App.state.projConfig.groups[group].includes(path)) App.state.projConfig.groups[group].push(path);
            } else {
                App.state.projConfig.groups[group] = App.state.projConfig.groups[group].filter(p => p !== path);
            }
            App.renderFavorites();
        }
    },

    updateStats: () => {
        document.getElementById('tokenEstimate').innerText = App.state.staging.size;
    },

    generateContext: async () => {
        if (App.state.staging.size === 0) return;
        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ files: Array.from(App.state.staging) })
            });
            const data = await res.json();
            await navigator.clipboard.writeText(data.content);
            App.showToast("✅ Context copied!", 'success');
        } catch (e) { App.showToast("Failed to copy", 'danger'); }
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
                await fetch('/api/fs/save', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ path: App.state.currentFile, content: editor.value })
                });
                App.state.isEditing = false;
                editor.style.display = 'none';
                preview.style.display = 'block';
                btn.innerText = 'Edit';
                App.previewFile(App.state.currentFile);
            } catch (e) { alert("Save failed"); }
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
        App.state.selectedFiles.forEach(p => App.state.staging.add(p));
        App.state.selectedFiles.clear();
        document.getElementById('selectAllCb').checked = false;
        App.renderStaging();
        App.syncStagingToBackend();
        App.updateBulkUI();
        App.showToast(`Batch added ${App.state.staging.size} files to staging.`);
    },

    bulkDelete: async () => {
        if (App.state.selectedFiles.size === 0 || !confirm(`Delete ${App.state.selectedFiles.size} files forever?`)) return;
        try {
            await fetch('/api/fs/delete', {
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
        } catch (e) { alert("Bulk delete failed"); }
    },

    bulkMove: async () => {
        alert("Bulk Move requires a target directory. Please use individual rename/move for now or implement a folder picker.");
    }
};

window.onload = App.init;
