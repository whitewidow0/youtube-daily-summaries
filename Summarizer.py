import logging
import os
import json
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled
from google.cloud import storage
from google.oauth2 import service_account
import google.generativeai as genai

class TranscriptProcessor:
    def __init__(self, api_key=None):
        """
        Initialize TranscriptProcessor with Gemini API key
        
        Args:
            api_key (str, optional): Gemini API key. Defaults to environment variable.
        """
        # Use API key from parameter or environment variable
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        
        if not self.api_key:
            raise ValueError("Gemini API key is required")
        
        # Configure Gemini API
        genai.configure(api_key=self.api_key)
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def extract_transcript(self, video_id):
        """
        Extract transcript from a YouTube video with extensive error handling and logging
        
        Args:
            video_id (str): YouTube video ID
        
        Returns:
            str or None: Full transcript text or None if extraction fails
        """
        print(f"DEBUGGING TRANSCRIPT: Attempting to extract transcript for video ID: {video_id}")
        
        try:
            # Attempt to fetch transcripts
            print("DEBUGGING TRANSCRIPT: Using YouTubeTranscriptApi to fetch transcript")
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Prioritize languages
            preferred_languages = ['en', 'en-US', 'en-GB']
            
            # Try to find a transcript
            transcript = None
            
            # First, try manually created transcripts
            try:
                transcript = transcript_list.find_manually_created_transcript(preferred_languages)
                print("DEBUGGING TRANSCRIPT: Found manually created transcript")
            except Exception as manual_error:
                print(f"DEBUGGING TRANSCRIPT: No manually created transcript - {manual_error}")
            
            # If no manual transcript, try generated transcripts
            if not transcript:
                try:
                    transcript = transcript_list.find_generated_transcript(preferred_languages)
                    print("DEBUGGING TRANSCRIPT: Found generated transcript")
                except Exception as generated_error:
                    print(f"DEBUGGING TRANSCRIPT: No generated transcript - {generated_error}")
            
            # If still no transcript, try the first available transcript
            if not transcript:
                try:
                    transcript = transcript_list.transcripts[0]
                    print("DEBUGGING TRANSCRIPT: Using first available transcript")
                except Exception as first_error:
                    print(f"DEBUGGING TRANSCRIPT: No transcripts available - {first_error}")
                    return None
            
            # Extract full transcript text
            full_transcript = ' '.join([entry['text'] for entry in transcript.fetch()])
            
            # Check if transcript is empty
            if not full_transcript:
                print("DEBUGGING TRANSCRIPT: Extracted transcript is empty")
                return None
            
            print(f"DEBUGGING TRANSCRIPT: Transcript extracted successfully. Length: {len(full_transcript)} characters")
            print(f"DEBUGGING TRANSCRIPT: First 500 characters: {full_transcript[:500]}...")
            
            return full_transcript
        
        except TranscriptsDisabled:
            print(f"DEBUGGING TRANSCRIPT: Transcripts are disabled for video {video_id}")
            return None
        
        except Exception as retrieval_error:
            print(f"DEBUGGING TRANSCRIPT: Unexpected transcript retrieval error - {retrieval_error}")
            import traceback
            traceback.print_exc()
            return None

    def generate_summary(self, transcript, max_length=2000):
        """
        Generate summary using Gemini AI with a comprehensive trading analysis approach
        
        Args:
            transcript (str): Full video transcript
            max_length (int, optional): Maximum summary length. Defaults to 2000.
        
        Returns:
            str: Generated summary with market snapshot and trading strategy analysis
        """
        if not transcript:
            return "No transcript available for summarization."
        
        try:
            model = genai.GenerativeModel('gemini-pro')
            prompt = f"""Output MUST be in TWO PARTS:

Part 1: Current Market Snapshot

Part 2: Comprehensive Trading Strategy Analysis

No exceptions: If the video lacks content for one part, still generate both sections with whatever is available.

Step 1: Analyze the Video Content

Read the entire video transcript carefully.

Identify and mark sections that mention:

Market conditions, sentiment, trends, momentum, key price levels, liquidity zones, macro events, or time-sensitive information.

Trading indicators, tools, methods, entry/exit rules, stop-losses, risk management, and other detailed trading strategy components.

Step 2: Extract and Organize Information

For Part 1 (Current Market Snapshot):

Extract only explicit, time-sensitive information from the video.

Include:

Market sentiment (e.g., extreme greed, fear).

Trends (e.g., bullish, bearish, consolidation).

Momentum (e.g., higher highs, pullbacks).

Key price levels (e.g., support, resistance).

Liquidity zones (e.g., order book data, CME gaps).

Macro trends/events (e.g., Federal Reserve actions, economic data).

Do not include generic market commentary or assumptions.

For Part 2 (Comprehensive Trading Strategy Analysis):

Extract every explicit mention of trading indicators, tools, methods, and rules from the video.

Include:

Indicators and Tools: Exact rules, calculations, and interpretations (e.g., RSI, MACD, Fibonacci extensions).

Key Levels and Zones: How they're defined, confirmed, and used (e.g., support/resistance, liquidity zones).

Trading Rules: Entries, exits, stop-losses, and position sizing (e.g., "buy above 104k with RSI confirmation").

Risk Management: Risk tolerance, profit protection, and psychological frameworks (e.g., "risk no more than 2% per trade").

Do not include generic trading strategies or assumptions.

Step 3: Structure the Output

Part 1: Current Market Snapshot

Present the extracted content in bullet points or short paragraphs.

Ensure no overlap with Part 2.

Part 2: Comprehensive Trading Strategy Analysis

Present the extracted content in bullet points or short paragraphs.

Use clear headings for each category (e.g., Indicators and Tools, Key Levels and Zones, Trading Rules, Risk Management).

Ensure no overlap with Part 1.

Step 4: Quality Control

Double-check: Ensure only information explicitly mentioned in the video is included.

Remove generic content: Exclude any market or trading commentary not directly discussed in the video.

Flag gaps: If no explicit details exist for a section, clearly note that only minimal or no direct content was available.

Video Transcript:
{transcript}
"""
            
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            self.logger.error(f"Error generating summary: {e}")
            return "Failed to generate summary."

    def process_video(self, video_id):
        """
        Full video processing workflow
        
        Args:
            video_id (str): YouTube video ID
        
        Returns:
            dict: Processing results with transcript and summary
        """
        self.logger.info(f"Processing video: {video_id}")
        
        # Extract transcript
        transcript = self.extract_transcript(video_id)
        
        # Generate summary
        summary = self.generate_summary(transcript) if transcript else None
        
        return {
            'video_id': video_id,
            'transcript': transcript,
            'summary': summary
        }

def youtube_webhook(request):
    """
    Webhook to process video and get a transcript/summarization.
    
    Args:
        request (Request): The incoming HTTP request with video ID.
    
    Returns:
        str: Response to confirm the webhook was processed.
    """
    try:
        video_id = request.json.get('video_id')
        if not video_id:
            raise ValueError("Video ID is missing in the request.")

        # Get transcript for the given video ID
        transcript_processor = TranscriptProcessor()
        transcript = transcript_processor.extract_transcript(video_id)
        
        # If transcript is retrieved, summarize it
        summary = transcript_processor.generate_summary(transcript)

        # Return a response with the video ID and summary
        return {"video_id": video_id, "summary": summary}
    
    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        return {"error": str(e)}

# Main function to run the PubSub processor
def main():
    logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    main()
