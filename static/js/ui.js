import { state, config, escapeHtml, getFileName, getFileExt } from './state.js';
import { createVirtualList } from './virtual-list.js';

let app;
const searchResultViews = new Map();

export function setApp(appInstance) {
    app = appInstance;
}

const FILE_ICONS = {
    code: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M4.85 2.15a.5.5 0 0 1 0 .7L1.71 6l3.14 3.15a.5.5 0 1 1-.7.7l-3.5-3.5a.5.5 0 0 1 0-.7l3.5-3.5a.5.5 0 0 1 .7 0Zm6.3 0a.5.5 0 0 0 0 .7L14.29 6l-3.14 3.15a.5.5 0 0 0 .7.7l3.5-3.5a.5.5 0 0 0 0-.7l-3.5-3.5a.5.5 0 0 0-.7 0Z"/></svg>',
    image: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M14 2H2a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1ZM3 4h10v6.5l-2.5-2.5L8 10.5 5.5 8 3 10.5V4Zm2.5 1.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"/></svg>',
    archive: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M3 2a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1H3Zm5 3v1h1V5H8ZM4 7h8v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7Zm3 1v1h2V8H7Z"/></svg>',
    doc: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M9 1H3a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V5L9 1Zm0 1.5L12.5 5H9V2.5ZM5 7h6v1H5V7Zm0 2h6v1H5V9Zm0 2h4v1H5v-1Z"/></svg>',
    config: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 4.754a3.246 3.246 0 1 0 0 6.492 3.246 3.246 0 0 0 0-6.492ZM5.754 8a2.246 2.246 0 1 1 4.492 0 2.246 2.246 0 0 1-4.492 0Z"/><path d="M9.795 1.293a.5.5 0 0 1 .55.14l.708.708a.5.5 0 0 0 .65.08l.832-.5a.5.5 0 0 1 .73.27l.27.83a.5.5 0 0 0 .56.35l.872-.13a.5.5 0 0 1 .57.57l-.13.872a.5.5 0 0 0 .35.56l.83.27a.5.5 0 0 1 .27.73l-.5.832a.5.5 0 0 0 .08.65l.708.708a.5.5 0 0 1 0 .683l-.708.708a.5.5 0 0 0-.08.65l.5.832a.5.5 0 0 1-.27.73l-.83.27a.5.5 0 0 0-.35.56l.13.872a.5.5 0 0 1-.57.57l-.872-.13a.5.5 0 0 0-.56.35l-.27.83a.5.5 0 0 1-.73.27l-.832-.5a.5.5 0 0 0-.65.08l-.708.708a.5.5 0 0 1-.683 0l-.708-.708a.5.5 0 0 0-.65-.08l-.832.5a.5.5 0 0 1-.73-.27l-.27-.83a.5.5 0 0 0-.56-.35l-.872.13a.5.5 0 0 1-.57-.57l.13-.872a.5.5 0 0 0-.35-.56l-.83-.27a.5.5 0 0 1-.27-.73l.5-.832a.5.5 0 0 0-.08-.65l-.708-.708a.5.5 0 0 1 0-.683l.708-.708a.5.5 0 0 0 .08-.65l-.5-.832a.5.5 0 0 1 .27-.73l.83-.27a.5.5 0 0 0 .35-.56l-.13-.872a.5.5 0 0 1 .57-.57l.872.13a.5.5 0 0 0 .56-.35l.27-.83a.5.5 0 0 1 .73-.27l.832.5a.5.5 0 0 0 .65-.08l.708-.708a.5.5 0 0 1 .14-.08Z"/></svg>',
    default: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M9 1H3a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V5L9 1Zm0 1.5L12.5 5H9V2.5Z"/></svg>'
};

const FOLDER_ICON = '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h3.379a1.5 1.5 0 0 1 1.06.44L7.062 2.5H13.5A1.5 1.5 0 0 1 15 4v8.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5v-9Z"/></svg>';

function getFileIconClass(ext) {
    const codeExts = ['py', 'js', 'ts', 'tsx', 'jsx', 'java', 'c', 'cpp', 'h', 'cs', 'rs', 'go', 'rb', 'php', 'swift', 'kt', 'dart', 'vue', 'svelte', 'sh', 'bat'];
    const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico', 'bmp'];
    const archiveExts = ['zip', 'tar', 'gz', 'rar', '7z', 'bz2'];
    const docExts = ['md', 'txt', 'pdf', 'doc', 'docx', 'rst'];
    const configExts = ['json', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'env', 'xml'];

    if (codeExts.includes(ext)) return 'code';
    if (imageExts.includes(ext)) return 'image';
    if (archiveExts.includes(ext)) return 'archive';
    if (docExts.includes(ext)) return 'doc';
    if (configExts.includes(ext)) return 'config';
    return 'default';
}

