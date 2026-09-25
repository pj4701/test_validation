from __future__ import annotations

import queue
import threading
from pathlib import Path
import os
import sys
import customtkinter as ctk
from tkinter import filedialog

from validators.registry import VALIDATIONS
from utils.path_utils import OUTPUT_DIR, file_name


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

PRIMARY = "#2563EB"
SUCCESS = "#16A34A"
BACKGROUND = "#F8FAFC"
DARK = "#0F172A"


class ValidationHub(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Data Validation Hub")
        self.geometry("1500x900")
        self.minsize(1250, 760)
        self.configure(fg_color=BACKGROUND)

        self.file_paths = {}
        self.file_labels = {}
        self.log_queue = queue.Queue()
        self.running = False

        self._build_header()
        self._build_main()
        self._select_validation("Actuals Validation")
        self.after(100, self._drain_log_queue)

    # ---------------- UI ----------------
    def _build_header(self):
        header = ctk.CTkFrame(self, height=90, fg_color=DARK, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(
            header, text="📊 DATA VALIDATION HUB",
            font=("Segoe UI", 30, "bold"), text_color="white"
        ).pack(pady=(15, 0))
        ctk.CTkLabel(
            header, text="Integrated o9 / Source Reconciliation Platform",
            font=("Segoe UI", 12), text_color="#CBD5E1"
        ).pack()

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=20)

        self.left = ctk.CTkFrame(main, width=470, corner_radius=15)
        self.left.pack(side="left", fill="y", padx=(0, 15))
        self.left.pack_propagate(False)

        self.right = ctk.CTkFrame(main, fg_color="transparent")
        self.right.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            self.left, text="Validation Type",
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w", padx=20, pady=(20, 10))

        self.validation_combo = ctk.CTkComboBox(
            self.left,
            values=list(VALIDATIONS.keys()),
            height=40,
            command=self._select_validation
        )
        self.validation_combo.pack(fill="x", padx=20)

        self.description = ctk.CTkLabel(
            self.left, text="", justify="left", anchor="w",
            wraplength=420, font=("Segoe UI", 12), text_color="#475569"
        )
        self.description.pack(fill="x", padx=20, pady=(8, 10))

        self.files_frame = ctk.CTkScrollableFrame(
            self.left, label_text="Input Files", height=430
        )
        self.files_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        self.run_btn = ctk.CTkButton(
            self.left, text="▶ Run Validation", height=50,
            font=("Segoe UI", 16, "bold"),
            fg_color=SUCCESS, command=self._start_validation
        )
        self.run_btn.pack(fill="x", padx=20, pady=(5, 6))

        self.output_btn = ctk.CTkButton(
            self.left, text="📂 Open Output Folder", height=36,
            command=self._open_output_folder, fg_color="#475569"
        )
        self.output_btn.pack(fill="x", padx=20, pady=(0, 10))

        self.status = ctk.CTkLabel(
            self.left, text="Ready",
            font=("Segoe UI", 14, "bold"), text_color=PRIMARY
        )
        self.status.pack()

        self.progress = ctk.CTkProgressBar(self.left)
        self.progress.pack(fill="x", padx=20, pady=15)
        self.progress.set(0)

        self._build_right()

    def _build_right(self):
        kpi = ctk.CTkFrame(self.right, fg_color="transparent")
        kpi.pack(fill="x")

        self.kpi_values = {}
        for title in ["Records", "Passed", "Failed", "Match %"]:
            card = ctk.CTkFrame(kpi, corner_radius=15, height=120)
            card.pack(side="left", fill="x", expand=True, padx=7)
            ctk.CTkLabel(card, text=title, font=("Segoe UI", 14)).pack(pady=(20, 5))
            value = ctk.CTkLabel(
                card, text="0", font=("Segoe UI", 32, "bold")
            )
            value.pack()
            self.kpi_values[title] = value

        logs_frame = ctk.CTkFrame(self.right, corner_radius=15)
        logs_frame.pack(fill="both", expand=True, pady=15)

        ctk.CTkLabel(
            logs_frame, text="Validation Logs",
            font=("Segoe UI", 20, "bold")
        ).pack(anchor="w", padx=20, pady=(15, 10))

        self.log_text = ctk.CTkTextbox(logs_frame, font=("Consolas", 12))
        self.log_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))


    def _open_output_folder(self):
        try:
            path = Path(OUTPUT_DIR)
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as exc:
            self._append_log(f"Unable to open output folder: {exc}")

    # ---------------- File configuration ----------------
    def _select_validation(self, name):
        if self.running:
            return

        self.validation_combo.set(name)
        config = VALIDATIONS[name]
        self.description.configure(text=config["description"])

        self.file_paths = {}
        for child in self.files_frame.winfo_children():
            child.destroy()
        self.file_labels = {}

        for file_key in config["files"]:
            ctk.CTkLabel(
                self.files_frame, text=file_key,
                font=("Segoe UI", 13, "bold")
            ).pack(anchor="w", pady=(8, 2))

            row = ctk.CTkFrame(self.files_frame, fg_color="transparent")
            row.pack(fill="x", pady=(0, 3))

            label = ctk.CTkLabel(
                row, text="No file selected", anchor="w", height=32
            )
            label.pack(side="left", fill="x", expand=True)

            self.file_labels[file_key] = label

            ctk.CTkButton(
                row, text="Browse", width=85,
                command=lambda key=file_key: self._browse(key)
            ).pack(side="right", padx=(8, 0))

        self.status.configure(text="Ready")
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)

    def _browse(self, key):
        path = filedialog.askopenfilename(
            title=f"Select {key}",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if path:
            self.file_paths[key] = path
            self.file_labels[key].configure(text=file_name(path))

    # ---------------- Execution ----------------
    def _start_validation(self):
        if self.running:
            return

        name = self.validation_combo.get()
        config = VALIDATIONS.get(name)
        if not config:
            return

        missing = [f for f in config["files"] if f not in self.file_paths]
        if missing:
            self._append_log("Missing file(s): " + ", ".join(missing))
            self.status.configure(text="Missing File")
            return

        self.running = True
        self.run_btn.configure(state="disabled", text="Running...")
        self.status.configure(text="Running...")
        self.log_text.delete("1.0", "end")
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        threading.Thread(
            target=self._worker,
            args=(name, config["runner"], dict(self.file_paths)),
            daemon=True
        ).start()

    def _worker(self, name, runner, files):
        try:
            result = runner(
                files,
                output_dir=OUTPUT_DIR,
                log_callback=lambda msg: self.log_queue.put(("log", msg))
            )
            self.log_queue.put(("done", result))
        except Exception as exc:
            self.log_queue.put(("error", exc))

    def _drain_log_queue(self):
        try:
            while True:
                event, payload = self.log_queue.get_nowait()
                if event == "log":
                    self._append_log(payload)
                elif event == "done":
                    self._finish(payload)
                elif event == "error":
                    self._fail(payload)
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    def _append_log(self, message):
        self.log_text.insert("end", str(message) + "\n")
        self.log_text.see("end")

    def _finish(self, result):
        self.running = False
        self.run_btn.configure(state="normal", text="▶ Run Validation")
        self.status.configure(text="Completed ✅")
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(1)

        self.kpi_values["Records"].configure(text=f"{result.records:,}")
        self.kpi_values["Passed"].configure(text=f"{result.passed:,}")
        self.kpi_values["Failed"].configure(text=f"{result.failed:,}")
        self.kpi_values["Match %"].configure(text=f"{result.match_pct:.2f}%")

        self._append_log("")
        self._append_log("=" * 65)
        self._append_log("VALIDATION COMPLETED")
        self._append_log("=" * 65)
        for key, value in result.details.items():
            self._append_log(f"{key:<35}: {value}")
        self._append_log(f"Report: {result.output_file}")

    def _fail(self, exc):
        self.running = False
        self.run_btn.configure(state="normal", text="▶ Run Validation")
        self.status.configure(text="Failed ❌")
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        self._append_log("")
        self._append_log(f"ERROR: {exc}")


def main():
    app = ValidationHub()
    app.mainloop()


if __name__ == "__main__":
    main()
