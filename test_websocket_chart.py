#!/usr/bin/env python3
"""
WebSocket 圖表連線測試腳本
用於測試即時分時圖表的 WebSocket 連線
"""

import asyncio
import json
import sys
import websockets
from datetime import datetime

WS_URL = "ws://localhost:8000/ws/quotes"
TEST_SYMBOL = "TMFR1"

async def test_websocket_connection():
    """測試 WebSocket 連線和報價訂閱"""
    print("=" * 60)
    print("📊 WebSocket 圖表連線測試")
    print("=" * 60)
    
    try:
        print(f"\n🔍 連線到: {WS_URL}")
        async with websockets.connect(WS_URL) as websocket:
            print("✅ WebSocket 連線成功")
            
            # 等待連線確認訊息
            message = await websocket.recv()
            data = json.loads(message)
            print(f"📨 收到訊息: {data.get('type')}")
            
            if data.get('type') == 'connected':
                client_id = data.get('client_id')
                print(f"✅ 連線確認: client_id={client_id}")
            
            # 訂閱商品
            print(f"\n🔍 訂閱商品: {TEST_SYMBOL}")
            subscribe_msg = {
                "type": "subscribe",
                "symbol": TEST_SYMBOL,
                "simulation": True
            }
            await websocket.send(json.dumps(subscribe_msg))
            print("✅ 訂閱請求已發送")
            
            # 等待訂閱確認
            message = await websocket.recv()
            data = json.loads(message)
            print(f"📨 收到訊息: {data.get('type')}")
            
            if data.get('type') == 'subscribed':
                print(f"✅ 訂閱成功: {data.get('symbol')}")
                print(f"   商品資訊: {data.get('data')}")
            elif data.get('type') == 'error':
                print(f"❌ 訂閱失敗: {data.get('message')}")
                return False
            
            # 等待報價更新（最多等待 30 秒）
            print(f"\n🔍 等待報價更新（最多 30 秒）...")
            quote_count = 0
            
            try:
                async with asyncio.timeout(30):
                    while quote_count < 5:  # 接收 5 筆報價後結束
                        message = await websocket.recv()
                        data = json.loads(message)
                        
                        if data.get('type') == 'quote':
                            quote_count += 1
                            quote_data = data.get('data', {})
                            
                            print(f"\n📈 報價更新 #{quote_count}:")
                            print(f"   商品: {data.get('symbol')}")
                            print(f"   代碼: {quote_data.get('code')}")
                            print(f"   現價: {quote_data.get('close')}")
                            print(f"   漲跌: {quote_data.get('change_price')} ({quote_data.get('change_rate')}%)")
                            print(f"   買價: {quote_data.get('buy_price')}")
                            print(f"   賣價: {quote_data.get('sell_price')}")
                            print(f"   成交量: {quote_data.get('volume')}")
                            
                            timestamp = quote_data.get('timestamp')
                            if timestamp:
                                dt = datetime.fromtimestamp(timestamp / 1000)
                                print(f"   時間: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                        
                        elif data.get('type') == 'pong':
                            print("💓 心跳回應")
                        
                        elif data.get('type') == 'error':
                            print(f"❌ 錯誤: {data.get('message')}")
                            break
                
            except asyncio.TimeoutError:
                if quote_count == 0:
                    print("\n⚠️  30 秒內未收到報價更新")
                    print("   可能原因：")
                    print("   1. 非交易時段（日盤 08:45-13:45, 夜盤 15:00-05:00）")
                    print("   2. Trading Worker 未訂閱成功")
                    print("   3. Shioaji 連線問題")
                    return False
                else:
                    print(f"\n✅ 已收到 {quote_count} 筆報價，測試結束")
            
            # 取消訂閱
            print(f"\n🔍 取消訂閱: {TEST_SYMBOL}")
            unsubscribe_msg = {
                "type": "unsubscribe",
                "symbol": TEST_SYMBOL
            }
            await websocket.send(json.dumps(unsubscribe_msg))
            
            message = await websocket.recv()
            data = json.loads(message)
            if data.get('type') == 'unsubscribed':
                print(f"✅ 取消訂閱成功: {data.get('symbol')}")
            
            print("\n" + "=" * 60)
            print("✅ 測試完成")
            print("=" * 60)
            
            if quote_count > 0:
                print(f"\n總結: 成功接收 {quote_count} 筆報價")
                print("圖表應該可以正常顯示即時數據")
                return True
            else:
                print("\n總結: 連線正常但未收到報價")
                print("請確認：")
                print("1. 是否在交易時段")
                print("2. Trading Worker 是否正常運行")
                print("3. Shioaji 是否登入成功")
                return False
            
    except websockets.exceptions.WebSocketException as e:
        print(f"\n❌ WebSocket 錯誤: {e}")
        print("\n可能原因：")
        print("1. FastAPI 服務未啟動")
        print("2. WebSocket 端點無法訪問")
        print("3. 防火牆阻擋連線")
        return False
    
    except ConnectionRefusedError:
        print(f"\n❌ 連線被拒絕")
        print("\n解決方案：")
        print("1. 確認 FastAPI 正在運行: python main.py")
        print("2. 確認端口 8000 未被佔用")
        return False
    
    except Exception as e:
        print(f"\n❌ 未預期的錯誤: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_websocket_stats():
    """測試 WebSocket 統計 API"""
    import aiohttp
    
    print("\n🔍 測試 WebSocket 統計 API...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/ws/stats") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ WebSocket 服務狀態:")
                    print(f"   可用: {data.get('available')}")
                    print(f"   連線數: {data.get('connection_count', 0)}")
                    print(f"   訂閱商品: {data.get('subscribed_symbols', [])}")
                    return True
                else:
                    print(f"❌ HTTP {response.status}")
                    return False
    except Exception as e:
        print(f"❌ 無法連接到 FastAPI: {e}")
        return False

async def main():
    """主測試流程"""
    # 測試統計 API
    stats_ok = await test_websocket_stats()
    
    if not stats_ok:
        print("\n⚠️  WebSocket 服務未啟動，跳過連線測試")
        return 1
    
    # 測試 WebSocket 連線
    success = await test_websocket_connection()
    
    return 0 if success else 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  測試已中斷")
        sys.exit(1)
