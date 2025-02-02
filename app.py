import os
import sys
import json
import base64
import logging
import traceback
import time
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.cloud import pubsub_v1
from Summarizer import TranscriptProcessor
from cloud_storage import CloudStorageManager
import xml.etree.ElementTree as ET
import re
import threading

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Log all messages
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[logging.FileHandler('C:\\Users\\Boris Lap\\youtube_webhook.log'), logging.StreamHandler(sys.stdout)]
)

# Initialize summarizer with Gemini API key and YouTube API key from environment
gemini_api_key = os.getenv('GEMINI_API_KEY')
summarizer = TranscriptProcessor(api_key=gemini_api_key)

# Initialize cloud storage manager
cloud_storage = CloudStorageManager()

app = Flask(__name__)

def verify_webhook_token(token):
    """Verify the webhook token from environment variables"""
    expected_token = os.getenv('WEBHOOK_SECRET')
    return token == expected_token

@app.route('/youtube_webhook', methods=['POST'])
@app.route('/webhook', methods=['POST'])
def youtube_webhook():
    """
    Webhook endpoint for processing YouTube video notifications.
    Supports both XML payload and JSON Pub/Sub messages.
    """
    try:
        # Log the entire raw message for debugging
        raw_data = request.get_data()
        logging.debug(f"Received raw webhook data: {raw_data}")

        # Skip processing if message is empty
        if not raw_data:
            logging.info("Received empty webhook message")
            return '', 200

        video_id = None

        # Check if it's a Pub/Sub JSON message
        if request.is_json:
            logging.info("Processing JSON Pub/Sub message")
            message_data = request.get_json()
            
            # Log the full message data for debugging
            logging.debug(f"Full JSON message: {message_data}")
            
            video_url = message_data.get('videoUrl')
            if video_url:
                video_id = extract_video_id(video_url)
                logging.info(f"Extracted video URL: {video_url}")

        # Check if it's an XML payload
        elif raw_data:
            logging.info("Processing XML payload")
            xml_data = raw_data
            root = ET.fromstring(xml_data)
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'yt': 'http://www.youtube.com/xml/feeds/'
            }
            video_id_paths = [
                './/yt:videoId',
                './/atom:id',
                './/id'
            ]
            for path in video_id_paths:
                video_id_element = root.find(path, namespaces)
                if video_id_element is not None and video_id_element.text:
                    video_id = extract_id(video_id_element.text)
                    break

        # Skip processing if no video ID could be extracted
        if not video_id:
            logging.warning("No video ID could be extracted from the message")
            return '', 200

        logging.info(f"Processing video with ID: {video_id}")
        processed = process_video(video_id)

        if processed:
            return jsonify({"status": "success", "video_id": video_id, "message": "Video processed successfully"}), 200
        else:
            logging.warning(f"Failed to process video with ID: {video_id}")
            return jsonify({"status": "error", "video_id": video_id, "message": "Failed to process video"}), 400

    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        logging.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    start_time = time.time()
    
    try:
        # Log request metadata
        logging.info(f"Webhook request method: {request.method}")
        logging.info(f"Client IP: {request.remote_addr}")
        
        # Get and log the raw data
        data = request.get_json()
        logging.info(f"Received raw Pub/Sub message: {data}")

        # Extract video ID
        video_id = data.get("videoId")
        if not video_id:
            logging.warning("No video ID could be extracted from the message")
            return "No video ID", 400

        # Log processing attempt
        logging.info(f"Attempting to process video with ID: {video_id}")

        # Process the video
        processed = process_video(video_id)
        
        # Log processing result
        if processed:
            processing_time = time.time() - start_time
            logging.info(json.dumps({
                "event": "video_processed_successfully",
                "video_id": video_id,
                "processing_time": f"{processing_time:.2f} seconds"
            }))
            return "Success", 200
        else:
            logging.warning(f"Failed to process video with ID: {video_id}")
            return jsonify({"status": "error", "video_id": video_id, "message": "Failed to process video"}), 400

    except Exception as e:
        # Detailed error logging without blocking
        logging.error(f"Error processing webhook", extra={
            "error_type": type(e).__name__,
            "error_details": str(e)
        })
        return "Error", 500

