import os
import csv
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime

# ------------------ Konfiguration ------------------
INITIAL_SECONDS = 5 * 60  # 5 Minuten

# ------------------ Ordner und Modus am Start ------------------
root_select = tk.Tk()
root_select.withdraw()  # Hauptfenster verstecken

# Speicherordner wählen
DATA_DIR = filedialog.askdirectory(title="Speicherordner auswählen")
if not DATA_DIR:
    messagebox.showerror("Kein Ordner", "Es wurde kein Speicherordner ausgewählt. Programm beendet.")
    exit()

# Messmodus wählen
modus = simpledialog.askstring("Messmodus", "Messmodus wählen:\n'einzel' = Einzelmessungen\n'tages' = Tagesmessung")
TAGESMODUS = (modus.strip().lower() == "tages") if modus else False
root_select.destroy()

# ------------------ Hilfsfunktionen ------------------
def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)

def csv_path_for_target(target_nr: str):
    """Pfad data/<Target>-YYYY-MM-DD.csv erstellen."""
    ensure_dirs()
    ymd = datetime.now().strftime("%Y-%m-%d")
    safe_target = re.sub(r"[^A-Za-z0-9._-]+", "_", (target_nr or "").strip()) or "unbekannt"
    if TAGESMODUS:
        # Alle Messungen des Tages in eine Datei
        return os.path.join(DATA_DIR, f"Tagesmessung-{ymd}.csv")
    else:
        return os.path.join(DATA_DIR, f"{safe_target}-{ymd}.csv")

def write_csv_row_to_target(rowdict, target_nr: str):
    """Speichert eine Zeile in die Datei, je nach Modus."""
    path = csv_path_for_target(target_nr)
    headers = [
        "timestamp_start", "target_nr",
        "frostpunkt_ic", "frostpunkt_inlet_i", "frostpunkt_inlet_ii",
        "nulltest_skipped", "nulltest_skip_ts", "nulltest_end", "nulltest_eisbildung",
        "nulltest_total_seconds", "nulltest_extended_seconds",
        "messung_start", "messung_end", "messung_eis_vorhanden",
        "messung_kristalle", "messung_kristalle_code",
        "messung_total_seconds", "messung_extended_seconds",
    ]
    file_exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            w.writeheader()
        w.writerow({h: rowdict.get(h, "") for h in headers})
    return path

