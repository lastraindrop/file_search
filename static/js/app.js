const App = {
    state: {
        projectPath: "",
        staging: new Set(),
        currentFile: null,
        socket: null,
        isEditing: false,
        rawContent: "",
        selectedFiles: new Set()
    },

    init: () => {
        // Initial setup if needed
        document.getElementById('searchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') App.startSearch();
        });
    },

    openProject: async () => {
        const path = document.getElementById('projectPath').value.trim();
        if (!path) return alert("Please enter a valid path");

        try {
            const res = await fetch('/api/open', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ path })
            });
            
            if (!res.ok) throw new Error((await res.json()).detail);
            
            const data = await res.json();
            App.state.projectPath = path;
            const rootContainer = document.getElementById('fileTreeRoot');
            rootContainer.innerHTML = '';
            rootContainer.appendChild(App.renderTree(data.root));
            alert(`Project loaded: ${data.name}`);
        } catch (e) {
            alert("Error: " + e.message);
        }
    },

    renderTree: (node) => {
        const container = document.createElement('div');
        container.className = 'ms-3';
        const header = document.createElement('div');
        header.className = 'tree-node text-truncate d-flex align-items-center my-1';
        header.style.cursor = 'pointer';
        
        const isChecked = App.state.selectedFiles.has(node.path) ? 'checked' : '';
        const cb = `<input type="checkbox" class="form-check-input file-checkbox me-2 flex-shrink-0" style="margin-top:0;" value="${node.path}" onclick="event.stopPropagation()" onchange="App.toggleSelect('${node.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}', this.checked)" ${isChecked}>`;

        const expanderIcon = node.type === 'dir' ? '▶' : '';
        header.innerHTML = `${cb}<span class="tree-expander me-1 flex-shrink-0" style="width:16px; text-align:center;">${expanderIcon}</span><span class="icon me-1 flex-shrink-0">${node.type === 'dir' ? '📁' : '📄'}</span><span class="text-truncate">${node.name}</span>`;
        container.appendChild(header);

        if (node.type === 'dir') {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'tree-children';
            childrenContainer.style.display = 'none';
            container.appendChild(childrenContainer);

            let loaded = false;
            header.onclick = async (e) => {
                e.stopPropagation();
                if (e.target.tagName === 'INPUT') return;
                
                const isHidden = childrenContainer.style.display === 'none';
                if (isHidden && !loaded) {
                    header.querySelector('.tree-expander').innerText = '...';
                    try {
                        const res = await fetch('/api/fs/children', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ path: node.path })
                        });
                        const data = await res.json();
                        childrenContainer.innerHTML = '';
                        data.children.forEach(child => {
                            childrenContainer.appendChild(App.renderTree(child));
                        });
                        loaded = true;
                    } catch (err) {
                        console.error("Failed to load children", err);
                    }
                }
                
                childrenContainer.style.display = isHidden ? 'block' : 'none';
                header.querySelector('.tree-expander').innerText = isHidden ? '▼' : '▶';
            };
        } else {
            header.onclick = (e) => {
                e.stopPropagation();
                if (e.target.tagName === 'INPUT') return;
                document.querySelectorAll('.tree-node').forEach(n => n.classList.remove('active'));
                header.classList.add('active');
                App.previewFile(node.path);
            };
        }
        return container;
    },

    previewFile: async (path) => {
        App.state.currentFile = path;
        App.state.isEditing = false;
        document.getElementById('fileControls').style.display = 'inline-flex';
        document.getElementById('btnEditSave').innerHTML = '📝 Edit';
        document.getElementById('codeEditor').style.display = 'none';
        document.getElementById('preBlock').style.display = 'block';

        document.getElementById('currentFileName').innerText = path.split(/[\/\\]/).pop();
        const codeEl = document.getElementById('codePreview');
        codeEl.innerText = "Loading...";
        
        try {
            const res = await fetch(`/api/content?path=${encodeURIComponent(path)}`);
            const data = await res.json();
            App.state.rawContent = data.content;
            codeEl.innerText = data.content;
            hljs.highlightElement(codeEl);
        } catch (e) {
            codeEl.innerText = "Error loading file.";
        }
    },

    startSearch: () => {
        if (!App.state.projectPath) return alert("Open a project first.");
        const query = document.getElementById('searchInput').value;
        const mode = document.getElementById('searchMode').value;
        const isInverse = document.getElementById('isInverse').checked;
        const isCaseSensitive = document.getElementById('isCaseSensitive').checked;
        const resultsDiv = document.getElementById('searchResultsList');
        
        // Switch to search tab
        const tab = new bootstrap.Tab(document.getElementById('tab-search'));
        tab.show();

        resultsDiv.innerHTML = '';
        document.getElementById('searchStatus').style.display = 'block';

        // Close existing socket
        if (App.state.socket) App.state.socket.close();

        // Open WebSocket
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/search?path=${encodeURIComponent(App.state.projectPath)}&query=${encodeURIComponent(query)}&mode=${mode}&inverse=${isInverse}&case_sensitive=${isCaseSensitive}`;
        
        App.state.socket = new WebSocket(wsUrl);
        
        App.state.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.status === "DONE") {
                document.getElementById('searchStatus').style.display = 'none';
                App.state.socket.close();
                return;
            }
            
            const item = document.createElement('a');
            item.className = 'list-group-item list-group-item-action p-2 staging-item';
            
            const escPath = data.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            const isChecked = App.state.selectedFiles.has(data.path) ? 'checked' : '';
            const cb = `<input type="checkbox" class="form-check-input me-2 file-checkbox" value="${data.path}" onclick="event.stopPropagation()" onchange="App.toggleSelect('${escPath}', this.checked)" ${isChecked}>`;

            item.innerHTML = `
                <div class="d-flex w-100 justify-content-between align-items-center">
                    <div class="text-truncate">
                        ${cb}
                        <span class="fw-bold">${data.name}</span>
                    </div>
                    <small class="text-muted ms-2">${data.type}</small>
                </div>
                <small class="text-muted text-truncate d-block mt-1">${data.path}</small>
            `;
            item.onclick = (e) => {
                if(e.target.tagName === 'INPUT') return;
                App.previewFile(data.path);
            };
            resultsDiv.appendChild(item);
        };
    },

    toggleSelect: (path, isChecked) => {
        if (isChecked) App.state.selectedFiles.add(path);
        else App.state.selectedFiles.delete(path);
        App.updateBulkActions();
    },

    toggleSelectAll: (isChecked) => {
        const cbs = document.querySelectorAll('.file-checkbox');
        cbs.forEach(cb => {
            cb.checked = isChecked;
            if (isChecked) App.state.selectedFiles.add(cb.value);
            else App.state.selectedFiles.delete(cb.value);
        });
        App.updateBulkActions();
    },

    updateBulkActions: () => {
        const count = App.state.selectedFiles.size;
        const bulkDiv = document.getElementById('bulkActions');
        const countLabel = document.getElementById('selectedCount');
        if (count > 0) {
            bulkDiv.style.setProperty('display', 'flex', 'important');
            countLabel.innerText = `${count} selected`;
        } else {
            bulkDiv.style.setProperty('display', 'none', 'important');
            document.getElementById('selectAllCb').checked = false;
        }
    },

    bulkDelete: async () => {
        const paths = Array.from(App.state.selectedFiles);
        if(paths.length === 0) return;
        if(confirm(`Are you sure you want to PERMANENTLY delete ${paths.length} items?`)) {
            try {
                const res = await fetch('/api/fs/delete', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({paths: paths})
                });
                if(!res.ok) throw new Error((await res.json()).detail);
                App.state.selectedFiles.clear();
                App.updateBulkActions();
                App.openProject(); // Refresh tree
            } catch(e) { alert("Error: " + e.message); }
        }
    },

    bulkMove: async () => {
        const paths = Array.from(App.state.selectedFiles);
        if(paths.length === 0) return;
        const dstDir = prompt("Enter one destination directory path for all selected items:");
        if(dstDir) {
            try {
                const res = await fetch('/api/fs/move', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({src_paths: paths, dst_dir: dstDir})
                });
                if(!res.ok) throw new Error((await res.json()).detail);
                App.state.selectedFiles.clear();
                App.updateBulkActions();
                App.openProject(); // Refresh tree
            } catch(e) { alert("Error: " + e.message); }
        }
    },

    bulkStage: () => {
        App.state.selectedFiles.forEach(p => App.state.staging.add(p));
        App.state.selectedFiles.clear();
        App.updateBulkActions();
        document.querySelectorAll('.file-checkbox').forEach(cb => cb.checked = false);
        document.getElementById('selectAllCb').checked = false;
        App.renderStaging();
    },

    renameFile: async () => {
        if (!App.state.currentFile) return;
        const oldName = App.state.currentFile.split(/[\/\\]/).pop();
        const newName = prompt("Rename to:", oldName);
        if (newName && newName !== oldName) {
            try {
                const res = await fetch('/api/fs/rename', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({path: App.state.currentFile, new_name: newName})
                });
                if (!res.ok) throw new Error((await res.json()).detail);
                const data = await res.json();
                App.state.currentFile = data.new_path;
                document.getElementById('currentFileName').innerText = data.new_path.split(/[\/\\]/).pop();
                App.openProject(); // Refresh tree
            } catch (e) { alert("Error: " + e.message); }
        }
    },

    deleteFile: async () => {
        if (!App.state.currentFile) return;
        if (confirm(`Are you sure you want to PERMANENTLY delete:\n${App.state.currentFile}?`)) {
            try {
                const res = await fetch('/api/fs/delete', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({paths: [App.state.currentFile]})
                });
                if (!res.ok) throw new Error((await res.json()).detail);
                App.state.currentFile = null;
                document.getElementById('currentFileName').innerText = "Select a file to preview...";
                document.getElementById('codePreview').innerText = "";
                document.getElementById('fileControls').style.display = 'none';
                App.openProject(); // Refresh tree
            } catch (e) { alert("Error: " + e.message); }
        }
    },

    moveFile: async () => {
        if (!App.state.currentFile) return;
        const currentDir = App.state.currentFile.substring(0, App.state.currentFile.lastIndexOf('\\') !== -1 ? App.state.currentFile.lastIndexOf('\\') : App.state.currentFile.lastIndexOf('/'));
        const dstDir = prompt("Enter destination directory path:", currentDir);
        if (dstDir && dstDir !== currentDir) {
            try {
                const res = await fetch('/api/fs/move', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({src_paths: [App.state.currentFile], dst_dir: dstDir})
                });
                if (!res.ok) throw new Error((await res.json()).detail);
                const data = await res.json();
                App.state.currentFile = data.new_paths[0]; // array response now
                App.openProject(); // Refresh tree
            } catch (e) { alert("Error: " + e.message); }
        }
    },

    toggleEdit: async () => {
        if (!App.state.currentFile) return;
        if (!App.state.isEditing) {
            App.state.isEditing = true;
            document.getElementById('preBlock').style.display = 'none';
            const editor = document.getElementById('codeEditor');
            editor.value = App.state.rawContent;
            editor.style.display = 'block';
            document.getElementById('btnEditSave').innerHTML = '💾 Save';
        } else {
            const newContent = document.getElementById('codeEditor').value;
            try {
                const res = await fetch('/api/fs/save', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({path: App.state.currentFile, content: newContent})
                });
                if (!res.ok) throw new Error((await res.json()).detail);
                App.state.isEditing = false;
                document.getElementById('codeEditor').style.display = 'none';
                document.getElementById('preBlock').style.display = 'block';
                document.getElementById('btnEditSave').innerHTML = '📝 Edit';
                alert("File saved successfully.");
                App.previewFile(App.state.currentFile); // re-highlight
            } catch (e) { alert("Error: " + e.message); }
        }
    },

    addToStaging: () => {
        if (!App.state.currentFile) return;
        if (App.state.staging.has(App.state.currentFile)) return;
        
        App.state.staging.add(App.state.currentFile);
        App.renderStaging();
    },

    renderStaging: () => {
        const list = document.getElementById('stagingList');
        list.innerHTML = '';
        let totalFiles = 0;
        
        App.state.staging.forEach(path => {
            totalFiles++;
            const item = document.createElement('div');
            item.className = 'list-group-item d-flex justify-content-between align-items-center p-1 staging-item';
            
            // Escape path for the onclick event
            const escPath = path.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            item.innerHTML = `
                <span class="text-truncate" title="${path}">${path.split(/[\/\\]/).pop()}</span>
                <button class="btn btn-sm btn-outline-danger py-0 px-1" onclick="App.removeFromStaging('${escPath}')">×</button>
            `;
            list.appendChild(item);
        });

        document.getElementById('tokenEstimate').innerText = `${totalFiles} Files`;
    },

    removeFromStaging: (path) => {
        App.state.staging.delete(path);
        App.renderStaging();
    },

    clearStaging: () => {
        App.state.staging.clear();
        App.renderStaging();
    },

    generateContext: async () => {
        if (App.state.staging.size === 0) return alert("Staging is empty.");
        
        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ files: Array.from(App.state.staging) })
            });
            
            const data = await res.json();
            await navigator.clipboard.writeText(data.content);
            alert("✅ Context copied to clipboard!");
        } catch (e) {
            alert("Error: " + e.message);
        }
    }
};

App.init();
