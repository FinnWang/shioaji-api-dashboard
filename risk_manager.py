"""
風險管理器

管理交易的風險控制，包括：
- 固定停損：進場後固定點數停損
- 追蹤停損：獲利時跟隨移動停損線
- 每日虧損限制：累計虧損達上限自動停止交易
- 每日交易次數上限

使用方式：
    rm = RiskManager(stop_loss=50, trailing_stop=30, daily_max_loss=200)
    should_stop = rm.check_stop_loss(current_price)
"""
import json
import logging
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class StopReason(str, Enum):
    """停損原因"""
    FIXED_STOP_LOSS = "fixed_stop_loss"
    TRAILING_STOP = "trailing_stop"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    DAILY_TRADE_LIMIT = "daily_trade_limit"


@dataclass
class RiskState:
    """
    風控狀態（可序列化，用於持久化）

    追蹤每日累計損益、交易次數和停損線位置。
    """
    # 當前持倉資訊
    entry_price: float = 0.0
    position_direction: str = "flat"  # "long", "short", "flat"

    # 停損線
    stop_loss_price: float = 0.0
    trailing_stop_price: float = 0.0

    # 追蹤停損用的最有利價格
    best_price: float = 0.0

    # 每日統計
    daily_pnl: float = 0.0
    daily_trade_count: int = 0

    # 是否已因風控停止交易
    trading_halted: bool = False
    halt_reason: str = ""

    def to_json(self) -> str:
        """序列化為 JSON"""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "RiskState":
        """從 JSON 反序列化"""
        return cls(**json.loads(data))


