import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import traceback
import datetime
import time
import threading
from flask import Flask, request, jsonify
from io import StringIO
from Summarizer import process_video_from_payload

# Enhanced Logging Setup
def setup_logging():
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'application.log')
    
    # Configure logging with rotation for file logs
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
    
    # Root logger configuration for file logs
    logging.getLogger().addHandler(handler)

    # Stream handler to print to stdout for Render logs
    stream_handler = logging.StreamHandler(sys.stdout)  # Log to stdout for Render
    stream_handler.setFormatter(formatter)
    logging.getLogger().addHandler(stream_handler)

    logging.getLogger().setLevel(logging.DEBUG)  # Set the log level to DEBUG or INFO
    return logging.getLogger(__name__)

# Global logger
logger = setup_logging()

# In-memory log capture (Optional)
log_stream = StringIO()
log_stream_handler = logging.StreamHandler(log_stream)
log_stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(log_stream_handler)

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

app = Flask(__name__)

# Input validation for payload data
def validate_payload(payload):
    if not isinstance(payload, dict):
        logger.warning("Invalid payload format: Expected a dictionary")
        return False
    required_keys = ['video_id', 'title', 'url']  # Example required keys
    for key in required_keys:
        if key not in payload:
            logger.warning(f"Missing required key: {key}")
            return False
    return True

@app.route('/webhook', methods=['HEAD', 'POST'])
def youtube_webhook():
    # Log details of the incoming HEAD request
    if request.method == 'HEAD':
        logger.info(f"HEAD request received - Headers: {dict(request.headers)}")
        logger.info(f"HEAD request - Remote Address: {request.remote_addr}")
        logger.info(f"HEAD request - User Agent: {request.headers.get('User-Agent', 'No User-Agent')}")
        return '', 200
    
    payload = request.json
    logger.debug(f"Incoming payload: {payload}")  # Log payload at debug level
    
    # Input validation - print warnings if invalid but continue
    if not validate_payload(payload):
        logger.warning("Invalid payload received, continuing processing with limited information.")
    
    try:
        # Process the payload with video summary
        result = process_video_from_payload(payload)
        logger.debug(f"Processed payload result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error processing video payload: {e}")
        return jsonify({'error': 'Failed to process payload'}), 500

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
