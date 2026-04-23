export const config = {
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
};

export const state = {
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
    globalSettings: {},
    contextPath: null
};

export function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
