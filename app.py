import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import traceback
import datetime
import time
import threading
from flask import Flask, request, jsonify
from Summarizer import TranscriptProcessor

# Enhanced Logging Setup
def setup_logging():
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'application.log')
    
    # Configure logging with rotation
    handler = RotatingFileHandler(
        log_file, 
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5
    )
    
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    # Root logger configuration
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    
    return logging.getLogger(__name__)

# Global logger
logger = setup_logging()

# Global error handler
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """
    Catch any unhandled exceptions, log them, and attempt recovery
    """
    # Log the full traceback
    logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    
    # Optional: Send alert (e.g., email, Slack notification)
    try:
        error_message = f"""
        Unhandled Exception Detected
        Type: {exc_type.__name__}
        Message: {exc_value}
        
        Full Traceback:
        {traceback.format_exception(exc_type, exc_value, exc_traceback)}
        """
        logger.critical(error_message)
    except Exception as log_error:
        print(f"Error logging failed: {log_error}")
    
    # Attempt to restart the application
    try:
        logger.info("Attempting application recovery...")
        os.execv(sys.executable, ['python'] + sys.argv)
    except Exception as restart_error:
        logger.error(f"Application restart failed: {restart_error}")

# Set the global exception handler
sys.excepthook = global_exception_handler

# Initialize summarizer
summarizer = TranscriptProcessor()

app = Flask(__name__)

def extract_video_id(href):
    """Extract video ID from YouTube URL"""
    import re
    patterns = [
        r'v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'watch\?v=([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, href)
        if match:
            return match.group(1)
    
    return None

@app.route('/webhook', methods=['HEAD', 'POST'])
def youtube_webhook():
    try:
        # Log details of the incoming HEAD request
        if request.method == 'HEAD':
            logger.info(f"HEAD request received - Headers: {dict(request.headers)}")
            logger.info(f"HEAD request - Remote Address: {request.remote_addr}")
            logger.info(f"HEAD request - User Agent: {request.headers.get('User-Agent', 'No User-Agent')}")
            return '', 200
        
        payload = request.json
        
        # Log the received payload
        logger.info(f"Received webhook payload: {payload}")
        
        # Pass entire payload to Summarizer
        processing_result = summarizer.process_video(
            video_id=payload['items'][0]['id'].split(':')[-1], 
            channel_name=payload.get('title', 'Unknown Channel'), 
            video_title=payload['items'][0].get('title', 'Unknown Title')
        )
        
        # Check processing result
        if not processing_result['success']:
            return jsonify({
                "error": processing_result.get('error', 'Video processing failed'),
                "payload": payload
            }), 500
        
        return jsonify({
            "video_id": processing_result.get('video_id'),
            "channel": processing_result.get('channel_name'),
            "video_title": processing_result.get('video_title'),
            "transcript_length": len(processing_result.get('transcript', '')),
            "summary_length": len(processing_result.get('summary', '')),
            "cloud_url": processing_result.get('cloud_url'),
            "full_result": processing_result
        }), 200
    
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': 'Failed to process webhook'
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """
    Comprehensive health check endpoint
    """
    # Check if request is from UptimeRobot
    user_agent = request.headers.get('User-Agent', '')
    is_uptimerobot = 'UptimeRobot' in user_agent

    try:
        # Add any specific health checks here
        status_data = {
            'status': 'healthy',
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        # Only log non-UptimeRobot health checks
        if not is_uptimerobot:
            logger.info(f"Health check received: {status_data}")
        
        return jsonify(status_data), 200
    
    except Exception as e:
        # Always log actual errors
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

# If you want to add periodic health checks or background tasks
def background_health_monitor():
    """
    Periodically check and log application health
    """
    while True:
        try:
            # Example: Check some critical resources or perform maintenance
            logger.info("Performing background health check")
            time.sleep(300)  # Check every 5 minutes
        except Exception as e:
            logger.error(f"Background health monitor error: {e}")

# Start background monitor in a separate thread
health_monitor_thread = threading.Thread(target=background_health_monitor, daemon=True)
health_monitor_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
