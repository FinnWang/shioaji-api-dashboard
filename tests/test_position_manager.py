"""
PositionManager 單元測試

測試涵蓋：
1. 開倉/平倉操作
2. 未實現損益計算
3. 券商同步邏輯
4. 狀態序列化/恢復
5. 同步間隔檢查
"""
import pytest
import time
from unittest.mock import patch

from position_manager import PositionManager, PositionState


class TestPositionState:
    """PositionState 序列化測試"""

    def test_序列化與反序列化應一致(self):
        """測試: PositionState 應能正確序列化與反序列化"""
        state = PositionState(
            direction="long",
            entry_price=21000.0,
            quantity=2,
            unrealized_pnl=50.0,
        )

        json_str = state.to_json()
        restored = PositionState.from_json(json_str)

        assert restored.direction == "long"
        assert restored.entry_price == 21000.0
        assert restored.quantity == 2
        assert restored.unrealized_pnl == 50.0


class TestPositionManagerOpenClose:
    """開倉/平倉測試"""

    def test_初始狀態應為空倉(self):
        """測試: 初始化後應為空倉"""
        pm = PositionManager()

        assert pm.is_flat is True
        assert pm.direction == "flat"
        assert pm.entry_price == 0.0

    def test_開多倉應正確設定狀態(self):
        """測試: 開多倉後狀態應正確"""
        pm = PositionManager(quantity=2)
        pm.open_position("long", 21000.0)

        assert pm.direction == "long"
        assert pm.entry_price == 21000.0
        assert pm.state.quantity == 2
        assert pm.is_flat is False

    def test_開空倉應正確設定狀態(self):
        """測試: 開空倉後狀態應正確"""
        pm = PositionManager(quantity=3)
        pm.open_position("short", 21000.0)

        assert pm.direction == "short"
        assert pm.entry_price == 21000.0
        assert pm.state.quantity == 3

    def test_多單平倉應正確計算損益(self):
        """測試: 多單平倉損益 = 出場價 - 進場價"""
        pm = PositionManager()
        pm.open_position("long", 21000.0)
        pnl = pm.close_position(21050.0)

        assert pnl == 50.0
        assert pm.is_flat is True

    def test_空單平倉應正確計算損益(self):
        """測試: 空單平倉損益 = 進場價 - 出場價"""
        pm = PositionManager()
        pm.open_position("short", 21000.0)
        pnl = pm.close_position(20950.0)

        assert pnl == 50.0
        assert pm.is_flat is True

    def test_多單虧損應為負數(self):
        """測試: 多單虧損時損益應為負"""
        pm = PositionManager()
        pm.open_position("long", 21000.0)
        pnl = pm.close_position(20950.0)

        assert pnl == -50.0

    def test_平倉後應重設所有狀態(self):
        """測試: 平倉後應重設為空倉狀態"""
        pm = PositionManager()
        pm.open_position("long", 21000.0)
        pm.close_position(21050.0)

        assert pm.state.direction == "flat"
        assert pm.state.entry_price == 0.0
        assert pm.state.quantity == 0
        assert pm.state.unrealized_pnl == 0.0


class TestPositionManagerUnrealizedPnl:
    """未實現損益測試"""

    def test_多單未實現損益應正確計算(self):
        """測試: 多單未實現損益 = 當前價 - 進場價"""
        pm = PositionManager()
        pm.open_position("long", 21000.0)

        pnl = pm.update_unrealized_pnl(21030.0)
        assert pnl == 30.0
        assert pm.state.unrealized_pnl == 30.0

    def test_空單未實現損益應正確計算(self):
        """測試: 空單未實現損益 = 進場價 - 當前價"""
        pm = PositionManager()
        pm.open_position("short", 21000.0)

        pnl = pm.update_unrealized_pnl(20970.0)
        assert pnl == 30.0

    def test_空倉未實現損益應為零(self):
        """測試: 空倉時未實現損益應為 0"""
        pm = PositionManager()
        pnl = pm.update_unrealized_pnl(21000.0)
        assert pnl == 0.0


class TestPositionManagerSync:
    """券商同步測試"""

    def test_首次應需要同步(self):
        """測試: 首次（last_sync_time=0）應需要同步"""
        pm = PositionManager()
        assert pm.should_sync() is True

    def test_同步間隔內不需要同步(self):
        """測試: 同步間隔內不應需要同步"""
        pm = PositionManager(sync_interval=60)
        pm.state.last_sync_time = time.time()

        assert pm.should_sync() is False

    def test_超過同步間隔應需要同步(self):
        """測試: 超過同步間隔應需要同步"""
        pm = PositionManager(sync_interval=60)
        pm.state.last_sync_time = time.time() - 61

        assert pm.should_sync() is True

    def test_券商無持倉但本地有持倉應修正(self):
        """測試: 券商無持倉時，應將本地持倉強制平倉"""
        pm = PositionManager(symbol="MXFR1")
        pm.open_position("long", 21000.0)

        corrected = pm.sync_with_broker([])
        assert corrected is True
        assert pm.is_flat is True

    def test_券商無持倉本地也無持倉不應修正(self):
        """測試: 雙方都無持倉時不需修正"""
        pm = PositionManager(symbol="MXFR1")

        corrected = pm.sync_with_broker([])
        assert corrected is False

    def test_券商持倉方向不同應以券商為準(self):
        """測試: 方向不一致時，以券商為準修正"""
        pm = PositionManager(symbol="MXFR1")
        pm.open_position("long", 21000.0)

        broker_positions = [
            {"code": "MXF202601", "direction": "short", "quantity": 2, "price": 20900.0}
        ]
        corrected = pm.sync_with_broker(broker_positions)

        assert corrected is True
        assert pm.direction == "short"
        assert pm.state.entry_price == 20900.0

    def test_券商持倉一致不應修正(self):
        """測試: 方向一致時不需修正"""
        pm = PositionManager(symbol="MXFR1")
        pm.open_position("long", 21000.0)

        broker_positions = [
            {"code": "MXF202601", "direction": "long", "quantity": 2, "price": 21000.0}
        ]
        corrected = pm.sync_with_broker(broker_positions)

        assert corrected is False


class TestPositionManagerRestore:
    """狀態恢復測試"""

    def test_restore_state應正確恢復(self):
        """測試: restore_state 應正確恢復持倉狀態"""
        pm = PositionManager()
        state = PositionState(
            direction="short",
            entry_price=21000.0,
            quantity=2,
            unrealized_pnl=-20.0,
        )

        pm.restore_state(state)

        assert pm.direction == "short"
        assert pm.entry_price == 21000.0
        assert pm.state.quantity == 2
