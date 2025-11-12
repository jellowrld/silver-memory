import ctypes, ctypes.wintypes as wt
import json, os, sys, time, threading, keyboard, tkinter as tk
from tkinter import ttk

CONFIG_FILE = "gamma_config.json"

# ==== Win32 bindings ====
gdi32  = ctypes.WinDLL("gdi32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

HDC, WORD = wt.HDC, ctypes.c_ushort

GetDeviceGammaRamp = gdi32.GetDeviceGammaRamp
GetDeviceGammaRamp.argtypes = [HDC, ctypes.c_void_p]
SetDeviceGammaRamp = gdi32.SetDeviceGammaRamp
SetDeviceGammaRamp.argtypes = [HDC, ctypes.c_void_p]
GetDC       = user32.GetDC
ReleaseDC   = user32.ReleaseDC

EnumDisplayDevicesW = user32.EnumDisplayDevicesW
EnumDisplayDevicesW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.POINTER(wt.DISPLAY_DEVICEW), wt.DWORD]
EnumDisplayDevicesW.restype  = wt.BOOL

class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("DeviceName", wt.WCHAR * 32),
        ("DeviceString", wt.WCHAR * 128),
        ("StateFlags", wt.DWORD),
        ("DeviceID", wt.WCHAR * 128),
        ("DeviceKey", wt.WCHAR * 128)
    ]

def clamp(x, lo, hi): return lo if x < lo else hi if x > hi else x

def make_ramp(gamma=1.0, scale=1.0, black_shift=0.0):
    arr = (WORD * (256 * 3))()
    inv_gamma = 1.0 / max(gamma, 1e-6)
    for i in range(256):
        x = i / 255.0
        if black_shift > 0: x = clamp(x + black_shift, 0.0, 1.0)
        y = (x ** inv_gamma) * scale
        y = clamp(y, 0.0, 1.0)
        v = int(round(y * 65535.0))
        arr[i] = arr[256+i] = arr[512+i] = v
    return arr

def get_current_ramp(hdc):
    buf = (WORD * (256 * 3))()
    if not GetDeviceGammaRamp(hdc, ctypes.byref(buf)):
        return None
    return buf

def set_ramp(hdc, ramp):
    if not SetDeviceGammaRamp(hdc, ctypes.byref(ramp)):
        raise OSError("SetDeviceGammaRamp failed")

def list_monitors():
    monitors = []
    dd = DISPLAY_DEVICEW(); dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
    i = 0
    while EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
        if dd.StateFlags & 0x1:
            monitors.append(dd.DeviceName)
        i += 1
        dd = DISPLAY_DEVICEW(); dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
    return monitors


