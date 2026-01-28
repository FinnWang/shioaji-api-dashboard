"""
統一配置管理

使用 Pydantic Settings 集中管理所有環境變數，
避免在多個檔案中重複讀取 os.getenv()。

使用方式：
    from config import settings

    api_key = settings.api_key
    redis_url = settings.redis_url
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """應用程式設定，從環境變數讀取"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Shioaji API 認證
    api_key: Optional[str] = None
    secret_key: Optional[str] = None

    # CA 憑證（正式環境下單需要）
    ca_path: Optional[str] = None
    ca_password: Optional[str] = None

    # 資料庫
    database_url: str = "postgresql://postgres:postgres@localhost:5432/shioaji_dashboard"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API 認證金鑰
    auth_key: str = "changeme"

    # 支援的商品（逗號分隔）
    supported_futures: str = "MXF,TXF"
    supported_options: str = "TXO"

    @property
    def supported_futures_list(self) -> list[str]:
        """取得支援的期貨商品列表"""
        return [f.strip() for f in self.supported_futures.split(",") if f.strip()]

    @property
    def supported_options_list(self) -> list[str]:
        """取得支援的選擇權商品列表"""
        return [o.strip() for o in self.supported_options.split(",") if o.strip()]

    def validate_shioaji_credentials(self) -> bool:
        """檢查 Shioaji 認證資訊是否完整"""
        return bool(self.api_key and self.secret_key)

    def validate_ca_credentials(self) -> bool:
        """檢查 CA 憑證資訊是否完整"""
        return bool(self.ca_path and self.ca_password)


@lru_cache
def get_settings() -> Settings:
    """
    取得設定單例（使用快取避免重複讀取）

    Returns:
        Settings: 應用程式設定
    """
    return Settings()


# 方便直接 import 使用
settings = get_settings()
