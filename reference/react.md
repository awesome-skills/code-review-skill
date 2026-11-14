# React Code Review Guide

> React 18 / 19 代码审查指南，覆盖 Hooks 规则、状态与列表 Key、副作用生命周期、性能优化与 React Compiler、组件与 Ref 设计、Server Components (RSC) 与 Next.js 15 边界、React 19 Actions & Forms、Suspense & Streaming、TanStack Query v5、XSS/无障碍安全及组件测试。通用 TypeScript 类型规范见 [TypeScript Guide](typescript.md)。

## 目录

- [版本与架构范围识别](#版本与架构范围识别)
- [基础 Hooks 规则](#基础-hooks-规则)
- [状态管理与列表 Key](#状态管理与列表-key)
- [useEffect 模式](#useeffect-模式)
- [useMemo / useCallback 与 React Compiler](#usememo--usecallback-与-react-compiler)
- [组件设计与 Ref 模式](#组件设计与-ref-模式)
- [Error Boundaries & Suspense](#error-boundaries--suspense)
- [Server Components (RSC) 与 Next.js 15](#server-components-rsc-与-nextjs-15)
- [React 19 Actions & Forms](#react-19-actions--forms)
- [Suspense & Streaming SSR](#suspense--streaming-ssr)
- [TanStack Query v5](#tanstack-query-v5)
- [安全与无障碍审查](#安全与无障碍审查)
- [组件测试](#组件测试)
- [Review Checklists](#review-checklists)
- [参考资料](#参考资料)

---

## 版本与架构范围识别

在提出版本或框架相关的审查意见前，先检查 `package.json`、构建配置与路由目录结构：

- **确认版本号**：检查 `react`（18 vs 19）、`next`（Pages Router vs App Router，14 vs 15+）、`@tanstack/react-query`（v4 vs v5）以及是否启用 `babel-plugin-react-compiler`。
- **不要跨版本强推新 API**：若仓库仍运行在 React 18，不要要求作者改用 `useActionState`、`useOptimistic`、`use()` 或移除 `forwardRef`（除非本次 PR 本身就是升级任务）。
- **区分严重级别**：
  - 🔴 `[blocking]`：违反 Hooks 调用规则、直接变异 State/Props、Server Action 缺失鉴权或输入校验、XSS / `javascript:` 协议注入、RSC 泄露敏感字段、竞态与内存泄漏、`useOptimistic` / `use()` 用法错误导致回滚或死循环。
  - 🟡 `[important]`：用 `useEffect` 同步派生状态或响应用户事件、组件内嵌套定义子组件、`queryKey` 遗漏依赖、缺少 Error Boundary、交互元素使用 `<div>` 破坏键盘与读屏无障碍。
  - 🟢 `[nit]`：对轻量原始值计算使用不必要的 `useMemo`、命名微调或非阻塞的现代化建议。

---

## 基础 Hooks 规则

### 顶层无条件调用（🔴 `[blocking]`）

Hooks 依赖固定的调用顺序维护内部链表，绝不能出现在条件分支、循环、提前 `return` 之后或事件回调中（`use(Context)` 除外）。

```tsx
// ❌ 在条件分支或提前 return 后调用 Hooks — 破坏 Hook 顺序导致运行时崩溃
function BadComponent({ isLoggedIn }: { isLoggedIn: boolean }) {
  if (!isLoggedIn) {
    return <LoginPrompt />;
  }
  const [user, setUser] = useState<User | null>(null); // Error!
  return <div>{user?.name}</div>;
}

// ✅ 所有 Hooks 必须在组件或自定义 Hook 顶层无条件调用
function GoodComponent({ isLoggedIn }: { isLoggedIn: boolean }) {
  const [user, setUser] = useState<User | null>(null);
  if (!isLoggedIn) {
    return <LoginPrompt />;
  }
  return <div>{user?.name}</div>;
}
```

### 自定义 Hook 命名与职责边界（🟡 `[important]`）

- 内部调用了任何 React Hook 的函数**必须**以 `use` 开头（如 `useAuth`），否则 `eslint-plugin-react-hooks` 无法检查调用位置规则。
- 不调用任何 Hook 的纯工具函数**不要**以 `use` 开头（如 `formatCurrency` 而非 `useCurrencyFormat`），避免误导调用者限制其使用位置。

```tsx
// ❌ 调用了 Hook 却未以 use 开头 — 绕过静态检查，极易被条件调用
function getWindowWidth() {
  const [width, setWidth] = useState(0);
  // ...
  return width;
}

// ✅ 遵循 use* 命名约定
function useWindowWidth() {
  const [width, setWidth] = useState(0);
  // ...
  return width;
}
```

---

## 状态管理与列表 Key

### 禁止直接变异 State 与 Props（🔴 `[blocking]`）

React 通过 `Object.is` 比较前后引用决定是否重渲染。原地修改数组或对象（`push`、`splice`、`sort`、`reverse` 或直接赋值属性）不会改变引用，导致界面不更新或引发撕裂。

```tsx
// ❌ 原地变异数组状态 — 引用未变，React 跳过重渲染
function BadTodoList() {
  const [todos, setTodos] = useState<Todo[]>([]);

  const handleSort = () => {
    todos.sort((a, b) => a.title.localeCompare(b.title)); // 原地修改 state！
    setTodos(todos); // Object.is(todos, todos) === true，UI 不更新
  };

  return <button onClick={handleSort}>Sort</button>;
}

// ✅ 返回全新引用，并在依赖前值时使用函数式更新避免闭包陈旧值
function GoodTodoList() {
  const [todos, setTodos] = useState<Todo[]>([]);

  const handleSort = () => {
    setTodos(prev => [...prev].sort((a, b) => a.title.localeCompare(b.title)));
  };

  const handleToggle = (id: string) => {
    setTodos(prev =>
      prev.map(t => (t.id === id ? { ...t, done: !t.done } : t))
    );
  };

  return <button onClick={handleSort}>Sort ({todos.length})</button>;
}
```

### 列表 `key` 与使用 `key` 重置组件状态（🔴 `[blocking]` / 🟡 `[important]`）

- **禁止在可排序、可筛选、可增删的列表中使用数组索引 `index` 作为 `key`**：当列表头部插入或删除项时，React 会按索引复用错误的组件实例，导致受控/非受控输入框内容串位（🔴 `[blocking]`）。
- **禁止在渲染期间生成随机 `key`**（如 `key={Math.random()}` 或 `key={crypto.randomUUID()}`）：每次渲染都会卸载并重新挂载整棵 DOM 子树，销毁焦点与内部状态（🔴 `[blocking]`）。
- **善用 `key` 重置状态**：切换实体（如切换不同用户的编辑表单）时，直接给表单传 `key={user.id}`，比在子组件中写 `useEffect(() => setDraft(user), [user])` 更简洁且无额外渲染闪烁。

```tsx
// ❌ 用 useEffect 在 prop 变化时手动重置内部状态（产生陈旧帧渲染）
function BadProfileEditor({ user }: { user: User }) {
  const [bio, setBio] = useState(user.bio);
  useEffect(() => {
    setBio(user.bio);
  }, [user.id, user.bio]);
  return <textarea value={bio} onChange={e => setBio(e.target.value)} />;
}

// ✅ 通过 key 显式声明组件身份，user.id 变化时自动重置整个子树状态
function ProfilePage({ user }: { user: User }) {
  return <ProfileEditor key={user.id} initialBio={user.bio} />;
}

function ProfileEditor({ initialBio }: { initialBio: string }) {
  const [bio, setBio] = useState(initialBio);
  return <textarea value={bio} onChange={e => setBio(e.target.value)} />;
}
```

### Context 拆分与高频重渲染隔离（🟡 `[important]`）

当 Context `value` 更新时，所有调用 `useContext` / `use(Context)` 的消费者都会无视 `React.memo` 强制重渲染。

```tsx
// ❌ 将高频变化状态（输入框/侧边栏开关）与低频数据（当前用户）混入同一内联对象
function BadProvider({ children, user }: { children: React.ReactNode; user: User }) {
  const [searchQuery, setSearchQuery] = useState('');
  // 每次输入都会创建新 value，导致只读 user 的所有组件全部重渲染
  return (
    <AppContext.Provider value={{ user, searchQuery, setSearchQuery }}>
      {children}
    </AppContext.Provider>
  );
}

// ✅ 按变化频率拆分 Context（或拆分 StateContext 与 DispatchContext），并稳定组合引用
function GoodProvider({ children, user }: { children: React.ReactNode; user: User }) {
  return (
    <AuthContext.Provider value={user}>
      <SearchStateProvider>{children}</SearchStateProvider>
    </AuthContext.Provider>
  );
}
```

---

## useEffect 模式

### 依赖完整性、竞态取消与错误处理（🔴 `[blocking]`）

客户端直接请求数据时，若缺少依赖会导致陈旧闭包；若缺少 `AbortController` 清理和错误捕获，快速切换参数时会发生后发先至的竞态覆盖（Race Condition）以及未处理的 Promise 拒绝。生产项目中优先使用 TanStack Query / SWR 或 Server Components 替代手写 `useEffect` 拉取数据。

```tsx
// ❌ 缺少 userId 依赖、未取消过期请求、且未捕获异步错误
function BadEffect({ userId }: { userId: string }) {
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    fetch(`/api/users/${userId}`)
      .then(res => res.json())
      .then(setUser);
  }, []); // 缺少 userId 依赖，且快速切换时存在竞态！
  return <div>{user?.name}</div>;
}

// ✅ 完整依赖 + AbortController 中止旧请求 + 显式错误处理
function GoodEffect({ userId }: { userId: string }) {
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);

    async function loadUser() {
      try {
        const res = await fetch(`/api/users/${encodeURIComponent(userId)}`, {
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: User = await res.json();
        setUser(data);
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError(err instanceof Error ? err.message : 'Failed to load user');
      }
    }

    void loadUser();
    return () => controller.abort();
  }, [userId]);

  if (error) return <p role="alert">{error}</p>;
  return <div>{user?.name}</div>;
}
```

### 避免用 `useEffect` 计算派生状态与响应事件（🟡 `[important]`）

```tsx
// ❌ useEffect 用于派生状态 — 触发多余的二次渲染与中间过期状态
function BadDerived({ items }: { items: Item[] }) {
  const [filteredItems, setFilteredItems] = useState<Item[]>([]);
  useEffect(() => {
    setFilteredItems(items.filter(i => i.active));
  }, [items]);
  return <List items={filteredItems} />;
}

// ✅ 渲染期间直接计算（列表巨大或下游为 memo 组件时再用 useMemo）
function GoodDerived({ items }: { items: Item[] }) {
  const filteredItems = items.filter(i => i.active);
  return <List items={filteredItems} />;
}

// ❌ useEffect 用于用户事件响应 — 组件重新挂载或 Strict Mode 下会重复上报
function BadEventEffect() {
  const [query, setQuery] = useState('');
  useEffect(() => {
    if (query) {
      analytics.track('search', { query });
    }
  }, [query]);
  return <input value={query} onChange={e => setQuery(e.target.value)} />;
}

// ✅ 在事件处理器中执行交互副作用
function GoodEvent() {
  const [query, setQuery] = useState('');
  const handleSearch = (q: string) => {
    setQuery(q);
    if (q) analytics.track('search', { query: q });
  };
  return <input value={query} onChange={e => handleSearch(e.target.value)} />;
}
```

### 订阅外部数据源优先使用 `useSyncExternalStore`（🟡 `[important]`）

手动在 `useEffect` 中监听浏览器状态（如 `navigator.onLine`、`matchMedia`、外部 Store）容易产生 SSR 水合不一致（Hydration Mismatch）与并发渲染撕裂。

```tsx
// ❌ 手写 useState + useEffect 订阅浏览器 API — SSR 易水合报错
function useBadOnlineStatus() {
  const [isOnline, setIsOnline] = useState(navigator.onLine); // SSR 下 window/navigator 不存在！
  useEffect(() => {
    const update = () => setIsOnline(navigator.onLine);
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);
  return isOnline;
}

// ✅ useSyncExternalStore 同时提供客户端快照与服务端安全快照
import { useSyncExternalStore } from 'react';

function subscribeOnline(callback: () => void) {
  window.addEventListener('online', callback);
  window.addEventListener('offline', callback);
  return () => {
    window.removeEventListener('online', callback);
    window.removeEventListener('offline', callback);
  };
}

export function useOnlineStatus() {
  return useSyncExternalStore(
    subscribeOnline,
    () => navigator.onLine,
    () => true // getServerSnapshot：SSR 默认返回确定值，避免水合不匹配
  );
}
```

> **Strict Mode 审查提示**：若组件在开发环境的 `<StrictMode>` 双重挂载（`mount → cleanup → mount`）下出现重复连接、重复动画或监听泄漏，根因通常是**缺少对称的清理函数**，切勿通过移除 `<StrictMode>` 或用 `useRef` 硬编码跳过第二次执行来掩盖泄漏。

---

## useMemo / useCallback 与 React Compiler

### 适度记忆化原则（🟢 `[nit]` / 🟡 `[important]`）

```tsx
// ❌ 过度优化 — 轻量字面量和未传给 memo 子组件的函数无需包装
function OverOptimized() {
  const config = useMemo(() => ({ timeout: 5000 }), []);
  const handleClick = useCallback(() => {
    console.log('clicked');
  }, []);
  return <button onClick={handleClick}>{config.timeout}</button>;
}

// ✅ 简单对象与普通 DOM 事件直接定义
function ProperlyOptimized() {
  const config = { timeout: 5000 };
  const handleClick = () => console.log('clicked');
  return <button onClick={handleClick}>{config.timeout}</button>;
}

// ✅ 当下游是昂贵的 React.memo 组件或作为 Hook 依赖时，配对使用 useMemo + useCallback
const MemoizedChart = React.memo(function Chart({
  onSelect,
  points,
}: {
  onSelect: (count: number) => void;
  points: Point[];
}) {
  return <div onClick={() => onSelect(points.length)}>{points.length}</div>;
});

function Dashboard({ rawPoints }: { rawPoints: RawPoint[] }) {
  const points = useMemo(() => normalizePoints(rawPoints), [rawPoints]);
  const handleSelect = useCallback((count: number) => {
    console.log(count);
  }, []);
  return <MemoizedChart onSelect={handleSelect} points={points} />;
}
```

### React Compiler 感知与渲染纯度（🔴 `[blocking]`）

如果项目已启用 **React Compiler**（`babel-plugin-react-compiler`），编译器会自动对组件和表达式做细粒度记忆化，新代码中通常无需手写模板化的 `useMemo` / `useCallback` / `React.memo`。审查重点应转向**渲染纯度（Rules of React）**——渲染阶段变异局部对象或读写 `ref.current` 会破坏编译器的缓存假设，导致难以排查的脏读 Bug。

```tsx
// ❌ 渲染期间读写 ref.current 或变异外部传入数组 — 破坏并发渲染与 React Compiler
function ImpureComponent({ items }: { items: string[] }) {
  const renderCountRef = useRef(0);
  renderCountRef.current += 1; // 禁止在 render 期间写入 ref！
  items.push('extra');         // 禁止变异 props！
  return <div>{items.join(', ')}</div>;
}

// ✅ 保持渲染为纯函数；副作用与 ref 写入放在 useEffect 或事件处理器中
function PureComponent({ items }: { items: readonly string[] }) {
  const displayItems = [...items, 'extra'];
  return <div>{displayItems.join(', ')}</div>;
}
```

---

## 组件设计与 Ref 模式

### 禁止在组件内部定义子组件（🟡 `[important]`）

```tsx
// ❌ 在父组件内部声明组件 — 每次父组件渲染都会生成全新的组件类型，导致子树卸载重挂载、输入框失焦
function BadParent() {
  const [step, setStep] = useState(1);
  function StepForm() {
    return <input placeholder="Type here..." />;
  }
  return <StepForm />;
}

// ✅ 将子组件提取到模块顶层，通过 props 传递数据
function StepForm({ step }: { step: number }) {
  return <input placeholder={`Step ${step}`} />;
}

function GoodParent() {
  const [step] = useState(1);
  return <StepForm step={step} />;
}
```

### React 19 `ref` Prop 与 Ref Cleanup（🟡 `[important]`）

在 React 19 中：
1. 函数组件可直接从 props 接收 `ref`，不再需要 `React.forwardRef` 包装。
2. Callback `ref` 支持返回清理函数（类似 `useEffect`），组件卸载时自动调用。
3. **注意 TypeScript 陷阱（🔴 `[blocking]`）**：在 React 19 中编写 `ref={el => (myRef.current = el)}` 会隐式返回 `HTMLElement | null`，被 React 误判为非法的清理函数并触发类型错误，必须使用花括号块体 `{ myRef.current = el; }`。

```tsx
// ❌ React 19 冗余写法 + 隐式返回赋值结果导致类型与运行时告警
const OldInput = React.forwardRef<HTMLInputElement, { label: string }>(
  function OldInput({ label }, ref) {
    return <input aria-label={label} ref={ref} />;
  }
);
// <div ref={el => (boxRef.current = el)} />  // ❌ 箭头函数隐式返回了 el！

// ✅ React 19 直接接收 ref prop，并利用 callback ref 返回清理函数管理观察器
interface InputProps extends React.ComponentPropsWithRef<'input'> {
  label: string;
}

function TextInput({ label, ref, ...props }: InputProps) {
  return <input aria-label={label} ref={ref} {...props} />;
}

function ResizablePanel() {
  const observeSize = useCallback((node: HTMLDivElement | null) => {
    if (!node) return;
    const observer = new ResizeObserver(entries => {
      console.log(entries[0]?.contentRect.width);
    });
    observer.observe(node);
    return () => observer.disconnect(); // React 19 卸载时自动调用清理函数
  }, []);

  return <div ref={observeSize}>Content</div>;
}
```

---

## Error Boundaries & Suspense

Suspense 本身只捕获未决的 Promise（加载态），**不会**捕获异步数据抛出的异常。未包裹 Error Boundary 的 Suspense 或 `use()` / `useSuspenseQuery` 一旦报错会向上冒泡直至白屏崩溃（🟡 `[important]`）。同时应提供重试与路由/参数变化时的 `resetKeys` 恢复机制。

```tsx
// ❌ 仅有 Suspense 没有错误边界 — 请求失败会导致整页白屏且无法恢复
function BadApp({ projectId }: { projectId: string }) {
  return (
    <Suspense fallback={<Loading />}>
      <ProjectBoard projectId={projectId} />
    </Suspense>
  );
}

// ✅ ErrorBoundary 包裹 Suspense，并随关键参数重置错误态
import { ErrorBoundary } from 'react-error-boundary';

function GoodApp({ projectId }: { projectId: string }) {
  return (
    <ErrorBoundary
      resetKeys={[projectId]}
      fallbackRender={({ error, resetErrorBoundary }) => (
        <div role="alert">
          <p>加载项目失败：{error instanceof Error ? error.message : '未知错误'}</p>
          <button type="button" onClick={resetErrorBoundary}>重试</button>
        </div>
      )}
    >
      <Suspense fallback={<BoardSkeleton />}>
        <ProjectBoard projectId={projectId} />
      </Suspense>
    </ErrorBoundary>
  );
}
```

---

## Server Components (RSC) 与 Next.js 15

### `'use client'` 下沉与 Children 组合模式（🟡 `[important]`）

`'use client'` 声明的是服务端到客户端的模块边界：在该文件中被 `import` 的所有子模块都会被打包进客户端 Bundle；但通过 `children`（插槽）传入的 Server Component 依然在服务端渲染。

```tsx
// ❌ 在顶层布局或大型容器标记 'use client'，把重型静态内容全部拖入客户端包体
// app/dashboard/layout.tsx
'use client';
import { HeavyMarkdownDocs } from './heavy-docs'; // 被迫打入客户端 JS！

export default function BadLayout({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(o => !o)}>Toggle</button>
      {open && <HeavyMarkdownDocs />}
      {children}
    </div>
  );
}

// ✅ 客户端组件只负责交互外壳，通过 children 插槽承载 Server Component
// app/dashboard/collapsible-shell.tsx
'use client';
export function CollapsibleShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(o => !o)}>Toggle</button>
      {open && children}
    </div>
  );
}

// app/dashboard/layout.tsx (Server Component)
import { CollapsibleShell } from './collapsible-shell';
import { HeavyMarkdownDocs } from './heavy-docs'; // 留在服务端渲染，零客户端体积！

export default function GoodLayout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <CollapsibleShell>
        <HeavyMarkdownDocs />
      </CollapsibleShell>
      {children}
    </div>
  );
}
```

### RSC 数据序列化与敏感字段脱敏（🔴 `[blocking]`）

Server Component 传给 Client Component 的所有 props 都会序列化进 HTML 流与 RSC Payload，用户在浏览器 DevTools 网络面板中可直接查看全部字段。**严禁**将完整的数据库 ORM 模型直接跨边界传递。

```tsx
// ❌ 将数据库完整实体直接传给客户端组件 — passwordHash、内部备注等敏感字段直接暴露到前端网络包
async function BadProfilePage({ userId }: { userId: string }) {
  const dbUser = await db.users.findUnique({ where: { id: userId } });
  return <ClientProfileCard user={dbUser} />; // 🔴 严重数据泄露！
}

// ✅ 服务端模块添加 'server-only' 防误引，且仅向客户端映射最小公开 DTO
import 'server-only';

async function GoodProfilePage({ userId }: { userId: string }) {
  const dbUser = await db.users.findUniqueOrThrow({ where: { id: userId } });
  const publicProfile = {
    id: dbUser.id,
    displayName: dbUser.displayName,
    avatarUrl: dbUser.avatarUrl,
  };
  return <ClientProfileCard user={publicProfile} />;
}
```

### Next.js 15 异步动态 API（🔴 `[blocking]`）

在 Next.js 15+ 中，路由 `params`、`searchParams` 以及 `cookies()`、`headers()`、`draftMode()` 均已改为**异步返回 Promise**，同步读取属性会导致运行时错误或类型报错。同时 Next.js 15 的 `fetch()` 默认不再强制缓存（`no-store` 语义）。

```tsx
// ❌ Next.js 14 同步访问写法 — 在 Next.js 15+ 中报错
import { cookies } from 'next/headers';

export default async function BadPage({
  params,
}: {
  params: { slug: string };
}) {
  const token = cookies().get('session')?.value; // Error in Next.js 15!
  return <h1>{params.slug} ({Boolean(token)})</h1>;
}

// ✅ Next.js 15+ 显式 await 动态路由参数与请求上下文 API
import { cookies } from 'next/headers';

export default async function GoodPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const [{ slug }, { page = '1' }, cookieStore] = await Promise.all([
    params,
    searchParams,
    cookies(),
  ]);
  const hasSession = cookieStore.has('session');
  return <h1>{slug} - Page {page} ({String(hasSession)})</h1>;
}
```

---

## React 19 Actions & Forms

React 19 引入了 Actions 系统和新的表单 Hooks，统一异步变更、待定状态与乐观更新。

### `useActionState`（类型安全与错误收窄）

```tsx
// ❌ 传统手写多个耦合状态变量，且 catch (e) 直接读取 e.message 违反 strict 类型检查
function OldForm() {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsPending(true);
    setError(null);
    try {
      await submitForm(new FormData(e.currentTarget));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsPending(false);
    }
  };
  return <form onSubmit={handleSubmit}>...</form>;
}

// ✅ React 19: useActionState 统一管理状态、Action 与 pending
import { useActionState } from 'react';

type FormState = {
  success: boolean;
  error: string | null;
};

const initialState: FormState = { success: false, error: null };

function SubscribeForm() {
  const [state, formAction, isPending] = useActionState(
    async (_prevState: FormState, formData: FormData): Promise<FormState> => {
      try {
        await submitForm(formData);
        return { success: true, error: null };
      } catch (err) {
        return {
          success: false,
          error: err instanceof Error ? err.message : '提交失败，请稍后重试',
        };
      }
    },
    initialState
  );

  return (
    <form action={formAction}>
      <input name="email" type="email" required />
      <button type="submit" disabled={isPending}>
        {isPending ? 'Submitting...' : 'Submit'}
      </button>
      {state.error && <p role="alert">{state.error}</p>}
    </form>
  );
}
```

### `useFormStatus` 调用层级约束（🔴 `[blocking]`）

`useFormStatus` 只读取**上层父级 `<form>`** 的提交状态，在渲染 `<form>` 的同一个组件内调用永远返回 `pending: false`。

```tsx
// ❌ 在渲染 <form> 的同级组件内调用 useFormStatus —— pending 永远为 false！
import { useFormStatus } from 'react-dom';

function BadForm({ action }: { action: (formData: FormData) => void }) {
  const { pending } = useFormStatus(); // 无法读取下方 <form> 的状态！
  return (
    <form action={action}>
      <button type="submit" disabled={pending}>Submit</button>
    </form>
  );
}

// ✅ 提取为 <form> 内部的子组件
function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending}>
      {pending ? 'Submitting...' : 'Submit'}
    </button>
  );
}

function GoodForm({ action }: { action: (formData: FormData) => void }) {
  return (
    <form action={action}>
      <SubmitButton />
    </form>
  );
}
```

### `useOptimistic` 与 Transition / 基准状态同步（🔴 `[blocking]`）

审查 `useOptimistic` 时需重点检查两个高频缺陷：
1. **必须在 Action 或 `startTransition` 内调用乐观更新函数**：在普通 `async onClick` 中直接调用会触发 React 19 警告并在下一次渲染立即回滚。
2. **成功后必须推进基准状态（Base State）**：当 Transition 结束时，`useOptimistic` 会切回传入的第一个参数（基准值）。如果请求成功后没有更新基准状态（或通过 Server Action 刷新父级 props），即使请求成功，数字也会瞬间跳回旧值！
3. **禁止用于不可逆关键交易**（如扣款成功确认、删除生产库等）。

```tsx
// ❌ 在 Transition 外调用 addOptimisticLike，且成功后未更新基准 likes 导致 UI 跳回旧值
function BrokenLike({ postId, initialLikes }: { postId: string; initialLikes: number }) {
  const [optimisticLikes, addOptimisticLike] = useOptimistic(
    initialLikes,
    (current, increment: number) => current + increment
  );

  const handleLike = async () => {
    addOptimisticLike(1); // ❌ 不在 Action / startTransition 内！
    await likePost(postId); // ❌ 结束后 initialLikes 未变，UI 跳回原值！
  };

  return <button type="button" onClick={handleLike}>{optimisticLikes} likes</button>;
}

// ✅ 在 startTransition 内执行乐观更新，并在成功后同步提交态，失败时自动回滚
import { useOptimistic, useState, useTransition } from 'react';

function FastLike({ postId, initialLikes }: { postId: string; initialLikes: number }) {
  const [likes, setLikes] = useState(initialLikes);
  const [isPending, startTransition] = useTransition();
  const [optimisticLikes, addOptimisticLike] = useOptimistic(
    likes,
    (current, increment: number) => current + increment
  );

  const handleLike = () => {
    startTransition(async () => {
      addOptimisticLike(1);
      try {
        const updatedCount = await likePost(postId);
        setLikes(updatedCount); // 推进基准状态，Transition 结束后保持最新值
      } catch {
        // Transition 结束时 React 自动回滚到未修改的 likes 基准值
      }
    });
  };

  return (
    <button type="button" onClick={handleLike} disabled={isPending}>
      {optimisticLikes} likes
    </button>
  );
}
```

### Server Actions 鉴权、校验与 `redirect()` 陷阱（🔴 `[blocking]`）

标记了 `'use server'` 的导出函数会被编译为**公开可访问的 HTTP POST 端点**，攻击者可绕过前端表单直接构造请求调用：
1. **每次调用都必须在函数内部校验身份与资源归属权限**（不能依赖外层 Layout 或前端隐藏按钮）。
2. **必须用 Schema（如 Zod）校验 `FormData`**（`formData.get()` 返回 `string | File | null`）。
3. **不要在宽泛的 `try/catch` 内调用 Next.js `redirect()` 或 `notFound()`**：它们通过抛出内部特殊异常中断执行，被 `catch` 捕获后会导致重定向静默失效！

```tsx
// ❌ 严重安全与逻辑缺陷：无鉴权、无输入校验、且 try/catch 吞掉了 redirect()
'use server';
import { redirect } from 'next/navigation';

export async function badCreatePost(_prevState: any, formData: FormData) {
  try {
    const title = formData.get('title'); // 可能是 File 或 null，无长度/格式校验！
    await db.posts.create({ data: { title } }); // 未验证登录态！
    redirect('/posts'); // ❌ 抛出的 NEXT_REDIRECT 被下方 catch 捕获，跳转失败！
  } catch (e: any) {
    return { error: e.message }; // ❌ 将数据库内部错误栈暴露给客户端！
  }
}

// ✅ 完整鉴权 + Zod 输入验证 + 将 redirect() 放在 try/catch 外部
'use server';
import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { z } from 'zod';

const CreatePostSchema = z.object({
  title: z.string().trim().min(1, '标题不能为空').max(120, '标题过长'),
});

export type CreatePostState = { error?: string };

export async function createPost(
  _prevState: CreatePostState,
  formData: FormData
): Promise<CreatePostState> {
  const session = await verifySession();
  if (!session?.userId) {
    return { error: '请先登录' };
  }

  const parsed = CreatePostSchema.safeParse({
    title: formData.get('title'),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? '参数不合法' };
  }

  try {
    await db.posts.create({
      data: {
        title: parsed.data.title,
        authorId: session.userId,
      },
    });
  } catch {
    return { error: '创建文章失败，请稍后重试' }; // 不泄露底层异常详情
  }

  revalidatePath('/posts');
  redirect('/posts'); // ✅ 在 try/catch 之外调用，正常触发路由跳转
}
```

---

## Suspense & Streaming SSR

### 细粒度独立 Suspense 边界与消除串行瀑布流（🟡 `[important]`）

```tsx
// ❌ 单一边界 + 串行 await 瀑布流 —— 慢接口阻塞整页与快接口
async function BadDashboard({ userId }: { userId: string }) {
  const user = await fetchUser(userId);       // 200ms
  const metrics = await fetchMetrics(userId); // 1200ms（本可并行！）
  return (
    <Suspense fallback={<FullPageSpinner />}>
      <Header user={user} />
      <MetricsPanel metrics={metrics} />
    </Suspense>
  );
}

// ✅ 无依赖请求使用 Promise.all 并行，慢模块拆分独立 Suspense 流式传输
async function GoodDashboard({ userId }: { userId: string }) {
  const user = await fetchUser(userId);
  return (
    <>
      <Header user={user} /> {/* 立即渲染 */}
      <div className="grid">
        <Suspense fallback={<MetricsSkeleton />}>
          <AsyncMetricsPanel userId={userId} /> {/* 独立流式传输 */}
        </Suspense>
        <Suspense fallback={<ActivitySkeleton />}>
          <AsyncActivityFeed userId={userId} /> {/* 独立流式传输 */}
        </Suspense>
      </div>
    </>
  );
}
```

### `use()` Hook 消费 Promise 与 Context（React 19，🔴 `[blocking]`）

React 19 的 `use()` 可以在渲染期间解包 Promise（触发最近的 `<Suspense>`）或读取 Context（且允许在 `if` 分支内按需读取 `use(ThemeContext)`）。

> **核心审查红线**：**绝不能在 Client Component 的渲染函数体中直接创建未缓存的 Promise 传给 `use()`**！否则每次重渲染都会产生新 Promise，导致组件无限挂起与重复请求。应在 **Server Component** 中创建 Promise 后通过 props 传给 Client Component（注意解析结果必须可序列化），或使用支持 Suspense 的缓存库。

```tsx
// ❌ 在客户端组件渲染期间直接调用 fetchComments() — 每次重渲染都生成新 Promise 导致无限挂起！
'use client';
import { use } from 'react';

function BrokenClientPost({ postId }: { postId: string }) {
  const comments = use(fetchComments(postId)); // 🔴 死循环风险！
  return <div>{comments.length}</div>;
}

// ✅ Server Component 创建 Promise（不 await），流式传递给 Client Component 用 use() 解包
// app/posts/[id]/page.tsx (Server Component)
import { Suspense } from 'react';
import { Comments } from './comments';

export default async function PostPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const post = await fetchPost(id);
  const commentsPromise = fetchComments(id); // 在服务端启动请求，不阻塞正文渲染

  return (
    <article>
      <h1>{post.title}</h1>
      <Suspense fallback={<CommentsSkeleton />}>
        <Comments commentsPromise={commentsPromise} />
      </Suspense>
    </article>
  );
}

// app/posts/[id]/comments.tsx (Client Component)
'use client';
import { use } from 'react';

export function Comments({
  commentsPromise,
}: {
  commentsPromise: Promise<CommentItem[]>;
}) {
  const comments = use(commentsPromise);
  return (
    <ul>
      {comments.map(c => (
        <li key={c.id}>{c.text}</li>
      ))}
    </ul>
  );
}
```

---

## TanStack Query v5

### 基础配置与 v4 → v5 破坏性变更（🔴 `[blocking]`）

审查 TanStack Query v5 代码时，注意以下已移除的 v4 写法：
1. **移除位置参数重载**：只支持单一对象参数 `useQuery({ queryKey, queryFn })`，旧写法 `useQuery(['users'], fetchUsers)` 直接报错。
2. **`useQuery` 已移除 `onSuccess` / `onError` / `onSettled` 回调**：避免在每次缓存读取或后台挂载时意外触发副作用；应在 `useMutation` 回调或渲染衍生逻辑中处理。
3. **`cacheTime` 已重命名为 `gcTime`**。

```tsx
// ✅ 生产环境 QueryClient 推荐默认配置
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 分钟内视为新鲜，避免组件频繁挂载时重复请求
      gcTime: 1000 * 60 * 30,   // 30 分钟未订阅后回收缓存（v5 由 cacheTime 重命名）
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});
```

### `queryOptions` 统一复用与 `queryKey` 依赖完整性（🟡 `[important]`）

```tsx
// ❌ queryKey 遗漏过滤参数 — filters 变化时不会重新请求且命中错误缓存
function BadItemsList({ filters }: { filters: ItemFilters }) {
  return useQuery({
    queryKey: ['items'], // 缺少 filters！
    queryFn: () => fetchItems(filters),
  });
}

// ✅ 使用 queryOptions 集中定义 queryKey 与 queryFn，兼顾复用与 getQueryData 类型推导
import { queryOptions, useQuery } from '@tanstack/react-query';

export const userQueryOptions = (userId: string) =>
  queryOptions({
    queryKey: ['users', userId] as const,
    queryFn: ({ signal }) => fetchUser(userId, { signal }), // 透传 signal 支持自动取消
  });

function UserCard({ userId }: { userId: string }) {
  const { data } = useQuery(userQueryOptions(userId));
  return <div>{data?.name}</div>;
}
```

### `useSuspenseQuery` 限制与并行查询

| 特性 | `useQuery` | `useSuspenseQuery` |
|------|------------|--------------------|
| `enabled` / `placeholderData` | ✅ 支持 | ❌ **不支持** |
| `data` 类型 | `T \| undefined` | `T`（保证已就绪） |
| 错误与加载处理 | `error` / `isPending` 字段 | 抛给 Error Boundary / Suspense |

```tsx
// ❌ useSuspenseQuery 不支持 enabled；且在同一组件内串行写多个 useSuspenseQuery 会产生请求瀑布流！
function BadProfile({ userId }: { userId?: string }) {
  const { data: user } = useSuspenseQuery({
    queryKey: ['user', userId],
    queryFn: () => fetchUser(userId!),
    // enabled: Boolean(userId), // ❌ 编译错误：不支持 enabled！
  });
  // ❌ 上一个挂起结束后才会发起下一个请求（串行瀑布流）！
  const { data: posts } = useSuspenseQuery({
    queryKey: ['posts', userId],
    queryFn: () => fetchPosts(userId!),
  });
  return <ProfileView user={user} posts={posts} />;
}

// ✅ 通过父组件条件渲染替代 enabled，并用 useSuspenseQueries 并行发起多个独立请求
import { useSuspenseQueries } from '@tanstack/react-query';

function ProfileContent({ userId }: { userId: string }) {
  const [userQuery, postsQuery] = useSuspenseQueries({
    queries: [
      { queryKey: ['user', userId], queryFn: () => fetchUser(userId) },
      { queryKey: ['posts', userId], queryFn: () => fetchPosts(userId) },
    ],
  });
  return <ProfileView user={userQuery.data} posts={postsQuery.data} />;
}

function ProfileSection({ userId }: { userId?: string }) {
  if (!userId) return <EmptySelection />;
  return (
    <ErrorBoundary fallback={<ErrorCard />}>
      <Suspense fallback={<ProfileSkeleton />}>
        <ProfileContent userId={userId} />
      </Suspense>
    </ErrorBoundary>
  );
}
```

### 乐观更新与 `onSettled` 返回 Promise 防闪烁（🟡 `[important]`）

在 v5 中利用 `useMutation` 的 `variables` 和 `isPending` 实现轻量乐观 UI 时，**必须在 `onSettled` 中 `return` `queryClient.invalidateQueries(...)` 的 Promise**——这样 `isPending` 会一直保持为 `true` 直到最新列表重新拉取完毕，避免乐观条目在请求完成与列表刷新之间的空窗期突然消失再闪现。

```tsx
// ✅ v5 简化乐观更新：return invalidateQueries Promise 消除空窗期闪烁
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

function TodoList() {
  const queryClient = useQueryClient();
  const { data: todos = [] } = useQuery(todosQueryOptions);

  const { mutate, variables, isPending } = useMutation({
    mutationFn: (title: string) => addTodo({ title }),
    onSettled: () => {
      // 关键：返回 Promise 使 isPending 持续到失效重拉完成！
      return queryClient.invalidateQueries({ queryKey: todosQueryOptions.queryKey });
    },
  });

  return (
    <ul>
      {todos.map(todo => (
        <TodoItem key={todo.id} todo={todo} />
      ))}
      {isPending && (
        <TodoItem
          todo={{ id: 'optimistic-temp', title: variables, completed: false }}
          isOptimistic
        />
      )}
    </ul>
  );
}
```

### v5 状态字段语义变化

```tsx
const { data, isPending, isFetching, isLoading } = useQuery(todosQueryOptions);

// isPending:  缓存中尚无数据（status === 'pending'）
// isFetching: 请求正在网络传输中（含后台静默刷新）
// isLoading:  isPending && isFetching（首次加载且正在请求中；对禁用查询为 false）
```

---

## 安全与无障碍审查

### XSS 防护：`dangerouslySetInnerHTML` 与 `javascript:` URL 注入（🔴 `[blocking]`）

React 默认转义 JSX 文本子节点（`<div>{input}</div>`），但**不会转义 `dangerouslySetInnerHTML`、直接操作 `ref.current.innerHTML` 或 `<a href={url}>` / `<iframe src={url}>` 中的危险协议**！详见 [XSS Prevention Guide](cross-cutting/xss-prevention.md)。

```tsx
// ❌ 两个常见 React XSS 漏洞：未净化富文本 + 未校验用户自定义链接协议
function BadComment({ htmlBio, websiteUrl }: { htmlBio: string; websiteUrl: string }) {
  return (
    <div>
      {/* 🔴 若 htmlBio 含 <img src=x onerror=...> 直接触发存储型 XSS */}
      <div dangerouslySetInnerHTML={{ __html: htmlBio }} />
      {/* 🔴 若 websiteUrl 为 "javascript:alert(document.cookie)" 点击即执行脚本 */}
      <a href={websiteUrl} target="_blank">访问主页</a>
    </div>
  );
}

// ✅ 使用 DOMPurify 净化富文本 + 白名单校验 http/https URL + rel="noopener noreferrer"
import DOMPurify from 'isomorphic-dompurify';

function toSafeHttpUrl(raw: string): string | null {
  try {
    const parsed = new URL(raw);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:'
      ? parsed.toString()
      : null;
  } catch {
    return null;
  }
}

function SafeComment({ htmlBio, websiteUrl }: { htmlBio: string; websiteUrl: string }) {
  const safeUrl = toSafeHttpUrl(websiteUrl);
  const cleanHtml = DOMPurify.sanitize(htmlBio);

  return (
    <div>
      <div dangerouslySetInnerHTML={{ __html: cleanHtml }} />
      {safeUrl && (
        <a href={safeUrl} target="_blank" rel="noopener noreferrer">
          访问主页
        </a>
      )}
    </div>
  );
}
```

### 语义化交互元素与 `useId()` 无障碍关联（🟡 `[important]`）

- **禁止用 `<div onClick>` 或 `<span onClick>` 冒充按钮**：它们无法通过 `Tab` 聚焦、无法响应键盘 `Enter`/`Space`、也没有无障碍角色。应使用 `<button type="button">`（注意在 `<form>` 内非提交按钮必须显式声明 `type="button"`，否则默认是 `type="submit"`！）。
- **使用 `useId()` 生成表单无障碍 ID**：不要使用模块自增计数器或 `Math.random()` 生成 `id`/`htmlFor`，否则在 SSR 流式渲染下会导致服务端与客户端 ID 不匹配的水合错误。

```tsx
// ❌ 非语义化 div 按钮 + 硬编码 id 在页面复用多个实例时冲突
function BadField({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <div>
      <label htmlFor="email-input">{label}</label>
      <input id="email-input" />
      <div className="btn" onClick={onClear}>清空</div>
    </div>
  );
}

// ✅ useId() 保证多实例与 SSR 水合唯一性 + 显式 type="button"
import { useId } from 'react';

function GoodField({ label, onClear }: { label: string; onClear: () => void }) {
  const inputId = useId();
  return (
    <div>
      <label htmlFor={inputId}>{label}</label>
      <input id={inputId} />
      <button type="button" onClick={onClear}>清空</button>
    </div>
  );
}
```

---

## 组件测试

测试应使用 `@testing-library/react` 与 `@testing-library/user-event` 验证**用户可感知的行为与无障碍语义**，避免耦合 CSS 类名或内部 State 实现细节（🟡 `[important]`）。

```tsx
// ❌ 脆弱的测试：依赖 querySelector 类名、使用同步 fireEvent、异步断言未用 findBy*
import { render, fireEvent } from '@testing-library/react';

test('bad login test', () => {
  const { container } = render(<LoginForm />);
  const btn = container.querySelector('.submit-btn')!;
  fireEvent.click(btn); // 未模拟真实焦点、键盘与指针事件序列
  expect(container.textContent).toContain('请输入邮箱'); // 异步校验时直接失败或产生 act() 告警
});

// ✅ 稳健的测试：screen + getByRole / getByLabelText + userEvent.setup() + findByRole
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

test('displays validation alert when submitting empty login form', async () => {
  const user = userEvent.setup();
  render(<LoginForm />);

  await user.click(screen.getByRole('button', { name: /登录/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent('请输入邮箱');
});
```

---

## Review Checklists

### Hooks 与状态管理

- [ ] Hooks 均在组件或 `use*` 自定义 Hook 顶层无条件调用（无提前 `return` 后调用 Hook）
- [ ] 没有原地变异 State 或 Props（如 `array.sort()` / `push()`），基于前值更新使用函数式 `setState(prev => ...)`
- [ ] 可重排/增删列表使用稳定的业务 ID 作为 `key`（未使用数组索引或 `Math.random()`）
- [ ] 没有用 `useEffect` 计算纯派生状态或处理用户交互事件
- [ ] `useEffect` 依赖数组完整，且请求/定时器/事件监听具备对称清理函数（如 `AbortController`）
- [ ] 浏览器/外部状态订阅优先使用 `useSyncExternalStore` 并提供 SSR `getServerSnapshot`

### 性能优化、组件与 Ref

- [ ] 没有在父组件函数体内嵌套定义子组件
- [ ] Context 按变化频率拆分，避免高频状态变化触发整棵消费树重渲染
- [ ] `useMemo` / `useCallback` 仅用于昂贵计算、稳定下游 `React.memo` 引用或稳定 Effect 依赖（启用 React Compiler 时保持渲染纯度，不在 render 中读写 `ref.current`）
- [ ] React 19 callback `ref` 使用块体避免隐式返回 DOM 节点，并在需要时返回清理函数

### RSC、Next.js 15 与 React 19 Actions

- [ ] `'use client'` 下沉到交互叶子组件，善用 `children` 插槽保留服务端渲染能力
- [ ] Server Component 传给 Client Component 的 props 已做最小化 DTO 脱敏（未直接透传数据库完整模型）
- [ ] Next.js 15+ 中已 `await` 异步动态 API（`params`、`searchParams`、`cookies()`、`headers()`）
- [ ] `useFormStatus` 在 `<form>` 内部的子组件中调用，而非同级组件
- [ ] `useOptimistic` 在 Action 或 `startTransition` 内调用，成功后同步更新基准状态，且未用于支付等关键不可逆操作
- [ ] `'use server'` Server Action 包含服务端登录/权限校验、Schema 输入校验，且未在 `try/catch` 中误吞 `redirect()` / `notFound()`

### Suspense、Streaming 与 TanStack Query v5

- [ ] 关键异步区域与每个 `use()` / `useSuspenseQuery` 的 `<Suspense>` 外层有 `<ErrorBoundary>` 兜底
- [ ] `use(promise)` 消费的 Promise 来自 Server Component 或缓存层，未在 Client Component 渲染体中每次新建
- [ ] TanStack Query v5 使用对象参数语法，未残留已废弃的 `useQuery` `onSuccess`/`onError` 回调
- [ ] `queryKey` 包含所有影响请求结果的参数，并配置合理的 `staleTime`
- [ ] `useSuspenseQuery` 未使用不支持的 `enabled`，多独立挂起请求使用 `useSuspenseQueries` 避免串行瀑布流
- [ ] 基于 `variables` 的乐观更新在 `onSettled` 中 `return queryClient.invalidateQueries(...)` 防止空窗期闪烁

### 安全、无障碍与测试

- [ ] 未使用未净化的 `dangerouslySetInnerHTML`，用户可控的 `<a href>` 已校验 `http:`/`https:` 协议防止 `javascript:` XSS
- [ ] 可点击交互元素使用语义化 `<button type="button">` / `<a>` 而非 `<div onClick>`，表单标签使用 `useId()` 关联
- [ ] 组件测试使用 `screen`、`*ByRole`、`userEvent.setup()` 与异步 `findBy*`，测试用户可见行为而非内部实现

---

## 参考资料

- [React Official Documentation (React 19)](https://react.dev/)
- [Rules of React & React Compiler Purity](https://react.dev/reference/rules)
- [Next.js 15 App Router & Data Security Guide](https://nextjs.org/docs/app/building-your-application/authentication)
- [TanStack Query v5 Documentation & Migration Guide](https://tanstack.com/query/v5/docs/framework/react/overview)
- [Testing Library — Guiding Principles](https://testing-library.com/docs/guiding-principles/)
