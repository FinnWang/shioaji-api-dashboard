"""
QuoteStorage - 報價資料批次寫入器

負責將 Shioaji 報價資料批次寫入 PostgreSQL，供量化分析使用。

功能：
- 緩衝區收集報價資料
- 背景執行緒定時批次寫入
- 錯誤重試機制
- 可透過設定開關啟用/停用
"""
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from database import SessionLocal
from models import QuoteHistory

logger = logging.getLogger(__name__)

# 最大重試次數
MAX_WRITE_RETRIES = 3


class QuoteStorage:
    """
    報價資料批次寫入器

    使用緩衝區收集報價資料，透過背景執行緒定時批次寫入資料庫。
    設計原則：
    - 非阻塞：不影響即時報價推送
    - 錯誤隔離：資料庫寫入失敗不影響 Redis 發布
    - 批次寫入：減少資料庫 I/O
    """

    def __init__(
        self,
        buffer_size: Optional[int] = None,
        flush_interval: Optional[float] = None,
        enabled: Optional[bool] = None,
    ):
        """
        初始化 QuoteStorage

        Args:
            buffer_size: 緩衝區大小，達到此數量時觸發批次寫入
            flush_interval: 定時刷新間隔（秒）
            enabled: 是否啟用報價儲存
        """
        self._buffer_size = buffer_size or settings.quote_storage_buffer_size
        self._flush_interval = flush_interval or settings.quote_storage_flush_interval
        self._enabled = enabled if enabled is not None else settings.quote_storage_enabled

        # 緩衝區和鎖
        self._buffer: deque = deque()
        self._lock = threading.Lock()

        # 背景執行緒控制
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None

        # 統計資訊
        self._total_quotes_stored = 0
        self._total_flush_count = 0
        self._last_flush_time: Optional[float] = None
        self._consecutive_errors = 0

        if self._enabled:
            self.start()
            logger.info(
                f"QuoteStorage 已啟動: buffer_size={self._buffer_size}, "
                f"flush_interval={self._flush_interval}s"
            )
        else:
            logger.info("QuoteStorage 已停用")

    def start(self) -> None:
        """啟動背景刷新執行緒"""
        if self._running:
            return

        self._running = True
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="QuoteStorageFlushThread",
            daemon=True,
        )
        self._flush_thread.start()
        logger.debug("QuoteStorage 背景執行緒已啟動")

    def stop(self) -> None:
        """
        停止背景刷新執行緒

        會先刷新緩衝區中剩餘的資料
        """
        if not self._running:
            return

        self._running = False

        # 等待執行緒結束
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=5.0)

        # 最後一次刷新
        self._flush_buffer()

        logger.info(
            f"QuoteStorage 已停止: 共儲存 {self._total_quotes_stored} 筆報價, "
            f"刷新 {self._total_flush_count} 次"
        )

    def add_quote(self, quote_data: Dict[str, Any]) -> bool:
        """
        新增報價到緩衝區

        Args:
            quote_data: 報價資料字典，包含 symbol, code, quote_type 等欄位

        Returns:
            成功加入緩衝區返回 True
        """
        if not self._enabled:
            return False

        try:
            # 驗證必要欄位
            if not quote_data.get("symbol") or not quote_data.get("code"):
                logger.warning(f"報價資料缺少必要欄位: {quote_data}")
                return False

            # 建立報價記錄
            quote_record = self._create_quote_record(quote_data)

            with self._lock:
                self._buffer.append(quote_record)
                buffer_len = len(self._buffer)

            # 達到緩衝區大小時觸發刷新
            if buffer_len >= self._buffer_size:
                logger.debug(f"緩衝區已滿 ({buffer_len}), 觸發刷新")
                threading.Thread(
                    target=self._flush_buffer,
                    name="QuoteStorageFlushNow",
                    daemon=True,
                ).start()

            return True

        except Exception as e:
            logger.error(f"新增報價到緩衝區失敗: {e}")
            return False

    def _create_quote_record(self, quote_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        從 QuoteData 建立資料庫記錄

        Args:
            quote_data: QuoteData 字典格式

        Returns:
            可用於建立 QuoteHistory 的字典
        """
        # 解析時間戳
        timestamp = quote_data.get("timestamp", 0)
        if isinstance(timestamp, (int, float)) and timestamp > 0:
            # 毫秒時間戳轉 datetime
            quote_time = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        else:
            quote_time = datetime.now(timezone.utc)

        return {
            "symbol": quote_data.get("symbol", ""),
            "code": quote_data.get("code", ""),
            "quote_type": quote_data.get("quote_type", "tick"),
            "close_price": quote_data.get("close") or None,
            "open_price": quote_data.get("open") or None,
            "high_price": quote_data.get("high") or None,
            "low_price": quote_data.get("low") or None,
            "change_price": quote_data.get("change_price") or None,
            "change_rate": quote_data.get("change_rate") or None,
            "volume": quote_data.get("volume") or None,
            "total_volume": quote_data.get("total_volume") or None,
            "buy_price": quote_data.get("buy_price") or None,
            "sell_price": quote_data.get("sell_price") or None,
            "buy_volume": quote_data.get("buy_volume") or None,
            "sell_volume": quote_data.get("sell_volume") or None,
            "quote_time": quote_time,
        }

    def _flush_loop(self) -> None:
        """背景刷新迴圈"""
        while self._running:
            try:
                time.sleep(self._flush_interval)
                if self._running:  # 確認仍在運行
                    self._flush_buffer()
            except Exception as e:
                logger.error(f"背景刷新迴圈錯誤: {e}")

    def _flush_buffer(self) -> None:
        """
        將緩衝區資料批次寫入資料庫

        使用重試機制處理暫時性錯誤
        """
        # 取出緩衝區所有資料
        with self._lock:
            if not self._buffer:
                return
            records = list(self._buffer)
            self._buffer.clear()

        if not records:
            return

        # 嘗試批次寫入
        for attempt in range(1, MAX_WRITE_RETRIES + 1):
            db: Optional[Session] = None
            try:
                db = SessionLocal()

                # 建立 ORM 物件並批次儲存
                quote_objects = [QuoteHistory(**record) for record in records]
                db.bulk_save_objects(quote_objects)
                db.commit()

                # 更新統計
                self._total_quotes_stored += len(records)
                self._total_flush_count += 1
                self._last_flush_time = time.time()
                self._consecutive_errors = 0

                logger.info(
                    f"已儲存 {len(records)} 筆報價 "
                    f"(累計: {self._total_quotes_stored} 筆)"
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
                    time.sleep(1.0 * attempt)  # 指數退避

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

        # 所有重試都失敗，記錄遺失的資料數量
        logger.error(f"批次寫入最終失敗，遺失 {len(records)} 筆報價資料")

    def get_stats(self) -> Dict[str, Any]:
        """
        取得統計資訊

        Returns:
            包含統計資訊的字典
        """
        with self._lock:
            buffer_size = len(self._buffer)

        return {
            "enabled": self._enabled,
            "running": self._running,
            "buffer_size": buffer_size,
            "buffer_capacity": self._buffer_size,
            "flush_interval": self._flush_interval,
            "total_quotes_stored": self._total_quotes_stored,
            "total_flush_count": self._total_flush_count,
            "last_flush_time": self._last_flush_time,
            "consecutive_errors": self._consecutive_errors,
        }

    @property
    def is_enabled(self) -> bool:
        """是否啟用"""
        return self._enabled

    @property
    def is_running(self) -> bool:
        """是否正在運行"""
        return self._running
