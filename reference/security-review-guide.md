# Security Review Guide

Security-focused code review checklist based on OWASP Top 10 and best practices.

## Authentication & Authorization

### Authentication
- [ ] Passwords hashed with strong algorithm (bcrypt, argon2)
- [ ] Password complexity requirements enforced
- [ ] Account lockout after failed attempts
- [ ] Secure password reset flow
- [ ] Multi-factor authentication for sensitive operations
- [ ] Session tokens are cryptographically random
- [ ] Session timeout implemented

### Authorization
- [ ] Authorization checks on every request
- [ ] Principle of least privilege applied
- [ ] Role-based access control (RBAC) properly implemented
- [ ] No privilege escalation paths
- [ ] Direct object reference checks (IDOR prevention)
- [ ] API endpoints protected appropriately

### JWT Security
```typescript
// ❌ Insecure JWT configuration
jwt.sign(payload, 'weak-secret');

// ✅ Secure JWT configuration
jwt.sign(payload, process.env.JWT_SECRET, {
  algorithm: 'RS256',
  expiresIn: '15m',
  issuer: 'your-app',
  audience: 'your-api'
});

// ❌ Not verifying JWT properly
const decoded = jwt.decode(token);  // No signature verification!

// ✅ Verify signature and claims
const decoded = jwt.verify(token, publicKey, {
  algorithms: ['RS256'],
  issuer: 'your-app',
  audience: 'your-api'
});
```

## Input Validation

### SQL Injection Prevention

**The #1 rule**: Always use parameterized queries. Never concatenate user input into SQL strings.

Every major language and framework has a parameterized query mechanism:
- Python: `cursor.execute("SELECT ...", params)` / ORM filter methods
- Java: `PreparedStatement` / JPA `@Query` with `@Param`
- Go: `db.Query("SELECT ...", args...)`
- Node.js: `client.query("SELECT ...", [args])` / Prisma ORM
- PHP: PDO prepared statements / Laravel Eloquent
- C#: ADO.NET `SqlParameter` / Dapper / EF Core LINQ

> **See [SQL Injection Prevention Guide](cross-cutting/sql-injection-prevention.md) for complete cross-language examples, ORM unsafe patterns, dynamic identifier handling, and detection tools.**

### XSS Prevention

**The #1 rule**: Rely on framework auto-escaping. Audit every escape hatch.

Every major framework auto-escapes by default:
- React: JSX auto-escapes. Audit `dangerouslySetInnerHTML`.
- Vue: `{{ }}` auto-escapes. Audit `v-html`.
- Angular: Interpolation auto-escapes. Audit `bypassSecurityTrustHtml`.
- Svelte: `{ }` auto-escapes. Audit `{@html}`.
- Django: Templates auto-escape. Audit `mark_safe`.

For defense-in-depth, configure Content Security Policy (CSP) with nonce-based `script-src`.

> **See [XSS Prevention Guide](cross-cutting/xss-prevention.md) for complete cross-framework examples, CSP configuration, input validation vs output encoding, and detection tools.**

### CSRF Prevention

**CSRF Token Implementation**
```typescript
// ✅ Server: generate and validate CSRF token
import crypto from 'node:crypto';

function generateCsrfToken(): string {
  return crypto.randomBytes(32).toString('hex');
}

// Middleware: validate token on state-changing requests
app.post('/api/data', (req, res) => {
  const token = req.headers['x-csrf-token'];
  const sessionToken = req.session.csrfToken;
  if (!token || token !== sessionToken) {
    return res.status(403).json({ error: 'Invalid CSRF token' });
  }
  // ...handle request
});
```

**Python (Django)**
```python
# ✅ Django: built-in CSRF protection
# settings.py
MIDDLEWARE = [
    'django.middleware.csrf.CsrfViewMiddleware',  # 默认启用
]

# templates: include CSRF token
# <form method="post">
#   {% csrf_token %}
# </form>

# ❌ Disabling CSRF on a view
@csrf_exempt  # 除非绝对必要，否则不使用
def my_view(request):
    ...
```

**Java (Spring Boot)**
```java
// ✅ Spring Security: CSRF enabled by default
@Configuration
@EnableWebSecurity
public class SecurityConfig {
    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) {
        http.csrf(csrf -> csrf
            .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
        );
        return http.build();
    }
}
```

**SameSite Cookie**
```typescript
// ✅ Set SameSite cookie as additional defense
res.cookie('session', sessionId, {
  httpOnly: true,
  secure: true,
  sameSite: 'strict',  // 或 'lax' 用于允许导航 GET 请求
  maxAge: 3600000,
});
```

