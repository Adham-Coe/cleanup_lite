# main.py
# CleanUp Lite – Tkinter UI glue around scanner.py + recycle.py

from __future__ import annotations
import os
import json
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import scanner
import recycle

# Optional memory display (safe if not installed)
try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

APP_TITLE = "CleanUp Lite"
SESSION_FILE = "session.json"
MAX_THREADS = 4 # as per optization guidance


class App:
    def __init__(self,root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("980x640")

        # ----- ADDED: theme state & availability check -----
        self.theme_mode = tk.StringVar(value="dark")
        try:
            _has = self.root.call("info", "commands", "set_theme")  # defined by sun-valley.tcl
            self._has_set_theme = bool(_has)
        except Exception:
            self._has_set_theme = False
        # ---------------------------------------------------

        # Threading control flags
        self.stop_flag = threading.Event()
        self.pause_flag = threading.Event()
        self.pause_flag.set()  # start in 'running' state

        self.ui_queue: "queue.Queue[tuple]" = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=MAX_THREADS)

        self.last_folder = os.path.expanduser("~")
        self.min_mb = tk.IntVar(value=50)

        self._build_ui()
        self._load_session()
        self._tick_queues()
        if psutil:
            self._tick_memory()

        # Save session at exit
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- UI BUILD ----------------
    def _build_ui(self) -> None:
        nav = ttk.Notebook(self.root)
        nav.pack(fill=tk.BOTH, expand=True)

        self.home = ttk.Frame(nav)
        self.scan = ttk.Frame(nav)
        self.dupes = ttk.Frame(nav)
        self.recycle_tab = ttk.Frame(nav)

        nav.add(self.home, text="Home")
        nav.add(self.scan, text="Scan (Large Files)")
        nav.add(self.dupes, text="Duplicates")
        nav.add(self.recycle_tab, text="Recycle")

        self._build_home()
        self._build_scan()
        self._build_dupes()
        self._build_recycle()

        # ----- MiniGame tab (ADDED) -----
        self.minigame = ttk.Frame(nav)
        nav.add(self.minigame, text="MiniGame")
        self._build_minigame()
        # --------------------------------

    def _build_home(self) -> None:
        pad = {"padx": 12, "pady": 8}
        lbl = ttk.Label(self.home, text="Welcome to CleanUp Lite", font=("Segoe UI", 16, "bold"))
        lbl.pack(**pad)

        desc = (
            "Find large files and duplicates, move them to a safe Recycle folder, and restore if needed.\n"
            "This app keeps memory usage low using generators, chunked I/O, and a max-4 thread pool."
        )
        ttk.Label(self.home, text=desc, justify=tk.LEFT).pack(**pad)

        frm = ttk.Frame(self.home)
        frm.pack(fill=tk.X, **pad)
        ttk.Label(frm, text="Target folder:").pack(side=tk.LEFT)
        self.folder_var = tk.StringVar(value=self.last_folder)
        ttk.Entry(frm, textvariable=self.folder_var, width=70).pack(side=tk.LEFT, padx=8)
        ttk.Button(frm, text="Browse", command=self._choose_folder).pack(side=tk.LEFT)

        frm2 = ttk.Frame(self.home)
        frm2.pack(fill=tk.X, **pad)
        ttk.Label(frm2, text="Minimum file size (MB):").pack(side=tk.LEFT)
        ttk.Spinbox(frm2, from_=1, to=100000, textvariable=self.min_mb, width=8).pack(side=tk.LEFT, padx=8)

        # Controls
        c = ttk.Frame(self.home)
        c.pack(**pad)
        ttk.Button(c, text="Start Scan (Large Files)", command=self.start_scan).grid(row=0, column=0, padx=6)
        ttk.Button(c, text="Find Duplicates", command=self.start_dupe_search).grid(row=0, column=1, padx=6)

        # Memory indicator (optional)
        self.mem_label = ttk.Label(self.home, text="Memory: n/a")
        self.mem_label.pack(**pad)

        # ----- ADDED: theme toggle (Light/Dark) -----
        theme_row = ttk.Frame(self.home)
        theme_row.pack(fill=tk.X, **pad)
        ttk.Label(theme_row, text="Appearance:").pack(side=tk.LEFT)
        ttk.Radiobutton(
            theme_row, text="Light", value="light", variable=self.theme_mode,
            command=lambda: self._apply_theme(self.theme_mode.get())
        ).pack(side=tk.LEFT, padx=6)
        ttk.Radiobutton(
            theme_row, text="Dark", value="dark", variable=self.theme_mode,
            command=lambda: self._apply_theme(self.theme_mode.get())
        ).pack(side=tk.LEFT, padx=6)
        # -------------------------------------------

    def _build_scan(self) -> None:
        pad = {"padx": 8, "pady": 6}
        # Toolbar
        t = ttk.Frame(self.scan)
        t.pack(fill=tk.X, **pad)
        ttk.Button(t, text="Start", command=self.start_scan).pack(side=tk.LEFT)
        ttk.Button(t, text="Pause/Resume", command=self.toggle_pause).pack(side=tk.LEFT, padx=6)
        ttk.Button(t, text="Stop", command=self.stop).pack(side=tk.LEFT)
        ttk.Button(t, text="Move Selected to Recycle", command=self.move_selected_large).pack(side=tk.RIGHT)

        # Results tree
        cols = ("path", "size")
        self.large_tree = ttk.Treeview(self.scan, columns=cols, show="headings", selectmode="extended")
        self.large_tree.heading("path", text="Path")
        self.large_tree.heading("size", text="Size (MB)")
        self.large_tree.column("path", width=740, anchor=tk.W)
        self.large_tree.column("size", width=100, anchor=tk.E)
        self.large_tree.pack(fill=tk.BOTH, expand=True, **pad)

        # Status
        self.scan_status = ttk.Label(self.scan, text="Idle")
        self.scan_status.pack(**pad)

    def _build_dupes(self) -> None:
        pad = {"padx": 8, "pady": 6}
        t = ttk.Frame(self.dupes)
        t.pack(fill=tk.X, **pad)
        ttk.Button(t, text="Find Duplicates", command=self.start_dupe_search).pack(side=tk.LEFT)
        ttk.Button(t, text="Pause/Resume", command=self.toggle_pause).pack(side=tk.LEFT, padx=6)
        ttk.Button(t, text="Stop", command=self.stop).pack(side=tk.LEFT)
        ttk.Button(t, text="Move Selected to Recycle", command=self.move_selected_dupes).pack(side=tk.RIGHT)

        self.dupe_tree = ttk.Treeview(self.dupes, columns=("group", "path"), show="headings", selectmode="extended")
        self.dupe_tree.heading("group", text="Group")
        self.dupe_tree.heading("path", text="Path")
        self.dupe_tree.column("group", width=80, anchor=tk.CENTER)
        self.dupe_tree.column("path", width=780, anchor=tk.W)
        self.dupe_tree.pack(fill=tk.BOTH, expand=True, **pad)

        self.dupe_status = ttk.Label(self.dupes, text="Idle")
        self.dupe_status.pack(**pad)

    def _build_recycle(self) -> None:
        pad = {"padx": 8, "pady": 6}
        t = ttk.Frame(self.recycle_tab)
        t.pack(fill=tk.X, **pad)
        ttk.Button(t, text="Refresh", command=self.refresh_recycle).pack(side=tk.LEFT)
        ttk.Button(t, text="Restore Selected", command=self.restore_selected).pack(side=tk.LEFT, padx=6)
        ttk.Button(t, text="Delete Selected Permanently", command=self.delete_selected).pack(side=tk.LEFT)

        self.recycle_tree = ttk.Treeview(self.recycle_tab, columns=("recycled", "original"), show="headings", selectmode="extended")
        self.recycle_tree.heading("recycled", text="Recycled Path")
        self.recycle_tree.heading("original", text="Original Path")
        self.recycle_tree.column("recycled", width=400, anchor=tk.W)
        self.recycle_tree.column("original", width=460, anchor=tk.W)
        self.recycle_tree.pack(fill=tk.BOTH, expand=True, **pad)

        self.recycle_status = ttk.Label(self.recycle_tab, text="Recycle folder not loaded yet")
        self.recycle_status.pack(**pad)

    # ------------- Helpers -------------
    def _choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or os.path.expanduser("~"))
        if folder:
            self.folder_var.set(folder)
            self.last_folder = folder
            self.refresh_recycle()

    def _human_mb(self, bytes_val: int) -> str:
        return f"{bytes_val / (1024*1024):.2f}"

    # ------------- Scan (Large Files) -------------
    def start_scan(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror(APP_TITLE, "Please choose a valid folder.")
            return
        self.stop_flag.clear()
        self.pause_flag.set()
        self.large_tree.delete(*self.large_tree.get_children())
        self.scan_status.config(text="Scanning…")
        min_bytes = int(self.min_mb.get()) * 1024 * 1024

        def worker():
            for path, size in scanner.big_files(folder, min_bytes, self.stop_flag, self.pause_flag):
                # send to UI thread
                self.ui_queue.put(("large", path, size))
            self.ui_queue.put(("large_done",))

        threading.Thread(target=worker, daemon=True).start()

    def move_selected_large(self):
        folder = self.folder_var.get().strip()
        if not folder:
            return
        selected = self.large_tree.selection()
        if not selected:
            return
        moved = 0
        for iid in selected:
            path = self.large_tree.set(iid, "path")
            try:
                out = recycle.move_to_recycle(folder, path)
                if out:
                    moved += 1
            except Exception:
                pass
        self.refresh_recycle()
        messagebox.showinfo(APP_TITLE, f"Moved {moved} file(s) to Recycle.")

    # ------------- Duplicates -------------
    def start_dupe_search(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror(APP_TITLE, "Please choose a valid folder.")
            return
        self.stop_flag.clear()
        self.pause_flag.set()
        self.dupe_tree.delete(*self.dupe_tree.get_children())
        self.dupe_status.config(text="Finding duplicates…")
        min_bytes = int(self.min_mb.get()) * 1024 * 1024

        def worker():
            group_id = 1
            for group in scanner.duplicate_groups(folder, min_bytes, self.executor, self.stop_flag, self.pause_flag):
                self.ui_queue.put(("dupe_group", group_id, group))
                group_id += 1
            self.ui_queue.put(("dupe_done",))

        threading.Thread(target=worker, daemon=True).start()

    def move_selected_dupes(self):
        folder = self.folder_var.get().strip()
        if not folder:
            return
        selected = self.dupe_tree.selection()
        moved = 0
        for iid in selected:
            path = self.dupe_tree.set(iid, "path")
            try:
                out = recycle.move_to_recycle(folder, path)
                if out:
                    moved += 1
            except Exception:
                pass
        self.refresh_recycle()
        messagebox.showinfo(APP_TITLE, f"Moved {moved} duplicate file(s) to Recycle.")

    # ------------- Recycle -------------
    def refresh_recycle(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            self.recycle_status.config(text="Select a valid folder on Home tab to enable Recycle view.")
            return
        rec = recycle.ensure_recycle(folder)
        manifest = recycle.load_manifest(rec)
        self.recycle_tree.delete(*self.recycle_tree.get_children())
        for recycled_path, original_path in manifest.items():
            self.recycle_tree.insert('', tk.END, values=(recycled_path, original_path))
        self.recycle_status.config(text=f"Recycle folder: {rec}  (items: {len(manifest)})")

    def restore_selected(self):
        folder = self.folder_var.get().strip()
        if not folder:
            return
        rec = recycle.ensure_recycle(folder)
        selected = self.recycle_tree.selection()
        restored = 0
        for iid in selected:
            recycled_path = self.recycle_tree.set(iid, "recycled")
            if recycle.restore_from_recycle(rec, recycled_path):
                restored += 1
        self.refresh_recycle()
        messagebox.showinfo(APP_TITLE, f"Restored {restored} item(s).")

    def delete_selected(self):
        folder = self.folder_var.get().strip()
        if not folder:
            return
        rec = recycle.ensure_recycle(folder)
        selected = self.recycle_tree.selection()
        deleted = 0
        for iid in selected:
            recycled_path = self.recycle_tree.set(iid, "recycled")
            if recycle.delete_permanently(rec, recycled_path):
                deleted += 1
        self.refresh_recycle()
        messagebox.showinfo(APP_TITLE, f"Permanently deleted {deleted} item(s).")

    # ------------- Pause/Stop -------------
    def toggle_pause(self):
        if self.pause_flag.is_set():
            self.pause_flag.clear()  # go to paused state (waiters will block)
            self._set_status("Paused")
        else:
            self.pause_flag.set()    # resume workers
            self._set_status("Resumed")

    def stop(self):
        self.stop_flag.set()
        self.pause_flag.set()  # ensure not stuck
        self._set_status("Stopping…")

    # ------------- UI queue pump -------------
    def _tick_queues(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                kind = item[0]
                if kind == "large":
                    _, path, size = item
                    self.large_tree.insert('', tk.END, values=(path, self._human_mb(size)))
                elif kind == "large_done":
                    self.scan_status.config(text="Done ✔")
                elif kind == "dupe_group":
                    _, gid, group = item
                    for p in group:
                        self.dupe_tree.insert('', tk.END, values=(gid, p))
                elif kind == "dupe_done":
                    self.dupe_status.config(text="Done ✔")
        except queue.Empty:
            pass
        self.root.after(100, self._tick_queues)

    def _set_status(self, text: str):
        self.scan_status.config(text=text)
        self.dupe_status.config(text=text)

    # ------------- Memory tick -------------
    def _tick_memory(self):
        if psutil:
            proc = psutil.Process()
            rss = proc.memory_info().rss / (1024*1024)
            self.mem_label.config(text=f"Memory: {rss:.1f} MB  |  Threads: {psutil.Process().num_threads()}")
            self.root.after(1000, self._tick_memory)

    # ------------- Session persistence -------------
    def _load_session(self):
        if not os.path.exists(SESSION_FILE):
            return
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.last_folder = data.get('last_folder', self.last_folder)
            self.folder_var.set(self.last_folder)
            self.min_mb.set(int(data.get('min_mb', self.min_mb.get())))
            # ----- ADDED: restore theme -----
            self.theme_mode.set(data.get('theme', self.theme_mode.get()))
            self._apply_theme(self.theme_mode.get())
            # --------------------------------
            self.refresh_recycle()
        except Exception:
            pass

    def _save_session(self):
        data = {
            'last_folder': self.folder_var.get().strip(),
            'min_mb': int(self.min_mb.get()),
            # ----- ADDED: persist theme -----
            'theme': self.theme_mode.get(),
            # --------------------------------
        }
        try:
            with open(SESSION_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _on_close(self):
        self.stop()
        self._save_session()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()

    # ----- ADDED: theme apply helper -----
    def _apply_theme(self, mode: str):
        if mode not in ("light", "dark"):
            return
        try:
            if self._has_set_theme:
                self.root.call("set_theme", mode)
        except Exception:
            # If sun-valley isn't available, silently ignore.
            pass
    # -------------------------------------

    # ===================== MiniGame (ADDED) =====================
    def _build_minigame(self) -> None:
        pad = {"padx": 8, "pady": 6}

        top = ttk.Frame(self.minigame)
        top.pack(fill=tk.X, **pad)
        ttk.Button(top, text="Reset", command=self._game_reset).pack(side=tk.LEFT)
        ttk.Label(top, text="   Score:").pack(side=tk.LEFT)
        self.game_score = tk.IntVar(value=0)
        ttk.Label(top, textvariable=self.game_score).pack(side=tk.LEFT)

        ttk.Label(
            top,
            text="Drag the crumpled paper and flick it into the basket.",
            anchor="e"
        ).pack(side=tk.RIGHT)

        self.game_canvas = tk.Canvas(self.minigame, bg="#202020", height=480, highlightthickness=0)
        self.game_canvas.pack(fill=tk.BOTH, expand=True, **pad)

        # State
        self._game_anim = False
        self._game_vx = 0.0
        self._game_vy = 0.0
        self._drag_active = False
        self._drag_hist = []  # (x, y, t)

        self._game_setup()

    def _game_setup(self):
        c = self.game_canvas
        c.update_idletasks()
        w = max(600, c.winfo_width())
        h = max(360, c.winfo_height())
        c.config(width=w, height=h)
        c.delete("all")

        # Floor line
        c.create_line(0, h-40, w, h-40, fill="#404040", width=2)

        # Basket (simple bin with open top)
        bx1, by1 = w - 160, h - 160
        bx2, by2 = w - 60, h - 40
        self.basket_id = c.create_rectangle(bx1, by1, bx2, by2, outline="#9acd32", width=3)
        # Goal area (slightly inset)
        self.goal_area = (bx1+8, by1+8, bx2-8, by1+30)
        # Visual hoop/opening
        c.create_rectangle(*self.goal_area, outline="#9acd32", dash=(3, 2))

        # Paper (circle)
        r = 16
        start_x, start_y = 80, h - 80
        self.paper_id = c.create_oval(start_x-r, start_y-r, start_x+r, start_y+r, fill="#f5f5f5", outline="#d0d0d0")
        c.addtag_withtag("paper", self.paper_id)

        # Bindings on the paper only
        c.tag_bind("paper", "<Button-1>", self._paper_press)
        c.tag_bind("paper", "<B1-Motion>", self._paper_drag)
        c.tag_bind("paper", "<ButtonRelease-1>", self._paper_release)

        # Resize handling keeps basket/floor aligned when user resizes window
        c.bind("<Configure>", lambda e: self._game_setup())

    def _paper_press(self, event):
        self._drag_active = True
        self._game_anim = False  # stop any flight
        self._drag_hist = [(event.x, event.y, time.time())]
        self._drag_last = (event.x, event.y)

    def _paper_drag(self, event):
        if not self._drag_active:
            return
        cx, cy = self._drag_last
        dx, dy = event.x - cx, event.y - cy
        self.game_canvas.move(self.paper_id, dx, dy)
        self._drag_last = (event.x, event.y)
        t = time.time()
        self._drag_hist.append((event.x, event.y, t))
        if len(self._drag_hist) > 6:
            self._drag_hist.pop(0)

    def _paper_release(self, event):
        if not self._drag_active:
            return
        self._drag_active = False

        # Compute flick velocity from the last few samples
        if len(self._drag_hist) >= 2:
            x0, y0, t0 = self._drag_hist[0]
            x1, y1, t1 = self._drag_hist[-1]
            dt = max(0.001, t1 - t0)
            self._game_vx = (x1 - x0) / dt * 0.025  # tune factor
            self._game_vy = (y1 - y0) / dt * 0.025
        else:
            self._game_vx = self._game_vy = 0.0

        self._game_anim = True
        self._game_step()

    def _game_step(self):
        if not self._game_anim:
            return
        c = self.game_canvas
        w = c.winfo_width()
        h = c.winfo_height()

        # Physics
        g = 0.9
        air = 0.995
        bounce = 0.7

        self._game_vy += g
        self._game_vx *= air
        self._game_vy *= air

        # Move paper
        c.move(self.paper_id, self._game_vx, self._game_vy)

        # Collisions with walls/floor/ceiling
        x1, y1, x2, y2 = c.bbox(self.paper_id)
        r = (x2 - x1) / 2.0

        # Left
        if x1 < 0:
            c.move(self.paper_id, -x1, 0)
            self._game_vx = -self._game_vx * bounce
        # Right
        if x2 > w:
            c.move(self.paper_id, w - x2, 0)
            self._game_vx = -self._game_vx * bounce
        # Ceiling
        if y1 < 0:
            c.move(self.paper_id, 0, -y1)
            self._game_vy = -self._game_vy * bounce
        # Floor (just above the floor line)
        floor_y = h - 40
        if y2 > floor_y:
            c.move(self.paper_id, 0, floor_y - y2)
            self._game_vy = -abs(self._game_vy) * bounce
            # small horizontal damping on floor contact
            self._game_vx *= 0.9

        # Scoring: center inside goal area while moving downward
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        gx1, gy1, gx2, gy2 = self.goal_area
        if gx1 < cx < gx2 and gy1 < cy < gy2 and self._game_vy > 0:
            self._game_anim = False
            self.game_score.set(self.game_score.get() + 1)
            self._flash_goal()
            self._reset_paper()
            return

        # Stop if the paper is nearly still on the floor
        if abs(self._game_vx) < 0.05 and abs(self._game_vy) < 0.05 and abs(y2 - floor_y) < 1.0:
            self._game_anim = False
            return

        self.root.after(16, self._game_step)

    def _flash_goal(self):
        # brief visual feedback on the hoop
        c = self.game_canvas
        gx1, gy1, gx2, gy2 = self.goal_area
        glow = c.create_rectangle(gx1, gy1, gx2, gy2, outline="#00ff7f", width=4)
        self.root.after(150, lambda: c.delete(glow))

    def _reset_paper(self):
        c = self.game_canvas
        c.update_idletasks()
        h = c.winfo_height()
        # Place near left
        r = 16
        start_x, start_y = 80, h - 80
        x1, y1, x2, y2 = c.bbox(self.paper_id)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        c.move(self.paper_id, start_x - cx, start_y - cy)
        self._game_vx = self._game_vy = 0.0

    def _game_reset(self):
        self._game_anim = False
        self.game_score.set(0)
        self._game_setup()
    # =================== End MiniGame (ADDED) ===================


def main():
    root = tk.Tk()
    # nicer default theme on Windows
    try:
        root.call("source", "sun-valley.tcl")
        root.call("set_theme", "dark")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()