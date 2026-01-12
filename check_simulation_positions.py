"""
查詢模擬環境持倉
"""
import os
from dotenv import load_dotenv
import shioaji as sj

load_dotenv()

API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

def main():
    print("=" * 50)
    print("模擬環境持倉查詢")
    print("=" * 50)
    
    # 登入模擬環境
    api = sj.Shioaji(simulation=True)
    
    print("\n[登入模擬環境...]")
    api.login(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        contracts_timeout=10000,
    )
    print("✓ 登入成功 (模擬模式)\n")
    
    # 帳號資訊
    print("-" * 50)
    print("【帳號資訊】")
    print("-" * 50)
    print(f"  期貨帳號: {api.futopt_account}")
    
    # 期貨持倉
    print("\n" + "-" * 50)
    print("【期貨持倉】")
    print("-" * 50)
    try:
        positions = api.list_positions(api.futopt_account)
        if positions:
            for pos in positions:
                direction = "多" if pos.direction.value == "Buy" else "空"
                print(f"  {pos.code} [{direction}] x{pos.quantity}")
                print(f"    成本: {pos.price:,.2f}, 現價: {pos.last_price:,.2f}, 損益: {pos.pnl:,.0f} 元")
        else:
            print("  (無持倉)")
    except Exception as e:
        print(f"  查詢失敗: {e}")
    
    # 查詢委託
    print("\n" + "-" * 50)
    print("【委託單列表】")
    print("-" * 50)
    try:
        api.update_status(api.futopt_account)
        trades = api.list_trades()
        if trades:
            for trade in trades:
                print(f"  {trade.contract.code}")
                print(f"    動作: {trade.order.action}, 數量: {trade.order.quantity}, 價格: {trade.order.price}")
                print(f"    狀態: {trade.status.status}")
        else:
            print("  (無委託單)")
    except Exception as e:
        print(f"  查詢失敗: {e}")
    
    print("\n" + "=" * 50)
    api.logout()
    print("✓ 已登出")

if __name__ == "__main__":
    main()
