-- 个人/群日常记账 SQLite Schema
-- DB 只存原始事实；分类别名、预算剩余、日报文案由 rules.py 计算。

-- 成员（对齐跑团：id / name / at_name / alias，轻量无病假期次）
CREATE TABLE IF NOT EXISTS member (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    at_name         TEXT DEFAULT '',                 -- @ 名称（群里 @人的句柄）
    alias           TEXT DEFAULT '',                 -- 别名/外号，多值用；分隔，供查找
    sort_order      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','exited')),
    is_admin        INTEGER NOT NULL DEFAULT 0,      -- 1=可改/删他人流水
    description     TEXT DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS txn (
    txn_id          TEXT PRIMARY KEY,                -- 如 2026-08-15_01
    member_id       TEXT DEFAULT '',                 -- 归属成员 id（建档后必填）
    direction       TEXT NOT NULL DEFAULT 'expense'
                    CHECK (direction IN ('expense','income')),
    amount          REAL NOT NULL CHECK (amount > 0),
    occurred_at     TEXT NOT NULL,                   -- YYYY-MM-DD 或 YYYY-MM-DD HH:MM
    category        TEXT NOT NULL DEFAULT '其它',
    note            TEXT DEFAULT '',
    image_url       TEXT DEFAULT '',                 -- 可选截图/小票
    recorded_for    TEXT DEFAULT '',                 -- 展示名（一般=member.name）
    recorded_by     TEXT DEFAULT '',                 -- 录入者展示名
    recorded_by_id  TEXT DEFAULT '',                 -- 录入者 member id
    source_msg      TEXT DEFAULT '',                 -- 可选消息摘要
    created_at      TEXT NOT NULL,
    deleted_at      TEXT,                            -- 软删
    deleted_reason  TEXT
);

CREATE INDEX IF NOT EXISTS idx_txn_occurred ON txn(occurred_at);
CREATE INDEX IF NOT EXISTS idx_txn_category ON txn(category);
CREATE INDEX IF NOT EXISTS idx_txn_for ON txn(recorded_for);
CREATE INDEX IF NOT EXISTS idx_txn_member ON txn(member_id);
CREATE INDEX IF NOT EXISTS idx_txn_deleted ON txn(deleted_at);

-- 可选预算：未设置则不展示预算相关字段
CREATE TABLE IF NOT EXISTS budget (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT NOT NULL CHECK (period IN ('day','week','month')),
    amount          REAL NOT NULL CHECK (amount > 0),
    category        TEXT NOT NULL DEFAULT '',        -- 空=总预算；非空=分类预算
    note            TEXT DEFAULT '',
    updated_at      TEXT NOT NULL,
    UNIQUE(period, category)
);
