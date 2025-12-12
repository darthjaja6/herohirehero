# HeroHireHero

> Hero only hire hero. Hero only work for hero.

## 理念

未来的招聘不再是LinkedIn式的"标准件匹配"。真正优秀的人，只需要几个问题就能识别彼此。

我们相信：
- 牛逼的人能一眼识别另一个牛逼的人
- 志同道合、有远见、有能耐的人应该更容易找到彼此
- 简单直接，不需要冗长的简历和面试流程

## 核心筛选问题

只需回答三个问题：

1. **What is the thing you have done that you are most proud of?**
   （你做过的最自豪的事是什么？）

2. **What's the hardest problem you have conquered?**
   （你攻克过的最难的问题是什么？）

3. **What's your dream?**
   （你的梦想是什么？）

通过这三个问题的回答，我们帮助like-minded的人发现彼此。

## 产品流程

1. 用户访问网站，阅读理念
2. 填写三个核心问题的回答并提交
3. 信息存入人才库（Supabase）
4. 后台进行匹配
5. 匹配成功后，双方收到邮件通知

## 技术栈

- **前端**: 纯HTML/CSS（极简，专注内容）
- **后端/数据库**: Supabase
- **邮件通知**: 待定（可考虑Supabase Edge Functions + Resend/SendGrid）

## 项目结构

```
herohirehero/
├── README.md          # 项目总纲
├── index.html         # 首页（理念 + 提交表单）
├── style.css          # 样式
└── js/
    └── main.js        # Supabase交互逻辑
```

## 开发计划

### Phase 1: MVP
- [ ] 创建首页HTML（理念展示 + 表单）
- [ ] 设置Supabase项目和数据表
- [ ] 实现表单提交功能
- [ ] 基础样式设计

### Phase 2: 匹配与通知
- [ ] 设计匹配算法/规则
- [ ] 实现邮件通知功能
- [ ] 管理后台（可选）

### Phase 3: 迭代优化
- [ ] 根据反馈优化问题设计
- [ ] 优化匹配精度
- [ ] 扩展功能

## 数据模型

### heroes 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | 主键 |
| email | text | 邮箱（用于通知） |
| name | text | 姓名（可选） |
| proud_of | text | 最自豪的事 |
| hardest_problem | text | 攻克的最难问题 |
| dream | text | 梦想 |
| created_at | timestamp | 提交时间 |

---

*Built for heroes, by heroes.*
