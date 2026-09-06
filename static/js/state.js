export const config = {
    storageKeys: {
        excludes: 'searchExcludes',
        mode: 'searchMode',
        includeDirs: 'searchIncludeDirs',
        caseSensitive: 'searchCaseSensitive',
        inverse: 'searchInverse',
        sidebarExpanded: 'sidebarExpanded',
        lastProjectPath: 'lastProjectPath',
        theme: 'theme',
        leftPanelWidth: 'leftPanelWidth',
        rightPanelWidth: 'rightPanelWidth'
    },
    ui: {
        searchDebounceMs: 400,
        panelWidths: {
            left: 22,
            right: 22,
            min: 18,
            max: 32,
        },
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
        openPathInOs: '/api/fs/open_os',
        projectConfig: '/api/project/config',
        projectSettings: '/api/project/settings',
        projectTools: '/api/project/tools',
        projectCategories: '/api/project/categories',
        globalSettings: '/api/global/settings',
        fsChildren: '/api/fs/children',
        content: '/api/content',
        fileNote: '/api/project/note',
        archive: '/api/fs/archive',
        rename: '/api/fs/rename',
        batchRename: '/api/fs/batch_rename',
        delete: '/api/fs/delete',
        move: '/api/fs/move',
        copy: '/api/fs/copy',
        extract: '/api/fs/extract',
        save: '/api/fs/save',
        stageAll: '/api/actions/stage_all',
        categorize: '/api/actions/categorize',
        terminate: '/api/actions/terminate',
        pin: '/api/workspaces/pin',
        stats: '/api/project/stats',
        generate: '/api/generate',
        collectPaths: '/api/fs/collect_paths',
        favorites: '/api/project/favorites',
        manageTag: '/api/project/tag',
        createFile: '/api/fs/create',
        wsSearch: '/ws/search',
        wsExecute: '/ws/actions/execute',
        progress: '/api/fs/progress',
        progressNew: '/api/fs/progress/new',
    }
};

export const state = {
    projectPath: "",
    staging: new Set(),
    currentFile: null,
    socket: null,
    isEditing: false,
    rawContent: "",
    currentFileEditable: false,
    previewRequestId: 0,
    selectedFiles: new Set(),
    searchResults: [],
    searchGeneration: 0,
    activeProgressTask: null,
    projConfig: {},
    collectionProfiles: {},
    isSidebarExpanded: false,
    activePid: null,
    activeToolSocket: null,
    toolRunInFlight: false,
    actionModalHandler: null,
    globalSettings: {},
    contextPath: null
};

export function escapeHtml(str) {
    // L10: distinguish null/undefined (-> "") from falsy values like 0/"0"
    // which should render their string form, not be collapsed to empty.
    if (str === null || str === undefined) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

export function getFileName(path) {
    if (!path) return "";
    const idx = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
    return idx >= 0 ? path.substring(idx + 1) : path;
}

export function getFileExt(path) {
    const name = getFileName(path);
    const dot = name.lastIndexOf(".");
    return dot > 0 ? name.substring(dot + 1).toLowerCase() : "";
}

export function getInjectedApiToken() {
    return document.querySelector('meta[name="fctx-api-token"]')?.content || "";
}

export function buildWsUrl(path, params = {}) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const base = `${proto}//${window.location.host}${path}`;
    const token = state.globalSettings.api_token || getInjectedApiToken();
    if (token) params.token = token;
    const qs = Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== null && v !== "")
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join("&");
    return qs ? `${base}?${qs}` : base;
}

export async function copyToClipboard(text) {
    // navigator.clipboard only exists in secure contexts (https or
    // localhost). LAN deployments over plain http must fall back to the
    // deprecated execCommand path or every "copy" action would throw.
    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
    }
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    document.body.removeChild(ta);
    return ok;
}
