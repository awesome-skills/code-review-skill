# Universal Code Quality Anti-Patterns

> 语言无关的代码质量反模式指南，覆盖代码复用、抽象泄漏、参数膨胀、嵌套条件、字符串类型化、TOCTOU、空操作更新等核心主题。适用于所有语言的 PR 审查。

## 目录

- [代码复用审查](#代码复用审查)
- [参数膨胀](#参数膨胀)
- [抽象泄漏](#抽象泄漏)
- [字符串类型化](#字符串类型化)
- [嵌套条件表达式](#嵌套条件表达式)
- [复制粘贴变种](#复制粘贴变种)
- [空操作更新](#空操作更新)
- [TOCTOU 竞争条件](#toctou-竞争条件)
- [过度宽泛操作](#过度宽泛操作)
- [冗余状态](#冗余状态)
- [通用质量审查清单](#通用质量审查清单)

---

## 代码复用审查

Before accepting new code, search the existing codebase for reusable utilities.

### 搜索现有工具函数

```python
# ❌ 新写的路径拼接逻辑——项目中已有 PathBuilder
def get_config_path(name):
    base = os.environ.get("APP_ROOT", ".")
    return os.path.join(base, "config", name + ".json")

# ✅ 使用已有的 PathBuilder
def get_config_path(name):
    return PathBuilder.config(f"{name}.json")
```

```javascript
// ❌ 手写 debounce——项目已有 lodash 或 utils/debounce.ts
function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// ✅ 使用已有的工具函数
import { debounce } from "@/utils/debounce";
```

**审查要点：**
- 新增函数是否与已有 utility 重名或功能重叠？
- inline 逻辑是否可以提取为已有模块的调用？
- 检查相邻文件和 shared/utils 目录

---

## 参数膨胀

### 函数参数不断增长

```python
# ❌ 每次新需求加一个参数
def create_user(name, email, role, team, active, avatar_url, timezone):
    ...

# ✅ 使用配置对象 / dataclass
@dataclass
class CreateUserParams:
    name: str
    email: str
    role: Role = Role.MEMBER
    team: str | None = None
    active: bool = True
    avatar_url: str | None = None
    timezone: str = "UTC"

def create_user(params: CreateUserParams) -> User:
    ...
```

```typescript
// ❌ 6+ 个 positional 参数
function renderWidget(
  title: string, width: number, height: number,
  theme: string, collapsible: boolean, icon: string
) { ... }

// ✅ Options object pattern
interface WidgetOptions {
  title: string;
  width?: number;
  height?: number;
  theme?: "light" | "dark";
  collapsible?: boolean;
  icon?: string;
}
function renderWidget(options: WidgetOptions) { ... }
```

**审查要点：**
- 函数参数是否 ≥ 4 个？考虑 options object / dataclass
- 新参数是否只是布尔标志？考虑 enum 或 strategy pattern
- 是否有 `enable_x`, `disable_y` 这类互斥参数？

---

## 抽象泄漏

### 暴露内部实现细节

```python
# ❌ 返回内部 ORM 对象——调用者被迫了解 SQLAlchemy
def get_users():
    return session.query(User).filter(User.active == True).all()

# ✅ 返回 domain 对象，隐藏持久化层
def get_active_users() -> list[UserDTO]:
    rows = user_repo.find_active()
    return [UserDTO.from_row(r) for r in rows]
```

```typescript
// ❌ 组件接收 API response 原始结构
<UserCard user={apiResponse.data.results[0]} />

// ✅ 组件接收 domain 类型，adapter 处理映射
interface UserSummary {
  displayName: string;
  avatarUrl: string;
}
<UserCard user={adaptUser(apiResponse)} />
```

**审查要点：**
- 函数返回类型是否泄露底层实现（ORM, HTTP client, file format）？
- 组件/函数是否依赖外部系统的数据结构？
- 是否破坏了已有的抽象边界？

---

## 字符串类型化

### 用原始字符串代替常量/枚举

```python
# ❌ Magic strings 散落各处
if status == "active":
    ...
if role == "admin":
    ...

# ✅ 使用 enum
class Status(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"

if user.status == Status.ACTIVE:
    ...
```

```typescript
// ❌ Raw string event names——拼写错误不会报错
emitter.emit("userCreated", data);
emitter.on("usercreated", handler); // bug: typo

// ✅ 常量或 branded type
const Events = {
  USER_CREATED: "userCreated",
  USER_SUSPENDED: "userSuspended",
} as const;
emitter.emit(Events.USER_CREATED, data);
```

**审查要点：**
- 是否用字符串代替了已有的 enum/union type？
- 事件名、action type、status 值是否散落在多个文件？
- 字符串比较是否 case-sensitive 但未验证？

---

## 嵌套条件表达式

### 三元链和嵌套 if/else

```python
# ❌ 三元链难以阅读
label = (
    "Admin" if role == "admin" else
    "Manager" if role == "manager" else
    "Viewer" if role == "viewer" else
    "Unknown"
)

# ✅ 查找表或 match
ROLE_LABELS = {
    "admin": "Admin",
    "manager": "Manager",
    "viewer": "Viewer",
}
label = ROLE_LABELS.get(role, "Unknown")
```

```typescript
// ❌ 嵌套三元
const bg = isHovered
  ? isSelected ? "blue" : "gray"
  : isSelected ? "navy" : "white";

// ✅ 查找表（lookup map）
const bgMap: Record<string, string> = {
  "true-true": "blue",
  "true-false": "gray",
  "false-true": "navy",
  "false-false": "white",
};
const bg = bgMap[`${isHovered}-${isSelected}`];
```

```python
# ❌ 嵌套 if 3+ 层
def process(order):
    if order is not None:
        if order.items:
            for item in order.items:
                if item.price > 0:
                    ...

# ✅ Early return + guard clauses
def process(order):
    if not order or not order.items:
        return
    for item in order.items:
        if item.price <= 0:
            continue
        ...
```

**审查要点：**
- 三元表达式是否嵌套 ≥ 2 层？
- if/else 嵌套是否 ≥ 3 层？
- 能否用 lookup table、early return 或 match 替换？

---

## 复制粘贴变种

### 近乎重复的代码块

```python
# ❌ 两个函数几乎一样，只有字段名不同
def format_user(user):
    return f"{user.first_name} {user.last_name} ({user.email})"

def format_employee(emp):
    return f"{emp.first_name} {emp.last_name} ({emp.work_email})"

# ✅ 统一抽象
def format_person(first: str, last: str, email: str) -> str:
    return f"{first} {last} ({email})"
```

```typescript
// ❌ Copy-paste handler 只改了 URL
async function deletePost(id: string) {
  await fetch(`/api/posts/${id}`, { method: "DELETE" });
  router.push("/posts");
}
async function deleteComment(id: string) {
  await fetch(`/api/comments/${id}`, { method: "DELETE" });
  router.push("/comments");
}

// ✅ 参数化
async function deleteResource(resource: string, id: string) {
  await fetch(`/api/${resource}/${id}`, { method: "DELETE" });
  router.push(`/${resource}`);
}
```

**审查要点：**
- 是否有 ≥ 2 段代码仅变量名/URL/字符串不同？
- 能否提取参数化的共享函数？
- 是否可以用 template method 或 strategy 消除变种？

---

## 空操作更新

### 无条件触发状态更新

```typescript
// ❌ 每次 poll 都触发 update——即使数据未变
useEffect(() => {
  const interval = setInterval(() => {
    fetch("/api/status").then(r => r.json()).then(setStatus);
  }, 5000);
  return () => clearInterval(interval);
}, []);

// ✅ 仅在值变化时更新
useEffect(() => {
  const interval = setInterval(() => {
    fetch("/api/status")
      .then(r => r.json())
      .then(data => {
        setStatus(prev => isEqual(prev, data) ? prev : data);
      });
  }, 5000);
  return () => clearInterval(interval);
}, []);
```

```python
# ❌ 每次 loop 都写 DB——即使值未变
for item in items:
    item.status = compute_status(item)
    session.commit()

# ✅ 仅在变化时写入
for item in items:
    new_status = compute_status(item)
    if item.status != new_status:
        item.status = new_status
        session.commit()
```

**审查要点：**
- polling / interval / event handler 是否无条件更新？
- wrapper function 是否尊重 same-reference return？
- DB 写入是否检查了实际变化？

---

## TOCTOU 竞争条件

### Time-of-Check-to-Time-of-Use

```python
# ❌ 先检查后操作——中间文件可能被删除/创建
if os.path.exists(path):
    with open(path) as f:
        data = f.read()

# ✅ 直接操作 + 处理异常
try:
    with open(path) as f:
        data = f.read()
except FileNotFoundError:
    data = None
```

```python
# ❌ 检查余额 → 扣款 两步操作不是原子的
if account.balance >= amount:
    account.balance -= amount

# ✅ 原子操作或锁
with account.lock:
    if account.balance < amount:
        raise InsufficientFundsError()
    account.balance -= amount
```

```typescript
// ❌ Check-then-act 在 async 环境中不安全
if (!fileExists(path)) {
  await writeFile(path, content);
}

// ✅ 直接操作 + catch
try {
  await writeFile(path, content, { flag: "wx" });
} catch (e) {
  if (e.code === "EEXIST") { /* handle */ }
  else throw e;
}
```

**审查要点：**
- `if exists → operate` 模式是否可替换为 `try operate → catch`？
- 多步状态变更是否在事务/锁内？
- async 操作中 check 和 act 之间是否有 await？

---

## 过度宽泛操作

### 读取过多数据

```python
# ❌ 读取整个文件再取第一行
content = Path("log.txt").read_text()
first_line = content.split("\n")[0]

# ✅ 只读第一行，不加载整个文件
with open("log.txt") as f:
    first_line = f.readline()
```

```typescript
// ❌ 加载所有 items 再过滤
const allItems = await db.query("SELECT * FROM orders");
const pending = allItems.filter(o => o.status === "pending");

// ✅ 数据库层过滤
const pending = await db.query(
  "SELECT * FROM orders WHERE status = ?", ["pending"]
);
```

```python
# ❌ 读取整个列表找一条记录
users = list(User.objects.all())
user = next(u for u in users if u.id == user_id)

# ✅ 精确查询
user = User.objects.get(id=user_id)
```

**审查要点：**
- 是否读取了整个集合/文件再只用一小部分？
- 能否将过滤推到数据库/存储层？
- API 调用是否支持 pagination/limit 参数？

---

## 冗余状态

### 状态可以被推导

```typescript
// ❌ 同时存储 fullName 和 firstName + lastName
interface User {
  firstName: string;
  lastName: string;
  fullName: string;  // redundant
}

// ✅ fullName 是推导值
interface User {
  firstName: string;
  lastName: string;
}
const fullName = `${user.firstName} ${user.lastName}`;
```

```python
# ❌ 缓存值在源数据变化时可能过时
class Order:
    total: float
    item_count: int       # redundant if len(items) gives the same
    items: list[Item]

# ✅ 推导或 property
class Order:
    items: list[Item]

    @property
    def total(self) -> float:
        return sum(item.price for item in self.items)

    @property
    def item_count(self) -> int:
        return len(self.items)
```

**审查要点：**
- 是否有字段可以从其他字段推导？
- 缓存值是否有 invalidation 机制？
- observer/effect 是否可以替换为直接调用？

---

## 通用质量审查清单

- [ ] **复用审查**: 搜索了现有 utility/helper，没有重复造轮子？
- [ ] **参数数量**: 函数参数 ≤ 3 个？超过则用 options object / dataclass？
- [ ] **抽象边界**: 返回类型没有暴露内部实现细节（ORM、HTTP client、file format）？
- [ ] **类型安全**: 没有 magic strings 代替已有的 enum/constant/union type？
- [ ] **条件深度**: 三元嵌套 ≤ 1 层？if/else 嵌套 ≤ 2 层？
- [ ] **DRY**: 没有 copy-paste-with-variation（≥ 2 段近似代码）？
- [ ] **空操作防护**: polling / interval / event handler 有 change-detection guard？
- [ ] **TOCTOU**: `if exists → operate` 替换为 `try operate → catch`？
- [ ] **数据精度**: 没有读取整个集合/文件只为了取子集？
- [ ] **冗余状态**: 没有可以从其他字段推导的存储字段？
