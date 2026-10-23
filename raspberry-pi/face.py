#face.py - Smart Attendance Kiosk (Location 2)
# Improved PC-connected kiosk - Pi 5 + Camera Module 3
# Capture and recognition run in restartable processes; Tk stays on the main thread.

import tkinter as tk
from tkinter import messagebox
import os
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
from PIL import Image, ImageTk
import cv2
import numpy as np
import time
import threading
import queue
import multiprocessing as mp
import signal
import re
from pathlib import Path
from types import SimpleNamespace
from kiosk_transport import ReliableTransport
from kiosk_config import load_config
from kiosk_touch import enable_touch_buttons, trace_input
from kiosk_instance import kiosk_instance, KioskAlreadyRunning
from kiosk_vision import camera_worker, inference_worker, put_latest
from datetime import datetime

import warnings

# --- HIDE WARNINGS ---
warnings.filterwarnings("once")

# --- PICAMERA2 IMPORT ---

os.environ['LIBCAMERA_LOG_LEVELS'] = '*:ERROR'

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = str(BASE_DIR / '1.png')
DB_PATH = str(BASE_DIR / "database")
try:
    API_URL, DEVICE_TOKEN = load_config(BASE_DIR)
except (ValueError, OSError) as exc:
    raise SystemExit(f'Kiosk connection: {exc}\nRun python3 configure_kiosk.py on the Raspberry Pi.') from None

# TIMING SETTINGS
COOLDOWN_SECONDS = 300
SUCCESS_DISPLAY_TIME = 8
SIMILARITY_THRESHOLD = 0.55

# --- SCREEN CONSTANTS ---
# Launch from the touchscreen terminal. KIOSK_FULLSCREEN=0 is a windowed fallback.
KIOSK_FULLSCREEN = os.environ.get('KIOSK_FULLSCREEN', '1') != '0'
SCREEN_W = 800 if KIOSK_FULLSCREEN else 780
SCREEN_H = 480 if KIOSK_FULLSCREEN else 400

# --- CAMERA CONFIG ---
CAM_WIDTH = 640
CAM_HEIGHT = 360
CAM_FPS = 15

# --- COLORS (RGB - frames are RGB after channel swap) ---
GUI_BG     = "#000000"
GUI_PANEL  = "#000000"
GUI_ACCENT = "#80dba8"
GUI_WARN   = "#f2c67b"
GUI_ERR    = "#f3b6c3"
GUI_TEAL   = "#ffffff"
GUI_INK    = "#ffffff"
GUI_MUTED  = "#ffffff"
GUI_BRAND  = "#000000"
GUI_BORDER = "#ffffff"
CV_GREEN  = (0, 255, 0)       # RGB Green
CV_YELLOW = (255, 255, 0)     # RGB Yellow
CV_RED    = (120, 27, 40)     # Sugihara dark maroon (RGB)
CV_GREY   = (100, 100, 100)

if not os.path.exists(DB_PATH):
    os.makedirs(DB_PATH)

class SmartAttendanceSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Attendance Kiosk")

        # Map a small managed window on the launch output before requesting
        # fullscreen. Keep WM focus/dialog handling and the working touch bindings.
        self.root.configure(bg=GUI_BG)
        self.root.geometry('780x400')
        self.root.resizable(False, False)
        self.root.update()
        if KIOSK_FULLSCREEN:
            self.root.after(250, lambda: self.root.attributes('-fullscreen', True))
        self.root.attributes('-topmost', True)
        self.root.after(1000, lambda: print(
            f'[DISPLAY] Tk window: {self.root.winfo_geometry()}; '
            'touchscreen terminal launch; test physical touch', flush=True))

        self.root.configure(bg=GUI_BG)
        self.root.update_idletasks()
        self.root.focus_force()
        self.root.bind("<Escape>", lambda e: self.return_to_menu('Escape'))

        # Native calls run in separate processes and can be restarted on a stall.
        self.process_context = mp.get_context('spawn')
        self.worker_stop = self.process_context.Event()
        self.shutdown_requested = threading.Event()
        self.camera_process = None
        self.ai_process = None
        self.camera_state = 'starting'
        self.ai_state = 'starting'
        self.ui_queue = queue.Queue(maxsize=50)
        self.database_lock = threading.Lock()
        self.capture_timestamp = 0
        self.frame_sequence = 0
        self.reg_embedding_time = 0
        self.reg_capture_started = 0
        self.candidate_uid = None
        self.candidate_count = 0
        self.latched_uid = None
        self.face_absent_since = None
        self.transport = None
        self.pending_names = {}

        # --- FIXED DISPLAY SIZE (prevents flicker/resize) ---
        # Frame is rotated 90°, so width/height swap: aspect = CAM_HEIGHT / CAM_WIDTH
        self.display_height = SCREEN_H
        self.display_width  = int(SCREEN_H * CAM_HEIGHT / CAM_WIDTH)
        print(f"[DISPLAY] Fixed size: {self.display_width}x{self.display_height}")

        # --- STATE ---
        self.mode = "MENU"
        self.scan_memory = {}
        self.worker_status_cache = {}
        self.worker_shift_cache  = {}
        self.known_embeddings = []
        self.known_ids = []
        self.known_names = []
        self.known_matrix = None
        self.reg_face_detected = False
        self.reg_face_embedding = None
        self.last_success_time = 0
        self._last_reset_key = None

        # --- THREADING (this is what kills the lag/freeze) ---
        self.frame_lock = threading.Lock()
        self.latest_frame = None          # newest processed RGB frame (rotated/flipped)
        self.att_overlays = []            # boxes/labels computed by inference thread
        self.reg_overlays = []
        self._threads_running = True

        # --- INIT GUI ---
        self.setup_menu()
        self.setup_register()
        self.setup_attendance()
        enable_touch_buttons(self.root)
        self.root.bind('<ButtonPress-1>', lambda event: trace_input(event, 'press'))
        self.root.bind('<ButtonRelease-1>', lambda event: trace_input(event, 'release'))
        self.reload_database()

        # --- START BACKGROUND THREADS ---
        self.capture_thread = threading.Thread(target=self.capture_loop, daemon=True)
        self.inference_thread = threading.Thread(target=self.inference_loop, daemon=True)
        self.capture_thread.start()
        self.inference_thread.start()
        self.root.protocol('WM_DELETE_WINDOW', self.on_shutdown)

        # --- START GUI LOOPS (main thread) ---
        self.show_frame("ATTENDANCE")
        self.update_display()
        self.pump_ui()
        self.transport = ReliableTransport(API_URL, DEVICE_TOKEN, BASE_DIR / 'kiosk-runtime',
                                           self.on_scan_result, self.on_transport_health)
        self.health_loop()

    def ui(self, fn):
        # Worker threads never call any Tk method, including root.after.
        try:
            self.ui_queue.put_nowait(fn)
        except queue.Full:
            try:
                self.ui_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.ui_queue.put_nowait(fn)
            except queue.Full:
                pass

    def pump_ui(self):
        for _ in range(30):
            try:
                fn = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as exc:
                print('[UI]', type(exc).__name__)
        if self._threads_running:
            self.root.after(30, self.pump_ui)

    def on_transport_health(self, online, pending, detail):
        self.network_state = 'Online' if online else 'Offline'
        self.pending_count = pending

    def health_loop(self):
        if self.transport:
            self.transport.face_employee_ids = list(self.known_ids)
            self.transport.camera_health = self.camera_state
            self.transport.ai_health = self.ai_state
        network = getattr(self, 'network_state', 'Connecting')
        pending = getattr(self, 'pending_count', 0)
        parts = [network]
        if pending:
            parts.append(f'{pending} pending')
        if self.camera_state != 'ready':
            parts.append('Camera connecting')
        elif self.ai_state != 'ready':
            parts.append('Starting recognition')
        health = ' · '.join(parts)
        if hasattr(self, 'lbl_health'):
            healthy = network == 'Online' and self.camera_state == 'ready' and self.ai_state == 'ready'
            self.lbl_health.config(text=health, fg=GUI_ACCENT if healthy else GUI_WARN)
        self.refresh_registration()
        if self._threads_running:
            self.root.after(1000, self.health_loop)

    def get_worker_status(self, uid):
        if self.transport:
            with self.transport.cache_lock:
                return self.transport.status_cache.get(str(uid), 'UNKNOWN')
        return 'UNKNOWN'

    def get_next_window_text(self, uid):
        worker = self.transport.workers().get(str(uid), {}) if self.transport else {}
        schedule = worker.get('effective_schedule')
        if not schedule:
            return 'No schedule · review needed'
        return f'{schedule["name"]}: {schedule["start"]} – {schedule["end"]}'

    def on_scan_result(self, uid, result):
        worker = self.transport.workers().get(uid, {}) if self.transport else {}
        name = worker.get('name') or self.pending_names.get(uid, uid)
        action = result['action']
        if action in ('IN', 'OUT'):
            title = 'Clocked in' if action == 'IN' else 'Clocked out'
            color = GUI_ACCENT
        elif action == 'REVIEW':
            title, color = 'Saved for review', GUI_WARN
        elif action == 'DUPLICATE':
            title, color = 'Already recorded', GUI_WARN
        else:
            title, color = 'Scan not accepted', GUI_ERR
        self.last_success_time = time.time()
        def apply():
            self.lbl_status_main.config(text=title, fg=color, font=('Arial', 23, 'bold'))
            self.lbl_current_status.config(text=result.get('message', ''), fg=color, wraplength=450)
            self.lbl_next_window.config(text='Review needed' if result.get('flags') else '', fg=GUI_WARN)
            self.lbl_name_res.config(text=name, fg=color)
            self.lbl_id_res.config(text=uid, fg=color)
        self.ui(apply)

    # ================= LOGO HELPER =================
    def get_logo_image(self, max_w, max_h, bg_color):
        if not os.path.exists(LOGO_PATH):
            return None
        try:
            img = Image.open(LOGO_PATH)
            img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"Logo Load Error: {e}")
            return None

    # ================= GUI LAYOUTS =================
    def setup_menu(self):
        backdrop, paper, ink = GUI_BG, GUI_PANEL, GUI_INK
        self.frame_menu = tk.Frame(self.root, bg=paper)

        brand = tk.Frame(self.frame_menu, bg=backdrop)
        brand.place(relx=0, rely=0, relwidth=.34, relheight=1)
        tk.Label(brand, text='PORT KLANG', font=('Arial', 9, 'bold'),
                 bg=backdrop, fg=GUI_INK, anchor='center').place(relx=.5, rely=.18, anchor='center')
        logo = self.get_logo_image(92, 92, backdrop)
        if logo:
            lbl_logo = tk.Label(brand, image=logo, bg=backdrop, bd=0)
            lbl_logo.image = logo
            lbl_logo.place(relx=.5, rely=.40, anchor='center')
        tk.Label(brand, text='Digital\nAttendance', font=('Arial', 20, 'bold'),
                 justify='center', anchor='center', bg=backdrop, fg='white').place(relx=.5, rely=.64, anchor='center')

        actions = tk.Frame(self.frame_menu, bg=paper)
        actions.place(relx=.34, rely=0, relwidth=.66, relheight=1)
        content = tk.Frame(actions, bg=paper)
        content.pack(fill='both', expand=True, padx=38, pady=28)
        footer = tk.Frame(content, bg=paper)
        footer.pack(side='bottom', fill='x', pady=(12, 0))
        self.btn_menu_shutdown = tk.Button(footer, text='Close', command=self.on_shutdown,
            font=('Arial', 10), bg='#781b28', fg=GUI_INK, activebackground='#952c3a',
            activeforeground=GUI_INK, relief='flat', bd=0, highlightthickness=1,
            highlightbackground=GUI_BORDER, highlightcolor=GUI_BORDER, padx=16, pady=10, cursor='hand2')
        self.btn_menu_shutdown.pack(anchor='center')
        group = tk.Frame(content, bg=paper)
        group.place(relx=.5, rely=.45, anchor='center', relwidth=1, height=244)
        tk.Label(group, text='Welcome', font=('Arial', 22, 'bold'),
                 bg=paper, fg=ink, anchor='center').pack(fill='x', pady=(0, 28))

        primary = tk.Frame(group, bg='#781b28', height=64, padx=1, pady=1)
        primary.pack(fill='x')
        primary.pack_propagate(False)
        self.btn_menu_scan = tk.Button(primary, text='Start scanning',
            command=lambda: self.show_frame('ATTENDANCE'), font=('Arial', 14, 'bold'),
            bg='#781b28', fg='white', activebackground='#952c3a', activeforeground='white',
            relief='flat', bd=0, anchor='center', padx=20, cursor='hand2')
        self.btn_menu_scan.pack(fill='both', expand=True)

        secondary = tk.Frame(group, bg='#781b28', height=60, padx=1, pady=1)
        secondary.pack(fill='x', pady=(18, 0))
        secondary.pack_propagate(False)
        self.btn_menu_register = tk.Button(secondary, text='Register face',
            command=lambda: self.show_frame('REGISTER'), font=('Arial', 14, 'bold'),
            bg='#781b28', fg=GUI_INK, activebackground='#952c3a', activeforeground=GUI_INK,
            relief='flat', bd=0, anchor='center', padx=19, cursor='hand2')
        self.btn_menu_register.pack(fill='both', expand=True)

    def setup_register(self):
        self.frame_register = tk.Frame(self.root, bg=GUI_BG)

        # Pixel-sized container: Label width/height otherwise use text units before the first image.
        video = tk.Frame(self.frame_register, bg='black', width=self.display_width)
        video.pack(side='left', fill='y')
        video.pack_propagate(False)
        self.lbl_video_reg = tk.Label(video, bg='black', bd=0)
        self.lbl_video_reg.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Frame(video, bg=GUI_BRAND, height=4).place(x=0, y=0, relwidth=1)

        panel = tk.Frame(self.frame_register, bg=GUI_PANEL, padx=14, pady=8)
        panel.pack(side="right", fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=1)
        self.registration_selected = None
        self.registration_page = 0
        self.registration_registered = False
        self.registration_signature = None

        tk.Label(panel, text="Register face", font=("Arial", 16, "bold"),
                 bg=GUI_PANEL, fg=GUI_INK, anchor='w').grid(row=0, column=0, sticky='ew')
        self.lbl_registration_sync = tk.Label(panel, text="Loading employee list...",
                 font=("Arial", 10), bg=GUI_PANEL, fg=GUI_WARN, anchor='w')
        self.lbl_registration_sync.grid(row=1, column=0, sticky='ew', pady=(2, 4))
        filters = tk.Frame(panel, bg=GUI_PANEL)
        filters.grid(row=2, column=0, sticky='ew')
        self.btn_registration_filter = tk.Button(filters, text="Show registered",
                 command=self.toggle_registration_filter, font=("Arial", 11),
                 bg='#781b28', fg=GUI_INK, relief='flat', height=2)
        self.btn_registration_filter.pack(side='left', fill='x', expand=True)
        self.lbl_registration_count = tk.Label(filters, bg=GUI_PANEL, fg=GUI_INK, font=("Arial", 10))
        self.lbl_registration_count.pack(side='right', padx=6)

        cards = tk.Frame(panel, bg=GUI_PANEL)
        cards.grid(row=3, column=0, sticky='nsew', pady=4)
        cards.columnconfigure(0, weight=1)
        self.registration_cards = []
        for row in range(3):
            cards.rowconfigure(row, weight=1, uniform='cards')
            card = tk.Button(cards, text='', font=("Arial", 12, "bold"),
                             bg='#202020', fg=GUI_INK, relief='flat', anchor='w',
                             padx=10, justify='left', width=1, height=2)
            card.grid(row=row, column=0, sticky='nsew', pady=2)
            self.registration_cards.append(card)

        pages = tk.Frame(panel, bg=GUI_PANEL)
        pages.grid(row=4, column=0, sticky='ew')
        self.btn_registration_previous = tk.Button(pages, text="Previous", height=2,
                 command=lambda: self.change_registration_page(-1), bg='#303030', fg=GUI_INK, relief='flat')
        self.btn_registration_previous.pack(side='left')
        self.lbl_registration_page = tk.Label(pages, bg=GUI_PANEL, fg=GUI_INK)
        self.lbl_registration_page.pack(side='left', expand=True)
        self.btn_registration_next = tk.Button(pages, text="Next", height=2,
                 command=lambda: self.change_registration_page(1), bg='#303030', fg=GUI_INK, relief='flat')
        self.btn_registration_next.pack(side='right')
        self.lbl_registration_selected = tk.Label(panel, text="Select an employee card",
                 font=("Arial", 11), bg=GUI_PANEL, fg=GUI_WARN, anchor='w', wraplength=440, height=2)
        self.lbl_registration_selected.grid(row=5, column=0, sticky='ew', pady=3)
        btn_row = tk.Frame(panel, bg=GUI_PANEL)
        btn_row.grid(row=6, column=0, sticky='ew', pady=(3, 2))
        self.btn_capture = tk.Button(btn_row, text="Select employee", font=("Arial", 12, "bold"),
                 bg=GUI_BG, fg=GUI_INK, disabledforeground=GUI_MUTED, relief='flat',
                 state="disabled", height=2, command=self.save_face_data)
        self.btn_capture.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(btn_row, text="Cancel", font=("Arial", 12, "bold"),
                  bg='#781b28', fg=GUI_INK, height=2, width=8, relief='flat',
                  command=lambda: self.show_frame("MENU")).pack(side="right", fill="y")

    def registration_employees(self):
        workers = self.transport.workers() if self.transport else {}
        with self.database_lock:
            enrolled = set(self.known_ids)
        rows = [(uid, str(worker.get('name') or uid), uid in enrolled)
                for uid, worker in workers.items()
                if worker.get('active') and bool(uid in enrolled) == self.registration_registered]
        return sorted(rows, key=lambda row: (row[1].casefold(), row[0]))

    def refresh_registration(self):
        # Only reads in-memory snapshots; HTTP remains in ReliableTransport's worker.
        if self.mode != 'REGISTER':
            return
        rows = self.registration_employees()
        online = getattr(self, 'network_state', 'Connecting') == 'Online'
        self.lbl_registration_sync.config(text=('Employees sync automatically' if online
            else 'Offline / connecting - using last synced employees'))
        valid = {row[0] for row in rows}
        if self.registration_selected not in valid:
            self.registration_selected = None
        pages = max(1, (len(rows) + 2) // 3)
        self.registration_page = max(0, min(self.registration_page, pages - 1))
        selected = next((row for row in rows if row[0] == self.registration_selected), None)
        self.lbl_registration_selected.config(text=(f"Selected: {selected[1]} ({selected[0]})"
                                                    if selected else 'Select an employee card'))
        signature = (tuple(rows), self.registration_page, self.registration_selected)
        if signature != self.registration_signature:
            self.registration_signature = signature
            visible = rows[self.registration_page * 3:self.registration_page * 3 + 3]
            for index, card in enumerate(self.registration_cards):
                if index < len(visible):
                    uid, name, enrolled = visible[index]
                    status = 'Registered - tap to recapture' if enrolled else 'Ready to capture'
                    card.config(text=f"{uid}  |  {name}\n{status}", state='normal',
                                bg='#345c45' if uid == self.registration_selected else '#202020',
                                command=lambda employee_id=uid: self.select_registration_employee(employee_id))
                else:
                    card.config(text=('No registered employees' if self.registration_registered
                                      else 'No employees waiting for capture') if index == 0 and not rows else '',
                                state='disabled', bg='#202020', command=lambda: None)
            self.lbl_registration_count.config(text=f"{len(rows)} employees")
            self.lbl_registration_page.config(text=f"{self.registration_page + 1} / {pages}")
            self.btn_registration_previous.config(state='normal' if self.registration_page else 'disabled')
            self.btn_registration_next.config(state='normal' if self.registration_page + 1 < pages else 'disabled')
        self.update_registration_capture()

    def select_registration_employee(self, uid):
        if uid not in {row[0] for row in self.registration_employees()}:
            self.refresh_registration()
            return
        self.registration_selected = uid
        self.reg_face_detected = False
        self.reg_face_embedding = None
        self.reg_embedding_time = 0
        self.registration_selected_at = time.monotonic()
        self.refresh_registration()

    def toggle_registration_filter(self):
        self.registration_registered = not self.registration_registered
        self.registration_page = 0
        self.registration_selected = None
        self.btn_registration_filter.config(text='Show pending' if self.registration_registered else 'Show registered')
        self.refresh_registration()

    def change_registration_page(self, delta):
        self.registration_page += delta
        self.refresh_registration()

    def update_registration_capture(self):
        selected = self.registration_selected is not None
        fresh = (self.reg_face_detected and self.reg_face_embedding is not None
                 and time.monotonic() - self.reg_embedding_time < 1
                 and getattr(self, 'reg_capture_started', self.reg_embedding_time) > getattr(self, 'registration_selected_at', 0))
        self.btn_capture.config(state='normal' if selected and fresh else 'disabled',
                                text=('Save face' if fresh else 'Look at camera') if selected else 'Select employee',
                                bg='#781b28' if selected and fresh else GUI_BG)

    def setup_attendance(self):
        self.frame_attendance = tk.Frame(self.root, bg="black")

        # Keep camera geometry in pixels, including before the first image arrives.
        video = tk.Frame(self.frame_attendance, bg='black', width=self.display_width)
        video.pack(side='left', fill='y')
        video.pack_propagate(False)
        self.lbl_video_att = tk.Label(video, bg='black', bd=0)
        self.lbl_video_att.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Frame(video, bg=GUI_BRAND, height=4).place(x=0, y=0, relwidth=1)

        self.panel_status = tk.Frame(self.frame_attendance, bg=GUI_PANEL, padx=18, pady=12)
        self.panel_status.pack(side="right", fill="both", expand=True)

        # Reserve controls before status text is packed. Images/messages cannot
        # overlap the touch target or push it beyond the 800x480 screen.
        controls = tk.Frame(self.panel_status, bg=GUI_PANEL, height=84)
        controls.pack(side='bottom', fill='x', pady=(6, 0))
        controls.pack_propagate(False)
        self.btn_stop = tk.Button(controls, text='Stop / Menu', bg='#781b28', fg='white',
                                  activebackground='#952c3a', activeforeground='white', relief='flat', bd=0,
                                  highlightthickness=1, highlightbackground=GUI_BORDER, highlightcolor=GUI_BORDER,
                                  font=('Arial', 13, 'bold'), width=15, takefocus=True,
                                  command=self.return_to_menu)
        self.btn_stop.place(x=0, rely=.5, anchor='w', width=180, height=54)

        logo = self.get_logo_image(84, 84, GUI_PANEL)
        if logo:
            lbl_logo = tk.Label(controls, image=logo, bg=GUI_PANEL, bd=0, padx=0, pady=0)
            lbl_logo.image = logo
            lbl_logo.pack(side='right')
            self.lbl_attendance_logo = lbl_logo

        # Clock
        self.lbl_clock = tk.Label(
            self.panel_status, text="",
            font=("Arial", 9), bg=GUI_PANEL, fg=GUI_MUTED
        )
        self.lbl_clock.pack(anchor="e")
        self.lbl_health = tk.Label(self.panel_status, text='Connecting…',
                                  font=('Arial', 8), bg=GUI_PANEL, fg=GUI_WARN, wraplength=440)
        self.lbl_health.pack(anchor='e')
        self.update_clock()

        # Main status
        tk.Label(self.panel_status, text="Attendance",
                 font=("Arial", 10), bg=GUI_PANEL, fg=GUI_MUTED).pack(anchor="w", pady=(16, 4))
        self.lbl_status_main = tk.Label(
            self.panel_status, text="WAITING...",
            font=("Arial", 24, "bold"), bg=GUI_PANEL, fg=GUI_INK,
            anchor="w", justify="left"
        )
        self.lbl_status_main.pack(anchor="w", pady=(0, 4), fill="x")

        # Current IN/OUT badge
        self.lbl_current_status = tk.Label(
            self.panel_status, text="",
            font=("Arial", 12, "bold"), bg=GUI_PANEL, fg=GUI_MUTED,
            anchor="w"
        )
        self.lbl_current_status.pack(anchor="w", pady=(0, 4), fill="x")

        # Next window info
        self.lbl_next_window = tk.Label(
            self.panel_status, text="",
            font=("Arial", 10), bg=GUI_PANEL, fg=GUI_WARN,
            anchor="w", wraplength=460, justify="left"
        )
        self.lbl_next_window.pack(anchor="w", pady=(0, 4), fill="x")

        tk.Frame(self.panel_status, height=1, bg=GUI_BORDER).pack(fill="x", pady=5)

        tk.Label(self.panel_status, text="Employee",
                 font=("Arial", 10), bg=GUI_PANEL, fg=GUI_MUTED).pack(anchor="w")
        self.lbl_name_res = tk.Label(
            self.panel_status, text="-",
            font=("Arial", 20, 'bold'), bg=GUI_PANEL, fg=GUI_INK,
            anchor="w", justify="left"
        )
        self.lbl_name_res.pack(anchor="w", pady=(0, 4), fill="x")

        identity = tk.Frame(self.panel_status, bg=GUI_PANEL)
        identity.pack(anchor='w', fill='x')
        tk.Label(identity, text="ID:",
                 font=("Arial", 10), bg=GUI_PANEL, fg=GUI_MUTED).pack(side='left', padx=(0, 8))
        self.lbl_id_res = tk.Label(
            identity, text="-",
            font=("Arial", 14), bg=GUI_PANEL, fg=GUI_INK,
            anchor="w", justify="left"
        )
        self.lbl_id_res.pack(side='left', fill='x', expand=True)

    def update_clock(self):
        now = datetime.now().strftime("%d %b  %H:%M")
        self.lbl_clock.config(text=now)
        self.root.after(1000, self.update_clock)

    # ================= UTILS =================
    def auto_capitalize(self, event):
        widget = event.widget
        text = widget.get()
        titled = text.title()
        if text != titled:
            insert_cursor = widget.index("insert")
            widget.delete(0, tk.END)
            widget.insert(0, titled)
            widget.icursor(insert_cursor)

    def stop_process(self, process):
        if process and process.pid is not None:
            # Allow a worker signalled during shutdown to close Picamera2 first.
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1)

    def on_shutdown(self):
        if getattr(self, '_shutting_down', False):
            return
        self._shutting_down = True
        self._threads_running = False
        self.shutdown_requested.set()
        self.worker_stop.set()
        # Supervisors own the process handles. Let their finally blocks stop and
        # reap workers before a forced fallback; never race two join/terminate calls.
        for thread in (self.capture_thread, self.inference_thread):
            thread.join(timeout=5)
        for thread, process in ((self.capture_thread, self.camera_process),
                                (self.inference_thread, self.ai_process)):
            if thread.is_alive():
                print('[SHUTDOWN] Supervisor still stopping; terminating its worker.', flush=True)
                self.stop_process(process)
        if self.transport:
            self.transport.close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def capture_loop(self):
        while self._threads_running:
            output = self.process_context.Queue(maxsize=2)
            self.camera_state = 'recovering'
            process = self.process_context.Process(target=camera_worker, args=(output, CAM_WIDTH, CAM_HEIGHT, CAM_FPS, self.worker_stop), daemon=True)
            self.camera_process = process
            process.start()
            last_frame = time.monotonic()
            try:
                while self._threads_running and process.is_alive():
                    try:
                        kind, captured_at, frame = output.get(timeout=1)
                        if kind == 'error':
                            print('[CAMERA]', frame, flush=True)
                            self.camera_state = 'busy' if 'busy' in str(frame).lower() else 'failed'
                            break
                        with self.frame_lock:
                            self.latest_frame = frame
                            self.capture_timestamp = captured_at
                            self.frame_sequence += 1
                        self.camera_state = 'ready'
                        last_frame = time.monotonic()
                    except queue.Empty:
                        if time.monotonic() - last_frame > 8:
                            print('[CAMERA] No new frames. Restarting camera process.')
                            self.camera_state = 'stalled'
                            break
            finally:
                if self.camera_state not in ('busy', 'failed'):
                    self.camera_state = 'recovering'
                self.stop_process(process)
                output.cancel_join_thread()
                output.close()
                with self.frame_lock:
                    self.latest_frame = None
            self.shutdown_requested.wait(10 if self.camera_state in ('busy', 'failed') else 1)

    def inference_loop(self):
        while self._threads_running:
            incoming = self.process_context.Queue(maxsize=1)
            output = self.process_context.Queue(maxsize=2)
            process = self.process_context.Process(target=inference_worker, args=(incoming, output, self.worker_stop), daemon=True)
            self.ai_process = process
            self.ai_state = 'loading'
            process.start()
            started = time.monotonic()
            ready = False
            inflight = None
            last_sequence = -1
            try:
                while self._threads_running and process.is_alive():
                    try:
                        kind, sequence, result = output.get(timeout=.05)
                        if kind == 'ready':
                            ready = True
                            self.ai_state = 'ready'
                        elif kind == 'error':
                            print('[AI]', result)
                            self.ai_state = 'recovering'
                            break
                        elif kind == 'result':
                            job_mode, job_time = inflight[1], inflight[2]
                            inflight = None
                            if self.mode == job_mode and time.monotonic() - job_time < 3:
                                faces = [SimpleNamespace(**f) for f in result]
                                if job_mode == 'REGISTER':
                                    self.process_register(faces, job_time)
                                elif job_mode == 'ATTENDANCE':
                                    self.process_attendance(faces)
                    except queue.Empty:
                        pass
                    if not ready and time.monotonic() - started > 90:
                        print('[AI] Model startup stalled. Restarting.')
                        break
                    if inflight and time.monotonic() - inflight[2] > 20:
                        print('[AI] Inference stalled. Restarting.')
                        break
                    if ready and inflight is None and self.mode in ('REGISTER', 'ATTENDANCE'):
                        with self.frame_lock:
                            sequence = self.frame_sequence
                            age = time.monotonic() - self.capture_timestamp
                            frame = None if self.latest_frame is None else self.latest_frame.copy()
                        if frame is not None and age < 1 and sequence != last_sequence:
                            resized = cv2.resize(frame, (self.display_width, self.display_height))
                            inflight = (sequence, self.mode, time.monotonic())
                            put_latest(incoming, (sequence, resized))
                            last_sequence = sequence
            except Exception as exc:
                print('[AI supervisor]', type(exc).__name__, str(exc))
            finally:
                self.ai_state = 'recovering'
                self.att_overlays = []
                self.reg_overlays = []
                self.reg_face_embedding = None
                self.reg_face_detected = False
                self.stop_process(process)
                for channel in (incoming, output):
                    channel.cancel_join_thread()
                    channel.close()
            self.shutdown_requested.wait(2)

    # ================= DISPLAY LOOP (main thread) =================
    def update_display(self):
        if self.mode in ("REGISTER", "ATTENDANCE"):
            with self.frame_lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()
            if frame is not None and time.monotonic() - self.capture_timestamp < 2:
                disp = cv2.resize(frame, (self.display_width, self.display_height))   # RGB already

                if self.mode == "REGISTER":
                    h, w, _ = disp.shape
                    cx, cy = w // 2, h // 2
                    cv2.rectangle(disp, (cx-80, cy-100), (cx+80, cy+100), CV_GREY, 1)
                    self._draw_overlays(disp, self.reg_overlays)
                    img = ImageTk.PhotoImage(image=Image.fromarray(disp))
                    self.lbl_video_reg.configure(image=img, text='')
                    self.lbl_video_reg.image = img
                else:
                    self._draw_overlays(disp, self.att_overlays)
                    img = ImageTk.PhotoImage(image=Image.fromarray(disp))
                    self.lbl_video_att.configure(image=img, text='')
                    self.lbl_video_att.image = img
            else:
                label = self.lbl_video_reg if self.mode == 'REGISTER' else self.lbl_video_att
                label.configure(image='', text='Camera reconnecting…', fg='#f2c67b', font=('Arial', 11))
                label.image = None

        self.root.after(30, self.update_display)   # display decoupled from AI

    def _draw_overlays(self, disp, overlays):
        for ov in list(overlays):
            box, color, label, tcolor = ov["box"], ov["color"], ov["label"], ov["tcolor"]
            cv2.rectangle(disp, (box[0], box[1]), (box[2], box[3]), color, 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(disp, (box[0], box[1]-20), (box[0]+tw, box[1]), color, -1)
            cv2.putText(disp, label, (box[0], box[1]-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, tcolor, 1)

    # ================= REGISTER LOGIC (runs in inference thread) =================
    def process_register(self, faces, captured_at=None):
        """analysis_frame = BGR (for InsightFace). Boxes are in display coords."""

        if len(faces) == 1 and (captured_at is None or captured_at > getattr(self, 'registration_selected_at', 0)):
            self.reg_capture_started = captured_at if captured_at is not None else time.monotonic()
            self.reg_face_detected = True
            self.reg_face_embedding = faces[0].embedding.copy()
            self.reg_embedding_time = time.monotonic()
            box = faces[0].bbox.astype(int)
            self.reg_overlays = [dict(box=box, color=CV_GREEN,
                                      label="FACE DETECTED", tcolor=(255, 255, 255))]
            self.ui(self.update_registration_capture)
        else:
            self.reg_face_detected = False
            self.reg_face_embedding = None
            self.reg_overlays = []
            self.ui(self.update_registration_capture)

    # ================= ATTENDANCE LOGIC (runs in inference thread) =================
    def process_attendance(self, faces):
        """analysis_frame = BGR (for InsightFace). Boxes are in display coords."""
        if len(faces) != 1:
            self.candidate_uid = None
            self.candidate_count = 0
            self.att_overlays = []
            if self.face_absent_since is None:
                self.face_absent_since = time.monotonic()
            if time.monotonic() - self.face_absent_since >= 3:
                self.latched_uid = None
            if time.time() - self.last_success_time > SUCCESS_DISPLAY_TIME:
                def waiting():
                    self.lbl_status_main.config(text='Ready to scan' if not faces else 'One person at a time', fg=GUI_INK)
                    self.lbl_current_status.config(text='', fg=GUI_MUTED)
                    self.lbl_next_window.config(text='', fg=GUI_WARN)
                    self.lbl_name_res.config(text='-', fg=GUI_INK)
                    self.lbl_id_res.config(text='-', fg=GUI_INK)
                self.ui(waiting)
            return
        self.face_absent_since = None
        with self.database_lock:
            known_matrix, known_ids, known_names = self.known_matrix, self.known_ids, self.known_names

        found_someone = False
        success_screen_active = (time.time() - self.last_success_time) <= SUCCESS_DISPLAY_TIME
        overlays = []

        for face in faces:
            box = face.bbox.astype(int)
            box_color = CV_YELLOW
            label = "UNKNOWN"

            if known_matrix is not None:
                norm = np.linalg.norm(face.embedding)
                if norm == 0:
                    continue
                sims = np.dot(known_matrix, face.embedding / norm)
                best_idx = int(np.argmax(sims))

                margin = float(sims[best_idx] - np.partition(sims, -2)[-2]) if len(sims) > 1 else 1
                if sims[best_idx] > SIMILARITY_THRESHOLD and margin > .08 and face.det_score > .7:
                    uid  = known_ids[best_idx]
                    name = known_names[best_idx]
                    found_someone = True
                    label = "DETECTED"

                    last = self.scan_memory.get(uid, 0)
                    elapsed = time.time() - last

                    worker = self.transport.workers().get(str(uid)) if self.transport else None
                    if not worker or not worker.get('active'):
                        label = 'EMPLOYEE NOT ACTIVE'
                        continue
                    if self.candidate_uid == uid:
                        self.candidate_count += 1
                    else:
                        self.candidate_uid, self.candidate_count = uid, 1
                    cooldown = self.transport.cooldown_seconds if self.transport else COOLDOWN_SECONDS
                    if elapsed > cooldown and self.candidate_count >= 3 and uid != self.latched_uid:
                        # Valid scan
                        box_color = CV_GREEN
                        self.trigger_success(uid, name)
                        success_screen_active = True

                    elif elapsed <= cooldown:
                        # Cooldown active
                        box_color = CV_YELLOW
                        label = "COOLDOWN"

                        if not success_screen_active:
                            current_status = self.get_worker_status(uid)

                            if current_status == 'IN':
                                status_text  = "CURRENTLY: CLOCKED IN ✓"
                                status_color = GUI_ACCENT
                            elif current_status == 'OUT':
                                status_text  = "CURRENTLY: CLOCKED OUT"
                                status_color = GUI_ERR
                            else:
                                status_text  = "CURRENTLY: UNKNOWN"
                                status_color = "#888"

                            next_window_text = self.get_next_window_text(uid)

                            def _apply(st=status_text, sc=status_color,
                                       nw=next_window_text, nm=name, u=uid):
                                self.lbl_status_main.config(text="Already recorded", fg=GUI_WARN)
                                self.lbl_current_status.config(text=st, fg=sc)
                                self.lbl_next_window.config(text=nw, fg=GUI_WARN)
                                self.lbl_name_res.config(text=nm, fg=GUI_WARN)
                                self.lbl_id_res.config(text=u, fg=GUI_WARN)
                            self.ui(_apply)

            text_color = (0, 0, 0) if box_color in (CV_GREEN, CV_YELLOW) else (255, 255, 255)
            overlays.append(dict(box=box, color=box_color, label=label, tcolor=text_color))

        self.att_overlays = overlays

        if not success_screen_active and not found_someone:
            def _idle():
                self.lbl_status_main.config(text="Ready to scan", fg=GUI_INK)
                self.lbl_current_status.config(text="", fg=GUI_MUTED)
                self.lbl_next_window.config(text="", fg=GUI_WARN)
                self.lbl_name_res.config(text="-", fg=GUI_INK)
                self.lbl_id_res.config(text="-", fg=GUI_INK)
            self.ui(_idle)

    def trigger_success(self, uid, name):
        if not self.transport:
            return
        try:
            event_id, created = self.transport.submit(uid, name)
        except Exception as exc:
            print('[OUTBOX]', str(exc))
            self.ui(lambda: self.lbl_status_main.config(text='Scan not saved', fg=GUI_ERR))
            return
        self.scan_memory[uid] = time.time()
        self.last_success_time = time.time()
        self.pending_names[uid] = name
        self.latched_uid = uid
        if not created and self.transport.confirmation(event_id):
            self.on_scan_result(uid, {'action':'DUPLICATE','message':'This scan was already confirmed.', 'flags':[]})
            return
        def apply():
            self.lbl_status_main.config(text='Scan saved', fg=GUI_TEAL, font=('Arial', 24, 'bold'))
            self.lbl_current_status.config(text='Awaiting confirmation', fg=GUI_WARN)
            self.lbl_next_window.config(text='Retries automatically offline', fg=GUI_WARN)
            self.lbl_name_res.config(text=name, fg=GUI_TEAL)
            self.lbl_id_res.config(text=uid, fg=GUI_TEAL)
        self.ui(apply)

    def return_to_menu(self, source='STOP button'):
        print(f'[UI] Menu requested via {source}; previous mode={self.mode}', flush=True)
        self.mode = 'MENU'
        self.candidate_uid = None
        self.candidate_count = 0
        self.show_frame('MENU')

    def show_frame(self, mode):
        self.frame_menu.pack_forget()
        self.frame_register.pack_forget()
        self.frame_attendance.pack_forget()

        self.lbl_status_main.config(text="Ready to scan", fg=GUI_INK, font=('Arial', 24, 'bold'))
        self.lbl_current_status.config(text="", fg=GUI_MUTED)
        self.lbl_next_window.config(text="", fg=GUI_WARN)
        self.lbl_name_res.config(text="-", fg=GUI_INK)
        self.lbl_id_res.config(text="-",   fg=GUI_INK)
        self.last_success_time = 0
        self.att_overlays = []
        self.reg_overlays = []

        self.mode = mode
        if mode == "MENU":
            self.frame_menu.pack(fill="both", expand=True)
            self.root.focus_force()
        elif mode == "REGISTER":
            self.reg_face_embedding = None
            self.reg_face_detected = False
            self.registration_selected = None
            self.registration_page = 0
            self.registration_registered = False
            self.btn_registration_filter.config(text='Show registered')
            self.reload_database()
            self.frame_register.pack(fill="both", expand=True)
            self.root.focus_force()
            self.refresh_registration()
        elif mode == "ATTENDANCE":
            self.reload_database()
            self.frame_attendance.pack(fill="both", expand=True)

    def reload_database(self):
        embeddings, ids, names = [], [], []
        for path in Path(DB_PATH).glob('*.npy'):
            try:
                embedding = np.load(path, allow_pickle=False)
                if embedding.shape != (512,) or not np.all(np.isfinite(embedding)) or np.linalg.norm(embedding) == 0:
                    raise ValueError('invalid embedding')
                uid, _, name = path.stem.partition('_')
                embeddings.append(embedding / np.linalg.norm(embedding))
                ids.append(uid)
                names.append(name or uid)
            except Exception as exc:
                print('[DB] Skipping', path.name, type(exc).__name__)
        matrix = np.asarray(embeddings) if embeddings else None
        with self.database_lock:
            self.known_matrix, self.known_ids, self.known_names = matrix, ids, names
        print(f'[DB] Loaded {len(ids)} face registrations')

    def save_face_data(self):
        uid = self.registration_selected or ''
        worker = self.transport.workers().get(uid) if self.transport else None
        name = str(worker.get('name') or uid) if worker else ''

        if not uid:
            messagebox.showwarning('SELECT EMPLOYEE', 'Select an employee card first.', parent=self.root)
            return
        if not re.fullmatch(r"[A-Za-z0-9-]{1,40}", uid):
            messagebox.showwarning('INVALID EMPLOYEE ID', 'Correct this employee ID in the React system first.', parent=self.root)
            return

        if not worker or not worker.get('active'):
            messagebox.showwarning('EMPLOYEE NOT FOUND', 'Add this employee in the React app first, then wait for the kiosk to sync.', parent=self.root)
            return
        captured_at = self.reg_embedding_time
        embedding = self.reg_face_embedding
        if not self.reg_face_detected or embedding is None or (time.monotonic() - captured_at > 1 or getattr(self, 'reg_capture_started', captured_at) <= getattr(self, 'registration_selected_at', 0)):
            messagebox.showwarning('LOOK AT CAMERA', 'A fresh face capture is required.', parent=self.root)
            return
        name = re.sub(r'[^A-Za-z0-9 -]', '', name) or uid
        existing = [f for f in os.listdir(DB_PATH) if f.startswith(uid + "_")]
        if existing:
            if not messagebox.askyesno(
                "DUPLICATE ID",
                f"ID '{uid}' already exists.\nOverwrite the existing record?",
                parent=self.root
            ):
                return

        if embedding is not None:
            embedding = embedding.copy()
            target = Path(DB_PATH) / f'{uid}_{name}.npy'
            temporary = target.with_suffix('.tmp')
            try:
                with open(temporary, 'wb') as file:
                    np.save(file, embedding)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, target)
                for old_file in existing:
                    if old_file != target.name:
                        os.remove(os.path.join(DB_PATH, old_file))
            except OSError as exc:
                messagebox.showerror('SAVE FAILED', f'Face was not fully saved. Please retry.\n{exc}', parent=self.root)
                return
            messagebox.showinfo("SAVED", f"User '{name}' registered successfully!", parent=self.root)
            self.reload_database()
            self.registration_selected = None
            self.reg_face_embedding = None
            self.reg_face_detected = False
            self.refresh_registration()
        else:
            messagebox.showwarning("NO FACE", "No face detected. Please look at the camera.", parent=self.root)


def run_kiosk():
    def request_exit(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, request_exit)
    app = None
    try:
        root = tk.Tk()
        app = SmartAttendanceSystem(root)
        root.mainloop()
    except KeyboardInterrupt:
        print('[SHUTDOWN] Stopping kiosk and camera/AI workers.', flush=True)
    finally:
        if app is not None:
            app.on_shutdown()
        # Also clean workers if initialization was interrupted before app existed.
        for child in mp.active_children():
            child.terminate()
            child.join(timeout=2)
            if child.is_alive():
                child.kill()
                child.join(timeout=1)


if __name__ == "__main__":
    mp.freeze_support()
    try:
        with kiosk_instance():
            run_kiosk()
    except KioskAlreadyRunning as exc:
        print(f'[STARTUP] {exc}', flush=True)
