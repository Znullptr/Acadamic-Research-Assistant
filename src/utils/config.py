from dotenv import load_dotenv
import os


class Config:
    
    def __init__(self):
        load_dotenv(".env")
        # Required keys
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.google_cse_id = os.getenv("GOOGLE_CSE_ID")
        # Optional API Keys
        self.semantic_scholar_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        # Database Configuration
        self.chroma_db_path = "./chroma_db"
        # Processing Settings
        self.max_papers_per_search = 10
        self.ocr_language = "eng"
        self.log_level = "INFO"
        # Performance Settings
        self.request_delay = 1.0
        self.max_retries = 3
        self.timeout = 30
        self.chunk_size = 1000
        self.chunk_overlap = 200

config = Config()
