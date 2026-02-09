#!/usr/bin/env python3
"""
策略引擎 Worker - MA 均線交叉自動交易

作為獨立服務運行，透過 Redis Pub/Sub 接收即時報價，
執行 MA5/MA20 均線交叉策略，透過 TradingQueueClient 下單。

流程：
  訂閱報價 → Redis Pub/Sub → tick → K 線 → 策略 → 風控 → 下單

啟動方式：
  python strategy_worker.py
"""
import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime, time as dtime
from typing import Optional

import redis

from strategy_config import StrategySettings
from kline_builder import KLineBuilder, KLine
from strategy_engine import StrategyEngine, SignalAction, PositionDirection
from risk_manager import RiskManager, StopReason
from position_manager import PositionManager
from trading_queue import TradingQueueClient

# 日誌設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("strategy_worker")

# Redis 持久化鍵
STATE_KEY_PREFIX = "strategy:state:"
QUOTE_CHANNEL_PREFIX = "quote:"

# 交易時段定義
DAY_SESSION_START = dtime(8, 45)
DAY_SESSION_END = dtime(13, 45)
NIGHT_SESSION_START = dtime(15, 0)
# 夜盤跨日到隔天 05:00，用 23:59:59 表示當天結束
NIGHT_SESSION_END_BEFORE_MIDNIGHT = dtime(23, 59, 59)
NIGHT_SESSION_END_AFTER_MIDNIGHT = dtime(5, 0)


def is_trading_hours(now: Optional[datetime] = None) -> bool:
    """
    檢查是否在交易時段內

    日盤：08:45 - 13:45
    夜盤：15:00 - 隔天 05:00

    Args:
        now: 當前時間（測試用）

    Returns:
        是否在交易時段
    """
    if now is None:
        now = datetime.now()

    t = now.time()

    # 日盤
    if DAY_SESSION_START <= t <= DAY_SESSION_END:
        return True

    # 夜盤（15:00 到午夜）
    if t >= NIGHT_SESSION_START:
        return True

    # 夜盤（午夜到 05:00）
    if t <= NIGHT_SESSION_END_AFTER_MIDNIGHT:
        return True

    return False


