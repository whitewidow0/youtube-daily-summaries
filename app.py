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
import xmltodict

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

@app.route('/webhook', methods=['GET', 'POST'])
def youtube_webhook():
    """
    Webhook endpoint for WebSub notifications and verification.
    Strictly follows WebSub specification for verification.
    """
    # WebSub Verification Challenge (GET request)
    if request.method == 'GET':
        # Extract WebSub verification parameters
        hub_mode = request.args.get('hub.mode')
        hub_topic = request.args.get('hub.topic')
        hub_challenge = request.args.get('hub.challenge')
        hub_lease_seconds = request.args.get('hub.lease_seconds')

        # Logging for debugging
        logging.info(f"WebSub Verification Request:")
        logging.info(f"Mode: {hub_mode}")
        logging.info(f"Topic: {hub_topic}")
        logging.info(f"Challenge: {hub_challenge}")
        logging.info(f"Lease Seconds: {hub_lease_seconds}")

        # Strict validation as per WebSub spec
        if (hub_mode in ['subscribe', 'unsubscribe'] and 
            hub_topic and 
            hub_challenge):
            # Respond exactly as specified in the spec
            logging.info("WebSub verification challenge accepted")
            return hub_challenge, 200
        
        # If validation fails, return 404 as per spec
        logging.error("Invalid WebSub verification request")
        return 'Verification Failed', 404

    # WebSub Notification Handling (POST request)
    elif request.method == 'POST':
        try:
            # Log raw request details for debugging
            logging.info(f"Notification Headers: {dict(request.headers)}")
            logging.info(f"Notification Content Type: {request.content_type}")
            
            # Get raw request body
            raw_body = request.get_data()
            logging.info(f"Raw Notification Body: {raw_body.decode('utf-8', errors='ignore')}")
            
            # Parse XML notification
            feed = xmltodict.parse(raw_body)
            logging.info(f"Parsed Feed: {feed}")
            
            # Extract video ID and process
            if 'feed' in feed and 'entry' in feed['feed']:
                entry = feed['feed']['entry']
                video_id = entry.get('yt:videoId', '')
                
                if video_id:
                    # Process the video
                    process_video(video_id)
                    return 'Notification Processed', 200
                else:
                    logging.warning("No video ID found in notification")
                    return 'No Video ID', 400

        except Exception as e:
            logging.error(f"Webhook Processing Error: {e}")
            logging.error(traceback.format_exc())
            return 'Processing Error', 500

@app.route('/youtube_webhook', methods=['GET', 'POST'])
def youtube_webhook_legacy():
    """
    Webhook endpoint for WebSub notifications and verification.
    Supports verification challenge and video upload notifications.
    """
    try:
        # GET: Verification Challenge
        if request.method == 'GET':
            hub_mode = request.args.get('hub.mode')
            hub_topic = request.args.get('hub.topic')
            hub_challenge = request.args.get('hub.challenge')
            hub_lease_seconds = request.args.get('hub.lease_seconds')

            logging.info(f"WebSub Verification Request:")
            logging.info(f"Mode: {hub_mode}")
            logging.info(f"Topic: {hub_topic}")
            logging.info(f"Challenge: {hub_challenge}")
            logging.info(f"Lease Seconds: {hub_lease_seconds}")

            # Basic validation of verification parameters
            if hub_mode == 'subscribe' and hub_challenge:
                logging.info("WebSub subscription verification challenge received")
                return hub_challenge, 200
            
            logging.error("Invalid WebSub verification request")
            return 'Verification Failed', 400

        # POST: Notification Processing
        if request.method == 'POST':
            # Log the entire raw message for debugging
            raw_data = request.get_data()
            logging.debug(f"Received raw WebSub notification: {raw_data.decode('utf-8')}")

            # Skip processing if message is empty
            if not raw_data:
                logging.info("Received empty WebSub notification")
                return '', 200

            # Parse XML notification
            try:
                root = ET.fromstring(raw_data)
                namespaces = {
                    'atom': 'http://www.w3.org/2005/Atom',
                    'yt': 'http://www.youtube.com/xml/feeds/videos'
                }
                
                # Extract video ID
                video_id_element = root.find('.//yt:videoId', namespaces)
                if video_id_element is not None and video_id_element.text:
                    video_id = video_id_element.text
                    logging.info(f"Extracted video ID from WebSub notification: {video_id}")
                    
                    # Process the video
                    processed = process_video(video_id)
                    
                    if processed:
                        logging.info(f"Successfully processed video from WebSub: {video_id}")
                        return '', 200
                    else:
                        logging.warning(f"Failed to process video from WebSub: {video_id}")
                        return '', 500
                else:
                    logging.warning("No video ID found in WebSub notification")
                    return '', 200

            except ET.ParseError as parse_error:
                logging.error(f"XML Parsing Error in WebSub notification: {parse_error}")
                return '', 400
            except Exception as e:
                logging.error(f"Error processing WebSub notification: {e}")
                logging.error(traceback.format_exc())
                return '', 500

    except Exception as e:
        logging.error(f"Unexpected error in YouTube WebSub webhook: {e}")
        logging.error(traceback.format_exc())
        return '', 500

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
