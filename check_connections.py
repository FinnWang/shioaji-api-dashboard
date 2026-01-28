#!/usr/bin/env python3
"""
檢查 Shioaji API 連線數和使用量
"""
import os
import shioaji as sj
from dotenv import load_dotenv

def main():
    # 載入環境變數
    load_dotenv()
    API_KEY = os.getenv("API_KEY")
    SECRET_KEY = os.getenv("SECRET_KEY")
    CA_PATH = os.getenv("CA_PATH")
    CA_PASSWORD = os.getenv("CA_PASSWORD")
    
    if not API_KEY or not SECRET_KEY:
        print("❌ 錯誤: 請在 .env 檔案中設定 API_KEY 和 SECRET_KEY")
        return
    
    print("=" * 50)
    print("🔍 檢查 Shioaji API 連線狀態")
    print("=" * 50)
    
    api = sj.Shioaji(simulation=True)
    
    print("\n[登入中...]")
    try:
        api.login(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            contracts_timeout=10000
        )
        print("✅ 登入成功")
        
        # 查詢使用量和連線數
        print("\n[查詢 API 使用狀態...]")
        usage = api.usage()
        
        print("\n" + "=" * 50)
        print("📊 API 使用狀態")
        print("=" * 50)
        print(f"目前連線數: {usage.connections}")
        print(f"已使用流量: {usage.bytes / (1024*1024):.2f} MB")
        print(f"流量上限: {usage.limit_bytes / (1024*1024):.2f} MB")
        print(f"剩餘流量: {usage.remaining_bytes / (1024*1024):.2f} MB")
        print(f"流量使用率: {(usage.bytes / usage.limit_bytes * 100):.2f}%")
        
        # 警告訊息
        print("\n" + "=" * 50)
        print("⚠️  重要提醒")
        print("=" * 50)
        print(f"• 同一 person_id 最多允許 5 個連線")
        print(f"• 目前連線數: {usage.connections}/5")
        
        if usage.connections >= 4:
            print("⚠️  警告: 連線數接近上限！")
        
        if usage.connections >= 5:
            print("❌ 錯誤: 連線數已達上限！新的連線將被拒絕")
        
        # 登出
        print("\n[登出中...]")
        api.logout()
        print("✅ 已登出")
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return

if __name__ == "__main__":
    main()