def listen_for_pubsub_messages(project_id, subscription_id):
    """Listen for messages from Google Cloud Pub/Sub and trigger processing"""
    logging.info(f"Initializing Pub/Sub listener for project: {project_id}")
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(project_id, subscription_id)
    
    def callback(message):
        try:
            # Log the raw message data
            raw_data = message.data.decode("utf-8")
            logging.info(f"Received Pub/Sub message: {message.message_id}")
            logging.debug(f"Raw message data: {raw_data}")
            
            # You can also log the attributes if needed
            logging.debug(f"Message attributes: {message.attributes}")
            
            # Deserialize the message to inspect the structure
            message_data = json.loads(raw_data)
            logging.info(f"Parsed message data: {message_data}")
            
            # Now you can see exactly how the data is structured
            video_url = message_data.get('videoUrl')
            logging.info(f"Extracted video URL: {video_url}")
            
            if video_url:
                processed = process_video_from_url(video_url)
                if processed:
                    logging.info(f"Successfully processed video URL: {video_url}")
                else:
                    logging.warning(f"Failed to process video URL: {video_url}")
            else:
                logging.warning("No video URL found in message")
            
            # Acknowledge the message
            message.ack()
        except Exception as e:
            logging.error(f"Error processing Pub/Sub message: {e}")
            # Do not ack the message if processing fails
            message.nack()

    subscriber.subscribe(subscription_path, callback=callback)
    logging.info("Pub/Sub listener started. Waiting for messages...")

    try:
        # Keeps the main thread alive to keep listening
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logging.info("Pub/Sub listener stopped by user")

def process_video_from_url(video_url):
    """Process video given its URL (retrieves ID from URL, extracts transcript, etc.)"""
    video_id = extract_video_id(video_url)
    if video_id:
        return process_video(video_id)
    return False

def process_video(video_id):
    """Process video: extract transcript, generate summary, upload summary"""
    logging.info(f"Processing video: {video_id}")
    transcript = summarizer.extract_transcript(video_id)
    logging.info(f"Transcript length: {len(transcript)} characters")
    
    summary = summarizer.generate_summary(transcript)
    logging.info(f"Summary length: {len(summary)} characters")
    
    filename = f"summaries/{video_id}_summary.txt"
    cloud_storage.upload_summary(summary=summary, filename=filename)
    
    return True

def extract_video_id(url):
    """Extracts YouTube video ID from the provided URL"""
    if not url:
        return None
    return extract_id(url)

def extract_id(text):
    """Extract video ID from various YouTube URL formats"""
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
            return match.group(1)
    
    match = re.search(r'([a-zA-Z0-9_-]{11})', text)
    if match:
        return match.group(1)

    return None

@app.route('/', methods=['GET'])
def health_check():
    """Health check for the Flask application"""
    return jsonify({"status": "healthy", "message": "YouTube Daily Summaries API is running"}), 200

@app.errorhandler(Exception)
def handle_exception(e):
    """Global error handler"""
    logging.error(f"Unhandled exception: {e}")
    logging.error(traceback.format_exc())
    return jsonify({"status": "error", "message": "An unexpected error occurred"}), 500

if __name__ == '__main__':
    # Start the Pub/Sub listener in a separate thread
    project_id = 'careful-hangar-446706-n7'
    subscription_id = 'youtube-upload-sub'
    
    pubsub_thread = threading.Thread(target=listen_for_pubsub_messages, args=(project_id, subscription_id))
    pubsub_thread.daemon = True
    pubsub_thread.start()

    # Start the Flask application
    logging.info("Starting YouTube Pub/Sub webhook server")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
