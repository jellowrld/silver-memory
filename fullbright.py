import json
import os
import threading
import time
import ctypes
from ctypes import wintypes

import dxcam
import numpy as np
import pyglet
from pyglet.gl import *
import psutil

import win32api
import win32con
import win32gui
import win32process

# Optional: OpenCV for nicer thermal effect (Standard mode only)
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# Optional: DDC/CI monitor brightness
try:
    from monitorcontrol import get_monitors
    HAS_MONITORCONTROL = True
except ImportError:
    HAS_MONITORCONTROL = False

# Optional: registry access for HDR status
try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

# ---------------- CONFIG / CONSTANTS ----------------

CONFIG_FILE = "fullbright_config.json"

# Default overlay behavior
BRIGHTNESS = 1.8      # 1.0 = normal
GAMMA = 0.6           # <1.0 = brighter
OPACITY = 1.0         # 0..1 overlay strength
MODE = "overlay"      # "overlay" or "system_gamma"
EFFECT = "normal"     # "normal", "night_vision", "thermal"
PERFORMANCE_MODE = "standard"  # "standard" or "ultra" (no OpenCV)

TARGET_FPS = 120
PRIMARY_MONITOR_INDEX = 0      # dxcam monitor index

# Global defaults captured at startup
monitor_default_gamma_ramp = None
monitor_default_brightness_ddc = None

# State
current_game = None
config = {}
overlay_instance = None  # set once overlay is created


# ---------------- UTILITIES: CONFIG ----------------

def load_config():
    global config, BRIGHTNESS, GAMMA, MODE, EFFECT, OPACITY, PERFORMANCE_MODE, PRIMARY_MONITOR_INDEX
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except Exception:
            config = {}
    else:
        config = {}

    if "profiles" not in config:
        config["profiles"] = {}
    if "global" not in config["profiles"]:
        config["profiles"]["global"] = {
            "brightness": BRIGHTNESS,
            "gamma": GAMMA,
            "mode": MODE,
            "effect": EFFECT,
            "opacity": OPACITY,
            "performance_mode": PERFORMANCE_MODE,
            "monitor_index": PRIMARY_MONITOR_INDEX
        }

def save_config():
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print("Failed to save config:", e)

def apply_profile(profile_name):
    global BRIGHTNESS, GAMMA, MODE, EFFECT, OPACITY, PERFORMANCE_MODE, PRIMARY_MONITOR_INDEX
    prof = config["profiles"].get(profile_name)
    if not prof:
        return
    BRIGHTNESS = prof.get("brightness", BRIGHTNESS)
    GAMMA = prof.get("gamma", GAMMA)
    MODE = prof.get("mode", MODE)
    EFFECT = prof.get("effect", EFFECT)
    OPACITY = prof.get("opacity", OPACITY)
    PERFORMANCE_MODE = prof.get("performance_mode", PERFORMANCE_MODE)
    PRIMARY_MONITOR_INDEX = prof.get("monitor_index", PRIMARY_MONITOR_INDEX)
    print(f"[PROFILE] Applied '{profile_name}': B={BRIGHTNESS:.2f} G={GAMMA:.2f} "
          f"Mode={MODE} Effect={EFFECT} Opacity={OPACITY:.2f} Perf={PERFORMANCE_MODE} Mon={PRIMARY_MONITOR_INDEX}")

def save_profile(profile_name):
    config["profiles"][profile_name] = {
        "brightness": BRIGHTNESS,
        "gamma": GAMMA,
        "mode": MODE,
        "effect": EFFECT,
        "opacity": OPACITY,
        "performance_mode": PERFORMANCE_MODE,
        "monitor_index": PRIMARY_MONITOR_INDEX
    }
    save_config()
    print(f"[PROFILE] Saved profile '{profile_name}'.")


# ---------------- UTILITIES: ACTIVE GAME DETECTION ----------------

def get_active_process_name():
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        p = psutil.Process(pid)
        exe = os.path.basename(p.exe())
        return exe
    except Exception:
        return None

def game_profile_manager_loop():
    global current_game
    while True:
        exe = get_active_process_name()
        if exe and exe != current_game:
            current_game = exe
            prof_name = f"game:{exe}"
            if prof_name in config["profiles"]:
                apply_profile(prof_name)
            else:
                apply_profile("global")
        time.sleep(2)


# ---------------- UTILITIES: GAMMA RAMP (SYSTEM MODE) ----------------

gdi32 = ctypes.WinDLL("gdi32")
GetDC = ctypes.windll.user32.GetDC
ReleaseDC = ctypes.windll.user32.ReleaseDC

