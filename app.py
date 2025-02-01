import os
import sys
import json
import base64
import logging
import traceback
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from Summarizer import TranscriptProcessor
from cloud_storage import CloudStorageManager
import xml.etree.ElementTree as ET

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('youtube_webhook.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Initialize summarizer with Gemini API key and YouTube API key from environment
gemini_api_key = os.getenv('GEMINI_API_KEY')
summarizer = TranscriptProcessor(api_key=gemini_api_key)

# Initialize cloud storage manager
cloud_storage = CloudStorageManager()

app = Flask(__name__)

def verify_webhook_token(token):
    """
    Verify the webhook token from environment variables
    
    Args:
        token (str): Token to verify
    
    Returns:
        bool: Whether token is valid
    """
    expected_token = os.getenv('WEBHOOK_SECRET')
    return token == expected_token

@app.route('/youtube_webhook', methods=['GET', 'POST'])
def youtube_webhook():
    if request.method == 'POST':
        webhook_token = request.headers.get('X-Render-Webhook-Secret')
        if not verify_webhook_token(webhook_token):
            return jsonify({"status": "error", "message": "Unauthorized"}), 403

        try:
            # Get raw XML data
            xml_data = request.get_data(as_text=True)
            
            # Parse Atom XML
            root = ET.fromstring(xml_data)
            
            # Namespace for Atom XML
            namespace = {'atom': 'http://www.w3.org/2005/Atom'}
            
            # Extract entries
            entries = root.findall('.//atom:entry', namespace)
            
            processed_videos = []
            for entry in entries:
                # Extract video ID from <id> tag
                video_id_elem = entry.find('atom:id', namespace)
                video_id = video_id_elem.text if video_id_elem is not None else None
                
                # Remove 'yt:video:' prefix if present
                original_video_id = video_id
                if video_id and video_id.startswith('yt:video:'):
                    video_id = video_id.replace('yt:video:', '', 1)
                
                logging.info(f"Original Video ID: {original_video_id}")
                logging.info(f"Cleaned Video ID: {video_id}")
                
                # Validate cleaned video ID
                if not video_id:
                    logging.warning("Skipping entry: No valid video ID found")
                    continue
                
                # Extract video title
                title_elem = entry.find('atom:title', namespace)
                video_title = title_elem.text if title_elem is not None else 'Unknown Title'
                
                # Extract video link
                link_elem = entry.find('atom:link[@rel="alternate"]', namespace)
                video_url = link_elem.get('href') if link_elem is not None else None
                
                # Extract publication timestamp
                published_elem = entry.find('atom:published', namespace)
                published_at = published_elem.text if published_elem is not None else None
                
                # Log extracted information
                logging.info(f"Extracted Video - ID: {video_id}, Title: {video_title}")
                
                # Process the video
                try:
                    # Attempt to get transcript
                    transcript = summarizer.extract_transcript(video_id)
                    logging.info(f"Transcript length: {len(transcript) if transcript else 0} characters")
                    
                    if not transcript:
                        logging.warning(f"No transcript found for video {video_id}")
                        continue
                    
                    # Generate summary
                    summary = summarizer.generate_summary(transcript)
                    
                    # Fetch channel name using YouTube API
                    youtube = build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))
                    video_response = youtube.videos().list(
                        part='snippet',
                        id=video_id
                    ).execute()
                    
                    if video_response['items']:
                        channel_title = video_response['items'][0]['snippet']['channelTitle']
                        
                        # Sanitize channel title for filename
                        channel_title = "".join(x for x in channel_title if x.isalnum() or x in "._- ")
                        
                        # Upload summary to cloud storage with channel name
                        cloud_storage.upload_text(
                            summary, 
                            f"summaries/{channel_title}_{video_title}_summary.txt"
                        )
                        
                        processed_videos.append({
                            'videoId': video_id,
                            'title': video_title,
                            'channelTitle': channel_title,
                            'url': video_url,
                            'publishedAt': published_at,
                            'summaryGenerated': summary is not None,
                            'summarySaved': True
                        })
                        logging.info(f"Successfully processed video: {video_id}")
                    else:
                        logging.warning(f"Could not fetch channel name for video {video_id}")
                
                except Exception as process_error:
                    logging.error(f"Error processing video {video_id}: {process_error}")
                    logging.error(traceback.format_exc())
            
            # Return response
            return jsonify({
                "status": "success", 
                "message": f"Processed {len(processed_videos)} videos",
                "processedVideos": processed_videos
            }), 200
        
        except ET.ParseError:
            logging.error("Invalid XML in webhook payload")
            return jsonify({"status": "error", "message": "Invalid XML payload"}), 400
        
        except Exception as error:
            logging.error(f"Unexpected webhook error: {error}")
            logging.error(traceback.format_exc())
            return jsonify({
                "status": "error",
                "message": "Unexpected error processing webhook"
            }), 500

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "message": "YouTube Daily Summaries API is running"
    }), 200

@app.errorhandler(Exception)
def handle_exception(e):
    """Global error handler"""
    logging.error(f"Unhandled exception: {e}")
    logging.error(traceback.format_exc())
    return jsonify({
        "status": "error",
        "message": "An unexpected error occurred"
    }), 500

if __name__ == '__main__':
    logging.info("Starting YouTube Pub/Sub webhook server")
    app.run(host='0.0.0.0', port=5000, debug=True)
