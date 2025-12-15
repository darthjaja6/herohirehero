# Network Hunt

从 Product Hunt 发现优秀创业者/Maker，建立人才数据库。

## 功能

- **三阶段爬取**: API获取帖子 → 爬取帖子页面获取makers → 爬取用户档案
- **任务队列**: 基于 Supabase 的分布式任务队列，支持断点续爬
- **双模式**: 回溯历史数据 (backfill) + 增量更新 (incremental)

## 架构

所有数据存储在 Supabase：

| 表 | 用途 |
|---|---|
| `ph_posts` | Product Hunt 产品信息 |
| `ph_profiles` | 用户档案详情 |
| `post_people` | 产品-人员关联 (makers) |
| `task_queue` | 爬取任务队列 |

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
SUPABASE_KEY=your-anon-or-service-key

# Product Hunt (https://api.producthunt.com/v2/oauth/applications)
PRODUCT_HUNT_DEVELOPER_TOKEN=xxx
```

## 使用

### 完整爬取流程

```bash
# 并发运行所有阶段 (推荐，最快)
network-hunt crawl parallel --mode backfill --days 365

# 顺序运行所有阶段
network-hunt crawl all --mode backfill --days 365

# 增量更新
network-hunt crawl parallel --mode incremental
```

**parallel vs all:**
- `parallel`: 三个阶段并发运行，各自处理 pending 任务，速度最快
- `all`: 按顺序运行 (api → posts → profiles)，适合首次运行确保数据依赖

### 分阶段运行

```bash
# 阶段1: 从 API 获取帖子列表
network-hunt crawl api --mode backfill --days 30
network-hunt crawl api --mode incremental

# 阶段2: 爬取帖子页面，提取 makers
network-hunt crawl posts --limit 100

# 阶段3: 爬取用户档案
network-hunt crawl profiles --limit 100
```

### 查看状态

```bash
# 数据库统计 + 任务队列状态
network-hunt stats

# 仅查看任务队列
network-hunt tasks

# 重试失败的任务
network-hunt tasks --retry-failed

# 清理卡住的任务 (processing 状态超时)
network-hunt tasks --cleanup
```

### 重置数据

```bash
# 重置所有进度和数据 (谨慎使用)
network-hunt reset
```

## 爬取策略

### Backfill 模式
- 从指定天数前开始，逐天爬取历史数据
- 自动跳过已爬取的日期
- 适合首次运行或补充历史数据

### Incremental 模式
- 从上次爬取位置继续
- 只获取新发布的产品
- 适合日常增量更新

## 注意事项

- Product Hunt API 有 rate limit，爬取时会自动控制速度
- 爬取帖子页面和用户档案使用 HTTP 请求，注意频率
- 建议先小范围测试：`network-hunt crawl all --days 7 --limit 10`
