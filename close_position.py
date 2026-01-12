"""
平倉 - 模擬環境
"""
import os
from dotenv import load_dotenv
import shioaji as sj

load_dotenv()

API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

def main():
    print("=" * 60)
    print("平倉 - 模擬環境")
    print("=" * 60)
    
    # 登入模擬環境
    api = sj.Shioaji(simulation=True)
    
    print("\n[登入模擬環境...]")
    api.login(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        contracts_timeout=10000,
    )
    print("✓ 登入成功\n")
    
    # 查詢持倉
    print("-" * 60)
    print("【查詢持倉】")
    print("-" * 60)
    positions = api.list_positions(api.futopt_account)
    
    if not positions:
        print("  (無持倉，不需平倉)")
        api.logout()
        return
    
    for pos in positions:
        direction = "多" if pos.direction.value == "Buy" else "空"
        print(f"  {pos.code} [{direction}] x{pos.quantity}")
        print(f"    成本: {pos.price:,.2f}, 現價: {pos.last_price:,.2f}, 損益: {pos.pnl:,.0f} 元")
    
    # 平倉
    print("\n" + "-" * 60)
    print("【執行平倉】")
    print("-" * 60)
    
    for pos in positions:
        # 取得合約
        contract = api.Contracts.Futures[pos.code]
        
        # 多單平倉 -> 賣出, 空單平倉 -> 買進
        if pos.direction == sj.constant.Action.Buy:
            close_action = sj.constant.Action.Sell
            direction_str = "多單"
        else:
            close_action = sj.constant.Action.Buy
            direction_str = "空單"
        
        print(f"\n  平倉 {pos.code} {direction_str} x{pos.quantity}")
        
        order = api.Order(
            action=close_action,
            price=0,
            quantity=pos.quantity,
            price_type=sj.constant.FuturesPriceType.MKT,
            order_type=sj.constant.OrderType.IOC,
            octype=sj.constant.FuturesOCType.Cover,  # 平倉
            account=api.futopt_account,
        )
        
        try:
            trade = api.place_order(contract, order)
            print(f"  ✓ 平倉委託成功")
            print(f"    Order ID: {trade.order.id}")
            print(f"    狀態: {trade.status.status}")
        except Exception as e:
            print(f"  ✗ 平倉失敗: {e}")
    
    # 確認平倉結果
    print("\n" + "-" * 60)
    print("【平倉後持倉】")
    print("-" * 60)
    
    import time
    time.sleep(1)
    
    positions_after = api.list_positions(api.futopt_account)
    if positions_after:
        for pos in positions_after:
            direction = "多" if pos.direction.value == "Buy" else "空"
            print(f"  {pos.code} [{direction}] x{pos.quantity}")
    else:
        print("  (已全部平倉)")
    
    print("\n" + "=" * 60)
    api.logout()
    print("✓ 已登出")

if __name__ == "__main__":
    main()