class StrategyWorker:
    """
    策略引擎主程式

    整合 K 線合成、策略引擎、風控、持倉管理，
    透過 Redis Pub/Sub 接收報價，透過 TradingQueueClient 下單。
    """

    def __init__(self, settings: Optional[StrategySettings] = None):
        self.settings = settings or StrategySettings()
        self._running = False
        self._pubsub = None
        self._pubsub_thread = None

        # Redis 連線
        self._redis = redis.from_url(
            self.settings.redis_url, decode_responses=True
        )

        # 交易客戶端
        self._trading_client: Optional[TradingQueueClient] = None

        # K 線合成器
        self._kline_builder = KLineBuilder(
            interval_minutes=self.settings.kline_interval_minutes,
            on_complete=self._on_kline_complete,
        )

        # 策略引擎
        self._strategy = StrategyEngine(
            ma_fast_period=self.settings.ma_fast_period,
            ma_slow_period=self.settings.ma_slow_period,
        )

        # 風險管理器
        self._risk_manager = RiskManager(
            stop_loss_points=self.settings.stop_loss_points,
            trailing_stop_points=self.settings.trailing_stop_points,
            daily_max_loss_points=self.settings.daily_max_loss_points,
            daily_max_trades=self.settings.daily_max_trades,
        )

        # 持倉管理器
        self._position_manager = PositionManager(
            symbol=self.settings.symbol,
            quantity=self.settings.quantity,
            sync_interval=self.settings.position_sync_interval,
        )

        # 反轉等待狀態：平倉後需要反向開倉
        self._pending_reverse: Optional[str] = None  # "long" 或 "short"

        # 上次狀態持久化時間
        self._last_persist_time = 0.0

        # 上次每日重設的日期
        self._last_reset_date: Optional[str] = None

        logger.info(
            f"策略引擎初始化: symbol={self.settings.symbol} "
            f"MA{self.settings.ma_fast_period}/{self.settings.ma_slow_period} "
            f"K線={self.settings.kline_interval_minutes}分 "
            f"口數={self.settings.quantity} "
            f"停損={self.settings.stop_loss_points}點 "
            f"追蹤停損={self.settings.trailing_stop_points}點 "
            f"模擬={'是' if self.settings.simulation else '否'}"
        )

    def start(self) -> None:
        """啟動策略引擎"""
        self._running = True

        # 初始化交易客戶端
        try:
            self._trading_client = TradingQueueClient(
                redis_url=self.settings.redis_url
            )
            logger.info("交易客戶端連線成功")
        except Exception as e:
            logger.error(f"交易客戶端連線失敗: {e}")
            return

        # 嘗試恢復狀態
        self._restore_state()

        # 訂閱報價
        self._subscribe_quote()

        # 開始監聽 Redis Pub/Sub
        self._start_pubsub_listener()

        logger.info("策略引擎已啟動，等待報價...")

        # 主循環
        try:
            while self._running:
                self._main_loop_tick()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到中斷信號")
        finally:
            self.stop()

    def stop(self) -> None:
        """停止策略引擎"""
        logger.info("正在停止策略引擎...")
        self._running = False

        # 持久化最終狀態
        self._persist_state()

        # 停止 Pub/Sub 監聽
        if self._pubsub_thread and self._pubsub_thread.is_alive():
            self._pubsub.unsubscribe()
            self._pubsub_thread.join(timeout=5)

        logger.info("策略引擎已停止")

    def _subscribe_quote(self) -> None:
        """透過 TradingQueueClient 訂閱報價"""
        try:
            response = self._trading_client.subscribe_quote(
                symbol=self.settings.symbol,
                simulation=self.settings.simulation,
            )
            if response.success:
                logger.info(f"報價訂閱成功: {self.settings.symbol}")
            else:
                logger.error(f"報價訂閱失敗: {response.error}")
        except Exception as e:
            logger.error(f"報價訂閱異常: {e}")

    def _start_pubsub_listener(self) -> None:
        """啟動 Redis Pub/Sub 監聽執行緒"""
        channel = f"{QUOTE_CHANNEL_PREFIX}{self.settings.symbol}"
        self._pubsub = self._redis.pubsub()
        self._pubsub.subscribe(**{channel: self._on_quote_message})

        self._pubsub_thread = self._pubsub.run_in_thread(
            sleep_time=0.01, daemon=True
        )
        logger.info(f"已訂閱 Redis 頻道: {channel}")

    def _on_quote_message(self, message: dict) -> None:
        """
        處理 Redis Pub/Sub 報價訊息

        每個 tick 都會檢查停損（即時反應），
        K 線完成時才做策略判斷。
        """
        if message.get("type") != "message":
            return

        try:
            data = json.loads(message["data"])

            # 只處理 tick 資料（非 bidask）
            if data.get("quote_type") == "bidask":
                return

            price = data.get("close", 0.0)
            volume = data.get("volume", 0)
            timestamp_ms = data.get("timestamp", 0)

            if price <= 0:
                return

            # 轉換時間戳
            tick_time = datetime.fromtimestamp(timestamp_ms / 1000)

            # 檢查每日重設
            self._check_daily_reset(tick_time)

            # 檢查交易時段
            if not is_trading_hours(tick_time):
                return

            # 餵入 K 線合成器
            self._kline_builder.on_tick(price, volume, tick_time)

            # 更新未實現損益
            if not self._position_manager.is_flat:
                self._position_manager.update_unrealized_pnl(price)

            # 即時停損檢查
            self._check_stop_loss(price)

        except Exception as e:
            logger.error(f"處理報價訊息失敗: {e}", exc_info=True)

    def _on_kline_complete(self, kline: KLine) -> None:
        """
        K 線完成回調

        在此做策略判斷，產生交易訊號。
        """
        close_prices = self._kline_builder.get_close_prices()

        logger.info(
            f"K 線完成 [{kline.start_time}]: "
            f"O={kline.open} H={kline.high} L={kline.low} C={kline.close} "
            f"歷史K線數={len(close_prices)}"
        )

        # 確定當前持倉方向
        direction = self._position_manager.direction
        pos_dir = PositionDirection(direction)

        # 評估策略
        signal = self._strategy.evaluate(close_prices, pos_dir)

        if signal.action == SignalAction.NONE:
            logger.debug(f"策略訊號: 無動作 ({signal.reason})")
            return

        logger.info(
            f"策略訊號: {signal.action.value} ({signal.reason}) "
            f"MA{self.settings.ma_fast_period}={signal.ma_fast:.2f} "
            f"MA{self.settings.ma_slow_period}={signal.ma_slow:.2f}"
        )

        # 執行訊號
        self._execute_signal(signal, kline.close)

    def _execute_signal(self, signal, current_price: float) -> None:
        """
        執行交易訊號

        處理進場、平倉和反轉邏輯。
        反轉時先平倉，再設定 _pending_reverse 等待下次 tick 開倉。
        """
        if signal.action == SignalAction.BUY:
            self._place_entry("long", current_price)

        elif signal.action == SignalAction.SELL:
            self._place_entry("short", current_price)

        elif signal.action == SignalAction.CLOSE:
            # 判斷是否需要反轉
            if "反轉做多" in signal.reason:
                self._pending_reverse = "long"
            elif "反轉做空" in signal.reason:
                self._pending_reverse = "short"

            self._place_exit(current_price)

    def _place_entry(self, direction: str, price: float) -> None:
        """下進場單"""
        # 風控檢查
        can_trade, reason = self._risk_manager.can_trade()
        if not can_trade:
            logger.warning(f"風控拒絕開倉: {reason}")
            return

        action = "Buy" if direction == "long" else "Sell"

        try:
            logger.info(
                f"下單進場: {action} {self.settings.symbol} "
                f"x{self.settings.quantity} @ 市價"
            )

            response = self._trading_client.place_entry_order(
                symbol=self.settings.symbol,
                quantity=self.settings.quantity,
                action=action,
                simulation=self.settings.simulation,
                price_type="MKT",
            )

            if response.success:
                # 更新本地持倉和風控
                self._position_manager.open_position(direction, price)
                self._risk_manager.on_entry(price, direction)
                logger.info(f"進場成功: {direction} @ {price}")
            else:
                logger.error(f"進場下單失敗: {response.error}")

        except Exception as e:
            logger.error(f"進場下單異常: {e}", exc_info=True)

    def _place_exit(self, price: float) -> None:
        """下出場單"""
        direction = self._position_manager.direction
        if direction == "flat":
            return

        position_direction = "Long" if direction == "long" else "Short"

        try:
            logger.info(
                f"下單平倉: {self.settings.symbol} "
                f"方向={position_direction} @ 市價"
            )

            response = self._trading_client.place_exit_order(
                symbol=self.settings.symbol,
                position_direction=position_direction,
                simulation=self.settings.simulation,
                price_type="MKT",
            )

            if response.success:
                # 更新本地持倉和風控
                pnl = self._position_manager.close_position(price)
                self._risk_manager.on_exit(price)
                logger.info(f"平倉成功: 損益={pnl:.1f} 點")

                # 處理反轉
                if self._pending_reverse:
                    reverse_dir = self._pending_reverse
                    self._pending_reverse = None
                    logger.info(f"執行反轉開倉: {reverse_dir}")
                    self._place_entry(reverse_dir, price)
            else:
                logger.error(f"平倉下單失敗: {response.error}")
                self._pending_reverse = None

        except Exception as e:
            logger.error(f"平倉下單異常: {e}", exc_info=True)
            self._pending_reverse = None

    def _check_stop_loss(self, current_price: float) -> None:
        """即時停損檢查"""
        if self._position_manager.is_flat:
            return

        stop_reason = self._risk_manager.check_stop_loss(current_price)
        if stop_reason is not None:
            logger.warning(f"停損觸發: {stop_reason.value} @ {current_price}")
            self._pending_reverse = None  # 停損不做反轉
            self._place_exit(current_price)

    def _check_daily_reset(self, tick_time: datetime) -> None:
        """檢查是否需要每日重設"""
        today = tick_time.strftime("%Y-%m-%d")
        if self._last_reset_date is None:
            self._last_reset_date = today
            return

        if today != self._last_reset_date:
            logger.info(f"新交易日: {today}，重設每日統計")
            self._risk_manager.reset_daily()
            self._last_reset_date = today

    def _main_loop_tick(self) -> None:
        """主循環每秒執行的任務"""
        now = time.time()

        # 定期持久化狀態
        if now - self._last_persist_time >= self.settings.state_persist_interval:
            self._persist_state()
            self._last_persist_time = now

        # 定期同步券商持倉
        if self._position_manager.should_sync() and self._trading_client:
            self._sync_positions()

    def _sync_positions(self) -> None:
        """與券商同步持倉"""
        try:
            response = self._trading_client.get_positions(
                simulation=self.settings.simulation
            )
            if response.success and response.data:
                positions = response.data if isinstance(response.data, list) else []
                corrected = self._position_manager.sync_with_broker(positions)
                if corrected:
                    logger.warning("持倉已與券商同步修正")
        except Exception as e:
            logger.error(f"同步持倉失敗: {e}")

    def _persist_state(self) -> None:
        """持久化狀態到 Redis"""
        try:
            key = f"{STATE_KEY_PREFIX}{self.settings.symbol}"
            state = {
                "risk": self._risk_manager.get_state().to_json(),
                "position": self._position_manager.get_state().to_json(),
                "pending_reverse": self._pending_reverse,
                "last_reset_date": self._last_reset_date,
            }
            self._redis.set(key, json.dumps(state), ex=86400)  # 24 小時過期
            logger.debug("狀態已持久化")
        except Exception as e:
            logger.error(f"狀態持久化失敗: {e}")

    def _restore_state(self) -> None:
        """從 Redis 恢復狀態"""
        try:
            key = f"{STATE_KEY_PREFIX}{self.settings.symbol}"
            data = self._redis.get(key)
            if data is None:
                logger.info("無先前狀態，使用預設值")
                return

            state = json.loads(data)

            from risk_manager import RiskState
            from position_manager import PositionState

            if "risk" in state:
                self._risk_manager.restore_state(
                    RiskState.from_json(state["risk"])
                )
            if "position" in state:
                self._position_manager.restore_state(
                    PositionState.from_json(state["position"])
                )
            if "pending_reverse" in state:
                self._pending_reverse = state["pending_reverse"]
            if "last_reset_date" in state:
                self._last_reset_date = state["last_reset_date"]

            logger.info("已從 Redis 恢復狀態")

        except Exception as e:
            logger.error(f"狀態恢復失敗: {e}")


def main():
    """主入口"""
    settings = StrategySettings()

    logger.info("=" * 60)
    logger.info("微型台指期貨自動交易策略引擎")
    logger.info(f"商品: {settings.symbol}")
    logger.info(f"策略: MA{settings.ma_fast_period}/MA{settings.ma_slow_period} 均線交叉")
    logger.info(f"K線週期: {settings.kline_interval_minutes} 分鐘")
    logger.info(f"口數: {settings.quantity}")
    logger.info(f"停損: {settings.stop_loss_points} 點")
    logger.info(f"追蹤停損: {settings.trailing_stop_points} 點")
    logger.info(f"每日最大虧損: {settings.daily_max_loss_points} 點")
    logger.info(f"模擬模式: {'是' if settings.simulation else '否'}")
    logger.info("=" * 60)

    worker = StrategyWorker(settings)

    # 優雅關閉
    def signal_handler(sig, frame):
        logger.info(f"收到信號 {sig}，準備關閉...")
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    worker.start()


if __name__ == "__main__":
    main()
