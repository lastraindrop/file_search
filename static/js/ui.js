import { state, config, escapeHtml } from './state.js';

export function showToast(message, type = 'success') {
    const container = document.querySelector('.toast-container');
    if (!container) return;
    
    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-bg-${type} border-0 animate-in mb-2`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body fw-bold">${escapeHtml(message)}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    container.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

export function updatePinUI(isPinned) {
    const btn = document.getElementById('btnPin');
    if (!btn) return;
    btn.innerText = isPinned ? 'Pinned' : 'Pin';
    btn.classList.toggle('btn-warning', isPinned);
    btn.classList.toggle('btn-outline-warning', !isPinned);
}

export function renderWorkspaces(data) {
    const renderList = (list, containerId) => {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = '';
        list.forEach(item => {
            const btn = document.createElement('button');
            btn.className = 'btn btn-outline-info btn-sm text-truncate w-100 mb-1';
            btn.style.height = '32px';
            btn.innerText = state.isSidebarExpanded ? item.name : item.name[0].toUpperCase();
            btn.title = item.path;
            btn.onclick = () => {
                document.getElementById('projectPath').value = item.path;
                window.App.openProject();
            };
            container.appendChild(btn);
        });
    };
    renderList(data.pinned || [], 'pinnedProjectsList');
    renderList(data.recent || [], 'recentProjectsList');
    
    const isPinned = (data.pinned || []).some(p => p.path === state.projectPath);
    updatePinUI(isPinned);
}

export function updateFileMetaUI(path) {
    const tagContainer = document.getElementById('fileTags');
    if (!tagContainer) return;
    tagContainer.innerHTML = '';
    const tags = state.projConfig.tags || {};
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
}

export function renderStaging() {
    const list = document.getElementById('stagingList');
    if (!list) return;
    list.innerHTML = '';
    if (state.staging.size === 0) {
        list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">+</div><div>No staged files yet.</div></div>';
        window.App.updateStats();
        window.App.updateWorkspaceSummary();
        return;
    }
    state.staging.forEach(path => {
        const item = document.createElement('div');
        item.className = 'list-group-item d-flex justify-content-between p-1 bg-transparent border-0 text-white animate-in';
        const nameSpan = document.createElement('span');
        nameSpan.className = 'text-truncate small cursor-pointer';
        nameSpan.title = path;
        nameSpan.innerText = path.split(/[\\\/]/).pop();
        nameSpan.onclick = () => window.App.previewFile(path);

        const removeBtn = document.createElement('button');
        removeBtn.className = 'btn btn-sm btn-link text-danger p-0 ms-2';
        removeBtn.innerHTML = '&times;';
        removeBtn.onclick = (e) => { e.stopPropagation(); window.App.removeFromStaging(path); };

        item.appendChild(nameSpan);
        item.appendChild(removeBtn);
        list.appendChild(item);
    });
    window.App.updateStats();
    window.App.updateWorkspaceSummary();
}

export function renderFavorites() {
    const list = document.getElementById('favoritesList');
    const select = document.getElementById('favGroupSelect');
    if (!list || !select) return;
    list.innerHTML = '';
    
    if (!state.projConfig || !state.projConfig.groups) {
        window.App.updateWorkspaceSummary();
        return;
    }

    const groups = Object.keys(state.projConfig.groups);
    const currentOptions = Array.from(select.options).map(o => o.value);
    
    groups.forEach((g) => {
        if (!currentOptions.includes(g)) {
            const opt = document.createElement('option');
            opt.value = g;
            opt.innerText = g;
            select.appendChild(opt);
        }
    });
    
    if (!select.value && groups.length > 0) {
        select.value = state.projConfig.current_group || groups[0] || "Default";
    }

    const currentGroup = select.value || "Default";
    const files = state.projConfig.groups[currentGroup] || [];
    if (files.length === 0) {
        list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">*</div><div>No favorites in this group.</div></div>';
        window.App.updateWorkspaceSummary();
        return;
    }

    files.forEach(path => {
        const item = document.createElement('div');
        item.className = 'list-group-item bg-transparent text-white border-0 p-2 cursor-pointer hover-bg d-flex justify-content-between align-items-center';

        const infoDiv = document.createElement('div');
        infoDiv.className = 'text-truncate flex-grow-1';
        infoDiv.innerHTML = `
            <div class="fw-bold text-info small">${escapeHtml(path.split(/[\\\/]/).pop())}</div>
            <div class="text-muted" style="font-size:0.75rem">${escapeHtml(path)}</div>
        `;
        infoDiv.onclick = () => window.App.previewFile(path);

        const removeBtn = document.createElement('button');
        removeBtn.className = 'btn btn-sm btn-link text-danger p-0';
        removeBtn.title = 'Unfavorite';
        removeBtn.innerHTML = '&times;';
        removeBtn.onclick = (e) => { e.stopPropagation(); window.App.toggleFavorite(path, 'remove'); };

        item.appendChild(infoDiv);
        item.appendChild(removeBtn);
        list.appendChild(item);
    });
    window.App.updateWorkspaceSummary();
}

export function renderActions() {
    const catContainer = document.getElementById('categoriesContainer');
    const toolContainer = document.getElementById('toolsContainer');
    const section = document.getElementById('quickActionsSection');
    if (!catContainer || !toolContainer || !section) return;

    catContainer.innerHTML = '';
    toolContainer.innerHTML = '';

    const cats = state.projConfig.quick_categories || {};
    const tools = state.projConfig.custom_tools || {};
    const catKeys = Object.keys(cats);
    const toolKeys = Object.keys(tools);

    if (catKeys.length === 0 && toolKeys.length === 0) {
        section.style.display = 'none';
        window.App.updateWorkspaceSummary();
        return;
    }

    section.style.display = 'block';
    catKeys.forEach(name => {
        const btn = document.createElement('button');
        btn.className = 'btn btn-outline-info btn-xs py-0 px-1 x-small';
        btn.innerText = name;
        btn.onclick = () => window.App.categorizeStaged(name);
        catContainer.appendChild(btn);
    });
    toolKeys.forEach(name => {
        const btn = document.createElement('button');
        btn.className = 'btn btn-outline-warning btn-xs py-0 px-1 x-small';
        btn.innerText = name;
        btn.onclick = () => window.App.executeToolOnStaged(name);
        toolContainer.appendChild(btn);
    });
    window.App.updateWorkspaceSummary();
}

export function updateWorkspaceSummary() {
    const projectPath = state.projectPath;
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
        const searchSettings = window.App.getSearchUiSettings();
        const parts = [searchSettings.mode];
        if (searchSettings.includeDirs) parts.push('dirs');
        if (searchSettings.caseSensitive) parts.push('case');
        if (searchSettings.inverse) parts.push('inverse');
        searchState.innerText = projectPath ? parts.join(' | ') : 'Search disabled';
    }

    if (stageCount) stageCount.innerText = `${state.staging.size} staged`;

    const groups = state.projConfig.groups || {};
    const favoriteTotal = Object.values(groups).reduce((acc, items) => acc + items.length, 0);
    if (favoriteCount) favoriteCount.innerText = `${favoriteTotal} favorites`;
    if (categoryCount) categoryCount.innerText = `${Object.keys(state.projConfig.quick_categories || {}).length} categories`;
    if (toolCount) toolCount.innerText = `${Object.keys(state.projConfig.custom_tools || {}).length} tools`;
}

export function showActionModal({ title, bodyHtml, confirmText = 'Confirm', onConfirm }) {
    document.getElementById('actionModalTitle').innerText = title;
    document.getElementById('actionModalBody').innerHTML = bodyHtml;
    document.getElementById('actionModalConfirm').innerText = confirmText;
    state.actionModalHandler = onConfirm;
    new bootstrap.Modal(document.getElementById('actionModal')).show();
}

export function closeActionModal() {
    const modalEl = document.getElementById('actionModal');
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
    state.actionModalHandler = null;
}

export function renderSearchResultItem(data) {
    const list = document.getElementById('searchResultsList');
    if (!list) return;
    const item = document.createElement('div');
    item.className = 'list-group-item bg-transparent text-white border-0 animate-in p-2 cursor-pointer d-flex align-items-center';
    item.setAttribute('data-path', data.path);
    item.style.cursor = 'pointer';
    
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'form-check-input me-3 x-small';
    cb.style.width = '0.8rem';
    cb.style.height = '0.8rem';
    cb.checked = state.selectedFiles.has(data.path);
    cb.onclick = (e) => {
        e.stopPropagation();
        if (cb.checked) state.selectedFiles.add(data.path);
        else state.selectedFiles.delete(data.path);
        window.App.updateBulkUI();
    };
    item.appendChild(cb);
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'flex-grow-1 overflow-hidden';
    const snippetHtml = data.snippet ? `<div class="x-small text-warning mt-1 text-truncate border-start border-warning ps-2" style="background: rgba(255,193,7,0.05)">${escapeHtml(data.snippet)}</div>` : "";
    contentDiv.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
            <div class="fw-bold text-info">${escapeHtml(data.name)}</div>
            <div class="text-muted x-small" style="font-size:0.7rem">${data.mtime_fmt || ''}</div>
        </div>
        <div class="small text-muted text-truncate">${escapeHtml(data.path)}</div>
        ${snippetHtml}
    `;
    item.appendChild(contentDiv);
    
    item.onclick = () => window.App.previewFile(data.path);
    item.oncontextmenu = (e) => {
        e.preventDefault();
        window.App.showPathCollector([data.path]);
    };
    list.appendChild(item);
}

export function renderTree(node, options = {}) {
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
        cb.checked = state.selectedFiles.has(node.path);
        cb.onclick = (e) => {
            e.stopPropagation();
            if (cb.checked) state.selectedFiles.add(node.path);
            else state.selectedFiles.delete(node.path);
            window.App.updateBulkUI();
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
        <span>${escapeHtml(node.name)}</span>
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
                    await window.App.loadTreeChildren(node, childrenContainer);
                    loaded = true;
                } catch (err) {
                    childrenContainer.innerHTML = '<div class="small text-danger px-2 py-1">Failed to load folder.</div>';
                    showToast("Failed to expand directory: " + err.message, 'danger');
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
                    await window.App.loadTreeChildren(node, childrenContainer);
                    loaded = true;
                    setExpandedState(true);
                } catch (err) {
                    childrenContainer.innerHTML = '<div class="small text-danger px-2 py-1">Failed to load folder.</div>';
                    showToast("Failed to load workspace tree: " + err.message, 'danger');
                }
            });
        }
    } else {
        header.onclick = (e) => {
            e.stopPropagation();
            document.querySelectorAll('.tree-node').forEach(n => n.classList.remove('active'));
            header.classList.add('active');
            window.App.previewFile(node.path);
        };
    }

    return container;
}
