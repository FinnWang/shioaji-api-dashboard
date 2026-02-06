"""
測試模擬/實盤模式功能

測試範圍：
1. OrderHistory 模型的 simulation 欄位
2. API 依模式篩選訂單
3. 下單時正確記錄模式
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, OrderHistory


@pytest.fixture
def db_session():
    """建立測試用資料庫 session"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestOrderHistorySimulationField:
    """測試 OrderHistory 模型的 simulation 欄位"""

    def test_simulation_field_default_value(self, db_session):
        """測試 simulation 欄位預設值為 1 (模擬模式)"""
        order = OrderHistory(
            symbol="TXF",
            action="Buy",
            quantity=1,
            status="pending"
        )
        db_session.add(order)
        db_session.commit()

        assert order.simulation == 1

    def test_simulation_field_can_be_set_to_production(self, db_session):
        """測試可以設定為實盤模式 (0)"""
        order = OrderHistory(
            symbol="TXF",
            action="Buy",
            quantity=1,
            status="pending",
            simulation=0
        )
        db_session.add(order)
        db_session.commit()

        assert order.simulation == 0

    def test_to_dict_converts_simulation_to_bool(self, db_session):
        """測試 to_dict() 將 simulation 轉換為布林值"""
        # 模擬模式
        sim_order = OrderHistory(
            symbol="TXF",
            action="Buy",
            quantity=1,
            status="pending",
            simulation=1
        )
        db_session.add(sim_order)
        db_session.commit()

        sim_dict = sim_order.to_dict()
        assert sim_dict["simulation"] is True

        # 實盤模式
        prod_order = OrderHistory(
            symbol="TXF",
            action="Sell",
            quantity=1,
            status="pending",
            simulation=0
        )
        db_session.add(prod_order)
        db_session.commit()

        prod_dict = prod_order.to_dict()
        assert prod_dict["simulation"] is False


class TestSimulationModeFiltering:
    """測試依模式篩選訂單功能"""

    @pytest.fixture
    def sample_orders(self, db_session):
        """建立測試用訂單資料"""
        orders = [
            OrderHistory(
                symbol="TXF",
                action="Buy",
                quantity=1,
                status="filled",
                simulation=1,  # 模擬
                fill_price=18000.0,
                created_at=datetime(2026, 2, 6, 10, 0, 0, tzinfo=timezone.utc)
            ),
            OrderHistory(
                symbol="TXF",
                action="Sell",
                quantity=1,
                status="filled",
                simulation=1,  # 模擬
                fill_price=18100.0,
                created_at=datetime(2026, 2, 6, 11, 0, 0, tzinfo=timezone.utc)
            ),
            OrderHistory(
                symbol="TXF",
                action="Buy",
                quantity=2,
                status="filled",
                simulation=0,  # 實盤
                fill_price=18200.0,
                created_at=datetime(2026, 2, 6, 12, 0, 0, tzinfo=timezone.utc)
            ),
            OrderHistory(
                symbol="TXF",
                action="Sell",
                quantity=2,
                status="filled",
                simulation=0,  # 實盤
                fill_price=18300.0,
                created_at=datetime(2026, 2, 6, 13, 0, 0, tzinfo=timezone.utc)
            ),
        ]
        for order in orders:
            db_session.add(order)
        db_session.commit()
        return orders

    def test_filter_simulation_mode_only(self, db_session, sample_orders):
        """測試只篩選模擬模式訂單"""
        result = db_session.query(OrderHistory).filter(
            OrderHistory.simulation == 1
        ).all()

        assert len(result) == 2
        assert all(order.simulation == 1 for order in result)

    def test_filter_production_mode_only(self, db_session, sample_orders):
        """測試只篩選實盤模式訂單"""
        result = db_session.query(OrderHistory).filter(
            OrderHistory.simulation == 0
        ).all()

        assert len(result) == 2
        assert all(order.simulation == 0 for order in result)

    def test_no_filter_returns_all(self, db_session, sample_orders):
        """測試不篩選時回傳所有訂單"""
        result = db_session.query(OrderHistory).all()

        assert len(result) == 4

    def test_combined_filters(self, db_session, sample_orders):
        """測試組合篩選條件 (模式 + 商品 + 動作)"""
        result = db_session.query(OrderHistory).filter(
            OrderHistory.simulation == 1,
            OrderHistory.symbol == "TXF",
            OrderHistory.action == "Buy"
        ).all()

        assert len(result) == 1
        assert result[0].simulation == 1
        assert result[0].action == "Buy"


class TestSimulationModeIndexes:
    """測試 simulation 欄位的索引"""

    def test_simulation_index_exists(self, db_session):
        """測試 simulation 欄位有建立索引"""
        # 檢查 Column 定義中的 index 屬性
        assert OrderHistory.simulation.index is True
        
        # 建立測試資料驗證索引可用
        order = OrderHistory(
            symbol="TXF",
            action="Buy",
            quantity=1,
            status="pending",
            simulation=1
        )
        db_session.add(order)
        db_session.commit()
        
        # 使用索引欄位查詢
        result = db_session.query(OrderHistory).filter(
            OrderHistory.simulation == 1
        ).first()
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
