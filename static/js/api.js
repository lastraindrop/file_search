import { state, config } from './state.js';

export async function _fetch(url, options = {}) {
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
    const res = await _fetch(config.endpoints.openProject, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path: path })
    });
    return await res.json();
}

export async function fetchProjectConfig(path) {
    const res = await _fetch(`/api/project/config?path=${encodeURIComponent(path)}`);
    return await res.json();
}

export async function saveProjectSettings(path, settings) {
    return await _fetch('/api/project/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            project_path: path,
            settings: settings
        })
    });
}

export async function fetchGlobalSettings() {
    const res = await _fetch('/api/global/settings');
    return await res.json();
}

export async function saveGlobalSettings(body) {
    return await _fetch('/api/global/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
    });
}

export async function fetchChildren(path) {
    const res = await _fetch('/api/fs/children', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path: path })
    });
    return await res.json();
}

export async function fetchContent(path, limitMb = 1) {
    const res = await _fetch(`/api/content?path=${encodeURIComponent(path)}`);
    return await res.json();
}

export async function saveFileNote(projectPath, filePath, note) {
    return await _fetch('/api/project/note', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            project_path: projectPath,
            file_path: filePath,
            note: note
        })
    });
}

export async function archiveFiles(projectRoot, paths, outputName) {
    return await _fetch('/api/fs/archive', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            paths: paths,
            output_name: outputName,
            project_root: projectRoot
        })
    });
}

export async function renameFile(projectPath, oldPath, newName) {
    return await _fetch('/api/fs/rename', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            project_path: projectPath,
            path: oldPath,
            new_name: newName
        })
    });
}

export async function batchRename(projectPath, paths, pattern, replacement, dryRun = true) {
    const res = await _fetch('/api/fs/batch_rename', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            project_path: projectPath,
            paths: paths,
            pattern: pattern,
            replacement: replacement,
            dry_run: dryRun
        })
    });
    return await res.json();
}

export async function deleteFiles(projectPath, paths) {
    return await _fetch('/api/fs/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            project_path: projectPath,
            paths: paths
        })
    });
}

export async function moveFiles(srcPaths, dstDir) {
    const res = await _fetch('/api/fs/move', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            src_paths: srcPaths,
            dst_dir: dstDir
        })
    });
    return await res.json();
}

export async function saveFileContent(path, content) {
    return await _fetch('/api/fs/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path: path, content: content })
    });
}

export async function stageAll(projectPath, mode = 'files', applyExcludes = true) {
    const res = await _fetch('/api/actions/stage_all', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            project_path: projectPath,
            mode: mode,
            apply_excludes: applyExcludes
        })
    });
    return await res.json();
}

export async function categorizeFiles(projectPath, paths, categoryName) {
    const res = await _fetch('/api/actions/categorize', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            project_path: projectPath,
            paths: paths,
            category_name: categoryName
        })
    });
    return await res.json();
}

export async function terminateProcess(pid) {
    return await _fetch('/api/actions/terminate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ pid: pid })
    });
}

export async function togglePin(path) {
    const res = await _fetch('/api/workspaces/pin', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path: path })
    });
    return await res.json();
}

export async function fetchStats(projectPath, paths) {
    const res = await _fetch('/api/project/stats', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            paths: paths,
            project_path: projectPath
        })
    });
    return await res.json();
}

export async function generateContext(params) {
    const res = await _fetch('/api/generate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(params)
    });
    return await res.json();
}

export async function collectPaths(params) {
    const res = await _fetch('/api/fs/collect_paths', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(params)
    });
    return await res.json();
}

export async function openInOs(projectPath, path) {
    return await _fetch(config.endpoints.openPathInOs, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            project_path: projectPath,
            path: path
        })
    });
}

export async function toggleFavorite(projectPath, path, action, group) {
    return await _fetch('/api/project/favorites', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            project_path: projectPath,
            group_name: group,
            file_paths: [path],
            action: action
        })
    });
}