class GAMMARAMP(ctypes.Structure):
    _fields_ = [("Red", ctypes.c_ushort * 256),
                ("Green", ctypes.c_ushort * 256),
                ("Blue", ctypes.c_ushort * 256)]

def get_current_gamma_ramp():
    hdc = GetDC(0)
    ramp = GAMMARAMP()
    res = gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(ramp))
    ReleaseDC(0, hdc)
    if res:
        return ramp
    return None

def set_gamma_ramp(brightness=1.0, gamma=1.0):
    hdc = GetDC(0)
    ramp = GAMMARAMP()
    for i in range(256):
        v = i / 255.0
        v = pow(v, gamma) * brightness
        v = max(0.0, min(1.0, v))
        value = int(v * 65535.0)
        ramp.Red[i] = ramp.Green[i] = ramp.Blue[i] = value
    gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp))
    ReleaseDC(0, hdc)

def restore_default_gamma():
    global monitor_default_gamma_ramp
    if not monitor_default_gamma_ramp:
        return
    hdc = GetDC(0)
    gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(monitor_default_gamma_ramp))
    ReleaseDC(0, hdc)
    print("[GAMMA] Restored default gamma ramp.")


# ---------------- UTILITIES: DDC/CI (OPTIONAL MONITOR SETTINGS) ----------------

def capture_monitor_default_brightness_ddc(monitor_index=0):
    global monitor_default_brightness_ddc
    if not HAS_MONITORCONTROL:
        return
    try:
        mons = list(get_monitors())
        if not mons:
            return
        idx = min(max(monitor_index, 0), len(mons)-1)
        with mons[idx] as m:
            try:
                monitor_default_brightness_ddc = m.get_brightness()
                print(f"[DDC] Captured default monitor {idx} brightness (DDC/CI): {monitor_default_brightness_ddc}")
            except Exception:
                monitor_default_brightness_ddc = None
    except Exception:
        monitor_default_brightness_ddc = None

def restore_monitor_brightness_ddc(monitor_index=0):
    global monitor_default_brightness_ddc
    if not HAS_MONITORCONTROL or monitor_default_brightness_ddc is None:
        return
    try:
        mons = list(get_monitors())
        if not mons:
            return
        idx = min(max(monitor_index, 0), len(mons)-1)
        with mons[idx] as m:
            m.set_brightness(monitor_default_brightness_ddc)
            print(f"[DDC] Restored monitor {idx} brightness to {monitor_default_brightness_ddc}")
    except Exception as e:
        print("[DDC] Failed to restore brightness:", e)


# ---------------- HDR STATUS CHECK ----------------

def check_hdr_status():
    """
    Best-effort HDR check via registry.
    Returns:
        True  -> HDR appears ON
        False -> HDR appears OFF
        None  -> Unknown / could not detect
    """
    if not HAS_WINREG:
        return None

    candidates = [
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\VideoSettings",
         "HdrEnable"),
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\VideoSettings",
         "UserHDR"),
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\VideoSettings",
         "EnableHDR"),
    ]

    status = None
    for root, path, name in candidates:
        try:
            with winreg.OpenKey(root, path) as key:
                val, _ = winreg.QueryValueEx(key, name)
                if isinstance(val, int):
                    status = bool(val)
                    break
        except OSError:
            continue

    return status


# ---------------- OVERLAY: FRAME ADJUSTMENT ----------------

def apply_effect_cpu(frame):
    """
    Standard CPU path (can use OpenCV if available).
    """
    global BRIGHTNESS, GAMMA, EFFECT, OPACITY

    img = frame.astype(np.float32) / 255.0

    # Base gamma & brightness
    img = np.power(img, GAMMA)
    img *= BRIGHTNESS
    img = np.clip(img, 0, 1)

    if EFFECT == "night_vision":
        gray = np.dot(img[..., :3], [0.299, 0.587, 0.114])
        img = np.zeros_like(img)
        img[..., 1] = gray * 1.2
        img = np.clip(img, 0, 1)

    elif EFFECT == "thermal":
        gray = np.dot(img[..., :3], [0.299, 0.587, 0.114])
        gray8 = (gray * 255).astype(np.uint8)

        if HAS_CV2:
            colored = cv2.applyColorMap(gray8, cv2.COLORMAP_INFERNO)
            img = colored.astype(np.float32) / 255.0
        else:
            # Simple manual pseudo-thermal if no OpenCV
            img = np.zeros_like(img)
            # Map grayscale into R/G/B in bands
            img[..., 2] = np.clip((gray - 0.2) * 3.0, 0, 1)      # blue
            img[..., 1] = np.clip((gray - 0.4) * 3.0, 0, 1)      # green
            img[..., 0] = np.clip((gray - 0.6) * 3.0, 0, 1)      # red

    # Blend with original using opacity
    if 0.0 <= OPACITY < 1.0:
        base = frame.astype(np.float32) / 255.0
        img = base * (1.0 - OPACITY) + img * OPACITY

    img = np.clip(img, 0, 1)
    return (img * 255).astype(np.uint8)

