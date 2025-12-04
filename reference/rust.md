# Rust Code Review Guide

> Rust 代码审查指南。编译器能捕获内存安全问题，但审查者需要关注编译器无法检测的问题——业务逻辑、API 设计、性能、取消安全性和可维护性。

## 目录

- [现代 Rust 习语 (Modern Idioms)](#现代-rust-习语-modern-idioms)
- [所有权与借用](#所有权与借用)
- [Unsafe 代码审查](#unsafe-代码审查最关键)
- [异步代码与可观测性](#异步代码与可观测性)
- [取消安全性](#取消安全性)
- [spawn vs await](#spawn-vs-await)
- [错误处理](#错误处理)
- [性能](#性能)
- [API 设计与 Typestate](#api-设计与-typestate)
- [Review Checklist](#rust-review-checklist)

---

## 现代 Rust 习语 (Modern Idioms)

### let-else (Rust 1.65+)

```rust
// ❌ 传统的 match/if let 嵌套，导致右移（Rightward Drift）
fn process_user(id: Option<i32>) {
    if let Some(user_id) = id {
        if let Some(user) = find_user(user_id) {
            // 业务逻辑深层嵌套
            process(user);
        } else {
            return;
        }
    } else {
        return;
    }
}

// ✅ 使用 let-else 提前返回，减少嵌套
fn process_user(id: Option<i32>) {
    let Some(user_id) = id else { return };
    let Some(user) = find_user(user_id) else { return };

    // 业务逻辑在顶层
    process(user);
}
```

### 派生 Default 与 Smart Constructors

```rust
// ❌ 手动实现 Default 或使用 new() 但参数过多
struct Config {
    timeout: u64,
    retries: u32,
    verbose: bool,
}

impl Config {
    fn new(timeout: u64, retries: u32, verbose: bool) -> Self {
        Self { timeout, retries, verbose }
    }
}

// ✅ 派生 Default 并提供构建器风格的方法
#[derive(Default)]
struct Config {
    timeout: u64,
    retries: u32,
    verbose: bool,
}

impl Config {
    // 覆盖默认值的方法
    fn with_timeout(mut self, timeout: u64) -> Self {
        self.timeout = timeout;
        self
    }
}

// 使用
let config = Config::default().with_timeout(5000);
```

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

// ✅ 如果确实需要 clone，添加注释说明原因
fn justified_clone(data: &Data) -> Result<()> {
    // Clone needed: data will be moved to spawned task
    let owned = data.clone();
    tokio::spawn(async move {
        process(owned).await
    });
    Ok(())
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

// ✅ 如果确实需要并发访问，考虑更好的数据结构
use dashmap::DashMap;

struct ConcurrentService {
    cache: DashMap<String, Data>,  // 更细粒度的锁
}
```

### Cow (Copy-on-Write) 模式

```rust
use std::borrow::Cow;

// ❌ 总是分配新字符串
fn bad_process_name(name: &str) -> String {
    if name.is_empty() {
        "Unknown".to_string()  // 分配
    } else {
        name.to_string()  // 不必要的分配
    }
}

// ✅ 使用 Cow 避免不必要的分配
fn good_process_name(name: &str) -> Cow<'_, str> {
    if name.is_empty() {
        Cow::Borrowed("Unknown")  // 静态字符串，无分配
    } else {
        Cow::Borrowed(name)  // 借用原始数据
    }
}

// ✅ 只在需要修改时才分配
fn normalize_name(name: &str) -> Cow<'_, str> {
    if name.chars().any(|c| c.is_uppercase()) {
        Cow::Owned(name.to_lowercase())  // 需要修改，分配
    } else {
        Cow::Borrowed(name)  // 无需修改，借用
    }
}
```

---

## Unsafe 代码审查（最关键！）

### 基本要求

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

### Unsafe 块注释

```rust
// ❌ 没有解释的 unsafe 块
fn bad_get_unchecked(slice: &[u8], index: usize) -> u8 {
    unsafe { *slice.get_unchecked(index) }
}

// ✅ 每个 unsafe 块必须有 SAFETY 注释
fn good_get_unchecked(slice: &[u8], index: usize) -> u8 {
    debug_assert!(index < slice.len(), "index out of bounds");
    // SAFETY: We verified index < slice.len() via debug_assert.
    // In release builds, callers must ensure valid index.
    unsafe { *slice.get_unchecked(index) }
}

// ✅ 封装 unsafe 提供安全 API
pub fn checked_get(slice: &[u8], index: usize) -> Option<u8> {
    if index < slice.len() {
        // SAFETY: bounds check performed above
        Some(unsafe { *slice.get_unchecked(index) })
    } else {
        None
    }
}
```

### 常见 unsafe 模式

```rust
// ✅ FFI 边界
extern "C" {
    fn external_function(ptr: *const u8, len: usize) -> i32;
}

pub fn safe_wrapper(data: &[u8]) -> Result<i32, Error> {
    // SAFETY: data.as_ptr() is valid for data.len() bytes,
    // and external_function only reads from the buffer.
    let result = unsafe {
        external_function(data.as_ptr(), data.len())
    };
    if result < 0 {
        Err(Error::from_code(result))
    } else {
        Ok(result)
    }
}

// ✅ 性能关键路径的 unsafe
pub fn fast_copy(src: &[u8], dst: &mut [u8]) {
    assert_eq!(src.len(), dst.len(), "slices must be equal length");
    // SAFETY: src and dst are valid slices of equal length,
    // and dst is mutable so no aliasing.
    unsafe {
        std::ptr::copy_nonoverlapping(
            src.as_ptr(),
            dst.as_mut_ptr(),
            src.len()
        );
    }
}
```

---

## 异步代码与可观测性

### Tracing vs Println

```rust
// ❌ 在 async 代码中使用 println! 或 log crate
// 无法关联同一请求的不同日志，缺乏结构化信息
async fn bad_log(user_id: &str) {
    println!("Processing user {}", user_id);
    db.query().await;
    println!("Done");
}

// ✅ 使用 tracing crate
// 自动携带上下文（span），支持结构化日志，兼容 OpenTelemetry
#[tracing::instrument(skip(data))]
async fn good_log(user_id: &str, data: Data) {
    tracing::info!("Processing user"); // 自动包含 user_id
    if let Err(e) = db.query().await {
        tracing::error!(error = ?e, "Database query failed");
    }
}
```

### 避免阻塞操作

```rust
// ❌ 在 async 上下文中阻塞——会饿死其他任务
async fn bad_async() {
    let data = std::fs::read_to_string("file.txt").unwrap();  // 阻塞！
    std::thread::sleep(Duration::from_secs(1));  // 阻塞！
}

// ✅ 使用异步 API
async fn good_async() -> Result<String> {
    let data = tokio::fs::read_to_string("file.txt").await?;
    tokio::time::sleep(Duration::from_secs(1)).await;
    Ok(data)
}

// ✅ 如果必须使用阻塞操作，用 spawn_blocking
async fn with_blocking() -> Result<Data> {
    let result = tokio::task::spawn_blocking(|| {
        // 这里可以安全地进行阻塞操作
        expensive_cpu_computation()
    }).await?;
    Ok(result)
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

// ✅ 方案1：最小化锁范围
async fn good_lock_scoped(mutex: &std::sync::Mutex<Data>) {
    let data = {
        let guard = mutex.lock().unwrap();
        guard.clone()  // 立即释放锁
    };
    async_operation().await;
    process(&data);
}

// ✅ 方案2：使用 tokio::sync::Mutex（可跨 await）
async fn good_lock_tokio(mutex: &tokio::sync::Mutex<Data>) {
    let guard = mutex.lock().await;
    async_operation().await;  // OK: tokio Mutex 设计为可跨 await
    process(&guard);
}
```

---

## 取消安全性

### 什么是取消安全

```rust
// 当一个 Future 在 .await 点被 drop 时，它处于什么状态？
// 取消安全的 Future：可以在任何 await 点安全取消
// 取消不安全的 Future：取消可能导致数据丢失或不一致状态

// ❌ 取消不安全的例子
async fn cancel_unsafe(conn: &mut Connection) -> Result<()> {
    let data = receive_data().await;  // 如果这里被取消...
    conn.send_ack().await;  // ...确认永远不会发送，数据可能丢失
    Ok(())
}

// ✅ 取消安全的版本
async fn cancel_safe(conn: &mut Connection) -> Result<()> {
    // 使用事务或原子操作确保一致性
    let transaction = conn.begin_transaction().await?;
    let data = receive_data().await;
    transaction.commit_with_ack(data).await?;  // 原子操作
    Ok(())
}
```

### select! 中的取消安全

```rust
use tokio::select;

// ❌ 在 select! 中使用取消不安全的 Future
async fn bad_select(stream: &mut TcpStream) {
    let mut buffer = vec![0u8; 1024];
    loop {
        select! {
            // 如果 timeout 先完成，read 被取消
            // 部分读取的数据可能丢失！
            result = stream.read(&mut buffer) => {
                handle_data(&buffer[..result?]);
            }
            _ = tokio::time::sleep(Duration::from_secs(5)) => {
                println!("Timeout");
            }
        }
    }
}

// ✅ 使用取消安全的 API
async fn good_select(stream: &mut TcpStream) {
    let mut buffer = vec![0u8; 1024];
    loop {
        select! {
            // tokio::io::AsyncReadExt::read 是取消安全的
            // 取消时，未读取的数据留在流中
            result = stream.read(&mut buffer) => {
                match result {
                    Ok(0) => break,  // EOF
                    Ok(n) => handle_data(&buffer[..n]),
                    Err(e) => return Err(e),
                }
            }
            _ = tokio::time::sleep(Duration::from_secs(5)) => {
                println!("Timeout, retrying...");
            }
        }
    }
}

// ✅ 使用 tokio::pin! 确保 Future 可以安全重用
async fn pinned_select() {
    let sleep = tokio::time::sleep(Duration::from_secs(10));
    tokio::pin!(sleep);

    loop {
        select! {
            _ = &mut sleep => {
                println!("Timer elapsed");
                break;
            }
            data = receive_data() => {
                process(data).await;
                // sleep 继续倒计时，不会重置
            }
        }
    }
}
```

---

## spawn vs await

### 何时使用 spawn

```rust
// ❌ 不必要的 spawn——增加开销，失去结构化并发
async fn bad_unnecessary_spawn() {
    let handle = tokio::spawn(async {
        simple_operation().await
    });
    handle.await.unwrap();  // 为什么不直接 await？
}

// ✅ 直接 await 简单操作
async fn good_direct_await() {
    simple_operation().await;
}

// ✅ spawn 用于真正的并行执行
async fn good_parallel_spawn() {
    let task1 = tokio::spawn(fetch_from_service_a());
    let task2 = tokio::spawn(fetch_from_service_b());

    // 两个请求并行执行
    let (result1, result2) = tokio::try_join!(task1, task2)?;
}

// ✅ spawn 用于后台任务（fire-and-forget）
async fn good_background_spawn() {
    // 启动后台任务，不等待完成
    tokio::spawn(async {
        cleanup_old_sessions().await;
        // 使用 tracing 记录错误
        if let Err(e) = log_metrics().await {
            tracing::error!(error = ?e, "Failed to log metrics");
        }
    });

    // 继续执行其他工作
    handle_request().await;
}
```

### spawn 的 'static 要求

```rust
// ❌ spawn 的 Future 必须是 'static
async fn bad_spawn_borrow(data: &Data) {
    tokio::spawn(async {
        process(data).await;  // Error: `data` 不是 'static
    });
}

// ✅ 方案1：克隆数据
async fn good_spawn_clone(data: &Data) {
    let owned = data.clone();
    tokio::spawn(async move {
        process(&owned).await;
    });
}

// ✅ 方案2：使用 Arc 共享
async fn good_spawn_arc(data: Arc<Data>) {
    let data = Arc::clone(&data);
    tokio::spawn(async move {
        process(&data).await;
    });
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

## API 设计与 Typestate

### Typestate 模式 (状态机类型安全)

```rust
// ❌ 运行时检查状态
struct Order {
    state: String,
    items: Vec<Item>,
}

impl Order {
    fn pay(&mut self) {
        if self.state != "created" {
            panic!("Cannot pay order in state {}", self.state);
        }
        self.state = "paid".to_string();
    }
}

// ✅ 编译时检查状态 (Typestate)
struct Order<State> {
    items: Vec<Item>,
    state: std::marker::PhantomData<State>,
}

struct Created;
struct Paid;
struct Shipped;

impl Order<Created> {
    fn pay(self) -> Order<Paid> {
        // 执行支付逻辑
        Order {
            items: self.items,
            state: std::marker::PhantomData,
        }
    }
}

impl Order<Paid> {
    fn ship(self) -> Order<Shipped> {
        // 执行发货逻辑
        Order {
            items: self.items,
            state: std::marker::PhantomData,
        }
    }
}

// 无法对 Created 状态的订单调用 ship()：
// let order = Order::<Created>::new();
// order.ship(); // 编译错误！
```

---

## Rust Review Checklist

### 现代 Rust 习语
- [ ] 使用 `let-else` 减少嵌套
- [ ] 使用 `#[derive(Default)]` 而非手动实现
- [ ] 优先使用标准库/生态系统中的既定 trait (From/TryFrom)

### 可观测性 (Observability)
- [ ] Async 代码使用 `tracing` 而非 `println!` 或 `log`
- [ ] `tracing::instrument` 用于关键业务方法
- [ ] 错误日志包含上下文和错误链 (`error = ?e`)

### 所有权与借用
- [ ] clone() 是有意为之，文档说明了原因
- [ ] Arc<Mutex<T>> 真的需要共享状态吗？
- [ ] 生命周期不过度复杂
- [ ] 考虑使用 Cow 避免不必要的分配

### Unsafe 代码（最重要）
- [ ] 每个 unsafe 块有 SAFETY 注释
- [ ] unsafe fn 有 # Safety 文档节
- [ ] 解释了为什么是安全的，不只是做什么
- [ ] unsafe 边界尽可能小

### 异步/并发
- [ ] 没有在 async 中阻塞（std::fs、thread::sleep）
- [ ] 没有跨 .await 持有 std::sync 锁
- [ ] spawn 的任务满足 'static
- [ ] 文档化了 async 函数的取消安全性
- [ ] select! 中的 Future 是取消安全的

### 错误处理
- [ ] 库：thiserror 定义结构化错误
- [ ] 应用：anyhow + context
- [ ] 没有生产代码 unwrap/expect
- [ ] 使用 #[source] 保留错误链

### API 设计
- [ ] 使用 Typestate 模式将运行时错误转换为编译时错误
- [ ] 公共 API 难以误用
- [ ] 类型签名清晰表达意图
