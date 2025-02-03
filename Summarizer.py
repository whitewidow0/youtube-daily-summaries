import logging
import os
import json
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
from cloud_storage import CloudStorageManager

class TranscriptProcessor:
    def __init__(self, api_key=None):
        """
        Initialize TranscriptProcessor with optional API key
        
        Args:
            api_key (str, optional): Gemini API key. Defaults to None.
        """
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Set up Gemini API key
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        
        # Initialize Cloud Storage Manager
        try:
            self.cloud_storage = CloudStorageManager()
        except Exception as e:
            self.logger.error(f"Failed to initialize Cloud Storage: {e}")
            self.cloud_storage = None
        
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
            except Exception as e:
                self.logger.error(f"Gemini API configuration error: {e}")
        else:
            self.logger.warning("No API key found for Gemini")

    def get_transcript(self, video_id):
        """
        Retrieve transcript for a given video ID
        
        Args:
            video_id (str): YouTube video ID
        
        Returns:
            list: Transcript text
        """
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            return transcript
        except Exception as e:
            self.logger.error(f"Error retrieving transcript for {video_id}: {e}")
            return None

    def extract_transcript(self, video_id):
        """
        Extract full transcript text from video ID
        
        Args:
            video_id (str): YouTube video ID
        
        Returns:
            str: Full transcript text
        """
        transcript = self.get_transcript(video_id)
        if transcript:
            return ' '.join([entry['text'] for entry in transcript])
        return None

    def generate_summary(self, transcript):
        """
        Generate summary using Gemini API with a comprehensive trading analysis approach
        
        Args:
            transcript (str): Full transcript text
        
        Returns:
            str: Generated summary with market snapshot and trading strategy analysis
        """
        if not self.api_key:
            self.logger.error("Cannot generate summary: No Gemini API key")
            return None

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
{transcript}

OUTPUT FORMAT:
1. Part 1: Current Market Snapshot
2. Part 2: Comprehensive Trading Strategy Analysis"""
            
            response = model.generate_content(summary_prompt)
            return response.text.strip()
        except Exception as e:
            self.logger.error(f"Summary generation error: {e}")
            return None

    def process_video(self, video_id, channel_name=None, video_title=None):
        """
        Process video by extracting transcript and generating summary
        
        Args:
            video_id (str): YouTube video ID
            channel_name (str, optional): Name of the YouTube channel
            video_title (str, optional): Title of the YouTube video
        
        Returns:
            dict: Processing results
        """
        try:
            transcript = self.extract_transcript(video_id)
            if not transcript:
                return {
                    'video_id': video_id,
                    'success': False,
                    'error': 'Could not retrieve transcript'
                }
            
            summary = self.generate_summary(transcript)
            
            # Upload summary to cloud storage if possible
            cloud_url = None
            if self.cloud_storage and summary:
                try:
                    cloud_url = self.cloud_storage.upload_summary(
                        summary=summary, 
                        channel_name=channel_name, 
                        video_title=video_title
                    )
                except Exception as e:
                    self.logger.error(f"Cloud storage upload failed: {e}")
            
            return {
                'video_id': video_id,
                'success': True,
                'transcript': transcript,
                'summary': summary,
                'cloud_url': cloud_url
            }
        except Exception as e:
            return {
                'video_id': video_id,
                'success': False,
                'error': str(e)
            }
