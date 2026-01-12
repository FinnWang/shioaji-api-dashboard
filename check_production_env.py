"""
確認正式環境是否可用
- 檢查 API 登入
- 檢查 CA 憑證
- 檢查帳號簽署狀態
"""
import os
from dotenv import load_dotenv
import shioaji as sj

load_dotenv()

API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
CA_PATH = os.getenv("CA_PATH")
CA_PASSWORD = os.getenv("CA_PASSWORD")

def main():
    print("=" * 60)
    print("正式環境檢查")
    print("=" * 60)
    
    # 1. 檢查環境變數
    print("\n" + "-" * 60)
    print("【環境變數檢查】")
    print("-" * 60)
    print(f"  API_KEY:     {'✓ 已設定' if API_KEY else '✗ 未設定'}")
    print(f"  SECRET_KEY:  {'✓ 已設定' if SECRET_KEY else '✗ 未設定'}")
    print(f"  CA_PATH:     {CA_PATH if CA_PATH else '✗ 未設定'}")
    print(f"  CA_PASSWORD: {'✓ 已設定' if CA_PASSWORD else '✗ 未設定'}")
    
    # 2. 檢查 CA 憑證檔案
    print("\n" + "-" * 60)
    print("【CA 憑證檔案檢查】")
    print("-" * 60)
    if CA_PATH:
        if os.path.exists(CA_PATH):
            print(f"  ✓ 憑證檔案存在: {CA_PATH}")
        else:
            print(f"  ✗ 憑證檔案不存在: {CA_PATH}")
    else:
        print("  ✗ CA_PATH 未設定")
    
    # 3. 登入正式環境
    print("\n" + "-" * 60)
    print("【正式環境登入測試】")
    print("-" * 60)
    
    try:
        api = sj.Shioaji(simulation=False)  # 正式環境
        
        print("  [登入中...]")
        accounts = api.login(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            contracts_timeout=10000,
        )
        print("  ✓ 登入成功")
        
        # 4. 帳號資訊
        print("\n" + "-" * 60)
        print("【帳號資訊】")
        print("-" * 60)
        for acc in accounts:
            acc_type = "期貨" if acc.account_type == 'F' else "證券"
            signed = "✓ 已簽署" if getattr(acc, 'signed', False) else "✗ 未簽署"
            print(f"  {acc_type}: {acc.broker_id}-{acc.account_id} ({signed})")
        
        # 5. 啟用 CA 憑證
        print("\n" + "-" * 60)
        print("【CA 憑證啟用】")
        print("-" * 60)
        
        if CA_PATH and CA_PASSWORD and os.path.exists(CA_PATH):
            try:
                person_id = accounts[0].person_id
                print(f"  [啟用 CA 憑證中...] person_id={person_id}")
                
                result = api.activate_ca(
                    ca_path=CA_PATH,
                    ca_passwd=CA_PASSWORD,
                    person_id=person_id,
                )
                print(f"  ✓ CA 憑證啟用成功: {result}")
            except Exception as e:
                print(f"  ✗ CA 憑證啟用失敗: {e}")
        else:
            print("  ✗ 無法啟用 CA 憑證 (缺少設定或檔案)")
        
        # 6. 查詢保證金 (測試帳務功能)
        print("\n" + "-" * 60)
        print("【期貨保證金查詢】")
        print("-" * 60)
        try:
            margin = api.margin(api.futopt_account)
            print(f"  今日餘額:     {margin.today_balance:,.0f} 元")
            print(f"  可動用保證金: {margin.available_margin:,.0f} 元")
            print(f"  權益數:       {margin.equity:,.0f} 元")
        except Exception as e:
            print(f"  查詢失敗: {e}")
        
        # 7. 查詢持倉
        print("\n" + "-" * 60)
        print("【期貨持倉】")
        print("-" * 60)
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
        
        # 8. 總結
        print("\n" + "=" * 60)
        print("【正式環境狀態總結】")
        print("=" * 60)
        
        can_trade = True
        issues = []
        
        if not all([API_KEY, SECRET_KEY]):
            can_trade = False
            issues.append("API 金鑰未設定")
        
        if not CA_PATH or not os.path.exists(CA_PATH):
            can_trade = False
            issues.append("CA 憑證檔案不存在")
        
        if not CA_PASSWORD:
            can_trade = False
            issues.append("CA 密碼未設定")
        
        # 檢查帳號簽署狀態
        futopt_signed = getattr(api.futopt_account, 'signed', False)
        if not futopt_signed:
            can_trade = False
            issues.append("期貨帳號未簽署")
        
        if can_trade:
            print("  ✓ 正式環境可以使用！")
        else:
            print("  ✗ 正式環境尚未就緒")
            for issue in issues:
                print(f"    - {issue}")
        
        api.logout()
        print("\n✓ 已登出")
        
    except Exception as e:
        print(f"  ✗ 登入失敗: {e}")

if __name__ == "__main__":
    main()
