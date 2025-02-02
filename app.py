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

@app.route('/youtube_webhook', methods=['POST'])
def youtube_webhook():
    """
    Webhook endpoint for processing YouTube video notifications with extensive debugging
    """
    print("DEBUGGING WEBHOOK: Received webhook request")
    print(f"DEBUGGING WEBHOOK: Request method: {request.method}")
    print(f"DEBUGGING WEBHOOK: Request content type: {request.content_type}")
    
    try:
        # Log raw request data for debugging
        raw_data = request.get_data(as_text=True)
        print(f"DEBUGGING WEBHOOK: Raw request data:\n{raw_data}")
        
        # Verify webhook token if needed
        token = request.headers.get('X-Render-Webhook-Secret')
        print(f"DEBUGGING WEBHOOK: Received token: {token}")
        
        # Attempt to parse XML
        try:
            # Define potential namespaces
            NAMESPACES = {
                'atom': 'http://www.w3.org/2005/Atom',
                'yt': 'http://www.w3.org/2005/Atom'
            }
            
            # Parse XML with multiple potential namespace strategies
            root = ET.fromstring(raw_data)
            print("DEBUGGING WEBHOOK: XML parsing successful")
            
            # Print out all namespaces for debugging
            print("DEBUGGING WEBHOOK: XML Namespaces:")
            for key, value in root.nsmap.items() if hasattr(root, 'nsmap') else {}:
                print(f"  {key}: {value}")
        
        except ET.ParseError as xml_error:
            print(f"DEBUGGING WEBHOOK: XML Parsing Error - {xml_error}")
            print(f"DEBUGGING WEBHOOK: Problematic XML:\n{raw_data}")
            return jsonify({
                "status": "error",
                "message": f"XML Parsing Error: {xml_error}",
                "processedVideos": []
            }), 400
        
        # Video ID extraction
        def extract_id(text):
            import re
            match = re.search(r'([a-zA-Z0-9_-]{11})', str(text))
            return match.group(1) if match else None

        video_id = None

        # Strategy 1: Direct ID elements
        id_elem = root.find('.//id')
        if id_elem is not None and id_elem.text:
            video_id = extract_id(id_elem.text)

        # Strategy 2: Link href attributes
        if not video_id:
            for link in root.findall('.//link'):
                href = link.get('href')
                if href:
                    video_id = extract_id(href)
                    if video_id:
                        break

        # Strategy 3: Iterate through all text content
        if not video_id:
            for elem in root.iter():
                if elem.text:
                    video_id = extract_id(elem.text)
                    if video_id:
                        break

        # Strategy 4: Raw XML text
        if not video_id:
            video_id = extract_id(raw_data)

        # Process the video
        try:
            processed = process_video(video_id)
            
            if processed:
                return jsonify({
                    "status": "success",
                    "message": "Processed 1 videos",
                    "processedVideos": [{"status": "success", "video_id": video_id}]
                }), 200
            else:
                return jsonify({
                    "status": "success",
                    "message": "Processed 1 videos",
                    "processedVideos": [{"status": "failed", "video_id": video_id}]
                }), 200
        
        except Exception as process_error:
            print(f"DEBUGGING WEBHOOK: Video Processing Error - {process_error}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "status": "error",
                "message": f"Video Processing Error: {process_error}",
                "processedVideos": [{"status": "failed", "video_id": video_id}]
            }), 500
    
    except Exception as e:
        print(f"DEBUGGING WEBHOOK: Unexpected Error - {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": str(e),
            "processedVideos": []
        }), 500

def process_video(video_id):
    logging.info(f"Processing video: {video_id}")
    processor = TranscriptProcessor()
    transcript = processor.extract_transcript(video_id)
    logging.info(f"Transcript length: {len(transcript)} characters")
    summary = processor.generate_summary(transcript)
    logging.info(f"Summary length: {len(summary)} characters")
    return True

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
