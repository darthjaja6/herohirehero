-- ============================================
-- Network Hunt Database Schema (Supabase)
-- 只存最终产物和进度元数据
-- 工作数据存本地 SQLite
-- ============================================

-- 1. 数据源爬取进度
CREATE TABLE data_source_state (
    source VARCHAR(50) PRIMARY KEY,     -- 'product_hunt' | 'linkedin_feed' | ...
    oldest_date DATE,                   -- 回溯模式：已爬到的最早日期
    newest_date DATE,                   -- 增量模式：已爬到的最新日期
    last_cursor TEXT,                   -- API 分页游标（断点续爬）
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed')),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 人员表 - 核心实体
CREATE TABLE persons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 来源（记录这个人是怎么被发现/添加的）
    source VARCHAR(50),                 -- 'product_hunt' | 'manual' | 'referral' | ...

    -- 基本信息
    name TEXT NOT NULL,
    headline TEXT,
    avatar_url TEXT,

    -- 各平台 ID（用于去重和关联）
    ph_id TEXT UNIQUE,                  -- Product Hunt user ID
    twitter TEXT UNIQUE,                -- Twitter/X handle
    linkedin TEXT UNIQUE,               -- LinkedIn URL or username
    github TEXT UNIQUE,                 -- GitHub username

    -- 其他联系方式
    email TEXT,
    website TEXT,

    -- 各渠道搜索进度 (用于增量搜索)
    twitter_cutoff TIMESTAMPTZ,
    linkedin_cutoff TIMESTAMPTZ,
    github_cutoff TIMESTAMPTZ,
    arxiv_cutoff TIMESTAMPTZ,
    serp_cutoff TIMESTAMPTZ,

    -- 最终产物
    profile_summary TEXT,               -- 整理好的展示文档

    -- 元数据
    importance_score INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_persons_source ON persons(source);
CREATE INDEX idx_persons_importance ON persons(importance_score DESC);
CREATE INDEX idx_persons_name ON persons(name);
CREATE INDEX idx_persons_ph_id ON persons(ph_id) WHERE ph_id IS NOT NULL;
CREATE INDEX idx_persons_twitter ON persons(twitter) WHERE twitter IS NOT NULL;
CREATE INDEX idx_persons_github ON persons(github) WHERE github IS NOT NULL;

-- ============================================
-- Helper Functions
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_data_source_state_updated_at
    BEFORE UPDATE ON data_source_state
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_persons_updated_at
    BEFORE UPDATE ON persons
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 初始化
-- ============================================
INSERT INTO data_source_state (source, oldest_date, newest_date, status)
VALUES ('product_hunt', CURRENT_DATE, CURRENT_DATE, 'active');
