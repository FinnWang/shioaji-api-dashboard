# 專案開發規範

## 語言偏好
**重要: 所有互動必須使用繁體中文**
- 所有回應使用繁體中文
- 程式碼註解使用繁體中文
- 文件使用繁體中文撰寫
- Commit 訊息使用繁體中文

---

## 開發規範

### 必須遵守的原則

#### 1. TDD (測試驅動開發)
**工作流程:**
- 🔴 **紅燈**: 先寫失敗的測試
- 🟢 **綠燈**: 寫最少的程式碼讓測試通過
- 🔄 **重構**: 改善程式碼品質,確保測試仍通過

**要求:**
- 每個功能都要有對應的測試
- 不先寫測試就不寫實作
- 測試覆蓋率要達到合理水準

#### 2. SOLID 原則

**S - Single Responsibility Principle (單一職責原則)**
- 每個類別只做一件事
- 一個類別只有一個改變的理由
- 避免「上帝類別」(God Class)

**O - Open/Closed Principle (開放封閉原則)**
- 對擴展開放:可以新增功能
- 對修改封閉:不修改既有程式碼
- 透過繼承、介面、組合來擴展

**L - Liskov Substitution Principle (里氏替換原則)**
- 子類別可以替換父類別
- 不破壞父類別的行為契約
- 子類別不應該改變父類別的預期行為

**I - Interface Segregation Principle (介面隔離原則)**
- 不強迫類別依賴不需要的方法
- 將大介面拆分成小介面
- 客戶端只依賴需要的介面

**D - Dependency Inversion Principle (依賴反轉原則)**
- 高層模組不依賴低層模組,都依賴抽象
- 抽象不依賴細節,細節依賴抽象
- 使用依賴注入 (Dependency Injection)

---

## 開發檢查清單

### 開發新功能前
- [ ] 是否先寫好測試案例?
- [ ] 測試案例是否涵蓋正常情況和邊界情況?
- [ ] 是否考慮了 SOLID 原則?

### 實作程式碼時
- [ ] 是否只寫讓測試通過的最少程式碼?
- [ ] 類別是否只有單一職責?
- [ ] 是否使用依賴注入而非硬編碼依賴?

### 重構時
- [ ] 重構後測試是否仍然通過?
- [ ] 程式碼是否更易讀、易維護?
- [ ] 是否移除了重複的程式碼?
- [ ] 是否符合專案的命名規範?

### 提交前
- [ ] 所有測試是否通過?
- [ ] 程式碼是否已經格式化?
- [ ] 是否有適當的繁體中文註解?
- [ ] Commit 訊息是否清楚描述變更?

---

## 程式碼範例

### ❌ 不好的範例 (違反 SOLID)

```python
# 違反單一職責原則 - 一個類別做太多事
class UserManager:
    def create_user(self, data):
        # 驗證資料
        if not data.get('email'):
            raise ValueError('Email is required')
        
        # 連接資料庫
        conn = mysql.connect(host='localhost', user='root')
        
        # 儲存使用者
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users ...")
        
        # 發送歡迎信
        smtp = smtplib.SMTP('smtp.gmail.com')
        smtp.send_email(...)
        
        # 記錄日誌
        print(f"User created: {data['email']}")
```

### ✅ 好的範例 (遵循 SOLID)

```python
# 單一職責 - 每個類別只做一件事
class UserValidator:
    """負責驗證使用者資料"""
    def validate(self, data: dict) -> bool:
        """驗證使用者資料是否有效"""
        if not data.get('email'):
            raise ValueError('Email 是必填欄位')
        return True

class UserRepository:
    """負責使用者資料的持久化"""
    def __init__(self, db_connection):
        self.db = db_connection
    
    def save(self, user: User) -> int:
        """儲存使用者到資料庫"""
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO users ...", user.to_dict())
        return cursor.lastrowid

class EmailService:
    """負責發送郵件"""
    def __init__(self, smtp_client):
        self.smtp = smtp_client
    
    def send_welcome_email(self, user: User) -> None:
        """發送歡迎郵件給新使用者"""
        self.smtp.send_email(
            to=user.email,
            subject='歡迎加入',
            body=f'歡迎 {user.name}!'
        )

class UserService:
    """協調各個服務完成使用者創建流程"""
    def __init__(
        self,
        validator: UserValidator,
        repository: UserRepository,
        email_service: EmailService,
        logger
    ):
        self.validator = validator
        self.repository = repository
        self.email_service = email_service
        self.logger = logger
    
    def create_user(self, data: dict) -> User:
        """
        創建新使用者
        
        遵循 TDD:
        1. 先寫測試驗證此方法的行為
        2. 再實作此方法
        3. 重構優化
        """
        # 驗證
        self.validator.validate(data)
        
        # 建立使用者物件
        user = User(**data)
        
        # 儲存
        user.id = self.repository.save(user)
        
        # 發送歡迎信
        self.email_service.send_welcome_email(user)
        
        # 記錄
        self.logger.info(f'使用者已創建: {user.email}')
        
        return user
```

