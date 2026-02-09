"""
StrategyEngine 單元測試

測試涵蓋：
1. SMA 計算
2. 資料不足時的處理
3. 黃金交叉偵測（空倉/持空/持多）
4. 死亡交叉偵測（空倉/持多/持空）
5. 無交叉時不產生訊號
"""
import pytest

from strategy_engine import (
    StrategyEngine,
    SignalAction,
    PositionDirection,
    TradeSignal,
    calculate_sma,
)


class TestCalculateSMA:
    """SMA 計算測試"""

    def test_正常計算SMA(self):
        """測試: SMA 應正確計算平均值"""
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        assert calculate_sma(prices, 3) == 40.0  # (30+40+50)/3
        assert calculate_sma(prices, 5) == 30.0  # (10+20+30+40+50)/5

    def test_資料不足時應返回None(self):
        """測試: 資料不足時 SMA 應返回 None"""
        prices = [10.0, 20.0]
        assert calculate_sma(prices, 5) is None

    def test_剛好足夠資料(self):
        """測試: 資料剛好足夠時應正確計算"""
        prices = [10.0, 20.0, 30.0]
        assert calculate_sma(prices, 3) == 20.0


class TestStrategyEngine:
    """策略引擎測試"""

    def _make_engine(self, fast=3, slow=5):
        """建立小週期引擎方便測試"""
        return StrategyEngine(ma_fast_period=fast, ma_slow_period=slow)

    def _make_golden_cross_prices(self):
        """
        建構黃金交叉序列：MA3 從下方穿越 MA5

        設計：前幾根慢線高於快線，最後一根快線超越慢線
        """
        # 下降趨勢（slow > fast）
        prices = [100.0, 99.0, 98.0, 97.0, 96.0]
        # 突然反彈（fast > slow）
        prices.append(110.0)
        return prices

    def _make_death_cross_prices(self):
        """
        建構死亡交叉序列：MA3 從上方穿越 MA5

        設計：前幾根快線高於慢線，最後一根快線跌破慢線
        """
        # 上升趨勢（fast > slow）
        prices = [96.0, 97.0, 98.0, 99.0, 100.0]
        # 突然下跌（fast < slow）
        prices.append(90.0)
        return prices

    def test_資料不足時應返回NONE(self):
        """測試: 收盤價不足時應返回 NONE 訊號"""
        engine = self._make_engine(fast=3, slow=5)
        prices = [100.0, 101.0, 102.0]  # 需要 6 根

        signal = engine.evaluate(prices)

        assert signal.action == SignalAction.NONE
        assert "資料不足" in signal.reason

    def test_黃金交叉空倉時應做多(self):
        """測試: 黃金交叉 + 空倉 → BUY"""
        engine = self._make_engine(fast=3, slow=5)
        prices = self._make_golden_cross_prices()

        signal = engine.evaluate(prices, PositionDirection.FLAT)

        assert signal.action == SignalAction.BUY
        assert "黃金交叉" in signal.reason

    def test_黃金交叉持空時應平倉(self):
        """測試: 黃金交叉 + 持空 → CLOSE（準備反轉）"""
        engine = self._make_engine(fast=3, slow=5)
        prices = self._make_golden_cross_prices()

        signal = engine.evaluate(prices, PositionDirection.SHORT)

        assert signal.action == SignalAction.CLOSE
        assert "平空單" in signal.reason

    def test_黃金交叉持多時不重複進場(self):
        """測試: 黃金交叉 + 已持多 → NONE"""
        engine = self._make_engine(fast=3, slow=5)
        prices = self._make_golden_cross_prices()

        signal = engine.evaluate(prices, PositionDirection.LONG)

        assert signal.action == SignalAction.NONE
        assert "已持有多單" in signal.reason

    def test_死亡交叉空倉時應做空(self):
        """測試: 死亡交叉 + 空倉 → SELL"""
        engine = self._make_engine(fast=3, slow=5)
        prices = self._make_death_cross_prices()

        signal = engine.evaluate(prices, PositionDirection.FLAT)

        assert signal.action == SignalAction.SELL
        assert "死亡交叉" in signal.reason

    def test_死亡交叉持多時應平倉(self):
        """測試: 死亡交叉 + 持多 → CLOSE（準備反轉）"""
        engine = self._make_engine(fast=3, slow=5)
        prices = self._make_death_cross_prices()

        signal = engine.evaluate(prices, PositionDirection.LONG)

        assert signal.action == SignalAction.CLOSE
        assert "平多單" in signal.reason

    def test_死亡交叉持空時不重複進場(self):
        """測試: 死亡交叉 + 已持空 → NONE"""
        engine = self._make_engine(fast=3, slow=5)
        prices = self._make_death_cross_prices()

        signal = engine.evaluate(prices, PositionDirection.SHORT)

        assert signal.action == SignalAction.NONE
        assert "已持有空單" in signal.reason

    def test_無交叉時應返回NONE(self):
        """測試: 無交叉時應返回 NONE"""
        engine = self._make_engine(fast=3, slow=5)
        # 穩定上升，不會交叉
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]

        signal = engine.evaluate(prices, PositionDirection.FLAT)

        assert signal.action == SignalAction.NONE

    def test_signal應包含MA值(self):
        """測試: 訊號應包含 MA 快線和慢線數值"""
        engine = self._make_engine(fast=3, slow=5)
        prices = self._make_golden_cross_prices()

        signal = engine.evaluate(prices, PositionDirection.FLAT)

        assert signal.ma_fast > 0
        assert signal.ma_slow > 0

    def test_預設參數MA5_MA20(self):
        """測試: 預設引擎使用 MA5/MA20"""
        engine = StrategyEngine()
        assert engine.ma_fast_period == 5
        assert engine.ma_slow_period == 20
