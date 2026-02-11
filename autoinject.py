import os
import psutil
import time
import threading
import shutil
from ctypes import *
import winreg
import re
from pathlib import Path
import requests
import zipfile
import tempfile
import keyboard   # pip install keyboard
from rich.console import Console
from rich.theme import Theme
import sys

# ────────────────────────────────────────────────
# Rich console setup with colors
# ────────────────────────────────────────────────
console = Console(highlight=False, soft_wrap=True)

theme = Theme({
    "time":    "dim white",
    "info":    "cyan",
    "success": "green bold",
    "warn":    "yellow bold",
    "error":   "red bold",
    "path":    "magenta",
    "inject":  "bright_magenta",
    "state":   "bright_blue",
    "key":     "yellow bold",
})

console = Console(theme=theme)

# Rainbow cycling colors (hex)
RAINBOW = [
    "#ff0000", "#ff4000", "#ff7f00", "#ffbf00", "#ffff00",
    "#c0ff00", "#80ff00", "#40ff00", "#00ff00", "#00ff40",
    "#00ff80", "#00ffbf", "#00ffff", "#00bfff", "#0080ff",
    "#0040ff", "#0000ff", "#4000ff", "#8000ff", "#bf00ff",
    "#ff00ff", "#ff00bf", "#ff0080", "#ff0040",
]

def rainbow_text(text, offset=0):
    """Build rich markup for rainbow text"""
    parts = []
    for i, char in enumerate(text):
        color = RAINBOW[(i + offset) % len(RAINBOW)]
        parts.append(f"[{color}]{char}[/]")
    return "".join(parts)

def animated_log(msg, rainbow=False, frames=6, delay=0.07, final_style="info"):
    """Print message with optional rainbow animation"""
    ts = time.strftime("%H:%M:%S")
    prefix = f"[{ts}] "

    if not rainbow:
        console.print(f"[{final_style}]{prefix}{msg}[/]")
        return

    # Animated rainbow
    for frame in range(frames):
        sys.stdout.write("\r" + " " * 80 + "\r")  # clear line
        colored_prefix = rainbow_text(prefix, frame * 2)
        colored_msg   = rainbow_text(msg,    frame * 2)
        console.print(f"{colored_prefix}{colored_msg}", end="")
        time.sleep(delay)

    # Final static line
    console.print(f"[{final_style}]{prefix}{msg}[/]")


def log(msg, rainbow=False, style="info"):
    animated_log(msg, rainbow=rainbow, frames=7 if rainbow else 0, delay=0.08, final_style=style)


# ────────────────────────────────────────────────
# Your original functions (slightly cleaned up)
# ────────────────────────────────────────────────

def find_dll():
    dlls = list(Path.cwd().glob('*.dll'))
    if not dlls:
        log("No .dll found in current folder.", rainbow=True, style="error")
        sys.exit(1)
    if len(dlls) > 1:
        log(f"Multiple DLLs found → using first: {dlls[0].name}", style="warn")
    path = str(dlls[0].absolute())
    log(f"Using DLL → [path]{path}[/path]")
    return path


def find_game_folder():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
        winreg.CloseKey(key)
        steam_path = Path(steam_path)

        manifest = steam_path / "steamapps" / "appmanifest_2074920.acf"
        if manifest.exists():
            with open(manifest, "r", encoding="utf-8") as f:
                if m := re.search(r'"installdir"\s+"(.+?)"', f.read()):
                    path = steam_path / "steamapps" / "common" / m.group(1)
                    log(f"Game found (primary): [path]{path}[/path]")
                    return path

        lib_vdf = steam_path / "steamapps" / "libraryfolders.vdf"
        if lib_vdf.exists():
            with open(lib_vdf, "r", encoding="utf-8") as f:
                for p_str in re.findall(r'"path"\s+"(.+?)"', f.read()):
                    p = Path(p_str)
                    man = p / "steamapps" / "appmanifest_2074920.acf"
                    if man.exists():
                        with open(man, "r", encoding="utf-8") as af:
                            if m := re.search(r'"installdir"\s+"(.+?)"', af.read()):
                                path = p / "steamapps" / "common" / m.group(1)
                                log(f"Game found (library): [path]{path}[/path]")
                                return path
        return None
    except Exception as e:
        log(f"Cannot locate game folder: {e}", style="error")
        return None


