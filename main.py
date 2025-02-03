import base64
import json
import logging
import os
import requests

def handle_pubsub(event, context):
    """
    Cloud Function to handle Pub/Sub messages for YouTube video processing.
    
    Args:
        event (dict): Event payload.
        context (google.cloud.functions.Context): Metadata for the event.
    """
    try:
        # Logging configuration
        logging.basicConfig(level=logging.INFO, 
                            format='%(asctime)s - %(levelname)s: %(message)s')
        
        # Validate Pub/Sub message
        if not event or 'data' not in event:
            logging.warning("Invalid or empty Pub/Sub message")
            return
        
        # Decode the base64 encoded message
        pubsub_message = base64.b64decode(event['data']).decode('utf-8')
        logging.info(f"Decoded Pub/Sub message: {pubsub_message}")
        
        # Parse the message
        try:
            message_data = json.loads(pubsub_message)
            logging.info(f"Parsed message data: {json.dumps(message_data, indent=2)}")
        except json.JSONDecodeError:
            logging.error(f"Failed to parse JSON: {pubsub_message}")
            return
        
        # Send to render endpoint
        render_endpoint = os.environ.get('RENDER_ENDPOINT', 'https://your-default-render-endpoint.com/render')
        try:
            response = requests.post(render_endpoint, json=message_data)
            response.raise_for_status()
            logging.info(f"Successfully sent message to render endpoint: {response.text}")
        except requests.RequestException as e:
            logging.error(f"Failed to send message to render endpoint: {str(e)}")
            return
        
        return "Success"
    
    except Exception as e:
        logging.error(f"Error processing Pub/Sub message: {str(e)}")
        raise

# Optional health check endpoint
def health_check(request):
    """Simple health check endpoint for the Cloud Function."""
    return "OK", 200
