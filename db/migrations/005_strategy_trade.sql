-- 策略交易回合表：配對 entry → exit，記錄完整交易鏈路
-- Version: 005

CREATE TABLE IF NOT EXISTS strategy_trade (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    direction VARCHAR(10) NOT NULL,       -- long, short
    entry_price DECIMAL(12,2) NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE NOT NULL,
    entry_event_id BIGINT REFERENCES strategy_event(id),
    exit_price DECIMAL(12,2),
    exit_time TIMESTAMP WITH TIME ZONE,
    exit_event_id BIGINT REFERENCES strategy_event(id),
    exit_reason VARCHAR(20),              -- signal, stop_loss (fixed/trailing/daily)
    pnl DECIMAL(12,2),                    -- 實現損益（點數）
    quantity INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(10) NOT NULL DEFAULT 'open',  -- open, closed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 索引：依商品+進場時間查詢
CREATE INDEX IF NOT EXISTS ix_strategy_trade_symbol_time
    ON strategy_trade (symbol, entry_time DESC);

-- 索引：依狀態查詢（找未平倉交易）
CREATE INDEX IF NOT EXISTS ix_strategy_trade_status
    ON strategy_trade (status);

-- 索引：依商品+狀態+進場時間（復盤篩選用）
CREATE INDEX IF NOT EXISTS ix_strategy_trade_symbol_status
    ON strategy_trade (symbol, status, entry_time DESC);

COMMENT ON TABLE strategy_trade IS '策略交易回合表，配對進場與出場形成完整交易記錄';
COMMENT ON COLUMN strategy_trade.direction IS '交易方向: long (做多), short (做空)';
COMMENT ON COLUMN strategy_trade.exit_reason IS '出場原因: signal (策略訊號), fixed (固定停損), trailing (追蹤停損), daily (每日停損)';
COMMENT ON COLUMN strategy_trade.pnl IS '實現損益（以點數計）';
COMMENT ON COLUMN strategy_trade.status IS '交易狀態: open (持倉中), closed (已平倉)';