def update_eac_files(game_folder):
    url = "https://github.com/jellowrld/oldeac/archive/refs/heads/main.zip"
    log(f"Downloading EAC bypass files: {url}", rainbow=True)
    try:
        r = requests.get(url, stream=True, timeout=20)
        if r.status_code != 200:
            log(f"Download failed (HTTP {r.status_code})", style="error")
            return
        tmp = Path(tempfile.mkdtemp())
        zipf = tmp / "oldeac.zip"
        with open(zipf, "wb") as f:
            for chunk in r.iter_content(16384):
                f.write(chunk)
        with zipfile.ZipFile(zipf) as z:
            z.extractall(tmp)
        src = next(tmp.glob("oldeac-*"), None)
        if not src:
            log("Extraction folder not found", style="error")
            return
        log(f"Copying files to game folder...", rainbow=True)
        for item in src.iterdir():
            dst = game_folder / item.name
            try:
                if dst.exists():
                    if dst.is_dir():
                        shutil.rmtree(dst, ignore_errors=True)
                    else:
                        dst.unlink()
                if item.is_dir():
                    shutil.copytree(item, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dst)
                log(f"  copied: {item.name}", style="success")
            except Exception as ex:
                log(f"  skip {item.name} → {ex}", style="warn")
        log("EAC files updated", style="success")
    except Exception as e:
        log(f"EAC update failed: {e}", style="error")


def clean_game_folders(game_folder):
    log("Starting cleanup of logs / crashes / webcache / BlackCipher...", rainbow=True)
    user = Path(os.environ.get("USERPROFILE", ""))
    base = user / "AppData" / "Local" / "M1" / "Saved"
    folders = [
        base / "Config" / "CrashReportClient",
        base / "Logs",
        base / "Crashes",
        base / "webcache_4430",
    ]
    for folder in folders:
        if folder.exists():
            try:
                shutil.rmtree(folder, ignore_errors=True)
                log(f"  removed: {folder.name}", style="success")
            except:
                pass
    pipe = base.parent / "M1_PCD3D_SM6.upipelinecache"
    if pipe.exists():
        try:
            pipe.unlink()
            log("  removed pipeline cache", style="success")
        except:
            pass
    bc = game_folder / "M1" / "Binaries" / "Win64" / "BlackCipher"
    if bc.exists():
        for pat in ["*.log", "*.dump"]:
            for f in bc.glob(pat):
                try:
                    f.unlink()
                    log(f"  deleted: {f.name}", style="success")
                except:
                    pass
    log("Cleanup finished", style="success")


def launch_game():
    log("Launching game via Steam...", rainbow=True)
    os.system("start steam://run/2074920")


# ────────────────────────────────────────────────
# Injection logic
# ────────────────────────────────────────────────

PAGE_READWRITE     = 0x04
PROCESS_ALL_ACCESS = (0x000F0000 | 0x00100000 | 0xFFF)
VIRTUAL_MEM        = (0x1000 | 0x2000)

kernel32 = windll.kernel32
kernel32.OpenProcess.argtypes = [c_ulong, c_bool, c_ulong]
kernel32.OpenProcess.restype = c_void_p
kernel32.VirtualAllocEx.argtypes = [c_void_p, c_void_p, c_size_t, c_ulong, c_ulong]
kernel32.VirtualAllocEx.restype = c_void_p
kernel32.WriteProcessMemory.argtypes = [c_void_p, c_void_p, c_void_p, c_size_t, POINTER(c_size_t)]
kernel32.WriteProcessMemory.restype = c_bool
kernel32.GetModuleHandleW.argtypes = [c_wchar_p]
kernel32.GetModuleHandleW.restype = c_void_p
kernel32.GetProcAddress.argtypes = [c_void_p, c_char_p]
kernel32.GetProcAddress.restype = c_void_p
kernel32.CreateRemoteThread.argtypes = [c_void_p, c_void_p, c_size_t, c_void_p, c_void_p, c_ulong, POINTER(c_ulong)]
kernel32.CreateRemoteThread.restype = c_void_p


