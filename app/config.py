import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Required
    OPENAI_API_KEY: str    = os.getenv("OPENAI_API_KEY", "")

    # Optional - free tier enrichment sources
    ABSTRACT_API_KEY: str  = os.getenv("ABSTRACT_API_KEY", "")
    NEWS_API_KEY: str      = os.getenv("NEWS_API_KEY", "")
    ADZUNA_APP_ID: str     = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY: str    = os.getenv("ADZUNA_APP_KEY", "")
    GITHUB_TOKEN: str      = os.getenv("GITHUB_TOKEN", "")

    # Feature flags
    GDELT_ENABLED: str     = os.getenv("GDELT_ENABLED", "true")


settings = Settings()
