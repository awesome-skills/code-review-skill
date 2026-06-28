# Tasks

## 已完成的审查
- Task 1: 张择端审查核心文件 — done
- Task 2: 唐寅审查 reference/ + scripts/ — done

## 第一波（快速见效）✅
- Fix-1: SKILL.md description 补关键词 + README 行数 + CONTRIBUTING.md 补 swift.md — done
- Fix-2: HTML 补 fastapi/common-bugs/best-practices + 行数修正 — done
- Fix-3: HTML 190→220 行数同步 — done
- Review-1: 顾炎武 review — done (no blocking)

## 第二波（结构性改进）✅
- Fix-A: pr-analyzer.py 逻辑修复 + 测试扩充到 40 case — done
- Fix-B: SKILL.md Cross-Cutting 表整合 + 模板增强 + checklist 对齐 — done
- Fix-4: Review-2 发现的 3 个 important 修复 — done
- Review-2: 顾炎武 review — done (no blocking)

## 第三波（指南扩充）— 进行中

### Fix-C1: C + C++ + Qt 扩充
- **Assignee:** 张择端
- **Status:** done
- **Result:** c.md 890行, cpp.md 893行, qt.md 757行 (均 ≥500)
- **Items:**
  - C (285→500+行): 补测试章节、CERT C 安全编码、UB 示例、跨平台可移植性
  - C++ (385→500+行): 补 C++20/23 特性(concepts/modules/ranges)、测试、constexpr
  - Qt (185→500+行): 补测试、QML/Qt Quick、Qt6 迁移、Model/View 架构

### Fix-C2: Angular + TypeScript + security 扩充
- **Assignee:** 唐寅
- **Status:** done
- **Result:** angular 788行, typescript 1015行, security 636行 (均达标)
- **Items:**
  - Angular (419→500+行): 补测试(Jasmine/Karma)、路由守卫、DI 模式、HttpInterceptor
  - TypeScript (553行): 补测试(Vitest/Jest)、模块解析(ESM vs CJS)、TS 4.9+/5.x 特性
  - security-review-guide.md (266→500+行): 为 SQLi/XSS/CSRF/SSRF/IDOR/命令注入 提供跨语言代码示例

### Review-3: Review 第三波
- **Assignee:** 顾炎武
- **Status:** done
- **Result:** 3 blocking (围栏断裂+表格损坏+untracked文件) + 4 important (HTML行数+angular拦截器+guard+satisfies)

### Fix-5: Review-3 blocking/important 修复
- **Assignee:** 张择端 (README/HTML) + 唐寅 (angular/typescript)
- **Status:** done
- **Result:** 全部修复，40/40 tests passed

## 第四波（公共模块抽取）

### Fix-D: 跨语言重复内容抽取
- **Status:** done
- **Result:** 5 cross-cutting 模块 (1914行), 15+ 指南添加引用链接
- **Items:**
  - #14 抽取 N+1 查询、SQL 注入、XSS、错误处理原则、异步模式为公共模块
  - 语言指南中改为引用公共模块

### Review-4: 最终 review
- **Assignee:** 顾炎武
- **Status:** dispatched
