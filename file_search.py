import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, scrolledtext
import pathlib
import os
import threading
import queue
import sys
import subprocess
import re
from file_cortex_core import DataManager, FileUtils, SearchWorker, FileOps, ContextFormatter, FormatUtils, ActionBridge, PathValidator, logger

# --- Constants ---
PREVIEW_LIMIT = 100000  # Max characters to display in preview
TOKEN_RATIO = 4         # Character to token ratio estimate
SEARCH_POLL_MS = 100    # Queue polling interval
class FileCortexApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FileCortex v5.7 Production | 工业级分析助手")
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
        self.selected_template_var = tk.StringVar(value="None")
        self.positive_tags = []
        self.negative_tags = []

        self._init_ui()
        self._init_context_menu()
        
        last_dir = self.data_mgr.data.get("last_directory")
        if last_dir and os.path.exists(last_dir):
            try:
                self.load_project(last_dir)
            except Exception as e:
                
                logger.error(f"Failed to auto-load last project {last_dir}: {e}")
            
        # self.root.after(SEARCH_POLL_MS, self.process_queue) -> Moved to trigger_search for efficiency

    def _init_ui(self):
        self._setup_styles()
        self._init_menu()
        self._init_top_bar()
        self._init_main_body()
        self._init_status_bar()

    def _setup_styles(self):
        self.style = ttk.Style()
        # Ensure we use a modern base if available, but keep it robust
        try:
            if sys.platform == 'win32':
                self.style.theme_use('vista')
            else:
                self.style.theme_use('clam')
        except Exception:
            pass # Standard fallback if themes aren't available

        self.style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))
        self.style.configure("Treeview", rowheight=25, font=("Segoe UI", 9))
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        
        # Consistent fonts for scrolledtext
        self.mono_font = ("Consolas", 10)
        self.ui_font = ("Segoe UI", 9)

    def _init_top_bar(self):
        top_bar = ttk.Frame(self.root, padding=5)
        top_bar.pack(fill=tk.X)
        ttk.Button(top_bar, text="📁 浏览", command=self.on_browse).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="🔄 刷新", command=self.on_refresh).pack(side=tk.LEFT, padx=5)
        
        self.btn_pin = ttk.Button(top_bar, text="☆", width=3, command=self.on_toggle_pin)
        self.btn_pin.pack(side=tk.LEFT, padx=2)

        self.lbl_project = ttk.Label(top_bar, text="请打开项目路径", font=("Segoe UI", 9))
        self.lbl_project.pack(side=tk.LEFT, padx=10, pady=2)
        ttk.Button(top_bar, text="🌲 复制项目结构", command=self.copy_project_tree).pack(side=tk.RIGHT, padx=5)

    def _init_main_body(self):
        # Improvement: Using vanilla tk.PanedWindow for highly visible sashes
        self.main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, 
                                        sashwidth=4, sashrelief=tk.RAISED, bg="#f0f0f0")
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Left: Search & Tree
        self.left_nav = ttk.Notebook(self.main_paned)
        self.main_paned.add(self.left_nav)
        
        self.tab_search_frame = ttk.Frame(self.left_nav)
        self.left_nav.add(self.tab_search_frame, text="🔍 搜索")
        self._init_search_tab()
        
        self.tab_tree_frame = ttk.Frame(self.left_nav)
        self.left_nav.add(self.tab_tree_frame, text="📂 浏览")
        self._init_project_tree_tab()

        # Middle: Preview
        self._init_preview_area()

        # Right: Staging & Favorites
        self.right_nav = ttk.Notebook(self.main_paned)
        self.main_paned.add(self.right_nav)
        self.tab_staging = ttk.Frame(self.right_nav)
        self.right_nav.add(self.tab_staging, text="🛒 清单")
        self._init_staging_tab()
        self.tab_fav = ttk.Frame(self.right_nav)
        self.right_nav.add(self.tab_fav, text="📚 收藏")
        self._init_fav_tab()
        self.tab_tools = ttk.Frame(self.right_nav)
        self.right_nav.add(self.tab_tools, text="⚙️ 工具")
        self._init_tools_tab()

    def _init_preview_area(self):
        self.preview_frame = ttk.LabelFrame(self.main_paned, text="📄 内容预览 (只读)", padding=5)
        self.main_paned.add(self.preview_frame)
        
        self.preview_ctrl = ttk.Frame(self.preview_frame)
        self.preview_ctrl.pack(fill=tk.X, pady=(0, 2))
        
        # New Search Bar for Preview (Hidden by default)
        self.search_frame = ttk.Frame(self.preview_ctrl)
        ttk.Label(self.search_frame, text="🔍 查找:").pack(side=tk.LEFT)
        self.preview_search_var = tk.StringVar()
        self.preview_search_entry = ttk.Entry(self.search_frame, textvariable=self.preview_search_var, width=20)
        self.preview_search_entry.pack(side=tk.LEFT, padx=5)
        self.preview_search_entry.bind("<Return>", lambda e: self.find_in_preview())
        self.preview_search_entry.bind("<Escape>", lambda e: self.toggle_preview_search(False))
        ttk.Button(self.search_frame, text="下一个", command=self.find_in_preview).pack(side=tk.LEFT)
        ttk.Button(self.search_frame, text="×", width=2, command=lambda: self.toggle_preview_search(False)).pack(side=tk.LEFT, padx=2)
        
        self.btn_edit_save = ttk.Button(self.preview_ctrl, text="✏️ 开启编辑", command=self.toggle_preview_edit, state=tk.DISABLED)
        self.btn_edit_save.pack(side=tk.RIGHT)
        
        self.preview_text = scrolledtext.ScrolledText(self.preview_frame, font=("Consolas", 10), undo=True)
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        self.preview_text.config(state=tk.DISABLED)
        
        self.preview_text.bind("<Control-f>", lambda e: self.toggle_preview_search(True))
        self.preview_text.tag_config("match", background="yellow", foreground="black")

    def toggle_preview_search(self, show=True):
        if show:
            self.search_frame.pack(side=tk.LEFT, padx=5)
            self.preview_search_entry.focus_set()
        else:
            self.search_frame.pack_forget()
            self.preview_text.tag_remove("match", "1.0", tk.END)

    def find_in_preview(self):
        query = self.preview_search_var.get()
        if not query: return
        
        # Start searching from the current insert position
        start_pos = self.preview_text.index(tk.INSERT)
        pos = self.preview_text.search(query, start_pos, stopindex=tk.END, nocase=True)
        
        if not pos:
            # Wrap around
            pos = self.preview_text.search(query, "1.0", stopindex=tk.END, nocase=True)
            
        if pos:
            # Highlight and scroll
            self.preview_text.tag_remove("match", "1.0", tk.END)
            end_pos = f"{pos}+{len(query)}c"
            self.preview_text.tag_add("match", pos, end_pos)
            self.preview_text.mark_set(tk.INSERT, end_pos)
            self.preview_text.see(pos)
        else:
            self.show_status("未找到匹配项", is_error=True)

    def _init_status_bar(self):
        self.status_frame = ttk.Frame(self.root, relief=tk.SUNKEN, padding=2)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.lbl_status = ttk.Label(self.status_frame, text="就绪", foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=5)
        
        self.lbl_stats = ttk.Label(self.status_frame, text="清单: 0 文件 | 0 Tokens")
        self.lbl_stats.pack(side=tk.RIGHT, padx=5)

    def show_status(self, message, is_error=False):
        """Displays a non-intrusive status message."""
        color = "#ef4444" if is_error else "#10b981"
        self.lbl_status.config(text=message, foreground=color)
        # Revert color after 3 seconds
        self.root.after(3000, lambda: self.lbl_status.config(foreground="#555"))

    def _init_search_tab(self):
        f = self.tab_search_frame
        ctrl = ttk.Frame(f, padding=5); ctrl.pack(fill=tk.X)
        ttk.Label(ctrl, text="排除:").pack(side=tk.LEFT)
        ttk.Entry(ctrl, textvariable=self.exclude_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        s_box = ttk.Frame(f, padding=5); s_box.pack(fill=tk.X)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(s_box, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_entry.bind("<Return>", lambda e: self.add_search_tag())
        ttk.Button(s_box, text="🔍 搜索", command=self.trigger_search).pack(side=tk.LEFT, padx=5)
        
        # New Tag Bar
        self.tag_bar = ttk.Frame(f, padding=(5, 0))
        self.tag_bar.pack(fill=tk.X)
        
        m_box = ttk.Frame(f, padding=2); m_box.pack(fill=tk.X)
        for v, t in {"smart":"智能","exact":"精确","regex":"正则","content":"内容"}.items():
            ttk.Radiobutton(m_box, text=t, variable=self.search_mode_var, value=v, command=self.trigger_search).pack(side=tk.LEFT, padx=2)
        
        adv_box = ttk.Frame(f, padding=2); adv_box.pack(fill=tk.X)
        ttk.Checkbutton(adv_box, text="反向匹配", variable=self.is_inverse_var, command=self.trigger_search).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(adv_box, text="区分大小写", variable=self.case_sensitive_var, command=self.trigger_search).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(adv_box, text="包括目录", variable=self.search_include_dirs_var, command=self.trigger_search).pack(side=tk.LEFT, padx=5)
        
        # Wrapped Treeview with Scrollbar
        tree_container = ttk.Frame(f)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        self.tree_search = ttk.Treeview(tree_container, columns=("file", "path", "size", "mtime", "ext"), show="headings", selectmode="extended")
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree_search.yview)
        self.tree_search.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_search.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree_search.heading("file", text="文件名", command=lambda: self.sort_tree_column(self.tree_search, "file", False))
        self.tree_search.column("file", width=120)
        self.tree_search.heading("path", text="相对路径", command=lambda: self.sort_tree_column(self.tree_search, "path", False))
        self.tree_search.column("path", width=150)
        self.tree_search.heading("size", text="大小", command=lambda: self.sort_tree_column(self.tree_search, "size", False))
        self.tree_search.column("size", width=80)
        self.tree_search.heading("mtime", text="修改时间", command=lambda: self.sort_tree_column(self.tree_search, "mtime", False))
        self.tree_search.column("mtime", width=120)
        self.tree_search.heading("ext", text="类型", command=lambda: self.sort_tree_column(self.tree_search, "ext", False))
        self.tree_search.column("ext", width=60)
        
        self.tree_search.bind("<<TreeviewSelect>>", self.on_tree_select_preview)
        self.tree_search.bind("<Double-1>", lambda e: self.add_selected_to_staging())

    def _init_project_tree_tab(self):
        tree_container = ttk.Frame(self.tab_tree_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        self.tree_proj = ttk.Treeview(tree_container, show="tree", selectmode="extended")
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree_proj.yview)
        self.tree_proj.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_proj.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_proj.bind("<<TreeviewSelect>>", self.on_tree_select_preview)
        self.tree_proj.bind("<Double-1>", self.on_tree_double_click)
        self.tree_proj.bind("<<TreeviewOpen>>", self.on_tree_expand)

    def _init_fav_tab(self):
        c = ttk.Frame(self.tab_fav, padding=5); c.pack(fill=tk.X)
        self.combo_groups = ttk.Combobox(c, textvariable=self.current_group_var, state="readonly", width=15)
        self.combo_groups.pack(side=tk.LEFT, padx=5); self.combo_groups.bind("<<ComboboxSelected>>", self.on_group_changed)
        ttk.Button(c, text="➕", width=3, command=self.create_group).pack(side=tk.LEFT)
        
        tree_container = ttk.Frame(self.tab_fav)
        tree_container.pack(fill=tk.BOTH, expand=True)
        self.tree_fav = ttk.Treeview(tree_container, columns=("path",), show="tree", selectmode="extended")
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree_fav.yview)
        self.tree_fav.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_fav.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Button(self.tab_fav, text="⬇ 载入到清单", command=self.load_group_to_staging).pack(fill=tk.X)

    def _init_staging_tab(self):
        # Filter Entry
        f_box = ttk.Frame(self.tab_staging, padding=5)
        f_box.pack(fill=tk.X)
        ttk.Label(f_box, text="🔍 过滤:").pack(side=tk.LEFT)
        self.staging_filter_var = tk.StringVar()
        self.staging_filter_var.trace_add("write", lambda *a: self.refresh_staging_ui(apply_filter=True))
        ttk.Entry(f_box, textvariable=self.staging_filter_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        tree_container = ttk.Frame(self.tab_staging)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        self.tree_staging = ttk.Treeview(tree_container, columns=("path", "size"), show="tree headings", selectmode="extended")
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree_staging.yview)
        self.tree_staging.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_staging.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree_staging.heading("#0", text="文件"); self.tree_staging.column("#0", width=150)
        self.tree_staging.column("path", width=0, stretch=False)
        self.tree_staging.heading("size", text="大小"); self.tree_staging.column("size", width=80)
        
        # Staging Context Menu
        self.staging_menu = tk.Menu(self.root, tearoff=0)
        self.staging_menu.add_command(label="移除选中", command=self.remove_staging_selection)
        self.staging_menu.add_command(label="移除当前过滤出的所有文件", command=self.remove_filtered_from_staging)
        self.staging_menu.add_separator()
        self.staging_menu.add_command(label="清空清单", command=self.clear_staging)
        self.tree_staging.bind("<Button-3>", lambda e: self.staging_menu.post(e.x_root, e.y_root))

        act = ttk.Frame(self.tab_staging, padding=5); act.pack(fill=tk.X)
        
        tpl_row = ttk.Frame(act)
        tpl_row.pack(fill=tk.X, pady=2)
        ttk.Label(tpl_row, text="📋 模板:").pack(side=tk.LEFT, padx=2)
        self.combo_templates = ttk.Combobox(tpl_row, textvariable=self.selected_template_var, state="readonly")
        self.combo_templates.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(act, text="🚀 导出工作区上下文", command=self.copy_all_staging_content).pack(fill=tk.X, pady=2)
        
        btn_row = ttk.Frame(act)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="➕ 智能全选", command=self.on_stage_all).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btn_row, text="🔗 复制路径", command=self.on_copy_staged_paths).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btn_row, text="清空", command=self.clear_staging).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btn_row, text="移除", command=self.remove_staging_selection).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _init_tools_tab(self):
        f = self.tab_tools
        self.tools_scroll = scrolledtext.ScrolledText(f, height=5, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4")
        self.tools_scroll.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.tools_scroll.config(state=tk.DISABLED)
        # Visual Tags for Logs
        self.tools_scroll.tag_config('green', foreground='#4ade80')
        self.tools_scroll.tag_config('red', foreground='#f87171')
        self.tools_scroll.tag_config('cyan', foreground='#38bdf8')
        self.tools_scroll.tag_config('yellow', foreground='#facc15')
        
        # Action Group Panels
        action_frame = ttk.Frame(f, padding=5)
        action_frame.pack(fill=tk.X)
        
        cat_group = ttk.LabelFrame(action_frame, text="⚡ 快速分类 (移动)", padding=5)
        cat_group.pack(fill=tk.X, pady=(0, 5))
        self.cat_btn_frame = ttk.Frame(cat_group)
        self.cat_btn_frame.pack(fill=tk.X)
        
        tool_group = ttk.LabelFrame(action_frame, text="🛠️ 工具集 (脚本)", padding=5)
        tool_group.pack(fill=tk.X)
        self.tool_btn_frame = ttk.Frame(tool_group)
        self.tool_btn_frame.pack(fill=tk.X)
        
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Button(f, text="🕵️ 查找重复文件 (SHA256)", command=self.open_duplicate_finder).pack(fill=tk.X, padx=5)

    def _init_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="📂 所在文件夹", command=self.ctx_open_location)
        self.context_menu.add_command(label="📄 打开文件", command=self.ctx_open_file)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📋 复制文件 (OS)", command=self.ctx_copy_file_to_os)
        self.context_menu.add_command(label="🔗 复制路径", command=self.ctx_copy_path_to_clipboard)
        self.context_menu.add_command(label="🧬 复制路径 (高级)...", command=self.ctx_collect_paths)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✏️ 重命名", command=self.ctx_rename_file)
        self.context_menu.add_command(label="✂️ 移动至...", command=self.ctx_move_file)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="⭐ 收藏至当前组", command=self.ctx_add_to_favorites)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🗑️ 删除", command=self.ctx_delete_file)
        for t in [self.tree_search, self.tree_fav, self.tree_staging, self.tree_proj]: t.bind("<Button-3>", self.show_context_menu)

    def on_browse(self, fixed_path=None):
        path = fixed_path if fixed_path else filedialog.askdirectory()
        if not path: return
        
        # Clear cache for gitignore if requested via refresh
        if fixed_path: FileUtils.clear_cache()
        
        self.current_dir = pathlib.Path(path)
        self.lbl_project.config(text=f"📂 {path}")
        self.load_project(path)

    def on_refresh(self):
        if self.current_dir:
            FileUtils.clear_cache()
            self.save_project_settings()
            self.load_project(str(self.current_dir))
        else:
            self.show_status("请先浏览一个项目", is_error=True)

    def save_project_settings(self):
        if self.current_proj_config:
            # Sync UI state to config object
            self.current_proj_config["excludes"] = self.exclude_var.get()
            self.current_proj_config["search_settings"] = {
                "mode": self.search_mode_var.get(),
                "case_sensitive": self.case_sensitive_var.get(),
                "inverse": self.is_inverse_var.get(),
                "include_dirs": self.search_include_dirs_var.get()
            }
            self.data_mgr.save()
            self.lbl_status.config(text="项目配置已保存")

    def load_project(self, path_str):
        self.results_count = 0 
        self.lbl_status.config(text="正在加载项目...")
        
        # Clear UI components
        self.tree_proj.delete(*self.tree_proj.get_children())
        self.tree_search.delete(*self.tree_search.get_children())
        
        self.current_dir = pathlib.Path(path_str)
        self.lbl_project.config(text=f"📂 {path_str}")
        self.current_proj_config = self.data_mgr.get_project_data(path_str)
        
        # Restore UI Settings from Config
        ss = self.current_proj_config.get("search_settings", {})
        self.search_mode_var.set(ss.get("mode", "smart"))
        self.case_sensitive_var.set(ss.get("case_sensitive", False))
        self.is_inverse_var.set(ss.get("inverse", False))
        self.search_include_dirs_var.set(ss.get("include_dirs", False))
        self.exclude_var.set(self.current_proj_config.get("excludes", ""))
        self._update_pin_button()
        
        # Track history
        self.data_mgr.add_to_recent(path_str)
        self._update_history_menus()

        # Load dynamic components
        self.refresh_fav_tree()
        self.refresh_tools_ui()
        self.refresh_staging_ui()
        self.refresh_template_combo()
        self._refresh_tree()
        self.update_stats()
        self.trigger_search()
        
        self.lbl_status.config(text=f"已就绪: {self.current_dir.name}")

    def on_stage_all(self):
        if not self.current_dir: return
        
        # Simple Dialog to choose mode
        mode = messagebox.askquestion("选择添加模式", 
                                      "是否递归添加项目下所有非忽略文件？\n\n[Yes] 递归添加所有文件\n[No] 仅添加顶级文件夹", 
                                      icon='question')
        
        stage_mode = "files" if mode == 'yes' else "top_folders"
        manual_excludes = self.exclude_var.get().split()
        
        try:
            items = FileUtils.get_project_items(str(self.current_dir), manual_excludes, use_gitignore=self.use_gitignore_var.get(), mode=stage_mode)
            added = self.data_mgr.batch_stage(str(self.current_dir), items)
            self.show_status(f"已成功添加 {added} 个项目到清单")
            self.load_project(str(self.current_dir)) # Refresh UI
        except Exception as e:
            messagebox.showerror("错误", f"全选添加失败: {e}")

    def refresh_tools_ui(self):
        for w in self.cat_btn_frame.winfo_children(): w.destroy()
        for w in self.tool_btn_frame.winfo_children(): w.destroy()
        
        cats = self.current_proj_config.get("quick_categories", {})
        for name in cats:
            ttk.Button(self.cat_btn_frame, text=name, width=10, 
                       command=lambda n=name: self.on_categorize_staged(n)).pack(side=tk.LEFT, padx=2)
        
        tools = self.current_proj_config.get("custom_tools", {})
        for name in tools:
            ttk.Button(self.tool_btn_frame, text=name, width=10, 
                       command=lambda n=name: self.on_execute_tool_staged(n)).pack(side=tk.LEFT, padx=2)

    def refresh_template_combo(self):
        templates = self.current_proj_config.get("prompt_templates", {})
        vals = ["None"] + list(templates.keys())
        self.combo_templates['values'] = vals
        if self.selected_template_var.get() not in vals:
            self.selected_template_var.set("None")

    def on_categorize_staged(self, cat_name):
        if not self.staging_files: return
        try:
            moved = FileOps.batch_categorize(str(self.current_dir), self.staging_files, cat_name)
            self.show_status(f"已将 {len(moved)} 个文件移动至 {cat_name}")
            self.clear_staging()
            self.on_refresh()
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def on_execute_tool_staged(self, tool_name):
        if not self.staging_files:
            messagebox.showwarning("提示", "执行工具前，请先添加文件到清单。")
            return
        
        template = self.current_proj_config.get("custom_tools", {}).get(tool_name)
        if not template: return
        
        self.tools_scroll.config(state=tk.NORMAL)
        self.tools_scroll.insert(tk.END, f"\n> 执行: {tool_name}\n", 'cyan')
        for p_str in self.staging_files:
            file_name = pathlib.Path(p_str).name
            res = ActionBridge.execute_tool(template, p_str, self.current_dir)
            if "error" in res:
                self.tools_scroll.insert(tk.END, f"FAIL: {file_name} - {res['error']}\n", 'red')
            else:
                tag = 'green' if res['exit_code'] == 0 else 'red'
                self.tools_scroll.insert(tk.END, f"DONE: {file_name} (Exit: {res['exit_code']})\n", tag)
                if res['stdout']:
                    out_text = res['stdout'][:200]
                    self.tools_scroll.insert(tk.END, f"  └ {out_text.strip()}\n", 'yellow')
        
        self.tools_scroll.config(state=tk.DISABLED)
        self.tools_scroll.see(tk.END)

    def _refresh_tree(self):
        for item in self.tree_proj.get_children(): self.tree_proj.delete(item)
        root_node = self.tree_proj.insert("", "end", text=f"📁 {self.current_dir.name}", open=True)
        self.populate_tree(root_node, self.current_dir)

    def update_stats(self):
        """Recursively calculate staging stats in a background thread with debouncing."""
        if not self.current_dir:
            return
        
        if hasattr(self, '_stats_timer') and self._stats_timer:
            self.root.after_cancel(self._stats_timer)
        
        self.lbl_stats.config(text="清单: 正在计算...")
        self._stats_timer = self.root.after(300, self._run_stats_calc_thread)

    def _run_stats_calc_thread(self):
        def run_calc():
            try:
                ex_str = self.exclude_var.get()
                use_git = self.use_gitignore_var.get()
                manual_excludes = [e.lower().strip() for e in ex_str.split() if e.strip()]
                
                all_files = FileUtils.flatten_paths(self.staging_files, str(self.current_dir), 
                                                manual_excludes, use_git)
                
                count = len(all_files)
                total_tokens = 0
                for f_str in all_files:
                    p = pathlib.Path(f_str)
                    if p.is_file() and not FileUtils.is_binary(p):
                        try:
                            content = FileUtils.read_text_smart(p)
                            total_tokens += FormatUtils.estimate_tokens(content)
                        except Exception:
                            pass
                
                item_count = len(self.staging_files)
                self.root.after(0, lambda: self._update_stats_ui(item_count, count, total_tokens))
            except Exception as e:
                logger.error(f"Stats calculation failed: {e}")

    def _update_stats_ui(self, item_count, file_count, token_count):
        try:
            threshold = self.current_proj_config.get("token_threshold", 100000)
            color = "#ef4444" if token_count > threshold else "#555"
            self.lbl_stats.config(text=f"清单: {item_count} 项 ({file_count} 文件) | 估算 {FormatUtils.format_number(token_count)} Tokens", foreground=color)
        except Exception as e:
            logger.error(f"UI Stats update error: {e}")

    def add_search_tag(self, *args):
        txt = self.search_var.get().strip()
        if not txt:
            self.trigger_search() # Double enter = search
            return
            
        if txt.startswith('-') and len(txt) > 1:
            val = txt[1:].strip()
            if val and val not in self.negative_tags:
                self.negative_tags.append(val)
        elif txt.startswith('/') and txt.endswith('/') and len(txt) > 2:
            # Sub-regex tag (internal treat as positive for now)
            if txt not in self.positive_tags:
                self.positive_tags.append(txt)
        else:
            if txt not in self.positive_tags:
                self.positive_tags.append(txt)
        
        self.search_var.set("")
        self.render_tags()
        self.trigger_search()

    def remove_search_tag(self, tag, is_positive=True):
        if is_positive:
            if tag in self.positive_tags: self.positive_tags.remove(tag)
        else:
            if tag in self.negative_tags: self.negative_tags.remove(tag)
        self.render_tags()
        self.trigger_search()

    def render_tags(self):
        for w in self.tag_bar.winfo_children(): w.destroy()
        
        if not self.positive_tags and not self.negative_tags:
            return

        btn_clear = tk.Button(self.tag_bar, text="🗑️ 清空标签", bg="#f9fafb", bd=0, 
                             font=("Segoe UI", 8, "italic"), fg="gray", 
                             command=self.clear_all_tags)
        btn_clear.pack(side=tk.RIGHT, padx=5)

        # Positive Tags (Greenish)
        for t in self.positive_tags:
            f = tk.Frame(self.tag_bar, bg="#dcfce7", padx=2, pady=1)
            f.pack(side=tk.LEFT, padx=2, pady=2)
            tk.Label(f, text=t, bg="#dcfce7", font=("Segoe UI", 8)).pack(side=tk.LEFT)
            tk.Button(f, text="×", bg="#dcfce7", bd=0, font=("Segoe UI", 8, "bold"), 
                      command=lambda tag=t: self.remove_search_tag(tag, True)).pack(side=tk.LEFT)
        
        # Negative Tags (Reddish)
        for t in self.negative_tags:
            f = tk.Frame(self.tag_bar, bg="#fee2e2", padx=2, pady=1)
            f.pack(side=tk.LEFT, padx=2, pady=2)
            tk.Label(f, text=f"-{t}", bg="#fee2e2", font=("Segoe UI", 8)).pack(side=tk.LEFT)
            tk.Button(f, text="×", bg="#fee2e2", bd=0, font=("Segoe UI", 8, "bold"), 
                      command=lambda tag=t: self.remove_search_tag(tag, False)).pack(side=tk.LEFT)

    def clear_all_tags(self):
        self.positive_tags.clear()
        self.negative_tags.clear()
        self.render_tags()
        self.trigger_search()

    def trigger_search(self):
        self._perform_search()

    def _perform_search(self):
        self._search_timer = None
        if not self.current_dir:
            return
        if self.search_thread and self.search_thread.is_alive():
            self.stop_event.set()
        for item in self.tree_search.get_children():
            self.tree_search.delete(item)
        self.stop_event = threading.Event()
        self.result_queue = queue.Queue()
        self.lbl_status.config(text="扫描中...")
        max_size = self.current_proj_config.get("max_search_size_mb", 5) if self.current_proj_config else 5
        self.search_thread = SearchWorker(self.current_dir, self.search_var.get(), self.search_mode_var.get(), 
                                         self.exclude_var.get(), self.search_include_dirs_var.get(), 
                                         self.result_queue, self.stop_event, self.use_gitignore_var.get(),
                                         is_inverse=self.is_inverse_var.get(), case_sensitive=self.case_sensitive_var.get(),
                                         max_size_mb=max_size,
                                         positive_tags=list(self.positive_tags),
                                         negative_tags=list(self.negative_tags))
        self.search_thread.start()
        self.process_queue() # Trigger queue processing

    def process_queue(self):
        try:
            processed_in_this_tick = 0
            while processed_in_this_tick < 100:  # Batch limit: process max 100 items per 100ms
                res = self.result_queue.get_nowait()
                if isinstance(res, tuple) and res[0] == "DONE":
                    self.lbl_status.config(text=f"就绪 ({len(self.tree_search.get_children())}项)")
                    return # Stop polling cycle
                
                try:
                    path_str = res["path"]
                    p = pathlib.Path(path_str)
                    rel = p.relative_to(self.current_dir) if self.current_dir in p.parents else p.name

                    sz_str = FormatUtils.format_size(res['size'])
                    dt = FormatUtils.format_datetime(res['mtime'])

                    self.tree_search.insert("", "end", values=(
                        ("📁 " if p.is_dir() else "📄 ") + p.name,
                        str(rel),
                        sz_str,
                        dt,
                        res["ext"]
                    ))
                except Exception as e:
                    logger.error(f"Error processing search result: {e}")
                processed_in_this_tick += 1            
            # Re-register if not done and queue not explicitly stalled (optional safety)
            self.root.after(SEARCH_POLL_MS, self.process_queue)
        except queue.Empty: 
            # If search is still running, keep polling
            if self.search_thread and self.search_thread.is_alive():
                self.root.after(SEARCH_POLL_MS, self.process_queue)

    def sort_tree_column(self, tree, col, reverse):
        l = [(tree.set(k, col), k) for k in tree.get_children('')]
        
        # Numeric sort for size if possible
        if col == "size":
            def parse_sz(s):
                try:
                    parts = s.split()
                    if not parts: return 0
                    num = float(parts[0])
                    unit = parts[1].upper() if len(parts) > 1 else ""
                    if "GB" in unit: return num * 1024 * 1024 * 1024
                    if "MB" in unit: return num * 1024 * 1024
                    if "KB" in unit: return num * 1024
                    return num # Default to Bytes
                except Exception: return 0
            l.sort(key=lambda t: parse_sz(t[0]), reverse=reverse)
        else:
            l.sort(reverse=reverse)
            
        for index, (val, k) in enumerate(l):
            tree.move(k, '', index)
            
        tree.heading(col, command=lambda: self.sort_tree_column(tree, col, not reverse))

    def on_tree_select_preview(self, event):
        tree = event.widget; sel = tree.selection()
        if not sel: return
        full_path = None
        if tree == self.tree_search: full_path = self.current_dir / tree.item(sel[0])['values'][1]
        elif tree == self.tree_proj: full_path = self.get_tree_path(sel[0])
        elif tree == self.tree_staging: full_path = pathlib.Path(tree.item(sel[0])['values'][0])
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
                    # CR-14 Fix: Use read_text_smart for consistent encoding detection
                    content = FileUtils.read_text_smart(full_path, max_bytes=PREVIEW_LIMIT)
                    self.preview_text.insert(tk.END, content)
                    # CR-C08 Fix: Re-enable edit button for text files
                    self.btn_edit_save.config(state=tk.NORMAL)
                except Exception as e:
                    self.preview_text.insert(tk.END, f"--- Error reading file: {e} ---")
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
            
            with os.scandir(path) as it:
                for entry in sorted(it, key=lambda e: (not e.is_dir(), e.name.lower())):
                    # Update: pass git_spec
                    rel_path = pathlib.Path(entry.path).relative_to(self.current_dir)
                    if FileUtils.should_ignore(entry.name, rel_path, ex, git_spec): continue
                    
                    node = self.tree_proj.insert(parent_node, "end", text=("📁 " if entry.is_dir() else "📄 ") + entry.name, open=False)
                    if entry.is_dir(): self.tree_proj.insert(node, "end", text="加载中...")
        except Exception: pass

    def copy_project_tree(self):
        tree_text = FileUtils.generate_ascii_tree(self.current_dir, self.exclude_var.get(), self.use_gitignore_var.get())
        self.root.clipboard_clear(); self.root.clipboard_append(tree_text); self.show_status("结构已复制")

    def refresh_staging_ui(self, apply_filter=False):
        # We don't clear self.staging_files here, only the UI
        for i in self.tree_staging.get_children(): self.tree_staging.delete(i)
        
        if self.current_proj_config:
            # Data Isolation: pass a COPY of the config list to the UI 
            staging_data = list(self.current_proj_config.get("staging_list", []))
            filter_text = self.staging_filter_var.get().lower() if apply_filter else ""
            
            # Reset UI cache if not filtering
            if not apply_filter: self.staging_files.clear()

            for p_raw in staging_data:
                p_str = PathValidator.norm_path(p_raw)
                p = pathlib.Path(p_str)
                
                if apply_filter and filter_text:
                    if filter_text not in p.name.lower() and filter_text not in p_str.lower():
                        continue
                
                if not p.exists(): continue
                
                if p_str not in self.staging_files:
                    self.staging_files.append(p_str)
                
                sz = p.stat().st_size if p.is_file() else 0
                sz_str = FormatUtils.format_size(sz)
                self.tree_staging.insert("", "end", text=("📁 " if p.is_dir() else "📄 ") + p.name, values=(p_str, sz_str))
        
        self.update_stats()

    def remove_filtered_from_staging(self):
        filter_text = self.staging_filter_var.get().lower()
        if not filter_text: return
        
        to_remove = []
        for p_str in self.staging_files:
            p = pathlib.Path(p_str)
            if filter_text in p.name.lower() or filter_text in p_str.lower():
                to_remove.append(p_str)
        
        if to_remove:
            for p in to_remove:
                if p in self.staging_files: self.staging_files.remove(p)
            
            if self.current_proj_config:
                self.current_proj_config["staging_list"] = list(self.staging_files)
                self.data_mgr.save()
            
            self.show_status(f"已从清单移除 {len(to_remove)} 个匹配项")
            self.refresh_staging_ui(apply_filter=True)

    def _add_paths_to_staging(self, paths, save_to_disk=True):
        for p_raw in paths:
            # Sync: always normalize to match DataManager's internal key format
            p_str = PathValidator.norm_path(p_raw)
            if p_str not in self.staging_files:
                p = pathlib.Path(p_str)
                # Note: Windows is case-insensitive, so norm_path's lowercase 
                # will not prevent exists() from working.
                if not p.exists():
                    logger.warning(f"Staging Skip: Path does not exist on disk: '{p_str}'")
                    continue
                
                self.staging_files.append(p_str)
                sz = p.stat().st_size if p.is_file() else 0
                sz_str = FormatUtils.format_size(sz)
                self.tree_staging.insert("", "end", text=("📁 " if p.is_dir() else "📄 ") + p.name, values=(p_str, sz_str))
        
        if save_to_disk and self.current_proj_config:
            # Data Isolation: store a COPY to prevent back-pollution
            self.current_proj_config["staging_list"] = list(self.staging_files)
            self.data_mgr.save()
            
        self.update_stats()

    def add_selected_to_staging(self):
        self._add_paths_to_staging([str(self.current_dir / self.tree_search.item(i)['values'][1]) for i in self.tree_search.selection()])

    def on_tree_double_click(self, event):
        sel = self.tree_proj.selection()
        if not sel: return
        p = self.get_tree_path(sel[0])
        if p: self._add_paths_to_staging([str(p)])

    def clear_staging(self):
        self.staging_files.clear()
        for i in self.tree_staging.get_children(): self.tree_staging.delete(i)
        if self.current_proj_config:
            # Data Isolation
            self.current_proj_config["staging_list"] = []
            self.data_mgr.save()
        self.update_stats()

    def remove_staging_selection(self):
        for i in self.tree_staging.selection():
            val = self.tree_staging.item(i)['values'][0]
            if val in self.staging_files: self.staging_files.remove(val)
            self.tree_staging.delete(i)
        
        if self.current_proj_config:
            # Data Isolation: store a COPY
            self.current_proj_config["staging_list"] = list(self.staging_files)
            self.data_mgr.save()
        self.update_stats()

    def copy_all_staging_content(self):
        prefix = None
        tpl_name = self.selected_template_var.get()
        if tpl_name != "None" and self.current_proj_config:
            prefix = self.current_proj_config.get("prompt_templates", {}).get(tpl_name)
        
        # Pass filters for recursive expansion and de-duplication
        ex_str = self.exclude_var.get()
        use_git = self.use_gitignore_var.get()
        manual_excludes = [e.lower().strip() for e in ex_str.split() if e.strip()]
            
        final_text = ContextFormatter.to_markdown(self.staging_files, self.current_dir, 
                                                 prompt_prefix=prefix,
                                                 manual_excludes=manual_excludes,
                                                 use_gitignore=use_git)
        if final_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(final_text)
            self.show_status("内容已复制")

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
                self.show_status("文件保存成功")
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
        paths = []
        for sel_id in self.active_tree.selection():
            try:
                if self.active_tree == self.tree_proj: 
                    p = self.get_tree_path(sel_id)
                else:
                    val = self.active_tree.item(sel_id)['values']
                    p_str = val[0]
                    if self.active_tree == self.tree_search: p_str = str(self.current_dir / val[1])
                    p = pathlib.Path(p_str)
                if p: paths.append(p)
            except Exception:
                continue
        return paths

    def ctx_open_location(self):
        paths = self._get_ctx_paths()
        if paths: 
            p = paths[0]
            FileUtils.open_path_in_os(p.parent if p.is_file() else p)
        
    def ctx_open_file(self):
        paths = self._get_ctx_paths()
        for p in paths:
            if p.is_file(): FileUtils.open_path_in_os(p)

    def ctx_copy_file_to_os(self):
        paths = self._get_ctx_paths()
        if not paths: return
        
        try:
            if sys.platform == 'win32':
                # Secure execution: Use list arguments to avoid shell injection
                cmd = ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Path $args"]
                subprocess.run(cmd + [str(p) for p in paths], check=True)
            elif sys.platform == 'darwin':
                # macOS: Copying files to clipboard requires AppleScript
                path_list = ",".join([f'POSIX file "{str(p)}"' for p in paths])
                script = f'tell app "Finder" to set the clipboard to {{{path_list}}}'
                subprocess.run(["osascript", "-e", script], check=True)
            else:
                # Linux: Often requires xclip or wl-copy, but file copying is non-standard
                # Fallback to copy paths
                path_str = "\\n".join([str(p) for p in paths])
                self.root.clipboard_clear()
                self.root.clipboard_append(path_str)
                messagebox.showinfo("提示", "Linux 下已将文件路径复制到剪切板。")
                return

            self.lbl_status.config(text=f"已将 {len(paths)} 个项目复制到系统剪切板")
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {e}")

    def ctx_collect_paths(self):
        paths = self._get_ctx_paths()
        if not paths: return
        self._show_path_collection_dialog(paths)

    def on_copy_staged_paths(self):
        # Get all paths in staging
        paths = []
        for item in self.tree_staging.get_children():
            p_str = self.tree_staging.set(item, "path")
            paths.append(pathlib.Path(p_str))
        if not paths: return
        self._show_path_collection_dialog(paths)

    def _show_path_collection_dialog(self, paths):
        dialog = tk.Toplevel(self.root)
        dialog.title("路径搜集与格式化")
        dialog.geometry("380x420")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        main_f = ttk.Frame(dialog, padding=15); main_f.pack(fill=tk.BOTH, expand=True)
        
        # Mode
        mode_var = tk.StringVar(value="relative")
        ttk.Label(main_f, text="路径模式:", font=("Bold", 9)).pack(anchor=tk.W)
        ttk.Radiobutton(main_f, text="项目相对路径 (Relative)", variable=mode_var, value="relative").pack(anchor=tk.W, padx=10)
        ttk.Radiobutton(main_f, text="系统绝对路径 (Absolute)", variable=mode_var, value="absolute").pack(anchor=tk.W, padx=10)
        
        ttk.Separator(main_f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        
        # Presets
        p_f = ttk.Frame(main_f)
        p_f.pack(fill=tk.X, pady=5)
        ttk.Label(p_f, text="快速预设:").pack(side=tk.LEFT)
        profiles = self.current_proj_config.get("collection_profiles", {})
        profile_names = list(profiles.keys())
        preset_combo = ttk.Combobox(p_f, values=profile_names, state="readonly")
        preset_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Prefixes & Suffixes
        sym_f = ttk.Frame(main_f)
        sym_f.pack(fill=tk.X, pady=5)
        
        ttk.Label(sym_f, text="文件前缀 (Prefix):").grid(row=0, column=0, sticky=tk.W)
        file_prefix_var = tk.StringVar(value="")
        file_prefix_entry = ttk.Entry(sym_f, textvariable=file_prefix_var, width=15)
        file_prefix_entry.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(sym_f, text="目录后缀 (Suffix):").grid(row=1, column=0, sticky=tk.W)
        dir_suffix_var = tk.StringVar(value="/")
        dir_suffix_entry = ttk.Entry(sym_f, textvariable=dir_suffix_var, width=15)
        dir_suffix_entry.grid(row=1, column=1, padx=5, pady=2)

        ttk.Separator(main_f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        
        # Separator
        sep_var = tk.StringVar(value="\\n")
        ttk.Label(main_f, text="自定义分隔符:", font=("Bold", 9)).pack(anchor=tk.W)
        
        presets = ttk.Frame(main_f)
        presets.pack(fill=tk.X, pady=5)
        ttk.Button(presets, text="换行(\\n)", width=8, command=lambda: sep_var.set("\\n")).pack(side=tk.LEFT, padx=2)
        ttk.Button(presets, text="空格", width=8, command=lambda: sep_var.set(" ")).pack(side=tk.LEFT, padx=2)
        
        entry_sep = ttk.Entry(main_f, textvariable=sep_var)
        entry_sep.pack(fill=tk.X, pady=5)

        def on_preset_select(e):
            p_name = preset_combo.get()
            prof = profiles.get(p_name)
            if prof:
                file_prefix_var.set(prof.get("prefix", ""))
                dir_suffix_var.set(prof.get("suffix", ""))
                sep_var.set(prof.get("sep", "\\n"))
        
        preset_combo.bind("<<ComboboxSelected>>", on_preset_select)
        if profile_names:
            preset_combo.set(profile_names[0])
            on_preset_select(None)
        
        def do_copy():
            mode = mode_var.get()
            sep = sep_var.get()
            f_pref = file_prefix_var.get()
            d_suff = dir_suffix_var.get()
            formatted = FormatUtils.collect_paths([str(p) for p in paths], str(self.current_dir), mode, sep, f_pref, d_suff)
            self.root.clipboard_clear()
            self.root.clipboard_append(formatted)
            self.lbl_status.config(text=f"已成功搜集 {len(paths)} 条路径")
            dialog.destroy()
            
        ttk.Button(main_f, text="✅ 确定并复制到剪切板", command=do_copy).pack(fill=tk.X, pady=10)

    def ctx_copy_path_to_clipboard(self):
        paths = self._get_ctx_paths()
        if not paths: return
        path_str = "\n".join([str(p) for p in paths])
        self.root.clipboard_clear()
        self.root.clipboard_append(path_str)
        self.lbl_status.config(text=f"已复制 {len(paths)} 个路径到剪切板")

    def ctx_rename_file(self):
        paths = self._get_ctx_paths()
        if not paths: return
        if len(paths) > 1:
            # Multi-file rename: Open the Batch Rename dialog
            BatchRenameWindow(self.root, self.current_dir, paths, callback=lambda: self.load_project(str(self.current_dir)))
            return
        
        # Single-file rename: Use simple prompt
        p = paths[0]
        new_name = simpledialog.askstring("📝 重命名", "输入新文件名:", initialvalue=p.name)
        if new_name and new_name != p.name:
            try:
                FileOps.rename_file(str(p), new_name)
                self.load_project(str(self.current_dir))
            except Exception as e: 
                messagebox.showerror("错误", str(e))

    def ctx_delete_file(self):
        paths = self._get_ctx_paths()
        if not paths: return
        msg = f"确定要永久删除这 {len(paths)} 个项目吗？" if len(paths) > 1 else f"确定要永久删除:\n{paths[0].name} ?"
        if messagebox.askyesno("确认批量删除", msg):
            try:
                for p in paths:
                    # CR-09 Fix: Security validation
                    if not PathValidator.is_safe(str(p), str(self.current_dir)):
                        logger.warning(f"Blocking unsafe desktop delete: {p}")
                        continue
                    FileOps.delete_file(str(p))
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
                    # CR-09 Fix: Security validation for src and dst
                    if not PathValidator.is_safe(str(p), str(self.current_dir)):
                        continue
                    if not PathValidator.is_safe(dst_dir, str(self.current_dir)):
                        messagebox.showerror("错误", "目标路径不在项目根目录下，禁止跨项目移动。")
                        return
                    
                    if str(p.parent) != dst_dir: FileOps.move_file(str(p), dst_dir)
                self.load_project(str(self.current_dir))
            except Exception as e: messagebox.showerror("错误", f"移动中断: {str(e)}")

    def ctx_add_to_favorites(self):
        paths = self._get_ctx_paths()
        if not paths: return
        group = self.current_group_var.get()
        self.data_mgr.add_to_group(str(self.current_dir), group, [str(p) for p in paths])
        self.refresh_fav_tree()
        self.lbl_status.config(text=f"已将 {len(paths)} 个项目添加至收藏组: {group}")

    def _init_menu(self):
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)
        
        file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="文件 (File)", menu=file_menu)
        file_menu.add_command(label="📁 浏览工作区...", command=self.on_browse)
        
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="最近打开", menu=self.recent_menu)
        
        self.pinned_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="置顶工作区", menu=self.pinned_menu)
        
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        self._update_history_menus()

    def _update_history_menus(self):
        try:
            self.recent_menu.delete(0, tk.END)
            self.pinned_menu.delete(0, tk.END)
            summary = self.data_mgr.get_workspaces_summary()
            
            for item in summary["recent"]:
                self.recent_menu.add_command(label=item["name"], command=lambda p=item["path"]: self.on_browse(p))
                
            for item in summary["pinned"]:
                self.pinned_menu.add_command(label=item["name"], command=lambda p=item["path"]: self.on_browse(p))
        except Exception: pass

    def on_toggle_pin(self):
        if not self.current_dir: return
        is_pinned = self.data_mgr.toggle_pinned(str(self.current_dir))
        self._update_pin_button()
        self._update_history_menus()
        self.lbl_status.config(text="已置顶工作区" if is_pinned else "已取消置顶工作区")

    def _update_pin_button(self):
        if not self.current_dir:
            self.btn_pin.config(text="☆")
            return
        is_pinned = str(self.current_dir) in self.data_mgr.data.get("pinned_projects", [])
        self.btn_pin.config(text="⭐" if is_pinned else "☆")

    def open_duplicate_finder(self):
        from file_cortex_core import DuplicateWorker
        if not self.current_dir:
            messagebox.showwarning("提示", "请先打开一个项目目录。")
            return
        DuplicateFinderWindow(self.root, self.data_mgr, self.current_dir, 
                              self.exclude_var.get(), self.use_gitignore_var.get())

    def open_batch_io_dialog(self): pass 

