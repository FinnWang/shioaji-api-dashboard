-- 新增 simulation 欄位到 order_history 表
-- 區分模擬模式與實盤模式的委託記錄

-- 新增 simulation 欄位 (1=模擬, 0=實盤)，預設為 1 (模擬模式)
ALTER TABLE order_history ADD COLUMN IF NOT EXISTS simulation INTEGER NOT NULL DEFAULT 1;

-- 建立索引以加速篩選
CREATE INDEX IF NOT EXISTS idx_order_history_simulation ON order_history(simulation);

-- 複合索引：模式 + 建立時間（用於依模式查詢最新記錄）
CREATE INDEX IF NOT EXISTS idx_order_history_simulation_created ON order_history(simulation, created_at DESC);
