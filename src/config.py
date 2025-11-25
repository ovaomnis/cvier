"""
Configuration management for GitHub PR Fetcher
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class Config:
    """Configuration manager for application settings"""

    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()

        self.github_token: Optional[str] = os.getenv("GITHUB_TOKEN")
        self.default_output_dir: str = os.getenv("OUTPUT_DIR", "./github_prs")
        self.cache_enabled: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
        self.cache_dir: str = os.getenv("CACHE_DIR", "./.cache")

    def get_token(self) -> str:
        """Get GitHub token or raise error if not set"""
        if not self.github_token:
            raise ValueError(
                "GitHub token not found. Please set GITHUB_TOKEN in .env file or environment variable."
            )
        return self.github_token

    def set_token(self, token: str):
        """Set GitHub token"""
        self.github_token = token

    def get_output_dir(self) -> Path:
        """Get output directory as Path object"""
        return Path(self.default_output_dir)

    def set_output_dir(self, path: str):
        """Set output directory"""
        self.default_output_dir = path

    def get_cache_dir(self) -> Path:
        """Get cache directory as Path object"""
        return Path(self.cache_dir)

    def is_cache_enabled(self) -> bool:
        """Check if caching is enabled"""
        return self.cache_enabled


# Global config instance
config = Config()