"""
測試期貨下單 - 近月台指期貨 (TXF)
"""
import os
from dotenv import load_dotenv
import shioaji as sj

load_dotenv()

API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

def main():
    print("=" * 60)
    print("期貨下單測試 - 近月台指期貨")
    print("=" * 60)
    
    # 登入 (模擬模式)
    api = sj.Shioaji(simulation=True)
    
    print("\n[登入中...]")
    api.login(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        contracts_timeout=10000,
    )
    print("✓ 登入成功 (模擬模式)\n")
    
    # 顯示帳號資訊
    print("-" * 60)
    print("【帳號資訊】")
    print("-" * 60)
    print(f"  期貨帳號: {api.futopt_account}")
    
    # 商品檔 - 近月台指期貨
    print("\n" + "-" * 60)
    print("【取得近月台指期貨合約】")
    print("-" * 60)
    
    # 過濾掉 R1, R2 (連續月合約)，取最近到期的合約
    txf_contracts = [
        x for x in api.Contracts.Futures.TXF 
        if x.code[-2:] not in ["R1", "R2"]
    ]
    
    if not txf_contracts:
        print("  ✗ 找不到 TXF 合約")
        api.logout()
        return
    
    contract = min(txf_contracts, key=lambda x: x.delivery_date)
    
    print(f"  合約代碼: {contract.code}")
    print(f"  合約名稱: {contract.name}")
    print(f"  交割日期: {contract.delivery_date}")
    print(f"  Symbol:   {contract.symbol}")
    print(f"  參考價:   {contract.reference}")
    print(f"  漲停價:   {contract.limit_up}")
    print(f"  跌停價:   {contract.limit_down}")
    
    # 建立期貨委託單 - 使用市價單 (MKT + IOC)
    print("\n" + "-" * 60)
    print("【建立期貨委託單 - 市價單】")
    print("-" * 60)
    
    order = api.Order(
        action=sj.constant.Action.Buy,                   # 買賣別: 買進
        price=0,                                         # 市價單價格設為 0
        quantity=1,                                      # 數量
        price_type=sj.constant.FuturesPriceType.MKT,     # 委託價格類別: 市價
        order_type=sj.constant.OrderType.IOC,            # 委託條件: IOC (立即成交否則取消)
        octype=sj.constant.FuturesOCType.Auto,           # 倉別: 自動
        account=api.futopt_account                       # 下單帳號
    )
    
    print(f"  買賣別:   {order.action}")
    print(f"  價格:     {order.price}")
    print(f"  數量:     {order.quantity}")
    print(f"  價格類別: {order.price_type}")
    print(f"  委託條件: {order.order_type}")
    print(f"  倉別:     {order.octype}")
    
    # 下單
    print("\n" + "-" * 60)
    print("【執行下單】")
    print("-" * 60)
    
    try:
        trade = api.place_order(contract, order)
        print("✓ 下單成功!")
        print(f"\n  Trade 物件:")
        print(f"    contract: {trade.contract}")
        print(f"    order:    {trade.order}")
        print(f"    status:   {trade.status}")
    except Exception as e:
        print(f"✗ 下單失敗: {e}")
    
    print("\n" + "=" * 60)
    
    # 登出
    api.logout()
    print("✓ 已登出")

if __name__ == "__main__":
    main()
