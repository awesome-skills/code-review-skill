# Vue 3 Code Review Guide

> Vue 3 Composition API 代码审查指南，覆盖响应性系统、Props/Emits、Watchers、Composables 等核心主题。

---

## 响应性系统

### 解构 reactive 对象

```vue
<!-- ❌ 解构 reactive 会丢失响应性 -->
<script setup lang="ts">
const state = reactive({ count: 0, name: 'Vue' })
const { count, name } = state  // 丢失响应性！
</script>

<!-- ✅ 使用 toRefs 保持响应性 -->
<script setup lang="ts">
const state = reactive({ count: 0, name: 'Vue' })
const { count, name } = toRefs(state)  // 保持响应性
// 或者直接使用 ref
const count = ref(0)
const name = ref('Vue')
</script>
```

### computed 副作用

```vue
<!-- ❌ computed 中产生副作用 -->
<script setup lang="ts">
const fullName = computed(() => {
  console.log('Computing...')  // 副作用！
  otherRef.value = 'changed'   // 修改其他状态！
  return `${firstName.value} ${lastName.value}`
})
</script>

<!-- ✅ computed 只用于派生状态 -->
<script setup lang="ts">
const fullName = computed(() => {
  return `${firstName.value} ${lastName.value}`
})
// 副作用放在 watch 或事件处理中
watch(fullName, (name) => {
  console.log('Name changed:', name)
})
</script>
```

---

## Props & Emits

### 直接修改 props

```vue
<!-- ❌ 直接修改 props -->
<script setup lang="ts">
const props = defineProps<{ user: User }>()
props.user.name = 'New Name'  // 永远不要直接修改 props！
</script>

<!-- ✅ 使用 emit 通知父组件更新 -->
<script setup lang="ts">
const props = defineProps<{ user: User }>()
const emit = defineEmits<{
  update: [name: string]
}>()
const updateName = (name: string) => emit('update', name)
</script>
```

### defineProps 类型声明

```vue
<!-- ❌ defineProps 缺少类型声明 -->
<script setup lang="ts">
const props = defineProps(['title', 'count'])  // 无类型检查
</script>

<!-- ✅ 使用类型声明 + withDefaults -->
<script setup lang="ts">
interface Props {
  title: string
  count?: number
  items?: string[]
}
const props = withDefaults(defineProps<Props>(), {
  count: 0,
  items: () => []  // 对象/数组默认值需要工厂函数
})
</script>
```

---

## Watchers

### watch 清理函数

```vue
<!-- ❌ watch 缺少清理函数，可能内存泄漏 -->
<script setup lang="ts">
watch(searchQuery, async (query) => {
  const controller = new AbortController()
  const data = await fetch(`/api/search?q=${query}`, {
    signal: controller.signal
  })
  results.value = await data.json()
  // 如果 query 快速变化，旧请求不会被取消！
})
</script>

<!-- ✅ 使用 onCleanup 清理副作用 -->
<script setup lang="ts">
watch(searchQuery, async (query, _, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())  // 取消旧请求

  try {
    const data = await fetch(`/api/search?q=${query}`, {
      signal: controller.signal
    })
    results.value = await data.json()
  } catch (e) {
    if (e.name !== 'AbortError') throw e
  }
})
</script>
```

---

## 模板最佳实践

### v-for 的 key

```vue
<!-- ❌ v-for 中使用 index 作为 key -->
<template>
  <li v-for="(item, index) in items" :key="index">
    {{ item.name }}
  </li>
</template>

<!-- ✅ 使用唯一标识作为 key -->
<template>
  <li v-for="item in items" :key="item.id">
    {{ item.name }}
  </li>
</template>
```

### v-if 和 v-for 优先级

```vue
<!-- ❌ v-if 和 v-for 同时使用 -->
<template>
  <li v-for="user in users" v-if="user.active" :key="user.id">
    {{ user.name }}
  </li>
</template>

<!-- ✅ 使用 computed 过滤 -->
<script setup lang="ts">
const activeUsers = computed(() =>
  users.value.filter(user => user.active)
)
</script>
<template>
  <li v-for="user in activeUsers" :key="user.id">
    {{ user.name }}
  </li>
</template>
```

---

## Composables

### Props 传递给 composable

```vue
<!-- ❌ 传递 props 到 composable 丢失响应性 -->
<script setup lang="ts">
const props = defineProps<{ userId: string }>()
const { user } = useUser(props.userId)  // 丢失响应性！
</script>

<!-- ✅ 使用 toRef 或 computed 保持响应性 -->
<script setup lang="ts">
const props = defineProps<{ userId: string }>()
const userIdRef = toRef(props, 'userId')
const { user } = useUser(userIdRef)  // 保持响应性
// 或使用 computed
const { user } = useUser(computed(() => props.userId))
</script>
```

---

## Vue 3 Review Checklist

### 响应性系统
- [ ] ref 用于基本类型，reactive 用于对象
- [ ] 没有解构 reactive 对象（或使用了 toRefs）
- [ ] props 传递给 composable 时保持了响应性
- [ ] shallowRef/shallowReactive 用于大型对象优化

### Props & Emits
- [ ] defineProps 使用 TypeScript 类型声明
- [ ] 复杂默认值使用 withDefaults + 工厂函数
- [ ] defineEmits 有完整的类型定义
- [ ] 没有直接修改 props

### Watchers
- [ ] watch/watchEffect 有适当的清理函数
- [ ] 异步 watch 处理了竞态条件
- [ ] flush: 'post' 用于 DOM 操作的 watcher
- [ ] 避免过度使用 watcher（优先用 computed）

### 模板
- [ ] v-for 使用唯一且稳定的 key
- [ ] v-if 和 v-for 没有在同一元素上
- [ ] 事件处理使用 kebab-case
- [ ] 大型列表使用虚拟滚动

### Composables
- [ ] 相关逻辑提取到 composables
- [ ] composables 返回响应式引用（不是 .value）
- [ ] 纯函数不要包装成 composable
- [ ] 副作用在组件卸载时清理

### 性能
- [ ] 大型组件拆分为小组件
- [ ] 使用 defineAsyncComponent 懒加载
- [ ] 避免不必要的响应式转换
- [ ] v-memo 用于昂贵的列表渲染
