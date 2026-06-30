import { state, config } from './state.js';

function _getApiToken() {
    if (state.globalSettings.api_token) return state.globalSettings.api_token;
    if (window.__FCTX_API_TOKEN__ && window.__FCTX_API_TOKEN__ !== "") return window.__FCTX_API_TOKEN__;
    return "";
}

export async function _fetch(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    const token = _getApiToken();
    if (token) headers['X-API-Token'] = token;
    const res = await fetch(url, { ...options, headers });
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
}

async function _post(url, data) {
    return await _fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
}

async function _postJson(url, data) {
    const res = await _post(url, data);
    return await res.json();
}

export async function loadWorkspaces() {
    try {
        const res = await _fetch(config.endpoints.workspaces);
        return await res.json();
    } catch (e) {
        throw new Error("Failed to load workspaces: " + e.message);
    }
}

export async function openProject(path) {
    return await _postJson(config.endpoints.openProject, { path });
}

export async function fetchProjectConfig(path) {
    const res = await _fetch(`${config.endpoints.projectConfig}?path=${encodeURIComponent(path)}`);
    return await res.json();
}

export async function saveProjectSettings(path, settings) {
    await _post(config.endpoints.projectSettings, { project_path: path, settings });
}

export async function fetchGlobalSettings() {
    const res = await _fetch(config.endpoints.globalSettings);
    return await res.json();
}

export async function saveGlobalSettings(body) {
    await _post(config.endpoints.globalSettings, body);
}

export async function fetchChildren(path) {
    return await _postJson(config.endpoints.fsChildren, { path });
}

export async function fetchContent(path) {
    const res = await _fetch(`${config.endpoints.content}?path=${encodeURIComponent(path)}`);
    return await res.json();
}

export async function saveFileNote(projectPath, filePath, note) {
    await _post(config.endpoints.fileNote, { project_path: projectPath, file_path: filePath, note });
}

export async function archiveFiles(projectRoot, paths, outputName) {
    await _post(config.endpoints.archive, { paths, output_name: outputName, project_root: projectRoot });
}

export async function renameFile(projectPath, oldPath, newName) {
    await _post(config.endpoints.rename, { project_path: projectPath, path: oldPath, new_name: newName });
}

export async function batchRename(projectPath, paths, pattern, replacement, dryRun = true) {
    return await _postJson(config.endpoints.batchRename, { project_path: projectPath, paths, pattern, replacement, dry_run: dryRun });
}

export async function deleteFiles(projectPath, paths) {
    await _post(config.endpoints.delete, { project_path: projectPath, paths });
}

export async function moveFiles(srcPaths, dstDir) {
    return await _postJson(config.endpoints.move, { src_paths: srcPaths, dst_dir: dstDir });
}

export async function copyFile(src, dstDir, projectRoot, taskId = null) {
    const srcs = Array.isArray(src) ? src : [src];
    const payload = { srcs, dst_dir: dstDir, project_root: projectRoot };
    if (taskId !== null) payload.task_id = taskId;
    return await _postJson(config.endpoints.copy, payload);
}

export async function getProgress(taskId) {
    return await _postJson(config.endpoints.progress, { task_id: taskId });
}

export async function newProgressTask(total) {
    return await _postJson(config.endpoints.progressNew, { total });
}

export async function extractArchive(zipPath, dstDir, projectRoot, taskId = null) {
    const payload = { zip_path: zipPath, dst_dir: dstDir, project_root: projectRoot };
    if (taskId !== null) payload.task_id = taskId;
    return await _postJson(config.endpoints.extract, payload);
}

export async function saveFileContent(path, content) {
    await _post(config.endpoints.save, { path, content });
}

export async function stageAll(projectPath, mode = 'files', applyExcludes = true) {
    return await _postJson(config.endpoints.stageAll, { project_path: projectPath, mode, apply_excludes: applyExcludes });
}

export async function categorizeFiles(projectPath, paths, categoryName) {
    return await _postJson(config.endpoints.categorize, { project_path: projectPath, paths, category_name: categoryName });
}

export async function terminateProcess(pid) {
    await _post(config.endpoints.terminate, { pid });
}

export async function togglePin(path) {
    return await _postJson(config.endpoints.pin, { path });
}

export async function fetchStats(projectPath, paths) {
    return await _postJson(config.endpoints.stats, { paths, project_path: projectPath });
}

export async function generateContext(params) {
    return await _postJson(config.endpoints.generate, params);
}

export async function collectPaths(params) {
    return await _postJson(config.endpoints.collectPaths, params);
}

export async function openInOs(projectPath, path) {
    await _post(config.endpoints.openPathInOs, { project_path: projectPath, path });
}

export async function toggleFavorite(projectPath, path, action, group) {
    await _post(config.endpoints.favorites, { project_path: projectPath, group_name: group, file_paths: [path], action });
}

export async function manageTag(projectPath, filePath, tag, action) {
    await _post(config.endpoints.manageTag, { project_path: projectPath, file_path: filePath, tag, action });
}

export async function createFile(parentPath, name, isDir = false) {
    return await _postJson(config.endpoints.createFile, { parent_path: parentPath, name, is_dir: isDir });
}
