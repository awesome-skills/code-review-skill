# Rust Code Review Guide

> Rust 代码审查指南。编译器能捕获内存安全问题，但审查者需要关注编译器无法检测的问题——业务逻辑、API 设计、性能和可维护性。

---

## 所有权与借用

### 避免不必要的 clone()

```rust
// ❌ clone() 是"Rust 的胶带"——用于绕过借用检查器
fn bad_process(data: &Data) -> Result<()> {
    let owned = data.clone();  // 为什么需要 clone？
    expensive_operation(owned)
}

// ✅ 审查时问：clone 是否必要？能否用借用？
fn good_process(data: &Data) -> Result<()> {
    expensive_operation(data)  // 传递引用
}
```

### Arc<Mutex<T>> 的使用

```rust
// ❌ Arc<Mutex<T>> 可能隐藏不必要的共享状态
struct BadService {
    cache: Arc<Mutex<HashMap<String, Data>>>,  // 真的需要共享？
}

// ✅ 考虑是否需要共享，或者设计可以避免
struct GoodService {
    cache: HashMap<String, Data>,  // 单一所有者
}
```

---

## Unsafe 代码审查（最关键！）

```rust
// ❌ unsafe 没有安全文档——这是红旗
unsafe fn bad_transmute<T, U>(t: T) -> U {
    std::mem::transmute(t)
}

// ✅ 每个 unsafe 必须解释：为什么安全？什么不变量？
/// Transmutes `T` to `U`.
///
/// # Safety
///
/// - `T` and `U` must have the same size and alignment
/// - `T` must be a valid bit pattern for `U`
/// - The caller ensures no references to `t` exist after this call
unsafe fn documented_transmute<T, U>(t: T) -> U {
    // SAFETY: Caller guarantees size/alignment match and bit validity
    std::mem::transmute(t)
}
```

---

## 异步代码

### 避免阻塞操作

```rust
// ❌ 在 async 上下文中阻塞——会饿死其他任务
async fn bad_async() {
    let data = std::fs::read_to_string("file.txt").unwrap();  // 阻塞！
    std::thread::sleep(Duration::from_secs(1));  // 阻塞！
}

// ✅ 使用异步 API
async fn good_async() {
    let data = tokio::fs::read_to_string("file.txt").await?;
    tokio::time::sleep(Duration::from_secs(1)).await;
}
```

### Mutex 和 .await

```rust
// ❌ 跨 .await 持有 std::sync::Mutex——可能死锁
async fn bad_lock(mutex: &std::sync::Mutex<Data>) {
    let guard = mutex.lock().unwrap();
    async_operation().await;  // 持锁等待！
    process(&guard);
}

// ✅ 最小化锁范围，或使用 tokio::sync::Mutex
async fn good_lock(mutex: &std::sync::Mutex<Data>) {
    let data = mutex.lock().unwrap().clone();  // 立即释放
    async_operation().await;
    process(&data);
}
```

---

## 错误处理

### 库 vs 应用的错误类型

```rust
// ❌ 库代码用 anyhow——调用者无法 match 错误
pub fn parse_config(s: &str) -> anyhow::Result<Config> { ... }

// ✅ 库用 thiserror，应用用 anyhow
#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error("invalid syntax at line {line}: {message}")]
    Syntax { line: usize, message: String },
    #[error("missing required field: {0}")]
    MissingField(String),
    #[error(transparent)]
    Io(#[from] std::io::Error),
}

pub fn parse_config(s: &str) -> Result<Config, ConfigError> { ... }
```

### 保留错误上下文

```rust
// ❌ 吞掉错误上下文
fn bad_error() -> Result<()> {
    operation().map_err(|_| anyhow!("failed"))?;  // 原始错误丢失
    Ok(())
}

// ✅ 使用 context 保留错误链
fn good_error() -> Result<()> {
    operation().context("failed to perform operation")?;
    Ok(())
}
```

---

## 性能

### 避免不必要的 collect()

```rust
// ❌ 不必要的 collect——中间分配
fn bad_sum(items: &[i32]) -> i32 {
    items.iter()
        .filter(|x| **x > 0)
        .collect::<Vec<_>>()  // 不必要！
        .iter()
        .sum()
}

// ✅ 惰性迭代
fn good_sum(items: &[i32]) -> i32 {
    items.iter().filter(|x| **x > 0).sum()
}
```

### 字符串拼接

```rust
// ❌ 字符串拼接在循环中重复分配
fn bad_concat(items: &[&str]) -> String {
    let mut s = String::new();
    for item in items {
        s = s + item;  // 每次都重新分配！
    }
    s
}

// ✅ 预分配或用 join
fn good_concat(items: &[&str]) -> String {
    items.join("")  // 或用 with_capacity
}
```

---

## Trait 设计

```rust
// ❌ 过度抽象——不是 Java，不需要 Interface 一切
trait Processor { fn process(&self); }
trait Handler { fn handle(&self); }
trait Manager { fn manage(&self); }  // Trait 过多

// ✅ 只在需要多态时创建 trait
// 具体类型通常更简单、更快
```

---

## Rust Review Checklist

### 编译器不能捕获的问题

**业务逻辑正确性**
- [ ] 边界条件处理正确
- [ ] 状态机转换完整
- [ ] 并发场景下的竞态条件

**API 设计**
- [ ] 公共 API 难以误用
- [ ] 类型签名清晰表达意图
- [ ] 错误类型粒度合适

### 所有权与借用

- [ ] clone() 是有意为之，文档说明了原因
- [ ] Arc<Mutex<T>> 真的需要共享状态吗？
- [ ] RefCell 的使用有正当理由
- [ ] 生命周期不过度复杂

### Unsafe 代码（最重要）

- [ ] 每个 unsafe 块有 SAFETY 注释
- [ ] unsafe fn 有 # Safety 文档节
- [ ] 解释了为什么是安全的，不只是做什么
- [ ] 列出了必须维护的不变量
- [ ] unsafe 边界尽可能小
- [ ] 考虑过是否有 safe 替代方案

### 异步/并发

- [ ] 没有在 async 中阻塞（std::fs、thread::sleep）
- [ ] 没有跨 .await 持有 std::sync 锁
- [ ] spawn 的任务满足 'static
- [ ] 锁的获取顺序一致
- [ ] Channel 缓冲区大小合理

### 错误处理

- [ ] 库：thiserror 定义结构化错误
- [ ] 应用：anyhow + context
- [ ] 没有生产代码 unwrap/expect
- [ ] 错误消息对调试有帮助
- [ ] must_use 返回值被处理

### 性能

- [ ] 避免不必要的 collect()
- [ ] 大数据传引用
- [ ] 字符串用 with_capacity 或 write!
- [ ] impl Trait vs Box<dyn Trait> 选择合理
- [ ] 热路径避免分配

### 代码质量

- [ ] cargo clippy 零警告
- [ ] cargo fmt 格式化
- [ ] 文档注释完整
- [ ] 测试覆盖边界条件
- [ ] 公共 API 有文档示例