function getFileIconSvg(ext) {
    const cls = getFileIconClass(ext);
    return FILE_ICONS[cls] || FILE_ICONS.default;
}

function renderSkeletonList(container, count = 5) {
    if (!container) return;
    container.innerHTML = '';
    for (let i = 0; i < count; i++) {
        const item = document.createElement('div');
        item.className = 'skeleton-tree-item';
        item.innerHTML = `
            <div class="skeleton skeleton-icon"></div>
            <div class="skeleton skeleton-line ${i % 3 === 0 ? 'short' : 'medium'}" style="flex:1"></div>
        `;
        container.appendChild(item);
    }
}

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

export function showOperationSummary({ title, completed = 0, skipped = 0, details = '', level = 'success' }) {
    const container = document.getElementById('operationSummary');
    if (!container) return;

    container.replaceChildren();
    container.hidden = false;
    container.className = `operation-summary${level === 'warning' ? ' is-warning' : ''}${level === 'danger' ? ' is-danger' : ''}`;

    const message = document.createElement('span');
    const heading = document.createElement('strong');
    heading.textContent = title;
    message.appendChild(heading);
    message.append(` ${completed} completed`);
    if (skipped > 0) message.append(`, ${skipped} skipped`);
    if (details) message.append(`. ${details}`);

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'btn-close';
    close.setAttribute('aria-label', 'Dismiss operation summary');
    close.dataset.action = 'closeOperationSummary';

    container.append(message, close);
}

export function hideOperationSummary() {
    const container = document.getElementById('operationSummary');
    if (!container) return;
    container.hidden = true;
    container.replaceChildren();
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
            btn.innerText = state.isSidebarExpanded ? item.name : (item.name ? item.name[0].toUpperCase() : "?");
            btn.title = item.path;
            btn.addEventListener('click', () => {
                document.getElementById('projectPath').value = item.path;
                app.openProject();
            });
            container.appendChild(btn);
        });
    };
    renderList(data.pinned || [], 'pinnedProjectsList');
    renderList(data.recent || [], 'recentProjectsList');

    // state.projectPath may be a raw user-typed string (mixed case, back/
    // forward slashes) while the server returns normalized keys; compare
    // normalized forms or the pin highlight is wrong for typed variants.
    const norm = (p) => (p || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
    const isPinned = (data.pinned || []).some(p => norm(p.path) === norm(state.projectPath));
    updatePinUI(isPinned);
}

export function updateFileMetaUI(path) {
    const tagContainer = document.getElementById('fileTags');
    if (!tagContainer) return;
    tagContainer.innerHTML = '';
    const tags = state.projConfig.tags || {};
    const matchedTags = tags[path] || [];
    matchedTags.forEach(tag => {
        const span = document.createElement('span');
        span.className = 'badge bg-info text-dark small me-1';
        span.style.cursor = 'pointer';
        span.title = 'Click to remove';
        span.innerText = tag;
        span.addEventListener('click', () => app.removeTag(tag));
        tagContainer.appendChild(span);
    });
    const addBtn = document.createElement('span');
    addBtn.className = 'badge bg-outline-light small text-muted border border-secondary';
    addBtn.style.cursor = 'pointer';
    addBtn.innerText = '+';
    addBtn.title = 'Add tag';
    addBtn.addEventListener('click', () => app.addTag());
    tagContainer.appendChild(addBtn);
}

export function renderStaging() {
    const list = document.getElementById('stagingList');
    if (!list) return;
    list.innerHTML = '';
    if (state.staging.size === 0) {
        list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#128193;</div><div class="empty-state-text">No files staged yet</div><div class="empty-state-hint">Select files from the tree to build your context</div></div>';
        app.updateStats();
        app.updateWorkspaceSummary();
        return;
    }
    state.staging.forEach(path => {
        const item = document.createElement('div');
        item.className = 'list-group-item d-flex justify-content-between p-1 bg-transparent border-0 text-white animate-in';
        const nameSpan = document.createElement('span');
        nameSpan.className = 'text-truncate small cursor-pointer';
        nameSpan.title = path;
        nameSpan.innerText = getFileName(path);
        nameSpan.addEventListener('click', () => app.previewFile(path));

        const removeBtn = document.createElement('button');
        removeBtn.className = 'btn btn-sm btn-link text-danger p-0 ms-2';
        removeBtn.innerHTML = '&times;';
        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            app.removeFromStaging(path);
        });

        item.appendChild(nameSpan);
        item.appendChild(removeBtn);
        list.appendChild(item);
    });
    app.updateStats();
    app.updateWorkspaceSummary();
}

