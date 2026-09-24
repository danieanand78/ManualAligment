#!/usr/bin/env python3
"""
Audio-Text Manual Aligner (PRO VERSION)
"""

import os
import json
import csv
import threading
import time
import subprocess
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

import numpy as np
from pydub import AudioSegment, effects
from PIL import Image, ImageTk
from scipy import signal
from scipy.io import wavfile
import rebuild_dataset

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
AUDIO_DIR  = BASE_DIR / "audio"
TEXT_DIR   = BASE_DIR / "text"
OUTPUT_DIR = BASE_DIR / "dataset"

OUTPUT_DIR.mkdir(exist_ok=True)
(OUTPUT_DIR / "wavs").mkdir(exist_ok=True)

METADATA_FILE = OUTPUT_DIR / "metadata.csv"
HISTORY_DIR   = OUTPUT_DIR / "history"
HISTORY_DIR.mkdir(exist_ok=True)
USER_CONFIG_FILE = BASE_DIR / "user_config.json"

# Couleurs
BG        = "#0f1117"
BG2       = "#1a1d27"
BG3       = "#252836"
ACCENT    = "#6c63ff"
IN_PROGRESS = "#3498db"
SUCCESS   = "#2ecc71"
ACCENT2   = "#ff6584"
WARNING   = "#f9ca24"
TEXT_COL  = "#e8e8f0"
TEXT_MUTED= "#8888aa"
WAVEFORM  = "#6c63ff"
SILENCE_BG= "#1c2e2e"
MARKER_START = "#43e97b"
MARKER_END   = "#f9ca24"

# Détection du player
def get_player_cmd(file_path, speed=1.0):
    is_win = (os.name == "nt")
    for cmd in ["ffplay", "paplay", "aplay"]:
        try:
            if cmd == "ffplay":
                subprocess.run(["ffplay", "-version"], capture_output=True, shell=is_win)
                return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-af", f"atempo={speed}", str(file_path)]
            if speed == 1.0:
                return [cmd, str(file_path)]
        except: continue
    return None