### SSRF Prevention

```python
# ❌ Vulnerable: user-controlled URL
import requests
url = request.GET.get('url')
response = requests.get(url)

# ✅ Validate URL against whitelist
ALLOWED_HOSTS = ['api.example.com', 'cdn.example.com']

def is_safe_url(url: str) -> bool:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return parsed.hostname in ALLOWED_HOSTS

if is_safe_url(url):
    response = requests.get(url)
```

```typescript
// ❌ Vulnerable: fetching arbitrary URLs
const url = req.query.url;
const response = await fetch(url);

// ✅ Validate URL before fetching
const ALLOWED_DOMAINS = ['api.internal.com'];

function isSafeUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    // Block internal IPs
    if (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1') {
      return false;
    }
    if (parsed.hostname.match(/^10\.|^172\.(1[6-9]|2\d|3[01])\.|^192\.168\./)) {
      return false; // Block private IP ranges
    }
    return ALLOWED_DOMAINS.includes(parsed.hostname);
  } catch {
    return false;
  }
}
```

```go
// ✅ Go: validate URL before making requests
import "net/url"

func isSafeURL(rawURL string) bool {
    u, err := url.Parse(rawURL)
    if err != nil {
        return false
    }
    // Block internal IPs
    if u.Hostname() == "localhost" || u.Hostname() == "127.0.0.1" {
        return false
    }
    // Only allow HTTPS
    if u.Scheme != "https" {
        return false
    }
    return true
}
```

### IDOR（不安全直接对象引用）

```python
# ❌ Vulnerable: no ownership check
def get_order(request, order_id):
    order = Order.objects.get(id=order_id)  # 任何用户可查看任何订单
    return JsonResponse(order.to_dict())

# ✅ Check ownership before returning
def get_order(request, order_id):
    order = Order.objects.filter(id=order_id, user=request.user).first()
    if not order:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse(order.to_dict())
```

```typescript
// ❌ Vulnerable: no authorization check
app.get('/api/orders/:id', async (req, res) => {
  const order = await db.order.findUnique({
    where: { id: Number(req.params.id) }
  });
  res.json(order);
});

// ✅ Include user context in query
app.get('/api/orders/:id', async (req, res) => {
  const order = await db.order.findFirst({
    where: {
      id: Number(req.params.id),
      userId: req.user.id,  // Scope to current user
    }
  });
  if (!order) return res.status(404).json({ error: 'Not found' });
  res.json(order);
});
```

```java
// ✅ Spring Security: method-level authorization
@GetMapping("/api/orders/{id}")
@PreAuthorize("@orderService.isOwner(#id, authentication.principal.id)")
public Order getOrder(@PathVariable Long id) {
    return orderService.findById(id);
}
```

**UUID vs 自增 ID**
```typescript
// ❌ 自增 ID 可被枚举
// GET /api/users/1, /api/users/2, /api/users/3 ...

// ✅ UUID 不可预测
// GET /api/users/550e8400-e29b-41d4-a716-446655440000

// ⚠️ UUID 只是防止枚举，不是权限控制
// 仍然需要验证当前用户是否有权访问该资源
```

### Command Injection Prevention

**Python**
```python
# ❌ Vulnerable: shell=True
import subprocess
subprocess.run(f"convert {filename} output.png", shell=True)

# ✅ Use list arguments without shell
subprocess.run(['convert', filename, 'output.png'], check=True)

# ✅ Validate and sanitize input
import shlex
safe_filename = shlex.quote(filename)
```

**Node.js**
```typescript
// ❌ Vulnerable: exec with string interpolation
import { exec } from 'node:child_process';
exec(`convert ${filename} output.png`);

// ✅ Use execFile with array arguments
import { execFile } from 'node:child_process';
execFile('convert', [filename, 'output.png'], (error, stdout) => {
  if (error) throw error;
});

// ❌ Never pass user input to shell
exec(`echo ${userInput}`);  // userInput = "; rm -rf /"

// ✅ Sanitize or use non-shell alternatives
import { writeFile } from 'node:fs/promises';
await writeFile('output.txt', userInput);  // No shell involved
```

**Go**
```go
// ❌ Vulnerable: shell command with user input
cmd := exec.Command("sh", "-c", "echo " + userInput)

// ✅ Use exec.Command with separate arguments
cmd := exec.Command("echo", userInput)

// ❌ Passing user input to shell
out, _ := exec.Command("bash", "-c", "cat "+filename).Output()

// ✅ Read file directly without shell
data, err := os.ReadFile(filename)
```