export function renderFavorites() {
    const list = document.getElementById('favoritesList');
    const select = document.getElementById('favGroupSelect');
    if (!list || !select) return;
    list.innerHTML = '';

    if (!state.projConfig || !state.projConfig.groups) {
        app.updateWorkspaceSummary();
        return;
    }

    const groups = Object.keys(state.projConfig.groups);
    const currentValue = select.value;

    select.innerHTML = '';
    groups.forEach((g) => {
        const opt = document.createElement('option');
        opt.value = g;
        opt.innerText = g;
        select.appendChild(opt);
    });

    if (groups.includes(currentValue)) {
        select.value = currentValue;
    } else if (groups.length > 0) {
        select.value = state.projConfig.current_group || groups[0];
    }

    const currentGroup = select.value || "Default";
    const files = state.projConfig.groups[currentGroup] || [];
    if (files.length === 0) {
        list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#9734;</div><div class="empty-state-text">No favorites in this group</div><div class="empty-state-hint">Right-click files and add to favorites</div></div>';
        app.updateWorkspaceSummary();
        return;
    }

    files.forEach(path => {
        const item = document.createElement('div');
        item.className = 'list-group-item bg-transparent text-white border-0 p-2 cursor-pointer hover-bg d-flex justify-content-between align-items-center';

        const infoDiv = document.createElement('div');
        infoDiv.className = 'text-truncate flex-grow-1';
        infoDiv.innerHTML = `
            <div class="fw-bold text-info small">${escapeHtml(getFileName(path))}</div>
            <div class="text-muted" style="font-size:0.75rem">${escapeHtml(path)}</div>
        `;
        infoDiv.addEventListener('click', () => app.previewFile(path));

        const removeBtn = document.createElement('button');
        removeBtn.className = 'btn btn-sm btn-link text-danger p-0';
        removeBtn.title = 'Unfavorite';
        removeBtn.innerHTML = '&times;';
        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            app.toggleFavorite(path, 'remove');
        });

        item.appendChild(infoDiv);
        item.appendChild(removeBtn);
        list.appendChild(item);
    });
    app.updateWorkspaceSummary();
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
        app.updateWorkspaceSummary();
        return;
    }

    section.style.display = 'block';
    catKeys.forEach(name => {
        const btn = document.createElement('button');
        btn.className = 'btn btn-outline-info btn-xs py-0 px-1 x-small';
        btn.innerText = name;
        btn.addEventListener('click', () => app.categorizeStaged(name));
        catContainer.appendChild(btn);
    });
    toolKeys.forEach(name => {
        const btn = document.createElement('button');
        btn.className = 'btn btn-outline-warning btn-xs py-0 px-1 x-small';
        btn.innerText = name;
        btn.addEventListener('click', () => app.executeToolOnStaged(name));
        toolContainer.appendChild(btn);
    });
    app.updateWorkspaceSummary();
}

export function updateWorkspaceSummary() {
    const projectPath = state.projectPath;
    const projectName = document.getElementById('summaryProjectName');
    const stageCount = document.getElementById('summaryStageCount');
    const favoriteCount = document.getElementById('summaryFavoriteCount');

    if (projectName) {
        projectName.innerText = projectPath
            ? getFileName(projectPath)
            : 'No workspace loaded';
        projectName.title = projectPath || '';
    }

    if (stageCount) stageCount.innerText = `${state.staging.size} staged`;

    const groups = state.projConfig.groups || {};
    const favoriteTotal = Object.values(groups).reduce((acc, items) => acc + items.length, 0);
    if (favoriteCount) favoriteCount.innerText = `${favoriteTotal} favorites`;
}

export function showActionModal({ title, bodyHtml, confirmText = 'Confirm', onConfirm }) {
    document.getElementById('actionModalTitle').innerText = title;
    document.getElementById('actionModalBody').innerHTML = bodyHtml;
    const confirmBtn = document.getElementById('actionModalConfirm');
    confirmBtn.innerText = confirmText;
    // Always reset the confirm button so a previous run that left it disabled
    // (e.g. modal hidden before the handler resolved) cannot permanently
    // swallow subsequent confirm clicks.
    confirmBtn.disabled = false;
    state.actionModalHandler = onConfirm;
    new bootstrap.Modal(document.getElementById('actionModal')).show();
}

export function closeActionModal() {
    const modalEl = document.getElementById('actionModal');
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
    state.actionModalHandler = null;
}