class BatchRenameWindow(tk.Toplevel):
    """
    GUI for bulk renaming files using regex or simple replacement.
    """
    def __init__(self, parent, project_root, selected_paths, callback=None):
        super().__init__(parent)
        self.project_root = project_root
        self.selected_paths = selected_paths
        self.callback = callback
        
        self.title(f"📝 批量重命名 | 选中 {len(selected_paths)} 个项目")
        self.geometry("900x600")
        self.transient(parent)
        self.grab_set()

        self.pattern_var = tk.StringVar()
        self.replacement_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="regex") # or "simple"
        
        self._init_ui()
        self.update_preview()

    def _init_ui(self):
        main_f = ttk.Frame(self, padding=12)
        main_f.pack(fill=tk.BOTH, expand=True)

        # Config Area
        ctrl_f = ttk.LabelFrame(main_f, text="🔧 重命名规则", padding=10)
        ctrl_f.pack(fill=tk.X, pady=(0, 10))

        # First row: Regex vs Simple
        top_row = ttk.Frame(ctrl_f)
        top_row.pack(fill=tk.X, pady=2)
        ttk.Label(top_row, text="模式:", font=("Bold", 9)).pack(side=tk.LEFT)
        ttk.Radiobutton(top_row, text="正则表达式 (Regex)", variable=self.mode_var, value="regex", command=self.update_preview).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(top_row, text="普通替换 (Simple Replace)", variable=self.mode_var, value="simple", command=self.update_preview).pack(side=tk.LEFT, padx=10)

        # Second row: From/To
        grid_f = ttk.Frame(ctrl_f)
        grid_f.pack(fill=tk.X, pady=5)
        
        ttk.Label(grid_f, text="查找:").grid(row=0, column=0, sticky=tk.W, padx=2)
        self.entry_pattern = ttk.Entry(grid_f, textvariable=self.pattern_var)
        self.entry_pattern.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)
        self.pattern_var.trace_add("write", lambda *a: self.update_preview())

        ttk.Label(grid_f, text="替换为:").grid(row=1, column=0, sticky=tk.W, padx=2)
        self.entry_repl = ttk.Entry(grid_f, textvariable=self.replacement_var)
        self.entry_repl.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=2)
        self.replacement_var.trace_add("write", lambda *a: self.update_preview())
        
        grid_f.columnconfigure(1, weight=1)

        # Preview Area
        preview_f = ttk.LabelFrame(main_f, text="👁️ 效果预览", padding=5)
        preview_f.pack(fill=tk.BOTH, expand=True)

        tree_container = ttk.Frame(preview_f)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_container, columns=("old", "new", "status"), show="headings")
        self.tree.heading("old", text="原名称")
        self.tree.heading("new", text="新名称预览")
        self.tree.heading("status", text="状态/冲突")
        self.tree.column("old", width=250)
        self.tree.column("new", width=250)
        self.tree.column("status", width=120)
        
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom Buttons
        btn_f = ttk.Frame(main_f, padding=5)
        btn_f.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_f, text="🚩 立即应用变更", command=self.execute_rename, style="Accent.TButton").pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_f, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def update_preview(self):
        pattern = self.pattern_var.get()
        replacement = self.replacement_var.get()
        mode = self.mode_var.get()
        
        # Clear
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if not pattern:
            for p in self.selected_paths:
                self.tree.insert("", "end", values=(p.name, p.name, "无变化"))
            return

        try:
            # Prepare regex if simple mode
            final_pattern = pattern
            if mode == "simple":
                final_pattern = re.escape(pattern)
            
            results = FileOps.batch_rename(str(self.project_root), [str(p) for p in self.selected_paths], 
                                          final_pattern, replacement, dry_run=True)
            
            # Map back to original list for those not changed
            changed_map = {item["old"]: item for item in results}
            
            for p in self.selected_paths:
                p_str = str(p)
                if p_str in changed_map:
                    item = changed_map[p_str]
                    self.tree.insert("", "end", values=(p.name, pathlib.Path(item["new"]).name, item["status"]))
                else:
                    self.tree.insert("", "end", values=(p.name, p.name, "无匹配"))
                    
        except Exception as e:
            self.tree.insert("", "end", values=("错误", "---", str(e)))

    def execute_rename(self):
        pattern = self.pattern_var.get()
        replacement = self.replacement_var.get()
        mode = self.mode_var.get()
        
        if not pattern: return
        
        msg = f"确定要重命名这 {len(self.selected_paths)} 个项目吗？\n该操作不可撤销。"
        if not messagebox.askyesno("确认批量重命名", msg): return
        
        try:
            final_pattern = pattern
            if mode == "simple":
                final_pattern = re.escape(pattern)
                
            FileOps.batch_rename(str(self.project_root), [str(p) for p in self.selected_paths], 
                                final_pattern, replacement, dry_run=False)
            
            if self.callback: self.callback()
            messagebox.showinfo("成功", "批量重命名已完成。")
            self.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"重命名失败: {e}")

