import os
import logging
from datetime import datetime
from google.cloud import storage
from google.oauth2 import service_account
from googleapiclient.discovery import build

class CloudStorageManager:
    def __init__(self, bucket_name='youtube_summaries_daily-other_auto'):
        """
        Initialize Google Cloud Storage client with explicit credentials
        
        Args:
            bucket_name (str): Name of the GCS bucket to use
        """
        # Path to the service account JSON key file
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 
            os.path.join(os.path.dirname(__file__), 'careful-hangar-446706-n7-ea19c1b519da.json')
        )
        
        # Log credentials path details
        logging.info(f"Attempting to load credentials from: {credentials_path}")
        logging.info(f"Environment variable GOOGLE_APPLICATION_CREDENTIALS: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'NOT SET')}")
        logging.info(f"Current working directory: {os.getcwd()}")
        logging.info(f"Script directory: {os.path.dirname(__file__)}")
        
        # Check if credentials file exists
        if not os.path.exists(credentials_path):
            logging.error(f"Credentials file not found: {credentials_path}")
            raise FileNotFoundError(f"Credentials file not found: {credentials_path}")
        
        try:
            # Load credentials explicitly from the JSON file
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            
            # Initialize storage client with explicit credentials
            self.client = storage.Client(credentials=credentials)
            self.bucket = self.client.bucket(bucket_name)
            
            # Create bucket if it doesn't exist
            if not self.bucket.exists():
                logging.info(f"Creating bucket: {bucket_name}")
                self.client.create_bucket(bucket_name)
        
        except Exception as e:
            logging.error(f"Error initializing Cloud Storage: {e}")
            raise
    
    def upload_summary(self, summary, video_id, channel_id, video_title, channel_name):
        """
        Upload summary to Google Cloud Storage with a more descriptive filename
        
        Args:
            summary (str): Summary text to upload
            video_id (str): YouTube video ID
            channel_id (str): YouTube channel ID
            video_title (str): Title of the video
            channel_name (str): Name of the channel
        """
        # Sanitize filename by removing special characters and replacing spaces
        def sanitize_filename(name):
            return ''.join(c if c.isalnum() or c in [' ', '_'] else '_' for c in name).rstrip()
        
        # Generate a unique and descriptive filename
        sanitized_channel_name = sanitize_filename(channel_name)
        sanitized_video_title = sanitize_filename(video_title)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"summaries/{channel_id}/{sanitized_channel_name}_{sanitized_video_title}_summary.txt"
        
        try:
            blob = self.bucket.blob(filename)
            blob.upload_from_string(summary, content_type='text/plain')
            blob.make_public()
            
            logging.info(f"Summary uploaded: {filename}")
            return blob.public_url
        except Exception as e:
            logging.error(f"Failed to upload summary: {e}")
            raise
    
    def list_summaries(self, channel_id=None, max_results=100):
        """
        List summaries, optionally filtered by channel
        
        Args:
            channel_id (str, optional): Filter by specific channel
            max_results (int): Maximum number of results to return
        
        Returns:
            list: List of summary file details
        """
        try:
            prefix = f"summaries/{channel_id}/" if channel_id else "summaries/"
            blobs = list(self.client.list_blobs(self.bucket, prefix=prefix, max_results=max_results))
            
            return [
                {
                    'name': blob.name,
                    'url': blob.public_url,
                    'created': blob.time_created,
                    'size': blob.size
                }
                for blob in blobs
            ]
        
        except Exception as e:
            logging.error(f"Error listing summaries: {e}")
            return []
    
    def get_channel_name(self, channel_id):
        """
        Retrieve channel name using YouTube Data API
        
        Args:
            channel_id (str): YouTube channel ID
        
        Returns:
            str: Channel name or 'Unknown Channel'
        """
        try:
            # Use the same credentials path as in __init__
            credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 
                os.path.join(os.path.dirname(__file__), 'careful-hangar-446706-n7-ea19c1b519da.json')
            )
            
            # Log credentials path details
            logging.info(f"Attempting to load credentials from: {credentials_path}")
            logging.info(f"Environment variable GOOGLE_APPLICATION_CREDENTIALS: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'NOT SET')}")
            logging.info(f"Current working directory: {os.getcwd()}")
            logging.info(f"Script directory: {os.path.dirname(__file__)}")
            
            # Load credentials
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/youtube.readonly']
            )
            
            # Build YouTube service
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # Request channel details
            response = youtube.channels().list(
                part='snippet',
                id=channel_id
            ).execute()
            
            if response['items']:
                return response['items'][0]['snippet']['title']
            
            logging.warning(f"No channel found for ID: {channel_id}")
            return 'Unknown Channel'
        
        except Exception as e:
            logging.error(f"Error retrieving channel name: {e}")
            return 'Unknown Channel'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s'
)

# Example usage
if __name__ == "__main__":
    storage_manager = CloudStorageManager()
    
    # Example summary upload
    sample_summary = "This is a test summary about an important YouTube video."
    url = storage_manager.upload_summary(
        summary=sample_summary, 
        video_id='test_video_id', 
        channel_id='test_channel_id',
        video_title='Test Video Title',
        channel_name='Test Channel Name'
    )
    print(f"Uploaded summary URL: {url}")
