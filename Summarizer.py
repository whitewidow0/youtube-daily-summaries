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
        Initialize TranscriptProcessor with optional API key and comprehensive error handling
        
        Args:
            api_key (str, optional): Gemini API key. Defaults to None.
        
        Raises:
            ValueError: If no API key is found or configuration fails
        """
        print("DEBUGGING SUMMARIZER: Initializing TranscriptProcessor")
        
        try:
            # Initialize logging with more detailed configuration
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.StreamHandler(),  # Console output
                    logging.FileHandler('summarizer_debug.log', mode='a')  # File logging
                ]
            )
            self.logger = logging.getLogger(__name__)
            
            # Set up Gemini API with multiple fallback methods
            print("DEBUGGING SUMMARIZER: Setting up Gemini API")
            
            # Attempt to get API key from multiple sources
            if not api_key:
                # Priority 1: Passed argument
                api_key = os.getenv('GEMINI_API_KEY')
            
            if not api_key:
                # Priority 2: .env file
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                    api_key = os.getenv('GEMINI_API_KEY')
                except ImportError:
                    print("DEBUGGING SUMMARIZER: python-dotenv not installed")
            
            if not api_key:
                # Priority 3: Configuration file
                try:
                    with open('.gemini_config.json', 'r') as config_file:
                        config = json.load(config_file)
                        api_key = config.get('api_key')
                except FileNotFoundError:
                    print("DEBUGGING SUMMARIZER: No .gemini_config.json found")
                except json.JSONDecodeError:
                    print("DEBUGGING SUMMARIZER: Invalid .gemini_config.json")
            
            if not api_key:
                print("DEBUGGING SUMMARIZER: No API key found!")
                raise ValueError("No Gemini API key provided. Check environment, .env, or config file.")
            
            # Validate API key format (basic check)
            if len(api_key) < 10:
                print("DEBUGGING SUMMARIZER: Invalid API key format")
                raise ValueError("API key appears to be malformed")
            
            # Configure Gemini with extensive error handling
            try:
                genai.configure(api_key=api_key)
                print("DEBUGGING SUMMARIZER: Gemini API configured successfully")
                
                # Verify API configuration
                try:
                    test_model = genai.GenerativeModel('gemini-pro')
                    test_response = test_model.generate_content("Test API configuration")
                    print("DEBUGGING SUMMARIZER: API configuration test successful")
                except Exception as test_error:
                    print(f"DEBUGGING SUMMARIZER: API configuration test failed - {test_error}")
                    raise
            
            except Exception as config_error:
                print(f"DEBUGGING SUMMARIZER: Gemini API configuration error - {config_error}")
                raise
        
        except Exception as e:
            print(f"DEBUGGING SUMMARIZER: Initialization Error - {e}")
            import traceback
            traceback.print_exc()
            raise

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

    def generate_summary(self, transcript):
        """
        Generate a summary of the transcript using Gemini AI with extensive logging and error handling
        
        Args:
            transcript (str): Full transcript text
        
        Returns:
            str or None: Generated summary or None if generation fails
        """
        print("DEBUGGING SUMMARY: Starting summary generation")
        
        try:
            # Validate transcript
            if not transcript or not isinstance(transcript, str):
                print("DEBUGGING SUMMARY: Invalid or empty transcript")
                return None
            
            print(f"DEBUGGING SUMMARY: Transcript length: {len(transcript)} characters")
            
            # Truncate very long transcripts to avoid API limits
            max_transcript_length = 10000  # Adjust based on API limits
            if len(transcript) > max_transcript_length:
                print(f"DEBUGGING SUMMARY: Truncating transcript from {len(transcript)} to {max_transcript_length} characters")
                transcript = transcript[:max_transcript_length]
            
            # Prepare prompt for summary generation
            summary_prompt = f"""
            Please generate a concise, informative summary of the following transcript. 
            Focus on the key points, main ideas, and most important information.
            Aim for a summary that captures the essence of the content in about 3-5 sentences.

            Transcript:
            {transcript}
            """
            
            try:
                # Configure Gemini model for summarization
                model = genai.GenerativeModel('gemini-pro')
                
                print("DEBUGGING SUMMARY: Generating summary with Gemini AI")
                response = model.generate_content(summary_prompt)
                
                # Check response
                if not response or not response.text:
                    print("DEBUGGING SUMMARY: Empty response from Gemini AI")
                    return None
                
                summary = response.text.strip()
                
                print(f"DEBUGGING SUMMARY: Generated summary. Length: {len(summary)} characters")
                print(f"DEBUGGING SUMMARY: Summary preview: {summary[:500]}...")
                
                return summary
            
            except Exception as generation_error:
                print(f"DEBUGGING SUMMARY: Summary generation error - {generation_error}")
                import traceback
                traceback.print_exc()
                return None
        
        except Exception as e:
            print(f"DEBUGGING SUMMARY: Unexpected error in summary generation - {e}")
            import traceback
            traceback.print_exc()
            return None

    def process_video(self, video_id):
        """
        Process a single video by extracting transcript and generating summary
        
        Args:
            video_id (str): YouTube video ID to process
        
        Returns:
            bool: True if processing was successful, False otherwise
        """
        print(f"DEBUGGING PROCESS_VIDEO: Starting video processing for ID: {video_id}")
        
        try:
            # Transcript Extraction
            print("DEBUGGING PROCESS_VIDEO: Attempting transcript extraction")
            transcript = self.extract_transcript(video_id)
            
            if not transcript:
                print(f"DEBUGGING PROCESS_VIDEO: Failed to extract transcript for video {video_id}")
                return False
            
            print(f"DEBUGGING PROCESS_VIDEO: Transcript extracted successfully. Length: {len(transcript)} characters")
            
            # Summary Generation
            print("DEBUGGING PROCESS_VIDEO: Attempting summary generation")
            summary = self.generate_summary(transcript)
            
            if not summary:
                print(f"DEBUGGING PROCESS_VIDEO: Failed to generate summary for video {video_id}")
                return False
            
            print(f"DEBUGGING PROCESS_VIDEO: Summary generated successfully. Length: {len(summary)} characters")
            print(f"DEBUGGING PROCESS_VIDEO: Summary preview: {summary[:500]}...")
            
            # Optional: Cloud Storage Upload (placeholder)
            print("DEBUGGING PROCESS_VIDEO: Simulating cloud storage upload")
            
            print(f"DEBUGGING PROCESS_VIDEO: Successfully processed video {video_id}")
            return True
        
        except Exception as e:
            print(f"DEBUGGING PROCESS_VIDEO: Unexpected error processing video {video_id} - {e}")
            import traceback
            traceback.print_exc()
            return False

    def upload_summary_to_cloud_storage(self, video_id, summary):
        # TO DO: Implement cloud storage upload logic
        pass

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
