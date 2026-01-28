import logging
from typing import TYPE_CHECKING, List

import shioaji as sj
from shioaji.contracts import Contract
from shioaji.error import (
    TokenError,
    SystemMaintenance,
    TimeoutError as SjTimeoutError,
    AccountNotSignError,
    AccountNotProvideError,
    TargetContractNotExistError,
)

from config import settings

logger = logging.getLogger(__name__)

# 從統一配置取得支援的商品
SUPPORTED_FUTURES = settings.supported_futures_list
SUPPORTED_OPTIONS = settings.supported_options_list
logger.info(f"Supported futures: {SUPPORTED_FUTURES}")
logger.info(f"Supported options: {SUPPORTED_OPTIONS}")


class ShioajiError(Exception):
    """Base exception for Shioaji operations."""
    pass


class LoginError(ShioajiError):
    """Raised when login fails."""
    pass


class OrderError(ShioajiError):
    """Raised when order placement fails."""
    pass


def get_api_client(simulation: bool = True):
    logger.debug(f"Creating API client with simulation={simulation}")

    if not settings.validate_shioaji_credentials():
        logger.error("API_KEY or SECRET_KEY environment variable not set")
        raise LoginError("API_KEY or SECRET_KEY environment variable not set")

    try:
        api = sj.Shioaji(simulation=simulation)
        api.login(api_key=settings.api_key, secret_key=settings.secret_key)
        logger.debug("API client logged in successfully")

        # Activate CA certificate for real trading
        if not simulation:
            if not settings.validate_ca_credentials():
                logger.error("CA_PATH or CA_PASSWORD not set for real trading")
                raise LoginError(
                    "Real trading requires CA certificate. "
                    "Please set CA_PATH and CA_PASSWORD environment variables."
                )
            
            # Get person_id from account (Taiwan National ID / 身分證字號)
            # It's automatically available after login
            accounts = api.list_accounts()
            if not accounts:
                raise LoginError("No accounts found after login")
            
            person_id = accounts[0].person_id
            logger.info(f"Activating CA certificate from {ca_path} for person_id={person_id}")
            
            result = api.activate_ca(
                ca_path=settings.ca_path,
                ca_passwd=settings.ca_password,
                person_id=person_id,
            )
            logger.info(f"CA activation result: {result}")
        
        return api
    except TokenError as e:
        logger.error(f"Authentication failed: {e}")
        raise LoginError(f"Authentication failed: {e}") from e
    except SystemMaintenance as e:
        logger.error(f"System is under maintenance: {e}")
        raise LoginError(f"System is under maintenance: {e}") from e
    except SjTimeoutError as e:
        logger.error(f"Login timeout: {e}")
        raise LoginError(f"Login timeout: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}")
        raise LoginError(f"Unexpected error during login: {e}") from e


def _get_futures_contracts(api: sj.Shioaji) -> List[Contract]:
    """Get all contracts from supported futures products."""
    contracts = []
    for product in SUPPORTED_FUTURES:
        product_contracts = getattr(api.Contracts.Futures, product, None)
        if product_contracts:
            contracts.extend([c for c in product_contracts if c.symbol.startswith(product)])
        else:
            logger.warning(f"Futures product '{product}' not found in api.Contracts.Futures")
    return contracts


def _get_options_contracts(api: sj.Shioaji) -> List[Contract]:
    """Get all contracts from supported options products."""
    contracts = []
    for product in SUPPORTED_OPTIONS:
        product_contracts = getattr(api.Contracts.Options, product, None)
        if product_contracts:
            # Options have many contracts, limit to reasonable number
            contracts.extend([c for c in product_contracts][:100])  # Limit to first 100
        else:
            logger.warning(f"Options product '{product}' not found in api.Contracts.Options")
    return contracts


def get_valid_symbols(api: sj.Shioaji) -> List[str]:
    """Get all valid trading symbols from supported futures and options."""
    futures = [contract.symbol for contract in _get_futures_contracts(api)]
    options = [contract.symbol for contract in _get_options_contracts(api)]
    return futures + options


def get_valid_symbols_with_info(api: sj.Shioaji) -> List[dict]:
    """
    Get all valid trading symbols with their codes from supported futures and options.
    
    Returns list of dicts with:
    - symbol: Contract symbol - use this for trading
    - code: Contract code
    - name: Contract name
    - type: 'futures' or 'options'
    """
    result = []
    
    # Futures
    for contract in _get_futures_contracts(api):
        result.append({
            "symbol": contract.symbol,
            "code": contract.code,
            "name": contract.name,
            "type": "futures",
        })
    
    # Options
    for contract in _get_options_contracts(api):
        result.append({
            "symbol": contract.symbol,
            "code": contract.code,
            "name": contract.name,
            "type": "options",
        })
    
    return result


