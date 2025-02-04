import logging
import os
import json
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
from datetime import datetime
from google.cloud import storage
from google.oauth2 import service_account
import sys

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to capture all log messages
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Add stdout handler to ensure logs are printed
        logging.FileHandler('cloud_storage_debug.log')  # Optional: also log to a file
    ]
)
logger = logging.getLogger(__name__)

# Configure Gemini API
api_key = os.getenv('GEMINI_API_KEY')
if api_key:
    genai.configure(api_key=api_key)
else:
    logger.warning("No API key found for Gemini")

def upload_to_cloud_storage(summary_text, video_id=None, channel_name=None, video_title=None):
    """
    Upload summary to Google Cloud Storage
    
    Args:
        summary_text (str): Summary text to upload
        video_id (str, optional): YouTube video ID
        channel_name (str, optional): Name of the YouTube channel
        video_title (str, optional): Title of the YouTube video
    
    Returns:
        str: Public URL of the uploaded summary or None
    """
    try:
        # Load credentials
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        
        if not credentials_path:
            logger.error("No Google credentials path found in environment")
            return None
        
        try:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            
            # Initialize storage client
            try:
                client = storage.Client(credentials=credentials)
            except Exception as client_error:
                logger.error(f"Storage client initialization error: {client_error}")
                return None
        
        except Exception as credentials_error:
            logger.error(f"Credentials loading error: {credentials_error}")
            return None
        
        # Define bucket name
        bucket_name = 'youtube_summaries_daily-other_auto'
        
        # List buckets with alternative method
        try:
            storage_client = storage.Client(credentials=credentials)
            buckets = list(storage_client.list_buckets())
            if not buckets:
                print("No buckets found in the project.")
            else:
                print("Available buckets:")
                for bucket in buckets:
                    print(f"- {bucket.name}")
                if bucket_name not in [b.name for b in buckets]:
                    print(f"WARNING: Bucket '{bucket_name}' not found in the project.")
        except Exception as list_error:
            import traceback
            traceback.print_exc()
        
        # Verify bucket exists
        try:
            bucket = client.bucket(bucket_name)
            bucket.reload()  # This will raise an error if bucket doesn't exist
        except Exception as bucket_error:
            return None
        
        # Sanitize filenames
        def sanitize_filename(name):
            if not name:
                return "Unknown"
            return "".join(c if c.isalnum() or c in [' ', '_', '-'] else '_' for c in name).rstrip()
        
        channel_safe = sanitize_filename(channel_name)
        video_safe = sanitize_filename(video_title)
        timestamp = datetime.now().strftime("%Y%m%d")
        
        filename = f"{channel_safe}_{video_safe}_{timestamp}.txt"
        
        # Upload file
        try:
            blob = bucket.blob(filename)
            blob.upload_from_string(summary_text, content_type='text/plain')
            blob.make_public()
            print(f"Summary uploaded to cloud: {filename}")
            return blob.public_url
        except Exception as upload_error:
            logger.error(f"Cloud storage upload error: {upload_error}")
            return None
    
    except Exception as e:
        logger.error(f"Unexpected cloud storage error: {e}")
        return None

