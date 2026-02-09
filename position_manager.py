"""
持倉管理器

追蹤策略引擎的邏輯持倉（方向、成本價、口數、未實現損益），
並可定期與券商端同步。

使用方式：
    pm = PositionManager(symbol="MXFR1", quantity=2)
    pm.open_position("long", 21000.0)
    pm.close_position(21050.0)
"""
import json
import logging
import time
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PositionState:
    """
    持倉狀態（可序列化）
    """
    direction: str = "flat"  # "long", "short", "flat"
    entry_price: float = 0.0
    quantity: int = 0
    unrealized_pnl: float = 0.0
    last_sync_time: float = 0.0

    def to_json(self) -> str:
        """序列化為 JSON"""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "PositionState":
        """從 JSON 反序列化"""
        return cls(**json.loads(data))


class PositionManager:
    """
    持倉管理器

    Args:
        symbol: 交易商品代碼
        quantity: 每次交易口數
        sync_interval: 券商同步間隔（秒）
    """

    def __init__(
        self,
        symbol: str = "MXFR1",
        quantity: int = 2,
        sync_interval: int = 60,
    ):
        self.symbol = symbol
        self.default_quantity = quantity
        self.sync_interval = sync_interval

        self.state = PositionState()

    @property
    def direction(self) -> str:
        """當前持倉方向"""
        return self.state.direction

    @property
    def is_flat(self) -> bool:
        """是否無持倉"""
        return self.state.direction == "flat"

    @property
    def entry_price(self) -> float:
        """進場價格"""
        return self.state.entry_price

    def open_position(self, direction: str, entry_price: float) -> None:
        """
        建立新持倉

        Args:
            direction: 持倉方向 ("long" 或 "short")
            entry_price: 進場價格
        """
        self.state.direction = direction
        self.state.entry_price = entry_price
        self.state.quantity = self.default_quantity
        self.state.unrealized_pnl = 0.0

        logger.info(
            f"開倉: {direction} {self.symbol} x{self.default_quantity} @ {entry_price}"
        )

    def close_position(self, exit_price: float) -> float:
        """
        平倉

        Args:
            exit_price: 出場價格

        Returns:
            實現損益（點數）
        """
        if self.state.direction == "long":
            pnl = exit_price - self.state.entry_price
        elif self.state.direction == "short":
            pnl = self.state.entry_price - exit_price
        else:
            pnl = 0.0

        logger.info(
            f"平倉: {self.state.direction} {self.symbol} "
            f"@ {exit_price} 損益={pnl:.1f} 點"
        )

        self.state.direction = "flat"
        self.state.entry_price = 0.0
        self.state.quantity = 0
        self.state.unrealized_pnl = 0.0

        return pnl

    def update_unrealized_pnl(self, current_price: float) -> float:
        """
        更新未實現損益

        Args:
            current_price: 當前價格

        Returns:
            未實現損益（點數）
        """
        if self.state.direction == "long":
            self.state.unrealized_pnl = current_price - self.state.entry_price
        elif self.state.direction == "short":
            self.state.unrealized_pnl = self.state.entry_price - current_price
        else:
            self.state.unrealized_pnl = 0.0

        return self.state.unrealized_pnl

    def should_sync(self) -> bool:
        """
        檢查是否需要與券商同步

        Returns:
            是否需要同步
        """
        if self.state.last_sync_time == 0:
            return True
        return (time.time() - self.state.last_sync_time) >= self.sync_interval

    def sync_with_broker(self, broker_positions: list[dict]) -> bool:
        """
        與券商持倉同步

        從券商回傳的持倉資料中，找到符合 symbol 的持倉進行比對。
        如果不一致，以券商為準。

        Args:
            broker_positions: 券商持倉資料列表

        Returns:
            是否發生同步修正
        """
        self.state.last_sync_time = time.time()

        # 從券商持倉中找到匹配的商品
        matched = None
        for pos in broker_positions:
            code = pos.get("code", "")
            # 支援別名對應（MXFR1 匹配 MXF 開頭的合約）
            if code == self.symbol or (
                self.symbol.endswith("R1") and code.startswith(self.symbol[:-2])
            ):
                matched = pos
                break

        if matched is None:
            # 券商無持倉
            if self.state.direction != "flat":
                logger.warning(
                    f"同步修正: 本地持倉 {self.state.direction} 但券商無持倉，強制平倉"
                )
                self.state.direction = "flat"
                self.state.entry_price = 0.0
                self.state.quantity = 0
                self.state.unrealized_pnl = 0.0
                return True
            return False

        # 解析券商持倉方向和口數
        broker_qty = matched.get("quantity", 0)
        broker_direction = matched.get("direction", "flat")

        if broker_direction != self.state.direction:
            logger.warning(
                f"同步修正: 本地 {self.state.direction} → 券商 {broker_direction}"
            )
            self.state.direction = broker_direction
            self.state.entry_price = matched.get("price", 0.0)
            self.state.quantity = broker_qty
            return True

        return False

    def get_state(self) -> PositionState:
        """取得當前持倉狀態"""
        return self.state

    def restore_state(self, state: PositionState) -> None:
        """從持久化狀態恢復"""
        self.state = state
        logger.info(
            f"持倉狀態已恢復: {state.direction} @ {state.entry_price}"
        )
