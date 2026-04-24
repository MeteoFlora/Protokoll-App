import os
import csv
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime
try:
    from tkcalendar import DateEntry
    HAS_TKCALENDAR = True
except ImportError:
    HAS_TKCALENDAR = False

# ------------------ Konfiguration ------------------
INITIAL_SECONDS = 10 * 60  # 10 Minuten (Standard)

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
        return os.path.join(DATA_DIR, f"Tagesmessung-{ymd}.csv")
    else:
        return os.path.join(DATA_DIR, f"{safe_target}-{ymd}.csv")

def write_csv_row_to_target(rowdict, target_nr: str):
    """Speichert eine Zeile in die Datei, je nach Modus."""
    path = csv_path_for_target(target_nr)
    headers = [
        "timestamp_start", "target_nr",
        "frostpunkt_ic", "frostpunkt_inlet_i", "frostpunkt_inlet_ii",
        "herstellungsdatum_zuckerlosung",
        "fluss_inlet_i", "fluss_inlet_ii",
        "nulltest_skipped", "nulltest_skip_ts", "nulltest_end", "nulltest_eisbildung",
        "nulltest_total_seconds", "nulltest_extended_seconds",
        "messung_start", "messung_end", "messung_eis_vorhanden",
        "messung_kristalle", "messung_kristalle_code",
        "messung_wachstum",
        "messung_total_seconds", "messung_extended_seconds", "messung_abgebrochen",
    ]
    file_exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            w.writeheader()
        w.writerow({h: rowdict.get(h, "") for h in headers})
    return path

