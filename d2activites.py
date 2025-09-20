import requests
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ⚠️ Your Bungie API keys
API_KEYS = [
    "331da5124114f91928f07e871a3123a",
    "f523d424192d44598a0c56ce0636e058"
]

json_file = "destiny2_activities_full.json"
activity_mapping = {}

# ---------------- UTILITIES ----------------
def log(msg):
    log_box.config(state=tk.NORMAL)
    log_box.insert(tk.END, msg + "\n")
    log_box.see(tk.END)
    log_box.config(state=tk.DISABLED)
    root.update_idletasks()

def try_request(url, api_key):
    resp = requests.get(url, headers={"X-API-Key": api_key})
    resp.raise_for_status()
    return resp.json()

def fetch_manifest(api_key):
    url = "https://www.bungie.net/Platform/Destiny2/Manifest/"
    return try_request(url, api_key)["Response"]

def fetch_definition(path, api_key):
    url = "https://www.bungie.net" + path
    return try_request(url, api_key)

# ---------------- DUMPING ----------------
def start_dump():
    global activity_mapping
    try:
        log("🔑 Checking API keys...")
        api_key = None
        manifest = None
        for key in API_KEYS:
            try:
                manifest = fetch_manifest(key)
                api_key = key
                log(f"✅ Using API key: {key}")
                break
            except Exception as e:
                log(f"❌ Failed key: {key} ({e})")

        if not api_key:
            messagebox.showerror("Error", "No valid API keys worked!")
            return

        paths = manifest["jsonWorldComponentContentPaths"]["en"]

        log("⬇️ Downloading definitions...")
        activity_defs = fetch_definition(paths["DestinyActivityDefinition"], api_key)
        type_defs     = fetch_definition(paths["DestinyActivityTypeDefinition"], api_key)
        mode_defs     = fetch_definition(paths["DestinyActivityModeDefinition"], api_key)
        dest_defs     = fetch_definition(paths["DestinyDestinationDefinition"], api_key)
        place_defs    = fetch_definition(paths["DestinyPlaceDefinition"], api_key)
        mod_defs      = fetch_definition(paths["DestinyActivityModifierDefinition"], api_key)

        activity_mapping = {}
        total = len(activity_defs)
        log(f"📊 Processing {total} activities...")

        progress["maximum"] = total
        count = 0

        for hash_id, defn in activity_defs.items():
            count += 1
            name = defn.get("displayProperties", {}).get("name", "").strip()
            if not name:
                continue

            activity_type = type_defs.get(str(defn.get("activityTypeHash")), {})
            activity_mode = mode_defs.get(str(defn.get("directActivityModeHash")), {})
            destination   = dest_defs.get(str(defn.get("destinationHash")), {})
            place         = place_defs.get(str(defn.get("placeHash")), {})

            modifiers = []
            for mh in defn.get("modifierHashes", []):
                mod = mod_defs.get(str(mh))
                if mod:
                    modifiers.append({
                        "hash": mh,
                        "name": mod.get("displayProperties", {}).get("name"),
                        "description": mod.get("displayProperties", {}).get("description"),
                        "icon": mod.get("displayProperties", {}).get("icon")
                    })

            activity_mapping[hash_id] = {
                "name": name,
                "description": defn.get("displayProperties", {}).get("description", ""),
                "icon": defn.get("displayProperties", {}).get("icon"),
                "pgcrImage": defn.get("pgcrImage"),
                "releaseIcon": defn.get("releaseIcon"),

                "activityType": activity_type.get("displayProperties", {}).get("name"),
                "directMode": activity_mode.get("displayProperties", {}).get("name"),
                "allModes": [
                    mode_defs.get(str(m), {}).get("displayProperties", {}).get("name")
                    for m in defn.get("activityModeHashes", [])
                ],

                "destination": destination.get("displayProperties", {}).get("name"),
                "place": place.get("displayProperties", {}).get("name"),

                "tier": defn.get("tier"),
                "activityLightLevel": defn.get("activityLightLevel"),
                "isPlaylist": defn.get("isPlaylist"),
                "matchmaking": defn.get("matchmaking"),
                "modifiers": modifiers
            }

            progress["value"] = count
            log(f"✔️ {name}")
            root.update_idletasks()

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(activity_mapping, f, indent=2, ensure_ascii=False)

        log("💾 Saved to destiny2_activities_full.json")
        messagebox.showinfo("Done", f"Dumped {len(activity_mapping)} activities with full details!")

        switch_to_search()

    except Exception as e:
        messagebox.showerror("Error", str(e))
        log(f"❌ Error: {e}")

