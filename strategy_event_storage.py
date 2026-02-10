"""
StrategyEventStorage - 策略事件批次寫入器

負責將策略引擎事件批次寫入 PostgreSQL，並自動管理交易回合配對。

功能：
- 緩衝區收集策略事件
- 背景執行緒定時批次寫入
- 自動配對 entry/exit 建立交易回合
- 錯誤重試機制
"""
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal
from models import StrategyEvent, StrategyTrade

logger = logging.getLogger(__name__)

MAX_WRITE_RETRIES = 3


class StrategyEventStorage:
    """
    策略事件批次寫入器

    使用緩衝區收集事件，透過背景執行緒定時批次寫入資料庫。
    同時自動管理 strategy_trade 表的交易回合配對。
    """

    def __init__(
        self,
        buffer_size: int = 20,
        flush_interval: float = 2.0,
        enabled: bool = True,
    ):
        self._buffer_size = buffer_size
        self._flush_interval = flush_interval
        self._enabled = enabled

        self._buffer: deque = deque()
        self._lock = threading.Lock()

        self._running = False
        self._flush_thread: Optional[threading.Thread] = None

        # 統計資訊
        self._total_events_stored = 0
        self._total_trades_created = 0
        self._total_trades_closed = 0
        self._total_flush_count = 0
        self._consecutive_errors = 0

        if self._enabled:
            self.start()
            logger.info(
                f"StrategyEventStorage 已啟動: buffer_size={self._buffer_size}, "
                f"flush_interval={self._flush_interval}s"
            )
        else:
            logger.info("StrategyEventStorage 已停用")

    def start(self) -> None:
        """啟動背景刷新執行緒"""
        if self._running:
            return

        self._running = True
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="StrategyEventStorageFlushThread",
            daemon=True,
        )
        self._flush_thread.start()

    def stop(self) -> None:
        """停止背景刷新執行緒，刷新剩餘資料"""
        if not self._running:
            return

        self._running = False

        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=5.0)

        self._flush_buffer()

        logger.info(
            f"StrategyEventStorage 已停止: 共儲存 {self._total_events_stored} 筆事件, "
            f"建立 {self._total_trades_created} 筆交易, "
            f"關閉 {self._total_trades_closed} 筆交易"
        )

    def add_event(self, event: dict) -> bool:
        """
        將策略事件加入緩衝區

        Args:
            event: 策略事件字典，包含 event_type, symbol, timestamp, data

        Returns:
            成功加入緩衝區返回 True
        """
        if not self._enabled:
            return False

        try:
            if not event.get("event_type") or not event.get("symbol"):
                logger.warning(f"策略事件缺少必要欄位: {event}")
                return False

            with self._lock:
                self._buffer.append(event)
                buffer_len = len(self._buffer)

            if buffer_len >= self._buffer_size:
                threading.Thread(
                    target=self._flush_buffer,
                    name="StrategyEventStorageFlushNow",
                    daemon=True,
                ).start()

            return True

        except Exception as e:
            logger.error(f"新增策略事件到緩衝區失敗: {e}")
            return False

    def _flush_loop(self) -> None:
        """背景刷新迴圈"""
        while self._running:
            try:
                time.sleep(self._flush_interval)
                if self._running:
                    self._flush_buffer()
            except Exception as e:
                logger.error(f"背景刷新迴圈錯誤: {e}")

    def _flush_buffer(self) -> None:
        """將緩衝區資料批次寫入資料庫"""
        with self._lock:
            if not self._buffer:
                return
            events = list(self._buffer)
            self._buffer.clear()

        if not events:
            return

        for attempt in range(1, MAX_WRITE_RETRIES + 1):
            db: Optional[Session] = None
            try:
                db = SessionLocal()
                self._process_events(db, events)
                db.commit()

                self._total_flush_count += 1
                self._consecutive_errors = 0

                logger.info(
                    f"已儲存 {len(events)} 筆策略事件 "
                    f"(累計: {self._total_events_stored} 筆事件, "
                    f"{self._total_trades_created} 筆交易)"
                )
                return

            except SQLAlchemyError as e:
                self._consecutive_errors += 1
                logger.error(
                    f"批次寫入失敗 (嘗試 {attempt}/{MAX_WRITE_RETRIES}): {e}"
                )
                if db:
                    try:
                        db.rollback()
                    except Exception:
                        pass

                if attempt < MAX_WRITE_RETRIES:
                    time.sleep(1.0 * attempt)

            except Exception as e:
                self._consecutive_errors += 1
                logger.error(f"非預期的寫入錯誤: {e}")
                if db:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                break

            finally:
                if db:
                    try:
                        db.close()
                    except Exception:
                        pass

        logger.error(f"批次寫入最終失敗，遺失 {len(events)} 筆策略事件")

    def _process_events(self, db: Session, events: list) -> None:
        """
        處理事件列表：寫入 strategy_event 表並管理 strategy_trade 表

        Args:
            db: SQLAlchemy Session
            events: 事件列表
        """
        for event in events:
            event_type = event.get("event_type")
            symbol = event.get("symbol")
            data = event.get("data", {})
            timestamp_ms = event.get("timestamp", 0)

            # 轉換時間戳
            if isinstance(timestamp_ms, (int, float)) and timestamp_ms > 0:
                event_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            else:
                event_time = datetime.now(timezone.utc)

            # 寫入 strategy_event
            event_record = StrategyEvent(
                symbol=symbol,
                event_type=event_type,
                event_data=data,
                event_time=event_time,
            )
            db.add(event_record)
            db.flush()  # 取得 event_record.id

            self._total_events_stored += 1

            # 管理交易回合
            if event_type == "entry":
                self._handle_entry(db, event_record, symbol, data, event_time)
            elif event_type in ("exit", "stop_loss"):
                self._handle_exit(db, event_record, event_type, symbol, data, event_time)

    def _handle_entry(
        self, db: Session, event_record: StrategyEvent,
        symbol: str, data: dict, event_time: datetime,
    ) -> None:
        """處理進場事件：建立新的交易回合"""
        direction = data.get("direction", "long")
        price = data.get("price", 0)
        quantity = data.get("quantity", 1)

        trade = StrategyTrade(
            symbol=symbol,
            direction=direction,
            entry_price=price,
            entry_time=event_time,
            entry_event_id=event_record.id,
            quantity=quantity,
            status="open",
        )
        db.add(trade)
        self._total_trades_created += 1
        logger.debug(f"建立交易回合: {direction} @ {price}")

    def _handle_exit(
        self, db: Session, event_record: StrategyEvent,
        event_type: str, symbol: str, data: dict, event_time: datetime,
    ) -> None:
        """處理出場/停損事件：關閉對應的交易回合"""
        price = data.get("price", 0)

        # 找到同 symbol 最近的 open trade
        open_trade = (
            db.query(StrategyTrade)
            .filter(
                StrategyTrade.symbol == symbol,
                StrategyTrade.status == "open",
            )
            .order_by(StrategyTrade.entry_time.desc())
            .first()
        )

        if open_trade is None:
            logger.warning(f"找不到對應的未平倉交易: symbol={symbol}")
            return

        # 計算損益
        if open_trade.direction == "long":
            pnl = price - float(open_trade.entry_price)
        else:
            pnl = float(open_trade.entry_price) - price

        # 決定出場原因
        if event_type == "stop_loss":
            exit_reason = data.get("reason", "stop_loss")
        else:
            exit_reason = "signal"

        # 更新交易回合
        open_trade.exit_price = price
        open_trade.exit_time = event_time
        open_trade.exit_event_id = event_record.id
        open_trade.exit_reason = exit_reason
        open_trade.pnl = round(pnl, 2)
        open_trade.status = "closed"

        self._total_trades_closed += 1
        logger.debug(f"關閉交易回合: pnl={pnl:.2f} reason={exit_reason}")

    def get_stats(self) -> Dict[str, Any]:
        """取得統計資訊"""
        with self._lock:
            buffer_size = len(self._buffer)

        return {
            "enabled": self._enabled,
            "running": self._running,
            "buffer_size": buffer_size,
            "buffer_capacity": self._buffer_size,
            "flush_interval": self._flush_interval,
            "total_events_stored": self._total_events_stored,
            "total_trades_created": self._total_trades_created,
            "total_trades_closed": self._total_trades_closed,
            "total_flush_count": self._total_flush_count,
            "consecutive_errors": self._consecutive_errors,
        }

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_running(self) -> bool:
        return self._running
