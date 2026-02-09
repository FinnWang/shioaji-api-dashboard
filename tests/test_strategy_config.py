"""
StrategySettings 單元測試

測試涵蓋：
1. 預設值正確性
2. 環境變數覆蓋
3. 參數類型轉換
"""
import pytest
from unittest.mock import patch


class TestStrategySettings:
    """StrategySettings 設定測試"""

    def test_預設值應該正確(self):
        """測試: 所有預設值應該符合策略規格"""
        from strategy_config import StrategySettings
        settings = StrategySettings()

        assert settings.symbol == "MXFR1"
        assert settings.kline_interval_minutes == 3
        assert settings.ma_fast_period == 5
        assert settings.ma_slow_period == 20
        assert settings.quantity == 2
        assert settings.stop_loss_points == 50
        assert settings.trailing_stop_points == 30
        assert settings.daily_max_loss_points == 200
        assert settings.daily_max_trades == 10
        assert settings.simulation is True
        assert settings.state_persist_interval == 10
        assert settings.position_sync_interval == 60

    def test_環境變數應該能覆蓋預設值(self):
        """測試: 透過 STRATEGY_ 前綴的環境變數覆蓋設定"""
        from strategy_config import StrategySettings
        env = {
            "STRATEGY_SYMBOL": "TXFR1",
            "STRATEGY_QUANTITY": "5",
            "STRATEGY_STOP_LOSS_POINTS": "100",
            "STRATEGY_SIMULATION": "false",
        }
        with patch.dict("os.environ", env):
            settings = StrategySettings()

        assert settings.symbol == "TXFR1"
        assert settings.quantity == 5
        assert settings.stop_loss_points == 100
        assert settings.simulation is False

    def test_kline_interval_應該可自訂(self):
        """測試: K 線週期可以透過環境變數修改"""
        from strategy_config import StrategySettings
        with patch.dict("os.environ", {"STRATEGY_KLINE_INTERVAL_MINUTES": "5"}):
            settings = StrategySettings()

        assert settings.kline_interval_minutes == 5

    def test_ma_週期應該可自訂(self):
        """測試: 均線週期可以透過環境變數修改"""
        from strategy_config import StrategySettings
        env = {
            "STRATEGY_MA_FAST_PERIOD": "10",
            "STRATEGY_MA_SLOW_PERIOD": "30",
        }
        with patch.dict("os.environ", env):
            settings = StrategySettings()

        assert settings.ma_fast_period == 10
        assert settings.ma_slow_period == 30

    def test_daily_max_trades_應該可自訂(self):
        """測試: 每日最大交易次數可以透過環境變數修改"""
        from strategy_config import StrategySettings
        with patch.dict("os.environ", {"STRATEGY_DAILY_MAX_TRADES": "20"}):
            settings = StrategySettings()

        assert settings.daily_max_trades == 20

    def test_redis_url_應該可自訂(self):
        """測試: Redis URL 可以透過環境變數修改"""
        from strategy_config import StrategySettings
        with patch.dict("os.environ", {"STRATEGY_REDIS_URL": "redis://custom:6380/1"}):
            settings = StrategySettings()

        assert settings.redis_url == "redis://custom:6380/1"
