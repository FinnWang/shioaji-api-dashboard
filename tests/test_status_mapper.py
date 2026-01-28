"""
OrderStatusMapper 單元測試

測試涵蓋：
1. 狀態映射
2. 最終狀態判斷
3. 成功/等待狀態判斷
4. 訂單記錄更新
"""
import pytest
from unittest.mock import MagicMock

from status_mapper import OrderStatusMapper


class TestMapFillStatus:
    """map_fill_status 方法測試"""

    def test_Filled_應該映射為filled(self):
        """測試: Filled 狀態應該映射為 filled"""
        assert OrderStatusMapper.map_fill_status("Filled") == "filled"

    def test_PartFilled_應該映射為partial_filled(self):
        """測試: PartFilled 狀態應該映射為 partial_filled"""
        assert OrderStatusMapper.map_fill_status("PartFilled") == "partial_filled"

    def test_Cancelled_應該映射為cancelled(self):
        """測試: Cancelled 狀態應該映射為 cancelled"""
        assert OrderStatusMapper.map_fill_status("Cancelled") == "cancelled"

    def test_Inactive_應該映射為cancelled(self):
        """測試: Inactive 狀態應該映射為 cancelled（失效視同取消）"""
        assert OrderStatusMapper.map_fill_status("Inactive") == "cancelled"

    def test_Failed_應該映射為failed(self):
        """測試: Failed 狀態應該映射為 failed"""
        assert OrderStatusMapper.map_fill_status("Failed") == "failed"

    def test_PendingSubmit_應該映射為submitted(self):
        """測試: PendingSubmit 狀態應該映射為 submitted"""
        assert OrderStatusMapper.map_fill_status("PendingSubmit") == "submitted"

    def test_PreSubmitted_應該映射為submitted(self):
        """測試: PreSubmitted 狀態應該映射為 submitted"""
        assert OrderStatusMapper.map_fill_status("PreSubmitted") == "submitted"

    def test_Submitted_應該映射為submitted(self):
        """測試: Submitted 狀態應該映射為 submitted"""
        assert OrderStatusMapper.map_fill_status("Submitted") == "submitted"

    def test_未知狀態_應該映射為unknown(self):
        """測試: 未知狀態應該映射為 unknown"""
        assert OrderStatusMapper.map_fill_status("UnknownStatus") == "unknown"
        assert OrderStatusMapper.map_fill_status("") == "unknown"


class TestIsFinalStatus:
    """is_final_status 方法測試"""

    def test_Filled_是最終狀態(self):
        """測試: Filled 是最終狀態"""
        assert OrderStatusMapper.is_final_status("Filled") is True

    def test_Cancelled_是最終狀態(self):
        """測試: Cancelled 是最終狀態"""
        assert OrderStatusMapper.is_final_status("Cancelled") is True

    def test_Inactive_是最終狀態(self):
        """測試: Inactive 是最終狀態"""
        assert OrderStatusMapper.is_final_status("Inactive") is True

    def test_Failed_是最終狀態(self):
        """測試: Failed 是最終狀態"""
        assert OrderStatusMapper.is_final_status("Failed") is True

    def test_Submitted_不是最終狀態(self):
        """測試: Submitted 不是最終狀態"""
        assert OrderStatusMapper.is_final_status("Submitted") is False

    def test_PartFilled_不是最終狀態(self):
        """測試: PartFilled 不是最終狀態（可能會繼續成交）"""
        assert OrderStatusMapper.is_final_status("PartFilled") is False

    def test_PendingSubmit_不是最終狀態(self):
        """測試: PendingSubmit 不是最終狀態"""
        assert OrderStatusMapper.is_final_status("PendingSubmit") is False


class TestIsSuccessStatus:
    """is_success_status 方法測試"""

    def test_Filled_是成功狀態(self):
        """測試: Filled 是成功狀態"""
        assert OrderStatusMapper.is_success_status("Filled") is True

    def test_PartFilled_是成功狀態(self):
        """測試: PartFilled 是成功狀態"""
        assert OrderStatusMapper.is_success_status("PartFilled") is True

    def test_Cancelled_不是成功狀態(self):
        """測試: Cancelled 不是成功狀態"""
        assert OrderStatusMapper.is_success_status("Cancelled") is False

    def test_Failed_不是成功狀態(self):
        """測試: Failed 不是成功狀態"""
        assert OrderStatusMapper.is_success_status("Failed") is False

    def test_Submitted_不是成功狀態(self):
        """測試: Submitted 不是成功狀態（尚未成交）"""
        assert OrderStatusMapper.is_success_status("Submitted") is False


class TestIsPendingStatus:
    """is_pending_status 方法測試"""

    def test_PendingSubmit_是等待狀態(self):
        """測試: PendingSubmit 是等待狀態"""
        assert OrderStatusMapper.is_pending_status("PendingSubmit") is True

    def test_PreSubmitted_是等待狀態(self):
        """測試: PreSubmitted 是等待狀態"""
        assert OrderStatusMapper.is_pending_status("PreSubmitted") is True

    def test_Submitted_是等待狀態(self):
        """測試: Submitted 是等待狀態"""
        assert OrderStatusMapper.is_pending_status("Submitted") is True

    def test_PartFilled_是等待狀態(self):
        """測試: PartFilled 是等待狀態（等待剩餘成交）"""
        assert OrderStatusMapper.is_pending_status("PartFilled") is True

    def test_Filled_不是等待狀態(self):
        """測試: Filled 不是等待狀態"""
        assert OrderStatusMapper.is_pending_status("Filled") is False

    def test_Cancelled_不是等待狀態(self):
        """測試: Cancelled 不是等待狀態"""
        assert OrderStatusMapper.is_pending_status("Cancelled") is False


class TestUpdateOrderStatus:
    """update_order_status 方法測試"""

    def test_應該更新訂單狀態為mapped值(self):
        """測試: 應該將訂單狀態更新為映射後的值"""
        # Arrange
        mock_order = MagicMock()
        mock_order.status = "submitted"

        # Act
        OrderStatusMapper.update_order_status(mock_order, "Filled")

        # Assert
        assert mock_order.status == "filled"

    def test_未知狀態不應該更新訂單(self):
        """測試: 未知狀態不應該更新訂單"""
        # Arrange
        mock_order = MagicMock()
        mock_order.status = "submitted"

        # Act
        OrderStatusMapper.update_order_status(mock_order, "UnknownStatus")

        # Assert
        assert mock_order.status == "submitted"  # 保持原狀

    def test_Inactive應該更新為cancelled(self):
        """測試: Inactive 應該將訂單狀態更新為 cancelled"""
        # Arrange
        mock_order = MagicMock()
        mock_order.status = "submitted"

        # Act
        OrderStatusMapper.update_order_status(mock_order, "Inactive")

        # Assert
        assert mock_order.status == "cancelled"
