from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Float, Numeric
import enum

from database import Base


class OrderAction(str, enum.Enum):
    LONG_ENTRY = "long_entry"
    LONG_EXIT = "long_exit"
    SHORT_ENTRY = "short_entry"
    SHORT_EXIT = "short_exit"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL_FILLED = "partial_filled"
    CANCELLED = "cancelled"
    FAILED = "failed"
    NO_ACTION = "no_action"


class OrderHistory(Base):
    __tablename__ = "order_history"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)  # Shioaji symbol (e.g., MXF202601, MXFR1)
    code = Column(String, nullable=True, index=True)  # Exchange code (e.g., MXFA6)
    action = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    order_result = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    # Order tracking fields (from Shioaji Trade object)
    order_id = Column(String, nullable=True, index=True)  # Trade.order.id
    seqno = Column(String, nullable=True)  # Trade.order.seqno
    ordno = Column(String, nullable=True)  # Trade.order.ordno
    
    # Fill tracking fields
    fill_status = Column(String, nullable=True)  # Status from exchange: PendingSubmit, Submitted, Filled, etc.
    fill_quantity = Column(Integer, nullable=True)  # Actual filled quantity
    fill_price = Column(Float, nullable=True)  # Average fill price
    cancel_quantity = Column(Integer, nullable=True)  # Cancelled quantity
    updated_at = Column(DateTime, nullable=True)  # Last status update time

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "code": self.code,
            "action": self.action,
            "quantity": self.quantity,
            "status": self.status,
            "order_result": self.order_result,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "order_id": self.order_id,
            "fill_status": self.fill_status,
            "fill_quantity": self.fill_quantity,
            "fill_price": self.fill_price,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class QuoteHistory(Base):
    """
    報價歷史資料表

    儲存 Tick 和 BidAsk 報價資料供量化分析和回測使用。
    """
    __tablename__ = "quote_history"

    id = Column(BigInteger, primary_key=True, index=True)
    symbol = Column(String(32), nullable=False, index=True)  # Shioaji symbol (如 MXFR1)
    code = Column(String(32), nullable=False, index=True)  # 交易所代碼 (如 MXFA6)
    quote_type = Column(String(10), nullable=False)  # "tick" 或 "bidask"

    # 價格欄位
    close_price = Column(Numeric(12, 2), nullable=True)
    open_price = Column(Numeric(12, 2), nullable=True)
    high_price = Column(Numeric(12, 2), nullable=True)
    low_price = Column(Numeric(12, 2), nullable=True)
    change_price = Column(Numeric(12, 2), nullable=True)
    change_rate = Column(Numeric(8, 4), nullable=True)

    # 成交量欄位
    volume = Column(Integer, nullable=True)
    total_volume = Column(Integer, nullable=True)

    # 五檔報價欄位
    buy_price = Column(Numeric(12, 2), nullable=True)
    sell_price = Column(Numeric(12, 2), nullable=True)
    buy_volume = Column(Integer, nullable=True)
    sell_volume = Column(Integer, nullable=True)

    # 時間戳
    quote_time = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        """轉換為字典"""
        def decimal_to_float(val):
            if val is None:
                return None
            return float(val) if isinstance(val, Decimal) else val

        return {
            "id": self.id,
            "symbol": self.symbol,
            "code": self.code,
            "quote_type": self.quote_type,
            "close_price": decimal_to_float(self.close_price),
            "open_price": decimal_to_float(self.open_price),
            "high_price": decimal_to_float(self.high_price),
            "low_price": decimal_to_float(self.low_price),
            "change_price": decimal_to_float(self.change_price),
            "change_rate": decimal_to_float(self.change_rate),
            "volume": self.volume,
            "total_volume": self.total_volume,
            "buy_price": decimal_to_float(self.buy_price),
            "sell_price": decimal_to_float(self.sell_price),
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
            "quote_time": self.quote_time.isoformat() if self.quote_time else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