def get_valid_contract_codes(api: sj.Shioaji) -> List[str]:
    """Get all valid contract codes from supported futures."""
    return [contract.code for contract in _get_futures_contracts(api)]


def get_contract_from_symbol(api: sj.Shioaji, symbol: str) -> Contract:
    """Find a contract by its symbol (supports both futures and options)."""
    # Try futures first
    for contract in _get_futures_contracts(api):
        if contract.symbol == symbol:
            return contract
    
    # Try options
    for contract in _get_options_contracts(api):
        if contract.symbol == symbol:
            return contract
    
    raise ValueError(f"Contract {symbol} not found in supported futures/options: {SUPPORTED_FUTURES}/{SUPPORTED_OPTIONS}")


def get_contract_from_contract_code(api: sj.Shioaji, contract_code: str) -> Contract:
    """Find a contract by its contract code (supports both futures and options)."""
    # Try futures first
    for contract in _get_futures_contracts(api):
        if contract.code == contract_code:
            return contract
    
    # Try options
    for contract in _get_options_contracts(api):
        if contract.code == contract_code:
            return contract
    
    raise ValueError(f"Contract {contract_code} not found in supported futures/options: {SUPPORTED_FUTURES}/{SUPPORTED_OPTIONS}")


def get_current_position(api: sj.Shioaji, contract: Contract):
    logger.debug(f"Getting current position for contract: {contract.code}")
    for position in api.list_positions(api.futopt_account):
        if contract.code == position.code:
            # FuturePosition uses 'direction' not 'side'
            direction = position.direction
            if direction == sj.constant.Action.Buy:
                logger.debug(f"Found long position: {position.quantity}")
                return position.quantity
            elif direction == sj.constant.Action.Sell:
                logger.debug(f"Found short position: {-position.quantity}")
                return -position.quantity
            else:
                raise ValueError(f"Position {position.code} has invalid direction: {direction}")
    logger.debug("No position found")
    return None


def place_entry_order(
    api: sj.Shioaji, symbol: str, quantity: int, action: sj.constant.Action
):
    logger.debug(f"Placing entry order: symbol={symbol}, quantity={quantity}, action={action}")
    
    try:
        contract = get_contract_from_symbol(api, symbol)
    except ValueError as e:
        logger.error(f"Contract not found: {e}")
        raise OrderError(f"Contract not found: {e}") from e
    
    try:
        current_position = get_current_position(api, contract) or 0
        logger.debug(f"Current position: {current_position}")
    except (AccountNotSignError, AccountNotProvideError) as e:
        logger.error(f"Account error when getting position: {e}")
        raise OrderError(f"Account error: {e}") from e

    original_quantity = quantity
    if action == sj.constant.Action.Buy and current_position < 0:
        quantity = quantity - current_position
        logger.debug(f"Adjusting quantity for short reversal: {original_quantity} -> {quantity}")
    elif action == sj.constant.Action.Sell and current_position > 0:
        quantity = quantity + current_position
        logger.debug(f"Adjusting quantity for long reversal: {original_quantity} -> {quantity}")

    order = api.Order(
        action=action,
        price=0.0,
        quantity=quantity,
        price_type=sj.constant.FuturesPriceType.MKT,
        order_type=sj.constant.OrderType.IOC,
        octype=sj.constant.FuturesOCType.Auto,
        account=api.futopt_account,
    )

    try:
        logger.debug(f"Submitting order: action={action}, quantity={quantity}")
        result = api.place_order(contract, order)
        logger.debug(f"Order result: {result}")
        return result
    except TargetContractNotExistError as e:
        logger.error(f"Target contract not exist: {e}")
        raise OrderError(f"Target contract not exist: {e}") from e
    except SjTimeoutError as e:
        logger.error(f"Order timeout: {e}")
        raise OrderError(f"Order timeout: {e}") from e
    except (AccountNotSignError, AccountNotProvideError) as e:
        logger.error(f"Account error when placing order: {e}")
        raise OrderError(f"Account error: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error when placing order: {e}")
        raise OrderError(f"Unexpected error when placing order: {e}") from e


