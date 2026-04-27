#!/usr/bin/env python3
"""Duplicate finder window for FileCortex GUI.
"""

import pathlib
import queue
import threading
import tkinter as tk
from tkinter import (
    messagebox,
    ttk,
)

from ..config import DataManager, logger
from ..duplicate import DuplicateWorker
from ..file_io import FileUtils
from ..format_utils import FormatUtils


class DuplicateFinderWindow(tk.Toplevel):
    """Window for finding and managing duplicate files."""

    def __init__(
        self,
        parent: tk.Tk,
        data_mgr: DataManager,
        current_dir: pathlib.Path,
        excludes: str,
        use_gitignore: bool,
    ) -> None:
        """Initializes the duplicate finder window.

        Args:
            parent: Parent window.
            data_mgr: Data manager instance.
            current_dir: Current project directory.
            excludes: Exclusion patterns.
            use_gitignore: Whether to respect .gitignore.
        """
        super().__init__(parent)
        self.title(f"查找重复文件 (SHA256) | {current_dir.name}")
        self.geometry("1100x700")
        self.data_mgr = data_mgr
        self.current_dir = current_dir
        self.excludes = excludes
        self.use_gitignore = use_gitignore

        self.stop_event = threading.Event()
        self.result_queue: queue.Queue[dict] = queue.Queue()
        self.duplicate_groups: dict[str, list[str]] = {}

        self._init_ui()
        self.start_scan()
        self.poll_results()

    def _init_ui(self) -> None:
        """Initializes the window UI components."""
        main_f = ttk.Frame(self, padding=10)
        main_f.pack(fill=tk.BOTH, expand=True)

        self.lbl_head = ttk.Label(
            main_f,
            text="正在扫描并对比工作区所有非忽略文件...",
            font=("Segoe UI", 12, "bold"),
        )
        self.lbl_head.pack(fill=tk.X, pady=5)

        self.tree = ttk.Treeview(
            main_f,
            columns=("path", "size", "mtime"),
            show="tree headings",
            selectmode="extended",
        )
        self.tree.heading("#0", text="重复组 / 文件名")
        self.tree.heading("path", text="物理路径")
        self.tree.heading("size", text="大小")
        self.tree.heading("mtime", text="修改时间")
        self.tree.column("#0", width=250)
        self.tree.column("path", width=450)
        self.tree.column("size", width=80)
        self.tree.column("mtime", width=120)
        self.tree.pack(fill=tk.BOTH, expand=True)

        btn_f = ttk.Frame(main_f, padding=10)
        btn_f.pack(fill=tk.X)

        self.btn_smart = ttk.Menubutton(btn_f, text="✨ 智能全选...")
        self.smart_menu = tk.Menu(self.btn_smart, tearoff=0)
        self.smart_menu.add_command(
            label="保留最早 (推荐)", command=lambda: self.smart_select("oldest")
        )
        self.smart_menu.add_command(
            label="保留最晚", command=lambda: self.smart_select("newest")
        )
        self.smart_menu.add_separator()
        self.smart_menu.add_command(label="取消全选", command=lambda: self.tree.selection_set())
        self.btn_smart.config(menu=self.smart_menu, state=tk.DISABLED)
        self.btn_smart.pack(side=tk.LEFT, padx=5)

        self.btn_delete = ttk.Button(
            btn_f,
            text="永久删除选中的冗余文件",
            command=self.delete_selected,
            state=tk.DISABLED,
            style="Danger.TButton",
        )
        self.btn_delete.pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_f, text="停止并关闭", command=self.on_close).pack(
            side=tk.RIGHT, padx=5
        )

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def start_scan(self) -> None:
        """Starts the duplicate scan worker thread."""
        self.worker = DuplicateWorker(
            self.current_dir,
            self.excludes,
            self.use_gitignore,
            self.result_queue,
            self.stop_event,
        )
        self.worker.start()

    def poll_results(self) -> None:
        """Polls for duplicate scan results."""
        try:
            while True:
                try:
                    res = self.result_queue.get_nowait()
                    if isinstance(res, tuple):
                        if res[0] == "DONE":
                            self.lbl_head.config(
                                text=f"扫描结束: "
                                f"共发现 {len(self.duplicate_groups)} 组重复内容。"
                            )
                            self.btn_delete.config(state=tk.NORMAL)
                            self.btn_smart.config(state=tk.NORMAL)
                        elif res[0] == "ERROR":
                            messagebox.showerror("错误", f"扫描失败: {res[1]}")
                            self.destroy()
                        return

                    h = res["hash"]
                    sz = res["size"]
                    sz_fmt = FormatUtils.format_size(sz)
                    group_id = self.tree.insert(
                        "",
                        "end",
                        text=f"📁 Group {h[:8]} ({sz_fmt})",
                        open=True,
                    )
                    self.duplicate_groups[h] = res["paths"]

                    for p_str in res["paths"]:
                        p = pathlib.Path(p_str)
                        st = p.stat()
                        mtime = st.st_mtime
                        dt_fmt = FormatUtils.format_datetime(mtime)
                        rel = (
                            p.relative_to(self.current_dir)
                            if self.current_dir in p.parents
                            else p.name
                        )
                        self.tree.insert(
                            group_id,
                            "end",
                            text=f"📄 {rel}",
                            values=(p_str, sz_fmt, dt_fmt, mtime),
                        )
                except queue.Empty:
                    break
                except Exception as e:
                    logger.error(f"Duplicate result processing error: {e}")
                    continue
        except Exception as e:
            logger.error(f"Poll results loop failure: {e}")

        self.after(200, self.poll_results)

    def smart_select(self, mode: str = "oldest") -> None:
        """Automatically selects redundant files based on time.

        Args:
            mode: 'oldest' (keep oldest) or 'newest' (keep newest).
        """
        selection = []
        for group in self.tree.get_children():
            children = self.tree.get_children(group)
            if not children:
                continue

            # Sort children by mtime (stored in values[3])
            items = []
            for child in children:
                vals = self.tree.item(child)["values"]
                items.append((float(vals[3]), child))

            # Sort by time
            items.sort(key=lambda x: x[0])

            if mode == "oldest":
                # Keep items[0], select the rest
                selection.extend([it[1] for it in items[1:]])
            else:
                # Keep items[-1], select the rest
                selection.extend([it[1] for it in items[:-1]])

        self.tree.selection_set(selection)
        if selection:
            self.show_status(f"智能全选：已选中 {len(selection)} 个冗余文件。")

    def show_status(self, msg: str) -> None:
        """Updates the header text."""
        self.lbl_head.config(text=msg)

    def delete_selected(self) -> None:
        """Deletes the selected duplicate files."""
        sel = self.tree.selection()
        if not sel:
            return

        to_delete = []
        for s in sel:
            vals = self.tree.item(s)["values"]
            if vals and len(vals) > 0:
                # Ensure it's a file, not a group header
                if self.tree.parent(s):
                    to_delete.append(vals[0])

        if not to_delete:
            messagebox.showwarning("提示", "请先选中具体的重复文件（非分组标题）后再执行删除。")
            return

        if messagebox.askyesno(
            "确认删除",
            f"确定要永久删除这 {len(to_delete)} 个冗余文件吗？\n"
            "警告：该操作将从磁盘物理移除文件且无法撤销！",
        ):
            from ..actions import FileOps

            deleted_count = 0
            for p_str in to_delete:
                try:
                    FileOps.delete_file(p_str)
                    deleted_count += 1
                    # Find and remove item from tree
                    for group in self.tree.get_children():
                        for child in self.tree.get_children(group):
                            if (
                                self.tree.item(child)["values"]
                                and self.tree.item(child)["values"][0] == p_str
                            ):
                                self.tree.delete(child)
                except Exception as e:
                    messagebox.showerror("错误", f"删除 {p_str} 失败: {e}")

            messagebox.showinfo("成功", f"已清理 {deleted_count} 个冗余文件！")
            self.smart_select("oldest")  # Refresh selection if any groups remain

    def on_close(self) -> None:
        """Handles window close event."""
        self.stop_event.set()
        self.destroy()
