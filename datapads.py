import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import requests
from io import BytesIO
import webbrowser
from bs4 import BeautifulSoup
import re

class Destiny2DataPadApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Destiny 2: The Edge of Fate - Data Pad Locations")
        self.root.geometry("800x600")

        # Scrape image URLs from GameRant article
        self.image_urls = self.scrape_image_urls()

        # Data structure for Data Pads
        self.data_pads = {
            "Solo Ops": [
                {
                    "Op": "Skywatch",
                    "Location": "When you reach the outside area after defeating all enemies and clearing the shielded door, turn around to find this Data Pad on a barrel.",
                    "Image": "Skywatch data pad",
                    "Image_URL": self.image_urls.get("Skywatch data pad", None)
                },
                {
                    "Op": "The Salt Mines",
                    "Location": "After clearing the second room, head through the cave to find a massive pit. Before entering the pit below, pick up the Data Pad, which is on a rusted box.",
                    "Image": "The Salt Mines data pad",
                    "Image_URL": self.image_urls.get("The Salt Mines data pad", None)
                },
                {
                    "Op": "Caldera",
                    "Location": "At the start of the mission, head forward to a cave with a flag above it, and inside this cave is a Data Pad on the immediate right.",
                    "Image": "Caldera data pad",
                    "Image_URL": self.image_urls.get("Caldera data pad", None)
                }
            ],
            "Fireteam Ops": [
                {
                    "Op": "The Glassway",
                    "Locations": [
                        {
                            "Description": "After defeating the first miniboss, head forward to the right of the exit, where the Data Pad is beside a wall with two metal canisters.",
                            "Image": "The Glassway data pad 1",
                            "Image_URL": self.image_urls.get("The Glassway data pad 1", None)
                        },
                        {
                            "Description": "After defeating the second miniboss, head into the floating Vex platform area and take an immediate right to find this Data Pad on a ledge.",
                            "Image": "The Glassway data pad 2",
                            "Image_URL": self.image_urls.get("The Glassway data pad 2", None)
                        }
                    ]
                },
                {
                    "Op": "The Inverted Spire",
                    "Locations": [
                        {
                            "Description": "On the platform before dropping down to the Cabal tanks, players can find this Data Pad.",
                            "Image": "The Inverted Spire data pad 1",
                            "Image_URL": self.image_urls.get("The Inverted Spire data pad 1", None)
                        },
                        {
                            "Description": "After capturing the 3 Cabal plates in the Press Forward objective, head to the right metal grate platform for this Data Pad.",
                            "Image": "The Inverted Spire data pad 2",
                            "Image_URL": self.image_urls.get("The Inverted Spire data pad 2", None)
                        }
                    ]
                },
                {
                    "Op": "Battleground: Conduit",
                    "Locations": [
                        {
                            "Description": "At the beginning of the Op, head down the first sloped tunnel and look to the left wall to find this Data Pad next to a large plant.",
                            "Image": "Battleground Conduit data pad 1",
                            "Image_URL": self.image_urls.get("Battleground Conduit data pad 1", None)
                        },
                        {
                            "Description": "This Data Pad is found on the right ledge before the kneeling Vex that leads to a portal to the final boss.",
                            "Image": "Battleground Conduit data pad 2",
                            "Image_URL": self.image_urls.get("Battleground Conduit data pad 2", None)
                        }
                    ]
                },
                {
                    "Op": "Battleground: Delve",
                    "Locations": [
                        {
                            "Description": "At the start of the Op, head to the left to find this Data Pad on the floor by a Vex pillar.",
                            "Image": "Battleground Delve data pad 1",
                            "Image_URL": self.image_urls.get("Battleground Delve data pad 1", None)
                        },
                        {
                            "Description": "During the Explore the Caverns objective, jump to the left platform that's just before a triangle-shaped door to the final boss encounter for this Data Pad.",
                            "Image": "Battleground Delve data pad 2",
                            "Image_URL": self.image_urls.get("Battleground Delve data pad 2", None)
                        }
                    ]
                }
            ],
            "Empire Hunt": [
                {
                    "Op": "Empire Hunt: The Dark Priestess",
                    "Location": "After defeating the miniboss for the Find Kirdis objective, enter the teleporter and the first stairway on the right contains this Data Pad.",
                    "Image": "Empire Hunt The Dark Priestess data pad",
                    "Image_URL": self.image_urls.get("Empire Hunt The Dark Priestess data pad", None)
                },
                {
                    "Op": "Empire Hunt: The Technocrat",
                    "Location": "In the Pursue Praksis objective, look to the platform on the right for this Data Pad, which is just before the boss room.",
                    "Image": "Empire Hunt The Technocrat data pad 1",
                    "Image_URL": self.image_urls.get("Empire Hunt The Technocrat data pad 1", None)
                },
                {
                    "Op": "Empire Hunt: The Warrior",
                    "Location": "Near the start of this Fireteam Op, players will head right, where, through the tunnels after the Wyvern, players can turn around to check behind the raised pillar, for this Data Pad.",
                    "Image": "Empire Hunt The Warrior data pad 1",
                    "Image_URL": self.image_urls.get("Empire Hunt The Warrior data pad 1", None)
                }
            ],
            "Pinnacle Ops": [
                {
                    "Op": "Encore",
                    "Locations": [
                        {
                            "Description": "At the beginning of the Exotic Mission, head past the well and go to the left path and forward, where beneath the cliff is a mossy ledge that can be climbed down to find a rock cave with a Data Pad deep inside on a mossy floor behind a waterfall.",
                            "Image": None,
                            "Image_URL": None
                        },
                        {
                            "Description": "Before the final boss room, look to the left just before dropping down in the open circle door for this Data Pad.",
                            "Image": None,
                            "Image_URL": None
                        }
                    ]
                },
                {
                    "Op": "Kell's Fall",
                    "Locations": [
                        {
                            "Description": "Before going up the rising elevator for the boss arena, head to the right to find this Data Pad on the ground by a dead tree.",
                            "Image": "Kell's Fall data pad 1",
                            "Image_URL": self.image_urls.get("Kell's Fall data pad 1", None)
                        },
                        {
                            "Description": "Before the final boss room after the Trickster, look to the right of the main door for this Data Pad.",
                            "Image": "Kell's Fall data pad 2",
                            "Image_URL": self.image_urls.get("Kell's Fall data pad 2", None)
                        }
                    ]
                }
            ]
        }

        # GUI Components
        self.create_widgets()

    def scrape_image_urls(self):
        """
        Scrape image URLs from the GameRant article.
        Returns a dictionary mapping Data Pad image names to their URLs.
        """
        url = "https://gamerant.com/destiny-2-all-data-pad-locations-week-1-solo-fireteam-pinnacle-ops/"
        image_urls = {}
        try:
            # Fetch the webpage
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all image tags
            images = soup.find_all('img')
            for img in images:
                src = img.get('src', '')
                alt = img.get('alt', '')
                # Check if the image is hosted on GameRant's static server and matches a Data Pad name
                if 'static0.gamerantimages.com' in src:
                    # Normalize the image name for matching
                    for data_pad in [
                        "Skywatch data pad", "The Salt Mines data pad", "Caldera data pad",
                        "The Glassway data pad 1", "The Glassway data pad 2",
                        "The Inverted Spire data pad 1", "The Inverted Spire data pad 2",
                        "Battleground Conduit data pad 1", "Battleground Conduit data pad 2",
                        "Battleground Delve data pad 1", "Battleground Delve data pad 2",
                        "Empire Hunt The Dark Priestess data pad", "Empire Hunt The Technocrat data pad 1",
                        "Empire Hunt The Warrior data pad 1", "Kell's Fall data pad 1", "Kell's Fall data pad 2"
                    ]:
                        # Check if the Data Pad name appears in the alt text or nearby text
                        if data_pad.lower() in alt.lower() or data_pad.lower() in img.find_parent().text.lower():
                            image_urls[data_pad] = src
                            break
        except requests.RequestException as e:
            messagebox.showerror("Error", f"Failed to scrape image URLs: {str(e)}")
        return image_urls

    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Title
        ttk.Label(main_frame, text="Destiny 2: The Edge of Fate - Data Pad Locations", font=("Arial", 16, "bold")).grid(row=0, column=0, columnspan=2, pady=10)

        # Activity Type Dropdown
        ttk.Label(main_frame, text="Select Activity Type:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.activity_var = tk.StringVar()
        activity_dropdown = ttk.Combobox(main_frame, textvariable=self.activity_var, values=list(self.data_pads.keys()), state="readonly")
        activity_dropdown.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5)
        activity_dropdown.bind("<<ComboboxSelected>>", self.update_operation_dropdown)

        # Operation Dropdown
        ttk.Label(main_frame, text="Select Operation:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.operation_var = tk.StringVar()
        self.operation_dropdown = ttk.Combobox(main_frame, textvariable=self.operation_var, state="readonly")
        self.operation_dropdown.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5)
        self.operation_dropdown.bind("<<ComboboxSelected>>", self.update_data_pad_dropdown)

        # Data Pad Dropdown (for operations with multiple Data Pads)
        ttk.Label(main_frame, text="Select Data Pad:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.data_pad_var = tk.StringVar()
        self.data_pad_dropdown = ttk.Combobox(main_frame, textvariable=self.data_pad_var, state="readonly")
        self.data_pad_dropdown.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5)
        self.data_pad_dropdown.bind("<<ComboboxSelected>>", self.display_data_pad)

        # Text Area for Location Description
        self.description_text = tk.Text(main_frame, height=5, width=50, wrap=tk.WORD)
        self.description_text.grid(row=4, column=0, columnspan=2, pady=10)
        self.description_text.config(state="disabled")

        # Image Label
        self.image_label = ttk.Label(main_frame)
        self.image_label.grid(row=5, column=0, columnspan=2, pady=10)

        # Image URL Button
        self.url_button = ttk.Button(main_frame, text="Open Image in Browser", command=self.open_image_url, state="disabled")
        self.url_button.grid(row=6, column=0, columnspan=2, pady=5)

        # Exit Button
        ttk.Button(main_frame, text="Exit", command=self.root.quit).grid(row=7, column=0, columnspan=2, pady=10)

    def update_operation_dropdown(self, event):
        activity = self.activity_var.get()
        if activity:
            if activity in ["Solo Ops", "Empire Hunt"]:
                operations = [op["Op"] for op in self.data_pads[activity]]
                self.operation_dropdown["values"] = operations
                self.data_pad_dropdown["values"] = []
                self.data_pad_dropdown.set("")
                self.description_text.config(state="normal")
                self.description_text.delete(1.0, tk.END)
                self.description_text.config(state="disabled")
                self.image_label.config(image="")
                self.url_button.config(state="disabled")
            else:  # Fireteam Ops, Pinnacle Ops
                operations = [op["Op"] for op in self.data_pads[activity]]
                self.operation_dropdown["values"] = operations
                self.operation_dropdown.set("")
                self.data_pad_dropdown["values"] = []
                self.data_pad_dropdown.set("")
                self.description_text.config(state="normal")
                self.description_text.delete(1.0, tk.END)
                self.description_text.config(state="disabled")
                self.image_label.config(image="")
                self.url_button.config(state="disabled")

    def update_data_pad_dropdown(self, event):
        activity = self.activity_var.get()
        operation = self.operation_var.get()
        if activity and operation:
            if activity in ["Solo Ops", "Empire Hunt"]:
                for op in self.data_pads[activity]:
                    if op["Op"] == operation:
                        self.display_data_pad_info(op["Location"], op["Image_URL"])
                        break
                self.data_pad_dropdown["values"] = []
                self.data_pad_dropdown.set("")
            else:  # Fireteam Ops, Pinnacle Ops
                for op in self.data_pads[activity]:
                    if op["Op"] == operation:
                        data_pads = [f"Data Pad {i+1}" for i in range(len(op["Locations"]))]
                        self.data_pad_dropdown["values"] = data_pads
                        self.data_pad_dropdown.set("")
                        self.description_text.config(state="normal")
                        self.description_text.delete(1.0, tk.END)
                        self.description_text.config(state="disabled")
                        self.image_label.config(image="")
                        self.url_button.config(state="disabled")
                        break

    def display_data_pad(self, event):
        activity = self.activity_var.get()
        operation = self.operation_var.get()
        data_pad = self.data_pad_var.get()
        if activity and operation and data_pad:
            for op in self.data_pads[activity]:
                if op["Op"] == operation:
                    index = int(data_pad.split()[-1]) - 1
                    location = op["Locations"][index]["Description"]
                    image_url = op["Locations"][index]["Image_URL"]
                    self.display_data_pad_info(location, image_url)

    def display_data_pad_info(self, location, image_url):
        # Update description
        self.description_text.config(state="normal")
        self.description_text.delete(1.0, tk.END)
        self.description_text.insert(tk.END, location)
        self.description_text.config(state="disabled")

        # Update image
        self.image_label.config(image="")
        self.current_image_url = image_url
        if image_url:
            try:
                response = requests.get(image_url)
                if response.status_code == 200:
                    img_data = BytesIO(response.content)
                    img = Image.open(img_data)
                    img = img.resize((300, 200), Image.Resampling.LANCZOS)
                    self.photo = ImageTk.PhotoImage(img)
                    self.image_label.config(image=self.photo)
                    self.url_button.config(state="normal")
                else:
                    self.image_label.config(text="Image not found (invalid URL)")
                    self.url_button.config(state="disabled")
            except Exception as e:
                self.image_label.config(text=f"Error loading image: {str(e)}")
                self.url_button.config(state="disabled")
        else:
            self.image_label.config(text="No image available")
            self.url_button.config(state="disabled")

    def open_image_url(self):
        if self.current_image_url:
            webbrowser.open(self.current_image_url)

if __name__ == "__main__":
    root = tk.Tk()
    app = Destiny2DataPadApp(root)
    root.mainloop()