class RiskManager:
    """
    風險管理器

    Args:
        stop_loss_points: 固定停損點數
        trailing_stop_points: 追蹤停損點數
        daily_max_loss_points: 每日最大虧損點數
        daily_max_trades: 每日最大交易次數
    """

    def __init__(
        self,
        stop_loss_points: int = 50,
        trailing_stop_points: int = 30,
        daily_max_loss_points: int = 200,
        daily_max_trades: int = 10,
    ):
        self.stop_loss_points = stop_loss_points
        self.trailing_stop_points = trailing_stop_points
        self.daily_max_loss_points = daily_max_loss_points
        self.daily_max_trades = daily_max_trades

        self.state = RiskState()

    def on_entry(self, entry_price: float, direction: str) -> None:
        """
        建立新持倉時更新風控狀態

        設定固定停損線和追蹤停損的初始最有利價格。

        Args:
            entry_price: 進場價格
            direction: 持倉方向 ("long" 或 "short")
        """
        self.state.entry_price = entry_price
        self.state.position_direction = direction
        self.state.best_price = entry_price
        self.state.daily_trade_count += 1

        if direction == "long":
            self.state.stop_loss_price = entry_price - self.stop_loss_points
            self.state.trailing_stop_price = entry_price - self.trailing_stop_points
        elif direction == "short":
            self.state.stop_loss_price = entry_price + self.stop_loss_points
            self.state.trailing_stop_price = entry_price + self.trailing_stop_points

        logger.info(
            f"風控設定: 方向={direction} 進場={entry_price} "
            f"固定停損={self.state.stop_loss_price} "
            f"追蹤停損={self.state.trailing_stop_price}"
        )

    def on_exit(self, exit_price: float) -> float:
        """
        平倉時更新每日損益

        Args:
            exit_price: 出場價格

        Returns:
            本次交易損益（點數）
        """
        if self.state.position_direction == "long":
            pnl = exit_price - self.state.entry_price
        elif self.state.position_direction == "short":
            pnl = self.state.entry_price - exit_price
        else:
            pnl = 0.0

        self.state.daily_pnl += pnl
        logger.info(f"平倉損益: {pnl:.1f} 點，每日累計: {self.state.daily_pnl:.1f} 點")

        # 重設持倉相關狀態
        self.state.entry_price = 0.0
        self.state.position_direction = "flat"
        self.state.stop_loss_price = 0.0
        self.state.trailing_stop_price = 0.0
        self.state.best_price = 0.0

        # 檢查是否觸及每日虧損限制
        if self.state.daily_pnl <= -self.daily_max_loss_points:
            self.state.trading_halted = True
            self.state.halt_reason = StopReason.DAILY_LOSS_LIMIT.value
            logger.warning(
                f"每日虧損達上限: {self.state.daily_pnl:.1f} 點，停止交易"
            )

        return pnl

    def check_stop_loss(self, current_price: float) -> Optional[StopReason]:
        """
        檢查是否觸發停損

        先更新追蹤停損線（只往有利方向移動），再檢查是否觸發。

        Args:
            current_price: 當前價格

        Returns:
            觸發的停損原因，未觸發返回 None
        """
        if self.state.position_direction == "flat":
            return None

        # 更新追蹤停損
        self._update_trailing_stop(current_price)

        direction = self.state.position_direction

        # 檢查固定停損
        if direction == "long" and current_price <= self.state.stop_loss_price:
            logger.warning(
                f"固定停損觸發: 價格 {current_price} <= {self.state.stop_loss_price}"
            )
            return StopReason.FIXED_STOP_LOSS

        if direction == "short" and current_price >= self.state.stop_loss_price:
            logger.warning(
                f"固定停損觸發: 價格 {current_price} >= {self.state.stop_loss_price}"
            )
            return StopReason.FIXED_STOP_LOSS

        # 檢查追蹤停損
        if direction == "long" and current_price <= self.state.trailing_stop_price:
            logger.warning(
                f"追蹤停損觸發: 價格 {current_price} <= {self.state.trailing_stop_price}"
            )
            return StopReason.TRAILING_STOP

        if direction == "short" and current_price >= self.state.trailing_stop_price:
            logger.warning(
                f"追蹤停損觸發: 價格 {current_price} >= {self.state.trailing_stop_price}"
            )
            return StopReason.TRAILING_STOP

        return None

    def _update_trailing_stop(self, current_price: float) -> None:
        """
        更新追蹤停損線

        只往有利方向移動：
        - 多單：價格創新高時，停損線上移
        - 空單：價格創新低時，停損線下移
        """
        direction = self.state.position_direction

        if direction == "long" and current_price > self.state.best_price:
            self.state.best_price = current_price
            new_trailing = current_price - self.trailing_stop_points
            if new_trailing > self.state.trailing_stop_price:
                self.state.trailing_stop_price = new_trailing
                logger.debug(f"追蹤停損上移: {self.state.trailing_stop_price}")

        elif direction == "short" and current_price < self.state.best_price:
            self.state.best_price = current_price
            new_trailing = current_price + self.trailing_stop_points
            if new_trailing < self.state.trailing_stop_price:
                self.state.trailing_stop_price = new_trailing
                logger.debug(f"追蹤停損下移: {self.state.trailing_stop_price}")

    def can_trade(self) -> tuple[bool, str]:
        """
        檢查是否允許開新倉

        Returns:
            (是否允許, 原因)
        """
        if self.state.trading_halted:
            return False, f"交易已停止: {self.state.halt_reason}"

        if self.state.daily_trade_count >= self.daily_max_trades:
            self.state.trading_halted = True
            self.state.halt_reason = StopReason.DAILY_TRADE_LIMIT.value
            return False, f"每日交易次數已達上限 ({self.daily_max_trades})"

        return True, "允許交易"

    def reset_daily(self) -> None:
        """重設每日統計（新交易日開始時呼叫）"""
        self.state.daily_pnl = 0.0
        self.state.daily_trade_count = 0
        self.state.trading_halted = False
        self.state.halt_reason = ""
        logger.info("每日風控統計已重設")

    def get_state(self) -> RiskState:
        """取得當前風控狀態"""
        return self.state

    def restore_state(self, state: RiskState) -> None:
        """從持久化狀態恢復"""
        self.state = state
        logger.info(f"風控狀態已恢復: daily_pnl={state.daily_pnl}")