class DuplicateFinderWindow(tk.Toplevel):
    def __init__(self, parent, data_mgr, current_dir, excludes, use_gitignore):
        super().__init__(parent)
        self.title(f"🕵️ 重复文件查找器 | {current_dir.name}")
        self.geometry("1100x700")
        self.data_mgr = data_mgr
        self.current_dir = current_dir
        self.excludes = excludes
        self.use_gitignore = use_gitignore
        
        self.stop_event = threading.Event()
        self.result_queue = queue.Queue()
        self.duplicate_groups = {} # {hash: [path, ...]}
        
        self._init_ui()
        self.start_scan()
        self.poll_results()

    def _init_ui(self):
        main_f = ttk.Frame(self, padding=10)
        main_f.pack(fill=tk.BOTH, expand=True)

        self.lbl_head = ttk.Label(main_f, text="🔍 正在扫描项目重复文件...", font=("Segoe UI", 12, "bold"))
        self.lbl_head.pack(fill=tk.X, pady=5)
        
        self.tree = ttk.Treeview(main_f, columns=("path", "size"), show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="重复组 / 文件")
        self.tree.heading("path", text="完整路径")
        self.tree.heading("size", text="大小")
        self.tree.column("#0", width=300)
        self.tree.column("path", width=500)
        self.tree.column("size", width=100)
        self.tree.pack(fill=tk.BOTH, expand=True)

        btn_f = ttk.Frame(main_f, padding=10)
        btn_f.pack(fill=tk.X)
        self.btn_delete = ttk.Button(btn_f, text="🗑️ 彻底删除选中文件", command=self.delete_selected, state=tk.DISABLED)
        self.btn_delete.pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_f, text="❌ 停止扫描", command=self.on_close).pack(side=tk.RIGHT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def start_scan(self):
        from file_cortex_core import DuplicateWorker
        self.worker = DuplicateWorker(self.current_dir, self.excludes, self.use_gitignore, self.result_queue, self.stop_event)
        self.worker.start()

    def poll_results(self):
        try:
            while True:
                try:
                    res = self.result_queue.get_nowait()
                    if isinstance(res, tuple):
                        if res[0] == "DONE":
                            self.lbl_head.config(text=f"✅ 扫描完成: 发现 {len(self.duplicate_groups)} 组重复文件")
                            self.btn_delete.config(state=tk.NORMAL)
                        elif res[0] == "ERROR":
                            messagebox.showerror("错误", f"扫描失败: {res[1]}")
                            self.destroy()
                        return
                    
                    h = res["hash"]
                    sz_fmt = FormatUtils.format_size(res["size"])
                    group_id = self.tree.insert("", "end", text=f"📦 Group {h[:8]} ({sz_fmt})", open=True)
                    self.duplicate_groups[h] = res["paths"]
                    
                    for p_str in res["paths"]:
                        p = pathlib.Path(p_str)
                        rel = p.relative_to(self.current_dir) if self.current_dir in p.parents else p.name
                        self.tree.insert(group_id, "end", text=f"📄 {rel}", values=(p_str, sz_fmt))
                except queue.Empty:
                    break
                except Exception as e:
                    logger.error(f"Duplicate result processing error: {e}")
                    continue
        except Exception as e:
            logger.error(f"Poll results loop failure: {e}")
            
        self.after(200, self.poll_results)

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel: return
        
        to_delete = []
        for s in sel:
            vals = self.tree.item(s)["values"]
            if vals and len(vals) > 0:
                to_delete.append(vals[0])
        
        if not to_delete:
            messagebox.showwarning("警告", "请选中特定的重复文件（而非整个分组）。")
            return
            
        if messagebox.askyesno("二次确认", f"确定要永久删除这 {len(to_delete)} 个重复文件吗？\n删除操作不可逆！建议为每组至少留一份原件。"):
            from file_cortex_core import FileOps
            for p_str in to_delete:
                try:
                    FileOps.delete_file(p_str)
                    # We need to find the specific item in the tree to delete it visually
                    for item in self.tree.selection():
                         if self.tree.item(item)["values"] and self.tree.item(item)["values"][0] == p_str:
                             self.tree.delete(item)
                except Exception as e:
                    messagebox.showerror("错误", f"删除 {p_str} 失败: {e}")
            messagebox.showinfo("成功", "所选重复文件已清理完毕。")

    def on_close(self):
        self.stop_event.set()
        self.destroy()

if __name__ == "__main__":
    root = tk.Tk(); app = FileCortexApp(root); root.mainloop()
