# Network Hunt

从 Product Hunt 发现优秀创业者/Maker，通过多渠道搜索扩展认知，建立可联系的人才数据库。

## 功能

- **双模式爬取**: 回溯历史数据 + 增量更新新数据
- **去重机制**: 避免重复 API 调用
- **增量知识更新**: 每个渠道有独立 cutoff，只搜索新内容
- **多源信息聚合**: Product Hunt → Twitter/X → LinkedIn → GitHub → arXiv
- **混合存储**: 核心数据存 Supabase，工作数据存本地 SQLite

## 架构

```
Supabase (云端 - 核心数据):          本地 SQLite (工作数据):
├── data_source_state (爬取进度)     ├── ph_posts (产品信息)
└── persons (人员核心信息)           ├── person_posts (人员-产品关联)
                                     ├── person_knowledge (搜索知识)
                                     └── enrichment_queue (任务队列)
```

## 安装

```bash
cd network_hunt
pip install -e .
```

## 配置

复制 `.env.example` 为 `.env` 并填写：

```bash
# Supabase (Dashboard > Settings > API)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=sb_secret_xxx

# Product Hunt (https://api.producthunt.com/v2/oauth/applications)
PRODUCT_HUNT_DEVELOPER_TOKEN=xxx

# SerpAPI (https://serpapi.com/)
SERP_API_KEY=xxx

# GitHub (https://github.com/settings/tokens)
GITHUB_TOKEN=ghp_xxx
```

## 数据库初始化

在 Supabase SQL Editor 中执行 `network_hunt/db/schema.sql`

本地 SQLite 数据库会自动创建在 `data/network_hunt.db`

## 使用

### 爬取 Product Hunt

```bash
# 小量测试 (3个 posts)
network-hunt crawl --mode backfill --max-posts 3

# 回溯爬取最近 7 天
network-hunt crawl --mode backfill --days 7

# 回溯爬取最近 30 天
network-hunt crawl --mode backfill --days 30

# 增量更新 (爬取新数据)
network-hunt crawl --mode incremental
```

### 查看数据

```bash
# 数据库统计
network-hunt stats

# 列出人员
network-hunt persons

# 只看有 email 的人
network-hunt persons --with-email

# 只看有 Twitter 的人
network-hunt persons --with-twitter

# 按重要性筛选
network-hunt persons --min-score 50
```

### 信息扩充

```bash
# 扩充指定人员 (全部渠道)
network-hunt enrich --person-id <uuid>

# 只搜索 Twitter
network-hunt enrich --person-id <uuid> --task twitter

# 只搜索 GitHub
network-hunt enrich --person-id <uuid> --task github

# 增量搜索 (只搜索各渠道 cutoff 之后的新内容)
network-hunt enrich --person-id <uuid> --incremental

# 批量扩充 top 人员
network-hunt enrich --min-score 50 --limit 10
```

### 任务队列

```bash
# 查看队列状态
network-hunt queue --status

# 处理队列
network-hunt queue --process --limit 10
```

### 更新重要性评分

```bash
network-hunt update-scores
```

## 数据库架构

### Supabase 表

| 表 | 用途 |
|---|---|
| `data_source_state` | 数据源爬取进度 (支持断点续爬) |
| `persons` | 人员核心信息 + 各渠道增量搜索 cutoff |

### 本地 SQLite 表

| 表 | 用途 |
|---|---|
| `ph_posts` | Product Hunt 产品详情 |
| `person_posts` | 人员-产品关联 (maker 关系) |
| `person_knowledge` | 各渠道搜索到的知识内容 |
| `enrichment_queue` | 扩充任务队列 |

### persons 表结构

```sql
persons (
    id UUID PRIMARY KEY,
    source VARCHAR(50),           -- 来源: 'product_hunt'
    source_id TEXT,               -- 在来源平台的 ID
    name TEXT NOT NULL,
    headline TEXT,
    avatar_url TEXT,
    -- 联系方式
    email TEXT,
    twitter TEXT,
    linkedin TEXT,
    github TEXT,
    website TEXT,
    -- 各渠道搜索 cutoff (增量更新用)
    twitter_cutoff TIMESTAMPTZ,
    linkedin_cutoff TIMESTAMPTZ,
    github_cutoff TIMESTAMPTZ,
    arxiv_cutoff TIMESTAMPTZ,
    serp_cutoff TIMESTAMPTZ,
    -- 最终产物
    profile_summary TEXT,
    importance_score INTEGER DEFAULT 0
)
```

## 信息来源

| 来源 | 获取内容 |
|---|---|
| Product Hunt | 基础信息、Twitter、Website |
| SerpAPI (Twitter) | 推文、活动 |
| SerpAPI (LinkedIn) | Profile、Posts |
| GitHub API | Email、Repos、Activity |
| arXiv API | 学术论文 |
| SerpAPI (General) | 新闻、文章 |

## 注意事项

- Product Hunt API 有 fair-use 限制
- SerpAPI 按月计费，注意用量
- GitHub 搜索 API 限制 30 req/min
- arXiv 建议请求间隔 3 秒