def apply_effect_ultra(frame):
    """
    Ultra mode: no OpenCV, minimal extra work.
    Keeps it simple and fast.
    """
    global BRIGHTNESS, GAMMA, EFFECT, OPACITY

    img = frame.astype(np.float32) / 255.0

    # Base gamma & brightness (still needed)
    img = np.power(img, GAMMA)
    img *= BRIGHTNESS
    np.clip(img, 0, 1, out=img)

    if EFFECT == "night_vision":
        gray = np.dot(img[..., :3], [0.299, 0.587, 0.114])
        img[:] = 0
        img[..., 1] = np.clip(gray * 1.2, 0, 1)
    elif EFFECT == "thermal":
        # Very cheap pseudo-thermal: 3-band colorization
        gray = np.dot(img[..., :3], [0.299, 0.587, 0.114])
        img[:] = 0
        img[..., 2] = np.clip((gray - 0.2) * 2.5, 0, 1)
        img[..., 1] = np.clip((gray - 0.5) * 3.0, 0, 1)
        img[..., 0] = np.clip((gray - 0.7) * 4.0, 0, 1)

    if 0.0 <= OPACITY < 1.0:
        base = frame.astype(np.float32) / 255.0
        img = base * (1.0 - OPACITY) + img * OPACITY

    np.clip(img, 0, 1, out=img)
    return (img * 255).astype(np.uint8)

def apply_effect(frame):
    if PERFORMANCE_MODE == "ultra":
        return apply_effect_ultra(frame)
    else:
        return apply_effect_cpu(frame)


# ---------------- MAIN OVERLAY WINDOW ----------------

class FullBrightOverlay:
    def __init__(self):
        self.monitor_index = PRIMARY_MONITOR_INDEX
        self.camera = None
        self._init_camera()

        # Create fullscreen overlay
        self.window = pyglet.window.Window(
            fullscreen=True,
            style=pyglet.window.Window.WINDOW_STYLE_BORDERLESS,
            vsync=False
        )
        self.window.set_exclusive_mouse(False)

        hwnd = self.window._hwnd
        # Always-on-top
        win32api.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
        )

        # Make window layered, alpha, click-through
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                               style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
        win32gui.SetLayeredWindowAttributes(hwnd, 0, 255, win32con.LWA_ALPHA)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        @self.window.event
        def on_draw():
            self.on_draw()

        @self.window.event
        def on_key_press(symbol, modifiers):
            self.on_key_press(symbol, modifiers)

    def _init_camera(self):
        try:
            if self.camera:
                self.camera.stop()
        except Exception:
            pass
        self.camera = dxcam.create(output_idx=self.monitor_index)
        self.camera.start(target_fps=TARGET_FPS)
        print(f"[DXCAM] Using monitor index {self.monitor_index}")

    def set_monitor(self, idx: int):
        self.monitor_index = max(0, int(idx))
        self._init_camera()

    def on_draw(self):
        global MODE

        self.window.clear()

        if MODE == "system_gamma":
            # In system gamma mode, overlay can be visually empty
            return

        frame = self.camera.get_latest_frame()
        if frame is None:
            return

        frame = apply_effect(frame)
        h, w, _ = frame.shape

        image_data = pyglet.image.ImageData(
            w, h, 'BGR', frame.tobytes(), pitch=-w * 3
        )
        image_data.blit(0, 0)

    def on_key_press(self, symbol, modifiers):
        from pyglet.window import key
        global MODE

        if symbol == key.F9:
            MODE = "system_gamma"
            set_gamma_ramp(brightness=BRIGHTNESS, gamma=GAMMA)
            print(f"[GAMMA] System mode: B={BRIGHTNESS:.2f}, G={GAMMA:.2f}")
        elif symbol == key.F10:
            MODE = "overlay"
            restore_default_gamma()
            print("[GAMMA] Restored default gamma, back to overlay.")


# ---------------- SETTINGS UI (TKINTER) ----------------

