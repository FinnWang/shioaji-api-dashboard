-- Quote history table for storing Tick and BidAsk data
-- Version: 002

CREATE TABLE IF NOT EXISTS quote_history (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    code VARCHAR(32) NOT NULL,
    quote_type VARCHAR(10) NOT NULL,  -- "tick" or "bidask"
    close_price DECIMAL(12, 2),
    open_price DECIMAL(12, 2),
    high_price DECIMAL(12, 2),
    low_price DECIMAL(12, 2),
    change_price DECIMAL(12, 2),
    change_rate DECIMAL(8, 4),
    volume INTEGER,
    total_volume INTEGER,
    buy_price DECIMAL(12, 2),
    sell_price DECIMAL(12, 2),
    buy_volume INTEGER,
    sell_volume INTEGER,
    quote_time TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 建立索引以加速查詢
CREATE INDEX IF NOT EXISTS ix_quote_history_symbol_time ON quote_history (symbol, quote_time DESC);
CREATE INDEX IF NOT EXISTS ix_quote_history_code_time ON quote_history (code, quote_time DESC);
CREATE INDEX IF NOT EXISTS ix_quote_history_symbol_type_time ON quote_history (symbol, quote_type, quote_time DESC);

COMMENT ON TABLE quote_history IS '報價歷史資料表，儲存 Tick 和 BidAsk 資料供量化分析使用';
COMMENT ON COLUMN quote_history.symbol IS 'Shioaji 商品代碼 (如 MXFR1, MXF202601)';
COMMENT ON COLUMN quote_history.code IS '交易所代碼 (如 MXFA6)';
COMMENT ON COLUMN quote_history.quote_type IS '報價類型: tick (成交) 或 bidask (五檔)';
COMMENT ON COLUMN quote_history.quote_time IS 'Shioaji 報價時間戳';
