import os
import psutil
import time
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, scrolledtext
from ctypes import *
import winreg
import re
from pathlib import Path
import pefile
import requests
import zipfile
import tempfile

# ------------------ WinAPI Constants ------------------
PAGE_READWRITE = 0x04
PROCESS_ALL_ACCESS = (0x000F0000 | 0x00100000 | 0xFFF)
VIRTUAL_MEM = (0x1000 | 0x2000)
LIST_MODULES_ALL = 0x03
DX12_IMPORTS = ["LoadLibraryA", "GetProcAddress"]

# ------------------ DX12 Hook Check ------------------
def check_dx12_hooks(dll_path, logger=None):
    try:
        pe = pefile.PE(dll_path)
        found_imports = []
        found_strings = []
        if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                dll_name = entry.dll.decode("utf-8").lower()
                if "kernel32.dll" in dll_name:
                    for imp in entry.imports:
                        if imp.name and imp.name.decode("utf-8") in DX12_IMPORTS:
                            found_imports.append(imp.name.decode("utf-8"))
        with open(dll_path, "rb") as f:
            data = f.read()
            if b"D3D12" in data:
                found_strings.append("D3D12")
        if logger:
            logger("[i] DX12 Hook Scan Results:")
            logger(f" Imports found: {', '.join(found_imports) if found_imports else 'None'}")
            logger(f" Strings found: {', '.join(found_strings) if found_strings else 'None'}")
        return all(fn in found_imports for fn in DX12_IMPORTS) and "D3D12" in found_strings
    except Exception as e:
        if logger:
            logger(f"[!] DX12 check failed: {e}")
        return False

# ------------------ M1UI Detection ------------------
M1UI_EXPORT_HINTS = {
    "InitializeUI",
    "InitUI",
    "RenderUI",
    "DrawUI",
    "ShutdownUI",
}
M1UI_STRING_HINTS = [
    b"m1ui",
    b"imgui",
    b"imgui_impl_dx12",
    b"overlay",
    b"menu",
]

def check_m1ui_dll(dll_path, log=None):
    try:
        pe = pefile.PE(dll_path)
        score = 0
        if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
            for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
                if exp.name and exp.name.decode(errors="ignore") in M1UI_EXPORT_HINTS:
                    score += 2
        with open(dll_path, "rb") as f:
            data = f.read().lower()
            for s in M1UI_STRING_HINTS:
                if s in data:
                    score += 1
        if log:
            log(f"[i] M1UI score: {score}")
        return score >= 3
    except Exception as e:
        if log:
            log(f"[!] M1UI detection failed: {e}")
        return False

