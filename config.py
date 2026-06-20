import os
from dotenv import load_dotenv

load_dotenv()

BITGET_BASE_URL = "https://api.bitget.com"

# Default/public-data keys (optional — only needed for endpoints that require auth)
BITGET_API_KEY = os.getenv("BITGET_API_KEY", "")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET", "")
BITGET_PASSPHRASE = os.getenv("BITGET_PASSPHRASE", "")

# Used to encrypt user-submitted API keys before storing them
SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-this-in-production")

# Allowed frontend origin for CORS — set this to your deployed frontend URL
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")
