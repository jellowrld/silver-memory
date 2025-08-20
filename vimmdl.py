import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
from bs4 import BeautifulSoup
import os
import threading
import concurrent.futures
import re
import urllib.parse
from queue import Queue

class VimmGameSearcher:
    def __init__(self, root):
        self.root = root
        self.root.title("Vimm's Lair Game Downloader")
        self.root.geometry("700x600")

        # Console list
        self.consoles = {
            "NES": "NES",
            "SNES": "SNES",
            "Nintendo 64": "N64",
            "GameCube": "GameCube",
            "Wii": "Wii",
            "Game Boy": "GameBoy",
            "Game Boy Advance": "GBA",
            "Nintendo DS": "DS",
            "PlayStation": "PS1",
            "PlayStation 2": "PS2",
            "PSP": "PSP",
            "Xbox": "Xbox",
            "Xbox 360": "Xbox360"
        }

        # Download status
        self.download_queue = Queue()
        self.current_download = None
        self.cancel_download = False
        self.active_downloads = 0
        self.max_connections = 4  # Number of parallel download threads

        # GUI Elements
        self.create_widgets()

    def create_widgets(self):
        # Console selection
        tk.Label(self.root, text="Select Console:").pack(pady=5)
        self.console_var = tk.StringVar()
        self.console_dropdown = ttk.Combobox(self.root, textvariable=self.console_var, values=list(self.consoles.keys()), state="readonly")
        self.console_dropdown.pack(pady=5)
        self.console_dropdown.set("NES")

        # Search options
        tk.Label(self.root, text="Enter Game Name:").pack(pady=5)
        self.game_entry = tk.Entry(self.root, width=50)
        self.game_entry.pack(pady=5)

        # Advanced search options
        self.exact_match_var = tk.BooleanVar()
        tk.Checkbutton(self.root, text="Exact Match", variable=self.exact_match_var).pack(pady=5)
        tk.Label(self.root, text="Region Filter (e.g., USA, Europe, Japan, leave blank for all):").pack(pady=5)
        self.region_entry = tk.Entry(self.root, width=50)
        self.region_entry.pack(pady=5)

        # Search button
        tk.Button(self.root, text="Search Games", command=self.search_games).pack(pady=10)

        # Results display
        self.result_text = tk.Text(self.root, height=15, width=80)
        self.result_text.pack(pady=10)

        # Download queue display
        tk.Label(self.root, text="Download Queue:").pack(pady=5)
        self.queue_text = tk.Text(self.root, height=5, width=80, state="disabled")
        self.queue_text.pack(pady=5)

        # Progress bar
        self.progress = ttk.Progressbar(self.root, length=400, mode='determinate')
        self.progress.pack(pady=5)

        # Progress label
        self.progress_label = tk.Label(self.root, text="")
        self.progress_label.pack(pady=5)

        # Cancel download button
        self.cancel_button = tk.Button(self.root, text="Cancel Current Download", command=self.cancel_download_action, state="disabled")
        self.cancel_button.pack(pady=5)

    def search_games(self):
        console = self.console_var.get()
        game_name = self.game_entry.get().strip()
        region = self.region_entry.get().strip().lower()
        exact_match = self.exact_match_var.get()

        if not console:
            messagebox.showerror("Error", "Please select a console!")
            return
        if not game_name:
            messagebox.showerror("Error", "Please enter a game name!")
            return

        # Clear previous results
        self.result_text.delete(1.0, tk.END)
        self.progress["value"] = 0
        self.progress_label.config(text="")

        # Construct search URL
        console_code = self.consoles[console]
        search_url = f"https://vimm.net/vault/{console_code}"

        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(search_url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find game table
            games_found = False
            for row in soup.select("table tr"):
                cells = row.find_all("td")
                if len(cells) > 1:
                    game_title = cells[0].text.strip()
                    region_text = cells[1].text.strip().lower() if len(cells) > 1 else ""
                    # Apply filters
                    if exact_match and game_name.lower() != game_title.lower():
                        continue
                    if not exact_match and game_name.lower() not in game_title.lower():
                        continue
                    if region and region not in region_text:
                        continue
                    games_found = True
                    download_link = None
                    link_tag = cells[0].find("a", href=True)
                    if link_tag and "vault" in link_tag['href']:
                        download_link = f"https://vimm.net{link_tag['href']}"
                    result = f"Game: {game_title}\nRegion: {region_text or 'N/A'}\n"
                    if download_link:
                        result += f"Download: {download_link}\n"
                        self.result_text.insert(tk.END, result)
                        start_index = self.result_text.index(tk.END + "-2l linestart")
                        end_index = self.result_text.index(tk.END + "-1l lineend")
                        self.result_text.tag_add(f"link_{download_link}", start_index, end_index)
                        self.result_text.tag_configure(f"link_{download_link}", foreground="blue", underline=True)
                        self.result_text.tag_bind(f"link_{download_link}", "<Button-1>", lambda e, url=download_link, title=game_title: self.queue_download(url, title))
                    else:
                        result += "Download: Not available\n"
                        self.result_text.insert(tk.END, result)
                    self.result_text.insert(tk.END, "-" * 50 + "\n")

            if not games_found:
                self.result_text.insert(tk.END, f"No games found for '{game_name}' on {console}.\n")

        except requests.RequestException as e:
            messagebox.showerror("Error", f"Failed to fetch data: {e}")

    def queue_download(self, url, game_title):
        # Prompt for save location
        file_ext = self.get_file_extension(url) or ".zip"
        file_name = re.sub(r'[<>:"/\\|?*]', '_', game_title) + file_ext
        save_path = filedialog.asksaveasfilename(defaultextension=file_ext, initialfile=file_name, filetypes=[(f"{file_ext[1:].upper()} files", f"*{file_ext}"), ("All files", "*.*")])
        if not save_path:
            return

        # Add to download queue
        self.download_queue.put((url, save_path, game_title))
        self.update_queue_display()
        self.process_queue()

    def update_queue_display(self):
        self.queue_text.config(state="normal")
        self.queue_text.delete(1.0, tk.END)
        queue_list = []
        temp_queue = Queue()
        while not self.download_queue.empty():
            item = self.download_queue.get()
            queue_list.append(item[2])  # Game title
            temp_queue.put(item)
        self.download_queue = temp_queue
        if self.current_download:
            self.queue_text.insert(tk.END, f"Current: {self.current_download[2]}\n")
        for i, title in enumerate(queue_list, 1):
            self.queue_text.insert(tk.END, f"Queued ({i}): {title}\n")
        self.queue_text.config(state="disabled")

    def get_file_extension(self, url):
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.head(url, headers=headers, allow_redirects=True)
            content_type = response.headers.get('Content-Type', '')
            content_disposition = response.headers.get('Content-Disposition', '')
            if 'filename=' in content_disposition:
                filename = re.findall(r'filename="(.+)"', content_disposition)
                if filename:
                    return os.path.splitext(filename[0])[1].lower()
            if 'application/zip' in content_type:
                return '.zip'
            elif 'application/x-iso9660-image' in content_type:
                return '.iso'
            elif 'application/octet-stream' in content_type:
                parsed = urllib.parse.urlparse(url)
                return os.path.splitext(parsed.path)[1].lower() or '.bin'
        except requests.RequestException:
            pass
        return None

    def process_queue(self):
        if self.active_downloads >= 1 or self.download_queue.empty():
            return
        self.current_download = self.download_queue.get()
        self.active_downloads += 1
        self.cancel_download = False
        self.cancel_button.config(state="normal")
        self.update_queue_display()
        threading.Thread(target=self.download_file, args=self.current_download, daemon=True).start()

    def download_file(self, url, save_path, game_title):
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            # Check if file exists for resuming
            existing_size = os.path.getsize(save_path) if os.path.exists(save_path) else 0
            response = requests.head(url, headers=headers, allow_redirects=True)
            total_size = int(response.headers.get('content-length', 0))

            if total_size == 0:
                self.root.after(0, lambda: messagebox.showerror("Error", "Cannot determine file size."))
                self.cleanup_download(save_path)
                return

            # Split file into chunks for multi-threaded downloading
            chunk_size = total_size // self.max_connections
            ranges = [(i * chunk_size, (i + 1) * chunk_size - 1) for i in range(self.max_connections)]
            ranges[-1] = (ranges[-1][0], total_size - 1)  # Adjust last chunk to include remainder

            # Skip chunks already downloaded
            if existing_size > 0 and existing_size < total_size:
                ranges = [(start, end) for start, end in ranges if start >= existing_size]
                if not ranges:
                    self.root.after(0, lambda: self.progress_label.config(text="Download already complete!"))
                    self.cleanup_download(save_path)
                    return
            elif existing_size >= total_size:
                self.root.after(0, lambda: self.progress_label.config(text="Download already complete!"))
                self.cleanup_download(save_path)
                return
            else:
                existing_size = 0

            self.progress["maximum"] = total_size
            self.progress["value"] = existing_size
            downloaded_size = existing_size
            temp_files = []

            def download_chunk(start, end, chunk_index):
                chunk_file = f"{save_path}.part{chunk_index}"
                temp_files.append(chunk_file)
                chunk_headers = headers.copy()
                chunk_headers['Range'] = f'bytes={start}-{end}'
                with open(chunk_file, 'ab' if start < existing_size else 'wb') as f:
                    with requests.get(url, headers=chunk_headers, stream=True, allow_redirects=True) as r:
                        r.raise_for_status()
                        for chunk in r.iter_content(chunk_size=8192):
                            if self.cancel_download:
                                return False
                            if chunk:
                                f.write(chunk)
                                nonlocal downloaded_size
                                downloaded_size += len(chunk)
                                self.root.after(0, lambda: self.progress.configure(value=downloaded_size))
                                percent = (downloaded_size / total_size * 100) if total_size > 0 else 0
                                self.root.after(0, lambda: self.progress_label.config(text=f"Downloading {game_title}: {percent:.1f}% ({downloaded_size / 1024 / 1024:.2f} MB / {total_size / 1024 / 1024:.2f} MB)"))
                return True

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_connections) as executor:
                futures = [executor.submit(download_chunk, start, end, i) for i, (start, end) in enumerate(ranges)]
                for future in concurrent.futures.as_completed(futures):
                    if not future.result():
                        self.root.after(0, lambda: self.progress_label.config(text="Download canceled!"))
                        self.cleanup_download(save_path, temp_files)
                        return

            # Combine chunks
            with open(save_path, 'ab' if existing_size > 0 else 'wb') as f:
                for i in range(self.max_connections):
                    chunk_file = f"{save_path}.part{i}"
                    if os.path.exists(chunk_file):
                        with open(chunk_file, 'rb') as cf:
                            f.write(cf.read())
                        os.remove(chunk_file)

            self.root.after(0, lambda: self.progress_label.config(text=f"Download completed: {game_title}!"))
            self.cleanup_download(save_path)

        except requests.RequestException as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Download failed: {e}"))
            self.cleanup_download(save_path, temp_files if 'temp_files' in locals() else [])

    def cleanup_download(self, save_path, temp_files=None):
        self.active_downloads = 0
        self.current_download = None
        self.cancel_button.config(state="disabled")
        self.progress["value"] = 0
        if temp_files:
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        if self.cancel_download and os.path.exists(save_path):
            os.remove(save_path)
        self.process_queue()

    def cancel_download_action(self):
        if self.active_downloads > 0:
            self.cancel_download = True

def main():
    root = tk.Tk()
    app = VimmGameSearcher(root)
    root.mainloop()

if __name__ == "__main__":
    main()