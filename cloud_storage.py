import os
import logging
from datetime import datetime
from google.cloud import storage
from google.oauth2 import service_account

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

    def upload_summary(self, summary, channel_name=None, video_title=None):
        """
        Upload summary to Google Cloud Storage
        
        Args:
            summary (str): Summary text to upload
            channel_name (str, optional): Name of the YouTube channel
            video_title (str, optional): Title of the YouTube video
        
        Returns:
            str: Public URL of the uploaded summary
        """
        # Generate filename based on channel and video title
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Sanitize filenames by removing special characters and replacing spaces
        def sanitize_filename(name):
            if not name:
                return "Unknown"
            return "".join(c if c.isalnum() or c in [' ', '_', '-'] else '_' for c in name).rstrip()
        
        channel_safe = sanitize_filename(channel_name)
        video_safe = sanitize_filename(video_title)
        
        filename = f"summaries/{channel_safe}_{video_safe}_{timestamp}.txt"
        
        try:
            blob = self.bucket.blob(filename)
            blob.upload_from_string(summary, content_type='text/plain')
            blob.make_public()
            
            logging.info(f"Summary uploaded: {filename}")
            return blob.public_url
        except Exception as e:
            logging.error(f"Failed to upload summary: {e}")
            raise

    def list_summaries(self, channel_name=None, max_results=100):
        """
        List summaries, optionally filtered by channel
        
        Args:
            channel_name (str, optional): Filter by specific channel
            max_results (int): Maximum number of results to return
        
        Returns:
            list: List of summary file details
        """
        try:
            prefix = f"summaries/{channel_name}/" if channel_name else "summaries/"
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
        channel_name='Test Channel',
        video_title='Test Video'
    )
    print(f"Uploaded summary URL: {url}")
