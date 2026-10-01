-- 记账台账 SQLite Schema
--
-- 三张表：member（群成员档案）+ txn（流水）+ reissue_lock（失败换卡后禁止同轮代确认）。
--
-- 「台账 == db」：txn 只存 member_id，展示用的归属人姓名一律 JOIN member 实时取。
-- 成员改名后所有历史流水的展示名跟着变，不需要回填——所以 txn 里没有 owner_name 冗余列。
--
-- 派生值一律不入库：金额展示文本（¥38.50）、日期展示文本（2026.08.09）、分类中文名
-- 都由 vocab.py 实时渲染。库里只存机器码与原始数值，改文案不用回填。
--
-- 只存"用户确认过"的流水：待确认的草稿卡片从不落库（与跑团打卡同一条规矩），
-- 所以这张表里没有 pending 状态。status 只区分这条是用户点确认写的还是超时自动写的。

-- 成员档案。与跑团那张 member 表同结构取舍，但去掉了跑步专属列
-- （sun_count 周冠军 / age_exempt 年龄豁免 / walk_valid 健走有效）——记账没有这些概念。
-- status 也只留 active / exited：跑团的 suspended / wildcard 是为达标与处罚服务的，
-- 记账里没有对应业务含义，留着就是死字段。
CREATE TABLE IF NOT EXISTS member (
    id          TEXT PRIMARY KEY,           -- 系统自增数字串（'1','2'…）；旧库可能仍有拼音/user_N，只读兼容
    name        TEXT NOT NULL,
    at_name     TEXT NOT NULL DEFAULT '',   -- @ 名称（群里 @人的句柄，单值精确），空=不@但要列名
    alias       TEXT NOT NULL DEFAULT '',   -- 别名/外号，多值用；分隔，仅供查找（LIKE 模糊匹配）
    sort_order  INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','exited')),
    description TEXT NOT NULL DEFAULT '',   -- 自由文本：记账习惯备注（常用账户、默认分类等）
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_member_name    ON member(name);
CREATE INDEX IF NOT EXISTS idx_member_at_name ON member(at_name);

CREATE TABLE IF NOT EXISTS txn (
    txn_id           TEXT PRIMARY KEY,                -- {member_id}_{occurred_at}_{seq}
    group_id         TEXT NOT NULL DEFAULT 'default',
    card_id          TEXT NOT NULL DEFAULT '',        -- 来源卡片，用于重复确认的幂等判定
    member_id        TEXT NOT NULL REFERENCES member(id),  -- 归属人（这笔账记谁名下）
    occurred_at      TEXT NOT NULL,                   -- 记账日期 YYYY-MM-DD
    transaction_type TEXT NOT NULL
                     CHECK (transaction_type IN ('income','expense')),
    amount           REAL NOT NULL CHECK (amount > 0), -- 正数；收支方向由 transaction_type 表达
    currency         TEXT NOT NULL DEFAULT '人民币',
    -- category 的合法取值依赖 transaction_type（收入/支出各一组），SQL 里表达不了，
    -- 由 vocab.normalize_category 在写库前保证；这里只兜一个非空默认。
    category         TEXT NOT NULL DEFAULT 'other',
    account          TEXT NOT NULL DEFAULT 'other'
                     CHECK (account IN ('wechat','alipay','bank_card','cash','credit_card','other')),
    merchant_name    TEXT NOT NULL DEFAULT '',
    note             TEXT NOT NULL DEFAULT '',
    -- 流水落库一律 confirmed。CHECK 仍允许 expired 以兼容旧库已写入的超时结算行。
    status           TEXT NOT NULL DEFAULT 'confirmed'
                     CHECK (status IN ('confirmed','expired')),
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL DEFAULT '',
    deleted_at       TEXT,                            -- 软删
    deleted_reason   TEXT
);

CREATE INDEX IF NOT EXISTS idx_txn_member      ON txn(member_id);
CREATE INDEX IF NOT EXISTS idx_txn_date        ON txn(occurred_at);
CREATE INDEX IF NOT EXISTS idx_txn_member_date ON txn(member_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_txn_group       ON txn(group_id);

-- 同一张卡只能落一条流水：重复确认（用户连点、客户端重试）会撞这个唯一索引，
-- ledger_api 据此走幂等分支回"已录入"，而不是记成两笔账。
CREATE UNIQUE INDEX IF NOT EXISTS idx_txn_card
    ON txn(card_id) WHERE card_id != '' AND deleted_at IS NULL;

-- 确认失败换卡后，新卡在同一轮不能被模型代点确认。
-- source_seq_id = 用户点确认那条消息的 update_seq_id；同一 seq 再 commit 新卡直接拒。
-- 用户在新卡上再点确认时 seq 会变，锁解除后才允许落库。
CREATE TABLE IF NOT EXISTS reissue_lock (
    card_id         TEXT PRIMARY KEY,
    source_card_id  TEXT NOT NULL DEFAULT '',
    source_seq_id   TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);
