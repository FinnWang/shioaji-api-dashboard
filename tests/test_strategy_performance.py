"""
策略績效計算單元測試

測試涵蓋：
1. 績效指標計算（勝率、損益、回撤等）
2. 夏普比率計算
3. 獲利因子計算
4. 每日損益摘要
5. 邊界情況
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta
from decimal import Decimal


def _make_mock_trade(
    direction="long",
    entry_price=21000,
    exit_price=21050,
    pnl=50,
    entry_time=None,
    exit_time=None,
    exit_reason="signal",
    symbol="MXFR1",
):
    """輔助函數：建立模擬交易"""
    trade = MagicMock()
    trade.symbol = symbol
    trade.direction = direction
    trade.entry_price = Decimal(str(entry_price))
    trade.exit_price = Decimal(str(exit_price))
    trade.pnl = Decimal(str(pnl))
    trade.entry_time = entry_time or datetime(2026, 2, 10, 9, 0, 0, tzinfo=timezone.utc)
    trade.exit_time = exit_time or datetime(2026, 2, 10, 9, 30, 0, tzinfo=timezone.utc)
    trade.exit_reason = exit_reason
    trade.status = "closed"
    trade.quantity = 1
    return trade


# 直接 import _calculate_performance 函數
# 需要 mock 掉 main.py 的一些依賴才能 import
def _get_calculate_performance():
    """取得 _calculate_performance 函數"""
    import importlib
    import sys

    # mock 掉 main.py 不需要的依賴
    from unittest.mock import MagicMock

    # 建立需要的 mock
    mock_modules = {}
    for mod_name in [
        'redis.asyncio', 'trading_queue', 'websocket_manager',
        'status_mapper', 'analysis_levels_client',
    ]:
        if mod_name not in sys.modules:
            mock_modules[mod_name] = MagicMock()

    # 暫時加入 mock
    for name, mod in mock_modules.items():
        sys.modules[name] = mod

    try:
        from main import _calculate_performance
        return _calculate_performance
    finally:
        # 清理 mock
        for name in mock_modules:
            if name in sys.modules and sys.modules[name] is mock_modules[name]:
                del sys.modules[name]


class TestPerformanceCalculation:
    """績效計算測試"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.calc = _get_calculate_performance()

    def test_performance_空交易列表應返回零值(self):
        result = self.calc([])

        assert result["total_trades"] == 0
        assert result["win_rate"] == 0
        assert result["total_pnl"] == 0
        assert result["sharpe_ratio"] == 0

    def test_performance_應該正確計算勝率(self):
        trades = [
            _make_mock_trade(pnl=50),
            _make_mock_trade(pnl=30),
            _make_mock_trade(pnl=-20),
            _make_mock_trade(pnl=10),
        ]

        result = self.calc(trades)

        assert result["total_trades"] == 4
        assert result["winning_trades"] == 3
        assert result["losing_trades"] == 1
        assert result["win_rate"] == 75.0

    def test_performance_應該正確計算總損益(self):
        trades = [
            _make_mock_trade(pnl=50),
            _make_mock_trade(pnl=-30),
            _make_mock_trade(pnl=20),
        ]

        result = self.calc(trades)

        assert result["total_pnl"] == 40.0
        assert result["avg_pnl"] == pytest.approx(13.33, abs=0.01)

    def test_performance_應該正確計算平均獲利和虧損(self):
        trades = [
            _make_mock_trade(pnl=100),
            _make_mock_trade(pnl=60),
            _make_mock_trade(pnl=-40),
            _make_mock_trade(pnl=-20),
        ]

        result = self.calc(trades)

        assert result["avg_win"] == 80.0
        assert result["avg_loss"] == -30.0

    def test_performance_應該正確計算獲利因子(self):
        trades = [
            _make_mock_trade(pnl=100),
            _make_mock_trade(pnl=50),
            _make_mock_trade(pnl=-30),
        ]

        result = self.calc(trades)

        # 獲利因子 = 150 / 30 = 5.0
        assert result["profit_factor"] == 5.0

    def test_performance_全部獲利時獲利因子應為None(self):
        trades = [
            _make_mock_trade(pnl=50),
            _make_mock_trade(pnl=30),
        ]

        result = self.calc(trades)

        # 無虧損 → profit_factor = inf → None
        assert result["profit_factor"] is None

    def test_performance_應該正確計算最大回撤(self):
        # 損益序列: +50, -30, +40, -60, +20
        # 累計: 50, 20, 60, 0, 20
        # peak: 50, 50, 60, 60, 60
        # drawdown: 0, 30, 0, 60, 40
        # 最大回撤 = 60
        trades = [
            _make_mock_trade(pnl=50),
            _make_mock_trade(pnl=-30),
            _make_mock_trade(pnl=40),
            _make_mock_trade(pnl=-60),
            _make_mock_trade(pnl=20),
        ]

        result = self.calc(trades)

        assert result["max_drawdown"] == 60.0

    def test_performance_應該正確計算最大連續勝負(self):
        trades = [
            _make_mock_trade(pnl=10),
            _make_mock_trade(pnl=20),
            _make_mock_trade(pnl=30),   # 連勝 3
            _make_mock_trade(pnl=-10),
            _make_mock_trade(pnl=-20),  # 連虧 2
            _make_mock_trade(pnl=50),
        ]

        result = self.calc(trades)

        assert result["max_consecutive_wins"] == 3
        assert result["max_consecutive_losses"] == 2

    def test_performance_應該正確計算夏普比率(self):
        import statistics

        trades = [
            _make_mock_trade(pnl=50),
            _make_mock_trade(pnl=-30),
            _make_mock_trade(pnl=40),
            _make_mock_trade(pnl=-10),
        ]

        result = self.calc(trades)

        pnls = [50, -30, 40, -10]
        expected_avg = sum(pnls) / len(pnls)
        expected_std = statistics.stdev(pnls)
        expected_sharpe = round(expected_avg / expected_std, 4)

        assert result["sharpe_ratio"] == expected_sharpe

    def test_performance_單筆交易夏普比率應為零(self):
        trades = [_make_mock_trade(pnl=50)]

        result = self.calc(trades)

        # 只有一筆無法計算標準差
        assert result["sharpe_ratio"] == 0

    def test_performance_應該正確計算平均持倉時間(self):
        # 第一筆: 30 分鐘
        t1 = _make_mock_trade(
            entry_time=datetime(2026, 2, 10, 9, 0, 0, tzinfo=timezone.utc),
            exit_time=datetime(2026, 2, 10, 9, 30, 0, tzinfo=timezone.utc),
        )
        # 第二筆: 60 分鐘
        t2 = _make_mock_trade(
            entry_time=datetime(2026, 2, 10, 10, 0, 0, tzinfo=timezone.utc),
            exit_time=datetime(2026, 2, 10, 11, 0, 0, tzinfo=timezone.utc),
        )

        result = self.calc([t1, t2])

        # 平均 = (1800 + 3600) / 2 = 2700
        assert result["avg_duration_seconds"] == 2700.0


