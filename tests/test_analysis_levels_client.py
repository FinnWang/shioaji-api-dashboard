"""
AnalysisLevelsClient 單元測試

測試涵蓋：
1. AnalysisLevels 資料類功能測試
2. AnalysisLevelsClient API 呼叫測試
3. 錯誤處理測試
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from analysis_levels_client import AnalysisLevels, AnalysisLevelsClient


class TestAnalysisLevels:
    """AnalysisLevels 資料類測試"""

    def test_初始化應該設置預設值(self):
        """測試: 初始化時應該正確設置預設值"""
        # Act
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF"
        )

        # Assert
        assert levels.is_valid is True
        assert levels.symbol == "TXF"
        assert levels.price == 0
        assert levels.resistances == []
        assert levels.supports == []

    def test_get_nearest_resistance_應該返回最近壓力(self):
        """測試: 應該返回比當前價格高的最近壓力位"""
        # Arrange
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF",
            price=21500,
            resistances=[
                {"price": 21600, "strength": 2, "label": "R1"},
                {"price": 21800, "strength": 1, "label": "R2"},
                {"price": 21400, "strength": 1, "label": "已跌破"},
            ]
        )

        # Act
        result = levels.get_nearest_resistance()

        # Assert
        assert result == 21600

    def test_get_nearest_resistance_無壓力時應該返回None(self):
        """測試: 沒有比當前價格高的壓力時應該返回 None"""
        # Arrange
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF",
            price=22000,
            resistances=[
                {"price": 21600, "strength": 2, "label": "R1"},
                {"price": 21800, "strength": 1, "label": "R2"},
            ]
        )

        # Act
        result = levels.get_nearest_resistance()

        # Assert
        assert result is None

    def test_get_nearest_support_應該返回最近支撐(self):
        """測試: 應該返回比當前價格低的最近支撐位"""
        # Arrange
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF",
            price=21500,
            supports=[
                {"price": 21400, "strength": 2, "label": "S1"},
                {"price": 21200, "strength": 1, "label": "S2"},
                {"price": 21600, "strength": 1, "label": "已突破"},
            ]
        )

        # Act
        result = levels.get_nearest_support()

        # Assert
        assert result == 21400

    def test_get_nearest_support_無支撐時應該返回None(self):
        """測試: 沒有比當前價格低的支撐時應該返回 None"""
        # Arrange
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF",
            price=21000,
            supports=[
                {"price": 21400, "strength": 2, "label": "S1"},
                {"price": 21200, "strength": 1, "label": "S2"},
            ]
        )

        # Act
        result = levels.get_nearest_support()

        # Assert
        assert result is None

    def test_is_near_resistance_接近壓力時應該返回True(self):
        """測試: 價格接近壓力位時應該返回 True"""
        # Arrange
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF",
            price=21580,
            resistances=[{"price": 21600, "strength": 2, "label": "R1"}]
        )

        # Act & Assert
        assert levels.is_near_resistance(tolerance=30) is True
        assert levels.is_near_resistance(tolerance=10) is False

    def test_is_near_support_接近支撐時應該返回True(self):
        """測試: 價格接近支撐位時應該返回 True"""
        # Arrange
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF",
            price=21420,
            supports=[{"price": 21400, "strength": 2, "label": "S1"}]
        )

        # Act & Assert
        assert levels.is_near_support(tolerance=30) is True
        assert levels.is_near_support(tolerance=10) is False

    def test_get_price_position_在VWAP上方(self):
        """測試: 價格在 VWAP 上方時應該返回 above_vwap"""
        # Arrange
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF",
            price=21550,
            vwap=21500
        )

        # Act
        result = levels.get_price_position()

        # Assert
        assert result == "above_vwap"

    def test_get_price_position_在VWAP下方(self):
        """測試: 價格在 VWAP 下方時應該返回 below_vwap"""
        # Arrange
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF",
            price=21450,
            vwap=21500
        )

        # Act
        result = levels.get_price_position()

        # Assert
        assert result == "below_vwap"

    def test_get_price_position_在VWAP附近(self):
        """測試: 價格在 VWAP 附近時應該返回 at_vwap"""
        # Arrange
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF",
            price=21510,
            vwap=21500
        )

        # Act
        result = levels.get_price_position()

        # Assert
        assert result == "at_vwap"

    def test_get_price_position_無VWAP時應該返回unknown(self):
        """測試: 沒有 VWAP 數據時應該返回 unknown"""
        # Arrange
        levels = AnalysisLevels(
            is_valid=True,
            timestamp="2026-02-06T10:00:00",
            symbol="TXF",
            price=21500,
            vwap=0
        )

        # Act
        result = levels.get_price_position()

        # Assert
        assert result == "unknown"


class TestAnalysisLevelsClient:
    """AnalysisLevelsClient 測試"""

    def test_初始化應該設置正確的URL和超時(self):
        """測試: 初始化時應該正確設置 base_url 和 timeout"""
        # Act
        client = AnalysisLevelsClient("https://api.example.com/", timeout=5.0)

        # Assert
        assert client.base_url == "https://api.example.com"  # 應去除尾部斜線
        assert client.timeout == 5.0

        # Cleanup
        client.close()

    def test_context_manager_應該正確關閉連線(self):
        """測試: 使用 context manager 時應該正確關閉連線"""
        # Arrange & Act
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with AnalysisLevelsClient("https://api.example.com") as client:
                pass  # 使用 context manager

            # Assert
            mock_client.close.assert_called_once()

    @patch("httpx.Client")
    def test_get_levels_成功時應該返回正確數據(self, mock_client_class):
        """測試: API 呼叫成功時應該返回正確的 AnalysisLevels"""
        # Arrange
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "is_valid": True,
                "timestamp": "2026-02-06T10:00:00",
                "symbol": "TXF",
                "quote": {"close": 21500, "change": 100, "change_percent": 0.47},
                "pivot_points": {
                    "pp": 21450, "r1": 21550, "r2": 21650, "r3": 21750,
                    "s1": 21350, "s2": 21250, "s3": 21150
                },
                "oi_levels": {"max_pain": 21500, "resistance": 21600, "support": 21400},
                "vwap": 21480,
                "strength_levels": [
                    {"price": 21600, "type": "resistance", "strength": 2, "label": "R1+OI"},
                    {"price": 21400, "type": "support", "strength": 2, "label": "S1+OI"},
                ]
            }
        }
        mock_response.raise_for_status = Mock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Act
        with AnalysisLevelsClient("https://api.example.com") as client:
            levels = client.get_levels("TXF")

        # Assert
        assert levels.is_valid is True
        assert levels.symbol == "TXF"
        assert levels.price == 21500
        assert levels.vwap == 21480
        assert levels.pp == 21450
        assert levels.max_pain == 21500
        assert len(levels.resistances) == 1
        assert len(levels.supports) == 1

    @patch("httpx.Client")
    def test_get_levels_API失敗時應該返回無效數據(self, mock_client_class):
        """測試: API 返回失敗時應該返回 is_valid=False"""
        # Arrange
        mock_response = Mock()
        mock_response.json.return_value = {"success": False, "error": "服務不可用"}
        mock_response.raise_for_status = Mock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Act
        with AnalysisLevelsClient("https://api.example.com") as client:
            levels = client.get_levels("TXF")

        # Assert
        assert levels.is_valid is False

    @patch("httpx.Client")
    def test_get_levels_網路錯誤時應該返回無效數據(self, mock_client_class):
        """測試: 網路錯誤時應該返回 is_valid=False"""
        # Arrange
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client

        # Act
        with AnalysisLevelsClient("https://api.example.com") as client:
            levels = client.get_levels("TXF")

        # Assert
        assert levels.is_valid is False

    @patch("httpx.Client")
    def test_get_levels_simple_應該返回簡化數據(self, mock_client_class):
        """測試: get_levels_simple 應該返回簡化版數據"""
        # Arrange
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "timestamp": "2026-02-06T10:00:00",
            "price": 21500,
            "max_pain": 21500,
            "vwap": 21480,
            "resistances": [{"price": 21600, "strength": 2, "label": "R1"}],
            "supports": [{"price": 21400, "strength": 2, "label": "S1"}]
        }
        mock_response.raise_for_status = Mock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Act
        with AnalysisLevelsClient("https://api.example.com") as client:
            levels = client.get_levels_simple("TXF")

        # Assert
        assert levels.is_valid is True
        assert levels.price == 21500
        assert levels.vwap == 21480
        assert levels.max_pain == 21500
