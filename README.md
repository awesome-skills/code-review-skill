# Code Review Excellence

[English](#english) | [中文](#中文)

---

## English

> A modular code review skill for Claude Code, covering React 19, Vue 3, Rust, TypeScript, Java, Python, CSS/Less/Sass, architecture design, and performance optimization.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### Overview

This is a Claude Code skill designed to help developers conduct effective code reviews. It provides:

- **Language-specific patterns** for React 19, Vue 3, Rust, TypeScript/JavaScript, Java, Python
- **Modern framework support** including React Server Components, TanStack Query v5, Suspense & Streaming
- **Comprehensive checklists** for security, performance, and code quality
- **Best practices** for giving constructive feedback
- **Modular structure** for on-demand loading (reduces context usage)

### Features

#### Supported Languages & Frameworks

| Category | Coverage |
|----------|----------|
| **React** | Hooks rules, useEffect patterns, useMemo/useCallback, React 19 Actions (useActionState, useFormStatus, useOptimistic), Server Components, Suspense & Streaming |
| **Vue 3** | Composition API, reactivity system, defineProps/defineEmits, watch cleanup |
| **Rust** | Ownership & borrowing, unsafe code review, async/await, error handling (thiserror vs anyhow) |
| **TypeScript** | Type safety, async/await patterns, common pitfalls |
| **Java** | Java 17/21 features (Records, Switch), Spring Boot 3, Virtual Threads, Stream API best practices |
| **Go** | Error handling, goroutines/channels, context propagation, interface design, testing patterns |
| **CSS/Less/Sass** | CSS variables, !important usage, performance optimization, responsive design, browser compatibility |
| **TanStack Query** | v5 best practices, queryOptions, useSuspenseQuery, optimistic updates |
| **Architecture** | SOLID principles, anti-patterns, coupling/cohesion, layered architecture |
| **Performance** | Core Web Vitals, N+1 queries, memory leaks, algorithm complexity |

#### Content Statistics

| File | Lines | Description |
|------|-------|-------------|
| **SKILL.md** | ~190 | Core principles + index (loads on skill activation) |
| **reference/react.md** | ~870 | React 19/Next.js/TanStack Query v5 patterns (on-demand) |
| **reference/vue.md** | ~920 | Vue 3.5 patterns + Composition API (on-demand) |
| **reference/rust.md** | ~840 | Rust async/ownership/cancellation safety (on-demand) |
| **reference/typescript.md** | ~540 | TypeScript generics/strict mode/ESLint (on-demand) |
| **reference/java.md** | ~800 | Java 17/21 & Spring Boot 3 patterns (on-demand) |
| **reference/python.md** | ~1070 | Python async/typing/pytest (on-demand) |
| **reference/go.md** | ~990 | Go goroutines/channels/context/interfaces (on-demand) |
| **reference/css-less-sass.md** | ~660 | CSS/Less/Sass variables/performance/responsive (on-demand) |
| **reference/architecture-review-guide.md** | ~470 | SOLID/anti-patterns/coupling analysis (on-demand) |
| **reference/performance-review-guide.md** | ~750 | Core Web Vitals/N+1/memory/complexity (on-demand) |

**Total: ~9,000 lines** of review guidelines and code examples, loaded on-demand per language.

### Installation

#### For Claude Code Users

Copy the skill to your Claude Code skills directory:

```bash
# Clone the repository
git clone https://github.com/tt-a1i/code-review-skill.git

# Copy to Claude Code skills directory
cp -r code-review-skill ~/.claude/skills/code-review-excellence
```

Or add to your existing Claude Code plugin:

```bash
# Copy the entire directory structure
cp -r code-review-skill ~/.claude/plugins/your-plugin/skills/code-review/
```

### Usage

Once installed, you can invoke the skill in Claude Code:

```
Use code-review-excellence skill to review this PR
```

Or reference it in your custom commands.

### File Structure

```
code-review-skill/
├── SKILL.md                        # Core skill (loads immediately)
├── README.md                       # This file
├── LICENSE                         # MIT License
├── CONTRIBUTING.md                 # Contribution guidelines
├── reference/                      # On-demand loaded guides
│   ├── react.md                    # React/Next.js patterns (on-demand)
│   ├── vue.md                      # Vue 3 patterns (on-demand)
│   ├── rust.md                     # Rust patterns (on-demand)
│   ├── typescript.md               # TypeScript/JS patterns (on-demand)
│   ├── java.md                     # Java patterns (on-demand)
│   ├── python.md                   # Python patterns (on-demand)
│   ├── go.md                       # Go patterns (on-demand)
│   ├── css-less-sass.md            # CSS/Less/Sass patterns (on-demand)
│   ├── architecture-review-guide.md # Architecture design review (on-demand)
│   ├── performance-review-guide.md # Performance review (on-demand)
│   ├── common-bugs-checklist.md    # Language-specific bug patterns
│   ├── security-review-guide.md    # Security review checklist
│   └── code-review-best-practices.md
├── assets/
│   ├── review-checklist.md         # Quick reference checklist
│   └── pr-review-template.md       # PR review comment template
└── scripts/
    └── pr-analyzer.py              # PR complexity analyzer
```

### On-Demand Loading

This skill uses **Progressive Disclosure** to minimize context usage:

1. **SKILL.md** (~180 lines) loads when the skill is activated
2. **Language-specific files** load only when reviewing that language
3. **Reference files** load only when explicitly needed

This means reviewing a React PR only loads SKILL.md + react.md, not Vue/Rust/Python content.

### Key Topics Covered

#### Java & Spring Boot

- **Java 17/21 Features**: Records, Pattern Matching for Switch, Text Blocks
- **Virtual Threads**: High-throughput I/O with Project Loom
- **Spring Boot 3**: Constructor Injection, `@ConfigurationProperties`, ProblemDetail
- **JPA Performance**: Solving N+1 problems, correct Entity design (equals/hashCode)

#### React 19

- `useActionState` - Unified form state management
- `useFormStatus` - Access parent form status without prop drilling
- `useOptimistic` - Optimistic UI updates with automatic rollback
- Server Actions integration with Next.js 15+

#### Suspense & Streaming SSR

- Suspense boundary design patterns
- Error Boundary integration
- Next.js 15 streaming with `loading.tsx`
- `use()` Hook for Promise consumption

#### TanStack Query v5

- `queryOptions` for type-safe query definitions
- `useSuspenseQuery` best practices
- Optimistic updates (simplified v5 approach)
- `isPending` vs `isLoading` vs `isFetching`

#### Rust

- Ownership patterns and common pitfalls
- `unsafe` code review requirements (SAFETY comments)
- Async/await patterns (avoiding blocking in async context)
- Error handling (thiserror for libraries, anyhow for applications)

### Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

#### Areas for Contribution

- Additional language support (Java, C++, Swift, etc.)
- More framework-specific patterns
- Translations to other languages
- Bug pattern submissions

### License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### References

- [React v19 Official Documentation](https://react.dev/blog/2024/12/05/react-19)
- [TanStack Query v5 Documentation](https://tanstack.com/query/latest)
- [Vue 3 Composition API](https://vuejs.org/guide/extras/composition-api-faq.html)
- [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/)

---

## 中文

> 一个模块化的 Claude Code 代码审查技能，覆盖 React 19、Vue 3、Rust、TypeScript、Java、Python、CSS/Less/Sass、架构设计和性能优化。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### 概述

这是一个为 Claude Code 设计的代码审查技能，旨在帮助开发者进行高效的代码审查。它提供：

- **语言特定模式**：覆盖 React 19、Vue 3、Rust、TypeScript/JavaScript、Java、Python
- **现代框架支持**：包括 React Server Components、TanStack Query v5、Suspense & Streaming
- **全面的检查清单**：安全、性能和代码质量检查
- **最佳实践**：如何提供建设性的反馈
- **模块化结构**：按需加载，减少上下文占用

### 特性

#### 支持的语言和框架

| 分类 | 覆盖内容 |
|------|----------|
| **React** | Hooks 规则、useEffect 模式、useMemo/useCallback、React 19 Actions（useActionState、useFormStatus、useOptimistic）、Server Components、Suspense & Streaming |
| **Vue 3** | Composition API、响应性系统、defineProps/defineEmits、watch 清理 |
| **Rust** | 所有权与借用、unsafe 代码审查、async/await、错误处理（thiserror vs anyhow） |
| **TypeScript** | 类型安全、async/await 模式、常见陷阱 |
| **Java** | Java 17/21 特性（Records, Switch）、Spring Boot 3、虚拟线程、Stream API 最佳实践 |
| **Go** | 错误处理、goroutine/channel、context 传播、接口设计、测试模式 |
| **CSS/Less/Sass** | CSS 变量规范、!important 使用、性能优化、响应式设计、浏览器兼容性 |
| **TanStack Query** | v5 最佳实践、queryOptions、useSuspenseQuery、乐观更新 |
| **架构设计** | SOLID 原则、架构反模式、耦合度/内聚性、分层架构 |
| **性能优化** | Core Web Vitals、N+1 查询、内存泄漏、算法复杂度 |

#### 内容统计

| 文件 | 行数 | 描述 |
|------|------|------|
| **SKILL.md** | ~190 | 核心原则 + 索引（技能激活时加载）|
| **reference/react.md** | ~870 | React 19/Next.js/TanStack Query v5（按需加载）|
| **reference/vue.md** | ~920 | Vue 3.5 + Composition API（按需加载）|
| **reference/rust.md** | ~840 | Rust async/所有权/取消安全性（按需加载）|
| **reference/typescript.md** | ~540 | TypeScript 泛型/strict 模式/ESLint（按需加载）|
| **reference/java.md** | ~800 | Java 17/21 & Spring Boot 3 模式（按需加载）|
| **reference/python.md** | ~1070 | Python async/类型注解/pytest（按需加载）|
| **reference/go.md** | ~990 | Go goroutine/channel/context/接口（按需加载）|
| **reference/css-less-sass.md** | ~660 | CSS/Less/Sass 变量/性能/响应式（按需加载）|
| **reference/architecture-review-guide.md** | ~470 | SOLID/反模式/耦合度分析（按需加载）|
| **reference/performance-review-guide.md** | ~750 | Core Web Vitals/N+1/内存/复杂度（按需加载）|

**总计：9,000 行**审查指南和代码示例，按语言按需加载。

### 安装

#### Claude Code 用户

将技能复制到 Claude Code skills 目录：

```bash
# 克隆仓库
git clone https://github.com/tt-a1i/code-review-skill.git

# 复制到 Claude Code skills 目录
cp -r code-review-skill ~/.claude/skills/code-review-excellence
```

或添加到现有的 Claude Code 插件：

```bash
# 复制整个目录结构
cp -r code-review-skill ~/.claude/plugins/your-plugin/skills/code-review/
```

### 使用方法

安装后，可以在 Claude Code 中调用该技能：

```
使用 code-review-excellence skill 来审查这个 PR
```

或在自定义命令中引用。

### 文件结构

```
code-review-skill/
├── SKILL.md                        # 核心技能（立即加载）
├── README.md                       # 本文件
├── LICENSE                         # MIT 许可证
├── CONTRIBUTING.md                 # 贡献指南
├── reference/                      # 按需加载的指南
│   ├── react.md                    # React/Next.js 模式（按需加载）
│   ├── vue.md                      # Vue 3 模式（按需加载）
│   ├── rust.md                     # Rust 模式（按需加载）
│   ├── typescript.md               # TypeScript/JS 模式（按需加载）
│   ├── java.md                     # Java 模式（按需加载）
│   ├── python.md                   # Python 模式（按需加载）
│   ├── go.md                       # Go 模式（按需加载）
│   ├── css-less-sass.md            # CSS/Less/Sass 模式（按需加载）
│   ├── architecture-review-guide.md # 架构设计审查（按需加载）
│   ├── performance-review-guide.md # 性能审查（按需加载）
│   ├── common-bugs-checklist.md    # 语言特定的错误模式
│   ├── security-review-guide.md    # 安全审查清单
│   └── code-review-best-practices.md
├── assets/
│   ├── review-checklist.md         # 快速参考清单
│   └── pr-review-template.md       # PR 审查评论模板
└── scripts/
    └── pr-analyzer.py              # PR 复杂度分析器
```

### 按需加载机制

此技能使用 **Progressive Disclosure（渐进式披露）** 来最小化上下文占用：

1. **SKILL.md**（~180 行）在技能激活时加载
2. **语言特定文件** 仅在审查该语言时加载
3. **参考文件** 仅在明确需要时加载

这意味着审查 React PR 时只加载 SKILL.md + react.md，不会加载 Vue/Rust/Python 内容。

### 核心内容

#### Java & Spring Boot

- **Java 17/21 特性**：Records、Switch 模式匹配、文本块
- **虚拟线程**：Project Loom 带来的高吞吐量 I/O
- **Spring Boot 3**：构造器注入、`@ConfigurationProperties`、ProblemDetail
- **JPA 性能**：解决 N+1 问题、正确的 Entity 设计（equals/hashCode）

#### React 19

- `useActionState` - 统一的表单状态管理
- `useFormStatus` - 无需 props 透传即可访问父表单状态
- `useOptimistic` - 带自动回滚的乐观 UI 更新
- 与 Next.js 15+ Server Actions 集成

#### Suspense & Streaming SSR

- Suspense 边界设计模式
- Error Boundary 集成
- Next.js 15 streaming 与 `loading.tsx`
- `use()` Hook 消费 Promise

#### TanStack Query v5

- `queryOptions` 类型安全的查询定义
- `useSuspenseQuery` 最佳实践
- 乐观更新（v5 简化方案）
- `isPending` vs `isLoading` vs `isFetching` 区别

#### Rust

- 所有权模式和常见陷阱
- `unsafe` 代码审查要求（SAFETY 注释）
- Async/await 模式（避免在异步上下文中阻塞）
- 错误处理（库用 thiserror，应用用 anyhow）

### 贡献

欢迎贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解贡献指南。

#### 可贡献的方向

- 添加更多语言支持（Java、C++、Swift 等）
- 更多框架特定模式
- 翻译成其他语言
- 提交错误模式

### 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

### 参考资料

- [React v19 官方文档](https://react.dev/blog/2024/12/05/react-19)
- [TanStack Query v5 文档](https://tanstack.com/query/latest)
- [Vue 3 Composition API](https://vuejs.org/guide/extras/composition-api-faq.html)
- [Rust API 指南](https://rust-lang.github.io/api-guidelines/)
