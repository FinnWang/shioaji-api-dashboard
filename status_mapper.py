"""
訂單狀態映射器

統一處理 Shioaji 交易所狀態到系統內部狀態的轉換，
避免在多處重複相同的狀態判斷邏輯。

Shioaji 狀態說明：
- PendingSubmit: 傳送中
- PreSubmitted: 預約單
- Submitted: 已傳送
- Filled: 完全成交
- PartFilled: 部分成交
- Cancelled: 已取消
- Inactive: 失效（過期/被拒絕）
- Failed: 失敗
"""
from typing import Optional


class OrderStatusMapper:
    """訂單狀態映射器"""

    # Shioaji 狀態 -> 系統內部狀態
    STATUS_MAPPING = {
        "Filled": "filled",
        "PartFilled": "partial_filled",
        "Cancelled": "cancelled",
        "Inactive": "cancelled",  # 失效視同取消
        "Failed": "failed",
        "PendingSubmit": "submitted",
        "PreSubmitted": "submitted",
        "Submitted": "submitted",
    }

    # 最終狀態（不需要繼續輪詢）
    FINAL_STATUSES = {"Filled", "Cancelled", "Inactive", "Failed"}

    # 成功狀態
    SUCCESS_STATUSES = {"Filled", "PartFilled"}

    # 等待中狀態
    PENDING_STATUSES = {"PendingSubmit", "PreSubmitted", "Submitted", "PartFilled"}

    @classmethod
    def map_fill_status(cls, fill_status: str) -> str:
        """
        將 Shioaji 交易所狀態轉換為系統內部狀態

        Args:
            fill_status: Shioaji 回傳的狀態字串

        Returns:
            系統內部狀態字串
        """
        return cls.STATUS_MAPPING.get(fill_status, "unknown")

    @classmethod
    def is_final_status(cls, fill_status: str) -> bool:
        """
        檢查是否為最終狀態（不需要繼續輪詢）

        Args:
            fill_status: Shioaji 回傳的狀態字串

        Returns:
            True 如果是最終狀態
        """
        return fill_status in cls.FINAL_STATUSES

    @classmethod
    def is_success_status(cls, fill_status: str) -> bool:
        """
        檢查是否為成功狀態

        Args:
            fill_status: Shioaji 回傳的狀態字串

        Returns:
            True 如果是成功狀態
        """
        return fill_status in cls.SUCCESS_STATUSES

    @classmethod
    def is_pending_status(cls, fill_status: str) -> bool:
        """
        檢查是否為等待中狀態

        Args:
            fill_status: Shioaji 回傳的狀態字串

        Returns:
            True 如果是等待中狀態
        """
        return fill_status in cls.PENDING_STATUSES

    @classmethod
    def update_order_status(cls, order_record, fill_status: str) -> None:
        """
        根據交易所狀態更新訂單記錄的狀態

        Args:
            order_record: OrderHistory 資料庫記錄
            fill_status: Shioaji 回傳的狀態字串
        """
        mapped_status = cls.map_fill_status(fill_status)
        if mapped_status != "unknown":
            order_record.status = mapped_status
