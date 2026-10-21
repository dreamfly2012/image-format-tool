"""批量图片格式转换工具 — Tkinter 界面。

核心转换逻辑位于 converter.py，界面层仅负责交互、进度显示与日志输出。
不带参数运行时启动图形界面；带参数时进入 CLI 模式（见 converter.cli）。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.constants import BOTH, LEFT, RIGHT, W

import converter
from converter import ConversionStats, batch_convert, find_image_files

# ---------------------------------------------------------------- 常量

APP_TITLE = "批量图片格式转换工具"
FORMAT_LABELS = ("PNG", "JPEG", "BMP", "GIF", "TIFF", "WEBP")
SCALE_OPTIONS = ("保持原尺寸", "90%", "75%", "50%", "25%")
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".image_format_tool.json")
COLORS = {
    "bg": "#f5f7fa",
    "card": "#ffffff",
    "accent": "#3b82f6",
    "ok": "#16a34a",
    "err": "#dc2626",
}


def load_settings() -> dict:
    """读取上次的设置（输入/输出文件夹、格式、质量、递归、缩放）。"""
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    """记住设置；失败不影响主流程。"""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def parse_scale_option(value) -> int | None:
    """'保持原尺寸' → None；'90%' → 90。"""
    text = str(value).strip()
    if text.endswith("%"):
        try:
            pct = int(text[:-1].strip())
            return pct if 0 < pct < 100 else None
        except ValueError:
            return None
    return None


def human_size(nbytes: int) -> str:
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} GB"


class App:
    """主窗口。将 GUI 事件调度回主线程，避免后台线程直接操作控件。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("700x640")
        self.root.minsize(580, 540)
        self.root.configure(bg=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        settings = load_settings()
        self.input_folder: str = settings.get("input_folder", "")
        self.output_folder: str = settings.get("output_folder", "")
        self.target_format = tk.StringVar(value=settings.get("format", FORMAT_LABELS[0]))
        self.quality = tk.IntVar(value=settings.get("quality", 90))
        self.recursive = tk.BooleanVar(value=settings.get("recursive", True))
        self.scale_option = tk.StringVar(value=settings.get("scale", SCALE_OPTIONS[0]))

        self.cancel_event = threading.Event()
        self._running = False
        self._build_widgets()

        # 恢复上次的文件夹选择（仅当路径仍有效）
        if os.path.isdir(self.input_folder):
            self._show_folder(self.input_var, self.input_folder)
        else:
            self.input_folder = ""
        if os.path.isdir(self.output_folder):
            self._show_folder(self.output_var, self.output_folder)
        else:
            self.output_folder = ""
        self._refresh()

    # ------------------------------------------------------------- UI 构建

    def _build_widgets(self):
        self._configure_style()

        header = tk.Frame(self.root, bg=COLORS["accent"])
        header.pack(fill=BOTH)
        tk.Label(
            header,
            text="📷  批量图片格式转换",
            font=("Microsoft YaHei UI", 16, "bold"),
            bg=COLORS["accent"],
            fg="white",
        ).pack(padx=18, pady=(10, 0), anchor=W)
        tk.Label(
            header,
            text="支持 PNG / JPEG / BMP / GIF / TIFF / WEBP · 自动修正 EXIF 方向 · 可递归子目录",
            font=("Microsoft YaHei UI", 9),
            bg=COLORS["accent"],
            fg="#dbeafe",
        ).pack(padx=18, pady=(0, 10), anchor=W)

        body = tk.Frame(self.root, bg=COLORS["bg"])
        body.pack(fill=BOTH, expand=True, padx=14, pady=12)

        self._build_folder_section(body)
        self._build_format_section(body)
        self._build_actions(body)
        self._build_progress(body)
        self._build_log(body)

    def _configure_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor="#e5e7eb",
            background=COLORS["accent"],
            thickness=14,
        )
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(14, 7))
        style.map("TButton", background=[("active", "#eef2ff")])

    def _section(self, parent, title):
        frame = tk.Frame(parent, bg=COLORS["card"])
        tk.Label(
            frame, text=title, bg=COLORS["card"], anchor=W,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(fill=BOTH, padx=14, pady=(10, 2))
        content = tk.Frame(frame, bg=COLORS["card"])
        content.pack(fill=BOTH, expand=True)
        frame.pack(fill=BOTH, pady=6)
        return frame, content

    def _show_folder(self, var, path):
        var.set(path if path else "未选择")

    def _build_folder_section(self, parent):
        _, content = self._section(parent, "📂  文件夹设置")

        self.input_var = tk.StringVar(value="未选择")
        self.output_var = tk.StringVar(value="未选择")

        row1 = tk.Frame(content, bg=COLORS["card"])
        row1.pack(fill=BOTH, pady=(2, 4))
        tk.Label(row1, text="输入文件夹", bg=COLORS["card"], width=10, anchor=W,
                 font=("Microsoft YaHei UI", 10)).pack(side=LEFT, padx=(12, 6), pady=4)
        tk.Label(row1, textvariable=self.input_var, bg=COLORS["card"],
                 font=("Microsoft YaHei UI", 10), fg="#374151").pack(
            side=LEFT, fill=BOTH, expand=True, pady=4, padx=2)
        ttk.Button(row1, text="浏览…", command=self._browse_input).pack(side=RIGHT, padx=(4, 12), pady=4)

        row2 = tk.Frame(content, bg=COLORS["card"])
        row2.pack(fill=BOTH, pady=4)
        tk.Label(row2, text="输出文件夹", bg=COLORS["card"], width=10, anchor=W,
                 font=("Microsoft YaHei UI", 10)).pack(side=LEFT, padx=(12, 6), pady=4)
        tk.Label(row2, textvariable=self.output_var, bg=COLORS["card"],
                 font=("Microsoft YaHei UI", 10), fg="#374151").pack(
            side=LEFT, fill=BOTH, expand=True, pady=4, padx=2)
        ttk.Button(row2, text="浏览…", command=self._browse_output).pack(side=RIGHT, padx=(4, 12), pady=4)

        self.hint_var = tk.StringVar(value="")
        tk.Label(content, textvariable=self.hint_var, bg=COLORS["card"], anchor=W,
                 font=("Microsoft YaHei UI", 9), fg="#6b7280").pack(fill=BOTH, padx=14, pady=(0, 10))

    def _build_format_section(self, parent):
        _, content = self._section(parent, "⚙️  转换选项")

        row = tk.Frame(content, bg=COLORS["card"])
        row.pack(fill=BOTH, pady=(2, 4))
        tk.Label(row, text="目标格式", bg=COLORS["card"],
                 font=("Microsoft YaHei UI", 10)).pack(side=LEFT, padx=(12, 6), pady=4)
        ttk.Combobox(
            row, textvariable=self.target_format, state="readonly",
            values=FORMAT_LABELS, width=8,
        ).pack(side=LEFT, padx=2, pady=4, ipady=2)
        tk.Label(row, text="  质量(1-100)", bg=COLORS["card"],
                 font=("Microsoft YaHei UI", 10)).pack(side=LEFT, padx=(10, 6), pady=4)
        ttk.Spinbox(row, from_=1, to=100, textvariable=self.quality, width=5).pack(side=LEFT, pady=4, ipady=2)
        tk.Label(row, text="  尺寸", bg=COLORS["card"],
                 font=("Microsoft YaHei UI", 10)).pack(side=LEFT, padx=(14, 4), pady=4)
        ttk.Combobox(row, textvariable=self.scale_option, state="readonly",
                     values=SCALE_OPTIONS, width=8).pack(side=LEFT, padx=2, pady=4, ipady=2)

        row2 = tk.Frame(content, bg=COLORS["card"])
        row2.pack(fill=BOTH, pady=(0, 4))
        tk.Checkbutton(
            row2, text="包含子目录", variable=self.recursive,
            bg=COLORS["card"], font=("Microsoft YaHei UI", 10),
            activebackground=COLORS["card"], activeforeground=COLORS["accent"],
        ).pack(side=LEFT, padx=12, pady=4)
        tk.Label(row2, text="（JPEG/WEBP 的质量参数生效；GIF 保留全部帧）",
                 bg=COLORS["card"], font=("Microsoft YaHei UI", 8), fg="#9ca3af").pack(
            side=LEFT, padx=(10, 12), pady=4)

    def _build_actions(self, parent):
        _, content = self._section(parent, "🚀  开始")
        btns = tk.Frame(content, bg=COLORS["card"])
        btns.pack(fill=BOTH, padx=14, pady=4)
        self.convert_btn = tk.Button(
            btns, text="开 始 转 换", command=self._start_convert,
            bg=COLORS["accent"], fg="white",
            activebackground="#2563eb", activeforeground="white",
            font=("Microsoft YaHei UI", 12, "bold"),
            relief="flat", cursor="hand2",
        )
        self.convert_btn.pack(side=LEFT, fill=BOTH, expand=True)
        self.cancel_btn = tk.Button(
            btns, text="取 消", command=self._cancel_convert,
            bg="#e5e7eb", fg="#374151",
            activebackground="#d1d5db", activeforeground="#111827",
            font=("Microsoft YaHei UI", 12),
            relief="flat", cursor="hand2",
            state="disabled",
        )
        self.cancel_btn.pack(side=RIGHT, fill=BOTH, padx=(8, 0))

    def _build_progress(self, parent):
        _, content = self._section(parent, "📊  进度")
        self.progress = ttk.Progressbar(content, style="App.Horizontal.TProgressbar", mode="determinate")
        self.progress.pack(fill=BOTH, padx=14, pady=2)
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(content, textvariable=self.status_var, bg=COLORS["card"], anchor=W,
                 font=("Microsoft YaHei UI", 9), fg="#6b7280").pack(fill=BOTH, padx=14, pady=(0, 10))

    def _build_log(self, parent):
        _, content = self._section(parent, "📝  日志")
        self.log = tk.Text(
            content, height=8, wrap="word",
            font=("Consolas", 9), relief="flat",
            bg="#0f172a", fg="#d1d5db",
            insertbackground="white",
        )
        self.log.pack(fill=BOTH, expand=True, padx=14, pady=(2, 10))
        self.log.tag_config("ok", foreground=COLORS["ok"])
        self.log.tag_config("err", foreground=COLORS["err"])
        self.log.tag_config("info", foreground="#93c5fd")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------- 事件处理

    def _browse_input(self):
        folder = filedialog.askdirectory(title="选择图片输入文件夹")
        if folder:
            self.input_folder = os.path.abspath(folder)
            self._show_folder(self.input_var, self.input_folder)
            self._refresh()

    def _browse_output(self):
        folder = filedialog.askdirectory(title="选择图片输出文件夹")
        if folder:
            self.output_folder = os.path.abspath(folder)
            self._show_folder(self.output_var, self.output_folder)
            self._refresh()

    def _candidate_count(self):
        if not self.input_folder:
            return 0
        return len(find_image_files(self.input_folder, recursive=self.recursive.get()))

    def _refresh(self):
        self._show_folder(self.input_var, self.input_folder)
        self._show_folder(self.output_var, self.output_folder)
        count = self._candidate_count()
        self.hint_var.set(f"发现 {count} 个可转换图片文件" if count else "该文件夹中没有图片文件")
        self.status_var.set("就绪" if not self._running else "转换中…")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self._log_line(f"共 {count} 个候选图片", "info")

    def _log_line(self, message, tag="info"):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------- 转换

    def _start_convert(self):
        if self._running:
            messagebox.showinfo(APP_TITLE, "正在转换中，可点击“取 消”停止")
            return
        if not self.input_folder or not os.path.isdir(self.input_folder):
            messagebox.showwarning(APP_TITLE, "请先选择有效的输入文件夹")
            return
        if not self.output_folder or not os.path.isdir(self.output_folder):
            messagebox.showwarning(APP_TITLE, "请先选择有效的输出文件夹")
            return
        if self._candidate_count() == 0:
            messagebox.showwarning(APP_TITLE, "输入文件夹中没有可转换的图片")
            return

        self.cancel_event.clear()
        self._running = True
        self.convert_btn.configure(state="disabled", bg="#9ca3af")
        self.cancel_btn.configure(state="normal")
        self.progress["value"] = 0
        self.status_var.set("正在转换…")
        self._log_line(
            f"▶ 开始转换 → {self.output_folder} | 格式={self.target_format.get()} "
            f"| 质量={self.quality.get()} | 尺寸={self.scale_option.get()}", "info")

        worker = threading.Thread(target=self._run_worker, daemon=True)
        worker.start()

    def _cancel_convert(self):
        if not self._running:
            return
        self.cancel_event.set()
        self.cancel_btn.configure(state="disabled")
        self._log_line("⏹ 正在取消，等待当前文件完成…", "info")

    # 后台线程只做计算，结果一律通过 after() 回到主线程
    def _run_worker(self):
        def progress_cb(done, total, name):
            self.root.after(0, self._on_progress, done, total, name)

        def log_cb(name, ok, message):
            self.root.after(0, self._on_log, name, ok, message)

        try:
            stats: ConversionStats = batch_convert(
                self.input_folder,
                self.output_folder,
                self.target_format.get(),
                quality=self.quality.get(),
                recursive=self.recursive.get(),
                progress_cb=progress_cb,
                log_cb=log_cb,
                cancel_event=self.cancel_event,
                scale_percent=parse_scale_option(self.scale_option.get()),
            )
            self.root.after(0, self._on_finished, stats)
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, self._on_error, str(exc))

    def _on_progress(self, done, total, name):
        self.progress["maximum"] = total
        self.progress["value"] = done
        self.status_var.set(f"{done}/{total} — {name}")

    def _on_log(self, name, ok, message):
        tag = "ok" if ok else "err"
        self._log_line(f"{'✅' if ok else '❌'} {name}: {message}", tag)

    def _on_finished(self, stats: ConversionStats):
        self._running = False
        self._reset_buttons()
        self.progress["value"] = stats.total
        parts = [f"成功 {stats.success}", f"失败 {stats.failed}"]
        if stats.cancelled:
            parts.append(f"取消 {stats.cancelled}")
        self.status_var.set("完成：" + "，".join(parts))

        summary = "；".join(parts) + f"，共 {stats.total} 个文件"
        if stats.savings_pct is not None:
            direction = "减小" if stats.savings_pct >= 0 else "增大"
            summary += (f"；总体积{direction} {abs(stats.savings_pct):.1f}%"
                        f"（{human_size(stats.bytes_in)} → {human_size(stats.bytes_out)}）")
        self._log_line(f"✔ 转换完成：{summary}", "ok" if not stats.failed else "info")
        save_settings({
            "input_folder": self.input_folder,
            "output_folder": self.output_folder,
            "format": self.target_format.get(),
            "quality": self.quality.get(),
            "recursive": self.recursive.get(),
            "scale": self.scale_option.get(),
        })
        self.root.after(150, lambda: messagebox.showinfo(APP_TITLE, f"转换完成：{summary}"))

    def _on_error(self, message):
        self._running = False
        self._reset_buttons()
        self.status_var.set("发生错误")
        self._log_line(f"✖ 出错：{message}", "err")
        messagebox.showerror(APP_TITLE, f"转换过程中发生错误：\n{message}")

    def _reset_buttons(self):
        self.convert_btn.configure(state="normal", bg=COLORS["accent"])
        self.cancel_btn.configure(state="disabled")

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno(APP_TITLE, "正在转换中，确定要退出吗？"):
                return
            self.cancel_event.set()
        self.root.destroy()


def main(argv=None):
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if argv:
        # CLI 模式：python app.py <输入> <输出> -f JPEG …
        import converter as _c
        return _c.cli(argv)
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    raise SystemExit(main())