function createSearchResultItem(data) {
    const item = document.createElement('div');
    item.className = 'list-group-item bg-transparent text-white border-0 animate-in p-2 cursor-pointer d-flex align-items-center virtual-search-item';
    item.setAttribute('data-path', data.path);

    const contentDiv = document.createElement('div');
    contentDiv.className = 'flex-grow-1 overflow-hidden';
    const snippetHtml = data.snippet ? `<div class="x-small text-warning mt-1 text-truncate border-start border-warning ps-2" style="background: rgba(255,193,7,0.05)">${escapeHtml(data.snippet)}</div>` : "";
    contentDiv.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
            <div class="fw-bold text-info">${escapeHtml(data.name)}</div>
            <div class="text-muted x-small" style="font-size:0.7rem">${escapeHtml(data.mtime_fmt || '')}</div>
        </div>
        <div class="small text-muted text-truncate">${escapeHtml(data.path)}</div>
        ${snippetHtml}
    `;
    item.appendChild(contentDiv);

    const stageBtn = document.createElement('button');
    stageBtn.type = 'button';
    stageBtn.className = 'btn btn-sm btn-link text-success p-0 ms-2';
    stageBtn.innerHTML = '&#43;';
    stageBtn.title = 'Stage this file';
    stageBtn.addEventListener('click', (event) => {
        event.stopPropagation();
        app.state.staging.add(data.path);
        renderStaging();
        app.syncStagingToBackend();
        app.updateWorkspaceSummary();
        showToast('Added to staging');
    });
    item.appendChild(stageBtn);

    item.addEventListener('click', () => app.previewFile(data.path));
    item.addEventListener('contextmenu', (event) => {
        event.preventDefault();
        app.showContextMenu(event, data.path);
    });
    return item;
}

export function clearVirtualSearchResults() {
    for (const view of searchResultViews.values()) view.destroy();
    searchResultViews.clear();
}

export function renderVirtualSearchResults(results) {
    const containers = [
        document.getElementById('searchResultsList'),
        document.getElementById('searchOverlayList'),
    ].filter(Boolean);

    containers.forEach((container) => {
        let view = searchResultViews.get(container);
        if (!view) {
            view = createVirtualList(container, createSearchResultItem);
            searchResultViews.set(container, view);
        }
        view.setItems(results);
    });
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
        cb.addEventListener('click', (e) => {
            e.stopPropagation();
            if (cb.checked) state.selectedFiles.add(node.path);
            else state.selectedFiles.delete(node.path);
            app.updateBulkUI();
        });
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

    const metaInfo = node.type === 'file' ? ` (${escapeHtml(node.size_fmt || '')})` : '';

    if (node.type === 'dir') {
        const iconSpan = document.createElement('span');
        iconSpan.className = 'file-icon icon-folder';
        iconSpan.innerHTML = FOLDER_ICON;
        header.appendChild(iconSpan);
    } else {
        const ext = getFileExt(node.name);
        const iconCls = getFileIconClass(ext);
        const iconSpan = document.createElement('span');
        iconSpan.className = `file-icon icon-file ${iconCls}`;
        iconSpan.innerHTML = getFileIconSvg(ext);
        header.appendChild(iconSpan);
    }

    const nameSpan = document.createElement('span');
    nameSpan.className = 'flex-grow-1 text-truncate';
    nameSpan.innerHTML = `
        <span>${escapeHtml(node.name)}</span>
        <span class="ms-2 text-muted x-small d-none d-lg-inline" style="font-size:0.7rem">${escapeHtml(node.mtime_fmt || '')}${metaInfo}</span>
    `;
    header.appendChild(nameSpan);
    container.appendChild(header);

    if (node.type === 'dir') {
        const childrenContainer = document.createElement('div');
        childrenContainer.className = 'tree-children';
        childrenContainer.style.display = initialExpand ? 'block' : 'none';
        if (initialExpand) {
            renderSkeletonList(childrenContainer, 3);
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
                    renderSkeletonList(childrenContainer, 3);
                    try {
                        await app.loadTreeChildren(node, childrenContainer);
                        loaded = true;
                    } catch (err) {
                        childrenContainer.innerHTML = '<div class="small text-danger px-2 py-2">&#9888; Failed to load folder</div>';
                        showToast("Failed to expand directory: " + err.message, 'danger');
                    }
            }
            setExpandedState(isHidden);
        };

        header.addEventListener('click', async (e) => {
            e.stopPropagation();
            await expandDirectory();
        });

        if (initialExpand) {
            Promise.resolve().then(async () => {
                try {
                    await app.loadTreeChildren(node, childrenContainer);
                    loaded = true;
                    setExpandedState(true);
                } catch (err) {
                    childrenContainer.innerHTML = '<div class="small text-danger px-2 py-2">&#9888; Failed to load workspace tree</div>';
                    showToast("Failed to load workspace tree: " + err.message, 'danger');
                }
            });
        }
    } else {
        header.addEventListener('click', (e) => {
            e.stopPropagation();
            const treeContainer = header.closest('.section-body, #fileTreeRoot');
            if (treeContainer) {
                treeContainer.querySelectorAll('.tree-node').forEach(n => n.classList.remove('active'));
            }
            header.classList.add('active');
            app.previewFile(node.path);
        });
    }

    return container;
}
