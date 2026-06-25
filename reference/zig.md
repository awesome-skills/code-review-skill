# Zig Code Review Guide

> Code review guidelines for Zig focusing on explicit memory ownership, error unions, defer/errdefer cleanup, comptime usage, safety-checked operations, C interop, and tests.

## Table of Contents

- [Memory & Allocators](#memory--allocators)
- [Errors & Cleanup](#errors--cleanup)
- [Pointers, Slices & Optionals](#pointers-slices--optionals)
- [Comptime & Generics](#comptime--generics)
- [Safety, Undefined Behavior & Casts](#safety-undefined-behavior--casts)
- [C Interop](#c-interop)
- [Testing](#testing)
- [Style & API Design](#style--api-design)
- [Review Checklist](#review-checklist)
- [References](#references)

---

## Memory & Allocators

### Make Allocator Ownership Explicit

Zig code should make allocation policy visible. Libraries should usually accept an `std.mem.Allocator` from the caller rather than creating a global allocator internally.

```zig
const std = @import("std");

// ❌ Bad: hides allocation policy and lifetime from callers.
fn readNamesBad() ![][]const u8 {
    var gpa = std.heap.DebugAllocator(.{}){};
    const allocator = gpa.allocator();
    return try allocator.alloc([]const u8, 10);
}

// ✅ Good: caller chooses allocator and owns the returned memory.
fn readNames(allocator: std.mem.Allocator) ![][]const u8 {
    return try allocator.alloc([]const u8, 10);
}
```

Review questions:
- Does the caller know who owns allocated memory?
- Does the API document whether returned slices must be freed?
- Is the allocator parameter passed through instead of replaced by an internal global allocator?

### Pair Allocations With Cleanup

Every allocation path should have a visible cleanup path. Look for missing `defer`, missing `errdefer`, and containers that are initialized but never deinitialized.

```zig
const std = @import("std");

fn collectBad(allocator: std.mem.Allocator) ![]u8 {
    // ❌ Bad: returns a slice whose backing memory is freed as the function exits.
    var bad_list: std.ArrayListUnmanaged(u8) = .empty;
    defer bad_list.deinit(allocator);
    try bad_list.append(allocator, 'a');
    return bad_list.items;
}

fn collect(allocator: std.mem.Allocator) ![]u8 {
    // ✅ Good: `errdefer` cleans up only on failure; success transfers ownership.
    var list: std.ArrayListUnmanaged(u8) = .empty;
    errdefer list.deinit(allocator);

    try list.append(allocator, 'a');
    try list.append(allocator, 'b');
    return try list.toOwnedSlice(allocator);
}
```

Review questions:
- Is cleanup registered immediately after acquisition?
- Is `errdefer` used when ownership transfers only on success?
- Are `deinit` calls paired with all container initializations?

### Choose Allocators Deliberately

Allocator choice is part of the design. A review should flag broad use of a debug/general-purpose allocator where a fixed buffer, arena, page allocator, or caller-provided allocator better matches the lifetime.

```zig
// ❌ Bad: allocation lifetime is scattered across many individual frees.
const user = try allocator.create(User);
const events = try allocator.alloc(Event, event_count);

// ✅ Good: request/frame-scoped allocations are freed together.
var arena = std.heap.ArenaAllocator.init(parent_allocator);
defer arena.deinit();
const allocator = arena.allocator();
```

Review questions:
- Are arena allocations freed at a clear lifetime boundary?
- Is a test using `std.testing.allocator` to catch leaks?
- Is a library avoiding policy decisions that belong to its caller?

---

## Errors & Cleanup

### Keep Error Sets Useful

Avoid flattening meaningful errors into `anyerror` unless the boundary genuinely needs it. Specific error sets improve API contracts and make callers handle expected failures.

```zig
// ❌ Bad: erases the expected parse failures behind `anyerror`.
fn parseDigitAny(input: []const u8) anyerror!u8 {
    if (input.len == 0) return error.EmptyInput;
    if (input[0] < '0' or input[0] > '9') return error.InvalidDigit;
    return input[0] - '0';
}

// ✅ Good: names the domain failures that callers should handle.
const ParseError = error{
    EmptyInput,
    InvalidDigit,
};

fn parseDigit(input: []const u8) ParseError!u8 {
    if (input.len == 0) return error.EmptyInput;
    if (input[0] < '0' or input[0] > '9') return error.InvalidDigit;
    return input[0] - '0';
}
```

Review questions:
- Are expected domain failures named explicitly?
- Is `anyerror` only used at integration boundaries?
- Does the caller preserve context when converting errors?

### Use `try`, `catch`, and `errdefer` Intentionally

Blind `catch unreachable` is a code smell unless the invariant is mechanically guaranteed. Prefer propagating errors with `try`, converting them at boundaries, or adding a comment for unreachable invariants.

```zig
// ❌ Bad: hides a real allocation failure.
const buffer_bad = allocator.alloc(u8, size) catch unreachable;

// ✅ Good: caller can handle OutOfMemory.
const buffer = try allocator.alloc(u8, size);
```

Review questions:
- Does `catch unreachable` mask I/O, allocation, parsing, or user-input errors?
- Are errors converted close to a boundary where the abstraction changes?
- Does `errdefer` undo partial state changes on failure?

---

## Pointers, Slices & Optionals

### Prefer Slices Over Pointer Plus Length

Slices carry pointer and length together, improving bounds checking and API clarity. Raw pointer plus length should be reserved for FFI or very low-level code.

```zig
// ❌ Bad: easy to mismatch pointer and length.
fn checksumRaw(ptr: [*]const u8, len: usize) u32 {
    var sum: u32 = 0;
    for (ptr[0..len]) |byte| sum += byte;
    return sum;
}

// ✅ Good: one value represents the buffer.
fn checksum(bytes: []const u8) u32 {
    var sum: u32 = 0;
    for (bytes) |byte| sum += byte;
    return sum;
}
```

Review questions:
- Can a raw pointer API become a slice API?
- Is nullability modeled with `?T` instead of sentinel values?
- Are pointer lifetimes clear after returning from a function?

### Avoid Returning Pointers to Stack Data

Review returned slices and pointers carefully. Zig makes many lifetime issues visible, but reviewers should still check that returned data outlives the function.

```zig
// ❌ Bad: returned slice points to stack memory.
fn labelStack() []const u8 {
    var buf: [16]u8 = undefined;
    _ = &buf;
    return buf[0..];
}

// ✅ Good: caller owns the allocated result and can free it.
fn label(allocator: std.mem.Allocator) ![]u8 {
    return try allocator.dupe(u8, "ready");
}
```

Review questions:
- Does returned memory come from the caller, allocator, static storage, or a stable owner?
- Does a slice escape after its backing buffer is mutated or freed?
- Is aliasing intentional and documented for mutable slices?

---

## Comptime & Generics

### Keep Comptime Work Bounded and Readable

`comptime` is powerful, but complex compile-time code can make error messages and build times worse. Prefer small generic helpers with clear type contracts.

```zig
fn RingBuffer(comptime T: type, comptime capacity: usize) type {
    // ✅ Good: invalid generic parameters fail with an actionable message.
    if (capacity == 0) @compileError("capacity must be greater than zero");

    return struct {
        items: [capacity]T = undefined,
        len: usize = 0,
    };
}
```

Review questions:
- Does `comptime` enforce a real invariant?
- Are compile errors explicit and actionable?
- Is reflection code isolated from ordinary runtime logic?

### Avoid Overly Broad `anytype`

`anytype` can make APIs flexible, but it can also hide required capabilities. Add comptime checks or prefer concrete interfaces when possible.

```zig
// ✅ Good: the required writer capability is obvious at the call site.
fn writeAll(writer: anytype, bytes: []const u8) !void {
    try writer.writeAll(bytes);
}
```

Review questions:
- Is the required shape of `anytype` clear from the function body or docs?
- Would a concrete type or smaller helper be easier to review?
- Are compile errors understandable when the wrong type is passed?

---

## Safety, Undefined Behavior & Casts

### Treat `undefined`, `unreachable`, and Casts as Review Hotspots

Zig exposes low-level control directly. Review every `undefined`, `unreachable`, `@ptrCast`, `@alignCast`, `@intCast`, and pointer/int conversion.

```zig
// ❌ Bad: assumes data layout, byte order, length, and alignment without proof.
const header: *const Header = @ptrCast(@alignCast(bytes.ptr));

// ✅ Good: parse fields explicitly and check length before reading.
if (bytes.len < 4) return error.ShortInput;
const magic = std.mem.readInt(u16, bytes[0..2], .little);
const flags = std.mem.readInt(u16, bytes[2..4], .little);
```

Review questions:
- Is `undefined` overwritten before being read?
- Is `unreachable` only used for impossible states, with a nearby explanation when non-obvious?
- Are casts preceded by checks for layout, range, alignment, size, byte order, and nullability?

### Prefer Checked Arithmetic Unless Wrapping Is Intentional

Wrapping operators such as `+%` and `-%` are useful, but they should communicate a deliberate modular arithmetic choice.

```zig
// ❌ Bad: wrapping silences overflow that should expose a logic bug.
index = index +% 1;

// ✅ Good: checked arithmetic traps on unexpected overflow.
sum += byte;

// ✅ Good: wrapping is intentional for modular hash behavior.
hash = hash *% 16777619;
hash = hash +% byte;
```

Review questions:
- Is wrapping arithmetic required by an algorithm?
- Would overflow indicate invalid input or a bug?
- Are integer width changes explicit and tested around boundaries?

---

## C Interop

### Contain C Boundaries

Keep `@cImport`, C pointer handling, and ABI assumptions close to a wrapper layer. Convert C data into Zig types before it spreads through the codebase.

```zig
const std = @import("std");

// ❌ Bad: uses C strlen when no external C boundary is needed.
fn strlenC(input: [*:0]const u8) usize {
    const c = @cImport({
        @cInclude("string.h");
    });

    return c.strlen(input);
}

// ✅ Good: use Zig's sentinel-aware standard library helper.
fn strlenZ(input: [*:0]const u8) usize {
    return std.mem.len(input);
}
```

Review questions:
- Are C pointers represented with the correct Zig pointer type?
- Are sentinel-terminated strings modeled as sentinel pointers or slices?
- Are ownership and cleanup rules from the C library documented?
- Are C error codes converted into Zig error unions near the boundary?

---

## Testing

### Use `std.testing` Assertions and Leak Detection

Tests that allocate should use `std.testing.allocator` where practical so leaks are reported by the test runner.

```zig
const std = @import("std");

test "collect returns owned memory on success" {
    const allocator = std.testing.allocator;
    const names = try collect(allocator);
    defer allocator.free(names);

    try std.testing.expectEqual(@as(usize, 2), names.len);
}

test "collect handles allocation failures cleanly" {
    var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{
        .fail_index = 0,
    });
    try std.testing.expectError(error.OutOfMemory, collect(failing.allocator()));
}
```

Review questions:
- Are allocation-heavy paths covered by tests?
- Are error paths tested with `std.testing.expectError`?
- Do tests cover boundary sizes such as empty input, one element, max capacity, and invalid encodings?

### Test Build Modes and Targets When Relevant

Behavior can differ across safety modes, targets, and ABIs. For low-level code, ask whether the PR was tested with the intended target and optimization mode.

Review questions:
- Does code rely on debug-only safety checks?
- Does packed/aligned/extern layout code have target-aware tests?
- Are endian, pointer-width, and ABI assumptions tested or documented?

---

## Style & API Design

### Follow Zig Naming Conventions

Use the official style guide as the baseline: `TitleCase` for types, `camelCase` for functions, and `snake_case` for variables. Avoid redundant words such as `Value`, `Data`, `Manager`, or `State` when the surrounding namespace already provides that meaning.

```zig
// ❌ Bad: redundant namespace and vague type name.
pub const json_bad = struct {
    pub const JsonValueManager = struct {};
};

// ✅ Good: name is meaningful in its fully-qualified namespace.
pub const json = struct {
    pub const Value = union(enum) {};
};
```

Review questions:
- Does the fully-qualified name read naturally?
- Are file and directory names consistent with the style guide?
- Are underscore-prefixed declarations avoided unless they come from an external convention?
- Are public APIs documented with doc comments where helpful?

### Keep Public APIs Small

Zig modules often expose declarations directly from files and structs. Review public declarations for accidental exports.

Review questions:
- Should this declaration be `pub`?
- Is the public API stable enough to expose?
- Are implementation details hidden behind a smaller surface?

---

## Review Checklist

### Memory & Lifetime
- [ ] Allocator ownership is explicit.
- [ ] Allocations have matching `free`, `deinit`, `defer`, or `errdefer`.
- [ ] Returned slices and pointers outlive the function.
- [ ] Arena or temporary allocations have a clear lifetime boundary.

### Errors & Cleanup
- [ ] Expected failures use specific error sets where practical.
- [ ] `catch unreachable` does not hide real runtime failures.
- [ ] Partial initialization is rolled back with `errdefer`.
- [ ] Error conversions happen at abstraction boundaries.

### Pointers & Safety
- [ ] Raw pointers are justified; slices are used for ordinary buffers.
- [ ] Casts check size, range, alignment, and nullability.
- [ ] `undefined` is not read before initialization.
- [ ] Wrapping arithmetic is intentional and tested.

### Comptime & API Design
- [ ] `comptime` logic enforces useful invariants.
- [ ] `anytype` usage has clear expectations.
- [ ] Public declarations are intentional.
- [ ] Names follow Zig style conventions.

### C Interop & Portability
- [ ] C boundaries are isolated behind wrappers.
- [ ] C ownership and cleanup rules are documented.
- [ ] Target, endian, pointer-width, and ABI assumptions are tested or documented.

### Tests
- [ ] Tests use `std.testing.allocator` for allocation-heavy code.
- [ ] Error paths use `std.testing.expectError`.
- [ ] Boundary cases are covered.
- [ ] Relevant build modes and targets are considered.

---

## References

- [Zig 0.16.0 Language Reference](https://ziglang.org/documentation/0.16.0/)
- [Zig 0.16.0 Standard Library documentation](https://ziglang.org/documentation/0.16.0/std/)
- [Zig 0.16.0 Style Guide](https://ziglang.org/documentation/0.16.0/#Style-Guide)
- [Choosing an Allocator](https://ziglang.org/documentation/0.16.0/#Choosing-an-Allocator)
