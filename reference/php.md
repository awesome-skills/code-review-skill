# PHP Code Review Guide

> PHP 8.x 代码审查指南，覆盖类型系统、现代语言特性、OOP 建模、PDO 数据访问、安全、错误处理、Composer 依赖、性能与测试。

## 目录

- [快速审查清单](#快速审查清单)
- [类型系统与现代 PHP](#类型系统与现代-php)
- [对象建模](#对象建模)
- [输入输出与安全](#输入输出与安全)
- [数据库访问](#数据库访问)
- [错误处理](#错误处理)
- [Composer 与依赖](#composer-与依赖)
- [性能与资源管理](#性能与资源管理)
- [测试与静态分析](#测试与静态分析)
- [Review Checklist](#review-checklist)
- [参考资料](#参考资料)

---

## 快速审查清单

### 必查项

- [ ] 新文件是否启用 `declare(strict_types=1);`
- [ ] 公共 API 是否有参数、返回值和属性类型
- [ ] 用户输入是否经过验证，输出是否按上下文转义
- [ ] SQL 是否使用参数化查询或 ORM binding
- [ ] 密码是否使用 `password_hash()` / `password_verify()`
- [ ] 文件上传是否校验 MIME、大小、扩展名和存储路径
- [ ] `composer.lock` 是否提交，依赖范围是否合理
- [ ] 是否有 PHPUnit/Pest 测试和 PHPStan/Psalm 静态分析

### 高频问题

- [ ] 弱比较 `==` / `!=` 导致类型转换漏洞
- [ ] 使用 `md5()` / `sha1()` 存密码
- [ ] 拼接 SQL、HTML、shell 命令或文件路径
- [ ] 使用 `@` 抑制错误
- [ ] `unserialize()` 处理不可信数据
- [ ] `$_GET` / `$_POST` / `$_FILES` 直接进入业务逻辑
- [ ] PHP 8.2+ 动态属性导致 deprecation，PHP 9 可能升级为错误

---

## 类型系统与现代 PHP

### strict_types 与显式类型

```php
<?php

// ❌ 弱类型边界：调用方传入 "42" 也会被悄悄转换
function findUser($id) {
    return User::find($id);
}

// ✅ 文件顶部启用 strict_types，公共 API 写清类型
declare(strict_types=1);

function findUser(int $id): ?User
{
    return User::find($id);
}
```

审查时不要把类型检查只交给运行时输入验证。类型声明表达的是代码内部契约，输入验证表达的是边界可信度，两者都需要。

### 避免弱比较

```php
<?php

// ❌ "0e12345" 这类字符串在弱比较下可能被当成 0
if ($providedHash == $storedHash) {
    grantAccess();
}

// ✅ 严格比较；密钥或 token 比较使用 hash_equals()
if (hash_equals($storedHash, $providedHash)) {
    grantAccess();
}

// ✅ match 使用 identity check，比 switch 更少类型转换意外
$status = match ($code) {
    200 => 'ok',
    404 => 'not_found',
    default => 'unknown',
};
```

重点关注鉴权、支付、状态机、权限判断里的 `==`、`!=`、`in_array($x, $list)` 默认弱比较。需要时使用 `===`、`!==`、`in_array($x, $list, true)`。

### Union / Intersection / Nullable 类型

```php
<?php

// ❌ mixed 或无类型让调用方猜返回形状
function loadConfig($source) {
    return parseConfig($source);
}

// ✅ 用类型表达真实契约
function loadConfig(string|PathInfo $source): Config
{
    return parseConfig($source);
}

// ✅ null 是业务状态时显式表达
function currentUser(): ?User
{
    return Auth::user();
}
```

`mixed` 可以出现在边界层或兼容旧代码的过渡期，但出现在核心业务服务中通常意味着缺少建模。

### Nullsafe operator 不应隐藏缺失状态

```php
<?php

// ❌ 链式 nullsafe 让失败原因变模糊
$country = $order?->customer?->profile?->country;

// ✅ 对关键业务状态给出明确分支
if ($order === null) {
    throw new OrderNotFound();
}

$customer = $order->customer();
if ($customer === null) {
    throw new MissingCustomer($order->id);
}

$country = $customer->profile()?->country;
```

审查时区分“可选展示字段”和“必须存在的业务不变量”。前者适合 `?->`，后者应该显式失败。

---

## 对象建模

### 使用 readonly 属性和值对象

```php
<?php

// ❌ 公开可变数组，调用方可以随意改状态
class Money
{
    public $amount;
    public $currency;
}

// ✅ 用类型和 readonly 表达不可变值对象
final readonly class Money
{
    public function __construct(
        public int $amount,
        public string $currency,
    ) {
        if ($amount < 0) {
            throw new InvalidArgumentException('Amount must be non-negative');
        }
    }
}
```

对 DTO、配置、领域值对象，优先看是否能用 `readonly class` 或 readonly 属性减少隐藏副作用。

### Enums 替代字符串状态

```php
<?php

// ❌ 字符串状态容易拼错，也无法枚举所有合法值
if ($order->status === 'paied') {
    ship($order);
}

// ✅ enum 让非法状态更早暴露
enum OrderStatus: string
{
    case Pending = 'pending';
    case Paid = 'paid';
    case Cancelled = 'cancelled';
}

if ($order->status === OrderStatus::Paid) {
    ship($order);
}
```

审查状态机、权限、类型字段时，优先寻找“字符串魔法值”。如果值集合稳定，建议 enum；如果来自外部系统，建议转换到内部 enum 后再进入业务层。

### 不要依赖动态属性

```php
<?php

// ❌ PHP 8.2+ 创建动态属性会触发 deprecation
$user = new User();
$user->emali = 'a@example.com'; // 拼写错误也会创建属性

// ✅ 声明属性或使用专门的数据结构
final class User
{
    public function __construct(
        public string $email,
    ) {}
}
```

`#[AllowDynamicProperties]` 应该是兼容遗留代码的例外，而不是新代码的默认选择。审查时要特别留意序列化、ORM hydration、测试替身里是否靠动态属性工作。

### 构造函数不要做重 I/O

```php
<?php

// ❌ 构造对象时偷偷连数据库，测试和错误处理都困难
final class ReportService
{
    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = new PDO($_ENV['DSN']);
    }
}

// ✅ 依赖从外部注入
final class ReportService
{
    public function __construct(
        private PDO $pdo,
    ) {}
}
```

构造函数应建立对象不变量，不应发送 HTTP 请求、打开连接、读大文件或做复杂查询。

---

## 输入输出与安全

### 输入验证放在边界层

```php
<?php

// ❌ 超全局变量直接进入业务逻辑
$user = $service->create($_POST['email'], $_POST['age']);

// ✅ 边界层先校验并转换类型
$email = filter_input(INPUT_POST, 'email', FILTER_VALIDATE_EMAIL);
$age = filter_input(INPUT_POST, 'age', FILTER_VALIDATE_INT, [
    'options' => ['min_range' => 0, 'max_range' => 130],
]);

if ($email === false || $email === null || $age === false || $age === null) {
    throw new InvalidInput();
}

$user = $service->create($email, $age);
```

`filter_input()` 只能处理一部分基础校验。复杂规则、跨字段约束、业务约束仍需要专门的 validator 或 request DTO。

### HTML 输出必须按上下文转义

```php
<?php

// ❌ 用户输入直接进入 HTML
echo "<h1>Hello {$_GET['name']}</h1>";

// ✅ HTML 文本上下文使用 htmlspecialchars
$name = (string) ($_GET['name'] ?? '');
echo '<h1>Hello ' . htmlspecialchars($name, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') . '</h1>';
```

不同上下文需要不同转义：HTML 文本、HTML 属性、URL、JavaScript 字符串、CSS 都不一样。模板引擎默认转义被关闭时，要把它当作安全风险。

### 密码与随机数

```php
<?php

// ❌ md5/sha1 不能用于密码存储
$hash = md5($password);

// ✅ 使用 PHP 内置密码 API
$hash = password_hash($password, PASSWORD_DEFAULT);

if (!password_verify($password, $hash)) {
    throw new InvalidCredentials();
}

// ✅ token 使用 CSPRNG
$token = bin2hex(random_bytes(32));
$code = random_int(100000, 999999);
```

不要手写 salt、轮数迁移或密码比较逻辑。需要升级成本时用 `password_needs_rehash()`。

### 反序列化与对象注入

```php
<?php

// ❌ 不可信输入进入 unserialize，可能触发对象注入
$payload = unserialize($_COOKIE['state']);

// ✅ 外部数据优先使用 JSON，并校验 schema/shape
$payload = json_decode($_COOKIE['state'] ?? '{}', true, flags: JSON_THROW_ON_ERROR);
```

如果必须处理历史 serialized 数据，至少限制 `allowed_classes`，并确保相关类的 magic methods 不会产生危险副作用。

### 文件上传和路径

```php
<?php

// ❌ 使用原始文件名拼路径
$target = __DIR__ . '/uploads/' . $_FILES['avatar']['name'];
move_uploaded_file($_FILES['avatar']['tmp_name'], $target);

// ✅ 生成服务端文件名，校验上传错误和 MIME
$file = $_FILES['avatar'];
if ($file['error'] !== UPLOAD_ERR_OK) {
    throw new UploadFailed();
}

$finfo = new finfo(FILEINFO_MIME_TYPE);
$mime = $finfo->file($file['tmp_name']);
if (!in_array($mime, ['image/png', 'image/jpeg'], true)) {
    throw new InvalidFileType();
}

$target = __DIR__ . '/uploads/' . bin2hex(random_bytes(16)) . '.jpg';
move_uploaded_file($file['tmp_name'], $target);
```

审查上传功能时检查大小限制、MIME 检测、扩展名、存储目录不可执行、路径穿越、防覆盖、病毒扫描或异步处理要求。

---

## 数据库访问

### 使用参数化查询

```php
<?php

// ❌ 拼接 SQL，存在注入风险
$sql = "SELECT * FROM users WHERE email = '" . $_GET['email'] . "'";
$user = $pdo->query($sql)->fetch();

// ✅ PDO prepared statement + bound value
$stmt = $pdo->prepare('SELECT id, email FROM users WHERE email = :email');
$stmt->execute(['email' => $email]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);
```

参数只能绑定值，不能绑定表名、列名、排序方向。动态 identifier 必须用白名单映射。

```php
<?php

// ✅ 动态排序字段使用白名单
$columns = [
    'created' => 'created_at',
    'email' => 'email',
];

$column = $columns[$_GET['sort'] ?? 'created'] ?? $columns['created'];
$stmt = $pdo->query("SELECT id, email FROM users ORDER BY {$column} DESC");
```

### 事务覆盖完整业务操作

```php
<?php

// ❌ 多步写入没有事务，中途失败会留下半成品
$orderId = $orders->create($cart);
$inventory->reserve($cart);
$payments->charge($orderId);

// ✅ 明确事务边界
$pdo->beginTransaction();
try {
    $orderId = $orders->create($cart);
    $inventory->reserve($cart);
    $payments->recordIntent($orderId);
    $pdo->commit();
} catch (Throwable $e) {
    $pdo->rollBack();
    throw $e;
}
```

外部不可回滚副作用（真正扣款、发邮件、消息投递）不要随便放进数据库事务里。常见方案是 outbox、幂等 key 或事务提交后再触发。

### 避免 N+1 查询

```php
<?php

// ❌ 循环里查询
foreach ($orders as $order) {
    $customer = $customerRepo->find($order->customerId);
    render($order, $customer);
}

// ✅ 批量加载再映射
$customerIds = array_unique(array_map(fn ($o) => $o->customerId, $orders));
$customers = $customerRepo->findByIds($customerIds);

foreach ($orders as $order) {
    render($order, $customers[$order->customerId] ?? null);
}
```

在 Laravel/Doctrine 等 ORM 中，对应检查 eager loading、join fetch、select 列、分页和索引。

---

## 错误处理

### 捕获具体异常，保留上下文

```php
<?php

// ❌ 吞掉异常，调用方无法知道失败
try {
    $mailer->send($message);
} catch (Exception $e) {
}

// ✅ 捕获具体异常，保留上下文并继续抛出
try {
    $mailer->send($message);
} catch (TransportException $e) {
    throw new NotificationFailed($userId, previous: $e);
}
```

生产代码里的空 `catch`、只 `error_log()` 不返回错误、把所有异常转成 `RuntimeException('failed')` 都值得追问。

### 不要使用 @ 抑制错误

```php
<?php

// ❌ 隐藏真实错误，调试困难
$content = @file_get_contents($path);

// ✅ 显式处理失败
$content = file_get_contents($path);
if ($content === false) {
    throw new RuntimeException("Unable to read file: {$path}");
}
```

`@` 常见于文件、网络、数组访问和遗留库调用。审查时优先要求显式分支或把第三方库错误转换成项目内异常。

### 日志不要泄漏敏感信息

```php
<?php

// ❌ 把 token、密码、完整请求体写入日志
$logger->error('Login failed', ['request' => $_POST]);

// ✅ 记录可定位问题的非敏感上下文
$logger->warning('Login failed', [
    'email_hash' => hash('sha256', strtolower($email)),
    'ip' => $requestIp,
]);
```

检查日志、异常消息、debug toolbar、错误页面和队列失败记录。敏感信息包括密码、token、session、PII、支付数据和完整 cookie。

---

## Composer 与依赖

### 锁定可复现依赖

```json
{
  "require": {
    "php": "^8.2",
    "monolog/monolog": "^3.0"
  },
  "require-dev": {
    "phpunit/phpunit": "^11.0",
    "phpstan/phpstan": "^1.10"
  }
}
```

审查 `composer.json` / `composer.lock` 时关注：

- 应用仓库提交 `composer.lock`，库仓库通常不提交
- `require-dev` 不应进入生产镜像
- PHP platform 版本和 CI 版本一致
- 自动加载规则不要过宽，避免加载测试或脚本目录
- `scripts` 中的命令不应依赖开发者本机秘密配置

### 依赖安全与维护状态

```bash
composer audit
composer outdated --direct
composer validate --strict
```

新增包时看维护状态、下载量不是唯一指标。重点是安全历史、发布时间、最小依赖范围、是否替代标准库或框架内置能力。

---

## 性能与资源管理

### 大数据处理用生成器或分页

```php
<?php

// ❌ 一次性读入所有记录
$rows = $repo->all();
foreach ($rows as $row) {
    exportRow($row);
}

// ✅ 分页或 generator，避免内存峰值
foreach ($repo->cursor() as $row) {
    exportRow($row);
}
```

PHP 请求生命周期短，但 CLI job、队列 worker、导出任务会长期运行。审查这类代码时特别关注内存增长、未关闭资源和全局状态污染。

### 避免循环中的昂贵操作

```php
<?php

// ❌ 每次循环重新解析配置或建立连接
foreach ($items as $item) {
    $client = new ApiClient($_ENV['API_KEY']);
    $client->send($item);
}

// ✅ 可复用依赖在循环外创建
$client = new ApiClient($_ENV['API_KEY']);
foreach ($items as $item) {
    $client->send($item);
}
```

关注循环里的数据库查询、HTTP 请求、正则编译、大数组复制、`array_merge()` 累积追加、反复读取环境变量或配置文件。

### 资源要释放或限定作用域

```php
<?php

// ✅ 文件句柄使用后关闭
$handle = fopen($path, 'rb');
if ($handle === false) {
    throw new RuntimeException('Unable to open file');
}

try {
    while (($line = fgets($handle)) !== false) {
        process($line);
    }
} finally {
    fclose($handle);
}
```

PDO 连接通常由容器管理，但文件句柄、curl handle、临时文件、锁、队列 worker 中的缓存对象仍需要明确生命周期。

---

## 测试与静态分析

### 测行为，不测实现细节

```php
<?php

// ❌ 断言内部方法调用，重构成本高
$mailer->expects($this->once())->method('buildTemplate');

// ✅ 断言可观察结果
$service->sendWelcomeEmail($user);

$this->assertTrue($mailbox->hasMessageFor($user->email));
```

对业务服务、控制器、队列 job，优先覆盖输入输出、数据库状态、发布事件、发送消息等可观察行为。

### 静态分析和格式化

```bash
vendor/bin/phpunit
vendor/bin/phpstan analyse
vendor/bin/psalm
vendor/bin/php-cs-fixer fix --dry-run --diff
vendor/bin/rector process --dry-run
```

审查 PR 时看新增代码是否降低 PHPStan/Psalm level，是否大量使用 baseline ignore，是否用 `@phpstan-ignore-next-line` 掩盖真实类型问题。

### 测试数据隔离

```php
<?php

// ❌ 测试依赖真实时间和外部服务
$service->expireOldSessions();

// ✅ 注入 clock 和 fake gateway
$clock->setNow(new DateTimeImmutable('2026-01-01T00:00:00Z'));
$service->expireOldSessions();
```

关注数据库事务回滚、fixture 清理、随机数、时间、队列、缓存和外部 API。PHP 测试慢通常不是语言问题，而是边界没有隔离。

---

## Review Checklist

### 类型与建模

- [ ] 文件顶部使用 `declare(strict_types=1);`
- [ ] 参数、返回值、属性有明确类型
- [ ] 使用 `===` / `!==`，集合查找启用 strict 模式
- [ ] 稳定状态集合使用 enum，而不是字符串魔法值
- [ ] 新代码不依赖动态属性
- [ ] 值对象使用 readonly 或不可变设计

### 安全

- [ ] 输入在边界层验证并转换类型
- [ ] 输出按 HTML/URL/JS/CSS 上下文转义
- [ ] SQL 使用 prepared statements 或 ORM binding
- [ ] 动态表名、列名、排序字段使用白名单
- [ ] 密码使用 `password_hash()` / `password_verify()`
- [ ] token、验证码、文件名使用 `random_bytes()` / `random_int()`
- [ ] 不可信输入不进入 `unserialize()`
- [ ] 文件上传检查错误码、大小、MIME、扩展名和存储目录
- [ ] shell 命令、路径拼接、日志输出没有注入或泄密风险

### 数据与事务

- [ ] 多步写入有事务或补偿机制
- [ ] 外部副作用有幂等设计
- [ ] 避免 N+1 查询
- [ ] 分页、索引和 select 列合理
- [ ] 数据库错误不会被吞掉

### 可维护性

- [ ] 构造函数不做重 I/O
- [ ] 依赖注入清晰，没有隐藏全局状态
- [ ] 没有 `@` 错误抑制
- [ ] 异常保留上下文和 previous
- [ ] Composer 依赖范围、autoload、scripts 合理
- [ ] 应用仓库提交 `composer.lock`

### 测试与工具

- [ ] PHPUnit/Pest 覆盖关键路径和失败路径
- [ ] PHPStan/Psalm 配置没有降低严格度
- [ ] 新增 ignore/baseline 有解释
- [ ] 格式化工具和 CI 命令可复现
- [ ] 测试隔离时间、随机数、数据库、队列、外部 API

---

## 参考资料

- [PHP Manual: Type declarations](https://www.php.net/manual/en/language.types.declarations.php)
- [PHP Manual: match](https://www.php.net/match)
- [PHP Manual: Enumerations](https://www.php.net/manual/en/language.enumerations.overview.php)
- [PHP Manual: Properties](https://www.php.net/manual/en/language.oop5.properties.php)
- [PHP Manual: PDO](https://www.php.net/manual/en/class.pdo.php)
- [PHP Manual: password_hash](https://www.php.net/manual/en/function.password-hash.php)
- [PHP Manual: random_bytes](https://www.php.net/manual/en/function.random-bytes.php)
- [Composer documentation](https://getcomposer.org/doc/)
- [PHPUnit documentation](https://docs.phpunit.de/)
- [PHPStan documentation](https://phpstan.org/user-guide/getting-started)
- [Psalm documentation](https://psalm.dev/docs/)
