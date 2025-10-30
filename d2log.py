import os
import tkinter as tk
from tkinter import messagebox, Menu
import subprocess
import fnmatch
import shutil

# Expanded for more games and crash artifacts, including CS2 and similar (Overwatch, PUBG, Rainbow Six Siege)
TARGET_FILES = [
    'crash_info.txt', 'DestinyCrashReport.log', 'CrashLogGenerator.exe', 
    '*.dmp', '*.mdmp', '*.log', 'error.txt', 'crashreport.log', 
    'FortniteGame.log', 'VALORANT*.log', 'r3dlog.txt', 'apex_crash.txt', 
    'hs_err_pid*.log', 'crash*.txt', 'error*.log', 'console.log', 
    'cs2*.dmp', 'csgo.log', 'ow*.log', 'pubg*.dmp', 'siege*.log'
]

TARGET_FOLDERS = [
    'Destiny 2', 'Destiny2_', 'Fortnite', 'FortniteGame', 'VALORANT', 
    'League of Legends', 'Apex', 'Respawn', 'Call of Duty', 'Modern Warfare', 
    'Warzone', 'Activision', 'Riot Games', 'crash_reports', 'Logs', 
    'CrashDumps', 'Crash', 'Saved', 'Temp', 'Counter-Strike 2', 'csgo', 
    'dumps', 'Overwatch', 'PUBG', 'TslGame', 'Rainbow Six', 'Ubisoft'
]

SEARCH_ROOTS = [
    os.path.expanduser('~'),
    os.environ.get('APPDATA', ''),
    os.environ.get('LOCALAPPDATA', ''),
    os.environ.get('TEMP', ''),
    os.environ.get('TMP', ''),
    os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Temp'),
    'C:\\Program Files',
    'C:\\Program Files (x86)',
    'C:\\ProgramData',
    'C:\\Program Files\\Steam\\steamapps\\common',
    'C:\\Program Files (x86)\\Steam\\steamapps\\common',
    'C:\\Program Files\\Steam',
    'C:\\Program Files (x86)\\Steam',
    'D:\\Steam\\steamapps\\common',
    'E:\\SteamLibrary\\steamapps\\common',
    'C:\\Program Files\\Epic Games',
    'C:\\Program Files\\Epic Games\\Fortnite',
    'C:\\Program Files\\Epic Games\\Destiny2',
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Bungie'),
    os.path.join(os.environ.get('APPDATA', ''), 'Bungie'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'CrashDumps'),
    os.path.join(os.path.expanduser('~'), 'OneDrive', 'Documents'),
    os.path.join(os.path.expanduser('~'), 'OneDrive', 'AppData'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'FortniteGame'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'VALORANT'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Riot Games'),
    os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'Riot Games'),
    os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), 'Riot Games'),
    'C:\\Riot Games',
    os.path.join(os.environ.get('USERPROFILE', ''), 'Saved Games'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Activision'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Battle.net'),
    'C:\\Program Files\\Battle.net',
    'C:\\Program Files (x86)\\Battle.net',
    'C:\\Windows\\Minidump',
    os.path.join(os.environ.get('USERPROFILE', ''), 'Documents', 'My Games'),
    'C:\\Program Files (x86)\\Ubisoft',
    'C:\\Program Files\\Ubisoft',
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Overwatch'),
    os.path.join(os.environ.get('APPDATA', ''), 'Battle.net'),
    'C:\\Program Files (x86)\\Steam\\dumps'  # Explicit for Steam dumps
]

CUSTOM_PATHS_FILE = "custom_paths.txt"

if os.path.exists(CUSTOM_PATHS_FILE):
    with open(CUSTOM_PATHS_FILE, "r") as f:
        for line in f:
            path = line.strip()
            if path and os.path.exists(path):
                SEARCH_ROOTS.append(path)

def find_crash_logs(max_depth=5):
    found_items = []
    for root_dir in SEARCH_ROOTS:
        if not os.path.exists(root_dir):
            continue
        for root, dirs, files in os.walk(root_dir):
            depth = root[len(root_dir):].count(os.sep)
            if depth > max_depth:
                dirs[:] = []
                continue
            for file in files:
                if any(fnmatch.fnmatch(file.lower(), pattern.lower()) for pattern in TARGET_FILES):
                    found_items.append(os.path.join(root, file))
            for dir_name in dirs:
                if any(dir_name.lower().startswith(pattern.lower()) for pattern in TARGET_FOLDERS):
                    full_path = os.path.join(root, dir_name)
                    for sub_root, sub_dirs, sub_files in os.walk(full_path):
                        if 'crash_folder' in sub_dirs or any(fnmatch.fnmatch(f.lower(), pattern.lower()) for f in sub_files for pattern in TARGET_FILES):
                            found_items.append(full_path)
                            break
    return list(set(found_items))

