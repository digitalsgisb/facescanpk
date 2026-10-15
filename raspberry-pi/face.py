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
import re
from pathlib import Path
from types import SimpleNamespace
from kiosk_transport import ReliableTransport
from kiosk_config import load_config
from kiosk_keyboard import TouchKeyboard
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
SCREEN_W = 800
SCREEN_H = 480

# --- CAMERA CONFIG ---
CAM_WIDTH = 640
CAM_HEIGHT = 360
CAM_FPS = 15

# --- COLORS (RGB - frames are RGB after channel swap) ---
GUI_BG     = "#000000"
GUI_PANEL  = "#1e1e1e"
GUI_ACCENT = "#00ff00"
GUI_WARN   = "#ffcc00"
GUI_ERR    = "#ff0000"
GUI_TEAL   = "#00bcd4"
CV_GREEN  = (0, 255, 0)       # RGB Green
CV_YELLOW = (255, 255, 0)     # RGB Yellow
CV_RED    = (255, 0, 0)       # RGB Red
CV_GREY   = (100, 100, 100)

if not os.path.exists(DB_PATH):
    os.makedirs(DB_PATH)

class SmartAttendanceSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Attendance Kiosk")

        # --- FULLSCREEN KIOSK ---
        # IMPORTANT: use the '-fullscreen' attribute, NOT overrideredirect(True).
        # overrideredirect bypasses the window manager, so the window never gets
        # KEYBOARD FOCUS (you can't type in the Entry fields) and popup dialogs
        # (messagebox) open HIDDEN BEHIND the window. Fullscreen keeps the WM in
        # charge while still hiding all decorations.
        # DSI-1 is 800x480 at (0,0); HDMI starts at (800,0).
        # Screen dimensions can describe the combined desktop. Map onto DSI first
        # so the window manager chooses the touchscreen for fullscreen.
        self.root.configure(bg=GUI_BG)
        self.root.geometry(f"{SCREEN_W}x{SCREEN_H}+0+0")
        self.root.update()
        self.root.attributes("-fullscreen", True)
        self.root.attributes('-topmost', True)

        self.root.configure(bg=GUI_BG)
        self.root.update_idletasks()
        self.root.focus_force()
        self.root.bind("<Escape>", lambda e: self.return_to_menu('Escape'))

        # Native calls run in separate processes and can be restarted on a stall.
        self.process_context = mp.get_context('spawn')
        self.camera_process = None
        self.ai_process = None
        self.camera_state = 'starting'
        self.ai_state = 'starting'
        self.ui_queue = queue.Queue(maxsize=50)
        self.database_lock = threading.Lock()
        self.capture_timestamp = 0
        self.frame_sequence = 0
        self.reg_embedding_time = 0
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
        self.active_entry = None          # which field the on-screen keyboard types into

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
        self.reload_database()

        # --- START BACKGROUND THREADS ---
        threading.Thread(target=self.capture_loop,   daemon=True).start()
        threading.Thread(target=self.inference_loop, daemon=True).start()

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
            self.transport.camera_health = self.camera_state
            self.transport.ai_health = self.ai_state
        network = getattr(self, 'network_state', 'Connecting')
        pending = getattr(self, 'pending_count', 0)
        health = f'{network} · queued: {pending} · camera: {self.camera_state} · AI: {self.ai_state}'
        if hasattr(self, 'lbl_health'):
            self.lbl_health.config(text=health, fg='#a8bd91' if network == 'Online' else GUI_WARN)
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
            return 'Working hours not assigned · scan kept for review'
        return f'{schedule["name"]}: {schedule["start"]} – {schedule["end"]}'

    def on_scan_result(self, uid, result):
        worker = self.transport.workers().get(uid, {}) if self.transport else {}
        name = worker.get('name') or self.pending_names.get(uid, uid)
        action = result['action']
        if action in ('IN', 'OUT'):
            title = 'CLOCK-IN CONFIRMED' if action == 'IN' else 'CLOCK-OUT CONFIRMED'
            color = GUI_ACCENT
        elif action == 'REVIEW':
            title, color = 'SAVED · NEEDS REVIEW', GUI_WARN
        elif action == 'DUPLICATE':
            title, color = 'ALREADY RECORDED', GUI_WARN
        else:
            title, color = 'SCAN NOT ACCEPTED', GUI_ERR
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
        self.frame_menu = tk.Frame(self.root, bg=GUI_BG)

        tk.Label(self.frame_menu, text="E-ATTENDANCE SYSTEM",
                 font=("Arial", 24, "bold"), bg=GUI_BG, fg=GUI_ACCENT).pack(pady=(24, 18))

        btn_style = {"font": ("Arial", 16, "bold"), "width": 25, "height": 2, "bd": 0}

        tk.Button(self.frame_menu, text="START SCANNING",
                  bg="#008000", fg="white",
                  command=lambda: self.show_frame("ATTENDANCE"), **btn_style).pack(pady=8)

        tk.Button(self.frame_menu, text="REGISTER NEW USER",
                  bg="#0055aa", fg="white",
                  command=lambda: self.show_frame("REGISTER"), **btn_style).pack(pady=8)

        tk.Button(self.frame_menu, text="SHUTDOWN",
                  bg="#550000", fg="white",
                  command=self.on_shutdown, **btn_style).pack(pady=8)

        logo = self.get_logo_image(150, 150, GUI_BG)
        if logo:
            lbl_logo = tk.Label(self.frame_menu, image=logo, bg=GUI_BG)
            lbl_logo.image = logo
            lbl_logo.place(relx=1.0, x=-30, rely=1.0, y=-30, anchor="se")

    def setup_register(self):
        self.frame_register = tk.Frame(self.root, bg=GUI_BG)

        # Pixel-sized container: Label width/height otherwise use text units before the first image.
        video = tk.Frame(self.frame_register, bg='black', width=self.display_width)
        video.pack(side='left', fill='y')
        video.pack_propagate(False)
        self.lbl_video_reg = tk.Label(video, bg='black', bd=0)
        self.lbl_video_reg.place(relx=0, rely=0, relwidth=1, relheight=1)

        panel = tk.Frame(self.frame_register, bg=GUI_PANEL, padx=10, pady=4)
        panel.pack(side="right", fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(5, weight=1)

        tk.Label(panel, text="NEW REGISTRATION",
                 font=("Arial", 16, "bold"), bg=GUI_PANEL, fg="white").grid(row=0, column=0, sticky='ew', pady=(0, 4))

        # USER ID (tap to select, use on-screen keyboard below)
        tk.Label(panel, text="USER ID", font=("Arial", 10), bg=GUI_PANEL, fg="#aaa").grid(row=1, column=0, sticky='w')
        self.entry_id = tk.Entry(panel, width=1, font=("Arial", 14), bg="#333", fg="white", insertbackground="white")
        self.entry_id.grid(row=2, column=0, sticky='ew', pady=(0, 4))
        self.entry_id.bind("<Button-1>", lambda e: self._set_active(self.entry_id))
        self.entry_id.bind("<FocusIn>",  lambda e: self._set_active(self.entry_id))

        # FULL NAME
        tk.Label(panel, text="FULL NAME", font=("Arial", 10), bg=GUI_PANEL, fg="#aaa").grid(row=3, column=0, sticky='w')
        self.entry_name = tk.Entry(panel, width=1, font=("Arial", 14), bg="#333", fg="white", insertbackground="white")
        self.entry_name.grid(row=4, column=0, sticky='ew', pady=(0, 3))
        self.entry_name.bind("<Button-1>", lambda e: self._set_active(self.entry_name))
        self.entry_name.bind("<FocusIn>",  lambda e: self._set_active(self.entry_name))

        # ON-SCREEN KEYBOARD (touchscreen kiosk - no physical keyboard)
        self.build_keyboard(panel)

        # SAVE + CANCEL side by side (saves vertical space)
        btn_row = tk.Frame(panel, bg=GUI_PANEL)
        btn_row.grid(row=6, column=0, sticky='ew', pady=(3, 2))
        self.btn_capture = tk.Button(
            btn_row, text="WAITING FOR FACE...",
            font=("Arial", 13, "bold"), bg="#444", fg="#888",
            state="disabled", height=2, command=self.save_face_data
        )
        self.btn_capture.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(btn_row, text="CANCEL", font=("Arial", 12, "bold"),
                  bg="#cc0000", fg="white", height=2, width=8,
                  command=lambda: self.show_frame("MENU")).pack(side="right", fill="y")

    # ================= ON-SCREEN KEYBOARD =================
    def build_keyboard(self, parent):
        self.keyboard = TouchKeyboard(parent, self._kb_insert, self._kb_backspace, self._kb_clear, GUI_PANEL)
        self.keyboard.grid(row=5, column=0, sticky='nsew', pady=2)

    def _set_active(self, entry):
        self.active_entry = entry
        entry.focus_set()

    def _active(self):
        e = getattr(self, "active_entry", None)
        return e if e is not None else self.entry_id

    def _kb_normalize(self, e):
        """Title-case the field (matches old auto_capitalize) and keep cursor at end."""
        text = e.get()
        titled = text.title()
        if text != titled:
            e.delete(0, tk.END)
            e.insert(0, titled)
        e.icursor(tk.END)

    def _kb_insert(self, ch):
        e = self._active()
        e.insert(tk.INSERT, ch.lower() if ch.isalpha() else ch)
        self._kb_normalize(e)

    def _kb_backspace(self):
        e = self._active()
        cur = e.index(tk.INSERT)
        if cur > 0:
            e.delete(cur - 1, cur)

    def _kb_clear(self):
        self._active().delete(0, tk.END)

    def setup_attendance(self):
        self.frame_attendance = tk.Frame(self.root, bg="black")

        # Keep camera geometry in pixels, including before the first image arrives.
        video = tk.Frame(self.frame_attendance, bg='black', width=self.display_width)
        video.pack(side='left', fill='y')
        video.pack_propagate(False)
        self.lbl_video_att = tk.Label(video, bg='black', bd=0)
        self.lbl_video_att.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.panel_status = tk.Frame(self.frame_attendance, bg="#101010", padx=20, pady=20)
        self.panel_status.pack(side="right", fill="both", expand=True)

        # Reserve controls before status text is packed. Images/messages cannot
        # overlap the touch target or push it beyond the 800x480 screen.
        controls = tk.Frame(self.panel_status, bg='#101010', height=54)
        controls.pack(side='bottom', fill='x', pady=(6, 0))
        controls.pack_propagate(False)
        self.btn_stop = tk.Button(controls, text='STOP / MENU', bg='#cc0000', fg='white',
                                  font=('Arial', 13, 'bold'), width=15, takefocus=True,
                                  command=self.return_to_menu)
        self.btn_stop.pack(side='left', fill='y', padx=(0, 10))

        logo = self.get_logo_image(54, 48, "#101010")
        if logo:
            lbl_logo = tk.Label(controls, image=logo, bg="#101010")
            lbl_logo.image = logo
            lbl_logo.pack(side='right')

        # Clock
        self.lbl_clock = tk.Label(
            self.panel_status, text="",
            font=("Arial", 11), bg="#101010", fg="#555"
        )
        self.lbl_clock.pack(anchor="e")
        self.lbl_health = tk.Label(self.panel_status, text='Starting camera and AI…',
                                  font=('Arial', 8), bg='#101010', fg=GUI_WARN, wraplength=440)
        self.lbl_health.pack(anchor='e')
        self.update_clock()

        # Main status
        tk.Label(self.panel_status, text="STATUS:",
                 font=("Arial", 12), bg="#101010", fg="#888").pack(anchor="w")
        self.lbl_status_main = tk.Label(
            self.panel_status, text="WAITING...",
            font=("Arial", 30, "bold"), bg="#101010", fg="white",
            anchor="w", justify="left"
        )
        self.lbl_status_main.pack(anchor="w", pady=(0, 6), fill="x")

        # Current IN/OUT badge
        self.lbl_current_status = tk.Label(
            self.panel_status, text="",
            font=("Arial", 13, "bold"), bg="#101010", fg="#555",
            anchor="w"
        )
        self.lbl_current_status.pack(anchor="w", pady=(0, 6), fill="x")

        # Next window info
        self.lbl_next_window = tk.Label(
            self.panel_status, text="",
            font=("Arial", 12), bg="#101010", fg=GUI_WARN,
            anchor="w", wraplength=280, justify="left"
        )
        self.lbl_next_window.pack(anchor="w", pady=(0, 8), fill="x")

        tk.Frame(self.panel_status, height=2, bg="#333").pack(fill="x", pady=8)

        tk.Label(self.panel_status, text="NAME:",
                 font=("Arial", 12), bg="#101010", fg="#888").pack(anchor="w")
        self.lbl_name_res = tk.Label(
            self.panel_status, text="-",
            font=("Arial", 22), bg="#101010", fg=GUI_ACCENT,
            anchor="w", justify="left"
        )
        self.lbl_name_res.pack(anchor="w", pady=(0, 10), fill="x")

        tk.Label(self.panel_status, text="ID:",
                 font=("Arial", 12), bg="#101010", fg="#888").pack(anchor="w")
        self.lbl_id_res = tk.Label(
            self.panel_status, text="-",
            font=("Arial", 22), bg="#101010", fg=GUI_ACCENT,
            anchor="w", justify="left"
        )
        self.lbl_id_res.pack(anchor="w", fill="x")

    def update_clock(self):
        now = datetime.now().strftime("%d %b %Y  %H:%M:%S")
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
        if process and process.is_alive():
            process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)

    def on_shutdown(self):
        self._threads_running = False
        if self.transport:
            self.transport.close()
        self.stop_process(self.camera_process)
        self.stop_process(self.ai_process)
        self.root.destroy()

    def capture_loop(self):
        while self._threads_running:
            output = self.process_context.Queue(maxsize=2)
            self.camera_state = 'recovering'
            process = self.process_context.Process(target=camera_worker, args=(output, CAM_WIDTH, CAM_HEIGHT, CAM_FPS), daemon=True)
            self.camera_process = process
            process.start()
            last_frame = time.monotonic()
            try:
                while self._threads_running and process.is_alive():
                    try:
                        kind, captured_at, frame = output.get(timeout=1)
                        if kind == 'error':
                            print('[CAMERA]', frame)
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
                self.camera_state = 'recovering'
                self.stop_process(process)
                output.cancel_join_thread()
                output.close()
                with self.frame_lock:
                    self.latest_frame = None
            time.sleep(1)

    def inference_loop(self):
        while self._threads_running:
            incoming = self.process_context.Queue(maxsize=1)
            output = self.process_context.Queue(maxsize=2)
            process = self.process_context.Process(target=inference_worker, args=(incoming, output), daemon=True)
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
                                    self.process_register(faces)
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
            time.sleep(2)

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
                label.configure(image='', text='CAMERA RESTARTING…', fg=GUI_WARN, font=('Arial', 12))
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
    def process_register(self, faces):
        """analysis_frame = BGR (for InsightFace). Boxes are in display coords."""

        if len(faces) == 1:
            self.reg_face_detected = True
            self.reg_face_embedding = faces[0].embedding.copy()
            self.reg_embedding_time = time.monotonic()
            box = faces[0].bbox.astype(int)
            self.reg_overlays = [dict(box=box, color=CV_GREEN,
                                      label="FACE DETECTED", tcolor=(255, 255, 255))]
            self.ui(lambda: self.btn_capture.config(bg=GUI_ACCENT, fg="black",
                                                    state="normal", text="SAVE USER"))
        else:
            self.reg_face_detected = False
            self.reg_face_embedding = None
            self.reg_overlays = []
            self.ui(lambda: self.btn_capture.config(bg="#444", fg="#888",
                                                    state="disabled", text="LOOK AT CAMERA"))

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
                    self.lbl_status_main.config(text='SCANNING...' if not faces else 'ONE PERSON AT A TIME', fg='white')
                    self.lbl_current_status.config(text='', fg='#555')
                    self.lbl_next_window.config(text='', fg=GUI_WARN)
                    self.lbl_name_res.config(text='-', fg=GUI_ACCENT)
                    self.lbl_id_res.config(text='-', fg=GUI_ACCENT)
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
                                self.lbl_status_main.config(text="ALREADY SCANNED", fg=GUI_WARN)
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
                self.lbl_status_main.config(text="SCANNING...", fg="white")
                self.lbl_current_status.config(text="", fg="#555")
                self.lbl_next_window.config(text="", fg=GUI_WARN)
                self.lbl_name_res.config(text="-", fg=GUI_ACCENT)
                self.lbl_id_res.config(text="-", fg=GUI_ACCENT)
            self.ui(_idle)

    def trigger_success(self, uid, name):
        if not self.transport:
            return
        try:
            event_id, created = self.transport.submit(uid, name)
        except Exception as exc:
            print('[OUTBOX]', str(exc))
            self.ui(lambda: self.lbl_status_main.config(text='SCAN NOT SAVED', fg=GUI_ERR))
            return
        self.scan_memory[uid] = time.time()
        self.last_success_time = time.time()
        self.pending_names[uid] = name
        self.latched_uid = uid
        if not created and self.transport.confirmation(event_id):
            self.on_scan_result(uid, {'action':'DUPLICATE','message':'This scan was already confirmed.', 'flags':[]})
            return
        def apply():
            self.lbl_status_main.config(text='SCAN SAVED LOCALLY', fg=GUI_TEAL, font=('Arial', 24, 'bold'))
            self.lbl_current_status.config(text='Waiting for attendance confirmation…', fg=GUI_WARN)
            self.lbl_next_window.config(text='Will retry automatically if the PC is offline', fg=GUI_WARN)
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

        self.lbl_status_main.config(text="WAITING...", fg="white")
        self.lbl_current_status.config(text="", fg="#555")
        self.lbl_next_window.config(text="", fg=GUI_WARN)
        self.lbl_name_res.config(text="-", fg=GUI_ACCENT)
        self.lbl_id_res.config(text="-",   fg=GUI_ACCENT)
        self.last_success_time = 0
        self.att_overlays = []
        self.reg_overlays = []

        self.mode = mode
        if mode == "MENU":
            self.frame_menu.pack(fill="both", expand=True)
            self.root.focus_force()
        elif mode == "REGISTER":
            self.reg_face_embedding = None
            self.entry_id.delete(0, tk.END)
            self.entry_name.delete(0, tk.END)
            self.frame_register.pack(fill="both", expand=True)
            self.root.focus_force()
            self._set_active(self.entry_id)   # ID field ready for on-screen keyboard
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
        uid  = self.entry_id.get().strip()
        name = self.entry_name.get().strip()

        if not re.fullmatch(r"[A-Za-z0-9-]{1,40}", uid):
            messagebox.showwarning("MISSING INFO", "Use a valid employee ID (letters, numbers or hyphens).", parent=self.root)
            return
        if not name:
            messagebox.showwarning("MISSING INFO", "Please enter a Name!", parent=self.root)
            return

        worker = self.transport.workers().get(uid) if self.transport else None
        if not worker or not worker.get('active'):
            messagebox.showwarning('EMPLOYEE NOT FOUND', 'Add this employee in the React app first, then wait for the kiosk to sync.', parent=self.root)
            return
        if not self.reg_face_detected or self.reg_face_embedding is None or time.monotonic() - self.reg_embedding_time > 1:
            messagebox.showwarning('LOOK AT CAMERA', 'A fresh face capture is required.', parent=self.root)
            return
        name = re.sub(r'[^A-Za-z0-9 -]', '', worker['name'])
        existing = [f for f in os.listdir(DB_PATH) if f.startswith(uid + "_")]
        if existing:
            if not messagebox.askyesno(
                "DUPLICATE ID",
                f"ID '{uid}' already exists.\nOverwrite the existing record?",
                parent=self.root
            ):
                return

        if self.reg_face_embedding is not None:
            embedding = self.reg_face_embedding.copy()
            target = Path(DB_PATH) / f'{uid}_{name}.npy'
            temporary = target.with_suffix('.tmp')
            with open(temporary, 'wb') as file:
                np.save(file, embedding)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
            for old_file in existing:
                if old_file != target.name:
                    os.remove(os.path.join(DB_PATH, old_file))
            messagebox.showinfo("SAVED", f"User '{name}' registered successfully!", parent=self.root)
            self.show_frame("MENU")
        else:
            messagebox.showwarning("NO FACE", "No face detected. Please look at the camera.", parent=self.root)


if __name__ == "__main__":
    mp.freeze_support()
    root = tk.Tk()
    app = SmartAttendanceSystem(root)
    root.mainloop()
