import logging
import traceback
from youtube_transcript_api import YouTubeTranscriptApi

class TranscriptTester:
    def __init__(self):
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def get_transcript(self, video_id):
        """
        Retrieve transcript for a given video ID
        
        Args:
            video_id (str): YouTube video ID
        
        Returns:
            list: Transcript text or None
        """
        try:
            # Log the video ID being processed
            self.logger.info(f"Attempting to retrieve transcript for video ID: {video_id}")
            
            # Attempt to get available transcripts
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try to get generated transcript
            transcript = transcript_list.find_generated_transcript(['en']).fetch()
            
            return transcript
        
        except Exception as e:
            # Detailed error logging
            self.logger.error(f"Detailed error retrieving transcript for {video_id}: {type(e).__name__} - {str(e)}")
            
            # If you want to see the full traceback
            self.logger.error(f"Full error traceback:\n{traceback.format_exc()}")
            
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

def main():
    tester = TranscriptTester()
    
    # Get video ID from user input
    video_id = input("Enter YouTube Video ID: ").strip()
    
    print(f"Attempting to retrieve transcript for video ID: {video_id}")
    
    try:
        # Retrieve transcript
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Retrieve and print transcript (auto-generated)
        transcript = transcript_list.find_generated_transcript(['en']).fetch()
        
        if transcript:
            print("\n=== 📜 Full Transcript ===\n")
            for entry in transcript:
                print(entry['text'])
        else:
            print("No transcript could be retrieved.")
    
    except Exception as e:
        print(f"Error retrieving transcript: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
