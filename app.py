import os
import sys
import json
import base64
import logging
import traceback
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.cloud import pubsub_v1
from Summarizer import TranscriptProcessor
from cloud_storage import CloudStorageManager
import xml.etree.ElementTree as ET
import re
import time

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

@app.route('/youtube_webhook', methods=['POST'])
def youtube_webhook():
    """
    Webhook endpoint for processing YouTube video notifications.
    Supports both XML payload and JSON Pub/Sub messages.
    """
    try:
        # Determine input type and extract video ID
        video_id = None
        
        # Check if it's a Pub/Sub JSON message
        if request.is_json:
            logging.info("Processing JSON Pub/Sub message")
            message_data = request.get_json()
            video_url = message_data.get('videoUrl')
            if video_url:
                video_id = extract_video_id(video_url)
        
        # Check if it's an XML payload
        elif request.data:
            logging.info("Processing XML payload")
            xml_data = request.data
            root = ET.fromstring(xml_data)
            
            # Define potential namespaces
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'yt': 'http://www.youtube.com/xml/feeds/'
            }
            
            # Try multiple ways to extract video ID
            video_id_paths = [
                './/yt:videoId',
                './/atom:id',
                './/id'
            ]
            
            for path in video_id_paths:
                try:
                    video_id_element = root.find(path, namespaces)
                    if video_id_element is not None and video_id_element.text:
                        video_id = extract_id(video_id_element.text)
                        break
                except Exception as path_error:
                    logging.debug(f"Failed to extract ID using path {path}: {path_error}")
        
        # Validate video ID
        if not video_id:
            logging.warning("No video ID could be extracted")
            return jsonify({
                "status": "error",
                "message": "Unable to extract video ID"
            }), 400
        
        # Process the video
        logging.info(f"Processing video with ID: {video_id}")
        processed = process_video(video_id)
        
        if processed:
            return jsonify({
                "status": "success",
                "video_id": video_id,
                "message": "Video processed successfully"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "video_id": video_id,
                "message": "Failed to process video"
            }), 400
    
    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

def listen_for_pubsub_messages(project_id, subscription_id):
    """
    Listen for messages from Google Cloud Pub/Sub and trigger processing
    """
    logging.info(f"Initializing Pub/Sub listener for project: {project_id}")
    logging.info(f"Listening on subscription: {subscription_id}")
    
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(project_id, subscription_id)
    logging.debug(f"Subscription path: {subscription_path}")

    def callback(message):
        try:
            logging.info(f"Received Pub/Sub message: {message.message_id}")
            logging.debug(f"Message data: {message.data}")
            
            # Deserialize the message
            message_data = json.loads(message.data.decode("utf-8"))
            video_url = message_data.get('videoUrl')
            
            logging.info(f"Extracted video URL: {video_url}")
            
            if video_url:
                # Process video URL
                processed = process_video_from_url(video_url)
                
                if processed:
                    logging.info(f"Successfully processed video URL: {video_url}")
                else:
                    logging.warning(f"Failed to process video URL: {video_url}")
            else:
                logging.warning("No video URL found in message")
            
            # Acknowledge the message
            message.ack()
            logging.debug(f"Message {message.message_id} acknowledged")

        except Exception as e:
            logging.error(f"Error processing Pub/Sub message: {e}")
            # Do not ack the message if processing fails
            message.nack()

    # Subscribe and start listening
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    logging.info("Pub/Sub listener started. Waiting for messages...")

    try:
        # Keeps the main thread alive to keep listening
        streaming_pull_future.result(timeout=None)
    except TimeoutError:
        streaming_pull_future.cancel()
        logging.warning("Pub/Sub listener timed out")
    except KeyboardInterrupt:
        streaming_pull_future.cancel()
        logging.info("Pub/Sub listener stopped by user")

def process_video_from_url(video_url):
    """
    Process video given its URL (retrieves ID from URL, extracts transcript, etc.)
    """
    video_id = extract_video_id(video_url)
    if video_id:
        return process_video(video_id)
    return False

def process_video(video_id):
    logging.info(f"Processing video: {video_id}")
    processor = TranscriptProcessor()
    cloud_storage = CloudStorageManager()
    
    transcript = processor.extract_transcript(video_id)
    logging.info(f"Transcript length: {len(transcript)} characters")
    
    summary = processor.generate_summary(transcript)
    logging.info(f"Summary length: {len(summary)} characters")
    
    # Upload summary with a descriptive filename
    filename = f"summaries/{video_id}_summary.txt"
    cloud_storage.upload_summary(
        summary=summary,
        filename=filename
    )
    
    return True

def extract_video_id(url):
    """
    Extracts YouTube video ID from the provided URL
    """
    if not url:
        return None
    return extract_id(url)  # Reuse the extract_id method you already defined

def extract_id(text):
    logging.debug(f"DEBUGGING: Full raw input: {repr(text)}")
    logging.debug(f"DEBUGGING: Full raw input type: {type(text)}")
    logging.debug(f"DEBUGGING: Full raw input length: {len(str(text))}")
    
    # Preprocessing to remove common prefixes and non-ID characters
    text = str(text).strip()
    
    # First, try to extract ID from YouTube-specific URL patterns
    url_patterns = [
        r'v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'embed/([a-zA-Z0-9_-]{11})',
        r'shorts/([a-zA-Z0-9_-]{11})',
        r'watch\?v=([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in url_patterns:
        match = re.search(pattern, text)
        if match:
            extracted_id = match.group(1)
            logging.debug(f"DEBUGGING: Extracted ID from URL pattern: {extracted_id}")
            return extracted_id
    
    # If no URL pattern matches, look for an 11-character sequence
    # Ensure it contains a mix of characters typical of YouTube IDs
    match = re.search(r'([a-zA-Z0-9_-]{11})', text)
    if match:
        extracted_id = match.group(1)
        logging.debug(f"DEBUGGING: Extracted ID: {extracted_id}")
        return extracted_id
    
    logging.debug("DEBUGGING: No valid YouTube ID could be extracted")
    return None

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
    # Start the Pub/Sub listener (run in the background or separate thread)
    project_id = 'careful-hangar-446706-n7'
    subscription_id = 'youtube-upload-sub'
    listen_for_pubsub_messages(project_id, subscription_id)
    
    # Start the Flask application
    logging.info("Starting YouTube Pub/Sub webhook server")
    app.run(host='0.0.0.0', port=5000, debug=True)
