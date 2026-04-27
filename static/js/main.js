import { state, config, escapeHtml } from './state.js';
import * as api from './api.js';
import * as ui from './ui.js';

const App = {
    state,
    config,
    escapeHtml,
    
    // API Bindings
    ...api,
    
    // UI Bindings
    ...ui,

    init: async () => {
        await App.loadGlobalSettings();
        await App.loadWorkspaces();
        
        const searchInput = document.getElementById('searchInput');
        let searchTimer;
        if (searchInput) {
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
        }
        
        // Context Menu Handler
        window.addEventListener('click', () => App.hideContextMenu());
        window.addEventListener('contextmenu', (e) => {
            const target = e.target.closest('[data-path]');
            if (target) {
                e.preventDefault();
                App.showContextMenu(e, target.getAttribute('data-path'));
            }
        });
        
        // Editor Shortcuts
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
                const helpModal = document.getElementById('helpModal');
                if (helpModal) new bootstrap.Modal(helpModal).show();
            }
            if (e.key === 'Escape') App.hideContextMenu();
        });

        // Restore search settings from localStorage
        const savedExcludes = localStorage.getItem(App.config.storageKeys.excludes);
        const excludeIn = document.getElementById('excludeInput');
        if (savedExcludes && excludeIn) excludeIn.value = savedExcludes;
        App.restoreSearchUiState();
        
        ['searchMode', 'searchIncludeDirs', 'searchCaseSensitive', 'searchInverse', 'excludeInput', 'searchInput']
            .forEach((id) => {
                const el = document.getElementById(id);
                if (!el) return;
                const eventType = el.tagName === 'INPUT' && el.type === 'text' ? 'input' : 'change';
                el.addEventListener(eventType, () => {
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
            const pathInput = document.getElementById('projectPath');
            if (pathInput) pathInput.value = lastProj;
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

    toggleSidebar: () => {
        const sb = document.getElementById('workspaceSidebar');
        if (!sb) return;
        App.state.isSidebarExpanded = !App.state.isSidebarExpanded;
        sb.style.width = App.state.isSidebarExpanded
            ? App.config.ui.sidebarWidths.expanded
            : App.config.ui.sidebarWidths.collapsed;
        localStorage.setItem(
            App.config.storageKeys.sidebarExpanded,
            App.state.isSidebarExpanded
        );
        // Refresh workspaces to update name/icon
        App.loadWorkspaces();
    },

    loadWorkspaces: async () => {
        try {
            const data = await api.loadWorkspaces();
            ui.renderWorkspaces(data);
        } catch (e) {
            console.error(e);
            ui.showToast(e.message, 'danger');
        }
    },

    togglePin: async () => {
        if (!App.state.projectPath) return;
        try {
            const data = await api.togglePin(App.state.projectPath);
            ui.updatePinUI(data.is_pinned);
            await App.loadWorkspaces();
        } catch (e) { ui.showToast("Pin failed: " + e.message, 'danger'); }
    },

    openProject: async (path = null) => {
        const p = path || document.getElementById('projectPath').value.trim();
        if (!p) return;

        try {
            const data = await api.openProject(p);
            App.state.projectPath = p;
            const pathInput = document.getElementById('projectPath');
            if (pathInput) pathInput.value = p;
            localStorage.setItem(App.config.storageKeys.lastProjectPath, p);
            
            App.state.projConfig = await api.fetchProjectConfig(p);
            App.state.collectionProfiles = App.state.projConfig.collection_profiles || {};
            
            // Restore UI Settings from Config
            if (App.state.projConfig.excludes) {
                const exInput = document.getElementById('excludeInput');
                if (exInput) exInput.value = App.state.projConfig.excludes;
            }
            if (App.state.projConfig.search_settings) {
                const searchSettings = App.state.projConfig.search_settings;
                const modeSelect = document.getElementById('searchMode');
                if (modeSelect) modeSelect.value = searchSettings.mode || 'smart';
                const caseCb = document.getElementById('searchCaseSensitive');
                if (caseCb) caseCb.checked = Boolean(searchSettings.case_sensitive);
                const invCb = document.getElementById('searchInverse');
                if (invCb) invCb.checked = Boolean(searchSettings.inverse);
                const dirCb = document.getElementById('searchIncludeDirs');
                if (dirCb) dirCb.checked = Boolean(searchSettings.include_dirs);
            }
            App.persistSearchUiState();
            
            App.updateTemplateList();
            App.updateProfileList();
            App.state.staging = new Set(App.state.projConfig.staging_list || []);

            const rootContainer = document.getElementById('fileTreeRoot');
            if (rootContainer) {
                rootContainer.innerHTML = '<div class="small text-muted px-2 py-1">Loading workspace tree...</div>';
                const rootTree = ui.renderTree(data, { initialExpand: true });
                rootContainer.innerHTML = '';
                rootContainer.appendChild(rootTree);
            }
            ui.renderStaging();
            ui.renderFavorites();
            ui.renderActions();
            await App.loadWorkspaces();
            ui.updateWorkspaceSummary();

            ui.showToast(`Opened project: ${data.name}`);
        } catch (e) { ui.showToast("Error: " + e.message, 'danger'); }
    },

    refreshProject: async () => {
        if (!App.state.projectPath) return;
        await App.saveSettings();
        await App.openProject(App.state.projectPath);
    },

    saveSettings: async () => {
        if (!App.state.projectPath) return;
        try {
            const searchSettings = App.getSearchUiSettings();
            await api.saveProjectSettings(App.state.projectPath, {
                excludes: searchSettings.excludes,
                search_settings: {
                    mode: searchSettings.mode,
                    case_sensitive: searchSettings.caseSensitive,
                    inverse: searchSettings.inverse,
                    include_dirs: searchSettings.includeDirs
                }
            });
            App.persistSearchUiState();
        } catch (e) { console.warn("Auto-save settings failed", e); }
    },

    loadGlobalSettings: async () => {
        try {
            App.state.globalSettings = await api.fetchGlobalSettings();
        } catch (e) { console.error("Failed to load global settings", e); }
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
            await api.saveGlobalSettings(body);
            App.state.globalSettings = { ...App.state.globalSettings, ...body };
            App.updateStats();
            ui.showToast("Global settings saved successfully");
            bootstrap.Modal.getInstance(document.getElementById('settingsModal')).hide();
        } catch (e) { ui.showToast("Failed to save settings: " + e.message, 'danger'); }
    },

    previewFile: async (path) => {
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
        ui.updateFileMetaUI(path);

        const codeEl = document.getElementById('codePreview');
        codeEl.innerText = "Loading...";
        
        try {
            const data = await api.fetchContent(path);
            App.state.rawContent = data.content;
            
            const ext = path.split('.').pop().toLowerCase();
            codeEl.className = 'hljs h-100 d-block p-4';
            
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
            const btn = document.getElementById('btnCopyPath');
            const originalText = btn ? btn.innerText : 'Copy Path';
            if (btn) btn.innerText = 'Copied';
            setTimeout(() => {
                if (btn) btn.innerText = originalText;
            }, 1000);
            ui.showToast("Path copied", 'success');
        } catch (e) { ui.showToast("Failed to copy path", 'danger'); }
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
            await api.saveFileNote(App.state.projectPath, App.state.currentFile, note);
            App.state.projConfig.notes[App.state.currentFile] = note;
            App.hideFileNote();
            ui.showToast("Note saved", 'success');
        } catch (e) { ui.showToast("Save failed: " + e.message, 'danger'); }
    },

    archiveStaging: async () => {
        if (App.state.staging.size === 0) {
            ui.showToast("Select files first.", 'warning');
            return;
        }

        ui.showActionModal({
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
                    ui.showToast("Archive name is required", 'warning');
                    return;
                }
                try {
                    const btn = document.getElementById('btnArchiveSelection');
                    const originalText = btn.innerText;
                    btn.innerText = 'Archiving...';
                    btn.disabled = true;
                    await api.archiveFiles(App.state.projectPath, Array.from(App.state.staging), name);
                    ui.closeActionModal();
                    ui.showToast(`Archived to ${name}`, 'success');
                    btn.innerText = originalText;
                    btn.disabled = false;
                } catch (e) { ui.showToast(e.message, 'danger'); }
            }
        });
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
        ui.showActionModal({
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
                    ui.closeActionModal();
                    return;
                }
                try {
                    await api.renameFile(App.state.projectPath, App.state.currentFile, newName);
                    ui.closeActionModal();
                    ui.showToast("Renamed successfully");
                    App.openProject();
                    App.state.currentFile = null;
                    document.getElementById('fileControls').style.display = 'none';
                } catch (e) { ui.showToast("Rename failed: " + e.message, 'danger'); }
            }
        });
    },

    deleteFile: async () => {
        if (!App.state.currentFile) return;
        ui.showActionModal({
            title: 'Delete file',
            confirmText: 'Delete',
            bodyHtml: `<p class="mb-0">Delete <strong>${App.escapeHtml(App.state.currentFile.split(/[\\\/]/).pop())}</strong>? This cannot be undone.</p>`,
            onConfirm: async () => {
                try {
                    await api.deleteFiles(App.state.projectPath, [App.state.currentFile]);
                    ui.closeActionModal();
                    App.openProject();
                    App.state.currentFile = null;
                    document.getElementById('fileControls').style.display = 'none';
                    ui.showToast("File deleted", 'success');
                } catch (e) { ui.showToast("Delete failed: " + e.message, 'danger'); }
            }
        });
    },

    batchRename: async () => {
        const files = Array.from(App.state.selectedFiles);
        if (files.length === 0) return ui.showToast("Select files first", 'warning');

        ui.showActionModal({
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
                    ui.showToast("Pattern is required", 'warning');
                    return;
                }

                try {
                    const dryData = await api.batchRename(App.state.projectPath, files, pattern, replacement, true);
                    const previewHtml = dryData.results.map(
                        (r) => `<div class="small mb-1">${App.escapeHtml(r.old.split(/[\\\/]/).pop())} &rarr; ${App.escapeHtml(r.new.split(/[\\\/]/).pop())} <span class="text-muted">[${App.escapeHtml(r.status)}]</span></div>`
                    ).join('');
                    ui.showActionModal({
                        title: 'Confirm batch rename',
                        confirmText: 'Rename',
                        bodyHtml: `<div class="small text-muted mb-2">Preview of changes</div>${previewHtml || '<div class="small">No matching files.</div>'}`,
                        onConfirm: async () => {
                            await api.batchRename(App.state.projectPath, files, pattern, replacement, false);
                            ui.closeActionModal();
                            ui.showToast("Batch rename completed!");
                            App.state.selectedFiles.clear();
                            App.updateBulkUI();
                            App.refreshProject();
                        }
                    });
                } catch (e) { ui.showToast("Batch rename failed: " + e.message, 'danger'); }
            }
        });
    },

    startSearch: () => {
        if (!App.state.projectPath) return;
        const settings = App.getSearchUiSettings();
        App.persistSearchUiState();
        ui.updateWorkspaceSummary();
        const query = document.getElementById('searchInput').value;
        const tab = new bootstrap.Tab(document.getElementById('tab-search'));
        tab.show();

        const resultsDiv = document.getElementById('searchResultsList');
        resultsDiv.innerHTML = '<div class="text-center p-3">Searching...</div>';

        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const token = App.state.globalSettings.api_token || "";
        const wsUrl = `${proto}//${window.location.host}/ws/search?path=${encodeURIComponent(App.state.projectPath)}&query=${encodeURIComponent(query)}&mode=${settings.mode}&inverse=${settings.inverse}&case_sensitive=${settings.caseSensitive}&include_dirs=${settings.include_dirs}${token ? `&token=${encodeURIComponent(token)}` : ''}`;

        if (App.state.socket) App.state.socket.close();
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
            ui.renderSearchResultItem(data);
            resultsDiv.scrollTop = resultsDiv.scrollHeight;
        };
        App.state.socket.onerror = () => {
            resultsDiv.innerHTML = '<div class="text-center p-3 text-danger">Search connection failed.</div>';
        };
    },

    categorizeStaged: async (catName) => {
        if (App.state.staging.size === 0) return ui.showToast("Add files to staging first.", 'warning');
        try {
            const data = await api.categorizeFiles(App.state.projectPath, Array.from(App.state.staging), catName);
            ui.showToast(`✅ Successfully moved ${data.moved_count} files to ${catName}`, 'success');
            App.state.staging.clear();
            ui.renderStaging();
            App.syncStagingToBackend();
            App.refreshProject();
        } catch (e) { ui.showToast("Error: " + e.message, 'danger'); }
    },

    executeToolOnStaged: async (toolName) => {
        if (App.state.staging.size === 0) return ui.showToast("Add files to staging first.", 'warning');
        
        const modalWrapper = document.getElementById('toolResultModal');
        const modalBody = document.getElementById('toolResultModalBody');
        const modalHeader = document.querySelector('#toolResultModal .modal-header');
        
        const bsModal = new bootstrap.Modal(modalWrapper);
        bsModal.show();

        const paths = Array.from(App.state.staging);
        modalBody.innerHTML = `<div class="p-4 text-center">Preparing to execute ${toolName} on ${paths.length} items...</div>`;
        
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

        const runNext = async (index) => {
            if (index >= paths.length) {
                modalBody.innerHTML += `<div class="p-3 border-top border-secondary text-success fw-bold">✨ All ${paths.length} tasks completed.</div>`;
                if (confirm("Tasks finished. Clear staging?")) {
                    App.state.staging.clear();
                    ui.renderStaging();
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
            await api.terminateProcess(App.state.activePid);
            ui.showToast("Termination signal sent");
        } catch (e) { ui.showToast("Termination failed: " + e.message, 'danger'); }
    },

    addToStaging: () => {
        if (!App.state.currentFile) return;
        App.state.staging.add(App.state.currentFile);
        ui.renderStaging();
        App.syncStagingToBackend();
    },

    removeFromStaging: (path) => {
        App.state.staging.delete(path);
        ui.renderStaging();
        App.syncStagingToBackend();
    },

    syncStagingToBackend: async () => {
        if (!App.state.projectPath) return;
        try {
            await api.saveProjectSettings(App.state.projectPath, { "staging_list": Array.from(App.state.staging) });
        } catch (e) { console.warn("Staging sync failed", e); }
    },

    addToFavorites: async () => {
        if (!App.state.currentFile) return;
        const group = document.getElementById('favGroupSelect').value || "Default";
        await App.toggleFavorite(App.state.currentFile, 'add', group);
    },

    toggleFavorite: async (path, action, group = null) => {
        if (!group) group = document.getElementById('favGroupSelect').value || "Default";
        try {
            await api.toggleFavorite(App.state.projectPath, path, action, group);
            if (!App.state.projConfig.groups[group]) App.state.projConfig.groups[group] = [];
            if (action === 'add') {
                if (!App.state.projConfig.groups[group].includes(path)) App.state.projConfig.groups[group].push(path);
                ui.showToast("⭐ Added to favorites");
            } else {
                App.state.projConfig.groups[group] = App.state.projConfig.groups[group].filter(p => p !== path);
                ui.showToast("Removed from favorites");
            }
            ui.renderFavorites();
        } catch (e) { ui.showToast(e.message, 'danger'); }
    },

    updateStats: async () => {
        if (App._statsTimer) clearTimeout(App._statsTimer);
        App._statsTimer = setTimeout(App._updateStatsImpl, 300);
        ui.updateWorkspaceSummary();
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
            const data = await api.fetchStats(App.state.projectPath, Array.from(App.state.staging));
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
            const data = await api.generateContext({
                files: Array.from(App.state.staging),
                project_path: App.state.projectPath,
                template_name: templateName,
                export_format: format,
                include_blueprint: includeBlueprint
            });
            await navigator.clipboard.writeText(data.content);
            ui.showToast("Context copied", 'success');
        } catch (e) { ui.showToast("Failed to generate context: " + e.message, 'danger'); }
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
                await api.saveFileContent(App.state.currentFile, editor.value);
                App.state.isEditing = false;
                editor.style.display = 'none';
                preview.style.display = 'block';
                btn.innerText = 'Edit';
                App.previewFile(App.state.currentFile);
                ui.showToast("File saved", 'success');
            } catch (e) { ui.showToast("Save failed: " + e.message, 'danger'); }
        }
    },

    toggleSelectAll: (checked) => {
        App.state.selectedFiles.clear();
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
        const countLabel = document.getElementById('selectedCount');
        if (countLabel) countLabel.innerText = count;
        const bulkActions = document.getElementById('bulkActions');
        if (bulkActions) {
            if (count > 0) {
                bulkActions.style.setProperty('display', 'flex', 'important');
            } else {
                bulkActions.style.setProperty('display', 'none', 'important');
            }
        }
    },

    bulkStage: () => {
        if (App.state.selectedFiles.size === 0) return;
        App.state.selectedFiles.forEach(path => App.state.staging.add(path));
        const selectAllCb = document.getElementById('selectAllCb');
        if (selectAllCb) selectAllCb.checked = false;
        ui.renderStaging();
        App.syncStagingToBackend();
        App.state.selectedFiles.clear();
        App.updateBulkUI();
        ui.showToast("✅ Added selected items to staging");
    },

    bulkDelete: async () => {
        if (App.state.selectedFiles.size === 0) return;
        ui.showActionModal({
            title: 'Delete selected files',
            confirmText: 'Delete',
            bodyHtml: `<p class="mb-0">Delete <strong>${App.state.selectedFiles.size}</strong> files forever? This cannot be undone.</p>`,
            onConfirm: async () => {
                try {
                    await api.deleteFiles(App.state.projectPath, Array.from(App.state.selectedFiles));
                    ui.closeActionModal();
                    App.state.selectedFiles.clear();
                    App.updateBulkUI();
                    App.openProject();
                    ui.showToast("Batch delete successful.");
                } catch (e) { ui.showToast("Bulk delete failed: " + e.message, 'danger'); }
            }
        });
    },

    bulkMove: async () => {
        if (App.state.selectedFiles.size === 0) return;
        ui.showActionModal({
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
                    const data = await api.moveFiles(Array.from(App.state.selectedFiles), dstDir);
                    ui.closeActionModal();
                    ui.showToast(`Batch Move: ${data.new_paths.length} items moved.`);
                    App.state.selectedFiles.clear();
                    App.updateBulkUI();
                    App.openProject();
                } catch (e) { ui.showToast("Move failed: " + e.message, 'danger'); }
            }
        });
    },

    clearStaging: () => {
        if (App.state.staging.size === 0) return;
        if (!confirm("Clear whole staging list?")) return;
        App.state.staging.clear();
        ui.renderStaging();
        App.syncStagingToBackend();
        ui.showToast("Staging cleared");
    },

    stageAll: async () => {
        if (!App.state.projectPath) return;
        try {
            const data = await api.stageAll(App.state.projectPath);
            await App.refreshProject();
            ui.showToast(`Staged ${data.added_count} files`);
        } catch (e) { ui.showToast("Stage All failed: " + e.message, 'danger'); }
    },

    showPathCollector: (paths = null) => {
        App._currentCollectionPaths = paths || Array.from(App.state.staging);
        if (!App._currentCollectionPaths || App._currentCollectionPaths.length === 0) {
            ui.showToast("No files selected or staged!", "warning");
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
            const data = await api.collectPaths({
                paths: paths,
                project_root: project_root,
                mode: mode,
                separator: separator,
                file_prefix: file_prefix,
                dir_suffix: dir_suffix
            });
            if (data.result) {
                await navigator.clipboard.writeText(data.result);
                ui.showToast(`✅ ${paths.length} paths copied to clipboard!`, "success");
                const modalEl = document.getElementById('pathCollectorModal');
                bootstrap.Modal.getInstance(modalEl).hide();
            }
        } catch (e) { ui.showToast("Collection failed: " + e.message, "danger"); }
    },

    openInExplorer: async (path) => {
        try {
            await api.openInOs(App.state.projectPath, path);
        } catch (e) { ui.showToast("Failed to open path: " + e.message, "danger"); }
    },

    openCurrentInExplorer: async () => {
        if (!App.state.currentFile) return;
        await App.openInExplorer(App.state.currentFile);
    },

    showContextMenu: (e, path) => {
        state.contextPath = path;
        const menu = document.getElementById('customContextMenu');
        if (menu) {
            menu.style.display = 'block';
            menu.style.left = e.clientX + 'px';
            menu.style.top = e.clientY + 'px';
        }
    },

    hideContextMenu: () => {
        const menu = document.getElementById('customContextMenu');
        if (menu) menu.style.display = 'none';
        state.contextPath = null;
    },

    ctxAction: async (action) => {
        const path = state.contextPath;
        if (!path) return;
        
        switch (action) {
            case 'stage': 
                App.state.staging.add(path);
                ui.renderStaging();
                App.syncStagingToBackend();
                ui.showToast("Added to Staging");
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
                    ui.showToast("Path Copied");
                } catch (_) { ui.showToast("Copy failed", 'danger'); }
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

    loadTreeChildren: async (node, childrenContainer) => {
        try {
            const data = await api.fetchChildren(node.path);
            childrenContainer.innerHTML = '';

            if (!data.children || data.children.length === 0) {
                childrenContainer.innerHTML = '<div class="empty-state py-2"><div class="small text-muted">Empty folder</div></div>';
                return;
            }

            data.children.forEach((child) => {
                childrenContainer.appendChild(ui.renderTree(child));
            });
        } catch (e) {
            throw e;
        }
    }
};

// Initialize App
document.addEventListener('DOMContentLoaded', () => App.init());

// Expose to window for inline onclick handlers
window.App = App;