def place_exit_order(api: sj.Shioaji, symbol: str, position_direction: sj.constant.Action):
    logger.debug(f"Placing exit order: symbol={symbol}, position_direction={position_direction}")
    
    try:
        contract = get_contract_from_symbol(api, symbol)
    except ValueError as e:
        logger.error(f"Contract not found: {e}")
        raise OrderError(f"Contract not found: {e}") from e
    
    try:
        current_position = get_current_position(api, contract) or 0
        logger.debug(f"Current position: {current_position}")
    except (AccountNotSignError, AccountNotProvideError) as e:
        logger.error(f"Account error when getting position: {e}")
        raise OrderError(f"Account error: {e}") from e

    # close long
    if position_direction == sj.constant.Action.Buy and current_position > 0:
        logger.debug(f"Closing long position: selling {current_position}")
        order = api.Order(
            action=sj.constant.Action.Sell,
            price=0.0,
            quantity=current_position,
            price_type=sj.constant.FuturesPriceType.MKT,
            order_type=sj.constant.OrderType.IOC,
            octype=sj.constant.FuturesOCType.Auto,
            account=api.futopt_account,
        )
    # close short
    elif position_direction == sj.constant.Action.Sell and current_position < 0:
        logger.debug(f"Closing short position: buying {-current_position}")
        order = api.Order(
            action=sj.constant.Action.Buy,
            price=0.0,
            quantity=-current_position,
            price_type=sj.constant.FuturesPriceType.MKT,
            order_type=sj.constant.OrderType.IOC,
            octype=sj.constant.FuturesOCType.Auto,
            account=api.futopt_account,
        )
    else:
        logger.debug("No position to exit")
        return None

    try:
        result = api.place_order(contract, order)
        logger.debug(f"Order result: {result}")
        return result
    except TargetContractNotExistError as e:
        logger.error(f"Target contract not exist: {e}")
        raise OrderError(f"Target contract not exist: {e}") from e
    except SjTimeoutError as e:
        logger.error(f"Order timeout: {e}")
        raise OrderError(f"Order timeout: {e}") from e
    except (AccountNotSignError, AccountNotProvideError) as e:
        logger.error(f"Account error when placing order: {e}")
        raise OrderError(f"Account error: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error when placing order: {e}")
        raise OrderError(f"Unexpected error when placing order: {e}") from e


def check_order_status(api: sj.Shioaji, trade) -> dict:
    """
    Check the actual fill status of an order by calling update_status.
    
    According to Shioaji source code:
    - update_status() updates the trade object in-place (doesn't return anything)
    - OrderStatus has: status, deal_quantity, cancel_quantity, deals, order_quantity
    - Status enum: PendingSubmit, PreSubmitted, Submitted, PartFilled, Filled, Cancelled, Failed, Inactive
    
    Ref: https://sinotrade.github.io/zh/tutor/order/FutureOption/#_2
    
    Returns a dict with:
        - status: str (PendingSubmit, Submitted, Filled, PartFilled, Cancelled, Failed, Inactive)
        - order_quantity: int
        - deal_quantity: int (filled quantity from OrderStatus)
        - cancel_quantity: int
        - deals: list of deal info (price, quantity, timestamp)
        - fill_avg_price: float (average fill price calculated from deals)
    """
    if trade is None:
        logger.warning("check_order_status called with trade=None")
        return {"status": "no_trade", "error": "No trade object provided"}
    
    order_id = getattr(trade.order, 'id', 'unknown')
    seqno = getattr(trade.order, 'seqno', 'unknown')
    
    try:
        logger.debug(f"Calling api.update_status(trade=...) for order_id={order_id}, seqno={seqno}")
        
        # update_status() updates trade object in-place, passing trade= for specific trade update
        api.update_status(trade=trade)
        
        # Extract status info from updated trade object
        status_obj = trade.status
        order_obj = trade.order
        
        # Get status value - Status is an Enum
        status_value = status_obj.status.value if hasattr(status_obj.status, 'value') else str(status_obj.status)
        
        logger.debug(
            f"Raw status from exchange: status={status_value}, "
            f"status_code={getattr(status_obj, 'status_code', '')}, "
            f"msg={getattr(status_obj, 'msg', '')}"
        )
        
        # Get deals list for calculating average price
        deals = status_obj.deals if status_obj.deals else []
        
        # Use deal_quantity from OrderStatus (this is the official filled quantity)
        deal_quantity = status_obj.deal_quantity if hasattr(status_obj, 'deal_quantity') else 0
        
        # Calculate average fill price from deals
        total_value = sum(d.price * d.quantity for d in deals) if deals else 0
        total_qty = sum(d.quantity for d in deals) if deals else 0
        fill_avg_price = total_value / total_qty if total_qty > 0 else 0.0
        
        # Log deal details if any
        if deals:
            logger.debug(f"Found {len(deals)} deal(s) for order_id={order_id}:")
            for i, d in enumerate(deals):
                logger.debug(f"  Deal[{i}]: seq={getattr(d, 'seq', '')}, qty={d.quantity}, price={d.price}, ts={getattr(d, 'ts', 0)}")
        
        result = {
            "status": status_value,
            "status_code": getattr(status_obj, 'status_code', ''),
            "msg": getattr(status_obj, 'msg', ''),
            "order_id": getattr(order_obj, 'id', ''),
            "seqno": getattr(order_obj, 'seqno', ''),
            "ordno": getattr(order_obj, 'ordno', ''),
            "order_quantity": getattr(status_obj, 'order_quantity', 0) or order_obj.quantity,
            "deal_quantity": deal_quantity,
            "cancel_quantity": getattr(status_obj, 'cancel_quantity', 0),
            "fill_avg_price": fill_avg_price,
            "deals": [
                {
                    "seq": getattr(d, 'seq', ''),
                    "price": d.price,
                    "quantity": d.quantity,
                    "ts": getattr(d, 'ts', 0),
                }
                for d in deals
            ],
        }
        
        return result
        
    except Exception as e:
        logger.exception(f"Error checking order status for order_id={order_id}: {e}")
        return {"status": "error", "error": str(e)}


