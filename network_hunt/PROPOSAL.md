# Network Hunt - 人才发现与信息聚合系统

## 1. 系统概述

从 Product Hunt 出发，发现优秀的创业者/Maker，然后通过多渠道搜索扩展对他们的认知，最终建立一个可联系的人才数据库。

### 核心特性
- **双模式爬取**: 回溯历史数据 + 增量更新新数据
- **去重机制**: 避免重复 API 调用，节省成本
- **增量知识更新**: 每个人的信息有 knowledge_cutoff，支持只搜索新信息
- **多源信息聚合**: Product Hunt → Twitter/X → LinkedIn → GitHub → arXiv → 通用搜索

---

## 2. 数据流架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA COLLECTION PIPELINE                         │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Product Hunt │────▶│    Person    │────▶│   Enrichment │
│   Crawler     │     │   Discovery  │     │   Pipeline   │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                     │
       ▼                    ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐
│ posts table  │     │ persons table│     │ 1. Twitter/X (SerpAPI)   │
│ crawl_state  │     │              │     │ 2. LinkedIn (SerpAPI)    │
└──────────────┘     └──────────────┘     │ 3. GitHub API            │
                                          │ 4. arXiv API             │
                                          │ 5. General Search        │
                                          └──────────────────────────┘
                                                    │
                                                    ▼
                                          ┌──────────────────────────┐
                                          │  person_knowledge table  │
                                          │  person_contacts table   │
                                          └──────────────────────────┘