# ------------------ Hilfsdialog: Startzeit wählen ------------------
def ask_initial_seconds(parent, title: str, current_seconds: int) -> int:
    """
    Öffnet einen kleinen Dialog, in dem der Benutzer die Startdauer
    in Minuten eingeben kann. Gibt die gewählten Sekunden zurück,
    oder current_seconds bei Abbruch.
    """
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.resizable(False, False)
    dlg.grab_set()

    ttk.Label(dlg, text="Startdauer in Minuten:").grid(row=0, column=0, padx=12, pady=(16, 4), sticky="w")

    var = tk.StringVar(value=str(current_seconds // 60))
    entry = ttk.Entry(dlg, textvariable=var, width=8)
    entry.grid(row=0, column=1, padx=12, pady=(16, 4))
    entry.focus()

    result = [current_seconds]  # Mutable container für Rückgabewert

    def _ok():
        try:
            mins = int(var.get().strip())
            if mins <= 0:
                raise ValueError
            result[0] = mins * 60
            dlg.destroy()
        except ValueError:
            messagebox.showwarning("Ungültige Eingabe", "Bitte eine positive ganze Zahl eingeben.", parent=dlg)

    def _cancel():
        dlg.destroy()

    btn_frame = ttk.Frame(dlg)
    btn_frame.grid(row=1, column=0, columnspan=2, pady=(8, 12))
    ttk.Button(btn_frame, text="OK", command=_ok).pack(side="left", padx=6)
    ttk.Button(btn_frame, text="Abbrechen", command=_cancel).pack(side="left", padx=6)

    entry.bind("<Return>", lambda e: _ok())
    parent.wait_window(dlg)
    return result[0]

# ------------------ App ------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Messung – Nulltest & Echte Messung")
        self.geometry("760x760")
        self.minsize(740, 720)

        # --- Zustände / Variablen ---
        self.start_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Nulltest
        self.nt_initial = INITIAL_SECONDS   # konfigurierbare Startdauer
        self.nt_total = INITIAL_SECONDS
        self.nt_remaining = INITIAL_SECONDS
        self.nt_timer_running = False
        self.nt_after_job = None
        self.nt_eisbildung = None
        self.nulltest_end_ts = None
        self.nulltest_skipped = False
        self.nulltest_skip_ts = None

        # Messung
        self.ms_initial = INITIAL_SECONDS   # konfigurierbare Startdauer
        self.ms_total = INITIAL_SECONDS
        self.ms_remaining = INITIAL_SECONDS
        self.ms_timer_running = False
        self.ms_after_job = None
        self.messung_start_ts = None
        self.messung_end_ts = None
        self.ms_eis = None
        self.ms_abgebrochen = False

        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        # Kopf / Stammdaten
        top = ttk.LabelFrame(root, text="Stammdaten")
        top.pack(fill="x", padx=0, pady=(0, 10))
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

        # NEU: Herstellungsdatum Zuckerlösung (mit Kalender wenn tkcalendar installiert)
        ttk.Label(top, text="Herstellungsdatum Zuckerlösung:").grid(row=5, column=0, sticky="w", padx=6, pady=6)
        self.zucker_var = tk.StringVar()
        if HAS_TKCALENDAR:
            zucker_frame = ttk.Frame(top)
            zucker_frame.grid(row=5, column=1, sticky="w", padx=6, pady=6)
            self.zucker_entry = DateEntry(
                zucker_frame, textvariable=self.zucker_var, width=16,
                date_pattern="dd.MM.yyyy", locale="de_DE"
            )
            self.zucker_entry.pack(side="left")
            self.zucker_var.set("")
            self.zucker_entry.delete(0, "end")
        else:
            self.zucker_entry = ttk.Entry(top, textvariable=self.zucker_var, width=30)
            self.zucker_entry.grid(row=5, column=1, sticky="w", padx=6, pady=6)
            ttk.Label(top, text="(tkcalendar nicht installiert – manuelle Eingabe)", foreground="gray").grid(
                row=5, column=2, sticky="w", padx=4, pady=6)

        # NEU: Fluss Inlet I und II
        ttk.Label(top, text="Fluss Inlet I (l/min):").grid(row=6, column=0, sticky="w", padx=6, pady=6)
        self.fluss_inlet1_var = tk.StringVar()
        self.fluss_inlet1_entry = ttk.Entry(top, textvariable=self.fluss_inlet1_var, width=30)
        self.fluss_inlet1_entry.grid(row=6, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(top, text="Fluss Inlet II (l/min):").grid(row=7, column=0, sticky="w", padx=6, pady=6)
        self.fluss_inlet2_var = tk.StringVar()
        self.fluss_inlet2_entry = ttk.Entry(top, textvariable=self.fluss_inlet2_var, width=30)
        self.fluss_inlet2_entry.grid(row=7, column=1, sticky="w", padx=6, pady=6)

        # ---------- Nulltest ----------
        nt = ttk.LabelFrame(root, text="Nulltest")
        nt.pack(fill="x", padx=0, pady=(0, 10))
        nt.columnconfigure(1, weight=1)

        nt_btns = ttk.Frame(nt)
        nt_btns.grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(8, 4))
        self.nt_start_btn = ttk.Button(nt_btns, text="Nulltest starten", command=self.nt_start)
        self.nt_start_btn.pack(side="left", padx=(0, 6))
        self.nt_skip_btn = ttk.Button(nt_btns, text="Nulltest überspringen", command=self.nt_skip)
        self.nt_skip_btn.pack(side="left", padx=6)
        self.nt_reset_btn = ttk.Button(nt_btns, text="Timer zurücksetzen", command=self.nt_reset, state="disabled")
        self.nt_reset_btn.pack(side="left", padx=6)

        # NEU: Startzeit konfigurieren
        self.nt_cfg_btn = ttk.Button(nt_btns, text="⏱ Startzeit …", command=self._nt_configure_time)
        self.nt_cfg_btn.pack(side="left", padx=(18, 6))

        self.nt_ext2_btn = ttk.Button(nt_btns, text="+2 min", command=lambda: self.nt_extend(2 * 60), state="disabled")
        self.nt_ext2_btn.pack(side="left", padx=(6, 6))
        self.nt_ext5_btn = ttk.Button(nt_btns, text="+5 min", command=lambda: self.nt_extend(5 * 60), state="disabled")
        self.nt_ext5_btn.pack(side="left", padx=6)

        ttk.Label(nt, text="Restzeit:").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        self.nt_time_var = tk.StringVar(value=self._fmt(self.nt_remaining))
        ttk.Label(nt, textvariable=self.nt_time_var, font=("TkDefaultFont", 11, "bold")).grid(row=1, column=1, sticky="w", padx=6, pady=6)

        self.nt_pb = ttk.Progressbar(nt, mode="determinate", maximum=self.nt_total, length=560)
        self.nt_pb.grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 10))
        self.nt_pb["value"] = 0

        ttk.Label(nt, text="Nulltest Ende/Status:").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        self.nt_end_var = tk.StringVar(value="")
        ttk.Entry(nt, textvariable=self.nt_end_var, state="readonly").grid(row=3, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(nt, text="Eisbildung (Nulltest):").grid(row=4, column=0, sticky="w", padx=6, pady=(0, 8))
        self.nt_eis_var = tk.StringVar(value="")
        ttk.Entry(nt, textvariable=self.nt_eis_var, state="readonly").grid(row=4, column=1, sticky="ew", padx=6, pady=(0, 8))

        # ---------- Echte Messung ----------
        ms_bg = tk.Frame(root, bg="#eaf6ff", bd=0, highlightthickness=0)
        ms_bg.pack(fill="x", padx=0, pady=(0, 10))
        self.ms_section = ms_bg

        ms = ttk.LabelFrame(ms_bg, text="Echte Messung")
        ms.pack(fill="x", padx=8, pady=8)
        ms.columnconfigure(1, weight=1)

        tk.Label(ms, text="Dieser Bereich erscheint nach abgeschlossenem Nulltest (oder wenn Nulltest übersprungen wurde).",
                 bg="#eaf6ff").grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 0))

        ms_btns = ttk.Frame(ms)
        ms_btns.grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(8, 4))
        self.ms_start_btn = ttk.Button(ms_btns, text="Messung starten", command=self.ms_start, state="disabled")
        self.ms_start_btn.pack(side="left", padx=(0, 6))
        self.ms_reset_btn = ttk.Button(ms_btns, text="Timer zurücksetzen", command=self.ms_reset, state="disabled")
        self.ms_reset_btn.pack(side="left", padx=6)

        # NEU: Startzeit konfigurieren
        self.ms_cfg_btn = ttk.Button(ms_btns, text="⏱ Startzeit …", command=self._ms_configure_time)
        self.ms_cfg_btn.pack(side="left", padx=(18, 6))

        self.ms_ext2_btn = ttk.Button(ms_btns, text="+2 min", command=lambda: self.ms_extend(2 * 60), state="disabled")
        self.ms_ext2_btn.pack(side="left", padx=(6, 6))
        self.ms_ext5_btn = ttk.Button(ms_btns, text="+5 min", command=lambda: self.ms_extend(5 * 60), state="disabled")
        self.ms_ext5_btn.pack(side="left", padx=6)
        self.ms_stop_btn = ttk.Button(ms_btns, text="⏹ Messung stoppen", command=self.ms_stop, state="disabled")
        self.ms_stop_btn.pack(side="left", padx=(18, 6))

        ttk.Label(ms, text="Restzeit:").grid(row=2, column=0, sticky="w", padx=6, pady=6)
        self.ms_time_var = tk.StringVar(value=self._fmt(self.ms_remaining))
        ttk.Label(ms, textvariable=self.ms_time_var, font=("TkDefaultFont", 11, "bold")).grid(row=2, column=1, sticky="w", padx=6, pady=6)
        self.ms_pb = ttk.Progressbar(ms, mode="determinate", maximum=self.ms_total, length=560)
        self.ms_pb.grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 10))
        self.ms_pb["value"] = 0

        ttk.Label(ms, text="Messung Start:").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        self.ms_start_var = tk.StringVar(value="")
        ttk.Entry(ms, textvariable=self.ms_start_var, state="readonly").grid(row=4, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(ms, text="Messung Ende:").grid(row=5, column=0, sticky="w", padx=6, pady=4)
        self.ms_end_var = tk.StringVar(value="")
        ttk.Entry(ms, textvariable=self.ms_end_var, state="readonly").grid(row=5, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(ms, text="Eis vorhanden (Messung):").grid(row=6, column=0, sticky="w", padx=6, pady=4)
        self.ms_eis_var = tk.StringVar(value="")
        ttk.Entry(ms, textvariable=self.ms_eis_var, state="readonly").grid(row=6, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(ms, text="Kristalle (Anzahl oder 'k.A.'):").grid(row=7, column=0, sticky="w", padx=6, pady=(4, 6))
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
        row7.grid(row=7, column=1, sticky="w", padx=6, pady=(4, 6))
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

        ttk.Label(ms, text="Art des Wachstums:").grid(row=8, column=0, sticky="w", padx=6, pady=(0, 10))
        self.ms_wachstum_var = tk.StringVar(value="")
        self.ms_wachstum_cb = ttk.Combobox(
            ms, textvariable=self.ms_wachstum_var,
            values=["dry", "wet", "transitional", "k.A."],
            state="disabled", width=18
        )
        self.ms_wachstum_cb.grid(row=8, column=1, sticky="w", padx=6, pady=(0, 10))

        # Statuszeile
        ttk.Separator(root, orient="horizontal").pack(fill="x", pady=(4, 4))

        bottom = ttk.Frame(root)
        bottom.pack(fill="x")

        self.status_var = tk.StringVar(value="Bereit.")
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left", anchor="w")

        self.new_measurement_btn = ttk.Button(
            bottom,
            text="Neue Messung beginnen",
            command=self.new_measurement,
            state="disabled"
        )
        self.new_measurement_btn.pack(side="right")

    # ---------- Hilfsmethoden ----------
    def _lock_inputs(self, lock: bool):
        state = "disabled" if lock else "normal"
        for e in (self.target_entry, self.fp_ic_entry, self.fp_inlet1_entry, self.fp_inlet2_entry,
                  self.zucker_entry, self.fluss_inlet1_entry, self.fluss_inlet2_entry):
            e.configure(state=state)

    @staticmethod
    def _fmt(seconds: int) -> str:
        m, s = divmod(max(0, int(seconds)), 60)
        return f"{m:02d}:{s:02d}"

    # ---------- Startzeit-Konfiguration ----------
    def _nt_configure_time(self):
        """Startdauer für Nulltest konfigurieren (nur vor dem Start möglich)."""
        if self.nt_timer_running:
            messagebox.showwarning("Nicht möglich", "Nulltest läuft bereits. Timer zurücksetzen, um die Startzeit zu ändern.")
            return
        new_secs = ask_initial_seconds(self, "Nulltest – Startzeit", self.nt_initial)
        self.nt_initial = new_secs
        self.nt_total = new_secs
        self.nt_remaining = new_secs
        self.nt_pb["maximum"] = new_secs
        self.nt_pb["value"] = 0
        self.nt_time_var.set(self._fmt(new_secs))
        self.status_var.set(f"Nulltest-Startzeit gesetzt: {new_secs // 60} min")

    def _ms_configure_time(self):
        """Startdauer für Messung konfigurieren (nur vor dem Start möglich)."""
        if self.ms_timer_running:
            messagebox.showwarning("Nicht möglich", "Messung läuft bereits. Timer zurücksetzen, um die Startzeit zu ändern.")
            return
        new_secs = ask_initial_seconds(self, "Messung – Startzeit", self.ms_initial)
        self.ms_initial = new_secs
        self.ms_total = new_secs
        self.ms_remaining = new_secs
        self.ms_pb["maximum"] = new_secs
        self.ms_pb["value"] = 0
        self.ms_time_var.set(self._fmt(new_secs))
        self.status_var.set(f"Messung-Startzeit gesetzt: {new_secs // 60} min")

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
        if not TAGESMODUS:
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
        self.nt_cfg_btn.configure(state="disabled")
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
        self.status_var.set(f"Nulltest verlängert um {seconds // 60} min – Rest {self._fmt(self.nt_remaining)}")

    def nt_reset(self):
        if self.nt_after_job is not None:
            self.after_cancel(self.nt_after_job)
            self.nt_after_job = None
        self.nt_timer_running = False
        self.nt_total = self.nt_initial
        self.nt_remaining = self.nt_initial
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
        self.nt_cfg_btn.configure(state="normal")
        if not TAGESMODUS:
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

        if self.nt_eisbildung == "Ja":
            # Nulltest positiv → Messung wird NICHT durchgeführt, direkt weiter
            self.status_var.set("Nulltest positiv (Eisbildung). Neue Messung kann gestartet werden.")
            messagebox.showinfo(
                "Nulltest positiv",
                "Eisbildung festgestellt – die echte Messung entfällt für diesen Target.\n"
                "Bitte mit 'Neue Messung beginnen' zur nächsten Target-Nr. wechseln."
            )
            self.new_measurement_btn.configure(state="normal")
            # Trotzdem Nulltest-Daten ohne Messung speichern
            self._save_nulltest_only()
        else:
            self.status_var.set("Nulltest negativ. Echte Messung kann gestartet werden.")
            self.ms_start_btn.configure(state="normal")

    def _save_nulltest_only(self):
        """Speichert einen Datensatz mit Nulltest-Ergebnis, aber ohne Messung."""
        row = {
            "timestamp_start": self.start_timestamp,
            "target_nr": self.target_var.get(),
            "frostpunkt_ic": self.fp_ic_var.get(),
            "frostpunkt_inlet_i": self.fp_inlet1_var.get(),
            "frostpunkt_inlet_ii": self.fp_inlet2_var.get(),
            "herstellungsdatum_zuckerlosung": self.zucker_var.get(),
            "fluss_inlet_i": self.fluss_inlet1_var.get(),
            "fluss_inlet_ii": self.fluss_inlet2_var.get(),
            "nulltest_skipped": "Nein",
            "nulltest_skip_ts": "",
            "nulltest_end": self.nulltest_end_ts,
            "nulltest_eisbildung": self.nt_eisbildung,
            "nulltest_total_seconds": self.nt_initial,
            "nulltest_extended_seconds": self.nt_total - self.nt_initial,
            "messung_start": "",
            "messung_end": "",
            "messung_eis_vorhanden": "",
            "messung_kristalle": "",
            "messung_kristalle_code": "",
            "messung_wachstum": "",
            "messung_total_seconds": "",
            "messung_extended_seconds": "",
            "messung_abgebrochen": "",
        }
        write_csv_row_to_target(row, self.target_var.get())

    def _enable_nt_controls(self, running: bool):
        self.nt_start_btn.configure(state="disabled" if running else "normal")
        self.nt_reset_btn.configure(state="normal" if running else "disabled")
        self.nt_ext2_btn.configure(state="normal" if running else "disabled")
        self.nt_ext5_btn.configure(state="normal" if running else "disabled")
        self.nt_cfg_btn.configure(state="disabled" if running else "normal")
        self.nt_skip_btn.configure(state="disabled" if running or self.nulltest_skipped else "normal")

    # ---------- Messung Methoden ----------
    def ms_start(self):
        if self.ms_timer_running:
            return
        self.messung_start_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.ms_start_var.set(self.messung_start_ts)

        self.ms_timer_running = True
        self.ms_total = self.ms_initial
        self.ms_remaining = self.ms_initial
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
        self.status_var.set(f"Messung verlängert um {seconds // 60} min – Rest {self._fmt(self.ms_remaining)}")

    def ms_stop(self):
        """Messung vorzeitig stoppen."""
        if not self.ms_timer_running:
            return
        if not messagebox.askyesno("Messung stoppen", "Messung wirklich vorzeitig stoppen?"):
            return
        if self.ms_after_job is not None:
            self.after_cancel(self.ms_after_job)
            self.ms_after_job = None
        self.ms_timer_running = False
        self.ms_abgebrochen = True
        self._ms_finish(abgebrochen=True)

    def ms_reset(self):
        if self.ms_after_job is not None:
            self.after_cancel(self.ms_after_job)
            self.ms_after_job = None
        self.ms_timer_running = False
        self.ms_total = self.ms_initial
        self.ms_remaining = self.ms_initial
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
        self.ms_stop_btn.configure(state=state)
        self.ms_kristalle_entry.configure(state=state)
        self.ms_kristalle_confirm.configure(state=state)
        self.ms_wachstum_cb.configure(state="readonly" if running else "disabled")
        self.ms_cfg_btn.configure(state="disabled" if running else "normal")
        self.ms_start_btn.configure(state="disabled" if running else "normal")

    def _reset_measurement_ui(self, full=False):
        self.ms_start_var.set("")
        self.ms_end_var.set("")
        self.ms_eis_var.set("")
        self.ms_kristalle_var.set("")
        self.ms_wachstum_var.set("")
        self.ms_abgebrochen = False
        if full:
            self.ms_start_btn.configure(state="disabled")

    def _ms_finish(self, abgebrochen=False):
        if self.ms_after_job is not None:
            self.after_cancel(self.ms_after_job)
            self.ms_after_job = None
        self.ms_timer_running = False
        self.messung_end_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.ms_end_var.set(self.messung_end_ts)

        eis_jn = messagebox.askyesno("Eis vorhanden?", "Eis vorhanden (Messung)?")
        self.ms_eis = "Ja" if eis_jn else "Nein"
        self.ms_eis_var.set(self.ms_eis)
        if abgebrochen:
            self.status_var.set("Messung vorzeitig gestoppt. Kristalle erfassen und speichern.")
        else:
            self.status_var.set("Messung beendet. Kristalle erfassen und speichern.")

    def _confirm_kristalle(self):
        k = self.ms_kristalle_var.get().strip()
        if not k:
            messagebox.showwarning("Eingabe fehlt", "Bitte Anzahl der Kristalle eingeben oder 'k.A.'")
            return
        w = self.ms_wachstum_var.get().strip()
        if not w:
            messagebox.showwarning("Eingabe fehlt", "Bitte Art des Wachstums auswählen.")
            return
        code = 1 if k.lower() == "k.a." else 0
        self._finalize_and_save(kristalle=k, kristalle_code=code, wachstum=w)
        self.ms_kristalle_entry.configure(state="disabled")
        self.ms_kristalle_confirm.configure(state="disabled")
        self.ms_wachstum_cb.configure(state="disabled")
        self.status_var.set("Daten gespeichert.")
        self.new_measurement_btn.configure(state="normal")

    def _finalize_and_save(self, kristalle, kristalle_code, wachstum=""):
        abgebrochen = getattr(self, "ms_abgebrochen", False)
        row = {
            "timestamp_start": self.start_timestamp,
            "target_nr": self.target_var.get(),
            "frostpunkt_ic": self.fp_ic_var.get(),
            "frostpunkt_inlet_i": self.fp_inlet1_var.get(),
            "frostpunkt_inlet_ii": self.fp_inlet2_var.get(),
            "herstellungsdatum_zuckerlosung": self.zucker_var.get(),
            "fluss_inlet_i": self.fluss_inlet1_var.get(),
            "fluss_inlet_ii": self.fluss_inlet2_var.get(),
            "nulltest_skipped": "Ja" if self.nulltest_skipped else "Nein",
            "nulltest_skip_ts": self.nulltest_skip_ts,
            "nulltest_end": self.nulltest_end_ts,
            "nulltest_eisbildung": self.nt_eisbildung,
            "nulltest_total_seconds": self.nt_initial,
            "nulltest_extended_seconds": self.nt_total - self.nt_initial,
            "messung_start": self.messung_start_ts,
            "messung_end": self.messung_end_ts,
            "messung_eis_vorhanden": self.ms_eis,
            "messung_kristalle": kristalle,
            "messung_kristalle_code": kristalle_code,
            "messung_wachstum": wachstum,
            "messung_total_seconds": self.ms_initial,
            "messung_extended_seconds": self.ms_total - self.ms_initial,
            "messung_abgebrochen": "Ja" if abgebrochen else "Nein",
        }
        write_csv_row_to_target(row, self.target_var.get())

    def new_measurement(self):
        """Startet eine neue Messung mit übernommenen Stammdaten."""
        target = self.target_var.get().strip()
        try:
            num = int(target)
            self.target_var.set(str(num + 1))
        except Exception:
            pass

        self.start_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.ts_var.set(self.start_timestamp)

        # Nulltest Reset
        self.nt_total = self.nt_initial
        self.nt_remaining = self.nt_initial
        self.nt_pb["value"] = 0
        self.nt_pb["maximum"] = self.nt_initial
        self.nt_time_var.set(self._fmt(self.nt_remaining))
        self.nt_end_var.set("")
        self.nt_eis_var.set("")
        self.nulltest_end_ts = None
        self.nt_eisbildung = None
        self.nulltest_skipped = False
        self.nulltest_skip_ts = None
        self._enable_nt_controls(running=False)
        self.nt_skip_btn.configure(state="normal")
        self.nt_cfg_btn.configure(state="normal")

        # Messung Reset
        self.ms_reset()
        self.ms_start_btn.configure(state="disabled")

        self.new_measurement_btn.configure(state="disabled")
        self.status_var.set("Neue Messung bereit.")


# ---------- App starten ----------
if __name__ == "__main__":
    app = App()
    app.mainloop()
