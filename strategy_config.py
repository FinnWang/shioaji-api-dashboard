"""
策略引擎設定

使用 Pydantic Settings 管理所有策略參數，
所有環境變數使用 STRATEGY_ 前綴。

使用方式：
    from strategy_config import strategy_settings

    symbol = strategy_settings.symbol
    ma_fast = strategy_settings.ma_fast_period
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrategySettings(BaseSettings):
    """策略引擎設定，從環境變數讀取（前綴 STRATEGY_）"""

    model_config = SettingsConfigDict(
        env_prefix="STRATEGY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 交易商品
    symbol: str = "MXFR1"

    # K 線週期（分鐘）
    kline_interval_minutes: int = 3

    # 均線參數
    ma_fast_period: int = 5
    ma_slow_period: int = 20

    # 下單口數
    quantity: int = 2

    # 停損設定（點數）
    stop_loss_points: int = 50
    trailing_stop_points: int = 30

    # 每日風控
    daily_max_loss_points: int = 200
    daily_max_trades: int = 10

    # 模擬/實盤切換
    simulation: bool = True

    # 狀態持久化間隔（秒）
    state_persist_interval: int = 10

    # 券商持倉同步間隔（秒）
    position_sync_interval: int = 60

    # Redis 設定（繼承自主系統或獨立設定）
    redis_url: str = "redis://localhost:6379/0"


strategy_settings = StrategySettings()
