# Common Bugs Checklist

Quick-reference bug patterns organized by category. For detailed code examples, explanations, and comprehensive review checklists, see the dedicated language guides linked below.

## Universal Issues

### Logic Errors
- [ ] Off-by-one errors in loops and array access
- [ ] Incorrect boolean logic (De Morgan's law violations)
- [ ] Missing null/undefined checks
- [ ] Race conditions in concurrent code
- [ ] Incorrect comparison operators (`==` vs `===`, `=` vs `==`)
- [ ] Integer overflow/underflow
- [ ] Floating point comparison issues

### Resource Management
- [ ] Memory leaks (unclosed connections, listeners)
- [ ] File handles not closed
- [ ] Database connections not released
- [ ] Event listeners not removed
- [ ] Timers/intervals not cleared

### Error Handling
- [ ] Swallowed exceptions (empty catch blocks)
- [ ] Generic exception handling hiding specific errors
- [ ] Missing error propagation
- [ ] Incorrect error types thrown
- [ ] Missing finally/cleanup blocks

## TypeScript/JavaScript

- [ ] `==` instead of `===`
- [ ] Using `any` — prefer proper types or `unknown` with type guards
- [ ] Missing `await` on async calls
- [ ] Unhandled promise rejections (no try-catch around await)
- [ ] `this` context lost in callbacks
- [ ] Missing `key` prop in lists
- [ ] Closure capturing stale loop variable
- [ ] `parseInt` without radix parameter
- [ ] Modifying array/object during iteration

**Full guide:** [TypeScript Review Guide](typescript.md)

## React / React 19

- [ ] Hooks called conditionally or in loops (violates Rules of Hooks)
- [ ] `useEffect` dependency array incomplete or incorrect
- [ ] `useEffect` missing cleanup function (subscriptions, timers, fetches)
- [ ] `useEffect` used for derived state (use `useMemo` instead)
- [ ] `useMemo`/`useCallback` over-used or used without `React.memo`
- [ ] Component defined inside another component (re-mounts every render)
- [ ] Unstable props (inline objects/functions passed to memo components)
- [ ] Direct mutation of props
- [ ] List missing `key` or using array index as key (reorderable lists)
- [ ] Server Component using client APIs (`useState`, `useEffect`, `onClick`)
- [ ] `'use client'` on parent making entire subtree client-side
- [ ] `useActionState` calling `setState` instead of returning new state
- [ ] `useFormStatus` called in same component as `<form>` (must be in child)
- [ ] `useOptimistic` used for critical operations (payments, deletions)
- [ ] Single Suspense boundary for entire page (slow blocks fast)
- [ ] Missing Error Boundary wrapping Suspense
- [ ] `use()` Hook receiving a new Promise each render

**TanStack Query v5:**
- [ ] `queryKey` missing parameters that affect data
- [ ] Default `staleTime: 0` causing excessive refetches
- [ ] `useSuspenseQuery` with `enabled` option (not supported)
- [ ] Mutation not invalidating related queries on success
- [ ] Optimistic update missing rollback in `onError`
- [ ] Using v4 array syntax (`useQuery(['key'], fn)`) instead of v5 object syntax

**Testing:**
- [ ] Using `container.querySelector` instead of `screen.getByRole`
- [ ] Using `fireEvent` instead of `userEvent`
- [ ] Testing implementation details instead of user-visible behavior
- [ ] Using `getBy*` for async content (use `findBy*`)

**Full guide:** [React Review Guide](react.md)

## Vue 3

- [ ] Destructuring `reactive()` object loses reactivity (use `toRefs`)
- [ ] Passing `props.x` to composable instead of `() => props.x` or `toRef(props, 'x')`
- [ ] `watch` with async callback missing `onCleanup` (race condition)
- [ ] `computed` with side effects (mutations, API calls)
- [ ] `v-for` using index as `:key` when list can reorder
- [ ] `v-if` and `v-for` on the same element
- [ ] `defineProps` without TypeScript type declaration
- [ ] `withDefaults` object default values not using factory functions
- [ ] Directly mutating props instead of emitting events
- [ ] `watchEffect` with unclear dependencies causing over-triggering

**Full guide:** [Vue 3 Review Guide](vue.md)

## Python

- [ ] Mutable default arguments (`def f(x=[])`)
- [ ] Bare `except:` catching `KeyboardInterrupt` and `SystemExit`
- [ ] Shared mutable class attributes (`class C: items = []`)
- [ ] Using `is` instead of `==` for value comparison
- [ ] Forgetting `self` parameter in methods
- [ ] Modifying list while iterating
- [ ] String concatenation in loops (use `"".join()`)
- [ ] Not closing files (use `with` statement)
- [ ] Missing type annotations on public functions

**Full guide:** [Python Review Guide](python.md)

## Rust

**Ownership & Borrowing:**
- [ ] Unnecessary `clone()` to work around borrow checker
- [ ] `Arc<Mutex<T>>` when single-owner would suffice
- [ ] Storing borrows in structs when owned data is simpler
- [ ] Unnecessary `RefCell` (runtime checks vs compile-time)

**Unsafe Code:**
- [ ] `unsafe` block without `SAFETY:` comment explaining invariants
- [ ] `unsafe fn` without `# Safety` doc section
- [ ] Unsafe invariants split across modules

**Async & Concurrency:**
- [ ] Blocking in async context (`std::fs`, `std::thread::sleep`)
- [ ] Holding `std::sync::Mutex` across `.await`
- [ ] Spawned task missing `'static` lifetime bound
- [ ] Dropping a Future without awaiting (forgotten work)

**Error Handling:**
- [ ] `unwrap()`/`expect()` in production code
- [ ] Library using `anyhow` instead of `thiserror` (callers can't match)
- [ ] Swallowing error context (`map_err(|_| ...)`)
- [ ] Ignoring `must_use` return values

**Performance:**
- [ ] Unnecessary `.collect()` — prefer lazy iterators
- [ ] String concatenation in loops without `with_capacity`
- [ ] `Box<dyn Trait>` when `impl Trait` would work

**Full guide:** [Rust Review Guide](rust.md)

## Go

- [ ] Ignoring errors (`result, _ := SomeFunction()`)
- [ ] Goroutine with no exit mechanism (leak)
- [ ] Missing or incorrect `context.Context` propagation
- [ ] Loop variable capture issue (Go < 1.22)
- [ ] `defer` in loops (deferred until function, not loop iteration)
- [ ] Variable shadowing
- [ ] Map used before initialization
- [ ] Error wrapping with `%v` instead of `%w` (breaks `errors.Is`/`errors.As`)

**Full guide:** [Go Review Guide](go.md)

## Java / Spring Boot

- [ ] POJO/DTO with manual boilerplate instead of `record` *(Java 17+)*
- [ ] Traditional switch missing `break` (use switch expressions) *(Java 14+)*
- [ ] Field injection instead of constructor injection
- [ ] JPA N+1 query (missing `fetch join` or `@EntityGraph`)
- [ ] Incorrect `equals`/`hashCode` on JPA entities (avoid `@Data`; prefer stable business key or null-safe id — never all lazy fields)
- [ ] `Optional.get()` without `isPresent()` check
- [ ] Stream operations with side effects

**Full guide:** [Java Review Guide](java.md) (17/21 + Boot 3)

## Java 8 / Spring Boot 2 (Legacy)

- [ ] Shared `SimpleDateFormat` / legacy `Date` instead of `java.time`
- [ ] `Collectors.toMap` with null values or missing merge function
- [ ] `Optional` used as field/parameter, or `isPresent()`+`get()` as null-check
- [ ] `CompletableFuture.supplyAsync` I/O on `commonPool` (no explicit executor)
- [ ] `RestTemplate` without connect/read timeouts
- [ ] `@Transactional` on private method or same-class self-invocation
- [ ] `parallelStream` with shared mutable state
- [ ] Mixing `javax.*` and `jakarta.*` on Boot 2

**Full guide:** [Java 8 Review Guide](java8.md)

## PHP

- [ ] Missing `declare(strict_types=1);` in new files
- [ ] Weak comparison (`==`, `!=`) in auth, token, payment, or state logic
- [ ] `in_array()` / `array_search()` used without strict mode
- [ ] SQL built with string concatenation instead of prepared statements
- [ ] User input echoed without context-aware escaping
- [ ] Passwords stored with `md5()` / `sha1()` instead of `password_hash()`
- [ ] Untrusted data passed to `unserialize()`
- [ ] PHP 8.2+ dynamic properties used instead of declared properties
- [ ] Errors hidden with `@` or swallowed in empty `catch` blocks
- [ ] File uploads using client-provided names or missing MIME/size validation

**Full guide:** [PHP Review Guide](php.md)

## Ruby / Rails

- [ ] Condition assumes `0`, `""`, or `[]` is falsey
- [ ] Mutable Hash/Array default shared across entries (`Hash.new([])`, `Array.new(3, [])`)
- [ ] Bang method return value treated as the transformed object
- [ ] Bare or broad `rescue` hides unrelated failures or exposes `error.message`
- [ ] Dynamic `send`, `constantize`, `eval`, or SQL fragment controlled by user input
- [ ] Untrusted data passed to `Marshal.load`, unsafe YAML loading, or an interpolated shell command
- [ ] Strong parameters use `permit!`, `to_unsafe_h`, or an empty hash allowlist
- [ ] Nested `params.expect` arrays use a flat shape instead of the required `[[...]]` form
- [ ] Active Record query interpolates values or dynamic identifiers into SQL
- [ ] `Model.find(params[:id])` loads a record before ownership or policy scoping (IDOR)
- [ ] `redirect_to` accepts a user-controlled URL with `allow_other_host: true` (open redirect)
- [ ] Browser-authenticated state changes skip CSRF protection or use unsafe session cookie flags
- [ ] Association access in a loop causes N+1 queries
- [ ] Model validation lacks a matching database constraint for a critical invariant
- [ ] `update_all` / `delete_all` unexpectedly skips callbacks and validations
- [ ] Bulk writes can drift a `counter_cache` without reconciliation
- [ ] Active Job retry can duplicate a payment, email, or other external side effect
- [ ] GlobalID job argument can be deleted before deserialization
- [ ] Transaction contains external side effects that cannot roll back
- [ ] Retried create/payment request can duplicate committed work without an idempotency key

**Full guide:** [Ruby and Rails Review Guide](ruby.md)

## Swift

- [ ] Force-unwrap (`!`) or `try!` where safe unwrapping is possible
- [ ] Closure capturing `self` strongly without `[weak self]` (retain cycle)
- [ ] Reference type (`class`) used where a value type (`struct`) is intended
- [ ] Errors swallowed instead of propagated via `throws` / `Result`
- [ ] Data race across concurrency boundaries (missing `Sendable`, `@MainActor`, actor isolation)
- [ ] Fire-and-forget `Task {}` that is never cancelled or leaks
- [ ] `@ObservedObject` used where `@StateObject` is required for ownership
- [ ] Implicitly unwrapped optional (`var x: T!`) outside IBOutlets
- [ ] Over-broad access control (`public` / `open` where `internal` suffices)

**Full guide:** [Swift Review Guide](swift.md)

## Dart / Flutter

- [ ] Missing `const` on static widget subtrees, or `_buildFoo()` helpers instead of extracted widgets
- [ ] `!` / `as` / unconstrained `late` used to silence null safety
- [ ] Heavy `jsonDecode` / image / crypto work on the UI isolate
- [ ] `Future` or `Stream` created inside `build` (new instance every rebuild)
- [ ] `setState` / `BuildContext` used after `await` without `mounted` / `context.mounted`
- [ ] `ref.watch` / `context.watch` in a callback; `read` used in `build` (or the reverse)
- [ ] `BlocProvider.value` / `ChangeNotifierProvider.value` given a new instance constructed in `build` (use `create`; `value` does not dispose)
- [ ] `BlocProvider(create: ...)` captures a stale `id` — missing `ValueKey(id)` remount or `didUpdateWidget` reload (`UniqueKey()` remounts every rebuild)
- [ ] Platform channel `invokeMethod` without `PlatformException` handling
- [ ] List children holding `State` missing a stable `ValueKey` (or using `UniqueKey()` in `build`)
- [ ] `TextEditingController` / `AnimationController` / `StreamSubscription` not disposed

**Full guide:** [Dart / Flutter Review Guide](dart.md)

## C

- [ ] Pointer/buffer overflow or underflow
- [ ] Undefined behavior (use-after-free, double-free, null deref)
- [ ] Missing error handling after allocation (`malloc` can return `NULL`)
- [ ] Integer overflow in size calculations
- [ ] Resource leaks (missing `free`, `fclose`, etc.)
- [ ] Missing `static` on file-local functions/variables

**Full guide:** [C Review Guide](c.md)

## C++

- [ ] Missing RAII wrapper for resources
- [ ] Violating Rule of 0/3/5 (destructor, copy, move)
- [ ] Exception safety issues (no `noexcept` where applicable)
- [ ] Dangling references from returned iterators or references
- [ ] Unnecessary copies (missing `std::move` or pass-by-reference)

**Full guide:** [C++ Review Guide](cpp.md)

## SQL

- [ ] String concatenation for queries (SQL injection risk) — use parameterized queries
- [ ] Missing indexes on filtered/joined columns
- [ ] `SELECT *` instead of specific columns
- [ ] N+1 query patterns
- [ ] Missing `LIMIT` on large tables
- [ ] Not handling `NULL` comparisons correctly (`IS NULL` vs `= NULL`)
- [ ] Missing transactions for related operations
- [ ] Incorrect JOIN types
- [ ] Collation / case sensitivity surprises across databases (MySQL vs Postgres defaults)
- [ ] Date and timezone handling errors (naive timestamps, server-local `NOW()`, DST)

**See also:** [Security Review Guide](security-review-guide.md) for SQL injection prevention

## API Design

- [ ] Inconsistent resource naming
- [ ] Wrong HTTP methods (POST for idempotent operations)
- [ ] Missing pagination for list endpoints
- [ ] Incorrect status codes
- [ ] Missing rate limiting
- [ ] Missing input validation and sanitization
- [ ] Trusting client-side validation only

## Testing

- [ ] Testing implementation details instead of behavior
- [ ] Missing edge case tests
- [ ] Flaky tests (non-deterministic)
- [ ] Tests with external dependencies (no mocks)
- [ ] Missing negative tests (error cases)
- [ ] Overly complex test setup
