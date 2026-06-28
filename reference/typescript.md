# TypeScript/JavaScript Code Review Guide

> TypeScript 代码审查指南，覆盖类型系统、泛型、条件类型、strict 模式、async/await 模式等核心主题。

## 目录

- [类型安全基础](#类型安全基础)
- [泛型模式](#泛型模式)
- [高级类型](#高级类型)
- [Strict 模式配置](#strict-模式配置)
- [异步处理](#异步处理)
- [不可变性](#不可变性)
- [ESLint 规则](#eslint-规则)
- [测试](#测试)
- [模块解析](#模块解析)
- [TS 4.9+ / 5.x 新特性](#ts-49--5x-新特性)
- [Review Checklist](#review-checklist)

---

## 类型安全基础

### 避免使用 any

```typescript
// ❌ Using any defeats type safety
function processData(data: any) {
  return data.value;  // 无类型检查，运行时可能崩溃
}

// ✅ Use proper types
interface DataPayload {
  value: string;
}
function processData(data: DataPayload) {
  return data.value;
}

// ✅ 未知类型用 unknown + 类型守卫
function processUnknown(data: unknown) {
  if (typeof data === 'object' && data !== null && 'value' in data) {
    return (data as { value: string }).value;
  }
  throw new Error('Invalid data');
}
```

### 类型收窄

```typescript
// ❌ 不安全的类型断言
function getLength(value: string | string[]) {
  return (value as string[]).length;  // 如果是 string 会出错
}

// ✅ 使用类型守卫
function getLength(value: string | string[]): number {
  if (Array.isArray(value)) {
    return value.length;
  }
  return value.length;
}

// ✅ 使用 in 操作符
interface Dog { bark(): void }
interface Cat { meow(): void }

function speak(animal: Dog | Cat) {
  if ('bark' in animal) {
    animal.bark();
  } else {
    animal.meow();
  }
}
```

### 字面量类型与 as const

```typescript
// ❌ 类型过于宽泛
const config = {
  endpoint: '/api',
  method: 'GET'  // 类型是 string
};

// ✅ 使用 as const 获得字面量类型
const config = {
  endpoint: '/api',
  method: 'GET'
} as const;  // method 类型是 'GET'

// ✅ 用于函数参数
function request(method: 'GET' | 'POST', url: string) { ... }
request(config.method, config.endpoint);  // 正确！
```

---

## 泛型模式

### 基础泛型

```typescript
// ❌ 重复代码
function getFirstString(arr: string[]): string | undefined {
  return arr[0];
}
function getFirstNumber(arr: number[]): number | undefined {
  return arr[0];
}

// ✅ 使用泛型
function getFirst<T>(arr: T[]): T | undefined {
  return arr[0];
}
```

### 泛型约束

```typescript
// ❌ 泛型没有约束，无法访问属性
function getProperty<T>(obj: T, key: string) {
  return obj[key];  // Error: 无法索引
}

// ✅ 使用 keyof 约束
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}

const user = { name: 'Alice', age: 30 };
getProperty(user, 'name');  // 返回类型是 string
getProperty(user, 'age');   // 返回类型是 number
getProperty(user, 'foo');   // Error: 'foo' 不在 keyof User
```

### 泛型默认值

```typescript
// ✅ 提供合理的默认类型
interface ApiResponse<T = unknown> {
  data: T;
  status: number;
  message: string;
}

// 可以不指定泛型参数
const response: ApiResponse = { data: null, status: 200, message: 'OK' };
// 也可以指定
const userResponse: ApiResponse<User> = { ... };
```

### 常见泛型工具类型

```typescript
// ✅ 善用内置工具类型
interface User {
  id: number;
  name: string;
  email: string;
}

type PartialUser = Partial<User>;         // 所有属性可选
type RequiredUser = Required<User>;       // 所有属性必需
type ReadonlyUser = Readonly<User>;       // 所有属性只读
type UserKeys = keyof User;               // 'id' | 'name' | 'email'
type NameOnly = Pick<User, 'name'>;       // { name: string }
type WithoutId = Omit<User, 'id'>;        // { name: string; email: string }
type UserRecord = Record<string, User>;   // { [key: string]: User }
```

---

## 高级类型

### 条件类型

```typescript
// ✅ 根据输入类型返回不同类型
type IsString<T> = T extends string ? true : false;

type A = IsString<string>;  // true
type B = IsString<number>;  // false

// ✅ 提取数组元素类型
type ElementType<T> = T extends (infer U)[] ? U : never;

type Elem = ElementType<string[]>;  // string

// ✅ 提取函数返回类型（内置 ReturnType）
type MyReturnType<T> = T extends (...args: any[]) => infer R ? R : never;
```

### 映射类型

```typescript
// ✅ 转换对象类型的所有属性
type Nullable<T> = {
  [K in keyof T]: T[K] | null;
};

interface User {
  name: string;
  age: number;
}

type NullableUser = Nullable<User>;
// { name: string | null; age: number | null }

// ✅ 添加前缀
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

type UserGetters = Getters<User>;
// { getName: () => string; getAge: () => number }
```

### 模板字面量类型

```typescript
// ✅ 类型安全的事件名称
type EventName = 'click' | 'focus' | 'blur';
type HandlerName = `on${Capitalize<EventName>}`;
// 'onClick' | 'onFocus' | 'onBlur'

// ✅ API 路由类型
type ApiRoute = `/api/${string}`;
const route: ApiRoute = '/api/users';  // OK
const badRoute: ApiRoute = '/users';   // Error
```

### Discriminated Unions

```typescript
// ✅ 使用判别属性实现类型安全
type Result<T, E> =
  | { success: true; data: T }
  | { success: false; error: E };

function handleResult(result: Result<User, Error>) {
  if (result.success) {
    console.log(result.data.name);  // TypeScript 知道 data 存在
  } else {
    console.log(result.error.message);  // TypeScript 知道 error 存在
  }
}

// ✅ Redux Action 模式
type Action =
  | { type: 'INCREMENT'; payload: number }
  | { type: 'DECREMENT'; payload: number }
  | { type: 'RESET' };

function reducer(state: number, action: Action): number {
  switch (action.type) {
    case 'INCREMENT':
      return state + action.payload;  // payload 类型已知
    case 'DECREMENT':
      return state - action.payload;
    case 'RESET':
      return 0;  // 这里没有 payload
  }
}
```

---

## Strict 模式配置

### 推荐的 tsconfig.json

```json
{
  "compilerOptions": {
    // ✅ 必须开启的 strict 选项
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "strictFunctionTypes": true,
    "strictBindCallApply": true,
    "strictPropertyInitialization": true,
    "noImplicitThis": true,
    "useUnknownInCatchVariables": true,

    // ✅ 额外推荐选项
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "exactOptionalPropertyTypes": true,
    "noPropertyAccessFromIndexSignature": true
  }
}
```

### noUncheckedIndexedAccess 的影响

```typescript
// tsconfig: "noUncheckedIndexedAccess": true

const arr = [1, 2, 3];
const first = arr[0];  // 类型是 number | undefined

// ❌ 直接使用可能出错
console.log(first.toFixed(2));  // Error: 可能是 undefined

// ✅ 先检查
if (first !== undefined) {
  console.log(first.toFixed(2));
}

// ✅ 或使用非空断言（确定时）
console.log(arr[0]!.toFixed(2));
```

---

## 异步处理

### Promise 错误处理

```typescript
// ❌ Not handling async errors
async function fetchUser(id: string) {
  const response = await fetch(`/api/users/${id}`);
  return response.json();  // 网络错误未处理
}

// ✅ Handle errors properly
async function fetchUser(id: string): Promise<User> {
  try {
    const response = await fetch(`/api/users/${id}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    if (error instanceof Error) {
      throw new Error(`Failed to fetch user: ${error.message}`);
    }
    throw error;
  }
}
```

### Promise.all vs Promise.allSettled

```typescript
// ❌ Promise.all 一个失败全部失败
async function fetchAllUsers(ids: string[]) {
  const users = await Promise.all(ids.map(fetchUser));
  return users;  // 一个失败就全部失败
}

// ✅ Promise.allSettled 获取所有结果
async function fetchAllUsers(ids: string[]) {
  const results = await Promise.allSettled(ids.map(fetchUser));

  const users: User[] = [];
  const errors: Error[] = [];

  for (const result of results) {
    if (result.status === 'fulfilled') {
      users.push(result.value);
    } else {
      errors.push(result.reason);
    }
  }

  return { users, errors };
}
```

### 竞态条件处理

```typescript
// ❌ 竞态条件：旧请求可能覆盖新请求
function useSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);

  useEffect(() => {
    fetch(`/api/search?q=${query}`)
      .then(r => r.json())
      .then(setResults);  // 旧请求可能后返回！
  }, [query]);
}

// ✅ 使用 AbortController
function useSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);

  useEffect(() => {
    const controller = new AbortController();

    fetch(`/api/search?q=${query}`, { signal: controller.signal })
      .then(r => r.json())
      .then(setResults)
      .catch(e => {
        if (e.name !== 'AbortError') throw e;
      });

    return () => controller.abort();
  }, [query]);
}
```

---

## 不可变性

### Readonly 与 ReadonlyArray

```typescript
// ❌ 可变参数可能被意外修改
function processUsers(users: User[]) {
  users.sort((a, b) => a.name.localeCompare(b.name));  // 修改了原数组！
  return users;
}

// ✅ 使用 readonly 防止修改
function processUsers(users: readonly User[]): User[] {
  return [...users].sort((a, b) => a.name.localeCompare(b.name));
}

// ✅ 深度只读
type DeepReadonly<T> = {
  readonly [K in keyof T]: T[K] extends object ? DeepReadonly<T[K]> : T[K];
};
```

### 不变式函数参数

```typescript
// ✅ 使用 as const 和 readonly 保护数据
function createConfig<T extends readonly string[]>(routes: T) {
  return routes;
}

const routes = createConfig(['home', 'about', 'contact'] as const);
// 类型是 readonly ['home', 'about', 'contact']
```

---

## ESLint 规则

### 推荐的 @typescript-eslint 规则

```javascript
// eslint.config.js（flat config，typescript-eslint v8）
import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  eslint.configs.recommended,
  // 需要类型信息的规则集，对应旧的 recommended-requiring-type-checking
  tseslint.configs.recommendedTypeChecked,
  tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        // 让带类型的规则自动找到对应 tsconfig
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // ✅ 类型安全
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unsafe-assignment': 'error',
      '@typescript-eslint/no-unsafe-member-access': 'error',
      '@typescript-eslint/no-unsafe-call': 'error',
      '@typescript-eslint/no-unsafe-return': 'error',

      // ✅ 最佳实践
      '@typescript-eslint/explicit-function-return-type': 'warn',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/await-thenable': 'error',
      '@typescript-eslint/no-misused-promises': 'error',

      // ✅ 代码风格
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/prefer-nullish-coalescing': 'error',
      '@typescript-eslint/prefer-optional-chain': 'error',
    },
  },
);
```

### 常见 ESLint 错误修复

```typescript
// ❌ no-floating-promises: Promise 必须被处理
async function save() { ... }
save();  // Error: 未处理的 Promise

// ✅ 显式处理
await save();
// 或
save().catch(console.error);
// 或明确忽略
void save();

// ❌ no-misused-promises: 不能在非 async 位置使用 Promise
const items = [1, 2, 3];
items.forEach(async (item) => {  // Error!
  await processItem(item);
});

// ✅ 使用 for...of
for (const item of items) {
  await processItem(item);
}
// 或 Promise.all
await Promise.all(items.map(processItem));
```

---

---

## 测试

### Vitest vs Jest 选择

```typescript
// ✅ 新项目推荐 Vitest（与 Vite 生态集成，原生 ESM 支持）
// vitest.config.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
    },
  },
});

