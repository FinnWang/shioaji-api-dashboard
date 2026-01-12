"""
查詢 Shioaji API 連線數量
"""
import os
from dotenv import load_dotenv
import shioaji as sj

load_dotenv()

API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

def main():
    print("=" * 50)
    print("Shioaji API 連線數量查詢")
    print("=" * 50)
    
    api = sj.Shioaji(simulation=True)
    
    print("\n[登入中...]")
    api.login(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        contracts_timeout=10000,
    )
    print("✓ 登入成功\n")
    
    # 查詢 API 使用量
    print("-" * 50)
    print("【API 使用量】")
    print("-" * 50)
    try:
        usage = api.usage()
        print(f"  連線數:     {usage.connections} / 5")
        print(f"  已使用流量: {usage.bytes / 1024 / 1024:.2f} MB")
        print(f"  每日上限:   {usage.limit_bytes / 1024 / 1024:.0f} MB")
        print(f"  剩餘流量:   {usage.remaining_bytes / 1024 / 1024:.2f} MB ({usage.remaining_bytes / usage.limit_bytes * 100:.1f}%)")
    except Exception as e:
        print(f"  查詢失敗: {e}")
    
    print("\n" + "=" * 50)
    api.logout()
    print("✓ 已登出")

if __name__ == "__main__":
    main()