# ─────────────────────────────────────────────
#  Canvas Waveform
# ─────────────────────────────────────────────
class WaveformCanvas(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, bg=BG3, highlightthickness=0, takefocus=1, **kw)
        self.samples   = None
        self.duration  = 1.0
        self.start_s   = 0.0
        self.end_s     = 1.0
        self.playhead  = 0.0
        self.view_start = 0.0
        self.view_end   = 1.0
        self.show_spectro = tk.BooleanVar(value=False)
        self.spectro_img = None
        self._drag     = None
        self._last_x   = 0
        self.saved_spans = []
        self.silences = []

        self.bind("<Configure>",        lambda e: self.draw())
        self.bind("<ButtonPress-1>",    self._on_press)
        self.bind("<B1-Motion>",        self._on_drag)
        self.bind("<ButtonRelease-1>",  self._on_release)
        self.bind("<Button-4>",         self._on_zoom_in)
        self.bind("<Button-5>",         self._on_zoom_out)
        self.bind("<ButtonPress-3>",    self._start_pan)
        self.bind("<B3-Motion>",        self._do_pan)

        self._callbacks = {"change": []}
        self.on_scroll_update = None

    def on_change(self, fn): self._callbacks["change"].append(fn)

    def load(self, samples, duration):
        self.samples = samples
        self.duration = duration
        self.view_start = 0.0
        self.view_end = min(10.0, duration)
        self.start_s = 0.0
        self.end_s = min(5.0, duration)
        self._find_silences()
        self.draw()

    def _find_silences(self):
        if self.samples is None: return
        self.silences = []
        energy = self.samples**2
        win = 800
        avg_energy = np.convolve(energy, np.ones(win)/win, mode='same')
        threshold = np.percentile(avg_energy, 10) * 1.5
        is_silence = avg_energy < threshold
        
        diff = np.diff(is_silence.astype(int))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        
        for s, e in zip(starts, ends):
            t_s, t_e = s/8000.0, e/8000.0
            if t_e - t_s > 0.1: self.silences.append((t_s, t_e))

    def set_playhead(self, t):
        self.playhead = t
        self.draw_playhead()

    def draw(self):
        self.delete("all")
        if self.samples is None: return
        w, h = self.winfo_width(), self.winfo_height()
        
        # Silences
        for s, e in self.silences:
            if e < self.view_start or s > self.view_end: continue
            x1 = (s - self.view_start) / (self.view_end - self.view_start) * w
            x2 = (e - self.view_start) / (self.view_end - self.view_start) * w
            self.create_rectangle(x1, 0, x2, h, fill=SILENCE_BG, outline="")

        # Wave
        s_idx = int(self.view_start * 8000)
        e_idx = int(self.view_end * 8000)
        visible = self.samples[s_idx:e_idx]
        if len(visible) > 0:
            step = max(1, len(visible) // w)
            points = []
            for i in range(0, len(visible), step):
                chunk = visible[i:i+step]
                v_max = np.max(chunk) * (h/2)
                v_min = np.min(chunk) * (h/2)
                x = (i / len(visible)) * w
                points.extend([x, h/2 - v_max, x, h/2 - v_min])
            self.create_line(points, fill=WAVEFORM)

        # Saved Spans
        for s, e in self.saved_spans:
            x1 = (s - self.view_start) / (self.view_end - self.view_start) * w
            x2 = (e - self.view_start) / (self.view_end - self.view_start) * w
            self.create_rectangle(x1, h-5, x2, h, fill=SUCCESS, outline="")

        # Selection
        x_s = (self.start_s - self.view_start) / (self.view_end - self.view_start) * w
        x_e = (self.end_s - self.view_start) / (self.view_end - self.view_start) * w
        self.create_rectangle(x_s, 0, x_e, h, fill=ACCENT, stipple="gray25", outline=ACCENT)
        self.create_line(x_s, 0, x_s, h, fill=MARKER_START, width=2)
        self.create_line(x_e, 0, x_e, h, fill=MARKER_END, width=2)
        
        self.draw_playhead()

    def draw_playhead(self):
        self.delete("playhead")
        w = self.winfo_width()
        x = (self.playhead - self.view_start) / (self.view_end - self.view_start) * w
        self.create_line(x, 0, x, self.winfo_height(), fill="white", width=1, tags="playhead")

    # Events logic
    def _on_press(self, e):
        w = self.winfo_width()
        t = self.view_start + (e.x / w) * (self.view_end - self.view_start)
        if abs(t - self.start_s) < abs(t - self.end_s): self._drag = "start"
        else: self._drag = "end"
        self._last_x = e.x

    def _on_drag(self, e):
        w = self.winfo_width()
        t = self.view_start + (e.x / w) * (self.view_end - self.view_start)
        t = max(0, min(t, self.duration))
        if self._drag == "start": self.start_s = min(t, self.end_s - 0.01)
        else: self.end_s = max(t, self.start_s + 0.01)
        self.draw()
        for fn in self._callbacks["change"]: fn(self.start_s, self.end_s)

    def _on_release(self, e): self._drag = None

    def _on_zoom_in(self, e): self._zoom(0.7, e.x)
    def _on_zoom_out(self, e): self._zoom(1.4, e.x)
    def _zoom(self, ratio, x):
        w = self.winfo_width()
        cursor_t = self.view_start + (x / w) * (self.view_end - self.view_start)
        new_dur = (self.view_end - self.view_start) * ratio
        new_dur = max(0.2, min(new_dur, self.duration))
        self.view_start = max(0, cursor_t - new_dur * (x/w))
        self.view_end = min(self.duration, self.view_start + new_dur)
        self.draw()
        if self.on_scroll_update: self.on_scroll_update()

    def _start_pan(self, e): self._last_x = e.x
    def _do_pan(self, e):
        w = self.winfo_width()
        dt = (self._last_x - e.x) / w * (self.view_end - self.view_start)
        if self.view_start + dt >= 0 and self.view_end + dt <= self.duration:
            self.view_start += dt
            self.view_end += dt
            self._last_x = e.x
            self.draw()
            if self.on_scroll_update: self.on_scroll_update()

# ─────────────────────────────────────────────
#  Application PRO
# ─────────────────────────────────────────────
class AlignerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Malagasy Audio-Text Manual Aligner (PRO)")
        self.geometry("1150x850")
        self.configure(bg=BG)
        
        self.user_name = self._get_user_name()
        self.pairs = self._collect_pairs()
        self.current_idx = 0
        self.history = self._load_history()
        self.existing_texts = self._load_existing_texts()
        self.plan = self._load_plan()
        
        self.player_proc = None
        self.is_playing = False
        self.speed = 1.0
        self.total_processed_sec = self._get_total_duration()

        self._build_ui()
        if self.pairs: self._load_pair(0)
        self._tick()

    def _get_user_name(self):
        if USER_CONFIG_FILE.exists():
            with open(USER_CONFIG_FILE) as f:
                return json.load(f).get("name", "user")
        from tkinter import simpledialog
        name = simpledialog.askstring("Collaborateur", "Entrez votre nom (ex: TOVO) :", parent=self)
        if not name: name = "user"
        name = "".join(c for c in name if c.isalnum())
        with open(USER_CONFIG_FILE, "w") as f:
            json.dump({"name": name}, f)
        return name

    def _change_user(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("Collaborateur", f"Nom actuel : {self.user_name}\nNouveau nom :", parent=self)
        if name:
            self.user_name = "".join(c for c in name if c.isalnum())
            with open(USER_CONFIG_FILE, "w") as f:
                json.dump({"name": self.user_name}, f)
            messagebox.showinfo("Profil", f"Nom changé en : {self.user_name}")
            self._reload_all_data()

    def _collect_pairs(self):
        pairs = []
        for ap in sorted(AUDIO_DIR.rglob("*.mp3")):
            tp = TEXT_DIR / ap.relative_to(AUDIO_DIR).with_suffix(".txt")
            if tp.exists(): pairs.append((ap, tp))
        return pairs

    def _load_history(self):
        history = {"completed_tasks": [], "stats": {}}
        for f in HISTORY_DIR.glob("*.json"):
            try:
                stem = f.stem
                if stem.startswith("success_tasks"): continue
                
                parts = stem.split("___")
                if len(parts) < 2: continue
                user = parts[-1]
                
                # Stats par personne
                if user not in history["stats"]:
                    history["stats"][user] = {"count": 0, "duration": 0.0}

                if stem.startswith("completed_tasks"):
                    with open(f, encoding="utf-8") as jf:
                        data = json.load(jf)
                        history["completed_tasks"] = list(set(history["completed_tasks"] + data))
                    continue

                key = "/".join(parts[:-1]).replace(".mp3", "") + ".mp3"
                with open(f, encoding="utf-8") as jf:
                    data = json.load(jf)
                    if key not in history: history[key] = {"segments": [], "finished": False}
                    
                    inc = data if isinstance(data, list) else data.get("segments", [])
                    history[key]["segments"].extend(inc)
                    
                    # Accumulation des stats
                    for s in inc:
                        history["stats"][user]["count"] += 1
                        history["stats"][user]["duration"] += (s["end"] - s["start"])
                    
                    if not isinstance(data, list) and data.get("finished"): 
                        history[key]["finished"] = True
            except: pass
        return history

    def _load_existing_texts(self):
        texts = set()
        if METADATA_FILE.exists():
            with open(METADATA_FILE, encoding="utf-8") as f:
                reader = csv.reader(f, delimiter="|")
                for row in reader:
                    if len(row) > 1: texts.add(row[1].strip().rstrip('.'))
        return texts

    def _load_plan(self):
        plan_path = OUTPUT_DIR / "optimization_plan.json"
        if plan_path.exists():
            with open(plan_path) as f: return json.load(f)
        return []

    def _get_total_duration(self):
        total = 0.0
        wavs_dir = OUTPUT_DIR / "wavs"
        for f in wavs_dir.glob("*.wav"):
            try: total += AudioSegment.from_file(str(f)).duration_seconds
            except: pass
        return total

    def _build_ui(self):
        paned = tk.PanedWindow(self, orient="horizontal", bg=BG, borderwidth=0)
        paned.pack(fill="both", expand=True)

        left = tk.Frame(paned, bg=BG2, width=300)
        paned.add(left)
        
        tabs = ttk.Notebook(left)
        tabs.pack(fill="both", expand=True)

        # Tab: Fichiers
        f_tab = tk.Frame(tabs, bg=BG2)
        tabs.add(f_tab, text="📂 Fichiers")
        self.listbox = tk.Listbox(f_tab, bg=BG3, fg=TEXT_COL, selectbackground=ACCENT, exportselection=0)
        self.listbox.pack(fill="both", expand=True)
        self._refresh_list()
        self.listbox.bind("<<ListboxSelect>>", self._on_list_click)

        # Tab: Plan (Hierarchique)
        p_tab = tk.Frame(tabs, bg=BG2)
        tabs.add(p_tab, text="🎯 Plan 2h")
        self.plan_tree = ttk.Treeview(p_tab, show="tree", selectmode="browse")
        self.plan_tree.pack(fill="both", expand=True)
        sc = ttk.Scrollbar(p_tab, orient="vertical", command=self.plan_tree.yview)
        sc.pack(side="right", fill="y")
        self.plan_tree.configure(yscrollcommand=sc.set)
        
        tk.Button(p_tab, text="✅ Fini", command=self._mark_task_done, bg=BG3, fg=SUCCESS).pack(fill="x")
        self.plan_tree.bind("<<TreeviewSelect>>", self._on_plan_click)
        self._refresh_plan_list()

        # Tab 3: Team Stats (Nouveau)
        t_tab = tk.Frame(tabs, bg=BG2)
        tabs.add(t_tab, text="👥 Équipe")
        self.stats_list = tk.Listbox(t_tab, bg=BG3, fg=TEXT_COL, font=("Arial", 10), borderwidth=0)
        self.stats_list.pack(fill="both", expand=True, padx=5, pady=5)
        self._refresh_stats()

        # Center
        mid = tk.Frame(paned, bg=BG)
        paned.add(mid)
        
        # Header
        self.lbl_info = tk.Label(mid, text="Malagasy Aligner PRO", fg=ACCENT, bg=BG, font=("Arial", 12, "bold"))
        self.lbl_info.pack(pady=5)
        
        # Toolbar
        tool = tk.Frame(mid, bg=BG)
        tool.pack(fill="x", padx=10)
        tk.Button(tool, text="🔄 Sync Git", command=self._reload_all_data, bg=BG3, fg=ACCENT).pack(side="left", padx=5)
        tk.Button(tool, text="🚀 Push Git", command=self._git_push, bg=BG3, fg=MARKER_START).pack(side="left", padx=5)
        tk.Button(tool, text="👤 Nom", command=self._change_user, bg=BG3, fg=TEXT_MUTED).pack(side="left", padx=5)
        tk.Button(tool, text="🏁 Terminer Chap.", command=self._mark_finished, bg=BG3, fg=SUCCESS).pack(side="left", padx=5)
        tk.Button(tool, text="⤺ Annuler", command=self._undo, bg=BG3, fg=ACCENT2).pack(side="right", padx=5)

        # Waveform
        wf_frame = tk.Frame(mid, bg=BG)
        wf_frame.pack(fill="x", padx=10, pady=5)
        self.wave = WaveformCanvas(wf_frame, height=180)
        self.wave.pack(fill="x")
        self.wave.on_change(self._on_wave_change)
        self.scroll = tk.Scrollbar(wf_frame, orient="horizontal", command=self._on_scroll)
        self.scroll.pack(fill="x")
        self.wave.on_scroll_update = self._update_scrollbar
        
        # Controls
        ctrl = tk.Frame(mid, bg=BG)
        ctrl.pack(fill="x", padx=10)
        tk.Button(ctrl, text="▶ JOUER (Espace)", command=self._play_selection, bg=ACCENT, fg="white", font=("Arial", 10, "bold")).pack(side="left", padx=5)
        tk.Button(ctrl, text="⏹ STOP", command=self._stop_audio, bg=BG3, fg="white").pack(side="left", padx=5)
        tk.Button(ctrl, text="✅ SAUVER (Entrée)", command=self._save, bg=SUCCESS, fg="black", font=("Arial", 10, "bold")).pack(side="left", padx=10)
        self.lbl_sel = tk.Label(ctrl, text="0.00s", fg=WARNING, bg=BG)
        self.lbl_sel.pack(side="right")
        
        # BARRE DE RECHERCHE (Nouveau)
        s_bar = tk.Frame(mid, bg=BG)
        s_bar.pack(fill="x", padx=10, pady=2)
        tk.Label(s_bar, text="🔍 Chercher :", fg=TEXT_MUTED, bg=BG).pack(side="left")
        self.ent_search = tk.Entry(s_bar, bg=BG3, fg=TEXT_COL, insertbackground="white")
        self.ent_search.pack(side="left", fill="x", expand=True, padx=5)
        self.ent_search.bind("<KeyRelease>", lambda e: self._search_text())
        
        # Text Area
        tk.Label(mid, text="Texte :", fg=TEXT_MUTED, bg=BG).pack(anchor="w", padx=10)
        self.txt_area = tk.Text(mid, bg=BG3, fg=TEXT_COL, font=("Arial", 12), wrap="word")
        self.txt_area.pack(fill="both", expand=True, padx=10, pady=5)
        self.txt_area.tag_configure("saved", overstrike=True, foreground="#555")
        self.txt_area.tag_configure("suggestion", background="#1b5e20", foreground="white")
        self.txt_area.tag_configure("search", background="yellow", foreground="black")
        # Priorité : La sélection souris doit être au-dessus du vert
        self.txt_area.tag_lower("suggestion")

        # Progress
        self.progress_bar = ttk.Progressbar(self, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", side="bottom")
        self.lbl_total_time = tk.Label(self, text="00:00:00 / 02:00:00", bg=BG2, fg=TEXT_COL)
        self.lbl_total_time.pack(side="bottom", pady=2)
        self._update_total_time_label()

        # Keybinds
        self.bind("<space>", lambda e: self._toggle_play())
        self.bind("<Return>", lambda e: self._save())
        self.bind("<q>", lambda e: self._nudge("start", -0.05))
        self.bind("<w>", lambda e: self._nudge("start", 0.05))
        self.bind("<e>", lambda e: self._nudge("end", -0.05))
        self.bind("<r>", lambda e: self._nudge("end", 0.05))

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for i, (ap, _) in enumerate(self.pairs):
            key = str(ap.relative_to(AUDIO_DIR))
            is_finished = self.history.get(key, {}).get("finished", False)
            has_started = len(self.history.get(key, {}).get("segments", [])) > 0
            self.listbox.insert("end", ap.name)
            if is_finished: self.listbox.itemconfig(i, fg=SUCCESS)
            elif has_started: self.listbox.itemconfig(i, fg=IN_PROGRESS)

    def _refresh_plan_list(self):
        if not hasattr(self, "plan_tree"): return
        
        # --- NOUVEAU : Mémoriser quels livres étaient OUVERTS ---
        opened_books = []
        for node in self.plan_tree.get_children(""):
            if self.plan_tree.item(node, "open"):
                # On stocke le nom du livre (sans l'icône)
                text = self.plan_tree.item(node, "text")
                clean_name = text.replace("✅ ", "").replace("📁 ", "").strip()
                opened_books.append(clean_name)

        for n in self.plan_tree.get_children(): self.plan_tree.delete(n)
        comp = self.history.get("completed_tasks", [])
        groups = {}
        for i, item in enumerate(self.plan):
            bk = Path(item["path"]).parent.name
            if bk not in groups: groups[bk] = []
            groups[bk].append((i, item))
        
        # Styles pour les dossiers
        self.plan_tree.tag_configure("done", foreground=SUCCESS)
        self.plan_tree.tag_configure("in_progress", foreground=IN_PROGRESS)
        
        for bk, items in groups.items():
            # On vérifie l'état d'avancement
            all_done = True
            any_done = False
            item_nodes = []
            
            for idx, item in items:
                task_name = Path(item['path']).name
                task_id = f"{task_name}#L{item['line']}"
                
                try:
                    rel = Path(item["path"]).relative_to("text")
                    chap_key = str(rel.with_suffix(".mp3"))
                    chap_segments = self.history.get(chap_key, {}).get("segments", [])
                except: chap_segments = []
                
                in_this_chap = any(s.get("text", "").strip().rstrip('.') == item['text'].strip().rstrip('.') for s in chap_segments)
                done = in_this_chap or (task_id in comp)
                
                ic = "✅ " if done else "  "
                if done: any_done = True
                else: all_done = False
                node_text = f"{ic}{task_name} L{item['line']}"
                item_nodes.append((idx, node_text, done))
            
            # Dossier parent (Livre)
            bk_ic = "✅ " if all_done else "📁 "
            tag = "done" if all_done else ("in_progress" if any_done else "")
            
            # On restaure l'état OUVERT si le livre était déjà ouvert
            is_open = (bk in opened_books)
            bid = self.plan_tree.insert("", "end", text=f"{bk_ic}{bk}", open=is_open, tags=(tag,))
            
            # Ajout des enfants
            for idx, txt, done in item_nodes:
                self.plan_tree.insert(bid, "end", iid=f"task_{idx}", text=txt, tags=("done",) if done else ())

    def _refresh_stats(self):
        if not hasattr(self, "stats_list"): return
        self.stats_list.delete(0, "end")
        
        stats = self.history.get("stats", {})
        # Trier par durée décroissante
        sorted_users = sorted(stats.items(), key=lambda x: x[1]["duration"], reverse=True)
        
        for user, data in sorted_users:
            dur_min = int(data["duration"] // 60)
            dur_sec = int(data["duration"] % 60)
            self.stats_list.insert("end", f"👤 {user.upper()}")
            self.stats_list.insert("end", f"   • {data['count']} segments")
            self.stats_list.insert("end", f"   • {dur_min}m {dur_sec}s")
            self.stats_list.insert("end", "") # Espace

    def _on_list_click(self, e):
        sel = self.listbox.curselection()
        if sel: self._load_pair(sel[0])

    def _on_plan_click(self, e):
        sel = self.plan_tree.selection()
        if not sel or not sel[0].startswith("task_"): return
        idx = int(sel[0].split("_")[1])
        item = self.plan[idx]
        target_key = str(Path(item["path"]).relative_to("text").with_suffix(".mp3"))
        for i, (ap, _) in enumerate(self.pairs):
            if str(ap.relative_to(AUDIO_DIR)) == target_key:
                self.listbox.selection_clear(0, "end")
                self.listbox.selection_set(i)
                self._load_pair(i)
                L = item["line"]
                self.txt_area.config(state="normal")
                line_content = self.txt_area.get(f"{L}.0", f"{L}.end")
                target_text = item["text"].strip()
                
                # On cherche l'index exact du texte dans la ligne
                start_col = line_content.find(target_text)
                self.txt_area.tag_remove("suggestion", "1.0", "end")
                
                if start_col != -1:
                    # Surlignage précis
                    s_pos = f"{L}.{start_col}"
                    e_pos = f"{L}.{start_col + len(target_text)}"
                    self.txt_area.tag_add("suggestion", s_pos, e_pos)
                    self.txt_area.see(s_pos)
                    # Auto-sélection
                    self.txt_area.tag_remove("sel", "1.0", "end")
                    self.txt_area.tag_add("sel", s_pos, e_pos)
                    
                    # --- NOUVEAU : Estimation temporelle SMART ---
                    full_text = self.txt_area.get("1.0", "end")
                    total_chars = len(full_text)
                    # Position du début de la phrase dans tout le texte
                    before_text = self.txt_area.get("1.0", s_pos)
                    start_char_idx = len(before_text)
                    
                    if total_chars > 0:
                        ratio_start = start_char_idx / total_chars
                        ratio_end = (start_char_idx + len(target_text)) / total_chars
                        
                        est_start = ratio_start * self.duration
                        est_end = ratio_end * self.duration
                        
                        # On ajuste la vue avec une petite marge
                        self.wave.start_s = max(0, est_start - 0.2)
                        self.wave.end_s = min(self.duration, est_end + 0.2)
                        self.wave.view_start = max(0, self.wave.start_s - 3)
                        self.wave.view_end = min(self.duration, self.wave.end_s + 5)
                        self.wave.draw()
                        self._update_scrollbar()
                break

    def _load_pair(self, idx):
        self._stop_audio()
        self.current_idx = idx
        ap, tp = self.pairs[idx]
        key = str(ap.relative_to(AUDIO_DIR))
        samples, dur, seg = audio_to_numpy(ap)
        self.audio_seg = seg
        self.duration = dur
        self.wave.saved_spans = []
        hist = self.history.get(key, {})
        for s in hist.get("segments", []): self.wave.saved_spans.append((s["start"], s["end"]))
        self.wave.load(samples, dur)
        self.txt_area.delete("1.0", "end")
        with open(tp, encoding="utf-8") as f: content = f.read()
        self.txt_area.insert("end", content)
        
        # --- NOUVEAU : Barrer les textes déjà sauvegardés ---
        if key in self.history:
            segments = self.history[key] if isinstance(self.history[key], list) else self.history[key].get("segments", [])
            for seg in segments:
                txt = seg.get("text", "").strip()
                if not txt: continue
                start_search = "1.0"
                while True:
                    pos = self.txt_area.search(txt, start_search, stopindex="end")
                    if not pos: break
                    end_pos = f"{pos}+{len(txt)}c"
                    self.txt_area.tag_add("saved", pos, end_pos)
                    start_search = end_pos

        self.lbl_info.config(text=f"📖 {ap.name}", fg=SUCCESS if hist.get("finished") else ACCENT)

    def _save(self):
        try:
            s_idx, e_idx = self.txt_area.index(tk.SEL_FIRST), self.txt_area.index(tk.SEL_LAST)
            text = self.txt_area.get(s_idx, e_idx).strip()
        except: return messagebox.showwarning("Erreur", "Surlignez le texte d'abord !")
        
        chap_path = self.pairs[self.current_idx][0].relative_to(AUDIO_DIR)
        prefix = "-".join(chap_path.as_posix().replace(".mp3", "").split("/"))
        start_ms = int(self.wave.start_s * 1000)
        wav_name = f"{prefix}-T{start_ms:07d}.wav"
        
        clip = self.audio_seg[start_ms:int(self.wave.end_s*1000)]
        clip = effects.normalize(clip)
        out = OUTPUT_DIR / "wavs" / wav_name
        clip.export(str(out), format="wav")
        
        with open(METADATA_FILE, "a", encoding="utf-8") as f:
            f.write(f"wavs/{wav_name}|{text}\n")
        
        self.existing_texts.add(text.strip().rstrip('.'))
        ck = chap_path.as_posix()
        if ck not in self.history: self.history[ck] = {"segments": [], "finished": False}
        self.history[ck]["segments"].append({"start": self.wave.start_s, "end": self.wave.end_s, "text": text, "wav_name": wav_name})
        self._write_history_item(ck)
        
        self.total_processed_sec += (self.wave.end_s - self.wave.start_s)
        self.txt_area.tag_add("saved", s_idx, e_idx)
        self.wave.saved_spans.append((self.wave.start_s, self.wave.end_s))
        
        # Step forward
        old_end = self.wave.end_s
        self.wave.start_s, self.wave.end_s = old_end, min(old_end+5, self.duration)
        self.wave.draw()
        self._update_total_time_label()
        self._refresh_plan_list()

    def _write_history_item(self, key):
        safe = key.replace("/", "___")
        path = HISTORY_DIR / f"{safe}___{self.user_name}.json"
        if key == "completed_tasks": path = HISTORY_DIR / f"completed_tasks___{self.user_name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.history.get(key, []), f if key=="completed_tasks" else f, indent=2)

    def _mark_task_done(self):
        sel = self.plan_tree.selection()
        if not sel or not sel[0].startswith("task_"): return
        idx = int(sel[0].split("_")[1])
        tid = f"{Path(self.plan[idx]['path']).name}#L{self.plan[idx]['line']}"
        if "completed_tasks" not in self.history: self.history["completed_tasks"] = []
        if tid not in self.history["completed_tasks"]:
            self.history["completed_tasks"].append(tid)
            self._write_history_item("completed_tasks")
        self._refresh_plan_list()

    def _mark_finished(self):
        k = Path(self.pairs[self.current_idx][0].relative_to(AUDIO_DIR)).as_posix()
        if k not in self.history: self.history[k] = {"segments": [], "finished": False}
        self.history[k]["finished"] = True
        self._write_history_item(k)
        self._refresh_list()
        messagebox.showinfo("OK", "Chapitre marqué comme fini !")

    def _reload_all_data(self):
        self.history = self._load_history()
        self.existing_texts = self._load_existing_texts()
        self.total_processed_sec = self._get_total_duration()
        self._refresh_list()
        self._refresh_plan_list()
        self._refresh_stats()
        rebuild_dataset.rebuild()
        messagebox.showinfo("Sync", "Données rechargées !")

    def _git_push(self):
        is_win = (os.name == "nt")
        try:
            subprocess.run(["git", "add", "dataset/history"], check=True, shell=is_win)
            subprocess.run(["git", "commit", "-m", f"🚀 Aligned by {self.user_name}"], capture_output=True, shell=is_win)
            subprocess.run(["git", "push"], check=True, shell=is_win)
            messagebox.showinfo("Git", "Push réussi !")
        except Exception as e: messagebox.showerror("Git Error", str(e))

    def _undo(self):
        ap = self.pairs[self.current_idx][0]
        key = str(ap.relative_to(AUDIO_DIR))
        if key not in self.history or not self.history[key]["segments"]:
            return messagebox.showwarning("Annuler", "Rien à annuler pour ce chapitre.")
        
        # 1. On retire le dernier segment
        last = self.history[key]["segments"].pop()
        wav_name = last["wav_name"]
        
        # 2. Supprimer le fichier WAV
        wav_path = OUTPUT_DIR / "wavs" / wav_name
        if wav_path.exists():
            try: os.unlink(wav_path)
            except: pass
            
        # 3. Supprimer du metadata.csv (on enlève la dernière ligne correspondante)
        if METADATA_FILE.exists():
            lines = open(METADATA_FILE, encoding="utf-8").readlines()
            # On cherche la ligne qui correspond au wav_name
            new_lines = [l for l in lines if f"wavs/{wav_name}|" not in l]
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        
        # 4. Sauvegarde de l'historique épuré
        self._write_history_item(key)
        
        # 5. Refresh UI
        self._load_pair(self.current_idx)
        self._refresh_list()
        self._refresh_plan_list()
        messagebox.showinfo("Annuler", "Dernier segment annulé avec succès.")
    def _on_wave_change(self, s, e): self.lbl_sel.config(text=f"{s:.2f}s - {e:.2f}s")
    def _update_total_time_label(self):
        t = int(self.total_processed_sec)
        self.lbl_total_time.config(text=f"Objectif 2h : {t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d} / 02:00:00")
        self.progress_bar["value"] = min(100, (t / 7200) * 100)

    def _on_scroll(self, m, *a):
        if m == "moveto":
            self.wave.view_start = float(a[0]) * self.duration
            self.wave.view_end = self.wave.view_start + 10.0
            self.wave.draw(); self._update_scrollbar()

    def _update_scrollbar(self):
        if self.duration > 0: self.scroll.set(self.wave.view_start/self.duration, self.wave.view_end/self.duration)

    def _play_selection(self):
        self._stop_audio()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t: p = t.name
        self.audio_seg[int(self.wave.start_s*1000):int(self.wave.end_s*1000)].export(p, format="wav")
        cmd = get_player_cmd(p, self.speed)
        if cmd:
            self.player_proc = subprocess.Popen(cmd)
            self.is_playing = True
            threading.Thread(target=self._wait_play, args=(self.player_proc, p), daemon=True).start()

    def _wait_play(self, p, path):
        p.wait()
        try: os.unlink(path)
        except: pass
        self.is_playing = False

    def _stop_audio(self):
        if self.player_proc: self.player_proc.terminate()
        self.is_playing = False

    def _toggle_play(self):
        if self.is_playing: self._stop_audio()
        else: self._play_selection()

    def _tick(self): self.after(100, self._tick)

    def _nudge(self, m, d):
        if m == "start": self.wave.start_s = max(0, min(self.wave.start_s+d, self.wave.end_s-0.01))
        else: self.wave.end_s = max(self.wave.start_s+0.01, min(self.wave.end_s+d, self.duration))
        self.wave.draw(); self._on_wave_change(self.wave.start_s, self.wave.end_s)

    def _search_text(self):
        query = self.ent_search.get().strip()
        self.txt_area.tag_remove("search", "1.0", "end")
        if not query or len(query) < 2: return
        start = "1.0"
        while True:
            pos = self.txt_area.search(query, start, stopindex="end", nocase=True)
            if not pos: break
            end = f"{pos}+{len(query)}c"
            self.txt_area.tag_add("search", pos, end)
            start = end

def audio_to_numpy(p):
    s = AudioSegment.from_file(str(p))
    sw = s.set_channels(1).set_frame_rate(8000)
    arr = np.array(sw.get_array_of_samples(), dtype=np.float32)
    if len(arr) > 0: arr /= max(abs(arr.max()), 1)
    return arr, len(s)/1000.0, s

if __name__ == "__main__":
    AlignerApp().mainloop()