def inject_dll(dll_path, pid):
    log(f"Injecting into PID {pid}...", rainbow=True, style="inject")
    try:
        path_bytes = (dll_path + '\0').encode('ascii')
        size = len(path_bytes)
        h_proc = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not h_proc:
            log("OpenProcess failed", style="error")
            return False
        addr = kernel32.VirtualAllocEx(h_proc, None, size, VIRTUAL_MEM, PAGE_READWRITE)
        if not addr:
            log("VirtualAllocEx failed", style="error")
            kernel32.CloseHandle(h_proc)
            return False
        written = c_size_t()
        if not kernel32.WriteProcessMemory(h_proc, addr, path_bytes, size, byref(written)):
            log("WriteProcessMemory failed", style="error")
            kernel32.CloseHandle(h_proc)
            return False
        h_k32 = kernel32.GetModuleHandleW("kernel32.dll")
        loadlib = kernel32.GetProcAddress(h_k32, b"LoadLibraryA")
        if not loadlib:
            log("LoadLibraryA not found", style="error")
            kernel32.CloseHandle(h_proc)
            return False
        tid = c_ulong()
        h_th = kernel32.CreateRemoteThread(h_proc, None, 0, loadlib, addr, 0, byref(tid))
        if not h_th:
            log("CreateRemoteThread failed", style="error")
            kernel32.CloseHandle(h_proc)
            return False
        log(f"Injected successfully (TID {tid.value})", style="success")
        kernel32.CloseHandle(h_th)
        kernel32.CloseHandle(h_proc)
        return True
    except Exception as e:
        log(f"Injection exception: {e}", style="error")
        return False


def get_game_pid():
    for p in psutil.process_iter(['pid', 'name']):
        if p.info.get('name', '').lower() == "m1-win64-shipping.exe":
            return p.info['pid']
    return None


# ────────────────────────────────────────────────
# Monitor & keyboard handler
# ────────────────────────────────────────────────

def monitor_and_reinject(dll_path, game_folder):
    injected = False
    while True:
        pid = get_game_pid()
        if pid:
            if not injected:
                log(f"Game detected (PID {pid}) → auto injecting...", rainbow=True)
                inject_dll(dll_path, pid)
                injected = True
        else:
            if injected:
                log("Game closed → state reset. Press [yellow bold]I[/] to restart full sequence (EAC + clean + launch)", style="state")
                injected = False
        time.sleep(1.3)


def keyboard_handler(dll_path, game_folder):
    log("Press [yellow bold]I[/] when game is CLOSED to re-download EAC + clean + launch again", style="key")
    while True:
        if keyboard.is_pressed('i'):
            if get_game_pid() is not None:
                log("Game is still running → ignoring I press", style="warn")
            else:
                log("I pressed → restarting full preparation sequence...", rainbow=True)
                update_eac_files(game_folder)
                clean_game_folders(game_folder)
                launch_game()
            time.sleep(0.6)  # debounce
        time.sleep(0.08)


# ────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────

if __name__ == '__main__':
    console.rule("Jell's Auto-Injector", style="bright_blue on black")

    log("Starting...", rainbow=True)
    dll_path = find_dll()
    game_folder = find_game_folder()

    if not game_folder:
        log("Game folder not found. Exiting.", rainbow=True, style="error")
        sys.exit(1)

    log(f"Game directory → [path]{game_folder}[/path]")

    # Initial sequence
    update_eac_files(game_folder)
    clean_game_folders(game_folder)
    launch_game()

    threading.Thread(target=monitor_and_reinject, args=(dll_path, game_folder), daemon=True).start()
    threading.Thread(target=keyboard_handler, args=(dll_path, game_folder), daemon=True).start()

    log("Running. Press Ctrl+C to exit.", style="state")
    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        log("Exiting.", rainbow=True)