# ------------------ DLL Injector GUI ------------------
class DLLInjectorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Jell's TFD Njector")
        self.root.geometry("700x620")

        self.dll_path = tk.StringVar()
        self.injection_done = False
        self.injected_pid = None
        self.delayed_injection = False
        self.blackcipher_delay = tk.DoubleVar(value=2500.0)

        # Variables for checkboxes (they were missing!)
        self.delete_cfg_var = tk.BooleanVar()
        self.update_ini_var = tk.BooleanVar()

        self.setup_winapi()
        self.build_ui()
        self.load_last_dll_path()
        self.start_auto_inject_thread()
        self.root.after(1000, self.update_status_badges)

    # ------------------ WinAPI Setup ------------------
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

    # ------------------ UI Build ------------------
    def build_ui(self):
        # ---------- Colors ----------
        BG_MAIN = "#171a21"
        BG_PANEL = "#1f232a"
        BG_DARK = "#0e1013"
        ACCENT = "#66c0f4"
        TEXT = "#c7d5e0"
        MUTED = "#8f98a0"
        GREEN = "#5cff8d"
        ORANGE = "#ffb454"
        RED = "#ff5c5c"

        # ---------- Fonts ----------
        FONT_TITLE = ("Segoe UI", 16, "bold")
        FONT_LABEL = ("Segoe UI", 10)
        FONT_BTN = ("Segoe UI", 10, "bold")
        FONT_CONSOLE = ("Consolas", 9)

        self.root.configure(bg=BG_MAIN)

        # ================= HEADER =================
        header = tk.Frame(self.root, bg=BG_MAIN)
        header.pack(fill="x", padx=20, pady=(15, 10))
        tk.Label(header, text="Jell's TFD Injector", fg=TEXT, bg=BG_MAIN,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(header, text="TFD Injector - Steam Stylized",
                 fg=MUTED, bg=BG_MAIN, font=("Segoe UI", 9)).pack(anchor="w")

        # ================= DLL PANEL =================
        dll_panel = tk.Frame(self.root, bg=BG_PANEL)
        dll_panel.pack(fill="x", padx=20, pady=8)
        tk.Label(dll_panel, text="DLL Selection", fg=TEXT, bg=BG_PANEL,
                 font=FONT_BTN).pack(anchor="w", padx=15, pady=(10, 4))
        dll_row = tk.Frame(dll_panel, bg=BG_PANEL)
        dll_row.pack(fill="x", padx=15, pady=(0, 10))
        tk.Entry(
            dll_row,
            textvariable=self.dll_path,
            bg=BG_DARK,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=FONT_LABEL
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Button(
            dll_row,
            text="Browse",
            command=self.browse_dll,
            bg=ACCENT,
            fg="#000000",
            font=FONT_BTN,
            relief="flat",
            padx=14
        ).pack(side="left")

        # ================= STATUS BAR =================
        status_panel = tk.Frame(self.root, bg=BG_PANEL)
        status_panel.pack(fill="x", padx=20, pady=8)
        self.status_labels = {}

        def status_badge(text, color):
            lbl = tk.Label(status_panel, text=text, bg=color,
                           fg="#000000", font=("Segoe UI", 9, "bold"),
                           padx=10, pady=2)
            lbl.pack(side="left", padx=6, pady=8)
            return lbl

        self.status_labels["m1ui"] = status_badge("M1UI", ORANGE)
        self.status_labels["dx12"] = status_badge("DX12", ACCENT)
        self.status_labels["delay"] = status_badge("DELAYED", ORANGE)
        self.status_labels["state"] = status_badge("WAITING", GREEN)

        # ================= OPTIONS =================
        opt_panel = tk.Frame(self.root, bg=BG_PANEL)
        opt_panel.pack(fill="x", padx=20, pady=8)
        tk.Label(opt_panel, text="Launch Options", fg=TEXT,
                 bg=BG_PANEL, font=FONT_BTN).pack(anchor="w", padx=15, pady=(10, 4))
        body = tk.Frame(opt_panel, bg=BG_PANEL)
        body.pack(fill="x", padx=15, pady=(0, 10))

        tk.Checkbutton(
            body, text="Delete CFG before launch",
            variable=self.delete_cfg_var,
            bg=BG_PANEL, fg=TEXT,
            selectcolor=BG_DARK,
            activebackground=BG_PANEL,
            font=FONT_LABEL
        ).pack(anchor="w")

        tk.Checkbutton(
            body, text="Apply default GameUserSettings.ini",
            variable=self.update_ini_var,
            bg=BG_PANEL, fg=TEXT,
            selectcolor=BG_DARK,
            activebackground=BG_PANEL,
            font=FONT_LABEL
        ).pack(anchor="w", pady=(4, 8))

        tk.Label(body, text="BlackCipherDelay (ms)", fg=MUTED,
                 bg=BG_PANEL, font=FONT_LABEL).pack(anchor="w")

        tk.Scale(
            body, variable=self.blackcipher_delay,
            from_=2500, to=60000,
            orient="horizontal",
            bg=BG_PANEL, fg=TEXT,
            troughcolor=BG_DARK,
            highlightthickness=0
        ).pack(fill="x")

        # ================= ACTIONS =================
        action_row = tk.Frame(self.root, bg=BG_MAIN)
        action_row.pack(fill="x", padx=20, pady=10)

        tk.Button(
            action_row, text="Launch TFD",
            command=self.launch_game,
            bg=GREEN, fg="#000000",
            font=FONT_BTN,
            relief="flat",
            padx=22, pady=6
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            action_row, text="EAC Files (One-Time)",
            command=self.update_game_files,
            bg=ORANGE, fg="#000000",
            font=FONT_BTN,
            relief="flat",
            padx=22, pady=6
        ).pack(side="left")

        # ================= CONSOLE =================
        console_panel = tk.Frame(self.root, bg=BG_DARK)
        console_panel.pack(fill="both", expand=True, padx=20, pady=(10, 15))
        tk.Label(console_panel, text="Console Output",
                 fg=MUTED, bg=BG_DARK,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=(6, 2))
        self.console = scrolledtext.ScrolledText(
            console_panel,
            bg=BG_DARK,
            fg="#00ff90",
            insertbackground="#00ff90",
            font=FONT_CONSOLE,
            relief="flat"
        )
        self.console.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.console.config(state="disabled")

    # ------------------ Status Badges Update ------------------
    def update_status_badges(self):
        try:
            dll = self.dll_path.get().strip()
            if os.path.isfile(dll):
                self.status_labels["m1ui"].config(
                    bg="#ffb454" if check_m1ui_dll(dll) else "#3b3f46"
                )
                self.status_labels["dx12"].config(
                    bg="#66c0f4" if check_dx12_hooks(dll) else "#3b3f46"
                )
            self.status_labels["delay"].config(
                bg="#ffb454" if self.delayed_injection else "#3b3f46"
            )
            self.status_labels["state"].config(
                text="INJECTED" if self.injection_done else "WAITING",
                bg="#5cff8d" if self.injection_done else "#66c0f4"
            )
        except:
            pass
        self.root.after(1000, self.update_status_badges)

    # ------------------ Logging ------------------
    def log(self, message):
        self.console.config(state='normal')
        self.console.insert('end', message + '\n')
        self.console.yview('end')
        self.console.config(state='disabled')
        print(message)

    # ------------------ Repo Download & Copy ------------------
    def update_game_files(self):
        repo_zip_url = "https://github.com/jellowrld/oldeac/archive/refs/heads/main.zip"
        try:
            game_folder = self.find_game_folder()
            if not game_folder or not game_folder.exists():
                self.log("[!] Game folder not found. Cannot update.")
                return
            self.log(f"[i] Downloading repo from {repo_zip_url} ...")
            resp = requests.get(repo_zip_url, stream=True)
            if resp.status_code != 200:
                self.log(f"[!] Failed to download repo. Status: {resp.status_code}")
                return
            temp_dir = Path(tempfile.mkdtemp())
            zip_path = temp_dir / "repo.zip"
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            extracted_dir = next(temp_dir.glob("oldeac-*"), None)
            if not extracted_dir or not extracted_dir.is_dir():
                self.log("[!] Could not find extracted repo folder.")
                return
            self.log(f"[i] Updating game folder {game_folder} ...")
            for item in extracted_dir.iterdir():
                dest = game_folder / item.name
                try:
                    if dest.exists():
                        if dest.is_file():
                            dest.unlink()
                        elif dest.is_dir():
                            shutil.rmtree(dest)
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
                except Exception as e:
                    self.log(f"[!] Failed to update {item}: {e}")
            self.log("[✓] Game files updated successfully.")
        except Exception as e:
            self.log(f"[!] Update failed: {e}")

    # ------------------ DLL Browse ------------------
    def browse_dll(self):
        file_path = filedialog.askopenfilename(filetypes=[("DLL files", "*.dll")])
        if file_path:
            self.dll_path.set(file_path)
            self.save_last_dll_path(file_path)

    # ------------------ Game Folder ------------------
    def find_game_folder(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            steam_path = Path(steam_path)
            app_manifest = steam_path / "steamapps" / "appmanifest_2074920.acf"
            if app_manifest.exists():
                with open(app_manifest, "r", encoding="utf-8") as f:
                    match = re.search(r'"installdir"\s+"(.+?)"', f.read())
                    if match:
                        return steam_path / "steamapps" / "common" / match.group(1)
            library_vdf = steam_path / "steamapps" / "libraryfolders.vdf"
            if library_vdf.exists():
                with open(library_vdf, "r", encoding="utf-8") as f:
                    paths = re.findall(r'"path"\s+"(.+?)"', f.read())
                    for p in paths:
                        folder = Path(p) / "steamapps" / "appmanifest_2074920.acf"
                        if folder.exists():
                            with open(folder, "r") as af:
                                match = re.search(r'"installdir"\s+"(.+?)"', af.read())
                                if match:
                                    return Path(p) / "steamapps" / "common" / match.group(1)
            return None
        except Exception as e:
            self.log(f"[!] Failed to detect game folder: {e}")
            return None

    # ------------------ Launch Game & Prelaunch ------------------
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

            # Clean logs, crashes, webcache
            self.clean_game_folders(game_folder)

            # DX12 Check
            dll_path = self.dll_path.get().strip()
            if not os.path.isfile(dll_path):
                self.log("[!] DLL path invalid. Launch aborted.")
                return
            self.log("[i] Running DX12 check on DLL...")
            dx12_ready = check_dx12_hooks(dll_path, logger=self.log)
            if dx12_ready:
                self.log("[✓] DX12 indicators detected → injection will run immediately.")
                self.delayed_injection = False
            else:
                self.log("[~] DX12 indicators missing → delaying injection by 40s (25+15).")
                self.delayed_injection = True

            # Launch the game via Steam
            os.system("start steam://run/2074920")
            self.log("[+] Launch command sent to Steam.")
        except Exception as e:
            self.log(f"[!] Failed during launch: {e}")

    # ------------------ Clean Game Folders ------------------
    def clean_game_folders(self, game_folder):
        try:
            userprofile = Path(os.environ.get("USERPROFILE", ""))
            crash_report_client = userprofile / "AppData" / "Local" / "M1" / "Saved" / "Config" / "CrashReportClient"
            logs_folder = crash_report_client.parent.parent / "Logs"
            crashes_folder = logs_folder.parent / "Crashes"
            webcache_folder = crashes_folder.parent / "webcache_4430"
            blackcipher_folder = game_folder / "M1" / "Binaries" / "Win64" / "BlackCipher"
            pipeline_file = webcache_folder.parent / "M1_PCD3D_SM6.upipelinecache"

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
                                self.log(f" [-] Deleted folder: {item.name}")
                            else:
                                safe_remove(item)
                                self.log(f" [-] Deleted file: {item.name}")
                        except Exception as e:
                            self.log(f"[!] Failed to delete {item}: {e}")
                else:
                    self.log(f"[i] {name} folder not found, skipping.")

            if pipeline_file.exists():
                safe_remove(pipeline_file)
                self.log(f"[i] Deleted pipeline cache: {pipeline_file.name}")
            else:
                self.log("[i] Pipeline cache not found, skipping.")

            if blackcipher_folder.exists():
                self.log("[i] Cleaning BlackCipher logs and dumps...")
                for ext in ["*.log", "*.dump"]:
                    for file in blackcipher_folder.glob(ext):
                        safe_remove(file)
                        self.log(f" [-] Deleted {file.name}")
            else:
                self.log("[i] BlackCipher folder not found, skipping.")
        except Exception as e:
            self.log(f"[!] Failed cleaning game folders: {e}")

    # ------------------ INI Update ------------------
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
                        updated[key] = True
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            for key, value in required_settings.items():
                if key not in updated:
                    new_lines.append(f"{key}={value}\n")
                    self.log(f"[+] Adding missing setting: {key}={value}")
            backup_path = ini_path.with_suffix(ini_path.suffix + ".bak")
            if not backup_path.exists():
                shutil.copy2(ini_path, backup_path)
                self.log(f"[i] Backup created: {backup_path}")
            with open(ini_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            self.log("[✓] GameUserSettings.ini updated successfully.")
        except Exception as e:
            self.log(f"[!] Failed to update INI: {e}")

    # ------------------ Get Process By Name ------------------
    def get_process_info_by_name(self, process_name):
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and proc.info['name'].lower() == process_name.lower():
                return proc
        return None

    # ------------------ Kill BlackCipher ------------------
    def kill_blackcipher(self):
        for p in psutil.process_iter(['pid', 'name']):
            if p.info['name'] and 'blackcipher64.aes' in p.info['name'].lower():
                try:
                    p.kill()
                    self.log("[i] BlackCipher64 killed")
                    return True
                except:
                    return False
        return False

    # ------------------ Locate Injected DLL ------------------
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
                self.log(f"[+] DLL loaded at: 0x{module_handles[i]:08X}")
                self.kernel32.CloseHandle(h_process)
                return
        self.log("[!] Could not locate injected DLL.")
        self.kernel32.CloseHandle(h_process)

    # ------------------ DLL Injection ------------------
    def inject_dll(self):
        dll_path = self.dll_path.get().strip()
        if not os.path.isfile(dll_path):
            self.log("[!] DLL path invalid or file missing.")
            return

        # M1UI SHORT-CIRCUIT
        if check_m1ui_dll(dll_path, self.log):
            self.log("[+] M1UI detected — skipping prep logic")
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
            alloc_address = self.kernel32.VirtualAllocEx(
                h_process, None, dll_length, VIRTUAL_MEM, PAGE_READWRITE
            )
            if not alloc_address:
                self.log("[!] Memory allocation failed.")
                self.kernel32.CloseHandle(h_process)
                return
            bytes_written = c_size_t(0)
            if not self.kernel32.WriteProcessMemory(
                h_process, alloc_address, dll_bytes, dll_length, byref(bytes_written)
            ):
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
            h_thread = self.kernel32.CreateRemoteThread(
                h_process, None, 0, h_loadlib, alloc_address, 0, byref(thread_id)
            )
            if not h_thread:
                self.log("[!] Remote thread creation failed.")
                self.kernel32.CloseHandle(h_process)
                return
            self.log("[+] M1UI DLL injected successfully.")
            self.injection_done = True
            self.injected_pid = PID
            threading.Timer(
                3.0,
                self.locate_injected_dll,
                args=[dll_path, h_process]
            ).start()
            return  # Stop here for M1UI case

        # ORIGINAL LOGIC
        self.save_last_dll_path(dll_path)
        target_proc = self.get_process_info_by_name("M1-Win64-Shipping.exe")
        if not target_proc:
            self.log("[!] Target process not found.")
            return

        # Instant injection CFG update
        if not self.delayed_injection and self.blackcipher_delay.get():
            try:
                game_folder = self.find_game_folder()
                cfg_file = game_folder / "M1" / "Binaries" / "Win64" / "CFG.ini"
                if cfg_file.exists():
                    with open(cfg_file, "r") as f:
                        lines = f.readlines()
                    found = False
                    for i, line in enumerate(lines):
                        if line.startswith("BlackCipherDelay"):
                            lines[i] = f"BlackCipherDelay = {self.blackcipher_delay.get():.6f}\n"
                            found = True
                    if not found:
                        lines.append(f"BlackCipherDelay = {self.blackcipher_delay.get():.6f}\n")
                    with open(cfg_file, "w") as f:
                        f.writelines(lines)
                    self.log(f"[i] Updated BlackCipherDelay to {self.blackcipher_delay.get():.6f}")
            except Exception as e:
                self.log(f"[!] Failed to update BlackCipherDelay: {e}")

        PID = target_proc.info['pid']
        dll_bytes = dll_path.encode('ascii') + b'\x00'
        dll_length = len(dll_bytes)
        h_process = self.kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, PID)
        if not h_process:
            self.log(f"[!] Could not open process {PID}")
            return
        alloc_address = self.kernel32.VirtualAllocEx(
            h_process, None, dll_length, VIRTUAL_MEM, PAGE_READWRITE
        )
        if not alloc_address:
            self.log("[!] Memory allocation failed.")
            self.kernel32.CloseHandle(h_process)
            return
        bytes_written = c_size_t(0)
        if not self.kernel32.WriteProcessMemory(
            h_process, alloc_address, dll_bytes, dll_length, byref(bytes_written)
        ):
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
        h_thread = self.kernel32.CreateRemoteThread(
            h_process, None, 0, h_loadlib, alloc_address, 0, byref(thread_id)
        )
        if not h_thread:
            self.log("[!] Remote thread creation failed.")
            self.kernel32.CloseHandle(h_process)
            return
        self.log("[+] DLL injected successfully.")
        self.injection_done = True
        self.injected_pid = PID
        threading.Timer(
            3.0,
            self.locate_injected_dll,
            args=[dll_path, h_process]
        ).start()

    # ------------------ Auto Inject Thread ------------------
    def start_auto_inject_thread(self):
        def monitor():
            while True:
                proc = self.get_process_info_by_name("M1-Win64-Shipping.exe")
                if proc:
                    if not self.injection_done:
                        if self.delayed_injection:
                            self.log("[i] Target process found. Waiting 25s, killing BlackCipher64.aes, then waiting 15s...")
                            time.sleep(25)
                            self.kill_blackcipher()
                            time.sleep(15)
                        self.log("[i] Injecting DLL now...")
                        self.inject_dll()
                else:
                    if self.injection_done:
                        self.log("[i] Target process exited. Resetting injector state.")
                        self.injection_done = False
                        self.injected_pid = None
                time.sleep(2)
        threading.Thread(target=monitor, daemon=True).start()

    # ------------------ Last DLL Path ------------------
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

# ------------------ Main ------------------
if __name__ == '__main__':
    try:
        root = tk.Tk()
        app = DLLInjectorGUI(root)
        root.mainloop()
    except Exception as e:
        print("[!] Uncaught Exception:\n" + str(e))