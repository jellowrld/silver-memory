import os
import psutil
import time
import traceback
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, scrolledtext
from ctypes import *
import winreg
import re
from pathlib import Path
import pefile

# Base64 PNG icon
ICON_B64 = ""

# DX12 hook detection settings
DX12_IMPORTS = ["LoadLibraryA", "GetProcAddress"]
DX12_KEYWORDS = [b"D3D12"]

PAGE_READWRITE = 0x04
PROCESS_ALL_ACCESS = (0x000F0000 | 0x00100000 | 0xFFF)
VIRTUAL_MEM = (0x1000 | 0x2000)
LIST_MODULES_ALL = 0x03

# ------------------- DX12 Check Function -------------------
def check_dx12_hooks(dll_path, logger=None):
    """
    Returns True if DLL contains all required DX12 indicators.
    Logs details of what was detected.
    """
    try:
        pe = pefile.PE(dll_path)
        found_imports = []
        found_strings = []

        # --- Imports ---
        if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                dll_name = entry.dll.decode("utf-8").lower()
                if "kernel32.dll" in dll_name:
                    for imp in entry.imports:
                        if imp.name:
                            fn = imp.name.decode("utf-8")
                            if fn in DX12_IMPORTS:
                                found_imports.append(fn)

        # --- Strings ---
        with open(dll_path, "rb") as f:
            data = f.read()
            if b"D3D12" in data:
                found_strings.append("D3D12")

        # --- Logging ---
        if logger:
            logger("[i] DX12 Hook Scan Results:")
            if found_imports:
                logger(f"    Imports found: {', '.join(found_imports)}")
            else:
                logger("    No relevant imports found.")

            if found_strings:
                logger(f"    Strings found: {', '.join(found_strings)}")
            else:
                logger("    No relevant strings found.")

        # --- Decision ---
        if all(fn in found_imports for fn in DX12_IMPORTS) and "D3D12" in found_strings:
            return True
        return False

    except Exception as e:
        if logger:
            logger(f"[!] DX12 check failed: {e}")
        return False

