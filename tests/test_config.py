"""
Config 單元測試

測試涵蓋：
1. 預設值設定
2. Trading Worker 連線設定
3. 訂單狀態檢查設定
"""
import pytest
from unittest.mock import patch, patch as patch_dict


class TestSettingsDefaults:
    """Settings 預設值測試"""

    def test_應該有正確的資料庫URL格式(self):
        """測試: 應該有正確的資料庫 URL 格式"""
        from config import Settings

        settings = Settings()
        assert "postgresql://" in settings.database_url

    def test_應該有正確的Redis_URL格式(self):
        """測試: 應該有正確的 Redis URL 格式"""
        from config import Settings

        settings = Settings()
        assert "redis://" in settings.redis_url

    def test_應該有auth_key設定(self):
        """測試: 應該有 auth_key 設定（非空字串）"""
        from config import Settings

        settings = Settings()
        assert settings.auth_key  # 非空字串
        assert isinstance(settings.auth_key, str)


class TestTradingWorkerSettings:
    """Trading Worker 連線設定測試"""

    def test_reconnect_delay預設值應該是5(self):
        """測試: reconnect_delay 預設值應該是 5"""
        from config import Settings

        settings = Settings()
        assert settings.reconnect_delay == 5

    def test_max_reconnect_attempts預設值應該是10(self):
        """測試: max_reconnect_attempts 預設值應該是 10"""
        from config import Settings

        settings = Settings()
        assert settings.max_reconnect_attempts == 10

    def test_queue_poll_timeout預設值應該是5(self):
        """測試: queue_poll_timeout 預設值應該是 5"""
        from config import Settings

        settings = Settings()
        assert settings.queue_poll_timeout == 5

    def test_health_check_interval預設值應該是300(self):
        """測試: health_check_interval 預設值應該是 300（5 分鐘）"""
        from config import Settings

        settings = Settings()
        assert settings.health_check_interval == 300

    def test_connection_logout_timeout預設值應該是3(self):
        """測試: connection_logout_timeout 預設值應該是 3"""
        from config import Settings

        settings = Settings()
        assert settings.connection_logout_timeout == 3

    def test_max_request_retries預設值應該是3(self):
        """測試: max_request_retries 預設值應該是 3"""
        from config import Settings

        settings = Settings()
        assert settings.max_request_retries == 3

    def test_request_retry_delay預設值應該是1(self):
        """測試: request_retry_delay 預設值應該是 1"""
        from config import Settings

        settings = Settings()
        assert settings.request_retry_delay == 1


class TestOrderStatusSettings:
    """訂單狀態檢查設定測試"""

    def test_order_status_check_delay預設值應該是2(self):
        """測試: order_status_check_delay 預設值應該是 2"""
        from config import Settings

        settings = Settings()
        assert settings.order_status_check_delay == 2

    def test_order_status_check_interval預設值應該是5(self):
        """測試: order_status_check_interval 預設值應該是 5"""
        from config import Settings

        settings = Settings()
        assert settings.order_status_check_interval == 5

    def test_order_status_max_retries預設值應該是120(self):
        """測試: order_status_max_retries 預設值應該是 120"""
        from config import Settings

        settings = Settings()
        assert settings.order_status_max_retries == 120


class TestSupportedProducts:
    """支援商品設定測試"""

    def test_supported_futures_list應該返回列表(self):
        """測試: supported_futures_list 應該返回列表"""
        from config import Settings

        settings = Settings()
        futures = settings.supported_futures_list
        assert isinstance(futures, list)
        assert "MXF" in futures
        assert "TXF" in futures

    def test_supported_options_list應該返回列表(self):
        """測試: supported_options_list 應該返回列表"""
        from config import Settings

        settings = Settings()
        options = settings.supported_options_list
        assert isinstance(options, list)
        assert "TXO" in options


class TestCredentialValidation:
    """認證驗證測試"""

    def test_validate_shioaji_credentials方法應該返回布林值(self):
        """測試: validate_shioaji_credentials 方法應該返回布林值"""
        from config import Settings

        settings = Settings()
        result = settings.validate_shioaji_credentials()
        assert isinstance(result, bool)

    def test_validate_ca_credentials方法應該返回布林值(self):
        """測試: validate_ca_credentials 方法應該返回布林值"""
        from config import Settings

        settings = Settings()
        result = settings.validate_ca_credentials()
        assert isinstance(result, bool)

    @patch.dict("os.environ", {"API_KEY": "", "SECRET_KEY": ""}, clear=False)
    def test_validate_shioaji_credentials空字串應該返回False(self):
        """測試: 空字串時 validate_shioaji_credentials 應該返回 False"""
        from config import Settings

        # 使用空字串建立設定
        settings = Settings(api_key="", secret_key="")
        assert settings.validate_shioaji_credentials() is False

    @patch.dict("os.environ", {"CA_PATH": "", "CA_PASSWORD": ""}, clear=False)
    def test_validate_ca_credentials空字串應該返回False(self):
        """測試: 空字串時 validate_ca_credentials 應該返回 False"""
        from config import Settings

        # 使用空字串建立設定
        settings = Settings(ca_path="", ca_password="")
        assert settings.validate_ca_credentials() is False
