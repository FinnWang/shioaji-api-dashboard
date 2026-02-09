"""
MA 均線交叉策略引擎

計算 SMA（簡單移動平均），根據 MA_fast / MA_slow 的交叉
產生交易訊號。

訊號邏輯：
- 黃金交叉（MA_fast 上穿 MA_slow）→ 做多
- 死亡交叉（MA_fast 下穿 MA_slow）→ 做空
- 根據當前持倉方向決定進場/平倉/反轉

使用方式：
    engine = StrategyEngine(ma_fast_period=5, ma_slow_period=20)
    signal = engine.on_kline_complete(close_prices, current_position)
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class SignalAction(str, Enum):
    """交易訊號動作"""
    BUY = "Buy"       # 做多進場
    SELL = "Sell"      # 做空進場
    CLOSE = "close"    # 平倉
    NONE = "none"      # 無動作


class PositionDirection(str, Enum):
    """持倉方向"""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class TradeSignal:
    """交易訊號"""
    action: SignalAction
    reason: str
    ma_fast: float = 0.0
    ma_slow: float = 0.0


def calculate_sma(prices: list[float], period: int) -> Optional[float]:
    """
    計算簡單移動平均 (SMA)

    Args:
        prices: 收盤價列表（從舊到新）
        period: 計算週期

    Returns:
        SMA 值，資料不足時返回 None
    """
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


class StrategyEngine:
    """
    MA 均線交叉策略引擎

    Args:
        ma_fast_period: 快線週期（預設 5）
        ma_slow_period: 慢線週期（預設 20）
    """

    def __init__(self, ma_fast_period: int = 5, ma_slow_period: int = 20):
        self.ma_fast_period = ma_fast_period
        self.ma_slow_period = ma_slow_period

    def evaluate(
        self,
        close_prices: list[float],
        current_position: PositionDirection = PositionDirection.FLAT,
    ) -> TradeSignal:
        """
        根據收盤價序列和當前持倉評估策略訊號

        需要至少 ma_slow_period + 1 根 K 線才能判斷交叉。
        比較前後兩根 K 線的 MA_fast - MA_slow 差值來偵測交叉。

        Args:
            close_prices: 收盤價列表（從舊到新）
            current_position: 當前持倉方向

        Returns:
            TradeSignal 交易訊號
        """
        min_required = self.ma_slow_period + 1
        if len(close_prices) < min_required:
            return TradeSignal(
                action=SignalAction.NONE,
                reason=f"資料不足（需要 {min_required} 根，目前 {len(close_prices)} 根）",
            )

        # 計算當前和前一根 K 線的 MA
        curr_fast = calculate_sma(close_prices, self.ma_fast_period)
        curr_slow = calculate_sma(close_prices, self.ma_slow_period)

        prev_prices = close_prices[:-1]
        prev_fast = calculate_sma(prev_prices, self.ma_fast_period)
        prev_slow = calculate_sma(prev_prices, self.ma_slow_period)

        if any(v is None for v in [curr_fast, curr_slow, prev_fast, prev_slow]):
            return TradeSignal(
                action=SignalAction.NONE,
                reason="均線計算失敗",
            )

        curr_diff = curr_fast - curr_slow
        prev_diff = prev_fast - prev_slow

        logger.info(
            f"均線評估: MA{self.ma_fast_period}={curr_fast:.2f} "
            f"MA{self.ma_slow_period}={curr_slow:.2f} "
            f"prev_diff={prev_diff:.2f} curr_diff={curr_diff:.2f}"
        )

        # 黃金交叉：prev_diff <= 0 且 curr_diff > 0
        if prev_diff <= 0 and curr_diff > 0:
            return self._handle_golden_cross(
                current_position, curr_fast, curr_slow
            )

        # 死亡交叉：prev_diff >= 0 且 curr_diff < 0
        if prev_diff >= 0 and curr_diff < 0:
            return self._handle_death_cross(
                current_position, curr_fast, curr_slow
            )

        return TradeSignal(
            action=SignalAction.NONE,
            reason="無交叉訊號",
            ma_fast=curr_fast,
            ma_slow=curr_slow,
        )

    def _handle_golden_cross(
        self,
        current_position: PositionDirection,
        ma_fast: float,
        ma_slow: float,
    ) -> TradeSignal:
        """處理黃金交叉訊號"""
        if current_position == PositionDirection.SHORT:
            # 空單 → 先平倉（反轉由外部處理：平倉 + 開多）
            return TradeSignal(
                action=SignalAction.CLOSE,
                reason="黃金交叉，平空單準備反轉做多",
                ma_fast=ma_fast,
                ma_slow=ma_slow,
            )
        elif current_position == PositionDirection.FLAT:
            return TradeSignal(
                action=SignalAction.BUY,
                reason="黃金交叉，做多進場",
                ma_fast=ma_fast,
                ma_slow=ma_slow,
            )
        else:
            # 已持有多單，不重複進場
            return TradeSignal(
                action=SignalAction.NONE,
                reason="黃金交叉，但已持有多單",
                ma_fast=ma_fast,
                ma_slow=ma_slow,
            )

    def _handle_death_cross(
        self,
        current_position: PositionDirection,
        ma_fast: float,
        ma_slow: float,
    ) -> TradeSignal:
        """處理死亡交叉訊號"""
        if current_position == PositionDirection.LONG:
            # 多單 → 先平倉（反轉由外部處理：平倉 + 開空）
            return TradeSignal(
                action=SignalAction.CLOSE,
                reason="死亡交叉，平多單準備反轉做空",
                ma_fast=ma_fast,
                ma_slow=ma_slow,
            )
        elif current_position == PositionDirection.FLAT:
            return TradeSignal(
                action=SignalAction.SELL,
                reason="死亡交叉，做空進場",
                ma_fast=ma_fast,
                ma_slow=ma_slow,
            )
        else:
            # 已持有空單，不重複進場
            return TradeSignal(
                action=SignalAction.NONE,
                reason="死亡交叉，但已持有空單",
                ma_fast=ma_fast,
                ma_slow=ma_slow,
            )