// ✅ 已有 Jest 项目可保持，注意配置差异
// jest.config.ts
import type { Config } from 'jest';

const config: Config = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
};
export default config;
```

### 类型测试（tsd / expect-type）

```typescript
// ✅ 使用 expect-type 验证类型推断
import { expectTypeOf } from 'vitest';

function getFirst<T>(arr: T[]): T | undefined {
  return arr[0];
}

it('should infer correct return type', () => {
  const result = getFirst([1, 2, 3]);
  expectTypeOf(result).toEqualTypeOf<number | undefined>();
});

// ✅ 使用 expect-type 验证函数签名
const fn = (a: string, b: number) => a.repeat(b);
expectTypeOf(fn).parameters.toEqualTypeOf<[string, number]>();
expectTypeOf(fn).returns.toBeString();

// ❌ 类型错误会在编译时被捕获
const result = getFirst(['a', 'b']);
// @ts-expect-error: 类型不匹配
expectTypeOf(result).toEqualTypeOf<number>();
```

### Snapshot 测试最佳实践

```typescript
// ✅ Snapshot 适合：稳定的输出结构、配置对象、错误消息
it('should match serialized config', () => {
  const config = createAppConfig();
  expect(config).toMatchSnapshot();
});

// ❌ 避免：大对象、动态数据、随机值
it('should not snapshot large payloads', () => {
  const hugePayload = { users: generateRandomUsers(1000) };
  // 太长的 snapshot 难以审查，变更时不知道意图
});

