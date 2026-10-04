"""CodeCoach Luau Kid GUI: A bright, kid-friendly visual desktop window.

Reads from coach engine and auto-refreshes live on file saves.
Zero external pip dependencies (pure standard library Tkinter).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import coach as C
import report as RP
from luaucheck import find_scripts

HERE = Path(__file__).resolve().parent
TOOLS = HERE / "tools"


class CodeCoachLuauApp(tk.Tk):
    def __init__(self, target_folder: Path):
        super().__init__()
        self.target = target_folder
        self.title("CodeCoach Luau for Kids 🎮")
        self.geometry("780x640")
        self.minsize(640, 500)
        self.configure(bg="#F0F4F8")

        self.engine = C.Coach(tools=TOOLS, state_dir=HERE)
        self.seen_mtimes: dict[str, float] = {}

        self._build_ui()
        self.check_files()
        self._poll_loop()

    def _build_ui(self):
        header = tk.Frame(self, bg="#E056FD", height=70)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        title = tk.Label(
            header,
            text="🎮 Roblox Script Coach",
            font=("Segoe UI", 18, "bold"),
            bg="#E056FD",
            fg="white",
        )
        title.pack(side=tk.LEFT, padx=20, pady=15)

        self.status_badge = tk.Label(
            header,
            text="Checking...",
            font=("Segoe UI", 12, "bold"),
            bg="#BE2EDD",
            fg="white",
            padx=12,
            pady=4,
        )
        self.status_badge.pack(side=tk.RIGHT, padx=20)

        main_frame = tk.Frame(self, bg="#F0F4F8")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        left_box = tk.LabelFrame(
            main_frame,
            text=" 📜 Your Luau Scripts ",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#2D3748",
            padx=8,
            pady=8,
        )
        left_box.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        self.file_listbox = tk.Listbox(
            left_box,
            font=("Consolas", 11),
            width=24,
            bd=0,
            highlightthickness=1,
            highlightcolor="#E056FD",
            selectbackground="#F3E8FF",
            selectforeground="#1A202C",
        )
        self.file_listbox.pack(fill=tk.BOTH, expand=True)
        self.file_listbox.bind("<<ListboxSelect>>", self._on_file_select)

        right_box = tk.LabelFrame(
            main_frame,
            text=" 💡 Coach Clues & Advice ",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#2D3748",
            padx=8,
            pady=8,
        )
        right_box.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.report_text = tk.Text(
            right_box,
            wrap=tk.WORD,
            font=("Segoe UI", 11),
            bg="#FAFAFA",
            fg="#2D3748",
            bd=0,
            padx=12,
            pady=12,
        )
        self.report_text.pack(fill=tk.BOTH, expand=True)
        self.report_text.config(state=tk.DISABLED)

        footer = tk.Frame(self, bg="#E2E8F0", height=35)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)

        path_lbl = tk.Label(
            footer,
            text=f"Watching: {self.target.name}",
            font=("Segoe UI", 9),
            bg="#E2E8F0",
            fg="#718096",
        )
        path_lbl.pack(side=tk.LEFT, padx=15)

        discord_btn = tk.Button(
            footer,
            text="💎 Join Discord (First 100 Badge)",
            font=("Segoe UI", 9, "bold"),
            bg="#5865F2",
            fg="white",
            relief=tk.FLAT,
            cursor="hand2",
            command=lambda: __import__("webbrowser").open("https://discord.gg/QtyBucygQ6"),
            padx=8,
        )
        discord_btn.pack(side=tk.RIGHT, padx=6, pady=4)

        recheck_btn = tk.Button(
            footer,
            text="🔄 Re-check Now",
            font=("Segoe UI", 9, "bold"),
            bg="white",
            fg="#BE2EDD",
            relief=tk.FLAT,
            command=self.check_files,
            padx=8,
        )
        recheck_btn.pack(side=tk.RIGHT, padx=15, pady=4)

    def _on_file_select(self, _event):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if hasattr(self, "current_checks") and idx < len(self.current_checks):
            check, rec = self.current_checks[idx]
            self._render_report(check, rec)

    def _render_report(self, check: C.Check, rec: C.StuckRecord):
        now = time.time()
        rendered = RP.render(check, rec, now, kid_mode=True)

        self.report_text.config(state=tk.NORMAL)
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert(tk.END, rendered)
        self.report_text.config(state=tk.DISABLED)

    def check_files(self):
        now = time.time()
        files = [self.target] if self.target.is_file() else find_scripts(self.target)
        checks = [self.engine.examine(p, now=now, run=False) for p in files]
        self.engine.save()
        self.current_checks = checks

        selected_idx = self.file_listbox.curselection()
        prev_sel = selected_idx[0] if selected_idx else 0

        self.file_listbox.delete(0, tk.END)
        all_clean = True
        has_stuck = False

        for check, rec in checks:
            name = Path(check.path).name
            if check.clean:
                tag = "✅ "
            elif rec.signature and C.is_stuck(rec, now):
                tag = "⏳ "
                all_clean = False
                has_stuck = True
            else:
                tag = "🐞 "
                all_clean = False
            self.file_listbox.insert(tk.END, f"{tag}{name}")

        if checks:
            new_idx = min(prev_sel, len(checks) - 1)
            self.file_listbox.selection_set(new_idx)
            self._render_report(checks[new_idx][0], checks[new_idx][1])

        if not checks:
            self.status_badge.config(text="No scripts found", bg="#A0AEC0")
        elif all_clean:
            self.status_badge.config(text="🌟 All Good!", bg="#38A169")
        elif has_stuck:
            self.status_badge.config(text="💡 Clue Time!", bg="#DD6B20")
        else:
            self.status_badge.config(text="🔧 Needs Fix", bg="#E53E3E")

    def _poll_loop(self):
        files = [self.target] if self.target.is_file() else find_scripts(self.target)
        current = {}
        for p in files:
            try:
                current[str(p)] = p.stat().st_mtime
            except OSError:
                continue
        if current != self.seen_mtimes:
            self.seen_mtimes = current
            self.check_files()
        self.after(1000, self._poll_loop)


def main():
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "kidcode"
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
    app = CodeCoachLuauApp(target)
    app.mainloop()


if __name__ == "__main__":
    main()
