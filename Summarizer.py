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
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        full_transcript = ' '.join([entry['text'] for entry in transcript])
        return full_transcript

    def generate_summary(self, transcript):
        model = genai.GenerativeModel('gemini-pro')
        summary_prompt = f"""
        Please generate a concise, informative summary of the following transcript. 
        Focus on the key points, main ideas, and most important information.
        Aim for a summary that captures the essence of the content in about 3-5 sentences.

        Transcript:
        {transcript}
        """
        
        response = model.generate_content(summary_prompt)
        return response.text.strip()

    def process_video(self, video_id):
        transcript = self.extract_transcript(video_id)
        summary = self.generate_summary(transcript)
        return True  

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
