"""
K 線合成器

從 tick 資料合成固定時間間隔的 K 線（OHLCV）。

使用固定時間切割法，以 tick 時間戳為準對齊到 N 分鐘邊界，
確保回測與實盤一致性。

使用方式：
    builder = KLineBuilder(interval_minutes=3, on_complete=callback)
    builder.on_tick(price=21000.0, volume=1, timestamp=datetime(...))
"""
import logging
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Callable, Optional, Deque

logger = logging.getLogger(__name__)


@dataclass
class KLine:
    """K 線資料結構"""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def to_dict(self) -> dict:
        """轉換為字典"""
        d = asdict(self)
        if self.start_time:
            d["start_time"] = self.start_time.isoformat()
        if self.end_time:
            d["end_time"] = self.end_time.isoformat()
        return d


class KLineBuilder:
    """
    K 線合成器

    從 tick 資料合成固定時間間隔的 K 線。
    使用 tick 時間戳對齊到 N 分鐘邊界。

    Args:
        interval_minutes: K 線週期（分鐘）
        on_complete: K 線完成時的回調函數
        max_history: 歷史 K 線最大保留數量
    """

    def __init__(
        self,
        interval_minutes: int = 3,
        on_complete: Optional[Callable[[KLine], None]] = None,
        max_history: int = 50,
    ):
        self.interval_minutes = interval_minutes
        self.on_complete = on_complete
        self.history: Deque[KLine] = deque(maxlen=max_history)

        # 當前正在建構的 K 線
        self._current: Optional[KLine] = None
        # 當前 K 線所屬的時間邊界
        self._current_boundary: Optional[datetime] = None

    def _get_boundary(self, ts: datetime) -> datetime:
        """
        計算 tick 時間戳所屬的 K 線起始時間邊界

        將時間對齊到最近的 N 分鐘邊界（向下取整）。
        例如 interval=3: 09:01 → 09:00, 09:04 → 09:03

        Args:
            ts: tick 時間戳

        Returns:
            對齊後的時間邊界
        """
        total_minutes = ts.hour * 60 + ts.minute
        aligned_minutes = (total_minutes // self.interval_minutes) * self.interval_minutes
        return ts.replace(
            hour=aligned_minutes // 60,
            minute=aligned_minutes % 60,
            second=0,
            microsecond=0,
        )

    def on_tick(self, price: float, volume: int, timestamp: datetime) -> None:
        """
        處理新的 tick 資料

        根據 tick 時間戳判斷是否需要切換到新的 K 線。

        Args:
            price: 成交價
            volume: 成交量
            timestamp: tick 時間戳
        """
        boundary = self._get_boundary(timestamp)

        # 第一筆 tick 或進入新的時間邊界 → 完成前一根 K 線，開始新的
        if self._current_boundary is None or boundary > self._current_boundary:
            # 完成前一根 K 線
            if self._current is not None:
                self._finalize_current()

            # 開始新的 K 線
            self._current = KLine(
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                start_time=boundary,
            )
            self._current_boundary = boundary
        else:
            # 更新當前 K 線
            self._current.high = max(self._current.high, price)
            self._current.low = min(self._current.low, price)
            self._current.close = price
            self._current.volume += volume

    def _finalize_current(self) -> None:
        """完成當前 K 線，加入歷史並觸發回調"""
        if self._current is None:
            return

        self._current.end_time = self._current_boundary.replace(
            minute=(self._current_boundary.minute + self.interval_minutes) % 60,
            hour=self._current_boundary.hour + (
                self._current_boundary.minute + self.interval_minutes
            ) // 60,
        )

        completed = self._current
        self.history.append(completed)

        logger.info(
            f"K 線完成: {completed.start_time} "
            f"O={completed.open} H={completed.high} "
            f"L={completed.low} C={completed.close} V={completed.volume}"
        )

        if self.on_complete:
            self.on_complete(completed)

    def get_history(self) -> list[KLine]:
        """取得歷史 K 線列表（從舊到新）"""
        return list(self.history)

    def get_close_prices(self) -> list[float]:
        """取得歷史收盤價列表（從舊到新）"""
        return [k.close for k in self.history]

    @property
    def current(self) -> Optional[KLine]:
        """取得當前正在建構的 K 線"""
        return self._current
