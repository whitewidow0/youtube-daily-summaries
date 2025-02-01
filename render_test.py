import os
import sys
import json
import logging
import requests
import traceback
import time
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(os.path.expanduser('~/Desktop/.env'))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('webhook_test_debug.log', mode='w'),
        logging.StreamHandler()
    ]
)

# Render deployment URL
render_url = 'https://youtube-daily-summaries.onrender.com/youtube_webhook'

# Video details from URL
video_url = 'https://www.youtube.com/watch?v=PZ5aFq2hPUg'

def get_youtube_api_key():
    """
    Retrieve YouTube API key from multiple sources
    """
    api_key = os.getenv('YOUTUBE_API_KEY')
    
    if not api_key:
        possible_key_files = [
            r'c:\Users\Boris Lap\Downloads\careful-hangar-446706-n7-ea19c1b519da.json',
            r'c:\Users\Boris Lap\Desktop\YoutubeDailySummaries\youtube_api_key.json'
        ]
        
        for key_file in possible_key_files:
            try:
                with open(key_file, 'r') as f:
                    key_data = json.load(f)
                    api_key = key_data.get('youtube_api_key') or key_data.get('API_KEY')
                    if api_key:
                        break
            except Exception:
                continue
    
    return api_key

def extract_video_details(video_url):
    """
    Extract video details using YouTube Data API
    """
    youtube_api_key = get_youtube_api_key()
    youtube = build('youtube', 'v3', developerKey=youtube_api_key)
    
    # Extract video ID from URL
    video_id = video_url.split('v=')[1].split('&')[0]
    
    # Fetch video details
    request = youtube.videos().list(
        part='snippet',
        id=video_id
    )
    response = request.execute()
    
    if not response['items']:
        raise ValueError(f"No video found with ID: {video_id}")
    
    video = response['items'][0]
    
    return {
        'video_id': video_id,
        'title': video['snippet']['title'],
        'published_at': video['snippet']['publishedAt'],
        'channel_title': video['snippet']['channelTitle'],
        'channel_id': video['snippet']['channelId']
    }

def send_webhook_request(render_url, video_details):
    """
    Send a simulated YouTube PubSub webhook request with comprehensive logging
    
    Args:
        render_url (str): Webhook endpoint URL
        video_details (dict): Video details for payload
    
    Returns:
        dict: Response from the webhook endpoint
    """
    print("DEBUGGING: Creating Atom XML payload")
    feed = ET.Element('feed', {
        'xmlns': 'http://www.w3.org/2005/Atom',
        'xmlns:yt': 'http://www.w3.org/2005/Atom'
    })
    
    # Create entry element
    entry = ET.SubElement(feed, 'entry')
    
    # Video ID
    id_elem = ET.SubElement(entry, 'id')
    id_elem.text = video_details['video_id']
    
    # Title
    title_elem = ET.SubElement(entry, 'title')
    title_elem.text = video_details['title']
    
    # Link
    link_elem = ET.SubElement(entry, 'link', {
        'href': f"https://www.youtube.com/watch?v={video_details['video_id']}",
        'rel': 'alternate',
        'type': 'text/html'
    })
    
    # Published timestamp
    published_elem = ET.SubElement(entry, 'published')
    published_elem.text = video_details['published_at']
    
    # Updated timestamp
    updated_elem = ET.SubElement(entry, 'updated')
    updated_elem.text = datetime.now(timezone.utc).isoformat()
    
    # Author information
    author_elem = ET.SubElement(entry, 'author')
    author_name = ET.SubElement(author_elem, 'name')
    author_name.text = video_details['channel_title']
    author_uri = ET.SubElement(author_elem, 'uri')
    author_uri.text = f"https://www.youtube.com/channel/{video_details['channel_id']}"
    
    # Convert to string for easier debugging
    rough_string = ET.tostring(feed, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    xml_payload = reparsed.toprettyxml(indent="  ")
    
    print("DEBUGGING: Preparing webhook request")
    headers = {
        'Content-Type': 'application/atom+xml',
        'X-Webhook-Token': os.getenv('RENDER_WEBHOOK_SECRET', 'test_secret')
    }
    
    print(f"DEBUGGING: Webhook URL: {render_url}")
    print(f"DEBUGGING: Video ID in Payload: {video_details['video_id']}")
    print(f"DEBUGGING: Video Title: {video_details['title']}")
    print(f"DEBUGGING: Published At: {video_details['published_at']}")
    
    try:
        print("DEBUGGING: Sending webhook request")
        response = requests.post(render_url, data=xml_payload, headers=headers)
        
        print("DEBUGGING: Webhook request sent")
        print(f"DEBUGGING: Response Status Code: {response.status_code}")
        print(f"DEBUGGING: Response Headers: {dict(response.headers)}")
        print(f"DEBUGGING: Response Text: {response.text}")
        
        try:
            response_json = response.json()
            print("DEBUGGING: Response JSON:")
            print(json.dumps(response_json, indent=2))
            
            # Add detailed logging for processing status
            if response_json.get('status') == 'success':
                processed_videos = response_json.get('processedVideos', [])
                for video in processed_videos:
                    print(f"DEBUGGING: Video Processing Status - Video ID: {video.get('video_id')}, Status: {video.get('status')}")
            else:
                print("DEBUGGING: Webhook processing failed")
        
        except Exception as json_error:
            print(f"DEBUGGING: Failed to parse response as JSON - {json_error}")
        
        return response
    
    except Exception as e:
        print(f"DEBUGGING: Webhook request error - {e}")
        import traceback
        traceback.print_exc()
        return None

# Main script execution
print("DEBUGGING: Starting render test script")
print(f"Current working directory: {os.getcwd()}")
print(f"Python path: {sys.path}")

try:
    # Extract video details
    video_details = extract_video_details(video_url)
    
    # Send webhook request
    response = send_webhook_request(render_url, video_details)

except Exception as e:
    print(f"DEBUGGING: Unexpected Error: {e}")
    import traceback
    traceback.print_exc()