# ---------------- SEARCH MODE ----------------
def switch_to_search():
    for widget in dump_frame.winfo_children():
        widget.pack_forget()
    dump_frame.pack_forget()

    global activity_mapping
    if not activity_mapping:
        with open(json_file, encoding="utf-8") as f:
            activity_mapping = json.load(f)

    global all_names
    all_names = [data["name"] for _, data in activity_mapping.items() if data.get("name")]

    search_frame.pack(fill="both", expand=True)

def update_suggestions(event=None):
    query = search_entry.get().lower()
    suggestions_list.delete(0, tk.END)
    if not query:
        return
    for name in all_names:
        if query in name.lower():
            suggestions_list.insert(tk.END, name)

def use_suggestion(event):
    selection = suggestions_list.curselection()
    if selection:
        picked = suggestions_list.get(selection[0])
        search_entry.delete(0, tk.END)
        search_entry.insert(0, picked)
        search_activity()

def search_activity(show_all=False):
    query = search_entry.get().strip().lower()
    category = category_var.get()

    results_box.config(state=tk.NORMAL)
    results_box.delete("1.0", tk.END)

    found = []
    for hash_id, data in activity_mapping.items():
        matches_query = (not query) if show_all else (query in str(hash_id) or query in data["name"].lower())
        matches_category = (category == "All" or
            category in str(data.get("activityType") or "") or
            category in str(data.get("directMode") or "") or
            any(category in (m or "") for m in data.get("allModes", []))
        )
        if matches_query and matches_category:
            found.append((hash_id, data))

    if not found:
        results_box.insert(tk.END, "No results found.")
    else:
        for hash_id, data in found:
            results_box.insert(tk.END, f"🔹 ID: {hash_id}\n")
            for k, v in data.items():
                results_box.insert(tk.END, f"   {k}: {v}\n")
            results_box.insert(tk.END, "-"*50 + "\n")

    results_box.config(state=tk.DISABLED)

# ---------------- GUI ----------------
root = tk.Tk()
root.title("Destiny 2 Activity Dumper & Search")

# Dump mode frame
dump_frame = tk.Frame(root)
dump_frame.pack(fill="both", expand=True)

ttk.Label(dump_frame, text="Destiny 2 Activity Dumper", font=("Segoe UI", 14, "bold")).pack(pady=10)

progress = ttk.Progressbar(dump_frame, orient="horizontal", length=400, mode="determinate")
progress.pack(pady=5)

log_box = scrolledtext.ScrolledText(dump_frame, wrap=tk.WORD, width=70, height=20, state=tk.DISABLED)
log_box.pack(padx=10, pady=10)

start_btn = ttk.Button(dump_frame, text="Start Dump", command=start_dump)
start_btn.pack(pady=10)

# Search mode frame
search_frame = tk.Frame(root)

ttk.Label(search_frame, text="Search Destiny 2 Activities", font=("Segoe UI", 14, "bold")).pack(pady=10)

search_entry = ttk.Entry(search_frame, width=50)
search_entry.pack(pady=5)
search_entry.bind("<KeyRelease>", update_suggestions)

suggestions_list = tk.Listbox(search_frame, height=6, width=50)
suggestions_list.pack(pady=5)
suggestions_list.bind("<<ListboxSelect>>", use_suggestion)

# Category filter
category_var = tk.StringVar(value="All")
categories = ["All", "Raid", "Dungeon", "Strike", "Nightfall", "Gambit", "PvP", "Playlist"]
ttk.Label(search_frame, text="Filter by Category:").pack(pady=(10,0))
category_menu = ttk.Combobox(search_frame, textvariable=category_var, values=categories, state="readonly")
category_menu.pack(pady=5)

# Buttons
btn_frame = tk.Frame(search_frame)
btn_frame.pack(pady=5)

search_btn = ttk.Button(btn_frame, text="Search", command=lambda: search_activity(False))
search_btn.pack(side="left", padx=5)

show_all_btn = ttk.Button(btn_frame, text="Show All in Category", command=lambda: search_activity(True))
show_all_btn.pack(side="left", padx=5)

results_box = scrolledtext.ScrolledText(search_frame, wrap=tk.WORD, width=80, height=25, state=tk.DISABLED)
results_box.pack(padx=10, pady=10)

root.mainloop()