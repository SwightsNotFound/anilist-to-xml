import os
import requests
import xml.etree.ElementTree as ET
import time
from xml.dom import minidom
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import json

ANILIST_USERNAME = os.getenv('ANILIST_USERNAME')  # AniList username
XML_USERNAME = os.getenv('XML_USERNAME')  # XML username (can be anything)
RATE_LIMIT_DELAY = 1000  # Delay in milliseconds between requests to avoid rate limiting

cancel_event = threading.Event()

# Function to download the anime-offline-database.json file
def download_anime_offline_database():
    url = 'https://raw.githubusercontent.com/manami-project/anime-offline-database/master/anime-offline-database.json'
    response = requests.get(url)
    response.raise_for_status()
    with open('anime-offline-database.json', 'wb') as f:
        f.write(response.content)

# Load the anime offline database
def load_anime_offline_database():
    global anime_offline_db
    with open('anime-offline-database.json', 'r') as f:
        anime_offline_db = json.load(f)['data']

# Ensure the anime offline database is downloaded and loaded
download_anime_offline_database()
load_anime_offline_database()

def fetch_user_anime_list():
    if cancel_event.is_set():
        return None

    query = '''
        query ($userName: String) {
            MediaListCollection(userName: $userName, type: ANIME) {
                lists {
                    name
                    entries {
                        media {
                            id
                            title {
                                english
                                romaji
                            }
                            episodes
                            format
                        }
                        score
                        progress
                        startedAt {
                            year
                            month
                            day
                        }
                        completedAt {
                            year
                            month
                            day
                        }
                        status
                    }
                }
            }
        }
    '''

    variables = {
        'userName': ANILIST_USERNAME
    }

    url = 'https://graphql.anilist.co'

    try:
        response = requests.post(url, json={'query': query, 'variables': variables})
        response.raise_for_status()

        data = response.json()
        if 'errors' in data:
            raise Exception(f'AniList username "{ANILIST_USERNAME}" not found.')

        lists = data['data']['MediaListCollection']['lists']
        return [
            {
                'anilist_id': entry['media']['id'],
                'title': entry['media']['title']['english'] or entry['media']['title']['romaji'],
                'episodes': entry['media']['episodes'],
                'format': entry['media']['format'],
                'score': entry['score'],
                'progress': entry['progress'],
                'startedAt': f"{entry['startedAt']['year'] or '0000'}-{entry['startedAt']['month'] or '00'}-{entry['startedAt']['day'] or '00'}",
                'completedAt': f"{entry['completedAt']['year'] or '0000'}-{entry['completedAt']['month'] or '00'}-{entry['completedAt']['day'] or '00'}",
                'status': entry['status']
            }
            for list_ in lists for entry in list_['entries']
        ]
    except Exception as e:
        if not cancel_event.is_set():
            print(f'Error fetching user anime list: {e}')
        return None


def fetch_mal_id(anilist_id):
    for anime in anime_offline_db:
        for source in anime['sources']:
            if f'https://anilist.co/anime/{anilist_id}' in source:
                for mal_source in anime['sources']:
                    if 'https://myanimelist.net/anime/' in mal_source:
                        return mal_source.split('/')[-1]
    return None


def map_format_to_mal_type(format_):
    return {
        'TV': 'TV',
        'MOVIE': 'Movie',
        'OVA': 'OVA',
        'ONA': 'ONA',
        'SPECIAL': 'Special',
        'MUSIC': 'Music'
    }.get(format_, 'Unknown')


def map_status_to_mal_status(status):
    return {
        'CURRENT': 'Watching',
        'COMPLETED': 'Completed',
        'PAUSED': 'On-Hold',
        'DROPPED': 'Dropped',
        'PLANNING': 'Plan to Watch'
    }.get(status, 'Unknown')


