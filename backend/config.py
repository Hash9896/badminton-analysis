import os
from typing import Optional


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    return value


class Settings:
    def __init__(self) -> None:
        # Required
        self.openai_api_key: Optional[str] = get_env("OPENAI_API_KEY")

        # Paths
        # Base directory for LanceDB storage (created if missing)
        self.vector_db_dir: str = get_env(
            "VECTOR_DB_DIR",
            os.path.join(os.path.dirname(__file__), "vector_store"),
        )
        # Root data directory that contains match folders like Aikya/1
        self.data_root_dir: str = get_env(
            "DATA_ROOT_DIR",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        )

        # Model choices
        self.embedding_model: str = get_env("EMBEDDING_MODEL", "text-embedding-3-small")
        self.chat_model: str = get_env("CHAT_MODEL", "gpt-4.1")

        # CORS
        self.cors_origins: str = get_env("CORS_ORIGINS", "http://localhost:5173")

        # S3 Configuration
        self.s3_bucket: str = get_env("S3_BUCKET", "badminton-analysis-data")
        self.s3_region: str = get_env("S3_REGION", "ap-south-1")
        self.aws_access_key_id: Optional[str] = get_env("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key: Optional[str] = get_env("AWS_SECRET_ACCESS_KEY")


settings = Settings()


