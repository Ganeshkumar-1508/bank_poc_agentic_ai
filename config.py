import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama3-8b-instruct")
WEBSITE_SEARCH_MODEL = os.getenv("WEBSITE_SEARCH_MODEL", NVIDIA_MODEL)
WEBSITE_SEARCH_API_KEY = os.getenv("WEBSITE_SEARCH_API_KEY", NVIDIA_API_KEY)
WEBSITE_SEARCH_BASE_URL = os.getenv("WEBSITE_SEARCH_BASE_URL", NVIDIA_BASE_URL)

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
CSV_PATH = os.getenv("CSV_PATH", os.path.join(DATA_DIR, "fd_rates.csv"))

SOURCE_NAME = os.getenv("SOURCE_NAME", "BankBazaar")
SOURCE_URL = os.getenv("SOURCE_URL", "https://www.bankbazaar.com/fixed-deposit-rate.html")
FALLBACK_SOURCE_NAME = os.getenv("FALLBACK_SOURCE_NAME", "HDFC Bank")
FALLBACK_SOURCE_URL = os.getenv("FALLBACK_SOURCE_URL", "https://www.hdfc.bank.in/fixed-deposit/fd-interest-rate")
TOP_PROVIDERS = int(os.getenv("TOP_PROVIDERS", "10"))
