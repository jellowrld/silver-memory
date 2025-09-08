#!/usr/bin/env python3
"""
Destiny 2 Folder Finder with GUI (Full Copy-Paste Version)

Finds Destiny 2, Bungie, BattlEye, crash dumps, screenshots, capture folders,
log files, temp files, and Steam/Battle.net caches using registry and Steam
libraries. Supports Epic Games Store. Displays in a Tkinter GUI with clickable
entries to open in Explorer, plus buttons to delete all or individual folders.
Includes folder sizes, async calculation, refresh button, and progress bar.

For personal visibility and privacy management only.
"""

import os, re, subprocess, winreg, json, platform, ctypes, logging, shutil, threading, queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

APPID = '1085660'  # Destiny 2 Steam app id

# Logging
logging.basicConfig(level=logging.INFO, filename='destiny2_folder_finder.log', filemode='w',
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ---------------- Utility Functions ----------------
def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except: return False

def get_steam_path_from_registry():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam_path_str, _ = winreg.QueryValueEx(key, "SteamPath")
        winreg.CloseKey(key)
        if steam_path_str and Path(steam_path_str).exists():
            return Path(steam_path_str)
    except Exception as e:
        logging.warning(f"Failed to get Steam path: {e}")
    return None

# ---------------- Steam Library Parsing ----------------
def parse_libraryfolders(steam_path: Path):
    paths = set()
    if not steam_path or not steam_path.exists():
        return []
    vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.exists():
        return [steam_path]
    try:
        text = vdf_path.read_text(encoding="utf-8", errors="ignore")
        patterns = [r'"path"\s+"([^"]+)"', r'"\d+"\s+"([A-Za-z]:\\\\[^"]+)"', r'"\d+"\s*:\s*"([A-Za-z]:\\\\[^"]+)"']
        for pattern in patterns:
            for m in re.finditer(pattern, text):
                raw = m.group(1).replace("\\\\", "\\")
                p = Path(raw)
                if p.exists(): paths.add(str(p.resolve()))
        paths.add(str(steam_path.resolve()))
        return [Path(p) for p in paths]
    except Exception as e:
        logging.error(f"Failed to parse libraryfolders.vdf: {e}")
        return [steam_path]

def find_destiny_install(steam_path: Path):
    found = []
    if not steam_path: return found
    for lib in parse_libraryfolders(steam_path):
        try:
            manifest = Path(lib) / "steamapps" / f"appmanifest_{APPID}.acf"
            install_dir = Path(lib) / "steamapps" / "common" / "Destiny 2"
            if manifest.exists() or install_dir.exists():
                found.append(install_dir.resolve() if install_dir.exists() else (lib.resolve() / "steamapps" / "common" / "Destiny 2"))
        except Exception as e:
            logging.warning(f"Error checking Steam library {lib}: {e}")
    return found

def find_epic_destiny_install():
    found = []
    try:
        manifest_dir = Path(os.environ.get("PROGRAMDATA", "")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        if manifest_dir.exists():
            for item_file in manifest_dir.glob("*.item"):
                try:
                    with open(item_file, 'r', encoding='utf-8') as f: data = json.load(f)
                    if data.get("AppName") == "Destiny 2":
                        install_location = data.get("InstallLocation")
                        if install_location and Path(install_location).exists():
                            found.append(Path(install_location).resolve())
                except: continue
    except: pass
    default_epic = Path(r"C:\Program Files\Epic Games\Destiny 2")
    if default_epic.exists() and default_epic.resolve() not in found: found.append(default_epic.resolve())
    return found

def find_destiny_install_all(cached_steam_path):
    steam_installs = find_destiny_install(cached_steam_path) if cached_steam_path else []
    epic_installs = find_epic_destiny_install()
    all_installs = []
    for p in (steam_installs + epic_installs):
        try:
            rp = Path(p).resolve()
            if rp not in all_installs: all_installs.append(rp)
        except: continue
    return all_installs

def find_bungie_appdata():
    results = []
    for env in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(env)
        if base:
            path = Path(base) / "Bungie" / "DestinyPC"
            if path.exists(): results.append(path.resolve())
    return results

def find_battleye(destiny_paths):
    results = [p.resolve() for p in [Path(r"C:\Program Files (x86)\Common Files\BattlEye"), Path(r"C:\Program Files\Common Files\BattlEye")] if p.exists()]
    for dp in destiny_paths:
        for sub in ("BattlEye", "battleye"):
            candidate = Path(dp) / sub
            if candidate.exists(): results.append(candidate.resolve())
    return list({p for p in results})

def find_crash_dumps(): p = Path(os.environ.get("LOCALAPPDATA", "")) / "CrashDumps"; return [p.resolve()] if p.exists() else []

def find_steam_screenshots(steam_path):
    results = []
    if not steam_path: return results
    userdata = steam_path / "userdata"
    if not userdata.exists(): return results
    for uid in userdata.iterdir():
        path = uid / "760" / "remote" / APPID / "screenshots"
        if path.exists(): results.append(path.resolve())
    return results

def find_capture_folders():
    results = []
    user = Path.home()
    for p in [user / "Videos" / "Captures", user / "Videos" / "Destiny 2", user / "Videos" / "Gameplay", user / "Pictures" / "Screenshots"]:
        if p.exists(): results.append(p.resolve())
    return results

def find_log_files(destiny_paths):
    results = []
    for destiny_path in destiny_paths:
        candidate = Path(destiny_path) / "logs"
        if candidate.exists(): results.append(candidate.resolve())
    for p in [Path(os.environ.get("APPDATA", "")) / "Bungie" / "DestinyPC" / "logs",
              Path(os.environ.get("LOCALAPPDATA", "")) / "Bungie" / "DestinyPC" / "logs"]:
        if p.exists(): results.append(p.resolve())
    return list({p for p in results})

def find_temp_files(destiny_paths):
    results = []
    for destiny_path in destiny_paths:
        candidate = Path(destiny_path) / "temp"
        if candidate.exists(): results.append(candidate.resolve())
    for p in [Path(os.environ.get("TEMP", "")) / "Bungie", Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" / "Bungie"]:
        if p.exists(): results.append(p.resolve())
    return list({p for p in results})

def find_steam_battlenet_caches():
    candidates = [Path(os.environ.get("PROGRAMDATA", "")) / "Steam",
                  Path(os.environ.get("APPDATA", "")) / "Steam",
                  Path(os.environ.get("PROGRAMDATA", "")) / "Battle.net",
                  Path(os.environ.get("APPDATA", "")) / "Battle.net",
                  Path(os.environ.get("LOCALAPPDATA", "")) / "Battle.net"]
    return list({p.resolve() for p in candidates if p.exists()})

def get_folder_size_mb(p: Path):
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(p):
            for f in filenames:
                try: total += os.path.getsize(os.path.join(dirpath,f))
                except: continue
        return round(total / (1024*1024),2)
    except: return 0.0

def open_in_explorer(path: Path):
    try: subprocess.Popen(["explorer", str(path)])
    except: messagebox.showerror("Error", f"Could not open {path}")

def safe_delete(p: Path, deleted: list, failed: list, allowed_roots: list, critical_dirs: list, status_label=None):
    if not p.exists(): failed.append(f"{p}: Not found"); return
    try: p_resolved = p.resolve()
    except: failed.append(f"{p}: Resolve failed"); return
    if any(p_resolved == cd.resolve() or cd.resolve() in p_resolved.parents for cd in critical_dirs if cd.exists()):
        failed.append(f"{p_resolved}: Skipped (critical)"); return
    if allowed_roots and not any(str(p_resolved).startswith(str(r.resolve())) for r in allowed_roots if r.exists()):
        failed.append(f"{p_resolved}: Skipped (outside allowed roots)"); return
    if status_label: status_label.config(text=f"Deleting {p_resolved.name}..."); status_label.update()
    try: shutil.rmtree(p_resolved); deleted.append(str(p_resolved))
    except Exception as e: failed.append(f"{p_resolved}: {e}")

def delete_folders(categories, allowed_roots, root_window):
    if not messagebox.askyesno("Confirm Deletion","Delete all found folders?"): return
    deleted, failed = [], []
    critical_dirs = [Path(os.environ.get(e)) for e in ["PROGRAMDATA","APPDATA","LOCALAPPDATA","TEMP"] if os.environ.get(e)] + [Path(r"C:\Program Files"),Path(r"C:\Program Files (x86)"), Path.home()]
    status_label = tk.Label(root_window,text="Starting deletion...", fg="blue"); status_label.pack(pady=5)
    total_folders = sum(len(paths) for paths in categories.values()); progress=0
    for cat, paths in categories.items():
        for p in paths:
            safe_delete(p, deleted, failed, allowed_roots, critical_dirs, status_label)
            progress+=1; status_label.config(text=f"Progress: {progress}/{total_folders}"); root_window.update_idletasks()
    status_label.destroy()
    msg=""
    if deleted: msg+="Deleted:\n"+"\n".join(deleted)+"\n\n"
    if failed: msg+="Failed/Skipped:\n"+"\n".join(failed)
    if not deleted and not failed: msg="No folders found."
    messagebox.showinfo("Deletion Results", msg)

def delete_selected(tree, allowed_roots, root_window):
    item = tree.selection(); 
    if not item: return
    text = tree.item(item[0], "text"); path=Path(text.split(" (")[0])
    if not path.exists(): messagebox.showwarning("Not found",f"{path} does not exist"); return
    if not messagebox.askyesno("Confirm Deletion",f"Delete this folder?\n{path}"): return
    deleted, failed = [], []
    critical_dirs = [Path(os.environ.get(e)) for e in ["PROGRAMDATA","APPDATA","LOCALAPPDATA","TEMP"] if os.environ.get(e)] + [Path(r"C:\Program Files"),Path(r"C:\Program Files (x86)"), Path.home()]
    status_label = tk.Label(root_window,text=f"Deleting {path.name}...", fg="blue"); status_label.pack(pady=5); root_window.update()
    safe_delete(path, deleted, failed, allowed_roots, critical_dirs, status_label); status_label.destroy()
    msg=""
    if deleted: msg+="Deleted:\n"+ "\n".join(deleted)+"\n\n"
    if failed: msg+="Failed/Skipped:\n"+ "\n".join(failed)
    messagebox.showinfo("Deletion Results", msg)

# ---------------- Async folder-size calculation ----------------
def calculate_sizes_async(tree, q, stop_event):
    while not stop_event.is_set():
        try: item, path = q.get(timeout=0.1)
        except: continue
        size = get_folder_size_mb(path)
        tree.set(item,"size",size)
        tree.item(item,text=f"{str(path)} ({size} MB)")
        q.task_done()

# ---------------- Refresh Tree ----------------
def refresh_tree(tree, categories, allowed_roots, stop_event):
    for i in tree.get_children(): tree.delete(i)
    total_count=0; q=queue.Queue()
    for cat, paths in categories.items():
        parent = tree.insert("", "end", text=cat, open=True, values=("",))
        if paths:
            for p in paths:
                item_id=tree.insert(parent,"end", text=f"{str(p)} (calculating...)", values=("",))
                q.put((item_id,p)); total_count+=1
        else: tree.insert(parent,"end",text="— None found —", tags=("dim",))
    tree.tag_configure("dim", foreground="gray")
    return total_count,q

# ---------------- Main ----------------
def main():
    if platform.system()!="Windows": messagebox.showerror("Unsupported OS","Windows only"); return
    if not is_admin(): messagebox.showwarning("Warning","Not running as admin")
    cached_steam_path=get_steam_path_from_registry()

    # Initial scan
    destiny_installs=find_destiny_install_all(cached_steam_path)
    bungie=find_bungie_appdata()
    battleye=find_battleye(destiny_installs)
    dumps=find_crash_dumps()
    steam_shots=find_steam_screenshots(cached_steam_path) if cached_steam_path else []
    captures=find_capture_folders()
    logs=find_log_files(destiny_installs)
    temp_files=find_temp_files(destiny_installs)
    steam_battlenet=find_steam_battlenet_caches()
    categories={
        "Destiny 2 Install": destiny_installs,
        "Bungie AppData": bungie,
        "BattlEye": battleye,
        "Crash Dumps": dumps,
        "Steam Screenshots": steam_shots,
        "Video/Capture Folders": captures,
        "Log Files": logs,
        "Temporary Files": temp_files,
        "Steam/Battle.net Caches": steam_battlenet
    }

    allowed_roots=[p for p in [cached_steam_path, Path.home()] if p and p.exists()]
    for env in ["LOCALAPPDATA","APPDATA"]:
        p=Path(os.environ.get(env,"")); 
        if p.exists(): allowed_roots.append(p)
    epic_root=Path(r"C:\Program Files\Epic Games"); 
    if epic_root.exists(): allowed_roots.append(epic_root)

    root=tk.Tk(); root.title("Destiny 2 Folder Finder")

    tree=ttk.Treeview(root, columns=("size",), show="tree headings")
    tree.heading("#0", text="Path"); tree.heading("size", text="Size (MB)")
    tree.pack(fill="both", expand=True)

    stop_event=threading.Event()
    total_count,q=refresh_tree(tree,categories,allowed_roots,stop_event)

    t=threading.Thread(target=calculate_sizes_async,args=(tree,q,stop_event),daemon=True); t.start()

    def on_double_click(event):
        item=tree.selection()
        if not item: return
        text=tree.item(item[0],"text")
        if text.startswith("—") or text in categories.keys(): return
        path_str=text.split(" (")[0]; p=Path(path_str)
        if p.exists(): open_in_explorer(p)
    tree.bind("<Double-1>",on_double_click)

    menu=tk.Menu(root, tearoff=0)
    menu.add_command(label="Delete This Folder", command=lambda: delete_selected(tree, allowed_roots, root))
    def on_right_click(event):
        item=tree.identify_row(event.y)
        if item: tree.selection_set(item); menu.post(event.x_root,event.y_root)
    tree.bind("<Button-3>",on_right_click)

    delete_button=ttk.Button(root,text="Delete All Found Folders",command=lambda: delete_folders(categories, allowed_roots, root))
    delete_button.pack(pady=5)
    if total_count==0: delete_button.state(["disabled"])

    def refresh_action():
        nonlocal total_count,q
        destiny_installs=find_destiny_install_all(cached_steam_path)
        bungie=find_bungie_appdata()
        battleye=find_battleye(destiny_installs)
        dumps=find_crash_dumps()
        steam_shots=find_steam_screenshots(cached_steam_path) if cached_steam_path else []
        captures=find_capture_folders()
        logs=find_log_files(destiny_installs)
        temp_files=find_temp_files(destiny_installs)
        steam_battlenet=find_steam_battlenet_caches()
        new_categories={
            "Destiny 2 Install": destiny_installs,
            "Bungie AppData": bungie,
            "BattlEye": battleye,
            "Crash Dumps": dumps,
            "Steam Screenshots": steam_shots,
            "Video/Capture Folders": captures,
            "Log Files": logs,
            "Temporary Files": temp_files,
            "Steam/Battle.net Caches": steam_battlenet
        }
        categories.clear(); categories.update(new_categories)
        total_count,q=refresh_tree(tree,categories,allowed_roots,stop_event)

    refresh_button=ttk.Button(root,text="Refresh",command=refresh_action); refresh_button.pack(pady=5)

    # Progress bar
    progress_bar=ttk.Progressbar(root, orient="horizontal", mode="determinate", maximum=total_count)
    progress_bar.pack(fill="x", padx=10, pady=5)

    def update_progress():
        completed = total_count - q.qsize() if q else total_count
        progress_bar['value'] = completed
        root.after(100, update_progress)
    update_progress()

    status=ttk.Label(root,text=f"Total folders found: {total_count}",anchor="w"); status.pack(fill="x",side="bottom")

    root.protocol("WM_DELETE_WINDOW", lambda: (stop_event.set(), root.destroy()))
    root.mainloop()

if __name__=="__main__":
    main()