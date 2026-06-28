# N+1 查询问题 — 跨语言通用指南

> N+1 查询是 ORM 和数据库访问层最常见的性能反模式。本文档覆盖问题定义、检测方法、通用解决方案和跨语言代码示例。

## 目录

- [问题定义](#问题定义)
- [性能影响](#性能影响)
- [检测方法](#检测方法)
- [通用解决方案](#通用解决方案)
- [语言特定实现](#语言特定实现)
- [Review Checklist](#review-checklist)

---

## 问题定义

N+1 查询是指：**1 次查询获取 N 条记录，随后在循环中触发 N 次额外查询**来获取关联数据。

```
请求流程:
  1 query   → 获取 N 条主记录
  N queries → 每条主记录查一次关联数据
  ─────────
  Total: 1 + N queries
```

### 危害

| 问题 | 影响 |
|------|------|
| **查询数量线性增长** | 100 条记录 = 101 条 SQL，1000 条 = 1001 条 |
| **网络延迟叠加** | 每条查询都有往返延迟（RTT），N 次往返 >> 1 次批量查询 |
| **连接池耗尽** | 大量查询占满数据库连接，拖慢整个应用 |
| **难以在开发中发现** | 开发环境数据少，N+1 不明显；生产环境数据量大时性能崩塌 |

---

## 性能影响

### 场景对比：获取 100 个用户及其订单

| 方案 | SQL 数量 | 延迟（假设 RTT=1ms） | 适用场景 |
|------|----------|---------------------|---------|
| N+1 懒加载 | 101 条 | ~101ms | 极少数据量 |
| Eager loading (JOIN) | 1 条 | ~1ms | 一对多，数据量适中 |
| Eager loading (IN) | 2 条 | ~2ms | 多对多，大数据集 |
| DataLoader / batch | 2 条 | ~2ms | GraphQL / 复杂图查询 |

### SQL 数量对比

```sql
-- ❌ N+1: 1 + 100 = 101 queries
SELECT * FROM users;                          -- 1 query
SELECT * FROM orders WHERE user_id = 1;       -- query 2
SELECT * FROM orders WHERE user_id = 2;       -- query 3
...
SELECT * FROM orders WHERE user_id = 100;     -- query 101

-- ✅ Batch: 2 queries
SELECT * FROM users;
SELECT * FROM orders WHERE user_id IN (1,2,...,100);
```

---

## 检测方法

### 1. ORM SQL 日志

开启 SQL 日志，在测试或开发环境中观察查询数量：

```python
# Django
import logging
logging.getLogger('django.db.backends').setLevel(logging.DEBUG)

# SQLAlchemy
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

```java
// Spring Boot application.yml
spring:
  jpa:
    show-sql: true
    properties:
      hibernate.format_sql: true
```

```csharp
// EF Core
optionsBuilder.LogTo(Console.WriteLine, LogLevel.Information);
```

### 2. 查询计数断言

在测试中断言 SQL 查询数量：

```python
# Django: django-assert-num-queries
from django.test.utils import CaptureQueriesContext
from django.db import connection

with CaptureQueriesContext(connection) as ctx:
    list(User.objects.select_related("profile").all())
assert len(ctx) <= 2  # 预期最多 2 条查询
```

```java
// Hibernate: p6spy 或 datasource-proxy
// 在测试中统计 SQL 执行次数
assertThat(sqlCount).isLessThanOrEqualTo(2);
```

### 3. APM / 数据库监控工具

- **Django Debug Toolbar** — 实时显示 SQL 数量和时间
- **p6spy** (Java) — JDBC 层拦截，记录所有 SQL
- **MiniProfiler** (.NET) — 页面内嵌 SQL 统计
- **DataDog / New Relic** — 生产环境慢查询告警

---

## 通用解决方案

### 方案 1: Eager Loading（JOIN 预加载）

一次 JOIN 查询获取主记录和关联记录。适用于一对一、一对多。

### 方案 2: Batch Fetching（IN 子句批量查询）

两次查询：主记录 + `WHERE id IN (...)` 批量获取关联记录。适用于多对多、大数据集。

### 方案 3: DataLoader Pattern

在 GraphQL 或复杂图查询场景中，收集所有需要的 ID，合并为一次批量查询。

```
// DataLoader 伪代码
class DataLoader<K, V> {
    load(K key) → V         // 注册需求，不立即查询
    loadAll([K]) → [V]      // 合并为一次批量查询
}
```

### 方案 4: Projection（投影）

只查询需要的字段，减少数据传输量：

```sql
-- ❌ 获取所有列
SELECT * FROM users JOIN profiles ON ...

-- ✅ 只投影需要的字段
SELECT u.name, p.avatar_url FROM users u JOIN profiles p ON ...
```

---

## 语言特定实现

### Python / Django

> 详见 [Django Guide](../django.md#n1-查询优化)

```python
# ForeignKey / OneToOne → select_related (SQL JOIN)
books = Book.objects.select_related("publisher")

# M2M / reverse FK → prefetch_related (2 queries + Python merge)
authors = Author.objects.prefetch_related("books")

# 嵌套预加载
authors = Author.objects.prefetch_related("books__publisher")

# Prefetch 对象精细控制
from django.db.models import Prefetch
authors = Author.objects.prefetch_related(
    Prefetch("books", queryset=Book.objects.filter(published=True), to_attr="published_books")
)
```

### Python / SQLAlchemy (FastAPI)

> 详见 [FastAPI Guide](../fastapi.md#database-sessions--n1)

```python
from sqlalchemy.orm import selectinload

# selectinload: IN 子句批量加载（推荐异步场景）
stmt = select(Order).options(selectinload(Order.customer))

# joinedload: JOIN 加载
stmt = select(Order).options(joinedload(Order.customer))
```

### Java / JPA (Spring Boot)

> 详见 [Java Guide](../java.md)

```java
// ❌ FetchType.EAGER 或循环中触发懒加载
@OneToMany(fetch = FetchType.EAGER)  // 危险！

// ✅ JOIN FETCH
@Query("SELECT u FROM User u JOIN FETCH u.orders")
List<User> findAllWithOrders();

// ✅ @EntityGraph（声明式）
@EntityGraph(attributePaths = {"orders", "profile"})
List<User> findAll();

// ✅ @BatchSize（减少 N+1 为 N/batchSize + 1）
@OneToMany
@BatchSize(size = 50)
private List<Order> orders;
```

### C# / EF Core

> 详见 [C# Guide](../csharp.md)

```csharp
// ❌ N+1: foreach 触发懒加载
foreach (var blog in await context.Blogs.ToListAsync())
    foreach (var post in blog.Posts)  // 每次循环都查询！

// ✅ Include + ThenInclude
var blogs = await context.Blogs
    .Include(b => b.Posts)
    .ToListAsync();

// ✅ 投影（最安全，避免过度获取）
var data = await context.Blogs
    .Select(b => new { b.Url, PostTitles = b.Posts.Select(p => p.Title) })
    .ToListAsync();
```

### PHP / Laravel / Doctrine

> 详见 [PHP Guide](../php.md)

```php
// ❌ 循环内查询
foreach ($orders as $order) {
    $customer = $customerRepo->find($order->customerId);
    render($order, $customer);
}

// ✅ 批量预加载
$customerIds = array_unique(array_map(fn($o) => $o->customerId, $orders));
$customers = $customerRepo->findByIds($customerIds);

foreach ($orders as $order) {
    render($order, $customers[$order->customerId] ?? null);
}

// Laravel Eloquent: with()
$orders = Order::with('customer')->get();

// Doctrine: JOIN FETCH
$dql = 'SELECT o, c FROM Order o JOIN o.customer c';
```

### TypeScript / Prisma

```typescript
// ❌ N+1
const users = await prisma.user.findMany();
for (const user of users) {
    user.posts = await prisma.post.findMany({ where: { userId: user.id } });
}

// ✅ include（Prisma 自动生成 JOIN 或批量查询）
const users = await prisma.user.findMany({
    include: { posts: true },
});

// ✅ 嵌套 include
const users = await prisma.user.findMany({
    include: {
        posts: {
            include: { comments: true },
        },
    },
});
```

---

## Review Checklist

### 检测
- [ ] 开启了 SQL 日志或查询计数监控
- [ ] 测试中有查询数量断言
- [ ] APM 工具配置了 N+1 告警

### 修复
- [ ] ForeignKey / OneToOne 关系使用 JOIN eager loading
- [ ] M2M / 反向关系使用 IN 批量预加载
- [ ] 避免在循环中触发数据库查询
- [ ] 使用投影只获取需要的字段

### 架构
- [ ] 列表 API 分页，避免一次加载过多记录
- [ ] GraphQL 场景使用 DataLoader
- [ ] 缓存策略（Redis）处理高频读取的关联数据