# ------------------- DLL Injector GUI -------------------
class DLLInjectorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Jell's TFD Njector")
        self.root.geometry("580x400")
        self.root.configure(bg="#1e1e1e")
        self.dll_path = tk.StringVar()
        self.injection_done = False
        self.injected_pid = None
        self.injected_dll_base = None
        self.delayed_injection = False

        self.setup_winapi()
        self.build_ui()
        self.load_last_dll_path()
        self.start_auto_inject_thread()

    # ------------------- UI -------------------
    def build_ui(self):
        # Console
        self.console = scrolledtext.ScrolledText(
            self.root, height=12, bg="#2e2e2e", fg="#ffffff",
            insertbackground="#ffffff", font=("Consolas", 9), bd=0, relief="flat"
        )
        self.console.pack(padx=10, pady=(15, 10), fill="both", expand=True)

        # Control Panel Frame
        control_frame = tk.Frame(self.root, bg="#1e1e1e")
        control_frame.pack(padx=10, pady=(5, 10), fill="x")

        # DLL Entry
        tk.Label(control_frame, text="💉 DLL to inject:", bg="#1e1e1e", fg="#ffffff").pack(anchor="w", pady=(0, 5))
        entry_frame = tk.Frame(control_frame, bg="#1e1e1e")
        entry_frame.pack(fill="x")
        tk.Entry(
            entry_frame, textvariable=self.dll_path, width=52, bg="#2e2e2e", fg="#ffffff",
            insertbackground="#ffffff", font=("Segoe UI", 10)
        ).pack(side="left", padx=(0, 5), fill="x", expand=True)
        tk.Button(entry_frame, text="📂 Browse", command=self.browse_dll).pack(side="left")

        # Options Frame
        options_frame = tk.Frame(control_frame, bg="#1e1e1e")
        options_frame.pack(fill="x", pady=(10, 5))
        options_frame.columnconfigure(0, weight=1)
        options_frame.columnconfigure(1, weight=0)

        checkboxes_frame = tk.Frame(options_frame, bg="#1e1e1e")
        checkboxes_frame.grid(row=0, column=0, sticky="w")

        self.delete_cfg_var = tk.BooleanVar()
        tk.Checkbutton(
            checkboxes_frame, text="🗑️ Delete CFG", variable=self.delete_cfg_var,
            bg="#1e1e1e", fg="#ffffff", selectcolor="#2e2e2e",
            font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(0, 5))

        self.update_ini_var = tk.BooleanVar()
        tk.Checkbutton(
            checkboxes_frame, text="📝 Default Settings (Run this Once)", variable=self.update_ini_var,
            bg="#1e1e1e", fg="#ffffff", selectcolor="#2e2e2e",
            font=("Segoe UI", 10)
        ).pack(anchor="w")

        warning_label = tk.Label(
            options_frame,
            text="⚠️ Changing Resolution or Windowed/Borderless mode\nwill and may cause crashes.",
            bg="#1e1e1e", fg="red", font=("Segoe UI", 10, "bold"),
            justify="right", anchor="e", wraplength=250
        )
        warning_label.grid(row=0, column=1, sticky="e", padx=(20, 0))

        # Launch Button
        tk.Button(control_frame, text="🚀 Launch TFD", command=self.launch_game).pack(pady=(10, 10))

    # ------------------- Logging -------------------
    def log(self, message):
        self.console.config(state='normal')
        self.console.insert('end', message + '\n')
        self.console.yview('end')
        self.console.config(state='disabled')
        print(message)

    # ------------------- DLL Selection -------------------
    def browse_dll(self):
        file_path = filedialog.askopenfilename(filetypes=[("DLL files", "*.dll")])
        if file_path:
            self.dll_path.set(file_path)
            self.save_last_dll_path(file_path)

    # ------------------- Game Folder -------------------
    def find_game_folder(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            steam_path = Path(steam_path)
            # Primary library
            app_manifest = steam_path / "steamapps" / "appmanifest_2074920.acf"
            if app_manifest.exists():
                with open(app_manifest, "r", encoding="utf-8") as f:
                    content = f.read()
                    match = re.search(r'"installdir"\s+"(.+?)"', content)
                    if match:
                        return steam_path / "steamapps" / "common" / match.group(1)
            # Other libraries
            library_vdf = steam_path / "steamapps" / "libraryfolders.vdf"
            if library_vdf.exists():
                with open(library_vdf, "r", encoding="utf-8") as f:
                    content = f.read()
                    paths = re.findall(r'"path"\s+"(.+?)"', content)
                    for p in paths:
                        folder = Path(p) / "steamapps" / f"appmanifest_2074920.acf"
                        if folder.exists():
                            with open(folder, "r", encoding="utf-8") as af:
                                c = af.read()
                                match = re.search(r'"installdir"\s+"(.+?)"', c)
                                if match:
                                    return Path(p) / "steamapps" / "common" / match.group(1)
            return None
        except Exception as e:
            self.log(f"[!] Failed to detect game folder: {e}")
            return None

    # ------------------- Launch Game & DX12 Check -------------------
    def launch_game(self):
        try:
            game_folder = self.find_game_folder()
            if not game_folder or not game_folder.exists():
                self.log("[!] Game folder not found. Skipping cleanup.")
                return
            self.log(f"[i] Game found at: {game_folder}")

            # CFG Deletion
            cfg_file = game_folder / "M1" / "Binaries" / "Win64" / "CFG.ini"
            if self.delete_cfg_var.get() and cfg_file.exists():
                try:
                    cfg_file.unlink()
                    self.log(f"[i] Deleted CFG file: {cfg_file.name}")
                except Exception as e:
                    self.log(f"[!] Failed to delete CFG file: {e}")
            else:
                self.log("[i] CFG file not found or deletion not selected, skipping.")

            # INI Update
            if self.update_ini_var.get():
                self.update_game_settings_ini()

            # Pre-launch log cleaning
            self.log("[i] Starting pre-launch log cleaning...")
            userprofile = Path(os.environ.get("USERPROFILE", ""))
            crash_report_client = userprofile / "AppData" / "Local" / "M1" / "Saved" / "Config" / "CrashReportClient"
            logs_folder = crash_report_client.parent.parent / "Logs"
            crashes_folder = logs_folder.parent / "Crashes"
            webcache_folder = crashes_folder.parent / "webcache_4430"
            pipeline_file = webcache_folder.parent / "M1_PCD3D_SM6.upipelinecache"
            blackcipher_folder = game_folder / "M1" / "Binaries" / "Win64" / "BlackCipher"

            folders_to_clean = [
                ("CrashReportClient", crash_report_client),
                ("Logs", logs_folder),
                ("Crashes", crashes_folder),
                ("Webcache", webcache_folder)
            ]

            def safe_rmdir(path):
                if path.exists() and path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)

            def safe_remove(path):
                if path.exists() and path.is_file():
                    path.unlink()

            for name, folder in folders_to_clean:
                if folder.exists():
                    self.log(f"[i] Cleaning {name} folder...")
                    for item in folder.iterdir():
                        try:
                            if item.is_dir():
                                safe_rmdir(item)
                                self.log(f"    [-] Deleted folder: {item.name}")
                            else:
                                safe_remove(item)
                                self.log(f"    [-] Deleted file: {item.name}")
                        except Exception as e:
                            self.log(f"[!] Failed to delete {item}: {e}")
                else:
                    self.log(f"[i] {name} folder not found, skipping.")

            if pipeline_file.exists():
                safe_remove(pipeline_file)
                self.log(f"[i] Deleted pipeline cache: {pipeline_file.name}")
            else:
                self.log(f"[i] Pipeline cache not found, skipping.")

            if blackcipher_folder.exists():
                self.log("[i] Cleaning BlackCipher logs and dumps...")
                for ext in ["*.log", "*.dump"]:
                    for file in blackcipher_folder.glob(ext):
                        safe_remove(file)
                        self.log(f"    [-] Deleted {file.name}")
            else:
                self.log("[i] BlackCipher folder not found, skipping.")

            # --- DX12 Check ---
            dll_path = self.dll_path.get().strip()
            if not os.path.isfile(dll_path):
                self.log("[!] DLL path is invalid or missing. Launch aborted.")
                return

            self.log("[i] Running DX12 check on DLL...")
            dx12_ready = check_dx12_hooks(dll_path, logger=self.log)

            if dx12_ready:
                self.log("[✓] All DX12 indicators detected → injection will run immediately.")
                self.delayed_injection = False
            else:
                self.log("[~] DX12 indicators missing → delaying injection by 60s.")
                self.delayed_injection = True

            # Launch game
            os.system("start steam://run/2074920")
            self.log("[+] Launch command sent to Steam.")

        except Exception as e:
            self.log(f"[!] Failed to clean or launch game: {e}")

    # ------------------- INI Update -------------------
    def update_game_settings_ini(self):
        ini_path = Path(os.path.expandvars(r"%LOCALAPPDATA%\M1\Saved\Config\Windows\GameUserSettings.ini"))
        required_settings = {
            "bDesiredUsingHDRDisplayOutput": "False",
            "QualityPreset": "EM1QualityPreset::Low",
            "ConsoleQuality": "EM1ConsoleQuality::PerformanceMode",
            "bConsoleFG": "False",
            "bConsoleRayTracing": "False",
            "ViewDistance": "0",
            "AntiAliasing": "0",
            "PostProcessing": "0",
            "Shadows": "0",
            "GlobalIllumination": "0",
            "Reflections": "0",
            "Textures": "0",
            "Effects": "0",
            "Foliage": "0",
            "Shading": "0",
            "Mesh": "0",
            "Physics": "0",
            "RayTracingQuality": "0",
            "SelectUpscaler": "EM1Upscaler::None",
            "bUseVSync": "False",
            "ResolutionSizeX": "1600",
            "ResolutionSizeY": "900"
        }

        if not ini_path.exists():
            self.log(f"[!] GameUserSettings.ini not found at: {ini_path}")
            return

        try:
            with open(ini_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            updated = {}
            new_lines = []

            for line in lines:
                stripped = line.strip()
                if "=" in stripped and not stripped.startswith(";"):
                    key, value = stripped.split("=", 1)
                    key = key.strip()
                    if key in required_settings:
                        new_value = required_settings[key]
                        if value.strip() != new_value:
                            self.log(f"[~] Updating {key} -> {new_value}")
                            new_lines.append(f"{key}={new_value}\n")
                        else:
                            new_lines.append(line)
                        updated[key] = True
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)

            for key, value in required_settings.items():
                if key not in updated:
                    self.log(f"[+] Adding missing setting: {key}={value}")
                    new_lines.append(f"{key}={value}\n")

            backup_path = ini_path.with_suffix(ini_path.suffix + ".bak")
            if not backup_path.exists():
                shutil.copy2(ini_path, backup_path)
                self.log(f"[i] Backup created: {backup_path}")

            with open(ini_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            self.log("[✓] GameUserSettings.ini updated successfully.")

        except Exception as e:
            self.log(f"[!] Failed to update INI: {e}")

    # ------------------- Process Helper -------------------
    def get_process_info_by_name(self, process_name):
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'].lower() == process_name.lower():
                return proc
        return None

    # ------------------- WinAPI Setup -------------------
    def setup_winapi(self):
        self.kernel32 = windll.kernel32
        self.psapi = windll.psapi

        self.kernel32.OpenProcess.argtypes = [c_ulong, c_bool, c_ulong]
        self.kernel32.OpenProcess.restype = c_void_p

        self.kernel32.VirtualAllocEx.argtypes = [c_void_p, c_void_p, c_size_t, c_ulong, c_ulong]
        self.kernel32.VirtualAllocEx.restype = c_void_p

        self.kernel32.WriteProcessMemory.argtypes = [c_void_p, c_void_p, c_void_p, c_size_t, POINTER(c_size_t)]
        self.kernel32.WriteProcessMemory.restype = c_bool

        self.kernel32.GetModuleHandleW.argtypes = [c_wchar_p]
        self.kernel32.GetModuleHandleW.restype = c_void_p

        self.kernel32.GetProcAddress.argtypes = [c_void_p, c_char_p]
        self.kernel32.GetProcAddress.restype = c_void_p

        self.kernel32.CreateRemoteThread.argtypes = [c_void_p, c_void_p, c_size_t, c_void_p, c_void_p, c_ulong, POINTER(c_ulong)]
        self.kernel32.CreateRemoteThread.restype = c_void_p

        self.psapi.EnumProcessModulesEx.argtypes = [c_void_p, POINTER(c_void_p), c_ulong, POINTER(c_ulong), c_ulong]
        self.psapi.EnumProcessModulesEx.restype = c_bool

        self.psapi.GetModuleBaseNameW.argtypes = [c_void_p, c_void_p, c_wchar_p, c_ulong]
        self.psapi.GetModuleBaseNameW.restype = c_ulong

    # ------------------- Save/Load DLL Path -------------------
    def save_last_dll_path(self, path):
        try:
            with open("last_dll_path.txt", "w") as f:
                f.write(path)
        except Exception as e:
            self.log(f"[!] Failed to save last DLL path: {e}")

    def load_last_dll_path(self):
        try:
            if os.path.isfile("last_dll_path.txt"):
                with open("last_dll_path.txt", "r") as f:
                    path = f.read().strip()
                    if os.path.isfile(path):
                        self.dll_path.set(path)
        except Exception as e:
            self.log(f"[!] Failed to load last DLL path: {e}")

    # ------------------- DLL Injection -------------------
    def inject_dll(self):
        dll_path = self.dll_path.get().strip()
        if not os.path.isfile(dll_path):
            self.log("[!] DLL path is invalid or file does not exist.")
            return

        self.save_last_dll_path(dll_path)

        target_proc = self.get_process_info_by_name("M1-Win64-Shipping.exe")
        if not target_proc:
            self.log("[!] Target process not found.")
            return

        PID = target_proc.info['pid']
        dll_bytes = dll_path.encode('ascii') + b'\x00'
        dll_length = len(dll_bytes)

        h_process = self.kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, PID)
        if not h_process:
            self.log(f"[!] Could not open process {PID}")
            return

        alloc_address = self.kernel32.VirtualAllocEx(h_process, None, dll_length, VIRTUAL_MEM, PAGE_READWRITE)
        if not alloc_address:
            self.log("[!] Memory allocation failed.")
            self.kernel32.CloseHandle(h_process)
            return

        bytes_written = c_size_t(0)
        if not self.kernel32.WriteProcessMemory(h_process, alloc_address, dll_bytes, dll_length, byref(bytes_written)):
            self.log("[!] Failed to write DLL path into memory.")
            self.kernel32.CloseHandle(h_process)
            return

        h_kernel32 = self.kernel32.GetModuleHandleW("kernel32.dll")
        h_loadlib = self.kernel32.GetProcAddress(h_kernel32, b"LoadLibraryA")
        if not h_loadlib:
            self.log("[!] Could not resolve LoadLibraryA.")
            self.kernel32.CloseHandle(h_process)
            return

        thread_id = c_ulong(0)
        h_thread = self.kernel32.CreateRemoteThread(h_process, None, 0, h_loadlib, alloc_address, 0, byref(thread_id))
        if not h_thread:
            self.log("[!] Remote thread creation failed.")
            self.kernel32.CloseHandle(h_process)
            return

        self.log("[+] DLL injected.")
        self.injected_pid = PID
        self.injection_done = True
        threading.Timer(3.0, self.locate_injected_dll, args=[dll_path, h_process]).start()

    # ------------------- Locate Injected DLL -------------------
    def locate_injected_dll(self, dll_path, h_process):
        dll_name = os.path.basename(dll_path)
        module_handles = (c_void_p * 1024)()
        cb = sizeof(module_handles)
        cb_needed = c_ulong(0)

        if not self.psapi.EnumProcessModulesEx(h_process, module_handles, cb, byref(cb_needed), LIST_MODULES_ALL):
            self.log("[!] Failed to enumerate process modules.")
            self.kernel32.CloseHandle(h_process)
            return

        module_count = cb_needed.value // sizeof(c_void_p)
        for i in range(module_count):
            mod_name = create_unicode_buffer(260)
            self.psapi.GetModuleBaseNameW(h_process, module_handles[i], mod_name, sizeof(mod_name) // 2)
            if mod_name.value.lower() == dll_name.lower():
                self.injected_dll_base = module_handles[i]
                self.log(f"[+] DLL loaded at: 0x{self.injected_dll_base:08X}")
                self.kernel32.CloseHandle(h_process)
                return

        self.log("[!] Could not locate injected DLL.")
        self.kernel32.CloseHandle(h_process)

    # ------------------- Auto Inject Thread -------------------
    def start_auto_inject_thread(self):
        def monitor():
            while True:
                proc = self.get_process_info_by_name("M1-Win64-Shipping.exe")
                if proc:
                    if not self.injection_done:
                        if self.delayed_injection:
                            self.log("[i] Target process found. Waiting 60s before injecting...")
                            time.sleep(60)
                        self.log("[i] Injecting DLL now...")
                        self.inject_dll()
                else:
                    if self.injection_done:
                        self.log("[i] Target process exited. Resetting injector state.")
                        self.injection_done = False
                        self.injected_pid = None
                        self.injected_dll_base = None
                time.sleep(2)

        threading.Thread(target=monitor, daemon=True).start()

# ------------------- Main -------------------
if __name__ == '__main__':
    try:
        root = tk.Tk()
        icon_data = tk.PhotoImage(data=ICON_B64)
        root.iconphoto(True, icon_data)
        app = DLLInjectorGUI(root)
        root.mainloop()
    except Exception:
        print("[!] Uncaught Exception:\n" + traceback.format_exc())
