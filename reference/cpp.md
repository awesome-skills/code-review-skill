# C++ Code Review Guide

> C++ code review guide focused on memory safety, lifetime, API design, modern features, and performance. Examples assume C++17/20/23.

## Table of Contents

- [Ownership and RAII](#ownership-and-raii)
- [Smart Pointer Selection Guide](#smart-pointer-selection-guide)
- [Lifetime and References](#lifetime-and-references)
- [Copy and Move Semantics](#copy-and-move-semantics)
- [Const-Correctness and API Design](#const-correctness-and-api-design)
- [Error Handling and Exception Safety](#error-handling-and-exception-safety)
- [Modern C++20/23 Features](#modern-c2023-features)
- [constexpr and consteval](#constexpr-and-consteval)
- [Concurrency](#concurrency)
- [Performance and Allocation](#performance-and-allocation)
- [Templates and Type Safety](#templates-and-type-safety)
- [Testing](#testing)
- [Tooling and Build Checks](#tooling-and-build-checks)
- [Review Checklist](#review-checklist)

---

## Ownership and RAII

### Prefer RAII and smart pointers

Use RAII to express ownership. Default to `std::unique_ptr`, use `std::shared_ptr` only for shared lifetime.

```cpp
// ❌ Bad: manual new/delete with early returns
Foo* make_foo() {
    Foo* foo = new Foo();
    if (!foo->Init()) {
        delete foo;
        return nullptr;
    }
    return foo;
}

// ✅ Good: RAII with unique_ptr
std::unique_ptr<Foo> make_foo() {
    auto foo = std::make_unique<Foo>();
    if (!foo->Init()) {
        return {};
    }
    return foo;
}
```

### Wrap C resources

```cpp
// ✅ Good: wrap FILE* with unique_ptr
using FilePtr = std::unique_ptr<FILE, decltype(&fclose)>;

FilePtr open_file(const char* path) {
    return FilePtr(fopen(path, "rb"), &fclose);
}
```

### RAII best practices

```cpp
// ✅ Good: RAII wrapper for POSIX file descriptors
class Fd {
    int fd_ = -1;
public:
    explicit Fd(int fd) : fd_(fd) {}
    ~Fd() { if (fd_ >= 0) ::close(fd_); }

    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
    Fd(Fd&& o) noexcept : fd_(std::exchange(o.fd_, -1)) {}
    Fd& operator=(Fd&& o) noexcept {
        if (this != &o) {
            if (fd_ >= 0) ::close(fd_);
            fd_ = std::exchange(o.fd_, -1);
        }
        return *this;
    }

    int get() const { return fd_; }
    int release() { return std::exchange(fd_, -1); }
};
```

### Never mix ownership styles

```cpp
// ❌ Bad: raw new + container of raw pointers — who deletes?
std::vector<Widget*> widgets;
widgets.push_back(new Widget());
// When is delete called? Unclear.

// ✅ Good: container of unique_ptr
std::vector<std::unique_ptr<Widget>> widgets;
widgets.push_back(std::make_unique<Widget>());
// Automatically cleaned up when vector is destroyed.
```

---

## Smart Pointer Selection Guide

### Decision matrix

| Scenario | Pointer | Why |
|----------|---------|-----|
| Single owner | `unique_ptr` | Zero overhead, clear ownership |
| Shared ownership (few owners) | `shared_ptr` | Reference counted, thread-safe refcount |
| Non-owning observer | `weak_ptr` | Breaks cycles, checks liveness |
| Never-null reference | raw reference `T&` | No ownership, cannot be null |
| Maybe-null observer | raw pointer `T*` | No ownership, can be null |

### Avoid shared_ptr when unique_ptr suffices

```cpp
// ❌ Bad: unnecessary shared ownership
class Window {
    std::shared_ptr<Renderer> renderer_;
public:
    Window() : renderer_(std::make_shared<Renderer>()) {}
};

// ✅ Good: sole owner uses unique_ptr
class Window {
    std::unique_ptr<Renderer> renderer_;
public:
    Window() : renderer_(std::make_unique<Renderer>()) {}
};
```

### Break cycles with weak_ptr

```cpp
// ❌ Bad: cycle → memory leak
struct Node {
    std::shared_ptr<Node> parent;
    std::shared_ptr<Node> child;
};

// ✅ Good: weak_ptr breaks the back-reference
struct Node {
    std::weak_ptr<Node> parent;    // non-owning back-reference
    std::shared_ptr<Node> child;   // owning forward-reference
};
```

---

## Lifetime and References

### Avoid dangling references and views

`std::string_view` and `std::span` do not own data. Make sure the owner outlives the view.

```cpp
// ❌ Bad: returning string_view to a temporary
std::string_view bad_view() {
    std::string s = make_name();
    return s; // dangling
}

// ✅ Good: return owning string
std::string good_name() {
    return make_name();
}

// ✅ Good: view tied to caller-owned data
std::string_view good_view(const std::string& s) {
    return s;
}
```

### Lambda captures

```cpp
// ❌ Bad: capture reference that escapes
std::function<void()> make_task() {
    int value = 42;
    return [&]() { use(value); }; // dangling
}

// ✅ Good: capture by value
std::function<void()> make_task() {
    int value = 42;
    return [value]() { use(value); };
}
```

### Beware of temporary lifetime extension pitfalls

```cpp
// ❌ Bad: reference bound to temporary that is destroyed
const std::string& name = get_name();  // temporary destroyed at end of statement
use(name);  // dangling reference

// ✅ Good: store the value
std::string name = get_name();
use(name);
```

---

## Copy and Move Semantics

### Rule of 0/3/5

Prefer the Rule of 0 by using RAII types. If you own a resource, define or delete copy and move operations.

```cpp
// ❌ Bad: raw ownership with default copy
struct Buffer {
    int* data;
    size_t size;
    explicit Buffer(size_t n) : data(new int[n]), size(n) {}
    ~Buffer() { delete[] data; }
    // copy ctor/assign are implicitly generated -> double delete
};

// ✅ Good: Rule of 0 with std::vector
struct Buffer {
    std::vector<int> data;
    explicit Buffer(size_t n) : data(n) {}
};
```

### Delete unwanted copies

```cpp
struct Socket {
    Socket() = default;
    ~Socket() { close(); }

    Socket(const Socket&) = delete;
    Socket& operator=(const Socket&) = delete;
    Socket(Socket&&) noexcept = default;
    Socket& operator=(Socket&&) noexcept = default;
};
```

### Use std::move explicitly

```cpp
// ❌ Bad: copies instead of moves
std::string name = get_name();
data_.push_back(name);  // copy

// ✅ Good: move when source is no longer needed
std::string name = get_name();
data_.push_back(std::move(name));
```

---

## Const-Correctness and API Design

### Use const and explicit

```cpp
class User {
public:
    const std::string& name() const { return name_; }
    void set_name(std::string name) { name_ = std::move(name); }

private:
    std::string name_;
};

struct Millis {
    explicit Millis(int v) : value(v) {}
    int value;
};
```

### Avoid object slicing

```cpp
struct Shape { virtual ~Shape() = default; };
struct Circle : Shape { void draw() const; };

// ❌ Bad: slices Circle into Shape
void draw(Shape shape);

// ✅ Good: pass by reference
void draw(const Shape& shape);
```

### Use override and final

```cpp
struct Base {
    virtual void run() = 0;
};

struct Worker final : Base {
    void run() override {}
};
```

---

## Error Handling and Exception Safety

### Prefer RAII for cleanup

```cpp
// ✅ Good: RAII handles cleanup on exceptions
void process() {
    std::vector<int> data = load_data(); // safe cleanup
    do_work(data);
}
```

### Do not throw from destructors

```cpp
struct File {
    ~File() noexcept { close(); }
    void close();
};
```

### Use expected results for normal failures

```cpp
// ✅ C++23: std::expected
#include <expected>

std::expected<int, ParseError> parse_int(std::string_view s) {
    try {
        return std::stoi(std::string(s));
    } catch (const std::invalid_argument&) {
        return std::unexpected(ParseError::InvalidFormat);
    } catch (const std::out_of_range&) {
        return std::unexpected(ParseError::OutOfRange);
    }
}

// ✅ Pre-C++23: std::optional
std::optional<int> parse_int(const std::string& s) {
    try {
        return std::stoi(s);
    } catch (...) {
        return std::nullopt;
    }
}
```

### Exception safety levels

- **No-throw guarantee**: `noexcept` — destructors, swap, move operations.
- **Strong guarantee**: operation either succeeds or state is unchanged. Use copy-and-swap idiom.
- **Basic guarantee**: on exception, no resources leaked, object in valid (but possibly modified) state.

```cpp
// ✅ Good: strong guarantee via copy-and-swap
void Container::push_back(const Item& item) {
    Container tmp(*this);    // copy
    tmp.push_back_impl(item); // may throw, but tmp is a copy
    swap(*this, tmp);         // noexcept swap
}
```

---

## Modern C++20/23 Features

### Concepts (C++20)

```cpp
// ❌ Bad: SFINAE boilerplate
template <typename T, std::enable_if_t<std::is_integral_v<T>, int> = 0>
T gcd(T a, T b) {
    while (b) { a %= b; std::swap(a, b); }
    return a;
}

// ✅ Good: concepts are readable and composable
template <std::integral T>
T gcd(T a, T b) {
    while (b) { a %= b; std::swap(a, b); }
    return a;
}

// ✅ Define custom concepts
template <typename T>
concept Printable = requires(T t, std::ostream& os) {
    { os << t } -> std::convertible_to<std::ostream&>;
};

void log(const Printable auto& value) {
    std::cout << "[LOG] " << value << '\n';
}
```

### Ranges and views (C++20)

```cpp
#include <ranges>
#include <vector>
#include <numeric>

// ✅ Good: composable range pipelines
std::vector<int> scores = {85, 92, 67, 73, 98, 55};

auto top_scores = scores
    | std::views::filter([](int s) { return s >= 80; })
    | std::views::transform([](int s) { return s * 1.1; })  // bonus
    | std::views::take(3);

// Iterate without allocating intermediate containers
for (double s : top_scores) {
    std::cout << s << ' ';
}
```

### Modules (C++20)

```cpp
// ✅ Module interface unit (math.cppm)
export module math;

export int add(int a, int b) { return a + b; }
export constexpr double pi = 3.14159265358979;

// ✅ Module implementation unit (math_impl.cpp)
module math;

int internal_helper() { /* not exported */ }

// Consumer:
import math;
int result = add(1, 2);
```

**Review note**: Modules are still maturing in tooling support. Check that your build system (CMake 3.28+, MSVC 17.x, Clang 16+) supports them before adopting. Headers remain the safe default.

### Deducing this (C++23)

```cpp
// ❌ Bad: verbose CRTP for static polymorphism
template <typename Derived>
struct Base {
    void call() { static_cast<Derived*>(this)->impl(); }
};

// ✅ Good: C++23 explicit object parameter
struct Widget {
    template <typename Self>
    void log(this Self&& self) {
        // self is Widget& or Widget&& depending on call context
        std::cout << self.name << '\n';
    }
    std::string name;
};
```

---

## constexpr and consteval

### When to use constexpr vs consteval

- `constexpr`: can be evaluated at compile time *or* runtime.
- `consteval`: **must** be evaluated at compile time (immediate function).

```cpp
// ✅ constexpr: compile-time when possible, runtime otherwise
constexpr int factorial(int n) {
    int result = 1;
    for (int i = 2; i <= n; ++i) result *= i;
    return result;
}

constexpr int c = factorial(5);  // compile-time
int r = factorial(argc);          // runtime

// ✅ consteval: enforce compile-time evaluation
consteval int forced_compiletime(int n) {
    return n * n;
}

constexpr int v = forced_compiletime(42);  // OK
// int v2 = forced_compiletime(argc);      // ERROR: not a constant expression
```

### Compile-time computation for performance

```cpp
// ✅ Good: lookup table generated at compile time
constexpr auto make_crc_table() {
    std::array<uint32_t, 256> table{};
    for (uint32_t i = 0; i < 256; ++i) {
        uint32_t crc = i;
        for (int j = 0; j < 8; ++j) {
            crc = (crc >> 1) ^ (crc & 1 ? 0xEDB88320 : 0);
        }
        table[i] = crc;
    }
    return table;
}

static constexpr auto crc_table = make_crc_table();

// Use at runtime with zero initialization cost
uint32_t crc32(const uint8_t* data, size_t len) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; ++i) {
        crc = (crc >> 8) ^ crc_table[(crc ^ data[i]) & 0xFF];
    }
    return ~crc;
}
```

### constinit for guaranteed static initialization

```cpp
// ✅ Good: prevent static initialization order fiasco
constinit int global_counter = 0;  // guaranteed static init, not dynamic
```

---

## Concurrency

### Protect shared data

```cpp
// ❌ Bad: data race
int counter = 0;
void inc() { counter++; }

// ✅ Good: atomic
std::atomic<int> counter{0};
void inc() { counter.fetch_add(1, std::memory_order_relaxed); }
```

### Use RAII locks

```cpp
std::mutex mu;
std::vector<int> data;

void add(int v) {
    std::lock_guard<std::mutex> lock(mu);
    data.push_back(v);
}
```

### Prefer std::jthread over std::thread (C++20)

```cpp
// ❌ Bad: std::thread requires manual join
void run() {
    std::thread t([]{ do_work(); });
    // forgot to join → std::terminate
}

// ✅ Good: jthread joins automatically on destruction
void run() {
    std::jthread t([](std::stop_token st) {
        while (!st.stop_requested()) {
            do_work();
        }
    });
    // automatically joined; stop token enables cooperative cancellation
}
```

### Structured concurrency with std::execution (future C++26)

Note: As of C++23, use `std::jthread` + `std::stop_token` for cooperative cancellation. The `std::execution` library (P2300) is expected in C++26.

---

## Performance and Allocation

### Avoid repeated allocations

```cpp
// ❌ Bad: repeated reallocation
std::vector<int> build(int n) {
    std::vector<int> out;
    for (int i = 0; i < n; ++i) {
        out.push_back(i);
    }
    return out;
}

// ✅ Good: reserve upfront
std::vector<int> build(int n) {
    std::vector<int> out;
    out.reserve(static_cast<size_t>(n));
    for (int i = 0; i < n; ++i) {
        out.push_back(i);
    }
    return out;
}
```

### String concatenation

```cpp
// ❌ Bad: repeated allocation
std::string join(const std::vector<std::string>& parts) {
    std::string out;
    for (const auto& p : parts) {
        out += p;
    }
    return out;
}

// ✅ Good: reserve total size
std::string join(const std::vector<std::string>& parts) {
    size_t total = 0;
    for (const auto& p : parts) {
        total += p.size();
    }
    std::string out;
    out.reserve(total);
    for (const auto& p : parts) {
        out += p;
    }
    return out;
}
```

### Small Buffer Optimization (SBO)

```cpp
// ✅ Good: avoid heap for small data
void process(const char* name) {
    // Use stack for short names, heap only for long ones
    std::string buf;
    buf.reserve(64);  // typically stays on stack via SSO
    buf = name;
    // ...
}
```

### Use std::span for zero-copy views

```cpp
// ❌ Bad: copies the vector
void process(std::vector<int> data);

// ✅ Good: non-owning view, works with vector, array, C array
void process(std::span<const int> data);

std::vector<int> v = {1, 2, 3};
process(v);             // no copy
int arr[] = {4, 5, 6};
process(arr);           // no copy
```

---

## Templates and Type Safety

### Prefer constrained templates (C++20)

```cpp
// ❌ Bad: overly generic
template <typename T>
T add(T a, T b) {
    return a + b;
}

// ✅ Good: constrained
template <typename T>
requires std::is_integral_v<T>
T add(T a, T b) {
    return a + b;
}
```

### Use static_assert for invariants

```cpp
template <typename T>
struct Packet {
    static_assert(std::is_trivially_copyable_v<T>,
        "Packet payload must be trivially copyable");
    T payload;
};
```

### Avoid template bloat

```cpp
// ❌ Bad: full template instantiation for each T, even if only one method varies
template <typename T>
class Service {
    void connect() { /* 100 lines of identical code */ }
    void process(T item) { /* type-specific */ }
};

// ✅ Good: factor out type-independent code into a non-template base
class ServiceBase {
protected:
    void connect() { /* 100 lines of shared code */ }
};

template <typename T>
class Service : public ServiceBase {
    void process(T item) { /* type-specific */ }
};
```

---

## Testing

### Framework selection

| Framework | Best For |
|-----------|----------|
| **Google Test (GTest)** | Large projects, CI, GMock integration |
| **Catch2** | Header-only, BDD-style, modern C++ |
| **doctest** | Lightweight, single-header, fast compile |

### Google Test basics

```cpp
#include <gtest/gtest.h>
#include "parser.h"

TEST(ParserTest, EmptyInputReturnsNull) {
    auto token = parse("");
    EXPECT_EQ(token, nullptr);
}

TEST(ParserTest, ValidInteger) {
    auto token = parse("42");
    ASSERT_NE(token, nullptr);
    EXPECT_EQ(token->type, TokenType::Int);
    EXPECT_EQ(token->value, 42);
}

TEST(ParserTest, NegativeNumber) {
    auto token = parse("-7");
    ASSERT_NE(token, nullptr);
    EXPECT_EQ(token->value, -7);
}
```

### Test fixtures

```cpp
class DatabaseTest : public ::testing::Test {
protected:
    void SetUp() override {
        db_ = std::make_unique<Database>(":memory:");
        db_->execute("CREATE TABLE users (id INTEGER, name TEXT)");
    }

    void TearDown() override {
        db_.reset();
    }

    std::unique_ptr<Database> db_;
};

TEST_F(DatabaseTest, InsertAndQuery) {
    db_->execute("INSERT INTO users VALUES (1, 'Alice')");
    auto rows = db_->query("SELECT * FROM users");
    ASSERT_EQ(rows.size(), 1);
    EXPECT_EQ(rows[0].get<std::string>("name"), "Alice");
}

TEST_F(DatabaseTest, EmptyTableReturnsNoRows) {
    auto rows = db_->query("SELECT * FROM users");
    EXPECT_TRUE(rows.empty());
}
```

### Mock objects with GMock

```cpp
#include <gmock/gmock.h>

class HttpClient {
public:
    virtual ~HttpClient() = default;
    virtual HttpResponse get(const std::string& url) = 0;
};

class MockHttpClient : public HttpClient {
public:
    MOCK_METHOD(HttpResponse, get, (const std::string& url), (override));
};

TEST(UserServiceTest, FetchesUserProfile) {
    MockHttpClient client;
    EXPECT_CALL(client, get("https://api.example.com/user/1"))
        .WillOnce(Return(HttpResponse{200, R"({"name":"Alice"})"}));

    UserService svc(&client);
    auto profile = svc.get_profile(1);
    EXPECT_EQ(profile.name, "Alice");
}
```

### Test exception safety

```cpp
TEST(AllocatorTest, ThrowsOnOverflow) {
    EXPECT_THROW(allocate(SIZE_MAX), std::bad_alloc);
}

TEST(AllocatorTest, NoLeakOnException) {
    // Run under ASan to verify no leaks when exception is thrown
    try {
        auto buf = allocate(1024);
        throw std::runtime_error("simulated failure");
    } catch (...) {
        // ASan will catch any leaks
    }
}
```

---

## Tooling and Build Checks

```bash
# Warnings
clang++ -Wall -Wextra -Werror -Wconversion -Wshadow -std=c++20 ...

# Sanitizers (debug builds)
clang++ -fsanitize=address,undefined -fno-omit-frame-pointer -g ...
clang++ -fsanitize=thread -fno-omit-frame-pointer -g ...

# Static analysis
clang-tidy src/*.cpp -- -std=c++20

# Formatting
clang-format -i src/*.cpp include/*.h
```

### Recommended compiler flags for safety

```bash
# Strict mode for new code
clang++ -std=c++20 -Wall -Wextra -Werror -Wshadow -Wconversion \
        -Wsign-conversion -Wold-style-cast -Wnon-virtual-dtor \
        -Woverloaded-virtual -Wnull-dereference -Wformat=2 \
        -fsanitize=address,undefined -fno-omit-frame-pointer
```

---

## Review Checklist

### Safety and Lifetime
- [ ] Ownership is explicit (RAII, unique_ptr by default)
- [ ] No dangling references or views
- [ ] Rule of 0/3/5 followed for resource-owning types
- [ ] No raw new/delete in business logic
- [ ] Destructors are noexcept and do not throw
- [ ] Smart pointer types match ownership semantics (unique vs shared vs weak)
- [ ] No shared_ptr cycles (use weak_ptr for back-references)

### API and Design
- [ ] const-correctness is applied consistently
- [ ] Constructors are explicit where needed
- [ ] Override/final used for virtual functions
- [ ] No object slicing (pass by ref or pointer)
- [ ] Concepts constrain template parameters (C++20)

### Modern Features
- [ ] constexpr used for compile-time computation where beneficial
- [ ] Ranges preferred over manual loops for data pipelines (C++20)
- [ ] std::jthread preferred over std::thread for new code (C++20)
- [ ] std::expected used for error handling (C++23) where available

### Concurrency
- [ ] Shared data is protected (mutex or atomics)
- [ ] Locking order is consistent
- [ ] No blocking while holding locks

### Performance
- [ ] Unnecessary allocations avoided (reserve, move, span)
- [ ] Copies avoided in hot paths
- [ ] Algorithmic complexity is reasonable

### Testing and Tooling
- [ ] Unit tests cover happy path, error paths, and edge cases
- [ ] Builds clean with warnings enabled
- [ ] Sanitizers run on critical code paths
- [ ] Static analysis (clang-tidy) results are addressed