def list_trades(api: sj.Shioaji) -> List[dict]:
    """
    Get list of all trades (成交紀錄).
    
    Returns list of trade records with details like:
    - code: contract code
    - price: trade price
    - quantity: trade quantity
    - ts: timestamp
    """
    try:
        logger.debug("Fetching trades list")
        trades = api.list_trades()
        
        result = []
        for trade in trades:
            result.append({
                "code": getattr(trade, 'code', ''),
                "order_id": getattr(trade, 'order_id', ''),
                "seqno": getattr(trade, 'seqno', ''),
                "price": getattr(trade, 'price', 0),
                "quantity": getattr(trade, 'quantity', 0),
                "action": str(getattr(trade, 'action', '')),
                "ts": getattr(trade, 'ts', 0),
            })
        
        logger.debug(f"Found {len(result)} trades")
        return result
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        raise OrderError(f"Failed to fetch trades: {e}") from e


def list_settlements(api: sj.Shioaji) -> List[dict]:
    """
    Get settlement records (結算資料).
    
    Returns list of settlement records.
    """
    try:
        logger.debug("Fetching settlements")
        settlements = api.list_settlements(api.futopt_account)
        
        # Handle None or empty response
        if settlements is None:
            logger.debug("No settlements data returned (None)")
            return []
        
        result = []
        for settlement in settlements:
            result.append({
                "date": str(getattr(settlement, 'date', '')),
                "amount": getattr(settlement, 'amount', 0),
                "T_money": getattr(settlement, 'T_money', 0),
                "T1_money": getattr(settlement, 'T1_money', 0),
            })
        
        logger.debug(f"Found {len(result)} settlements")
        return result
    except Exception as e:
        logger.error(f"Error fetching settlements: {e}")
        raise OrderError(f"Failed to fetch settlements: {e}") from e


def list_profit_loss(api: sj.Shioaji) -> dict:
    """
    Get profit/loss summary (損益).
    
    Returns profit/loss information.
    """
    try:
        logger.debug("Fetching profit/loss")
        pnl = api.list_profit_loss(api.futopt_account)
        
        result = {
            "realized_pnl": getattr(pnl, 'realized_pnl', 0),
            "unrealized_pnl": getattr(pnl, 'unrealized_pnl', 0),
            "total_pnl": getattr(pnl, 'total_pnl', 0),
        }
        
        logger.debug(f"P&L: realized={result['realized_pnl']}, unrealized={result['unrealized_pnl']}")
        return result
    except Exception as e:
        logger.error(f"Error fetching profit/loss: {e}")
        raise OrderError(f"Failed to fetch profit/loss: {e}") from e


