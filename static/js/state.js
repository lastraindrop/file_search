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
        openPathInOs: '/api/fs/open_os',
        projectConfig: '/api/project/config',
        projectSettings: '/api/project/settings',
        globalSettings: '/api/global/settings',
        fsChildren: '/api/fs/children',
        content: '/api/content',
        fileNote: '/api/project/note',
        archive: '/api/fs/archive',
        rename: '/api/fs/rename',
        batchRename: '/api/fs/batch_rename',
        delete: '/api/fs/delete',
        move: '/api/fs/move',
        save: '/api/fs/save',
        stageAll: '/api/actions/stage_all',
        categorize: '/api/actions/categorize',
        terminate: '/api/actions/terminate',
        pin: '/api/workspaces/pin',
        stats: '/api/project/stats',
        generate: '/api/generate',
        collectPaths: '/api/fs/collect_paths',
        favorites: '/api/project/favorites',
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
