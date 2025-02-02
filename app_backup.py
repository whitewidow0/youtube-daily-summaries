import os
import json
import logging
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.cloud import pubsub_v1
from Summarizer import TranscriptProcessor
from cloud_storage import CloudStorageManager
import xml.etree.ElementTree as ET
import re
import time

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Rest of the original app.py content will be copied here
