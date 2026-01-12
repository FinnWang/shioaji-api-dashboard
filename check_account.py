"""
快速查詢 Shioaji 帳號資訊
- 帳號列表
- 期貨保證金餘額
- 證券帳戶餘額
- 未實現損益
"""
import os
from dotenv import load_dotenv
import shioaji as sj

load_dotenv()

API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

def main():
    print("=" * 50)
    print("Shioaji 帳號資訊查詢")
    print("=" * 50)
    
    # 登入 (模擬模式不需要憑證)
    api = sj.Shioaji()
    
    print("\n[登入中...]")
    accounts = api.login(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        contracts_timeout=10000,
    )
    print("✓ 登入成功\n")
    
    # 1. 帳號列表
    print("-" * 50)
    print("【帳號列表】")
    print("-" * 50)
    for acc in accounts:
        acc_type = "期貨" if hasattr(acc, 'account_id') and acc.account_type == 'F' else "證券"
        signed = "✓ 已簽署" if getattr(acc, 'signed', False) else "✗ 未簽署"
        print(f"  {acc_type}: {acc.broker_id}-{acc.account_id} ({signed})")
    
    # 2. 期貨保證金
    print("\n" + "-" * 50)
    print("【期貨保證金】")
    print("-" * 50)
    try:
        margin = api.margin(api.futopt_account)
        print(f"  前日餘額:     {margin.yesterday_balance:,.0f} 元")
        print(f"  今日餘額:     {margin.today_balance:,.0f} 元")
        print(f"  存提金額:     {margin.deposit_withdrawal:,.0f} 元")
        print(f"  權益數:       {margin.equity:,.0f} 元")
        print(f"  權益總值:     {margin.equity_amount:,.0f} 元")
        print(f"  原始保證金:   {margin.initial_margin:,.0f} 元")
        print(f"  維持保證金:   {margin.maintenance_margin:,.0f} 元")
        print(f"  可動用保證金: {margin.available_margin:,.0f} 元")
        print(f"  風險指標:     {margin.risk_indicator:.2f}%")
    except Exception as e:
        print(f"  查詢失敗: {e}")
    
    # 3. 證券帳戶餘額
    print("\n" + "-" * 50)
    print("【證券帳戶餘額】")
    print("-" * 50)
    try:
        balance = api.account_balance()
        print(f"  帳戶餘額: {balance.acc_balance:,.0f} 元")
        print(f"  查詢時間: {balance.date}")
    except Exception as e:
        print(f"  查詢失敗: {e}")
    
    # 4. 期貨未實現損益
    print("\n" + "-" * 50)
    print("【期貨持倉 (未實現損益)】")
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
    
    # 5. API 使用量
    print("\n" + "-" * 50)
    print("【API 使用量】")
    print("-" * 50)
    try:
        usage = api.usage()
        used_mb = usage.bytes / 1024 / 1024
        limit_mb = usage.limit_bytes / 1024 / 1024
        remaining_mb = usage.remaining_bytes / 1024 / 1024
        print(f"  連線數:   {usage.connections}")
        print(f"  已使用:   {used_mb:.2f} MB")
        print(f"  每日上限: {limit_mb:.0f} MB")
        print(f"  剩餘:     {remaining_mb:.2f} MB ({remaining_mb/limit_mb*100:.1f}%)")
    except Exception as e:
        print(f"  查詢失敗: {e}")
    
    print("\n" + "=" * 50)
    
    # 登出
    api.logout()
    print("✓ 已登出")

if __name__ == "__main__":
    main()
