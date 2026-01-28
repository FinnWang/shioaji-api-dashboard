from contextlib import asynccontextmanager
import csv
from datetime import datetime, timezone
import io
import logging
import os
import time
from typing import Literal, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from config import settings
from database import get_db, SessionLocal
from models import OrderHistory
from status_mapper import OrderStatusMapper
from trading_queue import get_queue_client, TradingQueueClient

logger = logging.getLogger(__name__)


ACCEPT_ACTIONS = Literal["long_entry", "long_exit", "short_entry", "short_exit"]


async def verify_auth_key(x_auth_key: str = Header(..., alias="X-Auth-Key")):
    if x_auth_key != settings.auth_key:
        raise HTTPException(status_code=401, detail="Invalid authentication key")
    return x_auth_key


class OrderRequest(BaseModel):
    action: ACCEPT_ACTIONS
    quantity: int = Field(..., gt=0)
    symbol: str
    price_type: str = Field(default="MKT", description="Price type: MKT (market) or LMT (limit)")
    price: Optional[float] = Field(default=None, description="Price for limit orders")

    @model_validator(mode="after")
    def validate_order_params(self):
        # Symbol validation is now done via the trading worker
        # We'll validate during order processing instead
        
        # Validate price type
        if self.price_type not in ["MKT", "LMT"]:
            raise ValueError("price_type must be 'MKT' or 'LMT'")
        
        # Validate price for limit orders
        if self.price_type == "LMT":
            if self.price is None or self.price <= 0:
                raise ValueError("price must be provided and > 0 for limit orders")
        
        return self


class OrderHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    code: Optional[str] = None
    action: str
    quantity: int
    status: str
    order_result: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    order_id: Optional[str] = None
    fill_status: Optional[str] = None
    fill_quantity: Optional[int] = None
    fill_price: Optional[float] = None
    updated_at: Optional[datetime] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - database migrations are handled by separate migration service
    yield
    # Shutdown (cleanup if needed)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Background task configuration
ORDER_STATUS_CHECK_DELAY = 2  # seconds to wait before first check
ORDER_STATUS_CHECK_INTERVAL = 5  # seconds between retry checks
ORDER_STATUS_MAX_RETRIES = 120  # max number of status checks (~10 minutes total)


def _log_fill_status_change(order_id: int, fill_status: str, status_info: dict, deals: list):
    """記錄訂單成交狀態變更的日誌（輔助函數）"""
    if fill_status == "Filled":
        logger.info(
            f"[BG] ✓ Order {order_id} FILLED: "
            f"qty={status_info.get('deal_quantity')}, "
            f"avg_price={status_info.get('fill_avg_price')}, "
            f"deals={len(deals)}"
        )
    elif fill_status == "PartFilled":
        logger.info(
            f"[BG] ~ Order {order_id} PARTIAL: "
            f"filled={status_info.get('deal_quantity')}/{status_info.get('order_quantity')}, "
            f"avg_price={status_info.get('fill_avg_price')}"
        )
    elif fill_status == "Cancelled":
        logger.info(
            f"[BG] ✗ Order {order_id} CANCELLED: "
            f"cancel_qty={status_info.get('cancel_quantity')}, "
            f"msg={status_info.get('msg')}"
        )
    elif fill_status == "Inactive":
        logger.info(f"[BG] ✗ Order {order_id} INACTIVE (expired/rejected): msg={status_info.get('msg')}")
    elif fill_status == "Failed":
        logger.error(
            f"[BG] ✗ Order {order_id} FAILED: "
            f"msg={status_info.get('msg') or status_info.get('error')}, "
            f"status_code={status_info.get('status_code')}"
        )
    elif OrderStatusMapper.map_fill_status(fill_status) == "unknown":
        logger.warning(f"[BG] Order {order_id} unknown status: {fill_status}")


