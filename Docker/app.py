import os
import requests
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS support

ANILIST_USERNAME = os.getenv('ANILIST_USERNAME')  # AniList username
XML_USERNAME = os.getenv('XML_USERNAME')  # XML username (can be anything)
anime_offline_db = []

# Load the anime offline database
with open('anime-offline-database.json', 'r') as f:
    anime_offline_db = json.load(f)['data']


def fetch_user_anime_list(anilist_username):
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
        'userName': anilist_username
    }

    url = 'https://graphql.anilist.co'

    response = requests.post(url, json={'query': query, 'variables': variables})
    response.raise_for_status()

    data = response.json()
    if 'errors' in data:
        raise Exception(f'AniList username "{anilist_username}" not found.')

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


def create_mal_xml(anime_list, xml_username):
    root = ET.Element('myanimelist')
    myinfo = ET.SubElement(root, 'myinfo')
    ET.SubElement(myinfo, 'user_id').text = '0'
    ET.SubElement(myinfo, 'user_name').text = xml_username
    ET.SubElement(myinfo, 'user_export_type').text = '1'
    ET.SubElement(myinfo, 'user_total_anime').text = str(len(anime_list))
    ET.SubElement(myinfo, 'user_total_watching').text = str(len([a for a in anime_list if a['status'] == 'CURRENT']))
    ET.SubElement(myinfo, 'user_total_completed').text = str(len([a for a in anime_list if a['status'] == 'COMPLETED']))
    ET.SubElement(myinfo, 'user_total_onhold').text = str(len([a for a in anime_list if a['status'] == 'PAUSED']))
    ET.SubElement(myinfo, 'user_total_dropped').text = str(len([a for a in anime_list if a['status'] == 'DROPPED']))
    ET.SubElement(myinfo, 'user_total_plantowatch').text = str(len([a for a in anime_list if a['status'] == 'PLANNING']))

    for anime in anime_list:
        mal_id = fetch_mal_id(anime['anilist_id']) or anime['anilist_id']
        if mal_id is None:
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
    return pretty_xml_str


@app.route('/convert', methods=['POST'])
def convert():
    data = request.json
    anilist_username = data.get('anilist_username')
    xml_username = data.get('xml_username')

    if not anilist_username or not xml_username:
        return jsonify({'error': 'Missing usernames'}), 400

    try:
        anime_list = fetch_user_anime_list(anilist_username)
        if anime_list:
            xml_content = create_mal_xml(anime_list, xml_username)
            return jsonify({'xml_content': xml_content}), 200
        else:
            return jsonify({'error': 'Error fetching anime list or no anime found'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/cancel', methods=['POST'])
def cancel():
    # This endpoint can be used to handle cancellation logic if needed.
    return jsonify({'message': 'Cancellation not implemented'}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))