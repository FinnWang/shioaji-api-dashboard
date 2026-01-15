# 開發規範

## 必須遵守的原則

1. **TDD (測試驅動開發)**
   - 先寫測試，再寫實作
   - 紅燈 → 綠燈 → 重構 循環
   - 每個功能都要有對應的測試

2. **SOLID 原則**
   - **S**ingle Responsibility: 單一職責，每個類別只做一件事
   - **O**pen/Closed: 開放擴展，封閉修改
   - **L**iskov Substitution: 子類別可替換父類別
   - **I**nterface Segregation: 介面隔離，不強迫依賴不需要的方法
   - **D**ependency Inversion: 依賴抽象，不依賴具體實作

## 執行提醒

每次開發新功能或修改程式碼前，請確認：
- [ ] 是否先寫好測試案例？
- [ ] 是否符合 SOLID 原則？
- [ ] 重構後測試是否仍然通過？
