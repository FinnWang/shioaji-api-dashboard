#!/usr/bin/env python3
"""
測試價格類型功能 (TDD 原則)
"""
import pytest
from unittest.mock import Mock, patch
from main import OrderRequest


class TestPriceTypeFeature:
    """測試價格類型功能的各種情況"""
    
    def test_order_request_market_order_validation(self):
        """測試市價單的驗證邏輯"""
        # 市價單不需要價格
        order = OrderRequest(
            action="long_entry",
            quantity=1,
            symbol="TMFR1",
            price_type="MKT"
        )
        assert order.price_type == "MKT"
        assert order.price is None
    
    def test_order_request_limit_order_validation(self):
        """測試限價單的驗證邏輯"""
        # 限價單需要價格
        order = OrderRequest(
            action="long_entry",
            quantity=1,
            symbol="TMFR1",
            price_type="LMT",
            price=23500.0
        )
        assert order.price_type == "LMT"
        assert order.price == 23500.0
    
    def test_order_request_limit_order_missing_price(self):
        """測試限價單缺少價格時的驗證錯誤"""
        with pytest.raises(ValueError, match="price must be provided"):
            OrderRequest(
                action="long_entry",
                quantity=1,
                symbol="TMFR1",
                price_type="LMT"
                # 缺少 price
            )
    
    def test_order_request_invalid_price_type(self):
        """測試無效價格類型的驗證錯誤"""
        with pytest.raises(ValueError, match="price_type must be"):
            OrderRequest(
                action="long_entry",
                quantity=1,
                symbol="TMFR1",
                price_type="INVALID"
            )
    
    def test_order_request_default_price_type(self):
        """測試預設價格類型為市價單"""
        order = OrderRequest(
            action="long_entry",
            quantity=1,
            symbol="TMFR1"
            # 不指定 price_type，應該預設為 MKT
        )
        assert order.price_type == "MKT"
        assert order.price is None
    
    def test_order_request_limit_order_zero_price(self):
        """測試限價單價格為0時的驗證錯誤"""
        with pytest.raises(ValueError, match="price must be provided and > 0"):
            OrderRequest(
                action="long_entry",
                quantity=1,
                symbol="TMFR1",
                price_type="LMT",
                price=0.0
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])