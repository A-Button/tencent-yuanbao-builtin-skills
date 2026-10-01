-- 跑团 tracker SQLite 外部记忆 Schema
-- DB 只存原始事实 + 少量快照（sun_count、定稿冠军）。
-- 派生值（有效性 valid、折算 distance_km、配速、达标、期次、连续未达标/病假/恢复周数）
-- 由 rules.py 实时计算；checkin 的派生列写库便于聚合，改规则后用 recompute 回填。
--
-- 成员状态按生命周期拆两处：
--   member.status        长期角色态（active/suspended/exited/wildcard），手动改、极少回溯。
--   period.member_status 临期参与态（请假/恢复）事实流，按期存、默认空=active、次期自动恢复。
-- 「某成员第 N 期有效状态」由二者派生：角色态非 active 优先，否则查该期 JSON，否则 active。

CREATE TABLE IF NOT EXISTS member (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    at_name         TEXT DEFAULT '',                 -- @ 名称（群里 @人的句柄，单值精确），空=不@但要列名
    alias           TEXT DEFAULT '',                 -- 别名/外号，多值用；分隔，仅供查找（LIKE 模糊匹配）
    sort_order      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','suspended','exited','wildcard')),  -- 长期角色态；请假/恢复见 period.member_status
    age_exempt      INTEGER NOT NULL DEFAULT 0,      -- 60岁+ 豁免：任何形式只看距离
    walk_valid      INTEGER NOT NULL DEFAULT 0,      -- 健走有效成员
    description     TEXT DEFAULT '',                 -- 自由文本：识图辅助 + 单位/设备习惯
    sun_count       INTEGER NOT NULL DEFAULT 0,      -- 周冠军次数（定稿累加）
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS period (
    num               INTEGER PRIMARY KEY,
    start_date        TEXT NOT NULL,                 -- 周一 YYYY-MM-DD
    end_date          TEXT NOT NULL,                 -- 周日 YYYY-MM-DD
    status            TEXT NOT NULL DEFAULT 'in_progress'
                      CHECK (status IN ('in_progress','finalized')),
    champion_id       TEXT REFERENCES member(id),
    champion_distance REAL,
    finalized_at      TEXT,
    -- 本期参与态偏离事实流（只存非 active 的人）：
    --   {"<member_id>": {"status":"sick_leave|recovering","reason":"...","occurred_at":"YYYY-MM-DD"}, ...}
    -- 不在表中=本期 active；销假=删键。新建期次默认 '{}' 即「全员 active」=请假不延续（自动恢复）。
    member_status     TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS checkin (
    event_id        TEXT PRIMARY KEY,                -- {member_id}_{occurred_at}_{seq}
    member_id       TEXT NOT NULL REFERENCES member(id),
    occurred_at     TEXT NOT NULL,                   -- 截图日期，决定期次归属
    period          INTEGER NOT NULL,                -- 按 period 表锚点 + rules.period_for_date 算出
    activity_type   TEXT NOT NULL
                    CHECK (activity_type IN ('outdoor_run','treadmill','indoor_run','swim','walk')),
    distance_raw    REAL NOT NULL,                   -- 截图上的原始数值
    unit            TEXT NOT NULL DEFAULT 'km'
                    CHECK (unit IN ('km','miles','swim_m')),
    distance_km     REAL NOT NULL,                   -- rules.effective_km 折算后
    duration_seconds INTEGER,                        -- 用时秒数（截图未显示则空）
    valid           INTEGER NOT NULL,                -- rules.judge 判定（0/1），可被覆盖
    valid_overridden INTEGER NOT NULL DEFAULT 0,     -- 1=管理员手工覆盖，recompute 不动它
    note            TEXT DEFAULT '',                 -- 规则提示（如"配速略超标，提示管理员"）
    device          TEXT DEFAULT '',
    raw_summary     TEXT NOT NULL DEFAULT '',        -- 原始描述留档
    created_at      TEXT NOT NULL,
    deleted_at      TEXT,                            -- 软删
    deleted_reason  TEXT
);

CREATE INDEX IF NOT EXISTS idx_checkin_member ON checkin(member_id);
CREATE INDEX IF NOT EXISTS idx_checkin_period ON checkin(period);
CREATE INDEX IF NOT EXISTS idx_checkin_member_date ON checkin(member_id, occurred_at);