# ------------------ App ------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Messung – Nulltest & Echte Messung")
        self.geometry("760x680")
        self.minsize(740, 660)

        # --- Zustände / Variablen ---
        self.start_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Nulltest
        self.nt_total = INITIAL_SECONDS
        self.nt_remaining = INITIAL_SECONDS
        self.nt_timer_running = False
        self.nt_after_job = None
        self.nt_eisbildung = None
        self.nulltest_end_ts = None
        self.nulltest_skipped = False
        self.nulltest_skip_ts = None

        # Messung
        self.ms_total = INITIAL_SECONDS
        self.ms_remaining = INITIAL_SECONDS
        self.ms_timer_running = False
        self.ms_after_job = None
        self.messung_start_ts = None
        self.messung_end_ts = None
        self.ms_eis = None  # "Ja"/"Nein"

        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        # Kopf / Stammdaten
        top = ttk.LabelFrame(root, text="Stammdaten")
        top.pack(fill="x", padx=0, pady=(0,10))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Zeitstempel (Start):").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self.ts_var = tk.StringVar(value=self.start_timestamp)
        ttk.Entry(top, textvariable=self.ts_var, state="readonly", width=30).grid(row=0, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(top, text="Target-Nr.:").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        self.target_var = tk.StringVar()
        self.target_entry = ttk.Entry(top, textvariable=self.target_var, width=30)
        self.target_entry.grid(row=1, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(top, text="Frostpunkt IC:").grid(row=2, column=0, sticky="w", padx=6, pady=6)
        self.fp_ic_var = tk.StringVar()
        self.fp_ic_entry = ttk.Entry(top, textvariable=self.fp_ic_var, width=30)
        self.fp_ic_entry.grid(row=2, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(top, text="Frostpunkt Inlet I:").grid(row=3, column=0, sticky="w", padx=6, pady=6)
        self.fp_inlet1_var = tk.StringVar()
        self.fp_inlet1_entry = ttk.Entry(top, textvariable=self.fp_inlet1_var, width=30)
        self.fp_inlet1_entry.grid(row=3, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(top, text="Frostpunkt Inlet II:").grid(row=4, column=0, sticky="w", padx=6, pady=6)
        self.fp_inlet2_var = tk.StringVar()
        self.fp_inlet2_entry = ttk.Entry(top, textvariable=self.fp_inlet2_var, width=30)
        self.fp_inlet2_entry.grid(row=4, column=1, sticky="w", padx=6, pady=6)

        # ---------- Nulltest ----------
        nt = ttk.LabelFrame(root, text="Nulltest")
        nt.pack(fill="x", padx=0, pady=(0,10))
        nt.columnconfigure(1, weight=1)

        nt_btns = ttk.Frame(nt)
        nt_btns.grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(8,4))
        self.nt_start_btn = ttk.Button(nt_btns, text="Nulltest starten", command=self.nt_start)
        self.nt_start_btn.pack(side="left", padx=(0,6))
        self.nt_skip_btn  = ttk.Button(nt_btns, text="Nulltest überspringen", command=self.nt_skip)
        self.nt_skip_btn.pack(side="left", padx=6)
        self.nt_reset_btn = ttk.Button(nt_btns, text="Timer zurücksetzen", command=self.nt_reset, state="disabled")
        self.nt_reset_btn.pack(side="left", padx=6)
        self.nt_ext2_btn = ttk.Button(nt_btns, text="+2 min", command=lambda: self.nt_extend(2*60), state="disabled")
        self.nt_ext2_btn.pack(side="left", padx=(18,6))
        self.nt_ext5_btn = ttk.Button(nt_btns, text="+5 min", command=lambda: self.nt_extend(5*60), state="disabled")
        self.nt_ext5_btn.pack(side="left", padx=6)

        ttk.Label(nt, text="Restzeit:").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        self.nt_time_var = tk.StringVar(value=self._fmt(self.nt_remaining))
        ttk.Label(nt, textvariable=self.nt_time_var, font=("TkDefaultFont", 11, "bold")).grid(row=1, column=1, sticky="w", padx=6, pady=6)

        self.nt_pb = ttk.Progressbar(nt, mode="determinate", maximum=self.nt_total, length=560)
        self.nt_pb.grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(0,10))
        self.nt_pb["value"] = 0

        ttk.Label(nt, text="Nulltest Ende/Status:").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        self.nt_end_var = tk.StringVar(value="")
        ttk.Entry(nt, textvariable=self.nt_end_var, state="readonly").grid(row=3, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(nt, text="Eisbildung (Nulltest):").grid(row=4, column=0, sticky="w", padx=6, pady=(0,8))
        self.nt_eis_var = tk.StringVar(value="")
        ttk.Entry(nt, textvariable=self.nt_eis_var, state="readonly").grid(row=4, column=1, sticky="ew", padx=6, pady=(0,8))

        # ---------- Echte Messung (farblich abgesetzt) ----------
        ms_bg = tk.Frame(root, bg="#eaf6ff", bd=0, highlightthickness=0)
        ms_bg.pack(fill="x", padx=0, pady=(0,10))
        self.ms_section = ms_bg

        ms = ttk.LabelFrame(ms_bg, text="Echte Messung")
        ms.pack(fill="x", padx=8, pady=8)
        ms.columnconfigure(1, weight=1)

        tk.Label(ms, text="Dieser Bereich erscheint nach abgeschlossenem Nulltest (oder wenn Nulltest übersprungen wurde).",
                 bg="#eaf6ff").grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6,0))

        ms_btns = ttk.Frame(ms)
        ms_btns.grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(8,4))
        self.ms_start_btn = ttk.Button(ms_btns, text="Messung starten", command=self.ms_start, state="disabled")
        self.ms_start_btn.pack(side="left", padx=(0,6))
        self.ms_reset_btn = ttk.Button(ms_btns, text="Timer zurücksetzen", command=self.ms_reset, state="disabled")
        self.ms_reset_btn.pack(side="left", padx=6)
        self.ms_ext2_btn = ttk.Button(ms_btns, text="+2 min", command=lambda: self.ms_extend(2*60), state="disabled")
        self.ms_ext2_btn.pack(side="left", padx=(18,6))
        self.ms_ext5_btn = ttk.Button(ms_btns, text="+5 min", command=lambda: self.ms_extend(5*60), state="disabled")
        self.ms_ext5_btn.pack(side="left", padx=6)

        ttk.Label(ms, text="Restzeit:").grid(row=2, column=0, sticky="w", padx=6, pady=6)
        self.ms_time_var = tk.StringVar(value=self._fmt(self.ms_remaining))
        ttk.Label(ms, textvariable=self.ms_time_var, font=("TkDefaultFont", 11, "bold")).grid(row=2, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(ms, text="Messung Start:").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        self.ms_start_var = tk.StringVar(value="")
        ttk.Entry(ms, textvariable=self.ms_start_var, state="readonly").grid(row=4, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(ms, text="Messung Ende:").grid(row=5, column=0, sticky="w", padx=6, pady=4)
        self.ms_end_var = tk.StringVar(value="")
        ttk.Entry(ms, textvariable=self.ms_end_var, state="readonly").grid(row=5, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(ms, text="Eis vorhanden (Messung):").grid(row=6, column=0, sticky="w", padx=6, pady=4)
        self.ms_eis_var = tk.StringVar(value="")
        ttk.Entry(ms, textvariable=self.ms_eis_var, state="readonly").grid(row=6, column=1, sticky="ew", padx=6, pady=4)

        # Kristalle: Eingabefeld + Bestätigungsbutton
        ttk.Label(ms, text="Kristalle (Anzahl oder 'k.A.'):").grid(row=7, column=0, sticky="w", padx=6, pady=(4,10))
        self.ms_kristalle_var = tk.StringVar(value="")

        def _validate_kristalle(proposed: str):
            if proposed == "":
                return True
            if re.fullmatch(r"\d+", proposed):
                return True
            if re.fullmatch(r"k\.?a\.?", proposed, flags=re.IGNORECASE):
                return True
            return False

        vcmd = (self.register(_validate_kristalle), "%P")
        row7 = ttk.Frame(ms)
        row7.grid(row=7, column=1, sticky="w", padx=6, pady=(4,10))
        self.ms_kristalle_entry = ttk.Entry(
            row7, textvariable=self.ms_kristalle_var, width=12,
            validate="key", validatecommand=vcmd, state="disabled"
        )
        self.ms_kristalle_entry.pack(side="left")
        self.ms_kristalle_entry.bind("<Return>", lambda e: self._confirm_kristalle())

        self.ms_kristalle_confirm = ttk.Button(
            row7, text="Übernehmen & speichern", command=self._confirm_kristalle, state="disabled"
        )
        self.ms_kristalle_confirm.pack(side="left", padx=8)

        # Statuszeile
        ttk.Separator(root, orient="horizontal").pack(fill="x", pady=(4,4))
        self.status_var = tk.StringVar(value="Bereit.")
        ttk.Label(root, textvariable=self.status_var).pack(anchor="w")


    # ---------- Hilfsmethoden ----------
    def _lock_inputs(self, lock: bool):
        state = "disabled" if lock else "normal"
        for e in (self.target_entry, self.fp_ic_entry, self.fp_inlet1_entry, self.fp_inlet2_entry):
            e.configure(state=state)

    @staticmethod
    def _fmt(seconds: int) -> str:
        m, s = divmod(max(0, int(seconds)), 60)
        return f"{m:02d}:{s:02d}"

    # ---------- Nulltest Methoden ----------
    def nt_start(self):
        if self.nt_timer_running:
            return
        if not self.target_var.get().strip():
            if not messagebox.askyesno("Target-Nr. leer", "Keine Target-Nr. eingetragen. Nulltest trotzdem starten?"):
                return
        if self.nulltest_skipped:
            messagebox.showinfo("Hinweis", "Nulltest wurde bereits übersprungen.")
            return

        self.nt_timer_running = True
        self.nt_remaining = self.nt_total
        self._lock_inputs(True)
        self._enable_nt_controls(running=True)
        self.status_var.set("Nulltest läuft …")
        self._nt_tick()

    def nt_skip(self):
        if self.nt_timer_running:
            messagebox.showwarning("Nicht möglich", "Nulltest läuft gerade. Bitte erst zurücksetzen oder beenden.")
            return
        if not messagebox.askyesno("Nulltest überspringen", "Nulltest wirklich überspringen?"):
            return
        self.nulltest_skipped = True
        self.nulltest_skip_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.nt_end_var.set(f"Übersprungen um {self.nulltest_skip_ts}")
        self.nt_eis_var.set("—")
        self.nt_start_btn.configure(state="disabled")
        self.nt_skip_btn.configure(state="disabled")
        self.nt_reset_btn.configure(state="disabled")
        self.nt_ext2_btn.configure(state="disabled")
        self.nt_ext5_btn.configure(state="disabled")
        self.ms_start_btn.configure(state="normal")
        self.status_var.set("Nulltest übersprungen. Echte Messung kann gestartet werden.")

    def _nt_tick(self):
        self.nt_time_var.set(self._fmt(self.nt_remaining))
        self.nt_pb["maximum"] = self.nt_total
        self.nt_pb["value"] = self.nt_total - self.nt_remaining
        if self.nt_remaining <= 0:
            self._nt_finish()
            return
        self.nt_remaining -= 1
        self.nt_after_job = self.after(1000, self._nt_tick)

    def nt_extend(self, seconds):
        if not self.nt_timer_running:
            return
        self.nt_total += seconds
        self.nt_remaining += seconds
        self.status_var.set(f"Nulltest verlängert um {seconds//60} min – Rest {self._fmt(self.nt_remaining)}")

    def nt_reset(self):
        if self.nt_after_job is not None:
            self.after_cancel(self.nt_after_job)
            self.nt_after_job = None
        self.nt_timer_running = False
        self.nt_total = INITIAL_SECONDS
        self.nt_remaining = INITIAL_SECONDS
        self.nt_pb["maximum"] = self.nt_total
        self.nt_pb["value"] = 0
        self.nt_time_var.set(self._fmt(self.nt_remaining))
        self.nt_end_var.set("")
        self.nt_eis_var.set("")
        self.nulltest_end_ts = None
        self.nt_eisbildung = None
        self.nulltest_skipped = False
        self.nulltest_skip_ts = None
        self.nt_skip_btn.configure(state="normal")
        self._lock_inputs(False)
        self._enable_nt_controls(running=False)
        self._reset_measurement_ui(full=True)
        self.status_var.set("Nulltest zurückgesetzt.")

    def _nt_finish(self):
        if self.nt_after_job is not None:
            self.after_cancel(self.nt_after_job)
            self.nt_after_job = None
        self.nt_timer_running = False
        self._enable_nt_controls(running=False)

        self.nulltest_end_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.nt_end_var.set(self.nulltest_end_ts)

        eis_jn = messagebox.askyesno("Eisbildung?", "Eisbildung (Nulltest)?")
        self.nt_eisbildung = "Ja" if eis_jn else "Nein"
        self.nt_eis_var.set(self.nt_eisbildung)

        self.status_var.set("Nulltest abgeschlossen. Echte Messung kann gestartet werden.")
        self.ms_start_btn.configure(state="normal")

    def _enable_nt_controls(self, running: bool):
        self.nt_start_btn.configure(state="disabled" if running else "normal")
        self.nt_reset_btn.configure(state="normal" if running else "disabled")
        self.nt_ext2_btn.configure(state="normal" if running else "disabled")
        self.nt_ext5_btn.configure(state="normal" if running else "disabled")
        self.nt_skip_btn.configure(state="disabled" if running or self.nulltest_skipped else "normal")

    # ---------- Messung Methoden ----------
    def ms_start(self):
        if self.ms_timer_running:
            return
        self.messung_start_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.ms_start_var.set(self.messung_start_ts)

        self.ms_timer_running = True
        self.ms_total = INITIAL_SECONDS
        self.ms_remaining = INITIAL_SECONDS
        self._enable_ms_controls(running=True)
        self._ms_tick()
        self.status_var.set("Echte Messung läuft …")

    def _ms_tick(self):
        self.ms_time_var.set(self._fmt(self.ms_remaining))
        self.ms_pb["maximum"] = self.ms_total
        self.ms_pb["value"] = self.ms_total - self.ms_remaining
        if self.ms_remaining <= 0:
            self._ms_finish()
            return
        self.ms_remaining -= 1
        self.ms_after_job = self.after(1000, self._ms_tick)

    def ms_extend(self, seconds):
        if not self.ms_timer_running:
            return
        self.ms_total += seconds
        self.ms_remaining += seconds
        self.status_var.set(f"Messung verlängert um {seconds//60} min – Rest {self._fmt(self.ms_remaining)}")

    def ms_reset(self):
        if self.ms_after_job is not None:
            self.after_cancel(self.ms_after_job)
            self.ms_after_job = None
        self.ms_timer_running = False
        self.ms_total = INITIAL_SECONDS
        self.ms_remaining = INITIAL_SECONDS
        self.ms_pb["maximum"] = self.ms_total
        self.ms_pb["value"] = 0
        self.ms_time_var.set(self._fmt(self.ms_remaining))
        self.ms_start_var.set("")
        self.ms_end_var.set("")
        self.ms_eis_var.set("")
        self._enable_ms_controls(running=False)
        self._reset_measurement_ui()
        self.status_var.set("Messung zurückgesetzt.")

    def _enable_ms_controls(self, running: bool):
        state = "normal" if running else "disabled"
        self.ms_reset_btn.configure(state=state)
        self.ms_ext2_btn.configure(state=state)
        self.ms_ext5_btn.configure(state=state)
        self.ms_kristalle_entry.configure(state=state)
        self.ms_kristalle_confirm.configure(state=state)
        self.ms_start_btn.configure(state="disabled" if running else "normal")

    def _reset_measurement_ui(self, full=False):
        self.ms_start_var.set("")
        self.ms_end_var.set("")
        self.ms_eis_var.set("")
        self.ms_kristalle_var.set("")
        if full:
            self.ms_start_btn.configure(state="disabled")

    def _ms_finish(self):
        if self.ms_after_job is not None:
            self.after_cancel(self.ms_after_job)
            self.ms_after_job = None
        self.ms_timer_running = False
        self.messung_end_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.ms_end_var.set(self.messung_end_ts)

        eis_jn = messagebox.askyesno("Eis vorhanden?", "Eis vorhanden (Messung)?")
        self.ms_eis = "Ja" if eis_jn else "Nein"
        self.ms_eis_var.set(self.ms_eis)
        self.status_var.set("Messung beendet. Kristalle erfassen und speichern.")

    def _confirm_kristalle(self):
        k = self.ms_kristalle_var.get().strip()
        if not k:
            messagebox.showwarning("Eingabe fehlt", "Bitte Anzahl der Kristalle eingeben oder 'k.A.'")
            return
        code = 1 if k.lower() == "k.a." else 0
        self._finalize_and_save(kristalle=k, kristalle_code=code)
        self.ms_kristalle_entry.configure(state="disabled")
        self.ms_kristalle_confirm.configure(state="disabled")
        self.status_var.set("Daten gespeichert.")

    def _finalize_and_save(self, kristalle, kristalle_code):
        row = {
            "timestamp_start": self.start_timestamp,
            "target_nr": self.target_var.get(),
            "frostpunkt_ic": self.fp_ic_var.get(),
            "frostpunkt_inlet_i": self.fp_inlet1_var.get(),
            "frostpunkt_inlet_ii": self.fp_inlet2_var.get(),
            "nulltest_skipped": "Ja" if self.nulltest_skipped else "Nein",
            "nulltest_skip_ts": self.nulltest_skip_ts,
            "nulltest_end": self.nulltest_end_ts,
            "nulltest_eisbildung": self.nt_eisbildung,
            "nulltest_total_seconds": INITIAL_SECONDS,
            "nulltest_extended_seconds": self.nt_total - INITIAL_SECONDS,
            "messung_start": self.messung_start_ts,
            "messung_end": self.messung_end_ts,
            "messung_eis_vorhanden": self.ms_eis,
            "messung_kristalle": kristalle,
            "messung_kristalle_code": kristalle_code,
            "messung_total_seconds": INITIAL_SECONDS,
            "messung_extended_seconds": self.ms_total - INITIAL_SECONDS,
        }
        write_csv_row_to_target(row, self.target_var.get())

# ---------- App starten ----------
if __name__ == "__main__":
    app = App()
    app.mainloop()