def get_margin(api: sj.Shioaji) -> dict:
    """
    Get margin information (保證金).
    
    Ref: https://sinotrade.github.io/zh/tutor/accounting/margin/
    
    Returns margin details including:
    - yesterday_balance: 昨日餘額
    - today_balance: 今日餘額
    - available_margin: 可用保證金
    - equity: 權益數
    - initial_margin: 原始保證金
    - maintenance_margin: 維持保證金
    - margin_call: 追繳保證金
    - risk_indicator: 風險指標
    """
    try:
        logger.debug("Fetching margin info")
        margin = api.margin(api.futopt_account)
        
        result = {
            # 帳戶餘額
            "yesterday_balance": getattr(margin, 'yesterday_balance', 0.0),
            "today_balance": getattr(margin, 'today_balance', 0.0),
            "deposit_withdrawal": getattr(margin, 'deposit_withdrawal', 0.0),
            # 保證金相關
            "available_margin": getattr(margin, 'available_margin', 0.0),
            "initial_margin": getattr(margin, 'initial_margin', 0.0),
            "maintenance_margin": getattr(margin, 'maintenance_margin', 0.0),
            "margin_call": getattr(margin, 'margin_call', 0.0),
            # 權益與風險
            "equity": getattr(margin, 'equity', 0.0),
            "equity_amount": getattr(margin, 'equity_amount', 0.0),
            "risk_indicator": getattr(margin, 'risk_indicator', 0.0),
            # 期貨部位
            "future_open_position": getattr(margin, 'future_open_position', 0.0),
            "today_future_open_position": getattr(margin, 'today_future_open_position', 0.0),
            "future_settle_profitloss": getattr(margin, 'future_settle_profitloss', 0.0),
            # 選擇權部位
            "option_openbuy_market_value": getattr(margin, 'option_openbuy_market_value', 0.0),
            "option_opensell_market_value": getattr(margin, 'option_opensell_market_value', 0.0),
            "option_open_position": getattr(margin, 'option_open_position', 0.0),
            "option_settle_profitloss": getattr(margin, 'option_settle_profitloss', 0.0),
            # 其他
            "fee": getattr(margin, 'fee', 0.0),
            "tax": getattr(margin, 'tax', 0.0),
            "royalty_revenue_expenditure": getattr(margin, 'royalty_revenue_expenditure', 0.0),
            "order_margin_premium": getattr(margin, 'order_margin_premium', 0.0),
        }
        
        logger.debug(f"Margin: today_balance={result['today_balance']}, available={result['available_margin']}, equity={result['equity']}")
        return result
    except Exception as e:
        logger.error(f"Error fetching margin: {e}")
        raise OrderError(f"Failed to fetch margin: {e}") from e


def get_snapshot(api: sj.Shioaji, contract: Contract) -> dict | None:
    """
    Get real-time snapshot quote for a contract.
    
    Uses api.snapshots() to get current market data including:
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
    
    Ref: https://sinotrade.github.io/zh/tutor/market_data/snapshot/
    
    Args:
        api: Shioaji API client
        contract: Contract to get snapshot for
        
    Returns:
        dict with snapshot data, or None if unavailable
    """
    try:
        logger.debug(f"Getting snapshot for {contract.symbol}")
        snapshots = api.snapshots([contract])
        
        if not snapshots:
            logger.warning(f"No snapshot data for {contract.symbol}")
            return None
        
        snap = snapshots[0]
        
        # Convert nanosecond timestamp to milliseconds
        ts_ms = getattr(snap, 'ts', 0) // 1_000_000 if getattr(snap, 'ts', 0) else 0
        
        result = {
            "symbol": contract.symbol,
            "close": getattr(snap, 'close', 0.0),
            "open": getattr(snap, 'open', 0.0),
            "high": getattr(snap, 'high', 0.0),
            "low": getattr(snap, 'low', 0.0),
            "buy_price": getattr(snap, 'buy_price', 0.0),
            "sell_price": getattr(snap, 'sell_price', 0.0),
            "buy_volume": getattr(snap, 'buy_volume', 0),
            "sell_volume": getattr(snap, 'sell_volume', 0),
            "volume": getattr(snap, 'volume', 0),
            "total_volume": getattr(snap, 'total_volume', 0),
            "change_price": getattr(snap, 'change_price', 0.0),
            "change_rate": getattr(snap, 'change_rate', 0.0),
            "amount": getattr(snap, 'amount', 0.0),
            "total_amount": getattr(snap, 'total_amount', 0.0),
            "ts": ts_ms,
        }
        
        logger.debug(f"Snapshot for {contract.symbol}: close={result['close']}, buy={result['buy_price']}, sell={result['sell_price']}")
        return result
        
    except Exception as e:
        logger.error(f"Error getting snapshot for {contract.symbol}: {e}")
        return None
