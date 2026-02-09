"""
KLineBuilder 單元測試

測試涵蓋：
1. 時間邊界對齊
2. 單根 K 線建構（OHLCV）
3. K 線切換（新時間邊界）
4. 回調觸發
5. 歷史記錄管理
6. deque maxlen 限制
"""
import pytest
from datetime import datetime
from unittest.mock import Mock

from kline_builder import KLineBuilder, KLine


class TestKLine:
    """KLine 資料結構測試"""

    def test_to_dict_應該正確序列化(self):
        """測試: KLine 應能正確轉換為字典"""
        kline = KLine(
            open=100.0, high=110.0, low=90.0, close=105.0,
            volume=500,
            start_time=datetime(2026, 1, 1, 9, 0, 0),
            end_time=datetime(2026, 1, 1, 9, 3, 0),
        )
        d = kline.to_dict()

        assert d["open"] == 100.0
        assert d["high"] == 110.0
        assert d["low"] == 90.0
        assert d["close"] == 105.0
        assert d["volume"] == 500
        assert d["start_time"] == "2026-01-01T09:00:00"
        assert d["end_time"] == "2026-01-01T09:03:00"


class TestKLineBuilder:
    """KLineBuilder K 線合成器測試"""

    def test_時間邊界應該對齊到N分鐘(self):
        """測試: 3 分鐘邊界 09:01 → 09:00, 09:04 → 09:03"""
        builder = KLineBuilder(interval_minutes=3)

        ts1 = datetime(2026, 1, 1, 9, 1, 30)
        assert builder._get_boundary(ts1) == datetime(2026, 1, 1, 9, 0, 0)

        ts2 = datetime(2026, 1, 1, 9, 4, 59)
        assert builder._get_boundary(ts2) == datetime(2026, 1, 1, 9, 3, 0)

        ts3 = datetime(2026, 1, 1, 9, 6, 0)
        assert builder._get_boundary(ts3) == datetime(2026, 1, 1, 9, 6, 0)

    def test_5分鐘邊界應該正確對齊(self):
        """測試: 5 分鐘邊界 09:07 → 09:05"""
        builder = KLineBuilder(interval_minutes=5)

        ts = datetime(2026, 1, 1, 9, 7, 30)
        assert builder._get_boundary(ts) == datetime(2026, 1, 1, 9, 5, 0)

    def test_第一筆tick應該建立新K線(self):
        """測試: 第一筆 tick 應建立新的 K 線"""
        builder = KLineBuilder(interval_minutes=3)

        builder.on_tick(price=21000.0, volume=1, timestamp=datetime(2026, 1, 1, 9, 0, 30))

        assert builder.current is not None
        assert builder.current.open == 21000.0
        assert builder.current.high == 21000.0
        assert builder.current.low == 21000.0
        assert builder.current.close == 21000.0
        assert builder.current.volume == 1

    def test_同一K線內多筆tick應該正確更新OHLCV(self):
        """測試: 同一根 K 線內多筆 tick 應正確更新"""
        builder = KLineBuilder(interval_minutes=3)
        base = datetime(2026, 1, 1, 9, 0, 0)

        builder.on_tick(100.0, 10, base.replace(second=0))
        builder.on_tick(110.0, 5, base.replace(second=30))
        builder.on_tick(90.0, 8, base.replace(second=59))
        builder.on_tick(105.0, 3, base.replace(minute=1, second=30))

        assert builder.current.open == 100.0
        assert builder.current.high == 110.0
        assert builder.current.low == 90.0
        assert builder.current.close == 105.0
        assert builder.current.volume == 26

    def test_新時間邊界應該觸發K線完成(self):
        """測試: 進入新時間邊界時，前一根 K 線應完成"""
        callback = Mock()
        builder = KLineBuilder(interval_minutes=3, on_complete=callback)

        # 第一根 K 線 09:00-09:03
        builder.on_tick(100.0, 10, datetime(2026, 1, 1, 9, 0, 0))
        builder.on_tick(110.0, 5, datetime(2026, 1, 1, 9, 1, 0))

        # 進入新時間邊界 09:03
        builder.on_tick(105.0, 8, datetime(2026, 1, 1, 9, 3, 0))

        # 回調應被觸發
        callback.assert_called_once()
        completed = callback.call_args[0][0]
        assert completed.open == 100.0
        assert completed.high == 110.0
        assert completed.close == 110.0
        assert completed.volume == 15

    def test_完成的K線應該加入歷史(self):
        """測試: 完成的 K 線應加入歷史記錄"""
        builder = KLineBuilder(interval_minutes=3)

        # 第一根 K 線
        builder.on_tick(100.0, 10, datetime(2026, 1, 1, 9, 0, 0))
        # 第二根 K 線（觸發第一根完成）
        builder.on_tick(105.0, 8, datetime(2026, 1, 1, 9, 3, 0))

        assert len(builder.history) == 1
        assert builder.history[0].open == 100.0

    def test_get_close_prices應該返回收盤價列表(self):
        """測試: get_close_prices 應返回按時間排序的收盤價"""
        builder = KLineBuilder(interval_minutes=3)

        builder.on_tick(100.0, 1, datetime(2026, 1, 1, 9, 0, 0))
        builder.on_tick(110.0, 1, datetime(2026, 1, 1, 9, 2, 0))  # close=110
        builder.on_tick(105.0, 1, datetime(2026, 1, 1, 9, 3, 0))  # 觸發完成
        builder.on_tick(120.0, 1, datetime(2026, 1, 1, 9, 5, 0))  # close=120
        builder.on_tick(115.0, 1, datetime(2026, 1, 1, 9, 6, 0))  # 觸發完成

        prices = builder.get_close_prices()
        assert prices == [110.0, 120.0]

    def test_歷史應該受maxlen限制(self):
        """測試: 歷史 K 線數量應受 maxlen 限制"""
        builder = KLineBuilder(interval_minutes=3, max_history=3)

        # 建立 4 根 K 線（第 5 根 tick 觸發第 4 根完成）
        for i in range(5):
            builder.on_tick(
                100.0 + i,
                1,
                datetime(2026, 1, 1, 9, i * 3, 0),
            )

        # 歷史應最多 3 根
        assert len(builder.history) <= 3

    def test_無回調時不應該報錯(self):
        """測試: 未設定回調時，K 線完成不應報錯"""
        builder = KLineBuilder(interval_minutes=3, on_complete=None)

        builder.on_tick(100.0, 1, datetime(2026, 1, 1, 9, 0, 0))
        builder.on_tick(105.0, 1, datetime(2026, 1, 1, 9, 3, 0))

        assert len(builder.history) == 1

    def test_K線end_time應該正確計算(self):
        """測試: 完成的 K 線 end_time 應為 start_time + interval"""
        callback = Mock()
        builder = KLineBuilder(interval_minutes=3, on_complete=callback)

        builder.on_tick(100.0, 1, datetime(2026, 1, 1, 9, 0, 0))
        builder.on_tick(105.0, 1, datetime(2026, 1, 1, 9, 3, 0))

        completed = callback.call_args[0][0]
        assert completed.start_time == datetime(2026, 1, 1, 9, 0, 0)
        assert completed.end_time == datetime(2026, 1, 1, 9, 3, 0)

    def test_get_history應該返回列表副本(self):
        """測試: get_history 應返回列表（非 deque 引用）"""
        builder = KLineBuilder(interval_minutes=3)

        builder.on_tick(100.0, 1, datetime(2026, 1, 1, 9, 0, 0))
        builder.on_tick(105.0, 1, datetime(2026, 1, 1, 9, 3, 0))

        history = builder.get_history()
        assert isinstance(history, list)
        assert len(history) == 1