### TDD 測試範例

```python
import pytest
from unittest.mock import Mock

class TestUserService:
    """UserService 的測試案例"""
    
    def setup_method(self):
        """每個測試前的準備工作"""
        self.validator = Mock(spec=UserValidator)
        self.repository = Mock(spec=UserRepository)
        self.email_service = Mock(spec=EmailService)
        self.logger = Mock()
        
        self.service = UserService(
            self.validator,
            self.repository,
            self.email_service,
            self.logger
        )
    
    def test_create_user_應該驗證資料(self):
        """測試: 創建使用者時應該先驗證資料"""
        # Arrange (準備)
        user_data = {'email': 'test@example.com', 'name': '測試使用者'}
        
        # Act (執行)
        self.service.create_user(user_data)
        
        # Assert (驗證)
        self.validator.validate.assert_called_once_with(user_data)
    
    def test_create_user_應該儲存使用者到資料庫(self):
        """測試: 創建使用者時應該儲存到資料庫"""
        # Arrange
        user_data = {'email': 'test@example.com', 'name': '測試使用者'}
        self.repository.save.return_value = 123
        
        # Act
        user = self.service.create_user(user_data)
        
        # Assert
        self.repository.save.assert_called_once()
        assert user.id == 123
    
    def test_create_user_應該發送歡迎郵件(self):
        """測試: 創建使用者時應該發送歡迎郵件"""
        # Arrange
        user_data = {'email': 'test@example.com', 'name': '測試使用者'}
        
        # Act
        user = self.service.create_user(user_data)
        
        # Assert
        self.email_service.send_welcome_email.assert_called_once_with(user)
    
    def test_create_user_當驗證失敗時應該拋出例外(self):
        """測試: 驗證失敗時應該拋出例外且不儲存"""
        # Arrange
        user_data = {'name': '測試使用者'}  # 缺少 email
        self.validator.validate.side_effect = ValueError('Email 是必填欄位')
        
        # Act & Assert
        with pytest.raises(ValueError, match='Email 是必填欄位'):
            self.service.create_user(user_data)
        
        # 確保沒有儲存到資料庫
        self.repository.save.assert_not_called()
```

---

## 重要提醒

當您要求 Claude Code 開發新功能時,請記得:

1. **先要求寫測試**
   ```
   "請先為這個功能寫測試案例,使用 pytest,確保涵蓋正常流程和錯誤處理"
   ```

2. **再要求實作**
   ```
   "現在請實作程式碼,讓測試通過,並遵循 SOLID 原則"
   ```

3. **最後要求重構**
   ```
   "請審查程式碼,重構改善可讀性和維護性,確保測試仍通過"
   ```

---

## Claude Code 使用提示

### 開發新功能的標準流程

```bash
# 1. 創建新分支
"請創建一個新分支叫做 feature/user-authentication"

# 2. 要求寫測試
"請先為使用者認證功能寫完整的測試案例,包含:
- 成功登入
- 密碼錯誤
- 使用者不存在
- Token 驗證"

# 3. 確認測試後再實作
"測試看起來不錯,現在請實作程式碼,確保:
- 遵循 SOLID 原則
- 使用依賴注入
- 所有註解用繁體中文"

# 4. 執行測試
"請執行測試,確保全部通過"

# 5. 重構
"請審查程式碼,看是否有可以改善的地方,重構後再次執行測試"

# 6. 提交
"請提交變更,Commit 訊息用繁體中文清楚描述做了什麼"
```

---

**記住: 好的程式碼是測試出來的,不是一次寫對的!**
