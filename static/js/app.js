const App = {
    config: {
        storageKeys: {
            excludes: 'searchExcludes',
            mode: 'searchMode',
            includeDirs: 'searchIncludeDirs',
            caseSensitive: 'searchCaseSensitive',
            inverse: 'searchInverse',
            sidebarExpanded: 'sidebarExpanded',
            lastProjectPath: 'lastProjectPath'
        },
        ui: {
            searchDebounceMs: 400,
            sidebarWidths: {
                collapsed: '60px',
                expanded: '210px'
            }
        },
        defaults: {
            archiveName: 'context_backup.zip',
            tokenThreshold: 128000,
            tokenRatio: 4
        },
        endpoints: {
            workspaces: '/api/workspaces',
            openProject: '/api/open',
            openPathInOs: '/api/fs/open_os'
        }
    },

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
        collectionProfiles: {},
        isSidebarExpanded: false,
        activePid: null,
        actionModalHandler: null,
        globalSettings: {}
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
        if (!container) return; // Silent skip if UI not ready
        
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
        App.loadGlobalSettings();
        App.loadWorkspaces();
        
        const searchInput = document.getElementById('searchInput');
        let searchTimer;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(
                () => App.startSearch(),
                App.config.ui.searchDebounceMs
            );
        });
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(searchTimer);
                App.startSearch();
            }
        });
        
        // Context Menu Handler
        window.addEventListener('click', () => App.hideContextMenu());
        window.addEventListener('contextmenu', (e) => {
            const target = e.target.closest('[data-path]');
            if (target) {
                e.preventDefault();
                App.showContextMenu(e, target.getAttribute('data-path'));
            }
        });
        
        // Editor Shortcuts: Tab as indent, Ctrl+S as Save
        const editor = document.getElementById('codeEditor');
        if (editor) {
            editor.addEventListener('keydown', (e) => {
                if (e.key === 'Tab') {
                    e.preventDefault();
                    const start = editor.selectionStart;
                    const end = editor.selectionEnd;
                    editor.value = editor.value.substring(0, start) + "    " + editor.value.substring(end);
                    editor.selectionStart = editor.selectionEnd = start + 4;
                }
                if (e.ctrlKey && e.key === 's') {
                    e.preventDefault();
                    App.toggleEdit();
                }
            });
        }
        
        // Global Shortcuts
        window.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 's') {
                if (App.state.isEditing) {
                    e.preventDefault();
                    App.toggleEdit();
                }
            }
            if (e.altKey && (e.key === '1' || e.key === '2' || e.key === '3')) {
                const tabs = ['tab-tree', 'tab-search', 'tab-fav'];
                const b = document.getElementById(tabs[parseInt(e.key)-1]);
                if (b) b.click();
            }
            if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                new bootstrap.Modal(document.getElementById('helpModal')).show();
            }
            if (e.key === 'Escape') App.hideContextMenu();
        });

        // Restore search settings from localStorage
        const savedExcludes = localStorage.getItem(App.config.storageKeys.excludes);
        const excludeIn = document.getElementById('excludeInput');
        if (savedExcludes && excludeIn) excludeIn.value = savedExcludes;
        const savedMode = localStorage.getItem(App.config.storageKeys.mode);
        if (savedMode) document.getElementById('searchMode').value = savedMode;
        App.restoreSearchUiState();
        ['searchMode', 'searchIncludeDirs', 'searchCaseSensitive', 'searchInverse', 'excludeInput']
            .forEach((id) => {
                const el = document.getElementById(id);
                if (!el) return;
                el.addEventListener('change', () => {
                    App.persistSearchUiState();
                    App.updateWorkspaceSummary();
                });
            });
        
        // Restore sidebar state
        const sidebarState = localStorage.getItem(App.config.storageKeys.sidebarExpanded);
        if (sidebarState === 'true') App.toggleSidebar();
        
        // Auto-load last project if exists
        const lastProj = localStorage.getItem(App.config.storageKeys.lastProjectPath);
        if (lastProj) {
            document.getElementById('projectPath').value = lastProj;
            App.openProject();
        }
        const actionConfirm = document.getElementById('actionModalConfirm');
        if (actionConfirm) {
            actionConfirm.addEventListener('click', async () => {
                if (!App.state.actionModalHandler) return;
                actionConfirm.disabled = true;
                try {
                    await App.state.actionModalHandler();
                } finally {
                    actionConfirm.disabled = false;
                }
            });
        }
        App.updateWorkspaceSummary();
    },

    // --- Workspace Logic ---
    toggleSidebar: () => {
        const sb = document.getElementById('workspaceSidebar');
        App.state.isSidebarExpanded = !App.state.isSidebarExpanded;
        sb.style.width = App.state.isSidebarExpanded
            ? App.config.ui.sidebarWidths.expanded
            : App.config.ui.sidebarWidths.collapsed;
        localStorage.setItem(
            App.config.storageKeys.sidebarExpanded,
            App.state.isSidebarExpanded
        );
    },

    loadWorkspaces: async () => {
        try {
            const res = await App._fetch(App.config.endpoints.workspaces);
            const data = await res.json();
            App.renderWorkspaces(data);
        } catch (e) { 
            console.error("Failed to load workspaces", e);
            App.showToast("Connection failed: " + e.message, 'danger');
        }
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
            App.state.collectionProfiles = App.state.projConfig.collection_profiles || {};
            
            // Restore UI Settings from Config
            if (App.state.projConfig.excludes) {
                document.getElementById('excludeInput').value = App.state.projConfig.excludes;
            }
            if (App.state.projConfig.search_settings) {
                document.getElementById('searchMode').value = App.state.projConfig.search_settings.mode || 'smart';
            }
            
            App.updateTemplateList();
            App.updateProfileList();
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
                    settings: {
                        excludes: document.getElementById('excludeInput').value,
                        search_settings: {
                            mode: document.getElementById('searchMode').value
                        }
                    }
                })
            });
        } catch (e) { console.warn("Auto-save settings failed", e); }
    },

    loadGlobalSettings: async () => {
        try {
            const res = await App._fetch('/api/config/global');
            App.state.globalSettings = await res.json();
            // Inject values into modal if open or just keep in state
        } catch (e) { console.error("Failed to load global settings", e); }
    },

    showGlobalSettings: async () => {
        await App.loadGlobalSettings();
        const s = App.state.globalSettings;
        document.getElementById('set-preview-limit').value = s.preview_limit_mb || 1;
        document.getElementById('set-allowed-exts').value = s.allowed_extensions || "";
        document.getElementById('set-noise-reducer').checked = s.enable_noise_reducer || false;
        new bootstrap.Modal(document.getElementById('settingsModal')).show();
    },

    saveGlobalSettings: async () => {
        const body = {
            preview_limit_mb: parseInt(document.getElementById('set-preview-limit').value),
            allowed_extensions: document.getElementById('set-allowed-exts').value,
            enable_noise_reducer: document.getElementById('set-noise-reducer').checked
        };
        try {
            await App._fetch('/api/config/global', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });
            App.state.globalSettings = { ...App.state.globalSettings, ...body };
            App.showToast("Global settings saved successfully");
            bootstrap.Modal.getInstance(document.getElementById('settingsModal')).hide();
        } catch (e) { App.showToast("Failed to save settings: " + e.message, 'danger'); }
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
                        const res = await App._fetch('/api/fs/children', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ path: node.path })
                        });
                        const data = await res.json();
                        childrenContainer.innerHTML = '';
                        data.children.forEach(child => childrenContainer.appendChild(App.renderTree(child)));
                        loaded = true;
                    } catch (err) { 
                        App.showToast("Failed to expand directory: " + err.message, 'danger');
                    }
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
        // [Safety Check] Dirty Check before switching
        if (App.state.isEditing && App.state.currentFile !== path) {
            if (!confirm("Discard unsaved changes and switch file?")) return;
        }
        
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
            
            const ext = path.split('.').pop().toLowerCase();
            codeEl.className = 'hljs h-100 d-block p-4'; // Reset
            
            if (ext === 'md') {
                codeEl.innerHTML = marked.parse(data.content);
                codeEl.classList.remove('hljs');
            } else if (ext === 'mermaid') {
                codeEl.innerHTML = `<div class="mermaid">${App.escapeHtml(data.content)}</div>`;
                await mermaid.run({ nodes: [codeEl.querySelector('.mermaid')] });
                codeEl.classList.remove('hljs');
            } else {
                codeEl.innerText = data.content;
                hljs.highlightElement(codeEl);
            }
        } catch (e) { codeEl.innerText = "Error loading file: " + e.message; }
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
        const tags = App.state.projConfig.tags || {};
        const matchedTags = tags[path] || [];
        if (matchedTags.length === 0) {
            Object.entries(tags).forEach(([key, val]) => {
                if (path && key && path.endsWith(key.split('/').pop())) {
                    matchedTags.push(...val);
                }
            });
        }
        matchedTags.forEach(tag => {
            const span = document.createElement('span');
            span.className = 'badge bg-info text-dark small';
            span.innerText = tag;
            tagContainer.appendChild(span);
        });
    },

    showFileNote: () => {
        if (!App.state.currentFile) return;
        const notes = App.state.projConfig.notes || {};
        let note = notes[App.state.currentFile] || "";
        if (!note) {
            const fileName = App.state.currentFile.split(/[\\\/]/).pop();
            Object.entries(notes).forEach(([key, val]) => {
                if (key.endsWith(fileName)) note = val;
            });
        }
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

    updateProfileList: () => {
        const select = document.getElementById('pathProfileSelect');
        if (!select) return;
        const profiles = App.state.collectionProfiles;
        select.innerHTML = '<option value="">Custom...</option>';
        Object.keys(profiles).forEach(name => {
            const opt = document.createElement('option');
            opt.value = name; opt.innerText = name;
            select.appendChild(opt);
        });
    },

    applyProfile: () => {
        const name = document.getElementById('pathProfileSelect').value;
        if (!name) return;
        const prof = App.state.collectionProfiles[name];
        if (prof) {
            document.getElementById('pathFilePrefix').value = prof.prefix || "";
            document.getElementById('pathDirSuffix').value = prof.suffix || "";
            document.getElementById('pathSep').value = prof.sep || "\\n";
        }
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

    batchRename: async () => {
        const files = Array.from(App.state.selectedFiles);
        if (files.length === 0) return App.showToast("Select files first", 'warning');
        
        const pattern = prompt("Regex Pattern (e.g. ^IMG_(\\d+)):");
        if (!pattern) return;
        const replacement = prompt("Replacement (e.g. Photo_$1):");
        if (replacement === null) return;

        try {
            // First do a Dry Run
            const dryRes = await App._fetch('/api/fs/batch_rename', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    paths: files,
                    pattern: pattern,
                    replacement: replacement,
                    dry_run: true
                })
            });
            const dryData = await dryRes.json();
            
            // Show preview and ask for confirmation
            let previewText = "Preview of changes:\n\n";
            dryData.results.forEach(r => {
                previewText += `${r.old.split(/[\\\/]/).pop()} -> ${r.new.split(/[\\\/]/).pop()} [${r.status}]\n`;
            });
            
            if (!confirm(previewText + "\nProceed with rename?")) return;

            // Do the Live Run
            await App._fetch('/api/fs/batch_rename', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    paths: files,
                    pattern: pattern,
                    replacement: replacement,
                    dry_run: false
                })
            });

            App.showToast("Batch rename completed!");
            App.state.selectedFiles.clear();
            App.updateBulkUI();
            App.refreshProject();
        } catch (e) { App.showToast("Batch rename failed: " + e.message, 'danger'); }
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

        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${proto}//${window.location.host}/ws/search?path=${encodeURIComponent(App.state.projectPath)}&query=${encodeURIComponent(query)}&mode=${mode}`;
        App.state.socket = new WebSocket(wsUrl);
        
        App.state.socket.onopen = () => { resultsDiv.innerHTML = ''; };
        App.state.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.status === "DONE") {
                const count = resultsDiv.querySelectorAll('[data-path]').length;
                if (count === 0) {
                    resultsDiv.innerHTML = '<div class="text-center p-3 text-muted">No results found.</div>';
                } else {
                    const footer = document.createElement('div');
                    footer.className = 'text-center p-2 text-muted x-small border-top';
                    footer.innerText = `${count} results found`;
                    resultsDiv.appendChild(footer);
                }
                return App.state.socket.close();
            }
            if (data.status === "ERROR") {
                resultsDiv.innerHTML = `<div class="text-center p-3 text-danger">${App.escapeHtml(data.msg || 'Search error')}</div>`;
                return App.state.socket.close();
            }
            App.renderSearchResultItem(data);
            resultsDiv.scrollTop = resultsDiv.scrollHeight;
        };
        App.state.socket.onerror = () => {
            resultsDiv.innerHTML = '<div class="text-center p-3 text-danger">Search connection failed.</div>';
        };
    },

    renderSearchResultItem: (data) => {
        const list = document.getElementById('searchResultsList');
        const item = document.createElement('div');
        item.className = 'list-group-item bg-transparent text-white border-0 animate-in p-2 cursor-pointer d-flex align-items-center';
        item.setAttribute('data-path', data.path);
        item.style.cursor = 'pointer';
        
        // Add Checkbox for batch actions
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'form-check-input me-3 x-small';
        cb.style.width = '0.8rem';
        cb.style.height = '0.8rem';
        cb.checked = App.state.selectedFiles.has(data.path);
        cb.onclick = (e) => {
            e.stopPropagation();
            if (cb.checked) App.state.selectedFiles.add(data.path);
            else App.state.selectedFiles.delete(data.path);
            App.updateBulkUI();
        };
        item.appendChild(cb);
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'flex-grow-1 overflow-hidden';
        const snippetHtml = data.snippet ? `<div class="x-small text-warning mt-1 text-truncate border-start border-warning ps-2" style="background: rgba(255,193,7,0.05)">${App.escapeHtml(data.snippet)}</div>` : "";
        contentDiv.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div class="fw-bold text-info">${App.escapeHtml(data.name)}</div>
                <div class="text-muted x-small" style="font-size:0.7rem">${data.mtime_fmt || ''}</div>
            </div>
            <div class="small text-muted text-truncate">${App.escapeHtml(data.path)}</div>
            ${snippetHtml}
        `;
        item.appendChild(contentDiv);
        
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
            // We keep staging files that might have failed if backend supports it, 
            // but currently backend moves all or none in core.
            App.state.staging.clear();
            App.renderStaging();
            App.syncStagingToBackend();
            App.refreshProject();
        } catch (e) { App.showToast("Error: " + e.message, 'danger'); }
        finally { if (btn) { btn.innerText = originalText; btn.disabled = false; } }
    },

    executeToolOnStaged: async (toolName) => {
        if (App.state.staging.size === 0) return App.showToast("Add files to staging first.", 'warning');
        
        const modalWrapper = document.getElementById('toolResultModal');
        const modalBody = document.getElementById('toolResultModalBody');
        const modalHeader = document.querySelector('#toolResultModal .modal-header');
        
        const bsModal = new bootstrap.Modal(modalWrapper);
        bsModal.show();

        const paths = Array.from(App.state.staging);
        modalBody.innerHTML = `<div class="p-4 text-center">Preparing to execute ${toolName} on ${paths.length} items...</div>`;
        
        // Add Stop button to header if it doesn't exist
        let stopBtn = document.getElementById('btnStopTool');
        if (!stopBtn) {
            stopBtn = document.createElement('button');
            stopBtn.id = 'btnStopTool';
            stopBtn.className = 'btn btn-outline-danger btn-sm ms-auto me-3';
            stopBtn.innerText = '🛑 Stop';
            stopBtn.onclick = () => App.terminateProcess();
            modalHeader.insertBefore(stopBtn, modalHeader.lastElementChild);
        }
        stopBtn.style.display = 'none';

        // Helper for sequential execution
        const runNext = async (index) => {
            if (index >= paths.length) {
                modalBody.innerHTML += `<div class="p-3 border-top border-secondary text-success fw-bold">✨ All ${paths.length} tasks completed.</div>`;
                if (confirm("Tasks finished. Clear staging?")) {
                    App.state.staging.clear();
                    App.renderStaging();
                    App.syncStagingToBackend();
                }
                return;
            }

            const path = paths[index];
            const fileName = path.split(/[\\\/]/).pop();
            const logId = `tool-log-${index}`;
            
            modalBody.innerHTML += `<div class="p-2 border-bottom border-secondary x-small text-muted bg-dark">(${index+1}/${paths.length}) Executing on: ${fileName}</div>
                                   <pre id="${logId}" class="m-0 p-3" style="background:#000; color:#0f0; font-family:monospace; min-height:150px; white-space:pre-wrap; font-size: 12px;"></pre>`;
            
            const outputDiv = document.getElementById(logId);
            const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProto}//${window.location.host}/ws/actions/execute?project_path=${encodeURIComponent(App.state.projectPath)}&tool_name=${encodeURIComponent(toolName)}&path=${encodeURIComponent(path)}`;
            
            return new Promise((resolve) => {
                const socket = new WebSocket(wsUrl);
                socket.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    if (data.pid) {
                        App.state.activePid = data.pid;
                        stopBtn.style.display = 'block';
                    }
                    if (data.out && outputDiv) {
                        outputDiv.innerText += data.out;
                        outputDiv.scrollTop = outputDiv.scrollHeight;
                        modalWrapper.querySelector('.modal-body').scrollTop = modalWrapper.querySelector('.modal-body').scrollHeight;
                    }
                    if (data.exit_code !== undefined || data.status === "DONE" || data.error) {
                        stopBtn.style.display = 'none';
                        App.state.activePid = null;
                        if (data.error) outputDiv.innerText += `\nERROR: ${data.error}`;
                        if (data.exit_code !== undefined) outputDiv.innerText += `\n[Process exited with code: ${data.exit_code}]`;
                        socket.close();
                        resolve();
                    }
                };
                socket.onerror = () => { resolve(); };
            }).then(() => runNext(index + 1));
        };

        await runNext(0);
    },

    terminateProcess: async () => {
        if (!App.state.activePid) return;
        try {
            const res = await App._fetch('/api/actions/terminate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ pid: App.state.activePid })
            });
            App.showToast("Termination signal sent");
        } catch (e) { App.showToast("Termination failed: " + e.message, 'danger'); }
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
            label.innerText = "0 Tokens";
            label.classList.remove('pulse-warning');
            return;
        }

        try {
            const res = await App._fetch('/api/project/stats', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    paths: Array.from(App.state.staging),
                    project_path: App.state.projectPath
                })
            });
            const data = await res.json();
            const threshold = (App.state.globalSettings && App.state.globalSettings.token_threshold) || 128000;
            label.innerText = `${data.file_count} Files | ${data.total_tokens.toLocaleString()} Tokens`;
            
            // Remove all possible state classes
            label.classList.remove('bg-info', 'bg-warning', 'bg-danger', 'pulse-warning');
            
            if (data.total_tokens > threshold) {
                label.classList.add('bg-danger', 'pulse-warning');
                label.title = "CRITICAL: Token Count Exceeds Budget!";
            } else if (data.total_tokens > threshold * 0.7) {
                label.classList.add('bg-warning', 'text-dark');
                label.title = "Warning: High Token Count";
            } else {
                label.classList.add('bg-info');
                label.title = "Tokens within budget";
            }
        } catch (e) {
            label.innerText = `${count} Items`;
            label.classList.remove('pulse-warning');
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
            const format = document.getElementById('exportFormat').value;
            const res = await App._fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    files: Array.from(App.state.staging),
                    project_path: App.state.projectPath,
                    template_name: templateName,
                    export_format: format
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
        // [Fix Bug 1] Sync memory AND UI checkboxes
        const allItems = document.querySelectorAll('.tree-node[data-path], .list-group-item[data-path]');
        allItems.forEach(item => {
            const path = item.getAttribute('data-path');
            if (path) {
                if (checked) App.state.selectedFiles.add(path);
                const cb = item.querySelector('.form-check-input');
                if (cb) cb.checked = checked;
            }
        });
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

    clearStaging: () => {
        if (App.state.staging.size === 0) return;
        if (!confirm("Clear whole staging list?")) return;
        App.state.staging.clear();
        App.renderStaging();
        App.syncStagingToBackend();
        App.showToast("Staging cleared");
    },

    stageAll: async () => {
        if (!App.state.projectPath) return;
        try {
            const res = await App._fetch('/api/actions/stage_all', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    mode: 'files',
                    apply_excludes: true
                })
            });
            const data = await res.json();
            await App.refreshProject();
            App.showToast(`Staged ${data.added_count} files`);
        } catch (e) { App.showToast("Stage All failed: " + e.message, 'danger'); }
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
        const file_prefix = document.getElementById('pathFilePrefix').value;
        const dir_suffix = document.getElementById('pathDirSuffix').value;
        const project_root = App.state.projectPath;

        try {
            const res = await App._fetch('/api/fs/collect_paths', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    paths: paths,
                    project_root: project_root,
                    mode: mode,
                    separator: separator,
                    file_prefix: file_prefix,
                    dir_suffix: dir_suffix
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
    },

    openInExplorer: async (path) => {
        try {
            await App._fetch('/api/open', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ path: path })
            });
        } catch (e) {
            App.showToast("Failed to open path: " + e.message, "danger");
        }
    },

    showContextMenu: (e, path) => {
        App.state.contextPath = path;
        const menu = document.getElementById('customContextMenu');
        menu.style.display = 'block';
        menu.style.left = e.clientX + 'px';
        menu.style.top = e.clientY + 'px';
    },

    hideContextMenu: () => {
        const menu = document.getElementById('customContextMenu');
        if (menu) menu.style.display = 'none';
        App.state.contextPath = null;
    },

    ctxAction: async (action) => {
        const path = App.state.contextPath;
        if (!path) return;
        
        switch (action) {
            case 'stage': 
                App.state.staging.add(path);
                App.renderStaging();
                App.syncStagingToBackend();
                App.showToast("Added to Staging");
                break;
            case 'fav': 
                const savedFile = App.state.currentFile;
                App.state.currentFile = path;
                await App.addToFavorites();
                App.state.currentFile = savedFile;
                break;
            case 'copyPath':
                try {
                    await navigator.clipboard.writeText(path);
                    App.showToast("Path Copied");
                } catch (_) { App.showToast("Copy failed", 'danger'); }
                break;
            case 'openOs':
                App.openInExplorer(path);
                break;
            case 'delete':
                const savedCurrent = App.state.currentFile;
                App.state.currentFile = path;
                await App.deleteFile();
                App.state.currentFile = savedCurrent;
                break;
        }
        App.hideContextMenu();
    },

    updatePinUI: (isPinned) => {
        const btn = document.getElementById('btnPin');
        if (!btn) return;
        btn.innerText = isPinned ? 'Pinned' : 'Pin';
        btn.classList.toggle('btn-warning', isPinned);
        btn.classList.toggle('btn-outline-warning', !isPinned);
    },

    persistSearchUiState: () => {
        const settings = App.getSearchUiSettings();
        localStorage.setItem(App.config.storageKeys.excludes, settings.excludes || '');
        localStorage.setItem(App.config.storageKeys.mode, settings.mode);
        localStorage.setItem(App.config.storageKeys.includeDirs, settings.includeDirs);
        localStorage.setItem(App.config.storageKeys.caseSensitive, settings.caseSensitive);
        localStorage.setItem(App.config.storageKeys.inverse, settings.inverse);
    },

    restoreSearchUiState: () => {
        const assignBool = (id, key) => {
            const el = document.getElementById(id);
            if (el) el.checked = localStorage.getItem(key) === 'true';
        };
        assignBool('searchIncludeDirs', App.config.storageKeys.includeDirs);
        assignBool('searchCaseSensitive', App.config.storageKeys.caseSensitive);
        assignBool('searchInverse', App.config.storageKeys.inverse);
    },

    getSearchUiSettings: () => ({
        mode: document.getElementById('searchMode').value,
        includeDirs: document.getElementById('searchIncludeDirs').checked,
        caseSensitive: document.getElementById('searchCaseSensitive').checked,
        inverse: document.getElementById('searchInverse').checked,
        excludes: document.getElementById('excludeInput').value
    }),

    updateWorkspaceSummary: () => {
        const projectPath = App.state.projectPath;
        const projectName = document.getElementById('summaryProjectName');
        const searchState = document.getElementById('summarySearchState');
        const stageCount = document.getElementById('summaryStageCount');
        const favoriteCount = document.getElementById('summaryFavoriteCount');
        const categoryCount = document.getElementById('summaryCategoryCount');
        const toolCount = document.getElementById('summaryToolCount');

        if (projectName) {
            projectName.innerText = projectPath
                ? projectPath.split(/[\\\/]/).pop()
                : 'No workspace loaded';
        }

        if (searchState) {
            const searchSettings = App.getSearchUiSettings();
            const parts = [searchSettings.mode];
            if (searchSettings.includeDirs) parts.push('dirs');
            if (searchSettings.caseSensitive) parts.push('case');
            if (searchSettings.inverse) parts.push('inverse');
            searchState.innerText = projectPath ? parts.join(' | ') : 'Search disabled';
        }

        if (stageCount) stageCount.innerText = `${App.state.staging.size} staged`;

        const groups = App.state.projConfig.groups || {};
        const favoriteTotal = Object.values(groups).reduce((acc, items) => acc + items.length, 0);
        if (favoriteCount) favoriteCount.innerText = `${favoriteTotal} favorites`;
        if (categoryCount) categoryCount.innerText = `${Object.keys(App.state.projConfig.quick_categories || {}).length} categories`;
        if (toolCount) toolCount.innerText = `${Object.keys(App.state.projConfig.custom_tools || {}).length} tools`;
    },

    showActionModal: ({ title, bodyHtml, confirmText = 'Confirm', onConfirm }) => {
        document.getElementById('actionModalTitle').innerText = title;
        document.getElementById('actionModalBody').innerHTML = bodyHtml;
        document.getElementById('actionModalConfirm').innerText = confirmText;
        App.state.actionModalHandler = onConfirm;
        new bootstrap.Modal(document.getElementById('actionModal')).show();
    },

    closeActionModal: () => {
        const modalEl = document.getElementById('actionModal');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
        App.state.actionModalHandler = null;
    },

    loadTreeChildren: async (node, childrenContainer) => {
        const res = await App._fetch('/api/fs/children', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ path: node.path })
        });
        const data = await res.json();
        childrenContainer.innerHTML = '';

        if (!data.children || data.children.length === 0) {
            childrenContainer.innerHTML = `
                <div class="empty-state py-2">
                    <div class="small text-muted">Empty folder</div>
                </div>
            `;
            return;
        }

        data.children.forEach((child) => {
            childrenContainer.appendChild(App.renderTree(child));
        });
    },

    renderTree: (node, options = {}) => {
        const { initialExpand = false } = options;
        const container = document.createElement('div');
        container.className = 'ms-1';

        const header = document.createElement('div');
        header.className = 'tree-node d-flex align-items-center text-truncate animate-in';
        header.setAttribute('data-path', node.path);

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
        } else {
            const toggle = document.createElement(node.has_children ? 'button' : 'span');
            toggle.className = node.has_children ? 'tree-toggle' : 'tree-toggle-spacer';
            toggle.textContent = node.has_children ? (initialExpand ? '▾' : '▸') : '•';
            if (node.has_children) {
                toggle.type = 'button';
                toggle.tabIndex = -1;
            }
            header.appendChild(toggle);
        }

        const icon = node.type === 'dir' ? 'Folder' : 'File';
        const metaInfo = node.type === 'file' ? ` (${node.size_fmt})` : '';
        const nameSpan = document.createElement('span');
        nameSpan.className = 'flex-grow-1 text-truncate';
        nameSpan.innerHTML = `
            <span class="me-2 text-info-emphasis">${icon}</span>
            <span>${App.escapeHtml(node.name)}</span>
            <span class="ms-2 text-muted x-small d-none d-lg-inline" style="font-size:0.7rem">${node.mtime_fmt || ''}${metaInfo}</span>
        `;
        header.appendChild(nameSpan);
        container.appendChild(header);

        if (node.type === 'dir') {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'tree-children';
            childrenContainer.style.display = initialExpand ? 'block' : 'none';
            if (initialExpand) {
                childrenContainer.innerHTML = '<div class="small text-muted px-2 py-1">Loading...</div>';
            }
            container.appendChild(childrenContainer);

            let loaded = false;
            const toggleEl = header.querySelector('.tree-toggle');
            const setExpandedState = (expanded) => {
                childrenContainer.style.display = expanded ? 'block' : 'none';
                if (toggleEl) toggleEl.textContent = expanded ? '▾' : '▸';
            };

            const expandDirectory = async () => {
                const isHidden = childrenContainer.style.display === 'none';
                if (isHidden && !loaded) {
                    try {
                        await App.loadTreeChildren(node, childrenContainer);
                        loaded = true;
                    } catch (err) {
                        childrenContainer.innerHTML = '<div class="small text-danger px-2 py-1">Failed to load folder.</div>';
                        App.showToast("Failed to expand directory: " + err.message, 'danger');
                    }
                }
                setExpandedState(isHidden);
            };

            header.onclick = async (e) => {
                e.stopPropagation();
                await expandDirectory();
            };

            if (initialExpand) {
                Promise.resolve().then(async () => {
                    try {
                        await App.loadTreeChildren(node, childrenContainer);
                        loaded = true;
                        setExpandedState(true);
                    } catch (err) {
                        childrenContainer.innerHTML = '<div class="small text-danger px-2 py-1">Failed to load folder.</div>';
                        App.showToast("Failed to load workspace tree: " + err.message, 'danger');
                    }
                });
            }
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

    openProject: async (path = null) => {
        const p = path || document.getElementById('projectPath').value.trim();
        if (!p) return;

        try {
            const res = await App._fetch(App.config.endpoints.openProject, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ path: p })
            });
            const data = await res.json();

            App.state.projectPath = p;
            document.getElementById('projectPath').value = p;
            localStorage.setItem(App.config.storageKeys.lastProjectPath, p);

            const configRes = await App._fetch(`/api/project/config?path=${encodeURIComponent(p)}`);
            App.state.projConfig = await configRes.json();
            App.state.collectionProfiles = App.state.projConfig.collection_profiles || {};

            if (App.state.projConfig.excludes) {
                document.getElementById('excludeInput').value = App.state.projConfig.excludes;
            }
            if (App.state.projConfig.search_settings) {
                const searchSettings = App.state.projConfig.search_settings;
                document.getElementById('searchMode').value = searchSettings.mode || 'smart';
                document.getElementById('searchCaseSensitive').checked = Boolean(searchSettings.case_sensitive);
                document.getElementById('searchInverse').checked = Boolean(searchSettings.inverse);
                document.getElementById('searchIncludeDirs').checked = Boolean(searchSettings.include_dirs);
            }
            App.persistSearchUiState();

            App.updateTemplateList();
            App.updateProfileList();
            App.state.staging = new Set(App.state.projConfig.staging_list || []);

            const rootContainer = document.getElementById('fileTreeRoot');
            rootContainer.innerHTML = '<div class="small text-muted px-2 py-1">Loading workspace tree...</div>';
            const rootTree = App.renderTree(data, { initialExpand: true });
            rootContainer.innerHTML = '';
            rootContainer.appendChild(rootTree);
            App.renderStaging();
            App.renderFavorites();
            App.renderActions();
            await App.loadWorkspaces();
            App.updateWorkspaceSummary();

            App.showToast(`Opened project: ${data.name}`);
        } catch (e) {
            App.showToast("Error: " + e.message, 'danger');
        }
    },

    saveSettings: async () => {
        if (!App.state.projectPath) return;
        try {
            const searchSettings = App.getSearchUiSettings();
            await App._fetch('/api/project/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    settings: {
                        excludes: searchSettings.excludes,
                        search_settings: {
                            mode: searchSettings.mode,
                            case_sensitive: searchSettings.caseSensitive,
                            inverse: searchSettings.inverse,
                            include_dirs: searchSettings.includeDirs
                        }
                    }
                })
            });
            App.persistSearchUiState();
        } catch (e) {
            console.warn("Auto-save settings failed", e);
        }
    },

    loadGlobalSettings: async () => {
        try {
            const res = await App._fetch('/api/config/global');
            App.state.globalSettings = await res.json();
        } catch (e) {
            console.error("Failed to load global settings", e);
        }
    },

    showGlobalSettings: async () => {
        await App.loadGlobalSettings();
        const s = App.state.globalSettings || {};
        document.getElementById('set-preview-limit').value = s.preview_limit_mb || 1;
        document.getElementById('set-token-threshold').value = s.token_threshold || App.config.defaults.tokenThreshold;
        document.getElementById('set-token-ratio').value = s.token_ratio || App.config.defaults.tokenRatio;
        document.getElementById('set-allowed-exts').value = s.allowed_extensions || "";
        document.getElementById('set-noise-reducer').checked = Boolean(s.enable_noise_reducer);
        new bootstrap.Modal(document.getElementById('settingsModal')).show();
    },

    saveGlobalSettings: async () => {
        const body = {
            preview_limit_mb: parseFloat(document.getElementById('set-preview-limit').value),
            token_threshold: parseInt(document.getElementById('set-token-threshold').value || App.config.defaults.tokenThreshold, 10),
            token_ratio: parseFloat(document.getElementById('set-token-ratio').value || App.config.defaults.tokenRatio),
            allowed_extensions: document.getElementById('set-allowed-exts').value,
            enable_noise_reducer: document.getElementById('set-noise-reducer').checked
        };
        try {
            await App._fetch('/api/config/global', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });
            App.state.globalSettings = { ...App.state.globalSettings, ...body };
            App.updateStats();
            App.showToast("Global settings saved successfully");
            bootstrap.Modal.getInstance(document.getElementById('settingsModal')).hide();
        } catch (e) {
            App.showToast("Failed to save settings: " + e.message, 'danger');
        }
    },

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
            App.showToast("Note saved", 'success');
        } catch (e) {
            App.showToast("Save failed: " + e.message, 'danger');
        }
    },

    copyPath: async () => {
        if (!App.state.currentFile) return;
        try {
            await navigator.clipboard.writeText(App.state.currentFile);
            const btn = document.getElementById('btnCopyPath');
            const originalText = btn ? btn.innerText : 'Copy Path';
            if (btn) btn.innerText = 'Copied';
            setTimeout(() => {
                if (btn) btn.innerText = originalText;
            }, 1000);
            App.showToast("Path copied", 'success');
        } catch (e) {
            App.showToast("Failed to copy path", 'danger');
        }
    },

    renderStaging: () => {
        const list = document.getElementById('stagingList');
        list.innerHTML = '';
        if (App.state.staging.size === 0) {
            list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">+</div><div>No staged files yet.</div></div>';
            App.updateStats();
            App.updateWorkspaceSummary();
            return;
        }
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
        App.updateWorkspaceSummary();
    },

    renderFavorites: () => {
        const list = document.getElementById('favoritesList');
        const select = document.getElementById('favGroupSelect');
        list.innerHTML = '';
        select.innerHTML = '';

        if (!App.state.projConfig || !App.state.projConfig.groups) {
            App.updateWorkspaceSummary();
            return;
        }

        const groups = Object.keys(App.state.projConfig.groups);
        groups.forEach((g) => {
            const opt = document.createElement('option');
            opt.value = g;
            opt.innerText = g;
            select.appendChild(opt);
        });
        select.value = App.state.projConfig.current_group || groups[0] || "Default";

        const currentGroup = select.value || "Default";
        const files = App.state.projConfig.groups[currentGroup] || [];
        if (files.length === 0) {
            list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">*</div><div>No favorites in this group.</div></div>';
            App.updateWorkspaceSummary();
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
        App.updateWorkspaceSummary();
    },

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
            App.updateWorkspaceSummary();
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
        App.updateWorkspaceSummary();
    },

    updateStats: async () => {
        if (App._statsTimer) clearTimeout(App._statsTimer);
        App._statsTimer = setTimeout(App._updateStatsImpl, 300);
        App.updateWorkspaceSummary();
    },

    _updateStatsImpl: async () => {
        const count = App.state.staging.size;
        const label = document.getElementById('tokenEstimate');
        if (!label) return;

        if (count === 0) {
            label.innerText = "0 Tokens";
            label.classList.remove('pulse-warning', 'bg-warning', 'bg-danger', 'text-dark');
            label.classList.add('bg-info');
            return;
        }

        try {
            const res = await App._fetch('/api/project/stats', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    paths: Array.from(App.state.staging),
                    project_path: App.state.projectPath
                })
            });
            const data = await res.json();
            const threshold = (App.state.globalSettings && App.state.globalSettings.token_threshold)
                || App.config.defaults.tokenThreshold;
            label.innerText = `${data.file_count} Files | ${data.total_tokens.toLocaleString()} Tokens`;
            label.classList.remove('bg-info', 'bg-warning', 'bg-danger', 'pulse-warning', 'text-dark');

            if (data.total_tokens > threshold) {
                label.classList.add('bg-danger', 'pulse-warning');
                label.title = "CRITICAL: Token Count Exceeds Budget!";
            } else if (data.total_tokens > threshold * 0.7) {
                label.classList.add('bg-warning', 'text-dark');
                label.title = "Warning: High Token Count";
            } else {
                label.classList.add('bg-info');
                label.title = "Tokens within budget";
            }
        } catch (e) {
            label.innerText = `${count} Items`;
            label.classList.remove('pulse-warning');
        }
    },

    archiveStaging: async () => {
        if (App.state.staging.size === 0) {
            App.showToast("Select files first.", 'warning');
            return;
        }

        App.showActionModal({
            title: 'Archive staged files',
            confirmText: 'Archive',
            bodyHtml: `
                <label class="form-label small text-muted">Archive name</label>
                <input type="text" id="archiveNameInput" class="form-control bg-dark text-white border-secondary"
                    value="${App.config.defaults.archiveName}">
            `,
            onConfirm: async () => {
                const name = document.getElementById('archiveNameInput').value.trim();
                if (!name) {
                    App.showToast("Archive name is required", 'warning');
                    return;
                }
                try {
                    const btn = document.getElementById('btnArchiveSelection');
                    const originalText = btn.innerText;
                    btn.innerText = 'Archiving...';
                    btn.disabled = true;
                    await App._fetch('/api/fs/archive', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            paths: Array.from(App.state.staging),
                            output_name: name,
                            project_root: App.state.projectPath
                        })
                    });
                    App.closeActionModal();
                    App.showToast(`Archived to ${name}`, 'success');
                    btn.innerText = originalText;
                    btn.disabled = false;
                } catch (e) {
                    App.showToast(e.message, 'danger');
                }
            }
        });
    },

    renameFile: async () => {
        if (!App.state.currentFile) return;
        const oldName = App.state.currentFile.split(/[\\\/]/).pop();
        App.showActionModal({
            title: 'Rename file',
            confirmText: 'Rename',
            bodyHtml: `
                <label class="form-label small text-muted">New name</label>
                <input type="text" id="renameFileInput" class="form-control bg-dark text-white border-secondary"
                    value="${App.escapeHtml(oldName)}">
            `,
            onConfirm: async () => {
                const newName = document.getElementById('renameFileInput').value.trim();
                if (!newName || newName === oldName) {
                    App.closeActionModal();
                    return;
                }
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
                    App.closeActionModal();
                    App.showToast("Renamed successfully");
                    App.openProject();
                    App.state.currentFile = null;
                    document.getElementById('fileControls').style.display = 'none';
                } catch (e) {
                    App.showToast("Rename failed: " + e.message, 'danger');
                }
            }
        });
    },

    deleteFile: async () => {
        if (!App.state.currentFile) return;
        App.showActionModal({
            title: 'Delete file',
            confirmText: 'Delete',
            bodyHtml: `<p class="mb-0">Delete <strong>${App.escapeHtml(App.state.currentFile.split(/[\\\/]/).pop())}</strong>? This cannot be undone.</p>`,
            onConfirm: async () => {
                try {
                    await App._fetch('/api/fs/delete', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            project_path: App.state.projectPath,
                            paths: [App.state.currentFile]
                        })
                    });
                    App.closeActionModal();
                    App.openProject();
                    App.state.currentFile = null;
                    document.getElementById('fileControls').style.display = 'none';
                    App.showToast("File deleted", 'success');
                } catch (e) {
                    App.showToast("Delete failed: " + e.message, 'danger');
                }
            }
        });
    },

    batchRename: async () => {
        const files = Array.from(App.state.selectedFiles);
        if (files.length === 0) return App.showToast("Select files first", 'warning');

        App.showActionModal({
            title: 'Batch rename',
            confirmText: 'Preview',
            bodyHtml: `
                <div class="mb-3">
                    <label class="form-label small text-muted">Regex pattern</label>
                    <input type="text" id="batchRenamePattern" class="form-control bg-dark text-white border-secondary"
                        placeholder="e.g. ^IMG_(\\d+)">
                </div>
                <div class="mb-0">
                    <label class="form-label small text-muted">Replacement</label>
                    <input type="text" id="batchRenameReplacement" class="form-control bg-dark text-white border-secondary"
                        placeholder="e.g. Photo_$1">
                </div>
            `,
            onConfirm: async () => {
                const pattern = document.getElementById('batchRenamePattern').value;
                const replacement = document.getElementById('batchRenameReplacement').value;
                if (!pattern) {
                    App.showToast("Pattern is required", 'warning');
                    return;
                }

                try {
                    const dryRes = await App._fetch('/api/fs/batch_rename', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            project_path: App.state.projectPath,
                            paths: files,
                            pattern,
                            replacement,
                            dry_run: true
                        })
                    });
                    const dryData = await dryRes.json();
                    const previewHtml = dryData.results.map(
                        (r) => `<div class="small mb-1">${App.escapeHtml(r.old.split(/[\\\/]/).pop())} &rarr; ${App.escapeHtml(r.new.split(/[\\\/]/).pop())} <span class="text-muted">[${App.escapeHtml(r.status)}]</span></div>`
                    ).join('');
                    App.showActionModal({
                        title: 'Confirm batch rename',
                        confirmText: 'Rename',
                        bodyHtml: `<div class="small text-muted mb-2">Preview of changes</div>${previewHtml || '<div class="small">No matching files.</div>'}`,
                        onConfirm: async () => {
                            await App._fetch('/api/fs/batch_rename', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({
                                    project_path: App.state.projectPath,
                                    paths: files,
                                    pattern,
                                    replacement,
                                    dry_run: false
                                })
                            });
                            App.closeActionModal();
                            App.showToast("Batch rename completed!");
                            App.state.selectedFiles.clear();
                            App.updateBulkUI();
                            App.refreshProject();
                        }
                    });
                } catch (e) {
                    App.showToast("Batch rename failed: " + e.message, 'danger');
                }
            }
        });
    },

    startSearch: () => {
        if (!App.state.projectPath) return;
        const settings = App.getSearchUiSettings();
        App.persistSearchUiState();
        App.updateWorkspaceSummary();
        const query = document.getElementById('searchInput').value;
        const tab = new bootstrap.Tab(document.getElementById('tab-search'));
        tab.show();

        const resultsDiv = document.getElementById('searchResultsList');
        resultsDiv.innerHTML = '<div class="text-center p-3">Searching...</div>';

        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const token = App.state.globalSettings.api_token || "";
        const wsUrl = `${proto}//${window.location.host}/ws/search?path=${encodeURIComponent(App.state.projectPath)}&query=${encodeURIComponent(query)}&mode=${settings.mode}&inverse=${settings.inverse}&case_sensitive=${settings.caseSensitive}&include_dirs=${settings.include_dirs}${token ? `&token=${encodeURIComponent(token)}` : ''}`;


        App.state.socket = new WebSocket(wsUrl);
        App.state.socket.onopen = () => { resultsDiv.innerHTML = ''; };
        App.state.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.status === "DONE") {
                const count = resultsDiv.querySelectorAll('[data-path]').length;
                if (count === 0) {
                    resultsDiv.innerHTML = '<div class="empty-state"><div class="empty-state-icon">?</div><div>No results found.</div></div>';
                } else {
                    const footer = document.createElement('div');
                    footer.className = 'text-center p-2 text-muted x-small border-top';
                    footer.innerText = `${count} results found`;
                    resultsDiv.appendChild(footer);
                }
                return App.state.socket.close();
            }
            if (data.status === "ERROR") {
                resultsDiv.innerHTML = `<div class="text-center p-3 text-danger">${App.escapeHtml(data.msg || 'Search error')}</div>`;
                return App.state.socket.close();
            }
            App.renderSearchResultItem(data);
            resultsDiv.scrollTop = resultsDiv.scrollHeight;
        };
        App.state.socket.onerror = () => {
            resultsDiv.innerHTML = '<div class="text-center p-3 text-danger">Search connection failed.</div>';
        };
    },

    bulkMove: async () => {
        if (App.state.selectedFiles.size === 0) return;
        App.showActionModal({
            title: 'Move selected files',
            confirmText: 'Move',
            bodyHtml: `
                <label class="form-label small text-muted">Destination directory (within the project)</label>
                <input type="text" id="bulkMoveInput" class="form-control bg-dark text-white border-secondary"
                    placeholder="Destination directory path">
            `,
            onConfirm: async () => {
                const dstDir = document.getElementById('bulkMoveInput').value.trim();
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
                    App.closeActionModal();
                    App.showToast(`Batch Move: ${data.new_paths.length} items moved.`);
                    App.state.selectedFiles.clear();
                    App.updateBulkUI();
                    App.openProject();
                } catch (e) {
                    App.showToast("Move failed: " + e.message, 'danger');
                }
            }
        });
    },

    generateContext: async () => {
        if (App.state.staging.size === 0) return;
        const templateName = document.getElementById('promptTemplate').value;
        const btn = document.getElementById('btnGenerateContext');
        const originalText = btn.innerText;
        btn.innerText = "Generating...";
        btn.disabled = true;

        try {
            const format = document.getElementById('exportFormat').value;
            const includeBlueprint = document.getElementById('includeBlueprint')?.checked || false;
            const res = await App._fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    files: Array.from(App.state.staging),
                    project_path: App.state.projectPath,
                    template_name: templateName,
                    export_format: format,
                    include_blueprint: includeBlueprint
                })
            });
            const data = await res.json();
            await navigator.clipboard.writeText(data.content);
            App.showToast("Context copied", 'success');
        } catch (e) {
            App.showToast("Failed to generate context: " + e.message, 'danger');
        } finally {
            btn.innerText = originalText;
            btn.disabled = false;
        }
    },

    openInExplorer: async (path) => {
        try {
            await App._fetch(App.config.endpoints.openPathInOs, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    project_path: App.state.projectPath,
                    path: path
                })
            });
        } catch (e) {
            App.showToast("Failed to open path: " + e.message, "danger");
        }
    },

    openCurrentInExplorer: async () => {
        if (!App.state.currentFile) return;
        await App.openInExplorer(App.state.currentFile);
    }
};

// Initialize App
document.addEventListener('DOMContentLoaded', () => App.init());
