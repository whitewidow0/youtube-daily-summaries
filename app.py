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
        
        # Extract video ID from XML with multiple strategies
        try:
            # Different XPath strategies for video ID extraction
            video_id_paths = [
                ".//atom:id[contains(text(), 'yt:video:')]",
                ".//atom:id",
                ".//*[local-name()='id'][contains(text(), 'yt:video:')]",
                ".//*[local-name()='id']"
            ]
            
            video_id = None
            for path in video_id_paths:
                try:
                    # Try with each namespace
                    for ns_prefix, ns_uri in NAMESPACES.items():
                        namespaces = {ns_prefix: ns_uri}
                        id_elements = root.findall(path, namespaces)
                        
                        print(f"DEBUGGING WEBHOOK: Searching with path '{path}' and namespace '{ns_prefix}'")
                        print(f"DEBUGGING WEBHOOK: Found {len(id_elements)} ID elements")
                        
                        for elem in id_elements:
                            print(f"DEBUGGING WEBHOOK: Examining ID Element: {elem.text}")
                            if elem.text and 'yt:video:' in elem.text:
                                video_id = elem.text.split(':')[-1]
                                break
                        
                        if video_id:
                            break
                    
                    if video_id:
                        break
                
                except Exception as path_error:
                    print(f"DEBUGGING WEBHOOK: Error with path {path}: {path_error}")
            
            if not video_id:
                print("DEBUGGING WEBHOOK: No video ID found in XML")
                return jsonify({
                    "status": "error", 
                    "message": "No video ID found",
                    "processedVideos": []
                }), 400
            
            print(f"DEBUGGING WEBHOOK: Extracted Video ID: {video_id}")
        
        except Exception as extraction_error:
            print(f"DEBUGGING WEBHOOK: Video ID Extraction Error - {extraction_error}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "status": "error",
                "message": f"Video ID Extraction Error: {extraction_error}",
                "processedVideos": []
            }), 400
        
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
    """
    Process a single video by extracting transcript and generating summary with extensive debugging
    
    Args:
        video_id (str): YouTube video ID to process
    
    Returns:
        bool: True if processing was successful, False otherwise
    """
    print(f"DEBUGGING PROCESS_VIDEO: Starting processing for video ID: {video_id}")
    
    # Validate video ID
    if not video_id or not isinstance(video_id, str):
        print(f"DEBUGGING PROCESS_VIDEO: Invalid video ID type or empty: {video_id}")
        return False
    
    # Validate video ID format (basic sanity check)
    if not all(c in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-' for c in video_id):
        print(f"DEBUGGING PROCESS_VIDEO: Invalid characters in video ID: {video_id}")
        return False
    
    try:
        # Initialize TranscriptProcessor with extensive logging
        print("DEBUGGING PROCESS_VIDEO: Initializing TranscriptProcessor")
        transcript_processor = TranscriptProcessor()
        
        # Extract transcript
        try:
            print(f"DEBUGGING PROCESS_VIDEO: Attempting to extract transcript for video {video_id}")
            transcript = transcript_processor.extract_transcript(video_id)
            
            if not transcript:
                print(f"DEBUGGING PROCESS_VIDEO: No transcript found for video {video_id}")
                return False
            
            print(f"DEBUGGING PROCESS_VIDEO: Transcript extracted successfully. Length: {len(transcript)} characters")
            
            # Validate transcript length
            min_transcript_length = 50  # Minimum meaningful transcript length
            if len(transcript) < min_transcript_length:
                print(f"DEBUGGING PROCESS_VIDEO: Transcript too short. Length: {len(transcript)} characters")
                return False
        
        except Exception as transcript_error:
            print(f"DEBUGGING PROCESS_VIDEO: Transcript Extraction Error - {transcript_error}")
            import traceback
            traceback.print_exc()
            return False
        
        # Generate summary
        try:
            print(f"DEBUGGING PROCESS_VIDEO: Attempting to generate summary for video {video_id}")
            summary = transcript_processor.generate_summary(transcript)
            
            if not summary:
                print(f"DEBUGGING PROCESS_VIDEO: Summary generation failed for video {video_id}")
                return False
            
            print(f"DEBUGGING PROCESS_VIDEO: Summary generated successfully. Length: {len(summary)} characters")
            
            # Validate summary
            min_summary_length = 10  # Minimum meaningful summary length
            max_summary_length = 1000  # Maximum reasonable summary length
            if len(summary) < min_summary_length or len(summary) > max_summary_length:
                print(f"DEBUGGING PROCESS_VIDEO: Invalid summary length. Length: {len(summary)} characters")
                return False
        
        except Exception as summary_error:
            print(f"DEBUGGING PROCESS_VIDEO: Summary Generation Error - {summary_error}")
            import traceback
            traceback.print_exc()
            return False
        
        # Upload summary to cloud storage
        try:
            print(f"DEBUGGING PROCESS_VIDEO: Attempting to upload summary for video {video_id}")
            
            # Fetch video details for cloud storage
            try:
                youtube = build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))
                video_response = youtube.videos().list(
                    part='snippet',
                    id=video_id
                ).execute()
                
                if not video_response['items']:
                    print(f"DEBUGGING PROCESS_VIDEO: Could not fetch video details for {video_id}")
                    return False
                
                video_info = video_response['items'][0]['snippet']
            except Exception as video_fetch_error:
                print(f"DEBUGGING PROCESS_VIDEO: Video details fetch error - {video_fetch_error}")
                return False
            
            # Placeholder for cloud storage upload
            print(f"DEBUGGING PROCESS_VIDEO: Simulating cloud storage upload")
            # Actual implementation would use a CloudStorageManager
            # cloud_storage_manager = CloudStorageManager()
            # upload_result = cloud_storage_manager.upload_summary(
            #     summary=summary, 
            #     video_id=video_id, 
            #     video_title=video_info['title'],
            #     channel_title=video_info['channelTitle']
            # )
            
            # if not upload_result:
            #     print(f"DEBUGGING PROCESS_VIDEO: Cloud storage upload failed for video {video_id}")
            #     return False
            
            print(f"DEBUGGING PROCESS_VIDEO: Successfully processed video {video_id}")
            return True
        
        except Exception as upload_error:
            print(f"DEBUGGING PROCESS_VIDEO: Upload Error - {upload_error}")
            import traceback
            traceback.print_exc()
            return False
    
    except Exception as e:
        print(f"DEBUGGING PROCESS_VIDEO: Unexpected error processing video {video_id} - {e}")
        import traceback
        traceback.print_exc()
        return False

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
