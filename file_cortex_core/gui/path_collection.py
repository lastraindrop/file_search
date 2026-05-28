#!/usr/bin/env python3
"""Path collection dialog for FileCortex GUI."""

import pathlib
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any

from ..format_utils import FormatUtils


class PathCollectionDialog(tk.Toplevel):
    """Dialog window for collecting and formatting file paths."""

    def __init__(
        self,
        parent: tk.Tk,
        paths: list[pathlib.Path],
        current_dir: pathlib.Path,
        profiles: dict[str, Any],
        status_callback: Callable[[int], None] | None = None,
    ) -> None:
        """Initializes the path collection dialog.

        Args:
            parent: Parent window.
            paths: List of paths to format.
            current_dir: Current project directory.
            profiles: Collection profile definitions.
            status_callback: Optional callback(key, count) for status updates.
        """
        super().__init__(parent)
        self.paths = paths
        self.current_dir = current_dir
        self.profiles = profiles
        self.status_callback = status_callback
        self.result = ""

        self.title("路径搜集与格式化")
        self.geometry("380x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        x = (
            parent.winfo_x()
            + (parent.winfo_width() // 2)
            - (self.winfo_width() // 2)
        )
        y = (
            parent.winfo_y()
            + (parent.winfo_height() // 2)
            - (self.winfo_height() // 2)
        )
        self.geometry(f"+{x}+{y}")

        self._init_ui()

    def _init_ui(self) -> None:
        """Builds the dialog UI."""
        main_f = ttk.Frame(self, padding=15)
        main_f.pack(fill=tk.BOTH, expand=True)

        self.mode_var = tk.StringVar(value="relative")
        ttk.Label(main_f, text="路径模式:", font=("Bold", 9)).pack(anchor=tk.W)
        ttk.Radiobutton(
            main_f,
            text="项目相对路径 (Relative)",
            variable=self.mode_var,
            value="relative",
        ).pack(anchor=tk.W, padx=10)
        ttk.Radiobutton(
            main_f,
            text="系统绝对路径 (Absolute)",
            variable=self.mode_var,
            value="absolute",
        ).pack(anchor=tk.W, padx=10)

        ttk.Separator(main_f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        p_f = ttk.Frame(main_f)
        p_f.pack(fill=tk.X, pady=5)
        ttk.Label(p_f, text="快速预设:").pack(side=tk.LEFT)
        profile_names = list(self.profiles.keys())
        self.preset_combo = ttk.Combobox(p_f, values=profile_names, state="readonly")
        self.preset_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        sym_f = ttk.Frame(main_f)
        sym_f.pack(fill=tk.X, pady=5)

        ttk.Label(sym_f, text="文件前缀 (Prefix):").grid(row=0, column=0, sticky=tk.W)
        self.file_prefix_var = tk.StringVar(value="")
        file_prefix_entry = ttk.Entry(sym_f, textvariable=self.file_prefix_var, width=15)
        file_prefix_entry.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(sym_f, text="目录后缀 (Suffix):").grid(row=1, column=0, sticky=tk.W)
        self.dir_suffix_var = tk.StringVar(value="/")
        dir_suffix_entry = ttk.Entry(sym_f, textvariable=self.dir_suffix_var, width=15)
        dir_suffix_entry.grid(row=1, column=1, padx=5, pady=2)

        ttk.Separator(main_f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        self.sep_var = tk.StringVar(value="\\n")
        ttk.Label(main_f, text="自定义分隔符:", font=("Bold", 9)).pack(anchor=tk.W)

        presets = ttk.Frame(main_f)
        presets.pack(fill=tk.X, pady=5)
        ttk.Button(
            presets,
            text="换行(\\n)",
            width=8,
            command=lambda: self.sep_var.set("\\n"),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            presets, text="空格", width=8,
            command=lambda: self.sep_var.set(" "),
        ).pack(side=tk.LEFT, padx=2)

        entry_sep = ttk.Entry(main_f, textvariable=self.sep_var)
        entry_sep.pack(fill=tk.X, pady=5)

        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_select)
        if profile_names:
            self.preset_combo.set(profile_names[0])
            self._on_preset_select(None)

        ttk.Button(
            main_f,
            text="确定并复制到剪切板",
            command=self._do_copy_and_close,
        ).pack(fill=tk.X, pady=10)

    def _on_preset_select(self, event: tk.Event | None) -> None:
        """Handles preset profile selection."""
        p_name = self.preset_combo.get()
        prof = self.profiles.get(p_name)
        if prof:
            self.file_prefix_var.set(prof.get("prefix", ""))
            self.dir_suffix_var.set(prof.get("suffix", ""))
            self.sep_var.set(prof.get("sep", "\\n"))

    def _do_copy_and_close(self) -> None:
        """Formats paths and copies to clipboard, then closes."""
        self.result = FormatUtils.collect_paths(
            [str(p) for p in self.paths],
            str(self.current_dir),
            self.mode_var.get(),
            self.sep_var.get(),
            self.file_prefix_var.get(),
            self.dir_suffix_var.get(),
        )
        self.clipboard_clear()
        self.clipboard_append(self.result)
        if self.status_callback:
            self.status_callback(len(self.paths))
        self.destroy()