```

---

## 3. 数据库设计 (Supabase/PostgreSQL)

### 3.1 爬取状态表 - `ph_crawl_state`
追踪爬取进度，支持断点续爬

```sql
CREATE TABLE ph_crawl_state (
    id SERIAL PRIMARY KEY,
    crawl_type VARCHAR(20) NOT NULL,  -- 'backfill' | 'incremental'
    oldest_date DATE,                  -- 回溯模式: 已爬到的最早日期
    newest_date DATE,                  -- 增量模式: 已爬到的最新日期
    last_cursor TEXT,                  -- GraphQL 分页游标
    status VARCHAR(20) DEFAULT 'active', -- 'active' | 'paused' | 'completed'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.2 Product Hunt 产品表 - `ph_posts`

```sql
CREATE TABLE ph_posts (
    id TEXT PRIMARY KEY,               -- Product Hunt post ID
    name TEXT NOT NULL,
    tagline TEXT,
    description TEXT,
    slug TEXT,
    website_url TEXT,
    votes_count INTEGER,
    comments_count INTEGER,
    reviews_rating DECIMAL(3,2),
    topics TEXT[],                     -- 标签数组
    featured_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ph_posts_featured ON ph_posts(featured_at DESC);
CREATE INDEX idx_ph_posts_votes ON ph_posts(votes_count DESC);
```

### 3.3 人员表 - `persons`
核心实体，所有信息围绕人展开

```sql
CREATE TABLE persons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 基础信息 (from Product Hunt)
    ph_user_id TEXT UNIQUE,            -- Product Hunt user ID
    ph_username TEXT,
    name TEXT NOT NULL,
    headline TEXT,
    profile_image_url TEXT,

    -- 已验证的社交账号
    twitter_username TEXT,
    linkedin_url TEXT,
    github_username TEXT,
    personal_website TEXT,

    -- 联系方式
    email TEXT,

    -- 评分/优先级 (用于筛选重要人物)
    importance_score INTEGER DEFAULT 0,

    -- 知识管理
    knowledge_cutoff TIMESTAMPTZ,      -- 上次全量搜索的截止时间
    last_enriched_at TIMESTAMPTZ,      -- 上次信息扩充时间

    -- 元数据
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_persons_ph_user ON persons(ph_user_id);
CREATE INDEX idx_persons_twitter ON persons(twitter_username);
CREATE INDEX idx_persons_importance ON persons(importance_score DESC);
```

### 3.4 人员-产品关联表 - `person_posts`

```sql
CREATE TABLE person_posts (
    id SERIAL PRIMARY KEY,
    person_id UUID REFERENCES persons(id) ON DELETE CASCADE,
    post_id TEXT REFERENCES ph_posts(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,         -- 'maker' | 'hunter' | 'founder'
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(person_id, post_id, role)
);

CREATE INDEX idx_person_posts_person ON person_posts(person_id);
CREATE INDEX idx_person_posts_post ON person_posts(post_id);
```

### 3.5 知识条目表 - `person_knowledge`
存储从各渠道获取的信息片段

```sql
CREATE TABLE person_knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID REFERENCES persons(id) ON DELETE CASCADE,

    -- 来源信息
    source_type VARCHAR(50) NOT NULL,  -- 'twitter' | 'linkedin' | 'github' | 'arxiv' | 'serp' | 'product_hunt'
    source_url TEXT,
    source_query TEXT,                 -- 使用的搜索词

    -- 内容
    title TEXT,
    content TEXT,                      -- 原始内容或摘要
    content_type VARCHAR(50),          -- 'tweet' | 'post' | 'paper' | 'repo' | 'profile' | 'article'

    -- 时间
    content_date TIMESTAMPTZ,          -- 内容的原始发布时间
    fetched_at TIMESTAMPTZ DEFAULT NOW(),

    -- 去重
    content_hash TEXT,                 -- 内容哈希，用于去重

    UNIQUE(person_id, content_hash)
);

CREATE INDEX idx_person_knowledge_person ON person_knowledge(person_id);
CREATE INDEX idx_person_knowledge_source ON person_knowledge(source_type);
CREATE INDEX idx_person_knowledge_date ON person_knowledge(content_date DESC);
```

### 3.6 联系方式表 - `person_contacts`
存储发现的各种联系方式

```sql
CREATE TABLE person_contacts (
    id SERIAL PRIMARY KEY,
    person_id UUID REFERENCES persons(id) ON DELETE CASCADE,

    contact_type VARCHAR(50) NOT NULL, -- 'email' | 'twitter' | 'linkedin' | 'github' | 'website' | 'phone'
    contact_value TEXT NOT NULL,

    -- 可信度
    confidence VARCHAR(20) DEFAULT 'medium', -- 'high' | 'medium' | 'low'
    source TEXT,                       -- 从哪里发现的
    verified BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(person_id, contact_type, contact_value)
);

CREATE INDEX idx_person_contacts_person ON person_contacts(person_id);
```

### 3.7 搜索任务队列 - `enrichment_queue`
管理待搜索的任务

```sql
CREATE TABLE enrichment_queue (
    id SERIAL PRIMARY KEY,
    person_id UUID REFERENCES persons(id) ON DELETE CASCADE,

    task_type VARCHAR(50) NOT NULL,    -- 'twitter' | 'linkedin' | 'github' | 'arxiv' | 'general'
    priority INTEGER DEFAULT 0,

    status VARCHAR(20) DEFAULT 'pending', -- 'pending' | 'processing' | 'completed' | 'failed'
    attempts INTEGER DEFAULT 0,
    last_error TEXT,

    -- 增量搜索支持
    search_after TIMESTAMPTZ,          -- 只搜索此时间之后的内容

    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX idx_enrichment_queue_status ON enrichment_queue(status, priority DESC);
```

---

## 4. Product Hunt 爬取策略

### 4.1 GraphQL 查询

```graphql
# 按日期获取产品
query GetPosts($postedAfter: DateTime, $postedBefore: DateTime, $after: String) {
  posts(
    postedAfter: $postedAfter
    postedBefore: $postedBefore
    featured: true
    order: VOTES
    first: 20
    after: $after
  ) {
    edges {
      node {
        id
        name
        tagline
        description
        slug
        website
        votesCount
        commentsCount
        reviewsRating
        featuredAt
        createdAt
        topics(first: 10) {
          edges {
            node {
              name
            }
          }
        }
        makers {
          id
          username
          name
          headline
          profileImage
          twitterUsername
          websiteUrl
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

### 4.2 双模式爬取逻辑

```
┌─────────────────────────────────────────────────────────────────┐
│                      CRAWL MODES                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  BACKFILL MODE (回溯模式)                                        │
│  ─────────────────────────                                       │
│  从 oldest_date 继续往前爬                                        │
│                                                                  │
│  Timeline: ◀──────────────────────────────────────────────────   │
│            │                                    │                │
│         oldest_date                          TODAY               │
│         (继续往前)                                                │
│                                                                  │
│  INCREMENTAL MODE (增量模式)                                      │
│  ─────────────────────────                                       │
│  从 newest_date 爬到今天                                          │
│                                                                  │
│  Timeline: ──────────────────────────────────────────────────▶   │
│                                    │                    │        │
│                              newest_date              TODAY      │
│                              (继续往后)                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 去重策略
- 使用 `ph_posts.id` 作为唯一标识
- 插入前检查是否已存在
- 使用 `ON CONFLICT DO NOTHING` 或 `DO UPDATE` 更新统计数据

---

## 5. 信息扩充 Pipeline

### 5.1 优先级计算
根据以下因素决定哪些人值得深入搜索：

```javascript
importance_score =
  (maker_posts_count * 10) +           // 做过多少产品
  (total_votes_received * 0.1) +       // 获得的总票数
  (avg_product_rating * 20) +          // 平均评分
  (has_twitter ? 5 : 0) +              // 有社交账号
  (recent_activity ? 10 : 0)           // 近期活跃
```

### 5.2 各渠道搜索策略

#### Twitter/X (via SerpAPI)
```javascript
// Site search
query: `site:twitter.com OR site:x.com "${person.name}"`

// 如果有 twitter_username
query: `site:twitter.com/username`

// 增量: 添加时间过滤
query: `site:twitter.com "${person.name}" after:${knowledge_cutoff}`
```

#### LinkedIn (via SerpAPI)
```javascript
// LinkedIn profile search
query: `site:linkedin.com/in "${person.name}" ${person.headline || ''}`

// LinkedIn posts
query: `site:linkedin.com/posts "${person.name}"`
```

#### GitHub API
```javascript
// 1. Search users by name
GET /search/users?q=${encodeURIComponent(person.name)}

// 2. Get user details (includes email if public)
GET /users/${username}

// 3. Get recent repos & activity
GET /users/${username}/repos?sort=updated&per_page=10
GET /users/${username}/events?per_page=30
```

#### arXiv API
```javascript
// Author search
GET http://export.arxiv.org/api/query?search_query=au:${authorName}&sortBy=submittedDate&sortOrder=descending&max_results=20

// 增量: 添加 submittedDate 过滤
```

#### General Search (SerpAPI)
```javascript
// 综合搜索
query: `"${person.name}" (founder OR CEO OR maker OR startup)`

// 新闻搜索
query: `"${person.name}" news`
```

### 5.3 增量搜索机制

```
┌─────────────────────────────────────────────────────────────────┐
│              INCREMENTAL KNOWLEDGE UPDATE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Person: John Doe                                                │
│  knowledge_cutoff: 2024-06-01                                    │
│  last_enriched_at: 2024-06-01                                    │
│                                                                  │
│  Timeline:                                                       │
│  ──────────────────────────────────────────────────────────────▶ │
│  │                    │                                │         │
│  已有知识            cutoff                          TODAY       │
│  (不需要重新搜索)     │◀──────────────────────────────▶│         │
│                       只搜索这个时间段的新内容                    │
│                                                                  │
│  Search Query Examples:                                          │
│  - Twitter: after:2024-06-01                                     │
│  - arXiv: submittedDate >= 2024-06-01                           │
│  - SerpAPI: tbs=cdr:1,cd_min:6/1/2024                           │
│                                                                  │
│  After enrichment:                                               │
│  - Update knowledge_cutoff = TODAY                               │
│  - Update last_enriched_at = NOW()                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 联系方式提取

### 6.1 来源与优先级

| 来源 | 可获取的联系方式 | 可信度 |
|------|------------------|--------|
| Product Hunt Profile | Twitter, Website | High |
| GitHub Profile | Email, Website, Twitter | High |
| LinkedIn Profile | LinkedIn URL | High |
| Personal Website | Email, Social Links | Medium |
| SERP Results | Various | Low |

### 6.2 Email 发现策略

1. **GitHub Public Email** - 最可靠
2. **Personal Website** - 扫描 contact 页面
3. **Hunter.io API** (可选) - 通过域名查找
4. **Pattern Matching** - 公司邮箱模式推测

---

## 7. 项目文件结构

```
network_hunt/
├── PROPOSAL.md              # 本文档
├── package.json
├── .env.example
├── src/
│   ├── config/
│   │   └── index.ts         # 配置管理
│   ├── db/
│   │   ├── schema.sql       # 数据库 schema
│   │   └── client.ts        # Supabase client
│   ├── crawlers/
│   │   ├── producthunt.ts   # PH GraphQL 爬虫
│   │   └── types.ts
│   ├── enrichers/
│   │   ├── twitter.ts       # Twitter/X 搜索
│   │   ├── linkedin.ts      # LinkedIn 搜索
│   │   ├── github.ts        # GitHub API
│   │   ├── arxiv.ts         # arXiv API
│   │   └── general.ts       # 通用搜索
│   ├── extractors/
│   │   └── contact.ts       # 联系方式提取
│   ├── queue/
│   │   └── processor.ts     # 任务队列处理
│   ├── utils/
│   │   ├── hash.ts          # 内容哈希
│   │   ├── rateLimit.ts     # 速率限制
│   │   └── logger.ts
│   └── cli/
│       └── index.ts         # CLI 入口
└── scripts/
    ├── backfill.ts          # 回溯爬取脚本
    ├── incremental.ts       # 增量更新脚本
    └── enrich.ts            # 信息扩充脚本
```

---

## 8. API Keys 需求

| 服务 | 用途 | 获取方式 |
|------|------|----------|
| Product Hunt | 获取产品和 Maker 信息 | https://api.producthunt.com/v2/oauth/applications |
| SerpAPI | Twitter/LinkedIn/通用搜索 | https://serpapi.com/ |
| GitHub | 用户信息和仓库 | https://github.com/settings/tokens |
| Supabase | 数据存储 | 已有 |

---

## 9. 实施计划

### Phase 1: 基础设施
- [ ] 创建数据库表
- [ ] 配置环境变量
- [ ] 实现 Supabase client

### Phase 2: Product Hunt 爬虫
- [ ] 实现 GraphQL client
- [ ] 实现回溯模式
- [ ] 实现增量模式
- [ ] 实现 Maker 提取和去重

### Phase 3: 信息扩充
- [ ] 实现 SerpAPI 集成 (Twitter, LinkedIn, General)
- [ ] 实现 GitHub API 集成
- [ ] 实现 arXiv API 集成
- [ ] 实现增量搜索逻辑

### Phase 4: 联系方式提取
- [ ] 从各源提取联系方式
- [ ] 实现可信度评分
- [ ] 去重和验证

### Phase 5: CLI 和自动化
- [ ] 实现 CLI 命令
- [ ] 配置定时任务 (cron)
- [ ] 监控和日志

---

## 10. 使用示例 (预期)

```bash
# 回溯爬取 Product Hunt (从今天往回爬30天)
npx ts-node scripts/backfill.ts --days 30

# 增量更新 (爬取新数据)
npx ts-node scripts/incremental.ts

# 扩充指定人员的信息
npx ts-node scripts/enrich.ts --person-id <uuid>

# 扩充所有 importance_score > 50 的人
npx ts-node scripts/enrich.ts --min-score 50

# 增量更新某人的知识 (只搜索 cutoff 之后的新内容)
npx ts-node scripts/enrich.ts --person-id <uuid> --incremental
```

---

## 11. 注意事项

### 速率限制
- **Product Hunt**: Fair-use policy, 建议每秒不超过 1 请求
- **SerpAPI**: 根据订阅计划, 有月度配额
- **GitHub**: 认证用户 5000 req/hour, 搜索 API 30 req/min
- **arXiv**: 建议请求间隔 3 秒

### 法律合规
- Product Hunt API 默认不允许商业用途，需联系获取许可
- 遵守各平台 Terms of Service
- 存储个人信息需注意 GDPR/隐私法规

### 成本估算
- SerpAPI: ~$50/月 (5000 searches)
- GitHub: Free (with rate limits)
- arXiv: Free
- Supabase: 免费层或 $25/月

---

## 12. 下一步

确认本方案后，我将：
1. 创建数据库 schema SQL 文件
2. 初始化 TypeScript 项目
3. 按 Phase 顺序逐步实现

请确认或提出修改意见！
