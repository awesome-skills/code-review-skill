# Svelte / SvelteKit Code Review Guide

Svelte 5 / SvelteKit 审查重点：Runes 响应式系统、Server/Client 边界、Form Actions、Store 迁移、以及安全性。

## 目录

- [Runes: $state / $derived / $effect](#runes-state--derived--effect)
- [Load 函数（Server vs Client）](#load-函数server-vs-client)
- [Form Actions](#form-actions)
- [Store 迁移（→ $state）](#store-迁移)
- [SSR vs CSR 边界](#ssr-vs-csr-边界)
- [响应式语句迁移（$: → Runes）](#响应式语句迁移)
- [性能优化](#性能优化)
- [安全审查](#安全审查)
- [Review Checklist](#review-checklist)

---

## Runes: $state / $derived / $effect

### $state 基础用法

```svelte
<!-- ❌ $state 用于永远不会变化的值 -->
<script lang="ts">
  let config = $state({ timeout: 5000 });  // 不需要响应式
  const API_URL = $state('/api');           // 常量不需要 $state
</script>

<!-- ✅ 常量直接声明 -->
<script lang="ts">
  const config = { timeout: 5000 };
  const API_URL = '/api';

  // $state 只用于会变化的值
  let count = $state(0);
  let user = $state<User | null>(null);
</script>
```

### $state.raw 与大型对象

```svelte
<!-- ❌ 大型不可变数据使用深度响应式 -->
<script lang="ts">
  // largeData 会被深度代理，性能开销大
  let data = $state(hugeApiResponse);
</script>

<!-- ✅ $state.raw 避免深度代理 -->
<script lang="ts">
  let data = $state.raw(hugeApiResponse);

  // 整体替换时才触发更新
  async function refresh() {
    data = await fetchLatestData();  // ✅ triggers reactivity
  }

  // ❌ 修改嵌套属性不会触发更新
  // data.items[0].name = 'new';  // will NOT re-render
</script>
```

### $state.snapshot 用于外部库

```svelte
<!-- ❌ 直接将 $state 对象传给外部库 -->
<script lang="ts">
  let state = $state({ x: 0, y: 0 });

  onMount(() => {
    // 外部库可能无法正确处理 Proxy 对象
    chartLibrary.update(state);  // state is a Proxy!
  });
</script>

<!-- ✅ $state.snapshot 获取普通对象副本 -->
<script lang="ts">
  let state = $state({ x: 0, y: 0 });

  onMount(() => {
    // $state.snapshot produces a plain object (Svelte 5)
    chartLibrary.update($state.snapshot(state));
  });
</script>
```

### 解构 $state 丢失响应性

```svelte
<!-- ❌ 解构 $state 对象丢失响应性 -->
<script lang="ts">
  let state = $state({ count: 0, name: 'Svelte' });
  let { count, name } = state;  // count and name are plain values!
</script>
<p>{count}</p>  <!-- ❌ will NOT update when state.count changes -->

<!-- ✅ 直接访问 $state 属性 -->
<script lang="ts">
  let state = $state({ count: 0, name: 'Svelte' });
</script>
<p>{state.count}</p>  <!-- ✅ stays reactive -->

<!-- ✅ 或者单独声明每个 $state -->
<script lang="ts">
  let count = $state(0);
  let name = $state('Svelte');
</script>
```

---

### $derived 正确用法

```svelte
<!-- ❌ #1 反模式：用 $effect 做状态同步 -->
<script lang="ts">
  let firstName = $state('John');
  let lastName = $state('Doe');
  let fullName = $state('');

  // 不要用 $effect 来同步派生状态！
  $effect(() => {
    fullName = `${firstName} ${lastName}`;  // unnecessary effect
  });
</script>

<!-- ✅ 使用 $derived 计算派生值 -->
<script lang="ts">
  let firstName = $state('John');
  let lastName = $state('Doe');
  let fullName = $derived(`${firstName} ${lastName}`);
</script>
```

### $derived 中不应有副作用

```svelte
<!-- ❌ $derived 中产生副作用 -->
<script lang="ts">
  let items = $state<Item[]>([]);
  let count = $derived(() => {
    console.log('recalculating');  // side effect!
    analytics.track('count', items.length);  // side effect!
    return items.length;
  });
</script>

<!-- ✅ $derived 只用于纯计算 -->
<script lang="ts">
  let items = $state<Item[]>([]);
  let count = $derived(items.length);

  // side effects go in $effect
  $effect(() => {
    analytics.track('count', count);
  });
</script>
```

---

### $effect 正确用法

#### $effect vs $derived

```svelte
<!-- ❌ $effect 用于同步状态（第一大反模式） -->
<script lang="ts">
  let searchQuery = $state('');
  let results = $state([]);

  $effect(() => {
    results = searchQuery ? items.filter(i => i.name.includes(searchQuery)) : items;
  });
</script>

<!-- ✅ 使用 $derived -->
<script lang="ts">
  let searchQuery = $state('');
  let results = $derived(
    searchQuery ? items.filter(i => i.name.includes(searchQuery)) : items
  );
</script>
```

#### 无限循环

```svelte
<!-- ❌ $effect 中更新自身依赖 → 无限循环 -->
<script lang="ts">
  let count = $state(0);

  $effect(() => {
    console.log(count);
    count++;  // modifying dependency inside effect → infinite loop!
  });
</script>

<!-- ✅ 避免在 $effect 中修改被追踪的状态 -->
<script lang="ts">
  let count = $state(0);
  let log = $state<string[]>([]);

  $effect(() => {
    // read count, write to a different state
    log = [...log, `count is ${count}`];
  });
</script>
```

#### 清理函数

```svelte
<!-- ❌ 缺少清理函数 → 内存泄漏 -->
<script lang="ts">
  let roomId = $state('');

  $effect(() => {
    const ws = new WebSocket(`ws://example.com/${roomId}`);
    ws.onmessage = (e) => {
      messages = [...messages, JSON.parse(e.data)];
    };
    // no cleanup! WebSocket leaks when roomId changes
  });
</script>

<!-- ✅ 返回清理函数 -->
<script lang="ts">
  let roomId = $state('');

  $effect(() => {
    const ws = new WebSocket(`ws://example.com/${roomId}`);
    ws.onmessage = (e) => {
      messages = [...messages, JSON.parse(e.data)];
    };
    return () => ws.close();  // cleanup on re-run
  });
</script>

<!-- ✅ 定时器清理 -->
<script lang="ts">
  $effect(() => {
    const id = setInterval(() => {
      console.log('tick');
    }, 1000);
    return () => clearInterval(id);
  });
</script>
```

#### async $effect 的追踪陷阱

```svelte
<!-- ❌ await 后读取的状态不会被追踪 -->
<script lang="ts">
  let userId = $state('1');
  let preference = $state('dark');

  $effect(async () => {
    const user = await fetchUser(userId);   // userId IS tracked
    const theme = preference;               // NOT tracked (read after await)!
    applyTheme(user, theme);
  });
</script>

<!-- ✅ 在 await 前读取所有依赖 -->
<script lang="ts">
  let userId = $state('1');
  let preference = $state('dark');

  $effect(async () => {
    const currentPref = preference;  // read before await
    const user = await fetchUser(userId);
    applyTheme(user, currentPref);
  });
</script>
```

#### untrack 排除依赖

```svelte
<!-- ❌ 不小心追踪了不必要的依赖 -->
<script lang="ts">
  let data = $state<Data | null>(null);
  let debugMode = $state(false);

  $effect(() => {
    if (debugMode) {  // debugMode becomes a dependency!
      console.log('data changed', data);
    }
  });
</script>

<!-- ✅ untrack 排除不相关的依赖 -->
<script lang="ts">
  import { untrack } from 'svelte';

  let data = $state<Data | null>(null);
  let debugMode = $state(false);

  $effect(() => {
    if (untrack(() => debugMode)) {  // debugMode is NOT tracked
      console.log('data changed', data);
    }
  });
</script>
```

---

## Load 函数（Server vs Client）

### +page.server.js vs +page.js

```typescript
// ❌ 在 +page.js 中访问数据库或 secrets
// src/routes/admin/+page.js
export async function load({ fetch }) {
  // universal load runs on both server and client
  const data = await db.query('SELECT * FROM users');  // db not available in browser!
  return { users: data };
}

// ✅ 服务端逻辑放在 +page.server.js
// src/routes/admin/+page.server.js
import { db } from '$lib/server/db';

export async function load() {
  const users = await db.query('SELECT * FROM users');
  return { users };
}
```

```typescript
// ✅ +page.js 用于客户端也可用的数据（如 fetch 聚合）
// src/routes/dashboard/+page.js
export async function load({ fetch, parent }) {
  const [analytics, notifications] = await Promise.all([
    fetch('/api/analytics').then(r => r.json()),
    fetch('/api/notifications').then(r => r.json())
  ]);
  return { analytics, notifications };
}
```

### await parent() 瀑布流

```typescript
// ❌ 顺序 await parent → 瀑布流
// src/routes/blog/[slug]/+page.js
export async function load({ parent, fetch }) {
  const parentData = await parent();  // wait for parent
  const post = await fetch(`/api/posts/${parentData.blogId}`);
  return { post };
}

// ✅ 尽可能并行，避免不必要的 parent await
// src/routes/blog/[slug]/+page.js
export async function load({ parent, fetch }) {
  // only await parent if you truly need its data
  const post = await fetch('/api/posts/slug');
  return { post };
}

// ✅ 如果确实需要 parent 数据，无法避免瀑布流，但要明确注释
// src/routes/blog/[slug]/+page.js
export async function load({ parent, fetch }) {
  const { blogId } = await parent();  // required: need blogId for post URL
  const post = await fetch(`/api/posts/${blogId}`);
  return { post };
}
```

### 不可序列化的返回值

```typescript
// ❌ 从 server load 返回不可序列化的值
// src/routes/api/+page.server.js
export async function load() {
  return {
    stream: fs.createReadStream('data.csv'),  // not serializable!
    callback: () => console.log('hi'),        // functions not serializable!
    date: new Date(),                         // OK — devalue serializes Date/Map/Set fine
  };
}

// ✅ 只返回可序列化的数据
// src/routes/api/+page.server.js
export async function load() {
  return {
    data: await readFile('data.csv', 'utf-8'),
    timestamp: Date.now(),
  };
}
```

---

## Form Actions

### 使用 POST 处理副作用

```svelte
<!-- ❌ 用 GET/load 函数处理副作用 -->
<script lang="ts">
  import { goto } from '$app/navigation';

  async function deleteUser(id: string) {
    await fetch(`/api/users/${id}`, { method: 'DELETE' });
    goto('/users');  // side effect via client navigation
  }
</script>
<button onclick={() => deleteUser(user.id)}>Delete</button>

<!-- ✅ 使用 form actions -->
```

```typescript
// src/routes/users/+page.server.js
import { fail, redirect } from '@sveltejs/kit';

export const actions = {
  delete: async ({ request, locals }) => {
    const formData = await request.formData();
    const id = formData.get('id');

    if (!id) return fail(400, { message: 'Missing id' });

    await locals.db.users.delete(id);
    throw redirect(303, '/users');
  }
};
```

```svelte
<!-- form with progressive enhancement -->
<script lang="ts">
  import { enhance } from '$app/forms';
</script>

<form method="POST" action="?/delete" use:enhance>
  <input type="hidden" name="id" value={user.id} />
  <button type="submit">Delete</button>
</form>
```

### fail() 中不暴露敏感信息

```typescript
// ❌ fail() 中返回敏感信息
// src/routes/login/+page.server.js
export const actions = {
  default: async ({ request, locals }) => {
    const formData = await request.formData();
    const user = await locals.db.users.findByEmail(formData.get('email'));

    return fail(401, {
      password: formData.get('password'),  // ❌ exposes password in page data!
      hint: user.passwordHint,             // ❌ leaks internal data!
    });
  }
};

// ✅ 只返回安全的错误信息
export const actions = {
  default: async ({ request }) => {
    const formData = await request.formData();
    const email = formData.get('email');

    return fail(401, {
      email,                    // ✅ safe to echo back
      incorrect: true,          // ✅ generic error flag
    });
  }
};
```

### use:enhance 渐进增强

```svelte
<!-- ❌ 表单不使用 use:enhance → 没有 JS 时才用原生行为 -->
<form method="POST" action="?/create">
  <input name="title" />
  <button type="submit">Create</button>
</form>

<!-- ✅ use:enhance 提供 SPA 体验 + progressive enhancement -->
<script lang="ts">
  import { enhance } from '$app/forms';
</script>

<form method="POST" action="?/create" use:enhance={() => {
  return ({ update }) => {
    update({ reset: false });  // customize behavior
  };
}}>
  <input name="title" />
  <button type="submit">Create</button>
</form>

<!-- ✅ 带加载状态 -->
<form
  method="POST"
  action="?/create"
  use:enhance={() => {
    submitting = true;
    return ({ update }) => {
      update();
      submitting = false;
    };
  }}
>
  <button type="submit" disabled={submitting}>
    {submitting ? 'Creating...' : 'Create'}
  </button>
</form>
```

---

## Store 迁移（→ $state）

### writable/readable → $state

```typescript
// ❌ Legacy store pattern (Svelte 4)
// src/lib/stores/user.js
import { writable, derived } from 'svelte/store';

export const user = writable(null);
export const isLoggedIn = derived(user, $user => !!$user);

// usage with $ prefix
// $user = { name: 'John' };

// ✅ Svelte 5: shared state in .svelte.js files
// src/lib/stores/user.svelte.js
let currentUser = $state<User | null>(null);

export function getUser() {
  return currentUser;
}

export function setUser(user: User | null) {
  currentUser = user;
}

export function isLoggedIn() {
  return currentUser !== null;
}
```

### $ 前缀 store 语法是遗留语法

```svelte
<!-- ❌ $ 前缀 store 自动订阅是遗留模式 -->
<script lang="ts">
  import { count } from '$lib/stores/count';
  // $count is legacy syntax in Svelte 5
</script>
<p>{$count}</p>

<!-- ✅ Svelte 5 runes 模式 -->
<script lang="ts">
  import { getCount } from '$lib/stores/count.svelte';

  let count = $derived(getCount());
</script>
<p>{count}</p>

<!-- ✅ 或者直接用 export 的 $state 响应式 getter -->
<script lang="ts">
  // count.svelte.js exports a reactive reference
  import { counter } from '$lib/stores/count.svelte';
</script>
<p>{counter.value}</p>
```

### .svelte.js / .svelte.ts 扩展名

```typescript
// ❌ 在普通 .js 文件中使用 runes → 编译错误
// src/lib/utils.js
let state = $state(0);  // runes only work in .svelte.js files!

// ✅ 使用 .svelte.js 扩展名
// src/lib/utils.svelte.js
let state = $state(0);

export function getState() {
  return state;
}

export function setState(val: number) {
  state = val;
}
```

---

## SSR vs CSR 边界

### ssr=false SPA 模式

```typescript
// ❌ 在根 layout 中禁用 SSR → 全部变成 CSR
// src/routes/+layout.js
export const ssr = false;  // entire app becomes SPA

// ✅ 只在需要的页面禁用 SSR
// src/routes/admin/dashboard/+page.js
export const ssr = false;  // only this page skips SSR

// ✅ 更好的做法：按路由配置
// src/routes/editor/+page.js
export const ssr = false;  // editor needs browser APIs, skip SSR
```

### 浏览器全局变量在 SSR 中

```svelte
<!-- ❌ 在模块顶层访问浏览器 API -->
<script lang="ts">
  const height = window.innerHeight;        // ReferenceError during SSR!
  const prefersDark = matchMedia('(prefers-color-scheme: dark)');  // crash!
</script>

<!-- ✅ 在 onMount 或 browser guard 中访问 -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { browser } from '$app/environment';

  let height = $state(0);

  onMount(() => {
    height = window.innerHeight;
  });

  // or conditional check
  const prefersDark = browser
    ? matchMedia('(prefers-color-scheme: dark)').matches
    : false;
</script>
```

### prerender 与 actions 冲突

```typescript
// ❌ prerender 页面中定义 actions → 编译错误
// src/routes/contact/+page.server.js
export const prerender = true;

export const actions = {
  // Error: prerendered pages cannot have server-side form actions
  default: async ({ request }) => { /* ... */ }
};

// ✅ prerender 页面不使用 server actions
// src/routes/about/+page.server.js
export const prerender = true;
// no actions — static page

// ✅ 需要 actions 的页面不 prerender
// src/routes/contact/+page.server.js
export const actions = {
  default: async ({ request }) => {
    // handle form submission
  }
};
```

---

## 响应式语句迁移

### $: → $derived / $effect

```svelte
<!-- ❌ Svelte 4 响应式语句 -->
<script lang="ts">
  let count = 0;
  let doubled = 0;

  $: doubled = count * 2;              // reactive assignment
  $: if (count > 10) console.log('big');
</script>

<!-- ✅ Svelte 5 runes -->
<script lang="ts">
  let count = $state(0);
  let doubled = $derived(count * 2);   // derived value

  $effect(() => {
    if (count > 10) console.log('big');
  });
</script>
```

### export let → $props()

```svelte
<!-- ❌ Svelte 4 props -->
<script lang="ts">
  export let title: string;
  export let count = 0;
</script>

<!-- ✅ Svelte 5 $props() -->
<script lang="ts">
  let { title, count = 0 }: { title: string; count?: number } = $props();
</script>
```

### on:click → onclick

```svelte
<!-- ❌ Svelte 4 指令式事件 -->
<button on:click={handleClick}>Click</button>
<button on:click={() => count++}>Increment</button>

<!-- ✅ Svelte 5 HTML 属性式事件 -->
<button onclick={handleClick}>Click</button>
<button onclick={() => count++}>Increment</button>
```

### createEventDispatcher → 回调 props

```svelte
<!-- ❌ Svelte 4 事件 dispatch -->
<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  const dispatch = createEventDispatcher();

  function handleDelete() {
    dispatch('delete', { id: 42 });
  }
</script>

<!-- ✅ Svelte 5 回调 props -->
<script lang="ts">
  let { ondelete }: { ondelete?: (e: { id: number }) => void } = $props();

  function handleDelete() {
    ondelete?.({ id: 42 });
  }
</script>

<!-- parent usage -->
<Child ondelete={(e) => removeItem(e.id)} />
```

### slot → @render children()

```svelte
<!-- ❌ Svelte 4 slot -->
<!-- Card.svelte -->
<div class="card">
  <slot />
</div>

<!-- ✅ Svelte 5 snippets -->
<!-- Card.svelte -->
<script lang="ts">
  let { children } = $props();
</script>
<div class="card">
  {@render children()}
</div>

<!-- with named slots → named snippets -->
<!-- Layout.svelte -->
<script lang="ts">
  let { header, children, footer } = $props();
</script>
<div>
  <header>{@render header?.()}</header>
  <main>{@render children()}</main>
  <footer>{@render footer?.()}</footer>
</div>

<!-- parent usage -->
<Layout>
  {#snippet header()}<h1>Title</h1>{/snippet}
  <p>Body content</p>
  {#snippet footer()}<p>Footer</p>{/snippet}
</Layout>
```

### beforeUpdate / afterUpdate → $effect.pre

```svelte
<!-- ❌ Svelte 4 lifecycle hooks -->
<script lang="ts">
  import { beforeUpdate, afterUpdate } from 'svelte';

  let count = 0;

  beforeUpdate(() => {
    console.log('about to update', count);
  });

  afterUpdate(() => {
    console.log('updated', count);
    document.title = `Count: ${count}`;
  });
</script>

<!-- ✅ Svelte 5 $effect and $effect.pre -->
<script lang="ts">
  let count = $state(0);

  // $effect.pre runs before DOM updates (like beforeUpdate)
  $effect.pre(() => {
    console.log('about to update', count);
  });

  // $effect runs after DOM updates (like afterUpdate)
  $effect(() => {
    console.log('updated', count);
    document.title = `Count: ${count}`;
  });
</script>
```

---

## 性能优化

### $state.raw 用于大型不可变数据

```svelte
<!-- ❌ 深度代理大型不可变数据 -->
<script lang="ts">
  let searchResults = $state(largeResultArray);  // deep proxy on every item
</script>

<!-- ✅ $state.raw 避免深度代理 -->
<script lang="ts">
  let searchResults = $state.raw<SearchResult[]>([]);

  async function search(query: string) {
    searchResults = await fetchResults(query);  // whole-array replacement
  }
</script>
```

### Keyed {#each}

```svelte
<!-- ❌ 无 key 的 each → 低效 DOM diff -->
{#each items as item}
  <div>{item.name}</div>
{/each}

<!-- ✅ 带唯一 key 的 each -->
{#each items as item (item.id)}
  <div>{item.name}</div>
{/each}

<!-- ✅ 复合 key -->
{#each items as item (`${item.category}-${item.id}`)}
  <div>{item.name}</div>
{/each}
```

### Streaming 与 load 中的 Promise

```typescript
// ❌ 串行等待所有数据 → 页面阻塞
// src/routes/+page.server.js
export async function load({ params }) {
  const posts = await getPosts();       // slow
  const comments = await getComments(); // slow
  const tags = await getTags();         // slow
  return { posts, comments, tags };
}

// ✅ 并行加载独立数据
export async function load({ params }) {
  return {
    posts: getPosts(),       // return promises directly for streaming
    comments: getComments(),
    tags: getTags(),
  };
}
```

```svelte
<!-- streaming in template with {#await} -->
{#await data.posts}
  <p>Loading posts...</p>
{:then posts}
  <ul>
    {#each posts as post (post.id)}
      <li>{post.title}</li>
    {/each}
  </ul>
{:catch error}
  <p>Failed to load posts: {error.message}</p>
{/await}
```

---

## 安全审查

Svelte/SvelteKit 默认自动转义模板表达式。审查重点：`{@html}` 的使用、`$env/static/private` 泄露、CSRF 内建防护。

> **跨框架 XSS 防护详见 [XSS Prevention Guide](cross-cutting/xss-prevention.md)**，含 React/Vue/Angular/Svelte 示例及 CSP 配置。

### 不暴露私有环境变量

```typescript
// ❌ 在 universal load 中暴露服务端 secrets
// src/routes/admin/+page.js (universal — runs on client too!)
export async function load() {
  return {
    apiKey: process.env.SECRET_API_KEY,    // exposed to client bundle!
    dbUrl: import.meta.env.DATABASE_URL,    // leaks to browser!
  };
}

// ✅ 私有环境变量只在 server load 中使用
// src/routes/admin/+page.server.js (server-only)
export async function load({ locals }) {
  // secrets stay on server
  const data = await fetch(process.env.SECRET_API_KEY + '/admin');
  return { data };  // only derived data is sent to client
}

// ✅ 公开变量使用 PUBLIC_ 前缀
// .env
// PUBLIC_API_URL=https://api.example.com
// SECRET_API_KEY=xxx  (no PUBLIC_ prefix = server-only)
```

### $lib/server/ 服务端隔离

```typescript
// ❌ 服务端代码放在可被客户端导入的位置
// src/lib/db.js
import { SECRET_DB_URL } from '$env/static/private';
// any client component importing this gets the secret!

// ✅ 放在 $lib/server/ 目录 → 客户端导入会编译报错
// src/lib/server/db.js
import { SECRET_DB_URL } from '$env/static/private';

export async function query(sql: string) {
  // safe: client cannot import from $lib/server/
}

// usage in server files only
// src/routes/api/users/+server.js
import { query } from '$lib/server/db';
```

### CSRF 内建防护

```typescript
// ✅ SvelteKit 内建 CSRF 防护
// Origin header is checked automatically for POST/PUT/DELETE/PATCH
// No additional CSRF tokens needed for form actions

// ❌ 不要禁用 CSRF 检查（除非有充分理由）
// src/hooks.server.js
export const handle = sequence(
  // do NOT do this without understanding the implications
  // ({ event, resolve }) => resolve(event, { filterSerializedResponseHeaders: () => true })
);
```

### Cookie 安全设置

```typescript
// ❌ 不安全的 Cookie 设置
// src/hooks.server.js
export async function handle({ event, resolve }) {
  const token = event.cookies.get('session');
  // cookie without httpOnly, secure, sameSite flags
  event.cookies.set('session', token, {
    path: '/',
    // missing: httpOnly, secure, sameSite
  });
}

// ✅ 安全的 Cookie 配置
import { dev } from '$app/environment';

event.cookies.set('session', token, {
  path: '/',
  httpOnly: true,          // not accessible via JS
  secure: !dev,            // HTTPS only in production
  sameSite: 'lax',         // CSRF protection
  maxAge: 60 * 60 * 24 * 7 // 1 week, explicit expiry
});
```

---

## Review Checklist

### Runes: $state / $derived / $effect

- [ ] $state 只用于会变化的值，常量直接声明
- [ ] 大型不可变数据使用 $state.raw
- [ ] 没有解构 $state 对象（会丢失响应性）
- [ ] 外部库使用 $state.snapshot 传入普通对象
- [ ] $derived 中没有副作用
- [ ] 没有用 $effect 替代 $derived 做状态同步
- [ ] $effect 中不修改被追踪的状态（避免无限循环）
- [ ] $effect 有清理函数（订阅、定时器、WebSocket）
- [ ] async $effect 在 await 前读取所有需要追踪的状态
- [ ] 使用 untrack 排除不相关的依赖

### Load 函数

- [ ] 服务端逻辑放在 +page.server.js（不是 +page.js）
- [ ] 避免不必要的 await parent() 瀑布流
- [ ] 独立数据并行加载（Promise.all 或直接返回 Promise）
- [ ] server load 只返回可序列化的数据

### Form Actions

- [ ] 副作用操作（增删改）使用 form actions + POST
- [ ] fail() 不返回敏感信息（密码、内部数据）
- [ ] 使用 use:enhance 实现渐进增强

### Store 迁移

- [ ] writable/readable → $state 在 .svelte.js 文件中
- [ ] 不在普通 .js 文件中使用 runes
- [ ] 不使用遗留的 $ 前缀 store 语法

### SSR vs CSR 边界

- [ ] 不在根 layout 中全局禁用 SSR
- [ ] 浏览器 API（window、document）在 onMount 或 browser guard 中使用
- [ ] prerender 页面不包含 server actions

### Svelte 4 → 5 迁移

- [ ] $: → $derived / $effect
- [ ] export let → $props()
- [ ] on:click → onclick
- [ ] createEventDispatcher → 回调 props
- [ ] slot → @render children()
- [ ] beforeUpdate/afterUpdate → $effect.pre / $effect

### 性能优化

- [ ] 大型不可变数据使用 $state.raw
- [ ] {#each} 使用唯一 key
- [ ] load 函数返回 Promise 实现流式传输
- [ ] 独立数据并行加载

### 安全审查

- [ ] 私有环境变量只在 server load 中使用
- [ ] 服务端代码放在 $lib/server/ 目录
- [ ] 不禁用内建 CSRF 防护
- [ ] Cookie 设置 httpOnly、secure、sameSite
- [ ] server load 不泄露密钥和内部数据
