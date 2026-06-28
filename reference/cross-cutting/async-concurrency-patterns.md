# 异步与并发模式 — 跨语言通用指南

> 本文档覆盖并发模型对比、常见陷阱、跨语言最佳实践和结构化并发模式。

## 目录

- [并发模型对比](#并发模型对比)
- [常见陷阱](#常见陷阱)
- [最佳实践](#最佳实践)
- [跨语言代码示例](#跨语言代码示例)
- [Review Checklist](#review-checklist)

---

## 并发模型对比

| 模型 | 语言 | 核心概念 | 优点 | 缺点 |
|------|------|----------|------|------|
| **Goroutines + Channels** | Go | 轻量级协程 + CSP 通信 | 极简语法、低开销 | 手动取消传播 |
| **async/await + Event Loop** | Python, TypeScript | 单线程协作式多任务 | 无锁、易推理 | 不能阻塞事件循环 |
| **async/await + Tokio** | Rust | Futures + 运行时调度 | 零成本抽象、编译期安全 | 学习曲线陡 |
| **Coroutines + Flow** | Kotlin | 挂起函数 + 结构化并发 | 自动取消、生命周期绑定 | Dispatchers 选择复杂 |
| **async/await + Actors** | Swift | 结构化并发 + Actor 隔离 | 编译期数据竞争检查 | Swift 6 迁移成本 |
| **async/await + TPL** | C# | Task + 线程池 | 成熟生态、ConfigureAwait | 隐式线程切换 |
| **Threads + Mutexes** | C++, Java, 所有 | OS 线程 + 共享内存 | 真正并行 | 锁管理复杂、死锁风险 |

### 何时选择什么

```
I/O 密集型（网络、数据库、文件）:
  → async/await（Python, TS, Rust, Swift, C#）
  → goroutines（Go）
  → coroutines（Kotlin）

CPU 密集型（计算、图像处理）:
  → 线程池（Java, C++, C#）
  → multiprocessing（Python）
  → spawn_blocking（Rust tokio）
  → Dispatchers.Default（Kotlin）

混合型:
  → async + spawn_blocking（Rust）
  → async + run_in_executor（Python）
  → goroutines + sync.Mutex（Go）
```

---

## 常见陷阱

### 陷阱 1: 竞态条件（Race Condition）

多个并发任务读写共享状态，结果依赖执行顺序。

```
// 通用伪代码
counter = 0

task1: counter += 1   // 读 counter=0, 写 counter=1
task2: counter += 1   // 读 counter=0, 写 counter=1
// 期望 counter=2, 实际 counter=1
```

**解决方案**：互斥锁、原子操作、或将共享状态封装在 Actor 中。

### 陷阱 2: 死锁（Deadlock）

两个或多个任务互相等待对方持有的锁。

```
task1: lock(A); lock(B);  // 持有 A，等待 B
task2: lock(B); lock(A);  // 持有 B，等待 A
// 两者永远等待
```

**解决方案**：
- 一致的锁获取顺序
- 超时锁（tryLock with timeout）
- 避免嵌套锁

### 陷阱 3: Starvation

低优先级任务永远得不到执行机会。

```
// 高优先级任务持续到达，低优先级任务永远排队
```

**解决方案**：公平锁、任务优先级队列、限制并发数。

### 陷阱 4: Goroutine / Task 泄漏

启动并发任务但没有确保其退出。

```go
// ❌ Go: goroutine 泄漏
func process() {
    ch := make(chan int)
    go func() {
        result := <-ch  // 如果没有人发送，goroutine 永远阻塞
    }()
    // 函数返回，但 goroutine 仍在等待
}
```

```python
# ❌ Python: Task 泄漏
async def process():
    task = asyncio.create_task(long_running())
    # 函数返回，但 task 仍在运行
```

**解决方案**：使用 context/done channel (Go)、TaskGroup (Python)、structured concurrency (Kotlin/Swift)。

### 陷阱 5: 在异步上下文中阻塞

```python
# ❌ Python: 在 async 函数中使用同步 I/O 阻塞事件循环
async def handle():
    result = requests.get(url)  # 阻塞！整个事件循环停滞
    return result

# ✅ 使用异步 I/O 或将阻塞操作放到线程池
async def handle():
    result = await aiohttp.get(url)  # 非阻塞
    return result

# 或将同步代码放到线程池
async def handle():
    result = await asyncio.to_thread(requests.get, url)
    return result
```

```rust
// ❌ Rust: 在 async 函数中阻塞
async fn handle() {
    let result = std::fs::read_to_string("large.txt");  // 阻塞 tokio 运行时
}

// ✅ 使用 spawn_blocking
async fn handle() {
    let result = tokio::task::spawn_blocking(|| {
        std::fs::read_to_string("large.txt")
    }).await?;
}
```

---

## 最佳实践

### 1. 结构化并发

确保并发任务的生命周期与创建它们的 scope 绑定。父任务取消时，子任务自动取消。

```kotlin
// ✅ Kotlin: coroutineScope 确保子协程在 scope 结束时全部完成
suspend fun processItems(items: List<Item>) = coroutineScope {
    items.forEach { item ->
        launch { processItem(item) }  // 子协程
    }
    // scope 结束时等待所有子协程完成
}

// 如果 processItems 被取消，所有子协程自动取消
```

```swift
// ✅ Swift: async let + TaskGroup
func processItems() async throws {
    async let resultA = fetchA()  // 并发执行
    async let resultB = fetchB()
    let combined = try await (resultA, resultB)  // 等待两者
}
```

```python
# ✅ Python 3.11+: TaskGroup
async def process_items():
    async with asyncio.TaskGroup() as tg:
        for item in items:
            tg.create_task(process_item(item))
    # TaskGroup 退出时等待所有任务完成
    # 如果一个任务失败，其余任务自动取消
```

### 2. 取消传播

确保取消信号能正确传播到所有子任务。

```go
// ✅ Go: context 传播取消
func processAll(ctx context.Context, items []Item) error {
    g, ctx := errgroup.WithContext(ctx)
    for _, item := range items {
        item := item
        g.Go(func() error {
            return processItem(ctx, item)
        })
    }
    return g.Wait()  // 任一失败，context 取消，其余任务收到信号
}
```

```rust
// ✅ Rust: tokio::select! + JoinHandle
async fn process_with_timeout(item: Item) -> Result<Data> {
    tokio::select! {
        result = process(item) => result,
        _ = tokio::time::sleep(Duration::from_secs(30)) => {
            Err(anyhow!("processing timed out"))
        }
    }
}
```

### 3. Backpressure（反压）

当生产者速度远超消费者时，需要限制队列大小，防止内存膨胀。

```go
// ✅ Go: 有缓冲 channel 作为自然反压
func process(items <-chan Item) <-chan Result {
    results := make(chan Result, 10)  // 缓冲 10 个结果
    go func() {
        for item := range items {
            results <- processItem(item)  // 缓冲满时阻塞
        }
        close(results)
    }()
    return results
}
```

```kotlin
// ✅ Kotlin: Flow 自带反压
fun itemsFlow(): Flow<Item> = flow {
    for (item in fetchAll()) {
        emit(item)  // collector 未准备好时挂起
    }
}
// 使用 buffer() 控制缓冲策略
itemsFlow()
    .buffer(capacity = 10, onBufferOverflow = BufferOverflow.SUSPEND)
    .collect { process(it) }
```

### 4. 限制并发数

防止同时启动过多任务导致资源耗尽。

```python
# ✅ Python: Semaphore 限制并发
async def fetch_all(urls: list[str], max_concurrent: int = 10):
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(url: str):
        async with semaphore:
            return await aiohttp.get(url)

    return await asyncio.gather(*[fetch_one(url) for url in urls])
```

```go
// ✅ Go: errgroup + semaphore
func fetchAll(ctx context.Context, urls []string, maxConcurrent int) error {
    g, ctx := errgroup.WithContext(ctx)
    sem := make(chan struct{}, maxConcurrent)

    for _, url := range urls {
        url := url
        g.Go(func() error {
            sem <- struct{}{}        // 获取信号量
            defer func() { <-sem }() // 释放信号量
            return fetch(ctx, url)
        })
    }
    return g.Wait()
}
```

---

## 跨语言代码示例

### Go: Goroutines + Channels + Context

```go
// ✅ 完整模式: context 取消 + errgroup + 有界并发
func processBatch(ctx context.Context, items []Item) ([]Result, error) {
    g, ctx := errgroup.WithContext(ctx)
    results := make([]Result, len(items))
    sem := make(chan struct{}, 10)  // 最多 10 个并发

    for i, item := range items {
        i, item := i, item
        g.Go(func() error {
            select {
            case sem <- struct{}{}:
            case <-ctx.Done():
                return ctx.Err()
            }
            defer func() { <-sem }()

            result, err := process(ctx, item)
            if err != nil {
                return fmt.Errorf("item %d: %w", i, err)
            }
            results[i] = result
            return nil
        })
    }

    if err := g.Wait(); err != nil {
        return nil, err
    }
    return results, nil
}
```

### Python: asyncio + TaskGroup

```python
# ✅ Python 3.11+: 结构化并发 + 有界并发 + 超时
import asyncio

async def process_batch(items: list[Item], max_concurrent: int = 10) -> list[Result]:
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_one(item: Item) -> Result:
        async with semaphore:
            return await process(item)

    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(process_one(item)) for item in items]

    return [task.result() for task in tasks]
```

### Rust: tokio + select + spawn_blocking

```rust
// ✅ 有界并发 + 超时 + 阻塞操作隔离
use tokio::sync::Semaphore;
use std::sync::Arc;

async fn process_batch(items: Vec<Item>, max_concurrent: usize) -> Result<Vec<Output>> {
    let sem = Arc::new(Semaphore::new(max_concurrent));
    let mut handles = Vec::new();

    for item in items {
        let permit = sem.clone().acquire_owned().await?;
        handles.push(tokio::spawn(async move {
            let _permit = permit;  // drop on completion
            tokio::select! {
                result = process(item) => result,
                _ = tokio::time::sleep(Duration::from_secs(30)) => {
                    Err(anyhow!("timeout"))
                }
            }
        }));
    }

    let mut results = Vec::new();
    for handle in handles {
        results.push(handle.await??);
    }
    Ok(results)
}
```

### Kotlin: Coroutines + Flow + Dispatchers

```kotlin
// ✅ 结构化并发 + 有界并发 + 取消安全
suspend fun processBatch(items: List<Item>, maxConcurrent: Int = 10): List<Result> {
    val semaphore = Semaphore(maxConcurrent)

    return coroutineScope {
        items.map { item ->
            async(Dispatchers.IO) {
                semaphore.withPermit {
                    process(item)
                }
            }
        }.awaitAll()
    }
}

// ✅ Flow: 流式处理 + 反压
fun itemStream(): Flow<Result> = flow {
    for (item in fetchAllItems()) {
        emit(process(item))
    }
}
    .flowOn(Dispatchers.IO)
    .buffer(capacity = 10)
    .catch { e -> logger.error("stream failed", e) }
```

### Swift: async/await + TaskGroup + Actors

```swift
// ✅ 结构化并发 + actor 隔离
actor ResultCollector {
    private var results: [Result] = []
    func add(_ result: Result) { results.append(result) }
    func all() -> [Result] { results }
}

func processBatch(items: [Item], maxConcurrent: Int = 10) async throws -> [Result] {
    let collector = ResultCollector()

    try await withThrowingTaskGroup(of: Void.self) { group in
        var active = 0
        for item in items {
            if active >= maxConcurrent {
                try await group.next()
                active -= 1
            }
            group.addTask {
                let result = try await process(item)
                await collector.add(result)
            }
            active += 1
        }
    }

    return await collector.all()
}
```

### C#: async/await + SemaphoreSlim + CancellationToken

```csharp
// ✅ 有界并发 + 取消 + 异常处理
async Task<List<Result>> ProcessBatchAsync(
    List<Item> items,
    int maxConcurrent = 10,
    CancellationToken ct = default)
{
    using var semaphore = new SemaphoreSlim(maxConcurrent);
    var tasks = items.Select(async item =>
    {
        await semaphore.WaitAsync(ct);
        try
        {
            return await ProcessAsync(item, ct);
        }
        finally
        {
            semaphore.Release();
        }
    });

    var results = await Task.WhenAll(tasks);
    return results.ToList();
}
```

### TypeScript: Worker-pool 并发限制

```typescript
// ✅ Worker-pool pattern: 固定数量 worker 竞争任务队列
//    结果按原始索引赋值，保证输出顺序与输入一致。
async function processWithLimit<T, R>(
    items: T[],
    fn: (item: T) => Promise<R>,
    limit: number,
): Promise<R[]> {
    const results: R[] = [];
    let index = 0;

    const workers = Array.from({ length: limit }, async () => {
        while (index < items.length) {
            const i = index++;
            results[i] = await fn(items[i]);
        }
    });

    await Promise.all(workers);
    return results;
}
```

---

## Review Checklist

### 基本检查
- [ ] 并发任务有明确的退出机制（不会泄漏）
- [ ] 共享状态有适当保护（mutex、actor、channel）
- [ ] 没有在异步上下文中执行阻塞操作
- [ ] 取消信号正确传播到所有子任务

### 架构检查
- [ ] 使用结构化并发（TaskGroup / coroutineScope / errgroup）
- [ ] 并发数有上限（semaphore / bounded channel）
- [ ] 长时间运行的任务支持超时
- [ ] 背压机制防止内存膨胀

### 性能检查
- [ ] 并发粒度合理（不过细也不过粗）
- [ ] I/O 密集使用 async，CPU 密集使用线程/进程
- [ ] 锁的持有时间最小化
- [ ] 没有不必要的 await（可并行的操作串行执行）

### 语言特定
- [ ] Go: context 传播、errgroup 使用、channel 缓冲合理
- [ ] Python: 事件循环不阻塞、TaskGroup 管理生命周期
- [ ] Rust: spawn_blocking 隔离阻塞操作、select! 处理超时
- [ ] Kotlin: coroutineScope 结构化并发、Dispatchers 选择正确
- [ ] Swift: @MainActor 保护 UI、actor 隔离可变状态
- [ ] C#: CancellationToken 传播、ConfigureAwait(false) 在库代码中
- [ ] TypeScript: Promise.all + 并发限制、AbortController 取消
