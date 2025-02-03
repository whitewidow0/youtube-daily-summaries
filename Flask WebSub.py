import requests
import xmltodict
from flask import Flask, request, Response
import logging
import sys
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSubSubscriber:
    def __init__(self, hub_url='https://pubsubhubbub.appspot.com'):
        self.hub_url = hub_url
        self.app = Flask(__name__)
        self.setup_routes()

    def setup_routes(self):
        @self.app.route('/webhook', methods=['GET', 'POST'])
        def webhook():
            # GET: Subscription verification
            if request.method == 'GET':
                hub_mode = request.args.get('hub.mode')
                hub_topic = request.args.get('hub.topic')
                hub_challenge = request.args.get('hub.challenge')
                hub_lease_seconds = request.args.get('hub.lease_seconds')

                logger.info(f"Verification Request - Mode: {hub_mode}, Topic: {hub_topic}")
                
                # Basic validation of verification parameters
                if hub_mode == 'subscribe' and hub_challenge:
                    logger.info("Subscription verification challenge received")
                    return hub_challenge, 200
                
                logger.error("Invalid verification request")
                return 'Verification Failed', 400

            # POST: Receive notifications
            if request.method == 'POST':
                try:
                    # Log raw request details for debugging
                    logger.info(f"Notification Headers: {dict(request.headers)}")
                    logger.info(f"Notification Content Type: {request.content_type}")
                    
                    # Get raw request body
                    raw_body = request.get_data()
                    logger.info(f"Raw Notification Body: {raw_body.decode('utf-8')}")
                    
                    # Parse XML notification
                    feed = xmltodict.parse(raw_body)
                    logger.info(f"Parsed Feed: {feed}")
                    
                    # Extract video details
                    entry = feed['feed'].get('entry', {})
                    if entry:
                        video_id = entry.get('yt:videoId')
                        channel_id = entry.get('yt:channelId')
                        video_title = entry.get('title')
                        
                        logger.info(f"New Video Notification:")
                        logger.info(f"Video ID: {video_id}")
                        logger.info(f"Channel ID: {channel_id}")
                        logger.info(f"Video Title: {video_title}")
                    
                    return '', 200
                
                except Exception as e:
                    logger.error(f"Notification Processing Error: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    return '', 500

    def subscribe(self, callback_url, channel_id):
        """
        Subscribe to a YouTube channel's feed
        :param callback_url: Publicly accessible webhook URL
        :param channel_id: YouTube channel ID
        """
        # Ensure callback URL is fully qualified
        if not callback_url.startswith('https://'):
            print(f"Error: Callback URL must start with https://. Current URL: {callback_url}")
            return False

        payload = {
            'hub.callback': callback_url,
            'hub.mode': 'subscribe',
            'hub.topic': f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}',
            'hub.verify': 'sync'
        }
        
        logger.info(f"Attempting to subscribe to channel {channel_id}")
        logger.info(f"Callback URL: {callback_url}")
        logger.info(f"Full payload: {payload}")
        
        try:
            # Log full request details
            logger.info(f"Sending request to hub: {self.hub_url}")
            
            response = requests.post(
                self.hub_url, 
                data=payload,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'WebSub Subscription Client'
                },
                timeout=10
            )
            
            # Log full response details
            logger.info(f"Response Status Code: {response.status_code}")
            logger.info(f"Response Headers: {response.headers}")
            logger.info(f"Response Content: {response.text}")
            
            if response.status_code == 204:
                logger.info(f"Successfully subscribed to channel {channel_id}")
                return True
            else:
                logger.error(f"Subscription failed for channel {channel_id}")
                logger.error(f"Status Code: {response.status_code}")
                logger.error(f"Response Headers: {response.headers}")
                logger.error(f"Response Content: {response.text}")
                return False
        
        except requests.RequestException as e:
            logger.error(f"Subscription request error for channel {channel_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def test_subscription(self, callback_url, channel_id):
        """
        Comprehensive test of WebSub subscription with extensive diagnostics
        :param callback_url: Publicly accessible webhook URL
        :param channel_id: YouTube channel ID
        """
        print(f"Testing WebSub for Channel: {channel_id}")
        print(f"Callback URL: {callback_url}")
        print(f"Hub URL: {self.hub_url}")

        def attempt_subscription(mode):
            payload = {
                'hub.callback': callback_url,
                'hub.mode': mode,
                'hub.topic': f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}',
                'hub.verify': 'sync'
            }

            print(f"\n{'='*50}")
            print(f"Attempting {mode.upper()} Subscription")
            print("Payload Details:")
            for key, value in payload.items():
                print(f"{key}: {value}")

            try:
                # Send subscription request with verbose logging
                print("\nSending Request...")
                response = requests.post(
                    self.hub_url, 
                    data=payload, 
                    timeout=10,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'User-Agent': 'WebSub Diagnostic Tool/1.0'
                    }
                )

                print("\nResponse Details:")
                print(f"Status Code: {response.status_code}")
                print(f"Headers:")
                for header, value in response.headers.items():
                    print(f"  {header}: {value}")
                print(f"Content: {response.text}")

                # Detailed error analysis
                if response.status_code != 204:
                    print("\n❌ SUBSCRIPTION ERROR DETAILS:")
                    print(f"Status Code: {response.status_code}")
                    print(f"Response Headers: {dict(response.headers)}")
                    print(f"Response Content: {response.text}")

                return response.status_code == 204

            except requests.RequestException as e:
                print(f"\n❌ REQUEST ERROR: {e}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
                return False

        # First unsubscribe, then subscribe
        unsubscribe_result = attempt_subscription('unsubscribe')
        subscribe_result = attempt_subscription('subscribe')
        
        return subscribe_result

    def run(self, host='0.0.0.0', port=None):
        """
        Run the Flask application with Render-compatible configuration
        :param host: Host to bind the server
        :param port: Port to listen on, defaults to PORT environment variable
        """
        # Use PORT environment variable if available, otherwise default to 8080
        if port is None:
            port = int(os.environ.get('PORT', 8080))
        
        print(f"Starting server on {host}:{port}")
        self.app.run(host=host, port=port, debug=False)

# Usage example
if __name__ == '__main__':
    # Replace with your actual public callback URL
    CALLBACK_URL = 'https://youtube-daily-summaries.onrender.com/webhook'
    
    # YouTube channel IDs to subscribe
    CHANNELS = [
        'UCHeJKJZ1U3cvzbP8d6ax6Uw',  # Domen
        'UC8XNl6AATTgd25MpIMA4S4A',  # CryptoCobra
        'UCtdDMDk_G0ZM5bnzf-_-WoQ',  # WhiteWidow
    ]

    websub = WebSubSubscriber()
    
    # Test subscription for each channel
    for channel_id in CHANNELS:
        print(f"\n{'='*50}")
        websub.test_subscription(CALLBACK_URL, channel_id)
        print(f"{'='*50}\n")