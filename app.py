import os
import sys
import logging
from flask import Flask, request, jsonify
from Summarizer import TranscriptProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[logging.FileHandler('youtube_webhook.log'), logging.StreamHandler(sys.stdout)]
)

# Initialize summarizer
summarizer = TranscriptProcessor()

app = Flask(__name__)

def extract_video_id(href):
    """Extract video ID from YouTube URL"""
    import re
    patterns = [
        r'v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'watch\?v=([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, href)
        if match:
            return match.group(1)
    
    return None

@app.route('/webhook', methods=['HEAD', 'POST'])
def youtube_webhook():
    """
    Webhook endpoint for processing YouTube video notifications
    Supports both HEAD and POST methods
    
    Returns:
        JSON response with video details or error, or 200 OK for HEAD
    """
    if request.method == 'HEAD':
        return '', 200
    
    try:
        payload = request.json
        
        # Extract channel details
        channel_title = payload.get('title', 'Unknown Channel')
        
        # Check if items exist
        items = payload.get('items', [])
        if not items:
            return jsonify({"error": "No items found in payload"}), 400
        
        # Get the first item
        first_item = items[0]
        
        # Extract video details from standardLinks
        standard_links = first_item.get('standardLinks', {})
        alternate_links = standard_links.get('alternate', [])
        
        if not alternate_links:
            return jsonify({"error": "No alternate links found"}), 400
        
        # Get the first alternate link's href
        video_url = alternate_links[0].get('href', '')
        video_id = extract_video_id(video_url)
        video_title = first_item.get('title', 'Unknown Title')
        
        if not video_id:
            return jsonify({"error": f"Could not extract video ID from URL: {video_url}"}), 400
        
        # Process the entire video
        processing_result = summarizer.process_video(
            video_id=video_id, 
            channel_name=channel_title, 
            video_title=video_title
        )
        
        # Check processing result
        if not processing_result['success']:
            return jsonify({
                "error": processing_result.get('error', 'Video processing failed'),
                "video_id": video_id
            }), 500
        
        return jsonify({
            "video_id": video_id,
            "channel": channel_title,
            "video_title": video_title,
            "transcript_length": len(processing_result.get('transcript', '')),
            "summary_length": len(processing_result.get('summary', '')),
            "cloud_url": processing_result.get('cloud_url'),
            "full_result": processing_result
        }), 200
    
    except Exception as e:
        logging.error(f"Webhook processing error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        "status": "healthy",
        "services": {
            "gemini_api": summarizer.api_key is not None,
            "cloud_storage": summarizer.cloud_storage is not None
        }
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