def verify_order_fill(
    order_id: int,
    trade_order_id: str,
    trade_seqno: str,
    simulation: bool,
):
    """
    Background task to verify order fill status via Redis queue.
    
    According to Shioaji docs, after placing an order, the status is 'PendingSubmit'.
    We need to call update_status to get the actual status from the exchange.
    
    Ref: https://sinotrade.github.io/zh/tutor/order/FutureOption/#_2
    """
    logger.info(f"[BG] Starting order verification: order_id={order_id}, simulation={simulation}")
    
    # Wait before first check to allow order to reach exchange
    logger.debug(f"[BG] Waiting {ORDER_STATUS_CHECK_DELAY}s before first check...")
    time.sleep(ORDER_STATUS_CHECK_DELAY)
    
    # Database connection with retry logic
    db = None
    db_max_retries = 3
    
    def get_db_session():
        """Get a new database session with retry logic."""
        nonlocal db
        for retry in range(db_max_retries):
            try:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass
                db = SessionLocal()
                # Test connection
                db.execute(text("SELECT 1"))
                return db
            except OperationalError as e:
                logger.warning(f"[BG] DB connection failed (attempt {retry + 1}/{db_max_retries}): {e}")
                time.sleep(2 ** retry)  # Exponential backoff: 1s, 2s, 4s
        raise OperationalError("Failed to connect to database after retries", None, None)
    
    def safe_db_commit():
        """Safely commit with error handling."""
        nonlocal db
        try:
            db.commit()
            return True
        except OperationalError as e:
            logger.error(f"[BG] DB commit failed (connection error): {e}")
            try:
                db.rollback()
            except Exception:
                pass
            # Try to reconnect
            try:
                db = get_db_session()
                return False  # Caller should retry the operation
            except Exception:
                return False
        except SQLAlchemyError as e:
            logger.error(f"[BG] DB commit failed: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return False
    
    last_status = None
    order_record = None
    
    try:
        # Initialize database connection
        db = get_db_session()
        logger.debug(f"[BG] Database connection established")
        
        # Get queue client for status checks
        queue_client = get_queue_client()
        logger.info(f"[BG] Queue client ready, starting status checks (max {ORDER_STATUS_MAX_RETRIES} checks, {ORDER_STATUS_CHECK_INTERVAL}s interval)")
        
        for attempt in range(ORDER_STATUS_MAX_RETRIES):
            # Check order status via queue
            try:
                response = queue_client.check_order_status(
                    order_id=trade_order_id,
                    seqno=trade_seqno,
                    simulation=simulation,
                )
                
                if not response.success:
                    logger.warning(f"[BG] Status check failed: {response.error}")
                    time.sleep(ORDER_STATUS_CHECK_INTERVAL)
                    continue
                    
                status_info = response.data
            except (TimeoutError, ConnectionError) as e:
                logger.warning(f"[BG] Queue error during status check: {e}")
                time.sleep(ORDER_STATUS_CHECK_INTERVAL)
                continue
            
            fill_status = status_info.get("status", "unknown")
            
            # Log status change or periodic update (every 12 checks = ~1 minute)
            if fill_status != last_status:
                logger.info(f"[BG] Order {order_id} status changed: {last_status} -> {fill_status}")
                last_status = fill_status
            elif attempt % 12 == 0 and attempt > 0:
                elapsed = attempt * ORDER_STATUS_CHECK_INTERVAL
                logger.info(f"[BG] Order {order_id} still {fill_status} after {elapsed}s ({attempt}/{ORDER_STATUS_MAX_RETRIES} checks)")
            
            # Log detailed status info at debug level
            logger.debug(
                f"[BG] Check {attempt + 1}/{ORDER_STATUS_MAX_RETRIES}: "
                f"status={fill_status}, "
                f"deal_qty={status_info.get('deal_quantity', 0)}, "
                f"cancel_qty={status_info.get('cancel_quantity', 0)}, "
                f"order_qty={status_info.get('order_quantity', 0)}, "
                f"seqno={status_info.get('seqno')}, "
                f"ordno={status_info.get('ordno')}"
            )
            
            # Log deals if any
            deals = status_info.get("deals", [])
            if deals:
                for deal in deals:
                    logger.info(f"[BG] Order {order_id} DEAL: qty={deal.get('quantity')}, price={deal.get('price')}, ts={deal.get('ts')}")
            
            # Update database record with error handling
            try:
                order_record = db.query(OrderHistory).filter(OrderHistory.id == order_id).first()
            except OperationalError as e:
                logger.warning(f"[BG] DB query failed, reconnecting: {e}")
                try:
                    db = get_db_session()
                    order_record = db.query(OrderHistory).filter(OrderHistory.id == order_id).first()
                except Exception as reconnect_error:
                    logger.error(f"[BG] DB reconnect failed: {reconnect_error}")
                    time.sleep(ORDER_STATUS_CHECK_INTERVAL)
                    continue
            
            if order_record:
                order_record.fill_status = fill_status
                order_record.order_id = status_info.get("order_id")
                order_record.seqno = status_info.get("seqno")
                order_record.ordno = status_info.get("ordno")
                order_record.fill_quantity = status_info.get("deal_quantity", 0)
                order_record.fill_price = status_info.get("fill_avg_price")
                order_record.cancel_quantity = status_info.get("cancel_quantity", 0)
                order_record.updated_at = datetime.now(timezone.utc)

                # 使用 StatusMapper 統一更新狀態
                OrderStatusMapper.update_order_status(order_record, fill_status)

                # 處理 Failed 狀態的錯誤訊息
                if fill_status == "Failed":
                    error_msg = status_info.get("msg") or status_info.get("error", "Order failed at exchange")
                    order_record.error_message = error_msg

                # 提交並記錄日誌
                if fill_status == "error":
                    logger.error(f"[BG] Error checking order {order_id}: {status_info.get('error')}")
                    safe_db_commit()
                elif safe_db_commit():
                    _log_fill_status_change(order_id, fill_status, status_info, deals)

                # 最終狀態時停止輪詢
                if OrderStatusMapper.is_final_status(fill_status):
                    break
            else:
                logger.error(f"[BG] Order record not found in database: order_id={order_id}")
            
            # Wait before next check
            time.sleep(ORDER_STATUS_CHECK_INTERVAL)
        
        # Final status after all retries
        if order_record and order_record.status == "submitted":
            total_time = ORDER_STATUS_CHECK_DELAY + (ORDER_STATUS_MAX_RETRIES * ORDER_STATUS_CHECK_INTERVAL)
            logger.warning(
                f"[BG] ⚠ Order {order_id} timeout: still '{fill_status}' after {total_time}s "
                f"({ORDER_STATUS_MAX_RETRIES} checks). Last status_code={status_info.get('status_code')}"
            )
            
    except OperationalError as e:
        logger.error(f"[BG] Database connection error for order {order_id}: {e}")
    except SQLAlchemyError as e:
        logger.error(f"[BG] Database error for order {order_id}: {e}")
    except Exception as e:
        logger.exception(f"[BG] Error verifying order {order_id}: {e}")
    finally:
        if db is not None:
            try:
                db.close()
            except Exception as e:
                logger.debug(f"[BG] Error closing DB session: {e}")
        logger.debug(f"[BG] Order {order_id} verification completed")


@app.get("/futures")
async def list_futures_products(
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """
    Get all available futures products (first level).
    
    Returns a list of product codes (e.g., TXF, MXF, EXF) with their names.
    Use /futures/{code} to see all contracts for a specific product.
    """
    try:
        queue_client = get_queue_client()
        response = queue_client.get_futures_overview(simulation=simulation)
        
        if not response.success:
            raise HTTPException(status_code=503, detail=response.error)
        
        # Transform the response to match the expected format
        products = []
        for p in response.data.get("products", []):
            contracts = p.get("contracts", [])
            if contracts:
                products.append({
                    "code": p["product"],
                    "name": contracts[0].get("name", "N/A"),
                    "contract_count": len(contracts),
                })
        
        # Sort by code
        products.sort(key=lambda x: x['code'])
        
        return {
            "products": products,
            "count": len(products),
        }
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")


@app.get("/futures/{code}")
async def list_futures_contracts(
    code: str,
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """
    Get all contracts for a specific futures product (second level).
    
    Example: /futures/TXF returns all TXF contracts (TXFK5, TXFL5, etc.)
    """
    try:
        queue_client = get_queue_client()
        response = queue_client.get_product_contracts(product=code, simulation=simulation)
        
        if not response.success:
            if "not found" in (response.error or "").lower():
                raise HTTPException(
                    status_code=404, 
                    detail=f"Futures product '{code}' not found. Use /futures to see available products."
                )
            raise HTTPException(status_code=503, detail=response.error)
        
        contracts = response.data.get("contracts", [])
        
        return {
            "product_code": code.upper(),
            "product_name": contracts[0].get('name', 'N/A') if contracts else 'N/A',
            "contracts": contracts,
            "count": len(contracts),
        }
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")


@app.get("/symbols")
async def list_symbols(
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """Get list of valid trading symbols from SUPPORTED_FUTURES (configured in ENV)."""
    try:
        queue_client = get_queue_client()
        response = queue_client.get_symbols(simulation=simulation)
        
        if not response.success:
            raise HTTPException(status_code=503, detail=response.error)
        
        return response.data
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")


@app.get("/symbols/{symbol}")
async def get_symbol_details(
    symbol: str,
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """Get detailed information about a specific symbol."""
    try:
        queue_client = get_queue_client()
        response = queue_client.get_symbol_info(symbol=symbol, simulation=simulation)
        
        if not response.success:
            if "not found" in (response.error or "").lower():
                raise HTTPException(status_code=404, detail=response.error)
            raise HTTPException(status_code=503, detail=response.error)
        
        return response.data
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")


@app.get("/symbols/{symbol}/snapshot")
async def get_symbol_snapshot(
    symbol: str,
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """
    Get real-time snapshot quote for a symbol (即時報價).
    
    Returns current market data including:
    - close: 最新成交價
    - open: 開盤價
    - high: 最高價
    - low: 最低價
    - buy_price: 買價
    - sell_price: 賣價
    - change_price: 漲跌
    - change_rate: 漲跌幅 (%)
    - volume: 單量
    - total_volume: 總量
    
    Note: Subject to API rate limits (5秒上限 50次)
    """
    try:
        queue_client = get_queue_client()
        response = queue_client.get_snapshot(symbol=symbol, simulation=simulation)
        
        if not response.success:
            if "not found" in (response.error or "").lower():
                raise HTTPException(status_code=404, detail=response.error)
            raise HTTPException(status_code=503, detail=response.error)
        
        return response.data
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")


@app.get("/contracts")
async def list_contracts(
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """Get list of valid contract codes."""
    try:
        queue_client = get_queue_client()
        response = queue_client.get_contract_codes(simulation=simulation)
        
        if not response.success:
            raise HTTPException(status_code=503, detail=response.error)
        
        return response.data
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")


@app.get("/positions")
async def list_positions(
    _: str = Depends(verify_auth_key),
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """Get current futures/options positions. Ref: https://sinotrade.github.io/zh/tutor/accounting/position/"""
    try:
        queue_client = get_queue_client()
        response = queue_client.get_positions(simulation=simulation)
        
        if not response.success:
            raise HTTPException(status_code=503, detail=response.error)
        
        return response.data
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/order")
async def create_order(
    order_request: OrderRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    simulation: bool = Query(True, description="Use simulation mode (default: True)"),
):
    """
    Place a trading order. The order is submitted and a background task verifies
    the actual fill status from the exchange.
    
    According to Shioaji docs, after place_order returns, the status is 'PendingSubmit'.
    The background task calls update_status to get the actual status (Filled, Cancelled, etc.).
    
    Ref: https://sinotrade.github.io/zh/tutor/order/FutureOption/#_2
    """
    order_history = OrderHistory(
        symbol=order_request.symbol,
        action=order_request.action,
        quantity=order_request.quantity,
        status="pending",
        fill_status="PendingSubmit",
    )

    try:
        queue_client = get_queue_client()
    except (ConnectionError, Exception) as e:
        order_history.status = "failed"
        order_history.error_message = str(e)
        db.add(order_history)
        db.commit()
        raise HTTPException(status_code=503, detail=str(e))

    response = None
    try:
        if order_request.action == "long_entry":
            response = queue_client.place_entry_order(
                symbol=order_request.symbol,
                quantity=order_request.quantity,
                action="Buy",
                simulation=simulation,
                price_type=order_request.price_type,
                price=order_request.price,
            )
        elif order_request.action == "short_entry":
            response = queue_client.place_entry_order(
                symbol=order_request.symbol,
                quantity=order_request.quantity,
                action="Sell",
                simulation=simulation,
                price_type=order_request.price_type,
                price=order_request.price,
            )
        elif order_request.action == "long_exit":
            response = queue_client.place_exit_order(
                symbol=order_request.symbol,
                position_direction="Buy",
                simulation=simulation,
                price_type=order_request.price_type,
                price=order_request.price,
            )
        elif order_request.action == "short_exit":
            response = queue_client.place_exit_order(
                symbol=order_request.symbol,
                position_direction="Sell",
                simulation=simulation,
                price_type=order_request.price_type,
                price=order_request.price,
            )
            
        if response and not response.success:
            order_history.status = "failed"
            order_history.error_message = response.error
            db.add(order_history)
            db.commit()
            raise HTTPException(status_code=400, detail=response.error)
            
    except (TimeoutError, ConnectionError) as e:
        order_history.status = "failed"
        order_history.error_message = str(e)
        db.add(order_history)
        db.commit()
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")

    if response is None or response.data is None:
        order_history.status = "failed"
        order_history.error_message = "No response from trading service"
        db.add(order_history)
        db.commit()
        raise HTTPException(status_code=500, detail="No response from trading service")

    result_data = response.data
    
    # Check if it's a no-action response (no position to exit)
    if result_data.get("order_id") is None and result_data.get("message"):
        order_history.status = "no_action"
        order_history.fill_status = None
        db.add(order_history)
        db.commit()
        return {"status": "no_action", "message": result_data.get("message", "No position to exit or invalid action")}

    # Extract order info from result
    order_history.order_id = result_data.get("order_id")
    order_history.seqno = result_data.get("seqno")
    order_history.ordno = result_data.get("ordno")
    
    # Update symbol/code with resolved values from trading worker
    # (user may send code like MXFA6, but we store canonical symbol like MXF202601)
    if result_data.get("symbol"):
        order_history.symbol = result_data.get("symbol")
    if result_data.get("code"):
        order_history.code = result_data.get("code")
    
    # For exit orders, update quantity with actual traded quantity from position
    # (user's request quantity is ignored for exits - actual is determined by position size)
    if order_request.action in ("long_exit", "short_exit") and result_data.get("quantity"):
        order_history.quantity = result_data.get("quantity")

    # Initial status is "submitted" (order accepted, pending verification)
    order_history.status = "submitted"
    order_history.order_result = str(result_data)
    db.add(order_history)
    db.commit()
    db.refresh(order_history)
    
    # Spawn background task to verify fill status
    if result_data.get("order_id") and result_data.get("seqno"):
        background_tasks.add_task(
            verify_order_fill,
            order_id=order_history.id,
            trade_order_id=result_data.get("order_id"),
            trade_seqno=result_data.get("seqno"),
            simulation=simulation,
        )

    return {
        "status": "submitted",
        "order_id": order_history.id,
        "message": "Order submitted. Fill status will be verified in background.",
        "order": result_data,
    }


@app.get("/orders", response_model=list[OrderHistoryResponse])
async def get_orders(
    db: Session = Depends(get_db),
    _: str = Depends(verify_auth_key),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    action: Optional[str] = Query(None, description="Filter by action"),
    status: Optional[str] = Query(None, description="Filter by status"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    limit: int = Query(100, ge=1, le=1000, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    query = db.query(OrderHistory)

    if symbol:
        query = query.filter(OrderHistory.symbol == symbol)
    if action:
        query = query.filter(OrderHistory.action == action)
    if status:
        query = query.filter(OrderHistory.status == status)
    if start_date:
        query = query.filter(OrderHistory.created_at >= start_date)
    if end_date:
        query = query.filter(OrderHistory.created_at <= end_date)

    orders = query.order_by(OrderHistory.created_at.desc()).offset(offset).limit(limit).all()
    return orders


@app.get("/orders/export")
async def export_orders(
    db: Session = Depends(get_db),
    _: str = Depends(verify_auth_key),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    action: Optional[str] = Query(None, description="Filter by action"),
    status: Optional[str] = Query(None, description="Filter by status"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    format: str = Query("csv", description="Export format: csv or json"),
):
    query = db.query(OrderHistory)

    if symbol:
        query = query.filter(OrderHistory.symbol == symbol)
    if action:
        query = query.filter(OrderHistory.action == action)
    if status:
        query = query.filter(OrderHistory.status == status)
    if start_date:
        query = query.filter(OrderHistory.created_at >= start_date)
    if end_date:
        query = query.filter(OrderHistory.created_at <= end_date)

    orders = query.order_by(OrderHistory.created_at.desc()).all()

    if format == "json":
        return [order.to_dict() for order in orders]

    # CSV export
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "symbol", "action", "quantity", "status", "order_result", "error_message", "created_at"])

    for order in orders:
        writer.writerow([
            order.id,
            order.symbol,
            order.action,
            order.quantity,
            order.status,
            order.order_result,
            order.error_message,
            order.created_at.isoformat() if order.created_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=order_history.csv"},
    )


@app.post("/orders/{order_id}/recheck")
async def recheck_order_status(
    order_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_auth_key),
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """
    Manually re-check an order's fill status from the exchange.
    
    This performs a single status check (not a background loop) and updates the database.
    Useful for orders where the background task may have timed out or for manual verification.
    """
    # Get order from database
    order_record = db.query(OrderHistory).filter(OrderHistory.id == order_id).first()
    if not order_record:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    
    # Check if order has the necessary info to re-check
    if not order_record.seqno or not order_record.order_id:
        raise HTTPException(
            status_code=400, 
            detail="Order does not have seqno/order_id - cannot re-check status. This may be a failed or no_action order."
        )
    
    try:
        queue_client = get_queue_client()
        response = queue_client.check_order_status(
            order_id=order_record.order_id,
            seqno=order_record.seqno,
            simulation=simulation,
        )
        
        if not response.success:
            # Trade not found in current session - might have been from previous session
            if "not found" in (response.error or "").lower():
                return {
                    "order_id": order_id,
                    "status": "not_found_in_session",
                    "message": "Trade not found in current API session. The order may be from a previous trading session.",
                    "current_db_status": order_record.status,
                    "current_fill_status": order_record.fill_status,
                }
            raise HTTPException(status_code=503, detail=response.error)
        
        status_info = response.data
        fill_status = status_info.get("status", "unknown")
        
        # Get deals and calculate average price
        deals = status_info.get("deals", [])
        deal_quantity = status_info.get("deal_quantity", 0)
        fill_avg_price = status_info.get("fill_avg_price", 0.0)
        
        # Update database record
        old_status = order_record.status
        old_fill_status = order_record.fill_status
        
        order_record.fill_status = fill_status
        order_record.ordno = status_info.get("ordno")
        order_record.fill_quantity = deal_quantity
        order_record.fill_price = fill_avg_price
        order_record.cancel_quantity = status_info.get("cancel_quantity", 0)
        order_record.updated_at = datetime.now(timezone.utc)

        # 使用 StatusMapper 統一更新狀態
        OrderStatusMapper.update_order_status(order_record, fill_status)

        db.commit()
        db.refresh(order_record)
        
        return {
            "order_id": order_id,
            "previous_status": old_status,
            "current_status": order_record.status,
            "previous_fill_status": old_fill_status,
            "current_fill_status": fill_status,
            "fill_quantity": deal_quantity,
            "fill_price": fill_avg_price,
            "deals": deals,
            "message": "Order status updated successfully",
        }
        
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trades")
async def get_trades(
    _: str = Depends(verify_auth_key),
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """Get list of all trades (成交紀錄)."""
    try:
        queue_client = get_queue_client()
        response = queue_client.list_trades(simulation=simulation)
        
        if not response.success:
            raise HTTPException(status_code=503, detail=response.error)
        
        return response.data
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/settlements")
async def get_settlements(
    _: str = Depends(verify_auth_key),
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """Get settlement records (結算資料)."""
    try:
        queue_client = get_queue_client()
        response = queue_client.list_settlements(simulation=simulation)
        
        if not response.success:
            raise HTTPException(status_code=503, detail=response.error)
        
        return response.data
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/profit-loss")
async def get_profit_loss(
    _: str = Depends(verify_auth_key),
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """Get profit/loss summary (損益)."""
    try:
        queue_client = get_queue_client()
        response = queue_client.list_profit_loss(simulation=simulation)
        
        if not response.success:
            raise HTTPException(status_code=503, detail=response.error)
        
        return response.data
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/margin")
async def get_margin_info(
    _: str = Depends(verify_auth_key),
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """Get margin information (保證金)."""
    try:
        queue_client = get_queue_client()
        response = queue_client.get_margin(simulation=simulation)
        
        if not response.success:
            raise HTTPException(status_code=503, detail=response.error)
        
        return response.data
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/usage")
async def get_api_usage(
    _: str = Depends(verify_auth_key),
    simulation: bool = Query(True, description="Use simulation mode"),
):
    """Get API usage information (連線數、流量)."""
    try:
        queue_client = get_queue_client()
        response = queue_client.get_usage(simulation=simulation)
        
        if not response.success:
            raise HTTPException(status_code=503, detail=response.error)
        
        return response.data
    except (TimeoutError, ConnectionError) as e:
        raise HTTPException(status_code=503, detail=f"Trading service unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Mount static files directory for CSS, JS, etc.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health_check():
    """Check the health of the API and trading worker."""
    try:
        queue_client = get_queue_client()
        worker_healthy = queue_client.check_worker_health()
        
        return {
            "api": "healthy",
            "trading_worker": "healthy" if worker_healthy else "unhealthy",
            "redis": "connected",
        }
    except Exception as e:
        return {
            "api": "healthy",
            "trading_worker": "unknown",
            "redis": "disconnected",
            "error": str(e),
        }


@app.get("/dashboard")
async def dashboard():
    """Serve the dashboard HTML page."""
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"), media_type="text/html")