// ✅ 使用 inline snapshot 处理小片段
it('should generate correct error message', () => {
  expect(formatError('INVALID_INPUT')).toMatchInlineSnapshot(
    `"Error: Invalid input provided"`
  );
});

// ✅ 使用 snapshot 属性匹配器处理动态值
it('should match user with generated id', () => {
  expect(createUser('Alice')).toMatchSnapshot({
    id: expect.any(String),
    createdAt: expect.any(Date),
  });
});
```

### Mock 策略

```typescript
// ✅ Vitest: vi.mock 自动 hoist
import { vi, describe, it, expect } from 'vitest';

vi.mock('./api', () => ({
  fetchUser: vi.fn().mockResolvedValue({ id: 1, name: 'Alice' }),
}));

it('should display user', async () => {
  const { fetchUser } = await import('./api');
  const user = await fetchUser('1');
  expect(user.name).toBe('Alice');
});

// ✅ Jest: jest.mock 同样自动 hoist
jest.mock('./database', () => ({
  query: jest.fn().mockResolvedValue([{ id: 1 }]),
}));

// ❌ 避免部分 Mock——测试的是 Mock 而非真实行为
jest.mock('./utils', () => ({
  ...jest.requireActual('./utils'),
  calculateTotal: jest.fn(), // 其他函数是真实的，这个是假的
}));
```

### 测试辅助工具

```typescript
// ✅ 使用 testing-library 进行 DOM 测试
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

