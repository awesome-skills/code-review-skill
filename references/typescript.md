# TypeScript/JavaScript Code Review Guide

> TypeScript/JavaScript 通用代码审查指南，覆盖类型安全、异步处理、常见陷阱。

---

## 类型安全

### 避免使用 any

```typescript
// ❌ Using any defeats type safety
function processData(data: any) {  // Avoid any
    return data.value;
}

// ✅ Use proper types
interface DataPayload {
    value: string;
}
function processData(data: DataPayload) {
    return data.value;
}
```

---

## 异步处理

### 错误处理

```typescript
// ❌ Not handling async errors
async function fetchUser(id: string) {
    const response = await fetch(`/api/users/${id}`);
    return response.json();  // What if network fails?
}

// ✅ Handle errors properly
async function fetchUser(id: string): Promise<User> {
    try {
        const response = await fetch(`/api/users/${id}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Failed to fetch user:', error);
        throw error;
    }
}
```

---

## 不可变性

### 避免直接修改 Props/参数

```typescript
// ❌ Mutation of props
function UserProfile({ user }: Props) {
    user.lastViewed = new Date();  // Mutating prop!
    return <div>{user.name}</div>;
}

// ✅ Don't mutate props
function UserProfile({ user, onView }: Props) {
    useEffect(() => {
        onView(user.id);  // Notify parent to update
    }, [user.id]);
    return <div>{user.name}</div>;
}
```

---

## TypeScript Review Checklist

### 类型系统
- [ ] 没有使用 `any`（使用 `unknown` 代替未知类型）
- [ ] 接口和类型定义完整
- [ ] 使用泛型提高代码复用性
- [ ] 联合类型有正确的类型收窄

### 异步代码
- [ ] async 函数有错误处理
- [ ] Promise rejection 被正确处理
- [ ] 避免 callback hell，使用 async/await
- [ ] 并发请求使用 `Promise.all` 或 `Promise.allSettled`

### 不可变性
- [ ] 不直接修改函数参数
- [ ] 使用 spread 操作符创建新对象/数组
- [ ] 考虑使用 `readonly` 修饰符

### 代码质量
- [ ] 启用 strict 模式
- [ ] ESLint/TSLint 无警告
- [ ] 函数有返回类型注解
- [ ] 避免类型断言（`as`），除非确实必要
