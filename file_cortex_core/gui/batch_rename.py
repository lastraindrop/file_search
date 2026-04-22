#!/usr/bin/env python3
"""Batch rename window for FileCortex GUI.
"""

import pathlib
import re
import tkinter as tk
from tkinter import (
    messagebox,
    ttk,
)

from ..actions import FileOps


class BatchRenameWindow(tk.Toplevel):
    """GUI window for bulk renaming files using regex or simple replacement."""

    def __init__(
        self,
        parent: tk.Tk,
        project_root: pathlib.Path,
        selected_paths: list[pathlib.Path],
        callback=None,
    ) -> None:
        """Initializes the batch rename window.

        Args:
            parent: Parent window.
            project_root: Project root directory.
            selected_paths: List of paths to rename.
            callback: Optional callback function after rename.
        """
        super().__init__(parent)
        self.project_root = project_root
        self.selected_paths = selected_paths
        self.callback = callback

        self.title(f"批量重命名 | 选中 {len(selected_paths)} 个项目")
        self.geometry("900x600")
        self.transient(parent)
        self.grab_set()

        self.pattern_var = tk.StringVar()
        self.replacement_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="regex")

        self._init_ui()
        self.update_preview()

    def _init_ui(self) -> None:
        """Initializes the window UI components."""
        main_f = ttk.Frame(self, padding=12)
        main_f.pack(fill=tk.BOTH, expand=True)

        ctrl_f = ttk.LabelFrame(main_f, text="重命名规则", padding=10)
        ctrl_f.pack(fill=tk.X, pady=(0, 10))

        top_row = ttk.Frame(ctrl_f)
        top_row.pack(fill=tk.X, pady=2)
        ttk.Label(top_row, text="模式:", font=("Bold", 9)).pack(side=tk.LEFT)
        ttk.Radiobutton(
            top_row,
            text="正则表达式 (Regex)",
            variable=self.mode_var,
            value="regex",
            command=self.update_preview,
        ).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(
            top_row,
            text="普通替换 (Simple Replace)",
            variable=self.mode_var,
            value="simple",
            command=self.update_preview,
        ).pack(side=tk.LEFT, padx=10)

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

        preview_f = ttk.LabelFrame(main_f, text="效果预览", padding=5)
        preview_f.pack(fill=tk.BOTH, expand=True)

        tree_container = ttk.Frame(preview_f)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            tree_container,
            columns=("old", "new", "status"),
            show="headings",
        )
        self.tree.heading("old", text="原文件名")
        self.tree.heading("new", text="新文件名")
        self.tree.heading("status", text="状态/预判")
        self.tree.column("old", width=250)
        self.tree.column("new", width=250)
        self.tree.column("status", width=120)

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        btn_f = ttk.Frame(main_f, padding=5)
        btn_f.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(
            btn_f,
            text="执行批量重命名",
            command=self.execute_rename,
            style="Accent.TButton",
        ).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_f, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def update_preview(self) -> None:
        """Updates the rename preview table."""
        pattern = self.pattern_var.get()
        replacement = self.replacement_var.get()
        mode = self.mode_var.get()

        for item in self.tree.get_children():
            self.tree.delete(item)

        if not pattern:
            for p in self.selected_paths:
                self.tree.insert("", "end", values=(p.name, p.name, "无变化"))
            return

        try:
            final_pattern = pattern
            if mode == "simple":
                final_pattern = re.escape(pattern)

            results = FileOps.batch_rename(
                str(self.project_root),
                [str(p) for p in self.selected_paths],
                final_pattern,
                replacement,
                dry_run=True,
            )

            changed_map = {item["old"]: item for item in results}

            for p in self.selected_paths:
                p_str = str(p)
                if p_str in changed_map:
                    item = changed_map[p_str]
                    self.tree.insert(
                        "",
                        "end",
                        values=(
                            p.name,
                            pathlib.Path(item["new"]).name,
                            item["status"],
                        ),
                    )
                else:
                    self.tree.insert("", "end", values=(p.name, p.name, "未匹配"))

        except Exception as e:
            self.tree.insert("", "end", values=("错误", "---", str(e)))

    def execute_rename(self) -> None:
        """Executes the batch rename operation."""
        pattern = self.pattern_var.get()
        replacement = self.replacement_var.get()
        mode = self.mode_var.get()

        if not pattern:
            return

        msg = f"确定要重命名这 {len(self.selected_paths)} 个项目吗？\n该操作不可撤销！"
        if not messagebox.askyesno("确认批量重命名", msg):
            return

        try:
            final_pattern = pattern
            if mode == "simple":
                final_pattern = re.escape(pattern)

            FileOps.batch_rename(
                str(self.project_root),
                [str(p) for p in self.selected_paths],
                final_pattern,
                replacement,
                dry_run=False,
            )

            if self.callback:
                self.callback()
            messagebox.showinfo("成功", "批量重命名任务已完成！")
            self.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"批量重命名失败: {e}")