it('should submit form', async () => {
  render(<LoginForm />);
  await userEvent.type(screen.getByLabelText('Email'), 'alice@example.com');
  await userEvent.click(screen.getByRole('button', { name: 'Submit' }));
  expect(screen.getByText('Welcome, Alice!')).toBeInTheDocument();
});

// ✅ 使用 MSW 进行 API mock（Mock Service Worker）
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

const server = setupServer(
  http.get('/api/users/:id', ({ params }) => {
    return HttpResponse.json({ id: params.id, name: 'Alice' });
  })
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

---

## 模块解析

### ESM vs CJS 差异和陷阱

```typescript
// ❌ CJS 风格在 ESM 中不可用
// package.json: "type": "module"
const fs = require('fs');           // Error: require is not defined
module.exports = { foo: 'bar' };    // Error: module is not defined

// ✅ ESM 正确写法
import fs from 'node:fs';
export const foo = 'bar';

// ✅ 在 ESM 中获取 __dirname
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ❌ ESM 中动态 require
const moduleName = 'lodash';
const _ = require(moduleName); // Error!

// ✅ ESM 动态 import
const _ = await import(moduleName);
```

### tsconfig paths 与 path aliases

```json
// tsconfig.json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"],
      "@components/*": ["./src/components/*"],
      "@utils/*": ["./src/utils/*"]
    }
  }
}
```

```typescript
// ✅ 使用别名前
import { Button } from '../../components/ui/Button';
import { formatDate } from '../../../utils/date';

// ✅ 使用别名后——清晰且不易因文件移动而断裂
import { Button } from '@components/ui/Button';
import { formatDate } from '@utils/date';
```

```typescript
// ⚠️ tsconfig paths 只影响 TS 编译，不影响运行时
// 需要配合打包工具（Vite、webpack）或 tsx 的别名解析

// vite.config.ts
import { resolve } from 'node:path';

export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
});

// ⚠️ 发布 npm 包时，tsconfig paths 不会自动解析
// 需要 tsc-alias 或 tsconfig-paths 处理
```

### package.json exports field

```json
// package.json
{
  "name": "my-library",
  "exports": {
    ".": {
      "import": "./dist/index.mjs",
      "require": "./dist/index.cjs",
      "types": "./dist/index.d.ts"
    },
    "./utils": {
      "import": "./dist/utils.mjs",
      "require": "./dist/utils.cjs",
      "types": "./dist/utils.d.ts"
    },
    "./*": "./dist/*"
  }
}
```

```typescript
// ✅ 消费者使用
import { foo } from 'my-library';        // 解析到 "." 条件
import { bar } from 'my-library/utils';   // 解析到 "./utils" 条件

// ❌ 没有 exports 映射的路径无法访问
import { secret } from 'my-library/internal'; // Error!
```

### 动态 import() 和代码分割

```typescript
// ✅ 条件加载模块
async function loadChartLibrary() {
  if (typeof window === 'undefined') return null; // SSR 跳过
  const { Chart } = await import('chart.js');
  return Chart;
}

// ✅ React 懒加载组件
const AdminPanel = lazy(() => import('./AdminPanel'));
// 配合 Suspense 使用
<Suspense fallback={<Loading />}>
  <AdminPanel />
</Suspense>

// ✅ 带错误处理
const AdminPanel = lazy(() =>
  import('./AdminPanel').catch(() => ({
    default: () => <ErrorFallback />,
  }))
);
```

---

## TS 4.9+ / 5.x 新特性

### satisfies 关键字（TS 4.9+）

```typescript
// ❌ 没有 satisfies：类型太宽泛
const palette = {
  red: '#ff0000',
  green: '#00ff00',
  blue: '#0000ff',
};
// palette.red 类型是 string，丢失了 '#ff0000' 的精确值

// ✅ satisfies 保留字面量类型，同时验证结构
const palette = {
  red: '#ff0000',
  green: '#00ff00',
  blue: '#0000ff',
} satisfies Record<string, `#${string}`>;

// palette.red 类型是 '#ff0000'（不是 string）
// 但添加新属性时仍会验证格式
```

```typescript
// ✅ satisfies 用于验证对象符合接口
interface UserConfig {
  theme: 'light' | 'dark';
  locale: string;
}

const config = {
  theme: 'dark',
  locale: 'en-US',
} satisfies UserConfig;
// config.theme 类型是 'dark'（不是 'light' | 'dark'）
// 所有属性都通过 satisfies 类型检查
```

### const 类型参数（TS 5.0+）

```typescript
// ❌ 之前：需要 as const 断言
function getRoutes<T extends readonly string[]>(routes: T) {
  return routes;
}
const routes = getRoutes(['home', 'about'] as const);

// ✅ TS 5.0+：const 类型参数
function getRoutes<const T extends readonly string[]>(routes: T) {
  return routes;
}
const routes = getRoutes(['home', 'about']);
// routes 类型是 readonly ['home', 'about']
```

```typescript
// ✅ 真实场景：类型安全的配置对象
declare function createConfig<const T extends Record<string, unknown>>(
  config: T
): T;

const config = createConfig({
  api: { url: 'https://api.example.com', version: 2 },
  features: { newDashboard: true },
});
// config.api.url 类型是 'https://api.example.com'（字面量）
```

### 装饰器（Stage 3 Decorators, TS 5.0+）

```typescript
// ✅ Stage 3 装饰器（TS 5.0+，experimentalDecorators 不再需要）
function logged<This, Args extends unknown[], Return>(
  target: (this: This, ...args: Args) => Return,
  context: ClassMethodDecoratorContext
) {
  return function (this: This, ...args: Args): Return {
    console.log(`Calling ${String(context.name)} with`, args);
    return target.apply(this, args);
  };
}

class Calculator {
  @logged
  add(a: number, b: number): number {
    return a + b;
  }
}

// 输出: Calling add with [1, 2]
new Calculator().add(1, 2);
```

```typescript
// ⚠️ Stage 3 装饰器与旧版 experimentalDecorators 不同
// 旧版：tsconfig 中需要 "experimentalDecorators": true
// 新版（TS 5.0+）：默认支持，无需额外配置

// ❌ 旧版装饰器签名（仍支持但标记为 legacy）
function deprecated<T extends { new (...args: any[]): {} }>(constructor: T) {
  return class extends constructor { /* ... */ };
}

// ✅ 新版装饰器按类型区分 context
function sealed<T extends { new (...args: any[]): {} }>(
  target: T,
  context: ClassDecoratorContext
) {
  // context.kind === 'class'
}
```

### using 声明（显式资源管理，TS 5.2+）

```typescript
// ✅ 使用 Symbol.dispose 实现自动清理
class TempFile implements Disposable {
  private path: string;

  constructor() {
    this.path = `/tmp/file-${Date.now()}`;
  }

  write(data: string) { /* ... */ }

  [Symbol.dispose]() {
    // 自动清理——无论函数如何退出（正常/异常）
    fs.unlinkSync(this.path);
    console.log(`Cleaned up: ${this.path}`);
  }
}

function processFile() {
  using file = new TempFile(); // using 声明
  file.write('data');
  // 作用域结束时自动调用 file[Symbol.dispose]()
}
```

```typescript
// ✅ AsyncDisposable 用于异步资源（TS 5.2+）
class DatabaseConnection implements AsyncDisposable {
  private db: sqlite3.Database;

  async connect() {
    this.db = new sqlite3.Database(':memory:');
  }

  async [Symbol.asyncDispose]() {
    await this.db.close();
  }
}

async function query() {
  await using conn = new DatabaseConnection(); // await using
  await conn.connect();
  // 作用域结束时自动 await conn[Symbol.asyncDispose]()
}
```

### 枚举改进（TS 5.0+）

```typescript
// ✅ 所有枚举现在都是 union 枚举（TS 5.0+）
enum Color {
  Red = 'RED',
  Green = 'GREEN',
}

// 之前：Color 作为类型时行为不一致
// 现在：Color 完全作为字符串字面量联合类型
const color: Color = Color.Red; // TypeScript 现在对 Color 类型有更好的推断
```

## Review Checklist

### 类型系统
- [ ] 没有使用 `any`（使用 `unknown` + 类型守卫代替）
- [ ] 接口和类型定义完整且有意义的命名
- [ ] 使用泛型提高代码复用性
- [ ] 联合类型有正确的类型收窄
- [ ] 善用工具类型（Partial、Pick、Omit 等）

### 泛型
- [ ] 泛型有适当的约束（extends）
- [ ] 泛型参数有合理的默认值
- [ ] 避免过度泛型化（KISS 原则）

### Strict 模式
- [ ] tsconfig.json 启用了 strict: true
- [ ] 启用了 noUncheckedIndexedAccess
- [ ] 没有使用 @ts-ignore（改用 @ts-expect-error）

### 异步代码
- [ ] async 函数有错误处理
- [ ] Promise rejection 被正确处理
- [ ] 没有 floating promises（未处理的 Promise）
- [ ] 并发请求使用 Promise.all 或 Promise.allSettled
- [ ] 竞态条件使用 AbortController 处理

### 不可变性
- [ ] 不直接修改函数参数
- [ ] 使用 spread 操作符创建新对象/数组
- [ ] 考虑使用 readonly 修饰符

### ESLint
- [ ] 使用 @typescript-eslint/recommended
- [ ] 没有 ESLint 警告或错误
- [ ] 使用 consistent-type-imports