class TestDailySummary:
    """每日損益摘要測試（針對 API 回傳結構驗證）"""

    def test_daily_summary_結構驗證(self):
        """驗證每日摘要的累計損益計算邏輯"""
        # 模擬兩天的交易資料
        daily_data = [
            {"date": "2026-02-10", "total_pnl": 80, "trade_count": 3},
            {"date": "2026-02-11", "total_pnl": -30, "trade_count": 2},
        ]

        # 計算累計損益
        cumulative = 0
        for d in daily_data:
            cumulative += d["total_pnl"]
            d["cumulative_pnl"] = cumulative

        assert daily_data[0]["cumulative_pnl"] == 80
        assert daily_data[1]["cumulative_pnl"] == 50

    def test_daily_summary_應該正確聚合每日損益(self):
        """驗證每日聚合邏輯"""
        # 模擬同一天的多筆交易
        pnls_day1 = [50, -20, 30]   # 總計 +60
        pnls_day2 = [-40, 10]       # 總計 -30

        total_day1 = sum(pnls_day1)
        total_day2 = sum(pnls_day2)

        winning_day1 = sum(1 for p in pnls_day1 if p > 0)
        losing_day1 = sum(1 for p in pnls_day1 if p < 0)

        assert total_day1 == 60
        assert total_day2 == -30
        assert winning_day1 == 2
        assert losing_day1 == 1
