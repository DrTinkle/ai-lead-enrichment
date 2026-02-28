# app/config.py

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ABSTRACT_API_KEY: str = os.getenv("ABSTRACT_API_KEY", "")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")


settings = Settings()