def process_video_from_payload(payload):
    """
    Comprehensive video processing function that handles everything from 
    extracting video ID to uploading summary to cloud storage.
    
    Args:
        payload (dict): Superfeedr webhook payload
    
    Returns:
        dict: Processing results with success status, video details, and summary
    """
    try:
        # Extract video details from payload
        video_id = payload['items'][0]['id'].split(':')[-1]
        channel_name = payload.get('title', 'Unknown Channel')
        video_title = payload['items'][0].get('title', 'Unknown Title')
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Log processing start
        logger.info(f"Processing video: {video_title} from {channel_name}")
        
        # Retrieve transcript
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript_obj = transcript_list.find_generated_transcript(['en']).fetch()
            transcript_text = ' '.join([entry['text'] for entry in transcript_obj])
        except Exception as transcript_error:
            logger.error(f"Transcript retrieval error: {transcript_error}")
            return {
                'success': False,
                'video_id': video_id,
                'error': 'Could not retrieve transcript',
                'payload': payload
            }
        
        # Generate summary using Gemini
        try:
            model = genai.GenerativeModel('gemini-pro')
            summary_prompt = f"""CRITICAL INSTRUCTIONS:

Output MUST be in TWO PARTS:

Part 1: Current Market Snapshot

Part 2: Comprehensive Trading Strategy Analysis

No exceptions: If the video lacks content for one part, still generate both sections with whatever is available.

Step 1: Analyze the Video Content

Read the entire video transcript carefully.

Identify and mark sections that mention:

- Market conditions, sentiment, trends, momentum, key price levels, liquidity zones, macro events, or time-sensitive information.
- Trading indicators, tools, methods, entry/exit rules, stop-losses, risk management, and other detailed trading strategy components.

Step 2: Extract and Organize Information

For Part 1 (Current Market Snapshot):

Extract only explicit, time-sensitive information from the video.

Include:
- Market sentiment (e.g., extreme greed, fear).
- Trends (e.g., bullish, bearish, consolidation).
- Momentum (e.g., higher highs, pullbacks).
- Key price levels (e.g., support, resistance).
- Liquidity zones (e.g., order book data, CME gaps).
- Macro trends/events (e.g., Federal Reserve actions, economic data).

Do not include generic market commentary or assumptions.

For Part 2 (Comprehensive Trading Strategy Analysis):

Extract every explicit mention of trading indicators, tools, methods, and rules from the video.

Include:
- Indicators and Tools: Exact rules, calculations, and interpretations (e.g., RSI, MACD, Fibonacci extensions).
- Key Levels and Zones: How they're defined, confirmed, and used (e.g., support/resistance, liquidity zones).
- Trading Rules: Entries, exits, stop-losses, and position sizing (e.g., "buy above 104k with RSI confirmation").
- Risk Management: Risk tolerance, profit protection, and psychological frameworks (e.g., "risk no more than 2% per trade").

Do not include generic trading strategies or assumptions.

Step 3: Structure the Output

Part 1: Current Market Snapshot
- Present the extracted content in bullet points or short paragraphs.
- Ensure no overlap with Part 2.

Part 2: Comprehensive Trading Strategy Analysis
- Present the extracted content in bullet points or short paragraphs.
- Use clear headings for each category (e.g., Indicators and Tools, Key Levels and Zones, Trading Rules, Risk Management).
- Ensure no overlap with Part 1.

Step 4: Quality Control
- Double-check: Ensure only information explicitly mentioned in the video is included.
- Remove generic content: Exclude any market or trading commentary not directly discussed in the video.
- Flag gaps: If no explicit details exist for a section, clearly note that only minimal or no direct content was available.

Video Transcript:
{transcript_text}

OUTPUT FORMAT:
1. Part 1: Current Market Snapshot
2. Part 2: Comprehensive Trading Strategy Analysis"""
            
            summary_response = model.generate_content(summary_prompt)
            summary_text = summary_response.text.strip()
        except Exception as summary_error:
            logger.error(f"Summary generation error: {summary_error}")
            summary_text = "Unable to generate summary"
        
        # Upload to cloud storage
        cloud_url = upload_to_cloud_storage(summary_text, video_id, channel_name, video_title)
        
        # Prepare and return processing result
        return {
            'success': True,
            'video_id': video_id,
            'channel_name': channel_name,
            'video_title': video_title,
            'video_url': video_url,
            'transcript': transcript_text,
            'summary': summary_text,
            'cloud_url': cloud_url,
            'payload': payload
        }
    
    except Exception as e:
        logger.error(f"Unexpected error processing video: {e}")
        return {
            'success': False,
            'error': str(e),
            'payload': payload
        }

# Test the function if script is run directly
if __name__ == '__main__':
    # Example payload similar to Superfeedr webhook
    test_payload = {
        'title': 'Crypto Cobra',
        'items': [{
            'id': 'yt:video:I38uVbXGymA',
            'title': 'Bitcoin just hit the MOST Important Level! Do Not Miss THIS Move!',
            'published': 1738603337,
            'updated': 1738603700,
            'permalinkUrl': 'https://www.youtube.com/watch?v=I38uVbXGymA'
        }]
    }
    
    # Run the processing function
    print("Starting video processing...")
    result = process_video_from_payload(test_payload)
    
    # Print the result with full details
    import json
    print("\n--- FULL PROCESSING RESULT ---")
    print(json.dumps(result, indent=2))
    print("\n--- END OF PROCESSING RESULT ---")