def create_mal_xml(anime_list, file_name):
    if cancel_event.is_set():
        return

    root = ET.Element('myanimelist')
    myinfo = ET.SubElement(root, 'myinfo')
    ET.SubElement(myinfo, 'user_id').text = '0'
    ET.SubElement(myinfo, 'user_name').text = XML_USERNAME
    ET.SubElement(myinfo, 'user_export_type').text = '1'
    ET.SubElement(myinfo, 'user_total_anime').text = str(len(anime_list))
    ET.SubElement(myinfo, 'user_total_watching').text = str(len([a for a in anime_list if a['status'] == 'CURRENT']))
    ET.SubElement(myinfo, 'user_total_completed').text = str(len([a for a in anime_list if a['status'] == 'COMPLETED']))
    ET.SubElement(myinfo, 'user_total_onhold').text = str(len([a for a in anime_list if a['status'] == 'PAUSED']))
    ET.SubElement(myinfo, 'user_total_dropped').text = str(len([a for a in anime_list if a['status'] == 'DROPPED']))
    ET.SubElement(myinfo, 'user_total_plantowatch').text = str(len([a for a in anime_list if a['status'] == 'PLANNING']))

    for anime in anime_list:
        if cancel_event.is_set():
            return
        mal_id = fetch_mal_id(anime['anilist_id']) or anime['anilist_id']
        if mal_id is None:
            print(f'Unable to fetch MAL ID for {anime["title"]}, skipping.')
            continue
        anime_elem = ET.SubElement(root, 'anime')
        ET.SubElement(anime_elem, 'series_animedb_id').text = str(mal_id)
        ET.SubElement(anime_elem, 'series_title').text = anime['title']
        ET.SubElement(anime_elem, 'series_type').text = map_format_to_mal_type(anime['format'])
        ET.SubElement(anime_elem, 'series_episodes').text = str(anime['episodes'])
        ET.SubElement(anime_elem, 'my_id').text = '0'
        ET.SubElement(anime_elem, 'my_watched_episodes').text = str(anime['progress'])
        ET.SubElement(anime_elem, 'my_start_date').text = anime['startedAt']
        ET.SubElement(anime_elem, 'my_finish_date').text = anime['completedAt']
        ET.SubElement(anime_elem, 'my_rated').text = ''
        ET.SubElement(anime_elem, 'my_score').text = str(anime['score'])
        ET.SubElement(anime_elem, 'my_storage').text = ''
        ET.SubElement(anime_elem, 'my_storage_value').text = '0.00'
        ET.SubElement(anime_elem, 'my_status').text = map_status_to_mal_status(anime['status'])
        ET.SubElement(anime_elem, 'my_comments').text = ''
        ET.SubElement(anime_elem, 'my_times_watched').text = '0'
        ET.SubElement(anime_elem, 'my_rewatch_value').text = ''
        ET.SubElement(anime_elem, 'my_priority').text = 'LOW'
        ET.SubElement(anime_elem, 'my_tags').text = ''
        ET.SubElement(anime_elem, 'my_rewatching').text = '0'
        ET.SubElement(anime_elem, 'my_rewatching_ep').text = '0'
        ET.SubElement(anime_elem, 'my_discuss').text = '1'
        ET.SubElement(anime_elem, 'my_sns').text = 'default'
        ET.SubElement(anime_elem, 'update_on_import').text = '1'

    xml_str = ET.tostring(root, encoding='utf-8')
    pretty_xml_str = minidom.parseString(xml_str).toprettyxml(indent="  ")
    with open(file_name, 'w', encoding='utf-8') as f:
        f.write(pretty_xml_str)

    print('MAL XML file created successfully.')


class AnimeListConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AniList to XML Converter")
        self.root.geometry("600x400")
        self.root.configure(bg='#f0f0f0')

        style = ttk.Style()
        style.configure("TLabel", font=("Helvetica", 12), background='#f0f0f0')
        style.configure("TButton", font=("Helvetica", 12), padding=10)
        style.configure("TEntry", font=("Helvetica", 12), padding=10)

        main_frame = ttk.Frame(root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        ttk.Label(main_frame, text="AniList Username:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.anilist_username_entry = ttk.Entry(main_frame, width=30)
        self.anilist_username_entry.grid(row=0, column=1, pady=5)

        ttk.Label(main_frame, text="XML Username (This can be anything):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.xml_username_entry = ttk.Entry(main_frame, width=30)
        self.xml_username_entry.grid(row=1, column=1, pady=5)

        self.output_text = tk.Text(main_frame, wrap=tk.WORD, height=10, width=80, state=tk.DISABLED, bg='#e0e0e0', font=("Helvetica", 10))
        self.output_text.grid(row=3, column=0, columnspan=2, pady=10)
        self.output_text.tag_config("error", foreground="red")

        self.convert_button = ttk.Button(main_frame, text="Convert", command=self.on_convert_button_click)
        self.convert_button.grid(row=4, column=0, pady=10)

        self.cancel_button = ttk.Button(main_frame, text="Cancel", command=self.on_cancel_button_click)
        self.cancel_button.grid(row=4, column=1, pady=10)

        self.process = None
        self.timer_running = False
        self.start_time = None

        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)

    def on_convert_button_click(self):
        anilist_username = self.anilist_username_entry.get().strip()
        xml_username = self.xml_username_entry.get().strip()

        if not anilist_username or not xml_username:
            messagebox.showwarning("Input Error", "Please enter both usernames.")
            return

        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, "This will take a few minutes if you have a long list due to Jikan API rate limiting. Please wait...\n")
        self.output_text.insert(tk.END, "00:00\n")
        self.output_text.config(state=tk.DISABLED)

        cancel_event.clear()
        self.start_conversion_thread(anilist_username, xml_username)

    def on_cancel_button_click(self):
        cancel_event.set()
        if self.process and self.process.is_alive():
            self.timer_running = False
            self.process.join()
            self.output_text.config(state=tk.NORMAL)
            self.output_text.insert(tk.END, "\nProcess cancelled.\n")
            self.output_text.config(state=tk.DISABLED)
            print("Process cancelled.")

    def on_exit(self):
        self.on_cancel_button_click()
        self.root.destroy()

    def run_conversion(self, anilist_username, xml_username):
        try:
            global ANILIST_USERNAME, XML_USERNAME
            ANILIST_USERNAME = anilist_username
            XML_USERNAME = xml_username
            self.start_timer()
            anime_list = fetch_user_anime_list()
            if anime_list:
                create_mal_xml(anime_list, 'myanimelist.xml')
            self.stop_timer()
            if not cancel_event.is_set():
                self.output_text.config(state=tk.NORMAL)
                self.output_text.insert(tk.END, "\nMAL XML file created successfully.\n")
                self.output_text.config(state=tk.DISABLED)
                messagebox.showinfo("Success", "MAL XML file created successfully.")
        except Exception as e:
            self.stop_timer()
            if not cancel_event.is_set():
                self.output_text.config(state=tk.NORMAL)
                self.output_text.insert(tk.END, f"\nAn error occurred: {str(e)}\n", "error")
                self.output_text.config(state=tk.DISABLED)
                self.output_text.see(tk.END)
                messagebox.showerror("Error", f"An error occurred: {str(e)}")

    def start_conversion_thread(self, anilist_username, xml_username):
        self.process = threading.Thread(target=self.run_conversion, args=(anilist_username, xml_username))
        self.process.start()

    def start_timer(self):
        self.timer_running = True
        self.start_time = time.time()
        threading.Thread(target=self.update_timer).start()

    def stop_timer(self):
        self.timer_running = False

    def update_timer(self):
        while self.timer_running:
            elapsed_time = time.time() - self.start_time
            minutes, seconds = divmod(elapsed_time, 60)
            timer_text = f"{int(minutes):02}:{int(seconds):02}"
            self.output_text.config(state=tk.NORMAL)
            self.output_text.delete("end-2l", "end-1l")
            self.output_text.insert(tk.END, f"{timer_text}\n")
            self.output_text.config(state=tk.DISABLED)
            time.sleep(1)


def main():
    root = tk.Tk()
    app = AnimeListConverterApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()