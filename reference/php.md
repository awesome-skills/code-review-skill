# PHP Code Review Guide

> PHP 8.x code review guide covering the type system, modern language features, OOP modeling, PDO data access, security, error handling, Composer dependencies, performance, and testing.

## Table of Contents

- [Quick Review Checklist](#quick-review-checklist)
- [Type System & Modern PHP](#type-system--modern-php)
- [Object Modeling](#object-modeling)
- [Input, Output & Security](#input-output--security)
- [Database Access](#database-access)
- [Error Handling](#error-handling)
- [Composer & Dependencies](#composer--dependencies)
- [Performance & Resource Management](#performance--resource-management)
- [Testing & Static Analysis](#testing--static-analysis)
- [Review Checklist](#review-checklist)
- [References](#references)

---

## Quick Review Checklist

### Must-check

- [ ] New files enable `declare(strict_types=1);`
- [ ] Public APIs have parameter, return, and property types
- [ ] User input is validated; output is escaped per context
- [ ] SQL uses parameterized queries or ORM binding
- [ ] Passwords use `password_hash()` / `password_verify()`
- [ ] File uploads validate MIME, size, extension, and storage path
- [ ] `composer.lock` is committed; dependency ranges are reasonable
- [ ] PHPUnit/Pest tests and PHPStan/Psalm static analysis are present

### Common issues

- [ ] Loose comparison `==` / `!=` causing type-juggling vulnerabilities
- [ ] `md5()` / `sha1()` used to store passwords
- [ ] Concatenating SQL, HTML, shell commands, or file paths
- [ ] Using `@` to suppress errors
- [ ] `unserialize()` on untrusted data
- [ ] `$_GET` / `$_POST` / `$_FILES` flowing straight into business logic
- [ ] PHP 8.2+ dynamic properties trigger a deprecation; PHP 9 may turn it into an error

---

## Type System & Modern PHP

### strict_types and explicit types

```php
<?php

// ❌ weak boundary: passing "42" gets silently coerced
function findUser($id) {
    return User::find($id);
}

// ✅ enable strict_types at the top of the file; type the public API
declare(strict_types=1);

function findUser(int $id): ?User
{
    return User::find($id);
}
```

Don't leave type checking entirely to runtime input validation. Type declarations express an internal contract; input validation expresses how much to trust the boundary. You need both.

### Avoid loose comparisons

```php
<?php

// ❌ strings like "0e12345" can be treated as 0 under loose comparison
if ($providedHash == $storedHash) {
    grantAccess();
}

// ✅ strict comparison; use hash_equals() for secrets or tokens
if (hash_equals($storedHash, $providedHash)) {
    grantAccess();
}

// ✅ match uses identity checks, so fewer type-juggling surprises than switch
$status = match ($code) {
    200 => 'ok',
    404 => 'not_found',
    default => 'unknown',
};
```

Pay attention to `==`, `!=`, and `in_array($x, $list)` (loose by default) in auth, payment, state machine, and permission logic. Use `===`, `!==`, and `in_array($x, $list, true)` where it matters.

### Union / intersection / nullable types

```php
<?php

// ❌ mixed or untyped makes callers guess the return shape
function loadConfig($source) {
    return parseConfig($source);
}

// ✅ express the real contract with types
function loadConfig(string|PathInfo $source): Config
{
    return parseConfig($source);
}

// ✅ make null explicit when it's a real business state
function currentUser(): ?User
{
    return Auth::user();
}
```

`mixed` can show up at the boundary or while migrating legacy code, but in core business services it usually signals missing modeling.

### The nullsafe operator shouldn't hide missing state

```php
<?php

// ❌ chained nullsafe blurs the reason for failure
$country = $order?->customer?->profile?->country;

// ✅ branch explicitly on critical business state
if ($order === null) {
    throw new OrderNotFound();
}

$customer = $order->customer();
if ($customer === null) {
    throw new MissingCustomer($order->id);
}

$country = $customer->profile()?->country;
```

Distinguish "optional display field" from "business invariant that must exist." The former is a good fit for `?->`; the latter should fail loudly.

---

## Object Modeling

### Use readonly properties and value objects

```php
<?php

// ❌ public mutable fields let callers change state at will
class Money
{
    public $amount;
    public $currency;
}

// ✅ express an immutable value object with types and readonly
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

For DTOs, config, and domain value objects, check first whether a `readonly class` or readonly properties can remove hidden side effects.

### Enums instead of string states

```php
<?php

// ❌ string states are easy to typo and can't enumerate the legal set
if ($order->status === 'paied') {
    ship($order);
}

// ✅ an enum surfaces illegal states earlier
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

When reviewing state machines, permissions, or type fields, look for "magic string values." If the value set is stable, suggest an enum; if it comes from an external system, convert it to an internal enum before it enters the business layer.

### Don't rely on dynamic properties

```php
<?php

// ❌ PHP 8.2+ triggers a deprecation when creating a dynamic property
$user = new User();
$user->emali = 'a@example.com'; // a typo also silently creates a property

// ✅ declare properties or use a dedicated data structure
final class User
{
    public function __construct(
        public string $email,
    ) {}
}
```

`#[AllowDynamicProperties]` should be an exception for legacy compatibility, not the default for new code. Watch for serialization, ORM hydration, and test doubles that secretly rely on dynamic properties.

### Don't do heavy I/O in constructors

```php
<?php

// ❌ quietly connecting to the DB on construction makes testing and error handling hard
final class ReportService
{
    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = new PDO($_ENV['DSN']);
    }
}

// ✅ inject dependencies from the outside
final class ReportService
{
    public function __construct(
        private PDO $pdo,
    ) {}
}
```

A constructor should establish the object's invariants — not send HTTP requests, open connections, read large files, or run complex queries.

---

## Input, Output & Security

### Validate input at the boundary

```php
<?php

// ❌ superglobals flow straight into business logic
$user = $service->create($_POST['email'], $_POST['age']);

// ✅ validate and coerce types at the boundary first
$email = filter_input(INPUT_POST, 'email', FILTER_VALIDATE_EMAIL);
$age = filter_input(INPUT_POST, 'age', FILTER_VALIDATE_INT, [
    'options' => ['min_range' => 0, 'max_range' => 130],
]);

if ($email === false || $email === null || $age === false || $age === null) {
    throw new InvalidInput();
}

$user = $service->create($email, $age);
```

`filter_input()` only handles a slice of basic validation. Complex rules, cross-field constraints, and business constraints still need a dedicated validator or request DTO.

### Escape output per context

```php
<?php

// ❌ user input goes straight into HTML
echo "<h1>Hello {$_GET['name']}</h1>";

// ✅ use htmlspecialchars in an HTML text context
$name = (string) ($_GET['name'] ?? '');
echo '<h1>Hello ' . htmlspecialchars($name, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') . '</h1>';
```

Different contexts need different escaping: HTML text, HTML attributes, URLs, JavaScript strings, and CSS are all different. When a template engine's default escaping is turned off, treat it as a security risk.

### Passwords and randomness

```php
<?php

// ❌ md5/sha1 must not be used for password storage
$hash = md5($password);

// ✅ use PHP's built-in password API
$hash = password_hash($password, PASSWORD_DEFAULT);

if (!password_verify($password, $hash)) {
    throw new InvalidCredentials();
}

// ✅ use a CSPRNG for tokens
$token = bin2hex(random_bytes(32));
$code = random_int(100000, 999999);
```

Don't hand-roll salts, round migration, or password comparison. Use `password_needs_rehash()` when you need to upgrade the cost factor.

### Deserialization and object injection

```php
<?php

// ❌ untrusted input into unserialize can trigger object injection
$payload = unserialize($_COOKIE['state']);

// ✅ prefer JSON for external data, and validate its schema/shape
$payload = json_decode($_COOKIE['state'] ?? '{}', true, flags: JSON_THROW_ON_ERROR);
```

If you must process historical serialized data, at least restrict `allowed_classes` and make sure the relevant classes' magic methods can't produce dangerous side effects.

### File uploads and paths

```php
<?php

// ❌ building the path from the raw filename
$target = __DIR__ . '/uploads/' . $_FILES['avatar']['name'];
move_uploaded_file($_FILES['avatar']['tmp_name'], $target);

// ✅ generate a server-side filename, check the upload error and MIME
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

When reviewing upload features, check size limits, MIME detection, extensions, a non-executable storage directory, path traversal, overwrite protection, and any virus-scan or async-processing requirements.

---

## Database Access

### Use parameterized queries

PHP's PDO and mysqli both support prepared statements. Never concatenate user input into SQL strings. Dynamic identifiers (table/column names) must go through a whitelist mapping.

> **跨语言 SQL 注入防护详见 [SQL Injection Prevention Guide](cross-cutting/sql-injection-prevention.md)**，含 Python/Java/Go/Node.js/PHP/C# 示例及 ORM 不安全用法。

### Wrap multi-step writes in transactions

```php
<?php

// ❌ multi-step writes with no transaction leave half-finished state on failure
$orderId = $orders->create($cart);
$inventory->reserve($cart);
$payments->charge($orderId);

// ✅ explicit transaction boundary
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

Don't casually put external, non-rollbackable side effects (an actual charge, an email, a message dispatch) inside a database transaction. Common patterns are an outbox, an idempotency key, or triggering after the transaction commits.

### Avoid N+1 queries

> 📖 For cross-language N+1 patterns and solutions, see [N+1 Queries Guide](cross-cutting/n-plus-one-queries.md)

```php
<?php

// ❌ querying inside a loop
foreach ($orders as $order) {
    $customer = $customerRepo->find($order->customerId);
    render($order, $customer);
}

// ✅ batch-load, then map
$customerIds = array_unique(array_map(fn ($o) => $o->customerId, $orders));
$customers = $customerRepo->findByIds($customerIds);

foreach ($orders as $order) {
    render($order, $customers[$order->customerId] ?? null);
}
```

In ORMs like Laravel/Doctrine, check eager loading, join fetch, selected columns, pagination, and indexes.

---

## Error Handling

> 📖 For cross-language error handling principles, see [Error Handling Guide](cross-cutting/error-handling-principles.md)

### Catch specific exceptions, keep context

```php
<?php

// ❌ swallowing the exception leaves callers unable to know it failed
try {
    $mailer->send($message);
} catch (Exception $e) {
}

// ✅ catch a specific exception, keep context, and rethrow
try {
    $mailer->send($message);
} catch (TransportException $e) {
    throw new NotificationFailed($userId, previous: $e);
}
```

Empty `catch` blocks, `error_log()`-and-continue without surfacing the error, and turning every exception into `RuntimeException('failed')` in production code all deserve a question.

### Don't suppress errors with @

```php
<?php

// ❌ hides the real error and makes debugging hard
$content = @file_get_contents($path);

// ✅ handle failure explicitly
$content = file_get_contents($path);
if ($content === false) {
    throw new RuntimeException("Unable to read file: {$path}");
}
```

`@` is common around file, network, array access, and legacy library calls. Push for an explicit branch, or convert third-party errors into project exceptions.

### Don't leak sensitive data in logs

```php
<?php

// ❌ writing tokens, passwords, or the full request body to the log
$logger->error('Login failed', ['request' => $_POST]);

// ✅ log non-sensitive context that still helps locate the problem
$logger->warning('Login failed', [
    'email_hash' => hash('sha256', strtolower($email)),
    'ip' => $requestIp,
]);
```

Check logs, exception messages, the debug toolbar, error pages, and failed-queue records. Sensitive data includes passwords, tokens, sessions, PII, payment data, and full cookies.

---

## Composer & Dependencies

### Lock reproducible dependencies

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

When reviewing `composer.json` / `composer.lock`, watch for:

- Application repos commit `composer.lock`; library repos usually don't
- `require-dev` shouldn't make it into the production image
- The PHP platform version matches the CI version
- Autoload rules aren't too broad (don't load test or script directories)
- `scripts` commands don't depend on a developer's local secret config

### Dependency security and maintenance

```bash
composer audit
composer outdated --direct
composer validate --strict
```

When adding a package, look at its maintenance status — download count isn't the only signal. What matters is its security history, release cadence, minimal dependency footprint, and whether it duplicates the standard library or a framework built-in.

---

## Performance & Resource Management

### Stream large datasets with generators or pagination

```php
<?php

// ❌ loading every record at once
$rows = $repo->all();
foreach ($rows as $row) {
    exportRow($row);
}

// ✅ paginate or use a generator to avoid a memory spike
foreach ($repo->cursor() as $row) {
    exportRow($row);
}
```

A PHP request lifecycle is short, but CLI jobs, queue workers, and export tasks run for a long time. For that kind of code, watch memory growth, unclosed resources, and global-state pollution especially closely.

### Avoid expensive work inside loops

```php
<?php

// ❌ re-parsing config or opening a connection on every iteration
foreach ($items as $item) {
    $client = new ApiClient($_ENV['API_KEY']);
    $client->send($item);
}

// ✅ create reusable dependencies outside the loop
$client = new ApiClient($_ENV['API_KEY']);
foreach ($items as $item) {
    $client->send($item);
}
```

Watch for database queries, HTTP requests, regex compilation, large array copies, accumulating `array_merge()` appends, and repeatedly reading env vars or config files inside loops.

### Release or scope resources

```php
<?php

// ✅ close file handles after use
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

PDO connections are usually managed by the container, but file handles, curl handles, temp files, locks, and cached objects in queue workers still need an explicit lifecycle.

---

## Testing & Static Analysis

### Test behavior, not implementation details

```php
<?php

// ❌ asserting an internal method call makes refactoring expensive
$mailer->expects($this->once())->method('buildTemplate');

// ✅ assert observable results
$service->sendWelcomeEmail($user);

$this->assertTrue($mailbox->hasMessageFor($user->email));
```

For business services, controllers, and queue jobs, prefer covering observable behavior: inputs/outputs, database state, published events, and dispatched messages.

### Static analysis and formatting

```bash
vendor/bin/phpunit
vendor/bin/phpstan analyse
vendor/bin/psalm
vendor/bin/php-cs-fixer fix --dry-run --diff
vendor/bin/rector process --dry-run
```

When reviewing a PR, check whether the new code lowers the PHPStan/Psalm level, leans heavily on baseline ignores, or uses `@phpstan-ignore-next-line` to paper over a real type problem.

### Isolate test data

```php
<?php

// ❌ the test depends on real time and external services
$service->expireOldSessions();

// ✅ inject a clock and a fake gateway
$clock->setNow(new DateTimeImmutable('2026-01-01T00:00:00Z'));
$service->expireOldSessions();
```

Watch for database transaction rollback, fixture cleanup, randomness, time, queues, caches, and external APIs. Slow PHP tests are usually not a language problem — it's that the boundaries aren't isolated.

---

## Review Checklist

### Types & modeling

- [ ] `declare(strict_types=1);` at the top of the file
- [ ] Parameters, return values, and properties have explicit types
- [ ] `===` / `!==` used; collection lookups use strict mode
- [ ] Stable state sets use an enum, not magic strings
- [ ] New code doesn't rely on dynamic properties
- [ ] Value objects are readonly or otherwise immutable

### Security

- [ ] Input is validated and type-coerced at the boundary
- [ ] Output is escaped per HTML/URL/JS/CSS context
- [ ] SQL uses prepared statements or ORM binding
- [ ] Dynamic table/column/sort names go through a whitelist
- [ ] Passwords use `password_hash()` / `password_verify()`
- [ ] Tokens, codes, and filenames use `random_bytes()` / `random_int()`
- [ ] Untrusted input never reaches `unserialize()`
- [ ] File uploads check the error code, size, MIME, extension, and storage directory
- [ ] No injection or leakage risk in shell commands, path building, or log output

### Data & transactions

- [ ] Multi-step writes have a transaction or compensation mechanism
- [ ] External side effects are designed to be idempotent
- [ ] N+1 queries avoided
- [ ] Pagination, indexes, and selected columns are reasonable
- [ ] Database errors aren't swallowed

### Maintainability

- [ ] Constructors don't do heavy I/O
- [ ] Dependency injection is clear; no hidden global state
- [ ] No `@` error suppression
- [ ] Exceptions preserve context and `previous`
- [ ] Composer dependency ranges, autoload, and scripts are reasonable
- [ ] Application repos commit `composer.lock`

### Testing & tooling

- [ ] PHPUnit/Pest cover the critical and failure paths
- [ ] PHPStan/Psalm config doesn't lower strictness
- [ ] New ignores/baselines are explained
- [ ] Formatting tools and CI commands are reproducible
- [ ] Tests isolate time, randomness, the database, queues, and external APIs

---

## References

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