def open_directory(path):
    dir_path = os.path.dirname(path) if os.path.isfile(path) else path
    subprocess.Popen(['explorer', dir_path])

def delete_files_in_folder(path):
    if not os.path.isdir(path):
        path = os.path.dirname(path)
    confirm = messagebox.askyesno(
        "Confirm Delete",
        f"⚠️ This will delete ALL files and folders inside:\n{path}\n\nContinue?"
    )
    if not confirm:
        return
    deleted_count = 0
    errors = 0
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.remove(item_path)
                deleted_count += 1
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
                deleted_count += 1
        except Exception as e:
            errors += 1
            print(f"Error deleting {item_path}: {e}")
    messagebox.showinfo(
        "Deletion Complete",
        f"Deleted contents of:\n{path}\n\n"
        f"Removed {deleted_count} item(s).{' Some files could not be deleted.' if errors else ''}"
    )
    refresh_search()

def save_custom_path(path):
    """Save a custom path to the file if it doesn't already exist."""
    existing = []
    if os.path.exists(CUSTOM_PATHS_FILE):
        with open(CUSTOM_PATHS_FILE, "r") as f:
            existing = [line.strip() for line in f.readlines()]
    if path not in existing:
        with open(CUSTOM_PATHS_FILE, "a") as f:
            f.write(path + "\n")

def add_custom_path():
    custom_path = custom_entry.get().strip()
    if custom_path and os.path.exists(custom_path):
        SEARCH_ROOTS.append(custom_path)
        save_custom_path(custom_path)
        messagebox.showinfo("Success", f"Added custom path: {custom_path}")
        refresh_search()
    else:
        messagebox.showerror("Error", "Invalid or non-existent path.")

def refresh_search():
    listbox.delete(0, tk.END)
    found_items.clear()
    found_items.extend(find_crash_logs())
    if found_items:
        for item in found_items:
            listbox.insert(tk.END, item)
    else:
        messagebox.showinfo("No Results", "No crash logs or related folders found.")

root = tk.Tk()
root.title("Multi-Game Crash Log Finder")
root.geometry("650x520")
root.minsize(650, 520)

label = tk.Label(root, text="Found Crash Logs and Folders (Destiny 2, Fortnite, Valorant, LoL, Apex, CoD, CS2, Overwatch, PUBG, R6 Siege, etc.):")
label.pack(pady=10)

listbox = tk.Listbox(root, width=90, height=15)
listbox.pack(pady=10)

scrollbar = tk.Scrollbar(root, orient="vertical")
scrollbar.config(command=listbox.yview)
scrollbar.pack(side="right", fill="y")
listbox.config(yscrollcommand=scrollbar.set)

custom_label = tk.Label(root, text="Add Custom Search Path (e.g., F:\\SteamLibrary):")
custom_label.pack(pady=(5, 2))
custom_entry = tk.Entry(root, width=60)
custom_entry.pack(pady=3)
custom_button = tk.Button(root, text="Add Path and Search", command=add_custom_path)
custom_button.pack(pady=(3, 8))

menu = Menu(root, tearoff=0)
menu.add_command(label="Open Folder", command=lambda: open_directory(selected_path))
menu.add_command(label="Delete ALL Contents", command=lambda: delete_files_in_folder(selected_path))

selected_path = None

def on_right_click(event):
    global selected_path
    try:
        index = listbox.nearest(event.y)
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(index)
        selected_path = found_items[index]
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()

def on_double_click(event):
    selection = event.widget.curselection()
    if selection:
        index = selection[0]
        path = found_items[index]
        open_directory(path)

listbox.bind("<Double-Button-1>", on_double_click)
listbox.bind("<Button-3>", on_right_click)

found_items = []
found_items = find_crash_logs()
if found_items:
    for item in found_items:
        listbox.insert(tk.END, item)
else:
    messagebox.showinfo("No Results", "No crash logs or related folders found in common locations.")

instructions = tk.Label(
    root,
    text=(
        "📜 Instructions:\n"
        "• Double-click — Open folder in File Explorer\n"
        "• Right-click — Delete **all files and subfolders** inside selected folder\n"
        "• Add a custom path to expand search locations.\n\n"
        "Tip: Use this to clean out crash logs, dump files, or temp folders for various games.\n"
        "This will NOT delete the folder itself — only its contents. Be cautious with broad folders like 'Logs'."
    ),
    justify="left",
    fg="gray",
    anchor="w",
    wraplength=600
)
instructions.pack(pady=10, padx=10, fill="x")

root.mainloop()