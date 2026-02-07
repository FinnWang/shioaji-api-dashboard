#!/usr/bin/env python3
"""
圖表 API 連線測試腳本
用於診斷即時圖表載入失敗的問題
"""

import requests
import sys
from datetime import datetime

API_URL = "https://tripple-f.zeabur.app"
TIMEOUT = 10

def test_api_health():
    """測試 API 健康狀態"""
    print("🔍 測試 API 健康狀態...")
    try:
        response = requests.get(f"{API_URL}/health", timeout=TIMEOUT)
        if response.status_code == 200:
            print(f"✅ API 健康檢查通過 (HTTP {response.status_code})")
            return True
        else:
            print(f"❌ API 健康檢查失敗 (HTTP {response.status_code})")
            return False
    except requests.exceptions.Timeout:
        print(f"❌ 連線超時 (>{TIMEOUT}秒)")
        return False
    except requests.exceptions.ConnectionError:
        print(f"❌ 無法連線到 {API_URL}")
        return False
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return False

def test_kbar_api():
    """測試 K 線數據 API"""
    print("\n🔍 測試 K 線數據 API...")
    today = datetime.now().strftime("%Y-%m-%d")
    
    try:
        url = f"{API_URL}/api/kbars/TXF?start={today}&end={today}&session=day"
        print(f"   請求: {url}")
        
        response = requests.get(url, timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('data'):
                count = len(data['data'])
                print(f"✅ K 線數據 API 正常 (取得 {count} 筆數據)")
                
                if count > 0:
                    first = data['data'][0]
                    print(f"   範例數據: open={first.get('open')}, close={first.get('close')}")
                return True
            else:
                print(f"⚠️  API 回應成功但無數據 (可能非交易時段)")
                print(f"   回應: {data}")
                return False
        else:
            print(f"❌ K 線數據 API 失敗 (HTTP {response.status_code})")
            print(f"   回應: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ 連線超時 (>{TIMEOUT}秒)")
        return False
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return False

def test_analysis_api():
    """測試支撐壓力分析 API"""
    print("\n🔍 測試支撐壓力分析 API...")
    
    try:
        url = f"{API_URL}/api/analysis/levels?symbol=TXF"
        print(f"   請求: {url}")
        
        response = requests.get(url, timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('data'):
                print(f"✅ 支撐壓力 API 正常")
                
                levels = data['data']
                if 'pivot_points' in levels:
                    pivot = levels['pivot_points']
                    print(f"   Pivot Points: R1={pivot.get('r1')}, S1={pivot.get('s1')}")
                
                return True
            else:
                print(f"⚠️  API 回應成功但無數據")
                return False
        else:
            print(f"❌ 支撐壓力 API 失敗 (HTTP {response.status_code})")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ 連線超時 (>{TIMEOUT}秒)")
        return False
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return False

def main():
    print("=" * 60)
    print("📊 即時圖表 API 連線測試")
    print("=" * 60)
    
    results = []
    
    # 測試 API 健康狀態
    results.append(("API 健康檢查", test_api_health()))
    
    # 測試 K 線 API
    results.append(("K 線數據 API", test_kbar_api()))
    
    # 測試支撐壓力 API
    results.append(("支撐壓力 API", test_analysis_api()))
    
    # 總結
    print("\n" + "=" * 60)
    print("📋 測試結果總結")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ 通過" if result else "❌ 失敗"
        print(f"{name}: {status}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\n總計: {passed}/{total} 項測試通過")
    
    if passed == total:
        print("\n✅ 所有測試通過！圖表應該可以正常載入。")
        print("   如果圖表仍然無法載入，請檢查：")
        print("   1. 瀏覽器控制台是否有 JavaScript 錯誤")
        print("   2. Lightweight Charts CDN 是否載入成功")
        print("   3. 清除瀏覽器快取後重試")
        return 0
    else:
        print("\n❌ 部分測試失敗。")
        print("\n建議解決方案：")
        print("1. 檢查網路連線")
        print("2. 確認 API 服務是否正常運作")
        print("3. 如果是非交易時段，這是正常現象")
        print("4. 考慮使用備用方案（模擬數據）")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  測試已中斷")
        sys.exit(1)
