#!/usr/bin/env python3
"""
管理 Shioaji API 連線
"""
import subprocess
import sys

def run_command(cmd):
    """執行命令並返回輸出"""
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.stdout, result.stderr, result.returncode

def check_docker_containers():
    """檢查 Docker 容器狀態"""
    print("\n" + "=" * 50)
    print("🐳 Docker 容器狀態")
    print("=" * 50)
    
    stdout, _, _ = run_command("docker ps --format {{.Names}}")
    
    containers = []
    for line in stdout.strip().split('\n'):
        if line and line.strip():
            name = line.strip()
            containers.append(name)
            print(f"  • {name}")
    
    return containers

def stop_containers(container_names):
    """停止指定的容器"""
    print("\n[停止容器中...]")
    for name in container_names:
        print(f"  停止 {name}...")
        stdout, stderr, code = run_command(f"docker stop {name}")
        if code == 0:
            print(f"  ✅ 已停止 {name}")
        else:
            print(f"  ❌ 停止失敗: {stderr}")

def main():
    print("=" * 50)
    print("🔧 Shioaji API 連線管理工具")
    print("=" * 50)
    
    # 檢查 Docker 容器
    containers = check_docker_containers()
    
    if not containers:
        print("\n✅ 沒有找到相關的 Docker 容器")
        return
    
    print("\n" + "=" * 50)
    print("💡 建議操作")
    print("=" * 50)
    print("目前連線數已達上限 (5/5)")
    print("\n選項：")
    print("1. 停止 trading-worker (釋放 2 個連線)")
    print("2. 停止 api 容器 (釋放 2-3 個連線)")
    print("3. 停止所有相關容器")
    print("4. 取消")
    
    choice = input("\n請選擇 (1-4): ")
    
    if choice == "1":
        stop_containers(["shioaji-api-dashboard-trading-worker-1"])
    elif choice == "2":
        stop_containers(["shioaji-api-dashboard-api-1"])
    elif choice == "3":
        stop_containers([
            "shioaji-api-dashboard-trading-worker-1",
            "shioaji-api-dashboard-api-1"
        ])
    elif choice == "4":
        print("❌ 已取消")
        return
    else:
        print("❌ 無效的選擇")
        return
    
    print("\n✅ 完成！請重新檢查連線數")
    print("執行: python check_connections.py")

if __name__ == "__main__":
    main()