def launch_settings_ui():
    import tkinter as tk
    from tkinter import ttk

    def update_labels():
        lbl_brightness_val.config(text=f"{BRIGHTNESS:.2f}")
        lbl_gamma_val.config(text=f"{GAMMA:.2f}")
        lbl_opacity_val.config(text=f"{OPACITY:.2f}")

    def on_brightness_change(val):
        global BRIGHTNESS
        BRIGHTNESS = float(val)
        update_labels()

    def on_gamma_change(val):
        global GAMMA
        GAMMA = float(val)
        update_labels()

    def on_opacity_change(val):
        global OPACITY
        OPACITY = float(val)
        update_labels()

    def on_mode_change():
        global MODE
        MODE = mode_var.get()
        print("[UI] Mode:", MODE)

    def on_effect_change(_event=None):
        global EFFECT
        EFFECT = effect_var.get()
        print("[UI] Effect:", EFFECT)

    def on_perf_change(_event=None):
        global PERFORMANCE_MODE
        PERFORMANCE_MODE = perf_var.get()
        print("[UI] Performance mode:", PERFORMANCE_MODE)

    def on_monitor_change(_event=None):
        global PRIMARY_MONITOR_INDEX, overlay_instance
        try:
            idx = int(mon_var.get())
        except ValueError:
            idx = 0
        PRIMARY_MONITOR_INDEX = idx
        print("[UI] Monitor index:", PRIMARY_MONITOR_INDEX)
        if overlay_instance is not None:
            overlay_instance.set_monitor(PRIMARY_MONITOR_INDEX)
        # recapture default DDC brightness for this monitor
        capture_monitor_default_brightness_ddc(PRIMARY_MONITOR_INDEX)

    def save_global():
        save_profile("global")

    def save_current_game():
        if current_game:
            save_profile(f"game:{current_game}")
        else:
            print("[UI] No active game detected.")

    def restore_monitor_defaults():
        restore_default_gamma()
        restore_monitor_brightness_ddc(PRIMARY_MONITOR_INDEX)

    def update_hdr_label():
        status = check_hdr_status()
        if status is True:
            hdr_label.config(text="HDR status: ON (effects may be limited)", fg="red")
        elif status is False:
            hdr_label.config(text="HDR status: OFF (optimal)", fg="green")
        else:
            hdr_label.config(text="HDR status: Unknown", fg="orange")
        # re-check every 5s
        root.after(5000, update_hdr_label)

    root = tk.Tk()
    root.title("FullBright Settings")
    root.geometry("380x380")

    # Mode
    frame_mode = ttk.LabelFrame(root, text="Mode")
    frame_mode.pack(fill="x", padx=10, pady=5)

    global MODE, EFFECT, PERFORMANCE_MODE, PRIMARY_MONITOR_INDEX
    mode_var = tk.StringVar(value=MODE)
    rb_overlay = ttk.Radiobutton(frame_mode, text="Overlay", variable=mode_var,
                                 value="overlay", command=on_mode_change)
    rb_gamma = ttk.Radiobutton(frame_mode, text="System Gamma", variable=mode_var,
                               value="system_gamma", command=on_mode_change)
    rb_overlay.pack(side="left", padx=5, pady=5)
    rb_gamma.pack(side="left", padx=5, pady=5)

    # Effect
    frame_effect = ttk.LabelFrame(root, text="Effect")
    frame_effect.pack(fill="x", padx=10, pady=5)

    effect_var = tk.StringVar(value=EFFECT)
    combo_effect = ttk.Combobox(frame_effect, textvariable=effect_var,
                                values=["normal", "night_vision", "thermal"],
                                state="readonly")
    combo_effect.pack(fill="x", padx=5, pady=5)
    combo_effect.bind("<<ComboboxSelected>>", on_effect_change)

    # Performance mode
    frame_perf = ttk.LabelFrame(root, text="Performance Mode")
    frame_perf.pack(fill="x", padx=10, pady=5)

    perf_var = tk.StringVar(value=PERFORMANCE_MODE)
    combo_perf = ttk.Combobox(frame_perf, textvariable=perf_var,
                              values=["standard", "ultra"],
                              state="readonly")
    combo_perf.pack(fill="x", padx=5, pady=5)
    combo_perf.bind("<<ComboboxSelected>>", on_perf_change)

    # Monitor selection
    frame_mon = ttk.LabelFrame(root, text="Monitor")
    frame_mon.pack(fill="x", padx=10, pady=5)

    ttk.Label(frame_mon, text="Monitor index (0,1,2...)").pack(side="left", padx=5, pady=5)
    mon_var = tk.StringVar(value=str(PRIMARY_MONITOR_INDEX))
    entry_mon = ttk.Combobox(frame_mon, textvariable=mon_var,
                             values=[str(i) for i in range(4)])  # 0-3 quick options
    entry_mon.pack(side="left", padx=5, pady=5)
    entry_mon.bind("<<ComboboxSelected>>", on_monitor_change)

    # Sliders
    frame_sliders = ttk.LabelFrame(root, text="Adjustments")
    frame_sliders.pack(fill="x", padx=10, pady=5)

    ttk.Label(frame_sliders, text="Brightness").grid(row=0, column=0, sticky="w")
    s_brightness = ttk.Scale(frame_sliders, from_=0.1, to=3.0, value=BRIGHTNESS,
                             command=on_brightness_change)
    s_brightness.grid(row=0, column=1, sticky="we")
    lbl_brightness_val = ttk.Label(frame_sliders, text=f"{BRIGHTNESS:.2f}")
    lbl_brightness_val.grid(row=0, column=2, padx=5)

    ttk.Label(frame_sliders, text="Gamma").grid(row=1, column=0, sticky="w")
    s_gamma = ttk.Scale(frame_sliders, from_=0.2, to=2.5, value=GAMMA,
                        command=on_gamma_change)
    s_gamma.grid(row=1, column=1, sticky="we")
    lbl_gamma_val = ttk.Label(frame_sliders, text=f"{GAMMA:.2f}")
    lbl_gamma_val.grid(row=1, column=2, padx=5)

    ttk.Label(frame_sliders, text="Opacity").grid(row=2, column=0, sticky="w")
    s_opacity = ttk.Scale(frame_sliders, from_=0.0, to=1.0, value=OPACITY,
                          command=on_opacity_change)
    s_opacity.grid(row=2, column=1, sticky="we")
    lbl_opacity_val = ttk.Label(frame_sliders, text=f"{OPACITY:.2f}")
    lbl_opacity_val.grid(row=2, column=2, padx=5)

    frame_sliders.columnconfigure(1, weight=1)

    # Buttons
    frame_buttons = ttk.Frame(root)
    frame_buttons.pack(fill="x", padx=10, pady=10)

    btn_save_global = ttk.Button(frame_buttons, text="Save Global Profile",
                                 command=save_global)
    btn_save_global.pack(fill="x", pady=2)

    btn_save_game = ttk.Button(frame_buttons, text="Save Current Game Profile",
                               command=save_current_game)
    btn_save_game.pack(fill="x", pady=2)

    btn_restore = ttk.Button(frame_buttons, text="Restore Monitor Defaults",
                             command=restore_monitor_defaults)
    btn_restore.pack(fill="x", pady=2)

    # HDR status label
    hdr_label = tk.Label(root, text="HDR status: Unknown", justify="left", fg="orange")
    hdr_label.pack(padx=10, pady=5)

    # Info
    info = tk.Label(root,
                    text="Hotkeys in overlay:\nF9 = Apply System Gamma\nF10 = Restore Gamma & Overlay",
                    justify="left")
    info.pack(padx=10, pady=5)

    def local_update_hdr():
        update_hdr_label()

    # nested to capture hdr_label
    def update_hdr_label():
        status = check_hdr_status()
        if status is True:
            hdr_label.config(text="HDR status: ON (effects may be limited)", fg="red")
        elif status is False:
            hdr_label.config(text="HDR status: OFF (optimal)", fg="green")
        else:
            hdr_label.config(text="HDR status: Unknown", fg="orange")
        root.after(5000, update_hdr_label)

    update_labels()
    update_hdr_label()

    root.mainloop()


# ---------------- MAIN ----------------

def main():
    global monitor_default_gamma_ramp, overlay_instance

    print("[INIT] Loading config...")
    load_config()
    apply_profile("global")

    print("[INIT] Capturing default gamma ramp...")
    monitor_default_gamma_ramp = get_current_gamma_ramp()

    print("[INIT] Capturing default DDC brightness (if possible)...")
    capture_monitor_default_brightness_ddc(PRIMARY_MONITOR_INDEX)

    print("[INIT] Starting game profile manager...")
    t = threading.Thread(target=game_profile_manager_loop, daemon=True)
    t.start()

    print("[INIT] Launching settings UI...")
    t_ui = threading.Thread(target=launch_settings_ui, daemon=True)
    t_ui.start()

    print("[INIT] Starting overlay...")
    overlay_instance = FullBrightOverlay()

    try:
        pyglet.app.run()
    finally:
        restore_default_gamma()
        restore_monitor_brightness_ddc(PRIMARY_MONITOR_INDEX)
        print("[EXIT] Restored monitor settings and exiting.")

if __name__ == "__main__":
    main()