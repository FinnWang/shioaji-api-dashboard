"""
支撐壓力分析客戶端

用於從 shioaji-proxy 取得支撐壓力、VWAP 等技術分析數據
"""
import httpx
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AnalysisLevels:
    """分析數據結構"""
    is_valid: bool
    timestamp: str
    symbol: str

    # 報價
    price: float = 0
    change: float = 0
    change_percent: float = 0

    # Pivot Points
    pp: float = 0
    r1: float = 0
    r2: float = 0
    r3: float = 0
    s1: float = 0
    s2: float = 0
    s3: float = 0

    # OI 支撐壓力
    max_pain: float = 0
    oi_resistance: float = 0
    oi_support: float = 0

    # VWAP
    vwap: float = 0

    # 綜合強度支撐壓力
    resistances: List[Dict[str, Any]] = None
    supports: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.resistances is None:
            self.resistances = []
        if self.supports is None:
            self.supports = []

    def get_nearest_resistance(self) -> Optional[float]:
        """取得最近的壓力位"""
        if not self.resistances or self.price <= 0:
            return None
        # 找比當前價格高的最近壓力
        higher = [r["price"] for r in self.resistances if r["price"] > self.price]
        return min(higher) if higher else None

    def get_nearest_support(self) -> Optional[float]:
        """取得最近的支撐位"""
        if not self.supports or self.price <= 0:
            return None
        # 找比當前價格低的最近支撐
        lower = [s["price"] for s in self.supports if s["price"] < self.price]
        return max(lower) if lower else None

    def is_near_resistance(self, tolerance: float = 30) -> bool:
        """是否接近壓力位"""
        nearest = self.get_nearest_resistance()
        if nearest is None:
            return False
        return abs(self.price - nearest) <= tolerance

    def is_near_support(self, tolerance: float = 30) -> bool:
        """是否接近支撐位"""
        nearest = self.get_nearest_support()
        if nearest is None:
            return False
        return abs(self.price - nearest) <= tolerance

    def get_price_position(self) -> str:
        """
        判斷價格相對位置

        Returns:
            "above_vwap": 在 VWAP 上方（偏多）
            "below_vwap": 在 VWAP 下方（偏空）
            "at_vwap": 在 VWAP 附近
            "unknown": 無法判斷
        """
        if self.vwap <= 0 or self.price <= 0:
            return "unknown"

        diff = self.price - self.vwap
        if diff > 20:
            return "above_vwap"
        elif diff < -20:
            return "below_vwap"
        else:
            return "at_vwap"


