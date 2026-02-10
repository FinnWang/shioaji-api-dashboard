-- 策略事件表：記錄所有策略引擎產生的事件
-- Version: 004

CREATE TABLE IF NOT EXISTS strategy_event (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    event_type VARCHAR(20) NOT NULL,  -- kline_complete, signal, entry, exit, stop_loss
    event_data JSONB NOT NULL,        -- 事件詳細資料（保留彈性）
    event_time TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 索引：依商品+時間查詢
CREATE INDEX IF NOT EXISTS ix_strategy_event_symbol_time
    ON strategy_event (symbol, event_time DESC);

-- 索引：依事件類型+時間查詢
CREATE INDEX IF NOT EXISTS ix_strategy_event_type_time
    ON strategy_event (event_type, event_time DESC);

-- 索引：依商品+事件類型+時間查詢（復盤篩選用）
CREATE INDEX IF NOT EXISTS ix_strategy_event_symbol_type_time
    ON strategy_event (symbol, event_type, event_time DESC);

COMMENT ON TABLE strategy_event IS '策略引擎事件記錄表，儲存所有策略產生的事件供復盤分析';
COMMENT ON COLUMN strategy_event.event_type IS '事件類型: kline_complete, signal, entry, exit, stop_loss';
COMMENT ON COLUMN strategy_event.event_data IS '事件詳細資料 (JSONB 格式，保留擴展彈性)';
COMMENT ON COLUMN strategy_event.event_time IS '事件發生時間（毫秒時間戳轉換）';
