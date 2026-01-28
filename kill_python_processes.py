#!/usr/bin/env python3
"""
終止所有 Python 程序以釋放 Shioaji 連線
"""
import subprocess
import sys

def main():
    print("=" * 50)
    print("🔍 查找運行中的 Python 程序")
    print("=" * 50)
    
    try:
        # 查找所有 python.exe 程序
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV'],
            capture_output=True,
            text=True
        )
        
        if 'python.exe' not in result.stdout:
            print("✅ 沒有找到運行中的 Python 程序")
            return
        
        # 解析輸出
        lines = result.stdout.strip().split('\n')[1:]  # 跳過標題行
        pids = []
        
        for line in lines:
            if 'python.exe' in line:
                parts = line.replace('"', '').split(',')
                if len(parts) >= 2:
                    pid = parts[1].strip()
                    pids.append(pid)
                    print(f"找到 Python 程序: PID {pid}")
        
        if not pids:
            print("✅ 沒有找到需要終止的程序")
            return
        
        # 詢問是否終止
        print(f"\n找到 {len(pids)} 個 Python 程序")
        response = input("是否終止這些程序？(y/n): ")
        
        if response.lower() != 'y':
            print("❌ 已取消")
            return
        
        # 終止程序
        print("\n[終止程序中...]")
        for pid in pids:
            try:
                subprocess.run(['taskkill', '/F', '/PID', pid], check=True)
                print(f"✅ 已終止 PID {pid}")
            except subprocess.CalledProcessError:
                print(f"⚠️  無法終止 PID {pid}")
        
        print("\n✅ 完成！請重新檢查連線數")
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