class AnalysisLevelsClient:
    """
    支撐壓力分析客戶端

    使用方式:
        client = AnalysisLevelsClient("https://shioaji-proxy.zeabur.app")
        levels = client.get_levels("TXF")

        if levels.is_valid:
            print(f"當前價格: {levels.price}")
            print(f"最近壓力: {levels.get_nearest_resistance()}")
            print(f"最近支撐: {levels.get_nearest_support()}")
            print(f"VWAP 位置: {levels.get_price_position()}")
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        """
        初始化客戶端

        Args:
            base_url: shioaji-proxy API 的基礎 URL
            timeout: 請求超時時間（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def close(self):
        """關閉客戶端連線"""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_levels(self, symbol: str = "TXF") -> AnalysisLevels:
        """
        取得支撐壓力分析數據

        Args:
            symbol: 商品代碼（TXF 或 MXF）

        Returns:
            AnalysisLevels: 分析數據
        """
        try:
            response = self._client.get(
                f"{self.base_url}/api/analysis/levels",
                params={"symbol": symbol, "include_vwap": True}
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                logger.warning(f"API 返回失敗: {data}")
                return AnalysisLevels(
                    is_valid=False,
                    timestamp=datetime.now().isoformat(),
                    symbol=symbol
                )

            return self._parse_response(data["data"])

        except Exception as e:
            logger.error(f"取得支撐壓力數據失敗: {e}")
            return AnalysisLevels(
                is_valid=False,
                timestamp=datetime.now().isoformat(),
                symbol=symbol
            )

    def get_levels_simple(self, symbol: str = "TXF") -> AnalysisLevels:
        """
        取得簡化版支撐壓力數據（更快速）

        Args:
            symbol: 商品代碼

        Returns:
            AnalysisLevels: 分析數據
        """
        try:
            response = self._client.get(
                f"{self.base_url}/api/analysis/levels/simple",
                params={"symbol": symbol}
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                return AnalysisLevels(
                    is_valid=False,
                    timestamp=datetime.now().isoformat(),
                    symbol=symbol
                )

            return AnalysisLevels(
                is_valid=True,
                timestamp=data.get("timestamp", ""),
                symbol=symbol,
                price=data.get("price", 0),
                max_pain=data.get("max_pain", 0),
                vwap=data.get("vwap", 0),
                resistances=data.get("resistances", []),
                supports=data.get("supports", [])
            )

        except Exception as e:
            logger.error(f"取得簡化支撐壓力數據失敗: {e}")
            return AnalysisLevels(
                is_valid=False,
                timestamp=datetime.now().isoformat(),
                symbol=symbol
            )

    def _parse_response(self, data: Dict[str, Any]) -> AnalysisLevels:
        """解析 API 回應"""
        quote = data.get("quote", {})
        pivot = data.get("pivot_points", {})
        oi = data.get("oi_levels", {})
        strength_levels = data.get("strength_levels", [])

        # 分離壓力和支撐
        resistances = []
        supports = []
        for level in strength_levels:
            item = {
                "price": level["price"],
                "strength": level["strength"],
                "label": level["label"]
            }
            if level["type"] == "resistance":
                resistances.append(item)
            else:
                supports.append(item)

        return AnalysisLevels(
            is_valid=data.get("is_valid", False),
            timestamp=data.get("timestamp", ""),
            symbol=data.get("symbol", "TXF"),

            # 報價
            price=quote.get("close", 0),
            change=quote.get("change", 0),
            change_percent=quote.get("change_percent", 0),

            # Pivot Points
            pp=pivot.get("pp", 0) if pivot else 0,
            r1=pivot.get("r1", 0) if pivot else 0,
            r2=pivot.get("r2", 0) if pivot else 0,
            r3=pivot.get("r3", 0) if pivot else 0,
            s1=pivot.get("s1", 0) if pivot else 0,
            s2=pivot.get("s2", 0) if pivot else 0,
            s3=pivot.get("s3", 0) if pivot else 0,

            # OI
            max_pain=oi.get("max_pain", 0) if oi else 0,
            oi_resistance=oi.get("resistance", 0) if oi else 0,
            oi_support=oi.get("support", 0) if oi else 0,

            # VWAP
            vwap=data.get("vwap", 0),

            # 強度
            resistances=resistances,
            supports=supports
        )


# ============================================================================
# 使用範例
# ============================================================================

def example_usage():
    """展示如何使用支撐壓力分析客戶端"""
    # 連接到 shioaji-proxy（部署在 Zeabur 或本地）
    api_url = "https://shioaji-proxy.zeabur.app"  # 或 "http://localhost:8000"

    with AnalysisLevelsClient(api_url) as client:
        # 取得 TXF 的支撐壓力數據
        levels = client.get_levels("TXF")

        if not levels.is_valid:
            print("❌ 無法取得分析數據")
            return

        print("=" * 50)
        print(f"📊 {levels.symbol} 支撐壓力分析")
        print("=" * 50)

        # 當前報價
        print(f"\n💰 當前價格: {levels.price}")
        print(f"   漲跌: {levels.change:+.0f} ({levels.change_percent:+.2f}%)")

        # VWAP
        print(f"\n📈 VWAP: {levels.vwap}")
        print(f"   位置: {levels.get_price_position()}")

        # Pivot Points
        print(f"\n📐 Pivot Points (前日 OHLC 計算):")
        print(f"   PP: {levels.pp}")
        print(f"   R1: {levels.r1}  R2: {levels.r2}  R3: {levels.r3}")
        print(f"   S1: {levels.s1}  S2: {levels.s2}  S3: {levels.s3}")

        # OI 支撐壓力
        print(f"\n🎯 OI 支撐壓力:")
        print(f"   Max Pain: {levels.max_pain}")
        print(f"   OI 壓力: {levels.oi_resistance}")
        print(f"   OI 支撐: {levels.oi_support}")

        # 綜合強度
        print(f"\n🔥 綜合壓力線:")
        for r in sorted(levels.resistances, key=lambda x: x["price"]):
            strength = "●" * r["strength"]
            print(f"   {r['price']:,.0f} ({r['label']}) {strength}")

        print(f"\n💎 綜合支撐線:")
        for s in sorted(levels.supports, key=lambda x: x["price"], reverse=True):
            strength = "●" * s["strength"]
            print(f"   {s['price']:,.0f} ({s['label']}) {strength}")

        # 交易建議
        print(f"\n📋 參考建議:")
        nearest_r = levels.get_nearest_resistance()
        nearest_s = levels.get_nearest_support()

        if nearest_r:
            print(f"   最近壓力: {nearest_r:,.0f} (距離 {nearest_r - levels.price:+.0f} 點)")
        if nearest_s:
            print(f"   最近支撐: {nearest_s:,.0f} (距離 {nearest_s - levels.price:+.0f} 點)")

        if levels.is_near_resistance():
            print("   ⚠️ 接近壓力位，注意追高風險")
        elif levels.is_near_support():
            print("   ⚠️ 接近支撐位，注意追空風險")


def example_trading_decision():
    """展示如何用支撐壓力數據做交易決策"""
    api_url = "https://shioaji-proxy.zeabur.app"

    with AnalysisLevelsClient(api_url) as client:
        levels = client.get_levels("TXF")

        if not levels.is_valid:
            return None

        # 簡單的交易邏輯範例
        decision = None

        # 條件 1: 價格在 VWAP 上方 + 未接近壓力
        if levels.get_price_position() == "above_vwap" and not levels.is_near_resistance():
            decision = "偏多觀望"

        # 條件 2: 價格在 VWAP 下方 + 未接近支撐
        elif levels.get_price_position() == "below_vwap" and not levels.is_near_support():
            decision = "偏空觀望"

        # 條件 3: 接近支撐位
        elif levels.is_near_support(tolerance=30):
            decision = "支撐附近，可考慮做多"

        # 條件 4: 接近壓力位
        elif levels.is_near_resistance(tolerance=30):
            decision = "壓力附近，可考慮做空"

        print(f"交易參考: {decision}")
        return decision


if __name__ == "__main__":
    import sys

    # 設定日誌
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    print("支撐壓力分析客戶端範例")
    print("-" * 50)

    try:
        example_usage()
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)
