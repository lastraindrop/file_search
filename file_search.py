import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, scrolledtext
import pathlib
import os
import threading
import queue
import sys
import subprocess
from core_logic import DataManager, FileUtils, SearchWorker, FileOps

# --- Constants ---
PREVIEW_LIMIT = 100000  # Max characters to display in preview
TOKEN_RATIO = 4         # Character to token ratio estimate
SEARCH_POLL_MS = 100    # Queue polling interval
class FileWorkbenchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python 上下文收集助手 v3.1 (Core 分离版)")
        self.root.geometry("1280x850")

        self.data_mgr = DataManager()
        self.current_dir = None
        self.current_proj_config = None
        self.search_thread = None
        self.staging_files = [] 
        self.stop_event = threading.Event()
        self.result_queue = queue.Queue()
        
        self.search_mode_var = tk.StringVar(value="smart")
        self.exclude_var = tk.StringVar()
        self.current_group_var = tk.StringVar()
        self.search_include_dirs_var = tk.BooleanVar(value=False)
        self.is_inverse_var = tk.BooleanVar(value=False)
        self.case_sensitive_var = tk.BooleanVar(value=False)
        self.recursive_copy_var = tk.BooleanVar(value=True)
        self.use_gitignore_var = tk.BooleanVar(value=True)

        self._init_ui()
        self._init_context_menu()
        
        last_dir = self.data_mgr.data.get("last_directory")
        if last_dir and os.path.exists(last_dir):
            self.load_project(last_dir)
            
        self.root.after(SEARCH_POLL_MS, self.process_queue)

    def _init_ui(self):
        top_bar = ttk.Frame(self.root, padding=5)
        top_bar.pack(fill=tk.X)
        ttk.Button(top_bar, text="📂 打开项目", command=self.select_directory).pack(side=tk.LEFT)
        self.lbl_dir = ttk.Label(top_bar, text="未选择项目", foreground="gray", font=("Consolas", 10))
        self.lbl_dir.pack(side=tk.LEFT, padx=10, pady=2)
        ttk.Button(top_bar, text="🌲 复制项目结构", command=self.copy_project_tree).pack(side=tk.RIGHT, padx=5)

        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.left_nav = ttk.Notebook(self.main_paned)
        self.main_paned.add(self.left_nav, weight=2)
        
        self.tab_search_frame = ttk.Frame(self.left_nav)
        self.left_nav.add(self.tab_search_frame, text="🔍 搜索")
        self._init_search_tab()
        
        self.tab_tree_frame = ttk.Frame(self.left_nav)
        self.left_nav.add(self.tab_tree_frame, text="📂 浏览")
        self._init_project_tree_tab()

        self.preview_frame = ttk.LabelFrame(self.main_paned, text="📄 内容预览 (只读)", padding=5)
        self.main_paned.add(self.preview_frame, weight=4)
        
        self.preview_ctrl = ttk.Frame(self.preview_frame)
        self.preview_ctrl.pack(fill=tk.X, pady=(0, 2))
        self.btn_edit_save = ttk.Button(self.preview_ctrl, text="✏️ 开启编辑", command=self.toggle_preview_edit, state=tk.DISABLED)
        self.btn_edit_save.pack(side=tk.RIGHT)
        
        self.preview_text = scrolledtext.ScrolledText(self.preview_frame, font=("Consolas", 10), undo=True)
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        self.preview_text.config(state=tk.DISABLED)

        self.right_nav = ttk.Notebook(self.main_paned)
        self.main_paned.add(self.right_nav, weight=2)
        self.tab_staging = ttk.Frame(self.right_nav)
        self.right_nav.add(self.tab_staging, text="🛒 清单")
        self._init_staging_tab()
        self.tab_fav = ttk.Frame(self.right_nav)
        self.right_nav.add(self.tab_fav, text="📚 收藏")
        self._init_fav_tab()
        
        self.status_frame = ttk.Frame(self.root, relief=tk.SUNKEN, padding=2)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.lbl_status = ttk.Label(self.status_frame, text="就绪")
        self.lbl_status.pack(side=tk.LEFT)
        self.lbl_stats = ttk.Label(self.status_frame, text="清单: 0 文件 | 0 Tokens")
        self.lbl_stats.pack(side=tk.RIGHT)

    def _init_search_tab(self):
        f = self.tab_search_frame
        ctrl = ttk.Frame(f, padding=5); ctrl.pack(fill=tk.X)
        ttk.Label(ctrl, text="排除:").pack(side=tk.LEFT)
        ttk.Entry(ctrl, textvariable=self.exclude_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        s_box = ttk.Frame(f, padding=5); s_box.pack(fill=tk.X)
        self.search_var = tk.StringVar(); self.search_var.trace("w", self.on_search_input)
        self.search_entry = ttk.Entry(s_box, textvariable=self.search_var); self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        m_box = ttk.Frame(f, padding=2); m_box.pack(fill=tk.X)
        for v, t in {"smart":"智能","exact":"精确","regex":"正则","content":"内容"}.items():
            ttk.Radiobutton(m_box, text=t, variable=self.search_mode_var, value=v, command=self.on_search_input).pack(side=tk.LEFT, padx=2)
        
        adv_box = ttk.Frame(f, padding=2); adv_box.pack(fill=tk.X)
        ttk.Checkbutton(adv_box, text="反向匹配", variable=self.is_inverse_var, command=self.on_search_input).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(adv_box, text="区分大小写", variable=self.case_sensitive_var, command=self.on_search_input).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(adv_box, text="包括目录", variable=self.search_include_dirs_var, command=self.on_search_input).pack(side=tk.LEFT, padx=5)
        
        self.tree_search = ttk.Treeview(f, columns=("file", "path"), show="headings", selectmode="extended")
        self.tree_search.heading("file", text="文件名"); self.tree_search.column("file", width=100)
        self.tree_search.heading("path", text="路径"); self.tree_search.column("path", width=150)
        self.tree_search.pack(fill=tk.BOTH, expand=True)
        self.tree_search.bind("<<TreeviewSelect>>", self.on_tree_select_preview)
        self.tree_search.bind("<Double-1>", lambda e: self.add_selected_to_staging())

    def _init_project_tree_tab(self):
        self.tree_proj = ttk.Treeview(self.tab_tree_frame, show="tree", selectmode="extended")
        self.tree_proj.pack(fill=tk.BOTH, expand=True)
        self.tree_proj.bind("<<TreeviewSelect>>", self.on_tree_select_preview)
        self.tree_proj.bind("<Double-1>", self.on_tree_double_click)
        self.tree_proj.bind("<<TreeviewOpen>>", self.on_tree_expand)

    def _init_fav_tab(self):
        c = ttk.Frame(self.tab_fav, padding=5); c.pack(fill=tk.X)
        self.combo_groups = ttk.Combobox(c, textvariable=self.current_group_var, state="readonly", width=15)
        self.combo_groups.pack(side=tk.LEFT, padx=5); self.combo_groups.bind("<<ComboboxSelected>>", self.on_group_changed)
        ttk.Button(c, text="➕", width=3, command=self.create_group).pack(side=tk.LEFT)
        self.tree_fav = ttk.Treeview(self.tab_fav, columns=("path",), show="tree", selectmode="extended")
        self.tree_fav.pack(fill=tk.BOTH, expand=True)
        ttk.Button(self.tab_fav, text="⬇ 载入到清单", command=self.load_group_to_staging).pack(fill=tk.X)

    def _init_staging_tab(self):
        self.tree_staging = ttk.Treeview(self.tab_staging, columns=("path", "size"), show="tree headings", selectmode="extended")
        self.tree_staging.heading("#0", text="文件"); self.tree_staging.column("#0", width=150)
        self.tree_staging.column("path", width=0, stretch=False)
        self.tree_staging.heading("size", text="大小"); self.tree_staging.column("size", width=80)
        self.tree_staging.pack(fill=tk.BOTH, expand=True)
        
        act = ttk.Frame(self.tab_staging, padding=5); act.pack(fill=tk.X)
        ttk.Button(act, text="🚀 生成 AI 上下文", command=self.copy_all_staging_content).pack(fill=tk.X, pady=2)
        ttk.Button(act, text="清空", command=self.clear_staging).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(act, text="移除", command=self.remove_staging_selection).pack(side=tk.RIGHT, fill=tk.X, expand=True)

    def _init_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="📂 所在文件夹", command=self.ctx_open_location)
        self.context_menu.add_command(label="📄 打开文件", command=self.ctx_open_file)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✏️ 重命名", command=self.ctx_rename_file)
        self.context_menu.add_command(label="✂️ 移动至...", command=self.ctx_move_file)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🗑️ 删除", command=self.ctx_delete_file)
        for t in [self.tree_search, self.tree_fav, self.tree_staging, self.tree_proj]: t.bind("<Button-3>", self.show_context_menu)

    def select_directory(self):
        path = filedialog.askdirectory()
        if path: self.load_project(path)

    def load_project(self, path_str):
        self.current_dir = pathlib.Path(path_str)
        self.lbl_dir.config(text=f"项目: {self.current_dir.name}", foreground="black")
        self.data_mgr.data["last_directory"] = path_str
        self.current_proj_config = self.data_mgr.get_project_data(path_str)
        self.exclude_var.set(self.current_proj_config.get("excludes", ""))
        self.update_group_combo()
        self.current_group_var.set(self.current_proj_config.get("current_group", "默认组"))
        for item in self.tree_proj.get_children(): self.tree_proj.delete(item)
        root_node = self.tree_proj.insert("", "end", text=f"📁 {self.current_dir.name}", open=True)
        self.populate_tree(root_node, self.current_dir)
        self.refresh_fav_tree()
        self.data_mgr.save()
        self.on_search_input()
        self.update_stats()

    def update_stats(self):
        count = len(self.staging_files)
        total_chars = 0
        for p_str in self.staging_files:
            p = pathlib.Path(p_str)
            if p.is_file(): total_chars += p.stat().st_size if p.exists() else 0
        self.lbl_stats.config(text=f"清单: {count} 项 | 估算 {total_chars//TOKEN_RATIO} Tokens")

    def on_search_input(self, *args):
        if not self.current_dir: return
        if self.search_thread and self.search_thread.is_alive(): self.stop_event.set()
        for item in self.tree_search.get_children(): self.tree_search.delete(item)
        self.stop_event = threading.Event(); self.result_queue = queue.Queue()
        self.lbl_status.config(text="扫描中...")
        self.search_thread = SearchWorker(self.current_dir, self.search_var.get(), self.search_mode_var.get(), 
                                         self.exclude_var.get(), self.search_include_dirs_var.get(), 
                                         self.result_queue, self.stop_event, self.use_gitignore_var.get(),
                                         is_inverse=self.is_inverse_var.get(), case_sensitive=self.case_sensitive_var.get())
        self.search_thread.start()

    def process_queue(self):
        try:
            while True:
                path_str, m_type = self.result_queue.get_nowait()
                if path_str == "DONE":
                    self.lbl_status.config(text=f"就绪 ({len(self.tree_search.get_children())}项)")
                    break
                p = pathlib.Path(path_str); rel = p.relative_to(self.current_dir) if self.current_dir in p.parents else p.name
                self.tree_search.insert("", "end", values=(("📁 " if p.is_dir() else "📄 ") + p.name, str(rel)))
        except queue.Empty: pass
        self.root.after(SEARCH_POLL_MS, self.process_queue)

    def on_tree_select_preview(self, event):
        tree = event.widget; sel = tree.selection()
        if not sel: return
        full_path = None
        if tree == self.tree_search: full_path = self.current_dir / tree.item(sel[0])['values'][1]
        elif tree == self.tree_proj: full_path = self.get_tree_path(sel[0])
        elif tree == self.tree_staging: full_path = pathlib.Path(tree.item(sel[0])['values'][1])
        elif tree == self.tree_fav: full_path = pathlib.Path(tree.item(sel[0])['values'][0])
        if not full_path or not full_path.exists(): return
        
        self.current_preview_path = full_path
        self.is_editing = False
        self.btn_edit_save.config(text="✏️ 开启编辑")
        self.preview_frame.config(text="📄 内容预览 (只读)")
        
        self.preview_text.config(state=tk.NORMAL); self.preview_text.delete("1.0", tk.END)
        if full_path.is_file():
            if FileUtils.is_binary(full_path): 
                self.preview_text.insert(tk.END, "--- 二进制文件 ---")
                self.btn_edit_save.config(state=tk.DISABLED)
            else:
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='replace') as f: self.preview_text.insert(tk.END, f.read(PREVIEW_LIMIT))
                    self.btn_edit_save.config(state=tk.NORMAL)
                except Exception as e: 
                    self.preview_text.insert(tk.END, f"错误: {e}")
                    self.btn_edit_save.config(state=tk.DISABLED)
        else:
             self.preview_text.insert(tk.END, f"目录: {full_path}")
             self.btn_edit_save.config(state=tk.DISABLED)
        self.preview_text.config(state=tk.DISABLED); self.preview_text.see("1.0")

    def get_tree_path(self, node_id):
        parts = []
        curr = node_id
        while curr:
            name = self.tree_proj.item(curr)['text'].replace("📁 ", "").replace("📄 ", "")
            parts.insert(0, name)
            curr = self.tree_proj.parent(curr)
        return self.current_dir.parent / pathlib.Path(*parts) if parts else None

    def on_tree_expand(self, event):
        node_id = self.tree_proj.focus(); p = self.get_tree_path(node_id)
        if not p or not p.is_dir(): return
        for child in self.tree_proj.get_children(node_id):
            if self.tree_proj.item(child)['text'] == "加载中...":
                self.tree_proj.delete(child)
                self.populate_tree(node_id, p); break

    def populate_tree(self, parent_node, path):
        try:
            ex = [e.lower().strip() for e in self.exclude_var.get().split() if e.strip()]
            # Update: Use get_gitignore_spec
            git_spec = FileUtils.get_gitignore_spec(self.current_dir) if self.use_gitignore_var.get() else None
            
            for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower())):
                # Update: pass git_spec
                rel_path = pathlib.Path(entry.path).relative_to(self.current_dir)
                if FileUtils.should_ignore(entry.name, rel_path, ex, git_spec): continue
                
                node = self.tree_proj.insert(parent_node, "end", text=("📁 " if entry.is_dir() else "📄 ") + entry.name, open=False)
                if entry.is_dir(): self.tree_proj.insert(node, "end", text="加载中...")
        except: pass

    def copy_project_tree(self):
        tree_text = FileUtils.generate_ascii_tree(self.current_dir, self.exclude_var.get(), self.use_gitignore_var.get())
        self.root.clipboard_clear(); self.root.clipboard_append(tree_text); messagebox.showinfo("成功", "结构已复制")

    def _add_paths_to_staging(self, paths):
        for p_str in paths:
            if p_str not in self.staging_files:
                self.staging_files.append(p_str); p = pathlib.Path(p_str)
                sz = p.stat().st_size if p.is_file() else 0
                self.tree_staging.insert("", "end", text=("📁 " if p.is_dir() else "📄 ") + p.name, values=("", p_str, f"{sz/1024:.1f}KB"))
        self.update_stats()

    def add_selected_to_staging(self):
        self._add_paths_to_staging([str(self.current_dir / self.tree_search.item(i)['values'][1]) for i in self.tree_search.selection()])

    def on_tree_double_click(self, event):
        p = self.get_tree_path(self.tree_proj.selection()[0])
        if p: self._add_paths_to_staging([str(p)])

    def clear_staging(self):
        self.staging_files.clear()
        for i in self.tree_staging.get_children(): self.tree_staging.delete(i)
        self.update_stats()

    def remove_staging_selection(self):
        for i in self.tree_staging.selection():
            val = self.tree_staging.item(i)['values'][1]
            if val in self.staging_files: self.staging_files.remove(val)
            self.tree_staging.delete(i)
        self.update_stats()

    def copy_all_staging_content(self):
        final = []
        for p_str in self.staging_files:
            p = pathlib.Path(p_str)
            if p.is_file():
                if FileUtils.is_binary(p): continue
                try:
                    text = p.read_text('utf-8', 'ignore')
                    final.append(f"File: {p.name}\n```{FileUtils.get_language_tag(p.suffix)}\n{text}\n```\n\n")
                except: pass
        if final: self.root.clipboard_clear(); self.root.clipboard_append("".join(final)); messagebox.showinfo("完成", "内容已复制")

    def update_group_combo(self): self.combo_groups['values'] = list(self.current_proj_config["groups"].keys())
    def on_group_changed(self, e): self.refresh_fav_tree()
    def refresh_fav_tree(self):
        for i in self.tree_fav.get_children(): self.tree_fav.delete(i)
        grp = self.current_proj_config["groups"].get(self.current_group_var.get(), [])
        for ps in grp:
            p = pathlib.Path(ps)
            self.tree_fav.insert("", "end", text=("📁 " if p.is_dir() else "📄 ") + p.name, values=(ps,))

    def create_group(self):
        n = simpledialog.askstring("新建组", "名:")
        if n and n not in self.current_proj_config["groups"]:
            self.current_proj_config["groups"][n] = []; self.update_group_combo(); self.current_group_var.set(n); self.data_mgr.save()

    def load_group_to_staging(self): self._add_paths_to_staging(self.current_proj_config["groups"].get(self.current_group_var.get(), []))
    def toggle_preview_edit(self):
        if not hasattr(self, 'current_preview_path') or not self.current_preview_path: return
        if not getattr(self, 'is_editing', False):
            self.is_editing = True
            self.preview_text.config(state=tk.NORMAL)
            self.btn_edit_save.config(text="💾 保存文件")
            self.preview_frame.config(text="📄 内容预览 (编辑中)")
        else:
            try:
                content = self.preview_text.get("1.0", tk.END)
                FileOps.save_content(str(self.current_preview_path), content[:-1])
                self.is_editing = False
                self.preview_text.config(state=tk.DISABLED)
                self.btn_edit_save.config(text="✏️ 开启编辑")
                self.preview_frame.config(text="📄 内容预览 (只读)")
                messagebox.showinfo("成功", "文件保存成功！")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败: {e}")

    def show_context_menu(self, e):
        self.active_tree = e.widget; i = self.active_tree.identify_row(e.y)
        if i:
            # Only change selection if clicked item is not already selected (preserve multi-select)
            if i not in self.active_tree.selection():
                self.active_tree.selection_set(i)
            self.context_menu.post(e.x_root, e.y_root)

    def _get_ctx_paths(self):
        try:
            paths = []
            for sel_id in self.active_tree.selection():
                if self.active_tree == self.tree_proj: 
                    p = self.get_tree_path(sel_id)
                else:
                    val = self.active_tree.item(sel_id)['values']
                    p_str = val[1] if self.active_tree != self.tree_fav else val[0]
                    if self.active_tree == self.tree_search: p_str = str(self.current_dir / p_str)
                    p = pathlib.Path(p_str)
                if p: paths.append(p)
            return paths
        except: return []

    def ctx_open_location(self):
        paths = self._get_ctx_paths()
        if paths: 
            p = paths[0]
            os.startfile(p.parent if p.is_file() else p)
        
    def ctx_open_file(self):
        paths = self._get_ctx_paths()
        for p in paths:
            if p.is_file(): os.startfile(p)

    def ctx_rename_file(self):
        paths = self._get_ctx_paths()
        if not paths: return
        if len(paths) > 1:
            messagebox.showwarning("警告", "无法同时对多个文件或目录进行重命名！请单独选中一项。")
            return
        p = paths[0]
        new_name = simpledialog.askstring("重命名", "新名称:", initialvalue=p.name)
        if new_name and new_name != p.name:
            try:
                FileOps.rename_file(str(p), new_name); self.load_project(str(self.current_dir))
            except Exception as e: messagebox.showerror("错误", str(e))

    def ctx_delete_file(self):
        paths = self._get_ctx_paths()
        if not paths: return
        msg = f"确定要永久删除这 {len(paths)} 个项目吗？" if len(paths) > 1 else f"确定要永久删除:\n{paths[0].name} ?"
        if messagebox.askyesno("确认批量删除", msg):
            try:
                for p in paths: FileOps.delete_file(str(p))
                self.load_project(str(self.current_dir))
            except Exception as e: messagebox.showerror("错误", f"删除中断: {str(e)}")

    def ctx_move_file(self):
        paths = self._get_ctx_paths()
        if not paths: return
        default_dir = str(paths[0].parent)
        dst_dir = filedialog.askdirectory(title=f"将 {len(paths)} 个项目移动至...", initialdir=default_dir)
        if dst_dir:
            try:
                for p in paths: 
                    if str(p.parent) != dst_dir: FileOps.move_file(str(p), dst_dir)
                self.load_project(str(self.current_dir))
            except Exception as e: messagebox.showerror("错误", f"移动中断: {str(e)}")

    def open_batch_io_dialog(self): pass # 保持原有逻辑

if __name__ == "__main__":
    root = tk.Tk(); ttk.Style().theme_use('clam'); app = FileWorkbenchApp(root); root.mainloop()
