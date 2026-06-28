# C Code Review Guide

> C code review guide focused on memory safety, undefined behavior, portability, testing, and secure coding. Examples assume C11/C17.

## Table of Contents

- [Pointer and Buffer Safety](#pointer-and-buffer-safety)
- [Ownership and Resource Management](#ownership-and-resource-management)
- [Undefined Behavior Pitfalls](#undefined-behavior-pitfalls)
- [Integer Types and Overflow](#integer-types-and-overflow)
- [Error Handling](#error-handling)
- [Concurrency](#concurrency)
- [Macros and Preprocessor](#macros-and-preprocessor)
- [API Design and Const](#api-design-and-const)
- [Secure Coding Practices](#secure-coding-practices)
- [Cross-Platform Portability](#cross-platform-portability)
- [Testing](#testing)
- [Tooling and Build Checks](#tooling-and-build-checks)
- [Review Checklist](#review-checklist)

---

## Pointer and Buffer Safety

### Always carry size with buffers

```c
// ❌ Bad: ignores destination size
bool copy_name(char *dst, size_t dst_size, const char *src) {
    strcpy(dst, src);
    return true;
}

// ✅ Good: validate size and terminate
bool copy_name(char *dst, size_t dst_size, const char *src) {
    size_t len = strlen(src);
    if (len + 1 > dst_size) {
        return false;
    }
    memcpy(dst, src, len + 1);
    return true;
}
```

### Avoid dangerous APIs

Prefer `snprintf`, `fgets`, and explicit bounds over `gets`, `strcpy`, or `sprintf`.

```c
// ❌ Bad: unbounded write
sprintf(buf, "%s", input);

// ✅ Good: bounded write
snprintf(buf, buf_size, "%s", input);
```

### Use the right copy primitive

```c
// ❌ Bad: memcpy with overlapping regions
memcpy(dst, src, len);

// ✅ Good: memmove handles overlap
memmove(dst, src, len);
```

### Validate pointer arguments

```c
// ❌ Bad: no NULL check
int process(char *buf, size_t len) {
    buf[0] = '\0';
    return 0;
}

// ✅ Good: validate before use
int process(char *buf, size_t len) {
    if (!buf || len == 0) {
        return -EINVAL;
    }
    buf[0] = '\0';
    return 0;
}
```

### Beware of pointer-to-pointer pitfalls

```c
// ❌ Bad: caller cannot distinguish success from failure
void allocate(int **out) {
    *out = malloc(sizeof(int));
}

// ✅ Good: return status, set output only on success
int allocate(int **out) {
    if (!out) return -EINVAL;
    int *p = malloc(sizeof(int));
    if (!p) return -ENOMEM;
    *out = p;
    return 0;
}
```

---

## Ownership and Resource Management

### One allocation, one free

Track ownership and clean up on every error path.

```c
// ✅ Good: cleanup label avoids leaks
int load_file(const char *path) {
    int rc = -1;
    FILE *f = NULL;
    char *buf = NULL;

    f = fopen(path, "rb");
    if (!f) {
        goto cleanup;
    }
    buf = malloc(4096);
    if (!buf) {
        goto cleanup;
    }

    if (fread(buf, 1, 4096, f) == 0) {
        goto cleanup;
    }

    rc = 0;

cleanup:
    free(buf);
    if (f) {
        fclose(f);
    }
    return rc;
}
```

### Document ownership transfer

```c
// ✅ Good: comment clarifies that caller takes ownership
// Caller must free() the returned buffer.
char *read_line(FILE *f);

// ✅ Good: comment clarifies that callee does NOT take ownership
// The function borrows `buf`; caller retains ownership.
int parse_header(const char *buf, size_t len, struct Header *out);
```

### Free exactly once, set pointer to NULL

```c
// ❌ Bad: double free possible
void destroy(struct Cache *c) {
    free(c->entries);
    // caller might call destroy() again → double free
}

// ✅ Good: NULL after free prevents double free
void destroy(struct Cache *c) {
    if (!c) return;
    free(c->entries);
    c->entries = NULL;
    c->count = 0;
}
```

---

## Undefined Behavior Pitfalls

### Signed integer overflow

Signed overflow is UB in C; unsigned wraps around.

```c
// ❌ Bad: signed overflow is UB
int sum = INT_MAX + 1;  // undefined behavior

// ✅ Good: check before overflow
if (a > 0 && b > INT_MAX - a) {
    return -EOVERFLOW;
}
int sum = a + b;
```

### Dangling pointers

```c
// ❌ Bad: returning pointer to local array
char *greet(void) {
    char buf[64];
    snprintf(buf, sizeof(buf), "hello");
    return buf;  // UB: buf is gone when function returns
}

// ✅ Good: caller provides buffer or use static storage
void greet(char *out, size_t out_size) {
    snprintf(out, out_size, "hello");
}
```

### Uninitialized variables

```c
// ❌ Bad: x may be anything
int x;
if (x > 0) { /* UB: reading uninitialized automatic variable */ }

// ✅ Good: always initialize
int x = 0;
if (x > 0) { /* well-defined */ }
```

### Sequence point violations

```c
// ❌ Bad: undefined — order of evaluation of operands
int i = 0;
int a[] = { i++, i++ };  // UB: two modifications without sequence point

// ❌ Bad: modification and read without sequence point
int j = i + i++;  // UB

// ✅ Good: separate statements
int a0 = i++;
int a1 = i++;
int a[] = { a0, a1 };
```

### Strict aliasing violations

```c
// ❌ Bad: violates strict aliasing
float f = 3.14f;
int i = *(int *)&f;  // UB

// ✅ Good: use memcpy or union (C11 allows type-punning via union)
int i;
memcpy(&i, &f, sizeof(i));

// ✅ Also acceptable in C11:
union { float f; int i; } u;
u.f = 3.14f;
int i = u.i;
```

### Shift operations

```c
// ❌ Bad: shift by negative or >= width is UB
int x = 1 << 32;     // UB if int is 32-bit
int y = 1 << -1;     // UB

// ✅ Good: validate shift amount
if (shift >= 0 && shift < (int)(sizeof(int) * CHAR_BIT)) {
    int result = 1 << shift;
}
```

---

## Integer Types and Overflow

### Avoid signed/unsigned surprises

```c
// ❌ Bad: negative converted to large size_t
int len = -1;
size_t n = len;  // wraps to SIZE_MAX

// ✅ Good: validate before converting
if (len < 0) {
    return -1;
}
size_t n = (size_t)len;
```

### Check for overflow in size calculations

```c
// ❌ Bad: potential overflow in multiplication
size_t bytes = count * sizeof(Item);

// ✅ Good: check before multiplying
if (count > SIZE_MAX / sizeof(Item)) {
    return NULL;
}
size_t bytes = count * sizeof(Item);
```

### Use fixed-width types for binary protocols

```c
// ❌ Bad: int size varies by platform
struct PacketHeader {
    int type;
    int length;
};

// ✅ Good: explicit widths for wire format
#include <stdint.h>
struct PacketHeader {
    uint32_t type;
    uint32_t length;
};
```

### Beware of implicit promotion

```c
// ❌ Bad: uint8_t promotes to int in arithmetic
uint8_t a = 200, b = 100;
uint8_t sum = a + b;  // truncation: 300 → 44

// ✅ Good: be explicit about width
uint16_t sum = (uint16_t)a + (uint16_t)b;  // 300
```

---

## Error Handling

### Always check return values

```c
// ❌ Bad: ignore errors
fread(buf, 1, size, f);

// ✅ Good: handle errors
size_t read = fread(buf, 1, size, f);
if (read != size && ferror(f)) {
    return -1;
}
```

### Consistent error contracts

- Use a clear convention: 0 for success, negative for failure.
- Document ownership rules on success and failure.
- If using `errno`, set it only for actual failures.

```c
// ✅ Good: clear error contract with errno
// Returns 0 on success, -1 on failure (sets errno).
// On failure, *out is unchanged.
int parse_int(const char *s, int *out);
```

### Avoid errno across function boundaries

```c
// ❌ Bad: errno may be overwritten by intermediate calls
errno = 0;
long val = strtol(s, &end, 10);
log_debug("parsed: %ld", val);  // might change errno!
if (errno != 0) { /* unreliable */ }

// ✅ Good: capture errno immediately
errno = 0;
long val = strtol(s, &end, 10);
int saved_errno = errno;
log_debug("parsed: %ld", val);
if (saved_errno != 0) { /* reliable */ }
```

---

## Concurrency

### volatile is not synchronization

```c
// ❌ Bad: data race
volatile int stop = 0;
void worker(void) {
    while (!stop) { /* ... */ }
}

// ✅ Good: C11 atomics
_Atomic int stop = 0;
void worker(void) {
    while (!atomic_load(&stop)) { /* ... */ }
}
```

### Use mutexes for shared state

Protect shared data with `pthread_mutex_t` or equivalent. Avoid holding locks while doing I/O.

```c
// ✅ Good: mutex + RAII-style cleanup
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static int g_counter = 0;

void increment(void) {
    pthread_mutex_lock(&g_lock);
    g_counter++;
    pthread_mutex_unlock(&g_lock);
}
```

### Avoid lock ordering issues

```c
// ❌ Bad: inconsistent lock ordering → deadlock
// Thread 1: lock(A); lock(B);
// Thread 2: lock(B); lock(A);

// ✅ Good: always acquire locks in the same order
// All threads: lock(A); lock(B);
```

---

## Macros and Preprocessor

### Parenthesize arguments

```c
// ❌ Bad: macro with side effects
#define MIN(a, b) ((a) < (b) ? (a) : (b))
int x = MIN(i++, j++);  // evaluates argument twice

// ✅ Good: static inline function
static inline int min_int(int a, int b) {
    return a < b ? a : b;
}
```

### Multi-statement macros

```c
// ❌ Bad: breaks in if-else without braces
#define LOG_AND_RETURN(msg) \
    fprintf(stderr, "%s\n", msg); \
    return -1

// ✅ Good: do { ... } while(0) idiom
#define LOG_AND_RETURN(msg) do { \
    fprintf(stderr, "%s\n", msg); \
    return -1; \
} while (0)
```

### Include guards

```c
// ✅ Good: traditional include guard
#ifndef MY_HEADER_H
#define MY_HEADER_H
// ... declarations ...
#endif /* MY_HEADER_H */

// ✅ Also acceptable (non-standard but widely supported):
#pragma once
```

---

## API Design and Const

### Const-correctness and sizes

```c
// ✅ Good: explicit size and const input
int hash_bytes(const uint8_t *data, size_t len, uint8_t *out);
```

### Document nullability

Clearly document whether pointers may be NULL. Prefer returning error codes instead of NULL when possible.

```c
// ✅ Good: document contract in the header
// @param name  Non-NULL, NUL-terminated string.
// @param out    Non-NULL output pointer.
// @return 0 on success, -EINVAL if name or out is NULL.
int lookup(const char *name, struct Result *out);
```

### Opaque types for encapsulation

```c
// ✅ Good: header exposes only a pointer
typedef struct Parser Parser;

Parser *parser_create(const char *input);
int parser_next(Parser *p, struct Token *out);
void parser_destroy(Parser *p);
```

---

## Secure Coding Practices

### CERT C: buffer overflow prevention

```c
// ❌ Bad: strncpy does NOT guarantee NUL termination
char dst[32];
strncpy(dst, src, sizeof(dst));  // if src >= 32 bytes, dst is not terminated!

// ✅ Good: explicit NUL termination after strncpy
char dst[32];
strncpy(dst, src, sizeof(dst) - 1);
dst[sizeof(dst) - 1] = '\0';

// ✅ Better: use snprintf for bounded string copy
char dst[32];
snprintf(dst, sizeof(dst), "%s", src);
```

### Format string vulnerability

```c
// ❌ Bad: user-controlled format string
printf(user_input);  // if user_input = "%x %x %x", reads stack

// ✅ Good: always use a format literal
printf("%s", user_input);
```

### Integer overflow in allocation

```c
// ❌ Bad: count * size may overflow before malloc sees it
void *items = malloc(count * sizeof(Item));

// ✅ Good: check for overflow
if (count != 0 && SIZE_MAX / count < sizeof(Item)) {
    errno = ENOMEM;
    return NULL;
}
void *items = malloc(count * sizeof(Item));

// ✅ Also good: use calloc (checks internally)
Item *items = calloc(count, sizeof(Item));
```

### Validate external input lengths

```c
// ❌ Bad: trusting header-declared length
struct Msg { uint32_t len; char data[]; };
void handle(struct Msg *m) {
    char buf[256];
    memcpy(buf, m->data, m->len);  // attacker controls m->len
}

// ✅ Good: validate before use
void handle(struct Msg *m, size_t total_size) {
    if (m->len > total_size - sizeof(struct Msg)) {
        return -EINVAL;
    }
    char buf[256];
    if (m->len > sizeof(buf)) {
        return -E2BIG;
    }
    memcpy(buf, m->data, m->len);
}
```

### Avoid TOCTOU race conditions

```c
// ❌ Bad: check-then-use is a race (TOCTOU)
if (access(path, R_OK) == 0) {
    FILE *f = fopen(path, "r");  // file may have changed between access() and fopen()
}

// ✅ Good: try and check the result
FILE *f = fopen(path, "r");
if (!f) {
    // handle error (ENOENT, EACCES, etc.)
}
```

### Secure temporary files

```c
// ❌ Bad: predictable name
char path[] = "/tmp/myapp_XXXXXX";
FILE *f = fopen(path, "w");  // predictable, race condition

// ✅ Good: mkstemp creates and opens atomically
char tmpl[] = "/tmp/myapp_XXXXXX";
int fd = mkstemp(tmpl);
if (fd < 0) { /* handle error */ }
FILE *f = fdopen(fd, "w");
```

---

## Cross-Platform Portability

### Preprocessor conditionals best practices

```c
// ❌ Bad: nested #ifdef soup
#ifdef _WIN32
    #ifdef _WIN64
        // 64-bit Windows
    #else
        // 32-bit Windows
    #endif
#else
    #ifdef __linux__
        // Linux
    #endif
#endif

// ✅ Good: abstract behind feature macros
#if defined(PLATFORM_WINDOWS)
    #include "platform_win.h"
#elif defined(PLATFORM_LINUX)
    #include "platform_linux.h"
#elif defined(PLATFORM_MACOS)
    #include "platform_macos.h"
#else
    #error "Unsupported platform"
#endif
```

### Byte order (endianness)

```c
// ❌ Bad: assumes little-endian
uint32_t read_u32(const uint8_t *buf) {
    return *(const uint32_t *)buf;  // alignment + endianness issues
}

// ✅ Good: explicit byte-order handling
static inline uint32_t read_u32_le(const uint8_t *buf) {
    return (uint32_t)buf[0]
         | ((uint32_t)buf[1] << 8)
         | ((uint32_t)buf[2] << 16)
         | ((uint32_t)buf[3] << 24);
}

static inline uint32_t read_u32_be(const uint8_t *buf) {
    return ((uint32_t)buf[0] << 24)
         | ((uint32_t)buf[1] << 16)
         | ((uint32_t)buf[2] << 8)
         | (uint32_t)buf[3];
}
```

### Alignment-aware access

```c
// ❌ Bad: unaligned access is UB on many architectures
uint32_t val = *(const uint32_t *)ptr;

// ✅ Good: memcpy is safe for any alignment
uint32_t val;
memcpy(&val, ptr, sizeof(val));
```

### Avoid platform-specific extensions in portable code

```c
// ❌ Bad: GCC extension in shared code
typeof(x) y = x;

// ✅ Good: use standard C or isolate extensions
// In a platform-specific header:
#ifdef __GNUC__
    #define TYPEOF(x) typeof(x)
#else
    #define TYPEOF(x) decltype(x)  /* C++23 or compiler-specific */
#endif
```

### Use feature detection, not platform detection

```c
// ❌ Bad: assumes POSIX because Linux
#ifdef __linux__
    #include <sys/mman.h>
#endif

// ✅ Good: feature test via CMake/configure
#ifdef HAVE_MMAP
    #include <sys/mman.h>
#endif
```

---

## Testing

### Choosing a test framework

| Framework | Use Case | Notes |
|-----------|----------|-------|
| **Unity** | Embedded / bare-metal | Single-file, no dependencies, C89 compatible |
| **CUnit** | Desktop / CI | Richer assertions, HTML/XML output |
| **CMocka** | System-level code | Mocking via function pointers, works with `setjmp`/`longjmp` |

### Basic test structure with Unity

```c
#include "unity.h"
#include "parser.h"

void setUp(void) { /* runs before each test */ }
void tearDown(void) { /* runs after each test */ }

void test_parse_empty_string_returns_null(void) {
    struct Token *t = parse("");
    TEST_ASSERT_NULL(t);
}

void test_parse_valid_integer(void) {
    struct Token *t = parse("42");
    TEST_ASSERT_NOT_NULL(t);
    TEST_ASSERT_EQUAL_INT(TOKEN_INT, t->type);
    TEST_ASSERT_EQUAL_INT(42, t->value);
    token_free(t);
}

void test_parse_negative_number(void) {
    struct Token *t = parse("-7");
    TEST_ASSERT_NOT_NULL(t);
    TEST_ASSERT_EQUAL_INT(-7, t->value);
    token_free(t);
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_parse_empty_string_returns_null);
    RUN_TEST(test_parse_valid_integer);
    RUN_TEST(test_parse_negative_number);
    return UNITY_END();
}
```

### Test isolation: mock system calls

```c
// ✅ Good: inject dependencies for testability
// Production code:
struct FileOps {
    int (*read)(void *buf, size_t size, void *ctx);
    void *ctx;
};

int load_config(const struct FileOps *ops, struct Config *out);

// Test code:
static int mock_read(void *buf, size_t size, void *ctx) {
    const char *data = (const char *)ctx;
    size_t len = strlen(data);
    if (len < size) size = len;
    memcpy(buf, data, size);
    return (int)size;
}

void test_load_config_with_mock(void) {
    const char *fake_data = "key=value\n";
    struct FileOps ops = { .read = mock_read, .ctx = (void *)fake_data };
    struct Config cfg;
    int rc = load_config(&ops, &cfg);
    TEST_ASSERT_EQUAL_INT(0, rc);
    TEST_ASSERT_EQUAL_STRING("value", cfg.key);
}
```

### Memory leak testing with sanitizers

```bash
# Run tests under AddressSanitizer
cc -fsanitize=address -fno-omit-frame-pointer -g -o test_runner tests/*.c src/*.c
./test_runner

# Run tests under Valgrind
cc -g -O0 -o test_runner tests/*.c src/*.c
valgrind --leak-check=full --error-exitcode=1 ./test_runner
```

```c
// ✅ Good: test that error paths don't leak
void test_parse_invalid_frees_resources(void) {
    // Valgrind/ASan will catch any leaks from this call
    struct Token *t = parse("not_a_number");
    TEST_ASSERT_NULL(t);
    // If parse() allocated internal state and forgot to free on error,
    // the sanitizer will report it.
}
```

### Test edge cases systematically

```c
void test_edge_cases(void) {
    // Zero-length input
    TEST_ASSERT_EQUAL_INT(-EINVAL, process(NULL, 0));

    // Maximum valid input
    char buf[256];
    memset(buf, 'a', sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    TEST_ASSERT_EQUAL_INT(0, process(buf, sizeof(buf) - 1));

    // One byte over the limit
    TEST_ASSERT_EQUAL_INT(-E2BIG, process(buf, sizeof(buf)));
}
```

---

## Tooling and Build Checks

```bash
# Warnings
clang -Wall -Wextra -Werror -Wconversion -Wshadow -std=c11 ...

# Sanitizers (debug builds)
clang -fsanitize=address,undefined -fno-omit-frame-pointer -g ...
clang -fsanitize=thread -fno-omit-frame-pointer -g ...

# Static analysis
clang-tidy src/*.c -- -std=c11
cppcheck --enable=warning,performance,portability src/

# Formatting
clang-format -i src/*.c include/*.h
```

### CI integration checklist

```bash
# Typical CI pipeline for a C project
clang -Wall -Wextra -Werror -std=c11 -c src/*.c        # compile with strict warnings
clang -fsanitize=address,undefined -g -o test test/*.c src/*.c  # sanitizer build
./test                                                   # run tests
valgrind --leak-check=full --error-exitcode=1 ./test    # memory check
cppcheck --error-exitcode=1 --enable=all src/            # static analysis
```

---

## Review Checklist

### Memory and UB
- [ ] All buffers have explicit size parameters
- [ ] No out-of-bounds access or pointer arithmetic past objects
- [ ] No use after free or uninitialized reads
- [ ] Signed overflow and shift rules are respected
- [ ] Strict aliasing rules are respected
- [ ] Sequence point rules are respected

### Secure Coding
- [ ] No format string vulnerabilities (user input never used as format)
- [ ] No unchecked allocation sizes (overflow in count * size)
- [ ] No TOCTOU races on file operations
- [ ] External input lengths are validated before use
- [ ] Temporary files use mkstemp or equivalent

### API and Design
- [ ] Ownership rules are documented and consistent
- [ ] const-correctness is applied for inputs
- [ ] Error contracts are clear and consistent
- [ ] Pointer nullability is documented
- [ ] Opaque types used for encapsulation

### Portability
- [ ] No unaligned memory access
- [ ] Byte order handled explicitly for wire/binary formats
- [ ] Fixed-width types used for binary protocols
- [ ] Platform-specific code isolated behind feature macros

### Concurrency
- [ ] No data races on shared state
- [ ] volatile is not used for synchronization
- [ ] Locks are held for minimal time
- [ ] Lock ordering is consistent

### Testing and Tooling
- [ ] Unit tests cover happy path, error paths, and edge cases
- [ ] Builds clean with warnings enabled (-Wall -Wextra -Werror)
- [ ] Sanitizers (ASan, UBSan) run on critical code paths
- [ ] Valgrind or ASan confirms no memory leaks
- [ ] Static analysis results are addressed