class GammaController:
    def __init__(self):
        self.monitors = list_monitors()
        if not self.monitors:
            print("⚠️  No active monitors detected.")
            sys.exit(1)

        self.monitor_index = 0
        self.hdc = self.get_dc(self.monitor_index)
        self.original_ramp = get_current_ramp(self.hdc)

        self.config = self.load_config()
        self.auto_apply = self.config.get("auto_apply", True)

        self.load_profile(self.monitors[self.monitor_index])
        if self.auto_apply:
            self.apply()

        self.make_gui()
        self.register_hotkeys()
        self.report()

    # ---------- config ----------
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE) as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Config] Load error: {e}")
        return {"profiles": {}, "auto_apply": True}

    def save_config(self):
        self.config["auto_apply"] = self.auto_apply
        self.config.setdefault("profiles", {})[self.monitors[self.monitor_index]] = {
            "gamma": self.gamma,
            "scale": self.scale,
            "black_shift": self.black_shift
        }
        with open(CONFIG_FILE, "w") as f: json.dump(self.config, f, indent=2)
        print("[✔] Config saved.")

    def load_profile(self, monitor_name):
        prof = self.config.get("profiles", {}).get(monitor_name, {})
        self.gamma = prof.get("gamma", 1.0)
        self.scale = prof.get("scale", 1.0)
        self.black_shift = prof.get("black_shift", 0.0)

    # ---------- gamma ops ----------
    def get_dc(self, idx):
        CreateDCW = gdi32.CreateDCW
        CreateDCW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p]
        CreateDCW.restype = HDC
        dc = CreateDCW("DISPLAY", self.monitors[idx], None, None)
        if not dc: raise RuntimeError("CreateDC failed")
        return dc

    def switch_monitor(self, idx):
        ReleaseDC(0, self.hdc)
        self.monitor_index = idx
        self.hdc = self.get_dc(idx)
        self.original_ramp = get_current_ramp(self.hdc)
        self.load_profile(self.monitors[idx])
        self.sync_sliders()
        self.apply()
        self.report()

    def apply(self):
        set_ramp(self.hdc, make_ramp(self.gamma,self.scale,self.black_shift))

    def restore_original(self):
        set_ramp(self.hdc, self.original_ramp)
        print("[Restored] Original gamma ramp.")

    # ---------- hotkeys ----------
    def register_hotkeys(self):
        keyboard.add_hotkey("alt+pageup",  self.adjust_gamma, args=(-0.05,))
        keyboard.add_hotkey("alt+pagedown",self.adjust_gamma, args=(+0.05,))
        keyboard.add_hotkey("alt+up",      self.adjust_scale, args=(+0.05,))
        keyboard.add_hotkey("alt+down",    self.adjust_scale, args=(-0.05,))
        keyboard.add_hotkey("alt+right",   self.adjust_black, args=(+0.01,))
        keyboard.add_hotkey("alt+left",    self.adjust_black, args=(-0.01,))
        keyboard.add_hotkey("alt+home",    self.restore_original)
        keyboard.add_hotkey("alt+end",     self.exit_program)

    def adjust_gamma(self, d): self.gamma=clamp(self.gamma+d,0.2,3.0);self.apply();self.report();self.sync_sliders()
    def adjust_scale(self, d): self.scale=clamp(self.scale+d,0.5,2.5);self.apply();self.report();self.sync_sliders()
    def adjust_black(self, d): self.black_shift=clamp(self.black_shift+d,0.0,0.2);self.apply();self.report();self.sync_sliders()

    # ---------- GUI ----------
    def make_gui(self):
        self.root = tk.Tk()
        self.root.title("Gamma Controller v5 – Per Monitor")
        self.root.geometry("400x320")
        self.root.configure(bg="#111")
        self.root.attributes("-topmost", True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#111", foreground="white")
        style.configure("TButton", background="#222", foreground="white")
        style.configure("TCheckbutton", background="#111", foreground="white")

        ttk.Label(self.root, text="Monitor:").pack(pady=4)
        self.monitor_var = tk.StringVar(value=self.monitors[self.monitor_index])
        cb = ttk.Combobox(self.root, textvariable=self.monitor_var, values=self.monitors, state="readonly")
        cb.bind("<<ComboboxSelected>>", lambda e: self.switch_monitor(cb.current()))
        cb.pack(pady=4)

        self.gamma_slider = self.make_slider("Gamma", 0.2, 3.0, self.gamma, self.set_gamma)
        self.scale_slider = self.make_slider("Exposure", 0.5, 2.5, self.scale, self.set_scale)
        self.black_slider = self.make_slider("Shadow Lift", 0.0, 0.2, self.black_shift, self.set_black)

        self.auto_var = tk.BooleanVar(value=self.auto_apply)
        ttk.Checkbutton(self.root, text="Auto-apply on startup", variable=self.auto_var,
                        command=self.toggle_auto).pack(pady=5)

        ttk.Button(self.root, text="Restore Original", command=self.restore_original).pack(pady=4)
        ttk.Button(self.root, text="Reset Neutral", command=self.reset).pack(pady=4)
        ttk.Button(self.root, text="Save + Exit", command=self.exit_program).pack(pady=8)

        threading.Thread(target=self.hotkey_listener, daemon=True).start()
        self.root.mainloop()

    def make_slider(self, name, frm, to, val, cmd):
        ttk.Label(self.root, text=name).pack()
        s = ttk.Scale(self.root, from_=frm, to=to, orient="horizontal", length=280)
        s.set(val); s.pack(pady=3)
        s.bind("<ButtonRelease-1>", lambda e: cmd(s.get()))
        return s

    def set_gamma(self, v): self.gamma=float(v); self.apply(); self.report()
    def set_scale(self, v): self.scale=float(v); self.apply(); self.report()
    def set_black(self, v): self.black_shift=float(v); self.apply(); self.report()
    def toggle_auto(self): self.auto_apply=self.auto_var.get(); print(f"[Auto] {self.auto_apply}")

    def sync_sliders(self):
        self.gamma_slider.set(self.gamma)
        self.scale_slider.set(self.scale)
        self.black_slider.set(self.black_shift)

    def reset(self):
        self.gamma,self.scale,self.black_shift=1,1,0
        self.apply(); self.sync_sliders(); print("[Reset] Neutral applied")

    def hotkey_listener(self):
        while True: time.sleep(0.2)

    def report(self):
        m = self.monitors[self.monitor_index]
        print(f"[{m}] γ={self.gamma:.2f} scale={self.scale:.2f} lift={self.black_shift:.2f}")

    def exit_program(self):
        print("Saving profiles and restoring original gamma...")
        self.save_config()
        self.restore_original()
        self.root.destroy()
        ReleaseDC(0,self.hdc)
        sys.exit(0)


if __name__ == "__main__":
    GammaController()