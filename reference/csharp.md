# C# / .NET Code Review Guide

> C# / .NET 8 代码审查指南，覆盖 C# 12 新特性、异步编程、EF Core 性能、ASP.NET Core 最佳实践、依赖注入、LINQ 等核心主题。

## 目录

- [C# 12 新特性](#c-12-新特性)
- [异步编程](#异步编程)
- [EF Core 性能](#ef-core-性能)
- [ASP.NET Core 最佳实践](#aspnet-core-最佳实践)
- [依赖注入](#依赖注入)
- [LINQ 最佳实践](#linq-最佳实践)
- [Review Checklist](#review-checklist)

---

## C# 12 新特性

### Primary Constructors（非 record 类型）

```csharp
// ❌ 样板代码过多的传统构造函数
public class ProductService
{
    private readonly ProductDbContext _db;
    private readonly ILogger<ProductService> _logger;

    public ProductService(ProductDbContext db, ILogger<ProductService> logger)
    {
        _db = db;
        _logger = logger;
    }
}

// ✅ Primary Constructor——简洁的依赖注入
public class ProductService(ProductDbContext db, ILogger<ProductService> logger)
{
    public async Task<Product?> GetAsync(int id)
        => await db.Products.FindAsync(id);
}

// ⚠️ 注意：primary constructor 参数不是属性，不能被重新赋值
// ⚠️ 如果需要长期存储，显式声明字段
public class OrderService(OrderDbContext db)
{
    private readonly OrderDbContext _db = db; // 显式捕获
}
```

### Collection Expressions

```csharp
// ❌ 传统集合初始化
int[] nums = new int[] { 1, 2, 3 };
List<string> names = new List<string> { "alice", "bob" };

// ✅ 集合表达式
int[] nums = [1, 2, 3];
List<string> names = ["alice", "bob"];
Span<char> span = ['a', 'b'];

// ✅ 展开运算符
int[] merged = [..nums, 4, 5];
```

### Default Lambda Parameters

```csharp
// ❌ 重载 lambda
var add = (int a, int b) => a + b;
var addDefault = (int a) => a + 1;

// ✅ 默认参数
var add = (int a, int b = 1) => a + b;
```

---

## 异步编程

> 📖 通用并发模式和跨语言示例详见 [异步与并发跨语言指南](cross-cutting/async-concurrency-patterns.md)

### Task.Wait() / .Result / async void 是严重反模式

```csharp
// ❌ Task.Wait() —— 死锁风险（同步阻塞异步操作）
public ActionResult<Data> Get(int id)
{
    var data = _service.GetDataAsync(id).Result; // 死锁！
    return Ok(data);
}

// ❌ async void —— 异常无法捕获，会崩溃进程
public async void HandleEvent()
{
    await _service.ProcessAsync(); // 异常直接崩溃
}

// ✅ async Task —— 全链路异步
public async Task<ActionResult<Data>> Get(int id)
{
    var data = await _service.GetDataAsync(id);
    return Ok(data);
}
```

### ConfigureAwait(false) 用于库代码

```csharp
// ❌ 库代码不必要地捕获 SynchronizationContext
public class LibraryService
{
    public async Task<string> GetDataAsync()
    {
        var response = await _httpClient.GetAsync("/api/data");
        return await response.Content.ReadAsStringAsync();
    }
}

// ✅ 库代码使用 ConfigureAwait(false) 避免死锁
public class LibraryService
{
    public async Task<string> GetDataAsync()
    {
        var response = await _httpClient.GetAsync("/api/data").ConfigureAwait(false);
        return await response.Content.ReadAsStringAsync().ConfigureAwait(false);
    }
}
```

### CancellationToken 传播

```csharp
// ❌ 丢弃 CancellationToken
public async Task<List<User>> SearchAsync(string query)
{
    return await _db.Users.Where(u => u.Name.Contains(query)).ToListAsync();
}

// ✅ 全链路传递 CancellationToken
public async Task<List<User>> SearchAsync(string query, CancellationToken ct = default)
{
    return await _db.Users
        .Where(u => u.Name.Contains(query))
        .ToListAsync(ct);
}
```

### Async Disposal

```csharp
// ❌ 同步 dispose 异步资源
public class DataClient : IDisposable
{
    public void Dispose()
    {
        _httpClient.Dispose(); // 可能丢弃正在进行的请求
    }
}

// ✅ IAsyncDisposable
public class DataClient : IAsyncDisposable
{
    public async ValueTask DisposeAsync()
    {
        await _stream.DisposeAsync();
    }
}

// ✅ 调用方使用 await using
await using var client = new DataClient();
```

---

## EF Core 性能

### N+1 查询问题

> 📖 通用原理和跨语言方案详见 [N+1 查询跨语言指南](cross-cutting/n-plus-one-queries.md)

```csharp
// ❌ 经典 N+1——每个 Blog 触发一次查询获取 Posts
foreach (var blog in await context.Blogs.ToListAsync())
{
    foreach (var post in blog.Posts) // 每次循环都查询数据库！
    {
        Console.WriteLine(post.Title);
    }
}

// ✅ Eager Loading + 投影
await foreach (var blog in context.Blogs
    .Select(b => new { b.Url, b.Posts })
    .AsAsyncEnumerable())
{
    foreach (var post in blog.Posts)
        Console.WriteLine(post.Title);
}
```

### 过度获取（不投影）

```csharp
// ❌ 加载所有列——只需要 Url 时加载了全部字段
var urls = await context.Blogs.ToListAsync();

// ✅ 只投影需要的字段
var urls = await context.Blogs
    .Select(b => b.Url)
    .ToListAsync();
```

### 缺少分页

```csharp
// ❌ 无界结果集
var posts = await context.Posts
    .Where(p => p.Title.StartsWith("A"))
    .ToListAsync(); // 可能有百万条记录！

// ✅ 限制结果数量
var posts = await context.Posts
    .Where(p => p.Title.StartsWith("A"))
    .OrderBy(p => p.Id)
    .Skip((page - 1) * pageSize)
    .Take(pageSize)
    .ToListAsync();
```

### Cartesian Explosion（JOIN 笛卡尔爆炸）

```csharp
// ❌ 多个 Include 创建大量重复数据
var blogs = await context.Blogs
    .Include(b => b.Posts)
    .Include(b => b.Tags)
    .ToListAsync(); // 每行重复 Blog 数据

// ✅ 使用 AsSplitQuery 拆分查询
var blogs = await context.Blogs
    .Include(b => b.Posts)
    .Include(b => b.Tags)
    .AsSplitQuery()
    .ToListAsync();
```

### 只读场景缺少 AsNoTracking

```csharp
// ❌ 默认跟踪——只读查询也付出跟踪开销
var products = await context.Products.ToListAsync();

// ✅ AsNoTracking——跳过变更跟踪，更快且更省内存
var products = await context.Products
    .AsNoTracking()
    .ToListAsync();
```

### 列上函数阻止索引使用

```csharp
// ✅ 可以使用索引——sargable
var posts1 = await context.Posts
    .Where(p => p.Title.StartsWith("A"))
    .ToListAsync();

// ❌ 无法使用索引——全表扫描
var posts2 = await context.Posts
    .Where(p => p.Title.EndsWith("A"))
    .ToListAsync();

// ❌ 列上套函数——全表扫描
var posts3 = await context.Posts
    .Where(p => p.Title.ToLower() == "foo")
    .ToListAsync();
```

### 同步 vs 异步数据库访问

```csharp
// ❌ 同步数据库调用——阻塞线程
var products = context.Products.ToList();
context.SaveChanges();

// ✅ 异步数据库调用
var products = await context.Products.ToListAsync();
await context.SaveChangesAsync();
```

---

## ASP.NET Core 最佳实践

### HttpClient 误用

```csharp
// ❌ 每次请求创建新的 HttpClient——socket 耗尽
using var client = new HttpClient();
var response = await client.GetAsync("https://api.example.com/data");

// ✅ IHttpClientFactory 注入
public class MyService
{
    private readonly HttpClient _client;
    public MyService(HttpClient client) => _client = client; // 从工厂注入
}
```

### HttpContext 在后台线程中使用

```csharp
// ❌ 在后台任务中捕获 scoped 服务——请求结束后已释放
_ = Task.Run(async () =>
{
    await context.SaveChangesAsync(); // ObjectDisposedException!
});

// ✅ 创建新的 scope
_ = Task.Run(async () =>
{
    await using var scope = serviceScopeFactory.CreateAsyncScope();
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    await db.SaveChangesAsync();
});
```

### Request.Form 同步访问

```csharp
// ❌ 同步读取 Form——sync over async
var form = HttpContext.Request.Form;

// ✅ 异步读取
var form = await HttpContext.Request.ReadFormAsync();
```

### 异常用于控制流

```csharp
// ❌ 用异常判断是否存在——异常开销大，比直接检查慢得多
try
{
    var user = await _db.Users.FirstAsync(u => u.Id == id);
}
catch (InvalidOperationException)
{
    return NotFound();
}

// ✅ 使用检查而非异常
var user = await _db.Users.FirstOrDefaultAsync(u => u.Id == id);
if (user is null) return NotFound();
```

### 响应头在 Body 之后设置

```csharp
// ❌ body 已发送后再设置 header——抛异常
await next(context);
context.Response.Headers["X-Custom"] = "value"; // 可能抛异常！

// ✅ 使用 OnStarting 回调
context.Response.OnStarting(() =>
{
    context.Response.Headers["X-Custom"] = "value";
    return Task.CompletedTask;
});
await next(context);
```

---

## 依赖注入

### Scoped 服务注入 Singleton

```csharp
// ❌ Scoped 服务注入 Singleton——生命周期不匹配
services.AddSingleton<BackgroundWorker>();
services.AddScoped<IUserRepository, UserRepository>();

// BackgroundWorker 是 Singleton，UserRepository 是 Scoped
// → UserRepository 在多个请求间共享或已释放

// ✅ 在 Singleton 中通过 IServiceProvider 创建 scope
public class BackgroundWorker : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;

    public BackgroundWorker(IServiceScopeFactory scopeFactory)
        => _scopeFactory = scopeFactory;

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        await using var scope = _scopeFactory.CreateAsyncScope();
        var repo = scope.ServiceProvider.GetRequiredService<IUserRepository>();
    }
}
```

---

## LINQ 最佳实践

### ToList 之后再 LINQ

```csharp
// ❌ 先 ToList 再过滤——全表加载到内存
var results = context.Posts
    .Where(p => p.Title.StartsWith("A"))
    .ToList()
    .Where(p => SomeClientFilter(p)); // 客户端过滤，已加载全部行

// ✅ 尽可能让数据库执行过滤
var results = await context.Posts
    .Where(p => p.Title.StartsWith("A") && SomeDbFilter(p))
    .AsAsyncEnumerable()
    .Where(p => SomeClientFilter(p)) // 只过滤数据库返回的行
    .ToListAsync();
```

### Count() vs Any()

```csharp
// ❌ Count() 执行完整查询
if (context.Users.Count() > 0) { /* ... */ }

// ✅ Any() 更高效——遇到第一条记录就返回
if (await context.Users.AnyAsync()) { /* ... */ }
```

### 多次枚举 IEnumerable

```csharp
// ❌ IEnumerable 被枚举两次
public void Process(IEnumerable<int> numbers)
{
    if (numbers.Any()) // 第一次枚举
    {
        foreach (var n in numbers) // 第二次枚举（可能是重新查询）
        {
            Console.WriteLine(n);
        }
    }
}

// ✅ 如果需要多次使用，先物化
public void Process(IEnumerable<int> numbers)
{
    var list = numbers.ToList(); // 只枚举一次
    if (list.Any())
    {
        foreach (var n in list)
        {
            Console.WriteLine(n);
        }
    }
}
```

### Select 中的副作用

```csharp
// ❌ Select 中执行副作用——不可预测的执行时机
var results = users.Select(u =>
{
    _logger.LogInformation($"Processing {u.Name}"); // 副作用！
    return u.Email;
}).ToList();

// ✅ 副作用放在 foreach 中
foreach (var user in users)
{
    _logger.LogInformation("Processing {Name}", user.Name);
}
var results = users.Select(u => u.Email).ToList();
```

---

## Review Checklist

### C# 12 新特性

- [ ] Primary constructor 参数不被重新赋值
- [ ] 集合表达式语法一致（不混用新旧风格）

### 异步编程

- [ ] 无 `Task.Wait()`、`.Result`、`async void`
- [ ] 库代码使用 `ConfigureAwait(false)`
- [ ] `CancellationToken` 全链路传递
- [ ] 异步资源使用 `IAsyncDisposable` / `await using`
- [ ] 不混用同步和异步数据访问

### EF Core

- [ ] 无 N+1 查询（导航属性在循环中访问）
- [ ] 投影 `Select()` 避免过度获取
- [ ] 分页：`ToListAsync()` 前有 `Take()`/`Skip()`
- [ ] 多个 `Include()` 使用 `AsSplitQuery()`
- [ ] 只读查询使用 `AsNoTracking()`
- [ ] 列上无函数调用阻止索引使用
- [ ] 数据库调用全部异步

### ASP.NET Core

- [ ] HttpClient 通过 `IHttpClientFactory` 获取
- [ ] 后台任务中不直接使用 scoped 服务
- [ ] 使用 `ReadFormAsync` 代替 `Request.Form`
- [ ] 异常不用于控制流
- [ ] 响应头通过 `OnStarting` 设置

### 依赖注入

- [ ] Scoped 服务不注入 Singleton
- [ ] 后台任务创建新 scope

### LINQ

- [ ] 无不必要的 `ToList()` 后再 LINQ
- [ ] `Any()` 代替 `Count() > 0`
- [ ] IEnumerable 不被多次枚举（或先物化）
- [ ] Select 中无副作用