**Java**
```java
// ❌ Vulnerable: Runtime.exec with string concatenation
Runtime.getRuntime().exec("convert " + filename + " output.png");

// ✅ Use ProcessBuilder with separate arguments
ProcessBuilder pb = new ProcessBuilder("convert", filename, "output.png");
Process process = pb.start();

// ❌ Dangerous: passing user input to shell
Runtime.getRuntime().exec(new String[]{"sh", "-c", "echo " + userInput});
```

## Data Protection

### Sensitive Data Handling
- [ ] No secrets in source code
- [ ] Secrets stored in environment variables or secret manager
- [ ] Sensitive data encrypted at rest
- [ ] Sensitive data encrypted in transit (HTTPS)
- [ ] PII handled according to regulations (GDPR, etc.)
- [ ] Sensitive data not logged
- [ ] Secure data deletion when required

### Configuration Security
```yaml
# ❌ Secrets in config files
database:
  password: "super-secret-password"

# ✅ Reference environment variables
database:
  password: ${DATABASE_PASSWORD}
```

### Error Messages
```typescript
// ❌ Leaking sensitive information
catch (error) {
  return res.status(500).json({
    error: error.stack,  // Exposes internal details
    query: sqlQuery      // Exposes database structure
  });
}

// ✅ Generic error messages
catch (error) {
  logger.error('Database error', { error, userId });  // Log internally
  return res.status(500).json({
    error: 'An unexpected error occurred'
  });
}
```

## API Security

### Rate Limiting
- [ ] Rate limiting on all public endpoints
- [ ] Stricter limits on authentication endpoints
- [ ] Per-user and per-IP limits
- [ ] Graceful handling when limits exceeded

### CORS Configuration
```typescript
// ❌ Overly permissive CORS
app.use(cors({ origin: '*' }));

// ✅ Restrictive CORS
app.use(cors({
  origin: ['https://your-app.com'],
  methods: ['GET', 'POST'],
  credentials: true
}));
```

### HTTP Headers
```typescript
// Security headers to set
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
    }
  },
  hsts: { maxAge: 31536000, includeSubDomains: true },
  noSniff: true,
  xssFilter: true,
  frameguard: { action: 'deny' }
}));
```

## Cryptography

### Secure Practices
- [ ] Using well-established algorithms (AES-256, RSA-2048+)
- [ ] Not implementing custom cryptography
- [ ] Using cryptographically secure random number generation
- [ ] Proper key management and rotation
- [ ] Secure key storage (HSM, KMS)

### Common Mistakes
```typescript
// ❌ Weak random generation
const token = Math.random().toString(36);

// ✅ Cryptographically secure random
const crypto = require('crypto');
const token = crypto.randomBytes(32).toString('hex');

// ❌ MD5/SHA1 for passwords
const hash = crypto.createHash('md5').update(password).digest('hex');

// ✅ Use bcrypt or argon2
const bcrypt = require('bcrypt');
const hash = await bcrypt.hash(password, 12);
```

## Dependency Security

### Checklist
- [ ] Dependencies from trusted sources only
- [ ] No known vulnerabilities (npm audit, cargo audit)
- [ ] Dependencies kept up to date
- [ ] Lock files committed (package-lock.json, Cargo.lock)
- [ ] Minimal dependency usage
- [ ] License compliance verified

### Audit Commands
```bash
# Node.js
npm audit
npm audit fix

# Python
pip-audit
safety check

# Rust
cargo audit

# General
snyk test
```

## Logging & Monitoring

### Secure Logging
- [ ] No sensitive data in logs (passwords, tokens, PII)
- [ ] Logs protected from tampering
- [ ] Appropriate log retention
- [ ] Security events logged (login attempts, permission changes)
- [ ] Log injection prevented

```typescript
// ❌ Logging sensitive data
logger.info(`User login: ${email}, password: ${password}`);

// ✅ Safe logging
logger.info('User login attempt', { email, success: true });
```

## Security Review Severity Levels

| Severity | Description | Action |
|----------|-------------|--------|
| **Critical** | Immediate exploitation possible, data breach risk | Block merge, fix immediately |
| **High** | Significant vulnerability, requires specific conditions | Block merge, fix before release |
| **Medium** | Moderate risk, defense in depth concern | Should fix, can merge with tracking |
| **Low** | Minor issue, best practice violation | Nice to fix, non-blocking |
| **Info** | Suggestion for improvement | Optional enhancement |
