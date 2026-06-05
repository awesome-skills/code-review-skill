# Swift Code Review Guide

A code review checklist for modern Swift (5.9+/6), covering SwiftUI, Swift Concurrency, and the Swift API Design Guidelines.

## Quick Review Checklist

### Must-Check Items
- [ ] Are force-unwraps (`!`) and `try!` avoided in favor of safe unwrapping
- [ ] Do closures that capture `self` use `[weak self]` to avoid retain cycles
- [ ] Is the value vs reference type choice intentional (struct vs class)
- [ ] Are errors propagated with `throws`/`Result` instead of being swallowed
- [ ] Are concurrency boundaries data-race-safe (`Sendable`, `@MainActor`, actors)

### Common Issues
- [ ] Fire-and-forget `Task {}` that leaks or is never cancelled
- [ ] Wrong SwiftUI property wrapper (`@ObservedObject` where `@StateObject` is needed)
- [ ] O(n^2) lookups in loops that could use a `Set` or `Dictionary`
- [ ] Implicitly unwrapped optionals (`var x: T!`) outside of IBOutlets
- [ ] Over-broad access control (`public`/`open` where `internal` suffices)
- [ ] Naming that ignores the Swift API Design Guidelines

---

## 1. Optionals and Unwrapping

### 1.1 Avoid Force-Unwrapping

```swift
// ❌ Wrong: crashes at runtime if nil
let name = user.name!
let url = URL(string: urlString)!

// ✅ Correct: bind with guard let / if let
guard let name = user.name else {
    return
}

if let url = URL(string: urlString) {
    load(url)
}
```

### 1.2 Use Nil-Coalescing for Defaults

```swift
// ❌ Wrong: verbose and crash-prone
let count: Int
if let c = dictionary["count"] {
    count = c
} else {
    count = 0
}

// ✅ Correct: nil-coalescing
let count = dictionary["count"] ?? 0
```

### 1.3 Prefer guard let for Early Exit

```swift
// ❌ Wrong: deep nesting (pyramid of doom)
func process(_ input: String?) {
    if let input = input {
        if let value = Int(input) {
            if value > 0 {
                handle(value)
            }
        }
    }
}

// ✅ Correct: guard keeps the happy path unindented
func process(_ input: String?) {
    guard let input,
          let value = Int(input),
          value > 0 else {
        return
    }
    handle(value)
}
```

### 1.4 Avoid Implicitly Unwrapped Optionals

```swift
// ❌ Wrong: T! is a hidden force-unwrap on every access
class ViewModel {
    var service: NetworkService!
}

// ✅ Correct: inject a non-optional dependency
class ViewModel {
    private let service: NetworkService

    init(service: NetworkService) {
        self.service = service
    }
}
```

### 1.5 Use Optional Chaining and map/flatMap

```swift
// ❌ Wrong: manual unwrapping just to transform
var initial: String?
if let name = user.name {
    initial = String(name.prefix(1))
}

// ✅ Correct: optional chaining + map
let initial = user.name.map { String($0.prefix(1)) }

// ✅ Correct: flatMap to avoid double optionals
let port: Int? = components.port.flatMap { Int(exactly: $0) }
```

---

## 2. Memory Management and Retain Cycles

### 2.1 Use [weak self] in Escaping Closures

```swift
// ❌ Wrong: closure strongly captures self, creating a retain cycle
class ImageLoader {
    var onComplete: (() -> Void)?

    func load() {
        service.fetch { data in
            self.cache = data   // self is retained by the closure
            self.onComplete?()
        }
    }
}

// ✅ Correct: capture self weakly and guard
class ImageLoader {
    var onComplete: (() -> Void)?

    func load() {
        service.fetch { [weak self] data in
            guard let self else { return }
            self.cache = data
            self.onComplete?()
        }
    }
}
```

### 2.2 weak vs unowned

```swift
// ✅ Use weak when the reference can legitimately become nil
class Controller {
    weak var delegate: ControllerDelegate?
}

// ✅ Use unowned only when the captured object is guaranteed to
//    outlive the closure (e.g. self owns the closure tightly).
//    unowned crashes if accessed after deallocation.
class Owner {
    lazy var describe: () -> String = { [unowned self] in
        self.name
    }
    let name = "owner"
}

// ❌ Wrong: unowned on something that can outlive self -> crash
networkClient.onResponse = { [unowned self] in self.update() }
// Prefer [weak self] here, since onResponse may fire after self is gone.
```

### 2.3 Break Delegate Retain Cycles

```swift
// ❌ Wrong: strong delegate keeps both objects alive forever
protocol DataSourceDelegate: AnyObject {}

class DataSource {
    var delegate: DataSourceDelegate?   // strong by default
}

// ✅ Correct: delegates should be weak (and protocol AnyObject-bound)
class DataSource {
    weak var delegate: DataSourceDelegate?
}
```

### 2.4 Closures Stored as Properties

```swift
// ❌ Wrong: stored closure captures self strongly -> permanent cycle
class Timer {
    var tick: (() -> Void)!
    func configure() {
        tick = { self.count += 1 }
    }
    var count = 0
}

// ✅ Correct: weak capture for stored closures referencing self
class Timer {
    var tick: (() -> Void)?
    func configure() {
        tick = { [weak self] in self?.count += 1 }
    }
    var count = 0
}
```

---

## 3. Value vs Reference Types

### 3.1 Prefer Structs by Default

```swift
// ✅ Use a struct for data/models with value semantics
struct Coordinate {
    var latitude: Double
    var longitude: Double
}

// Copies are independent; no shared mutable state, thread-friendly.
var a = Coordinate(latitude: 1, longitude: 2)
var b = a
b.latitude = 99   // a is unchanged
```

### 3.2 Use a Class for Identity or Shared State

```swift
// ✅ Use a class when instances have identity or must be shared/mutated
//    by reference, or when you need inheritance / Objective-C interop.
final class DatabaseConnection {
    private(set) var isOpen = false
    func open() { isOpen = true }
}

// Two references point to the same connection.
let conn1 = DatabaseConnection()
let conn2 = conn1
conn1.open()
// conn2.isOpen == true
```

### 3.3 Mark Classes final When Not Subclassed

```swift
// ❌ Wrong: open to subclassing unintentionally (slower dispatch, fragile API)
class UserViewModel {}

// ✅ Correct: final enables static dispatch and signals intent
final class UserViewModel {}
```

### 3.4 Beware Reference Types Inside Structs

```swift
// ❌ Surprising: struct copy still shares the inner class instance
final class Box { var value = 0 }
struct Container { var box = Box() }

var x = Container()
var y = x
y.box.value = 42   // x.box.value is also 42 (shared reference!)

// ✅ Correct: use value semantics throughout, or copy on write deliberately
struct Container {
    var value = 0   // plain value type, copies are independent
}
```

---

## 4. Error Handling

### 4.1 Avoid try! and try?

```swift
// ❌ Wrong: try! crashes on any thrown error
let data = try! Data(contentsOf: url)

// ❌ Often wrong: try? silently discards the error and the cause
let data = try? Data(contentsOf: url)   // data is nil, you lose "why"

// ✅ Correct: propagate or handle with do-catch
do {
    let data = try Data(contentsOf: url)
    process(data)
} catch {
    log.error("failed to read \(url): \(error)")
}
```

### 4.2 Define Meaningful Error Types

```swift
// ✅ Recommended: an Error enum communicates failure modes precisely
enum NetworkError: Error {
    case invalidURL
    case unauthorized
    case server(statusCode: Int)
    case decoding(underlying: Error)
}

func fetch(_ path: String) throws -> Data {
    guard let url = URL(string: path) else {
        throw NetworkError.invalidURL
    }
    // ...
}
```

### 4.3 Use Result for Stored or Deferred Outcomes

```swift
// ✅ Result is useful at callback boundaries or when storing an outcome
func load(completion: @escaping (Result<User, NetworkError>) -> Void) {
    // completion(.success(user)) or completion(.failure(.unauthorized))
}

// ✅ Convert between Result and throws as needed
let user = try result.get()
```

### 4.4 Typed Throws (Swift 6)

```swift
// ✅ Typed throws constrains the error type when it is fully known.
//    Use it for closed, exhaustive error domains; prefer untyped
//    `throws` for library APIs that may grow new error cases.
func parse(_ raw: String) throws(ParsingError) -> Token {
    guard let token = Token(raw) else {
        throw ParsingError.malformed
    }
    return token
}

do {
    let token = try parse(input)
} catch {
    // `error` is statically known to be ParsingError
    handle(error)
}
```

### 4.5 Don't Catch and Rethrow Without Value

```swift
// ❌ Wrong: catch that adds nothing but obscures the trace
do {
    try work()
} catch {
    throw error   // pointless
}

// ✅ Correct: only catch to add context or recover
do {
    try work()
} catch {
    throw AppError.workFailed(underlying: error)
}
```

---

## 5. Swift Concurrency

### 5.1 Prefer async/await Over Nested Callbacks

```swift
// ❌ Wrong: callback pyramid, error handling scattered
func loadProfile(completion: @escaping (Result<Profile, Error>) -> Void) {
    fetchUser { userResult in
        switch userResult {
        case .success(let user):
            fetchAvatar(user) { avatarResult in /* ... */ }
        case .failure(let error):
            completion(.failure(error))
        }
    }
}

// ✅ Correct: linear async/await
func loadProfile() async throws -> Profile {
    let user = try await fetchUser()
    let avatar = try await fetchAvatar(user)
    return Profile(user: user, avatar: avatar)
}
```

### 5.2 Use @MainActor for UI State

```swift
// ❌ Wrong: mutating UI state from a background context (data race / crash)
func refresh() async {
    let items = try? await api.load()
    self.items = items ?? []   // may run off the main thread
}

// ✅ Correct: isolate UI-facing types to the main actor
@MainActor
final class FeedViewModel: ObservableObject {
    @Published var items: [Item] = []

    func refresh() async {
        let loaded = (try? await api.load()) ?? []
        items = loaded   // guaranteed on the main actor
    }
}
```

### 5.3 Protect Mutable State with Actors

```swift
// ❌ Wrong: shared mutable state without synchronization (data race)
final class Counter {
    var value = 0
    func increment() { value += 1 }
}

// ✅ Correct: an actor serializes access to its mutable state
actor Counter {
    private(set) var value = 0
    func increment() { value += 1 }
}

let counter = Counter()
await counter.increment()   // access is awaited and serialized
```

### 5.4 Conform Shared Types to Sendable

```swift
// ❌ Wrong: passing a non-Sendable class across actors (Swift 6 error)
final class Config {        // mutable, not Sendable
    var retries = 3
}

// ✅ Correct: make shared types Sendable (immutable value type is ideal)
struct Config: Sendable {
    let retries: Int
}

// ✅ For reference types, use final + immutable stored properties,
//    or @unchecked Sendable only with manual synchronization.
final class Cache: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [String: Data] = [:]
    // all access guarded by lock
}
```

### 5.5 Handle Task Cancellation

```swift
// ❌ Wrong: ignores cancellation, keeps working after the view is gone
func search(_ query: String) async -> [Result] {
    var results: [Result] = []
    for page in 0..<100 {
        results += await fetchPage(query, page)   // never stops
    }
    return results
}

// ✅ Correct: check for cancellation cooperatively
func search(_ query: String) async throws -> [Result] {
    var results: [Result] = []
    for page in 0..<100 {
        try Task.checkCancellation()
        results += try await fetchPage(query, page)
    }
    return results
}
```

### 5.6 Don't Leak Fire-and-Forget Tasks

```swift
// ❌ Wrong: unstructured Task with no handle, never cancelled
final class ViewModel {
    func onAppear() {
        Task {
            await self.stream()   // runs forever even after dismissal
        }
    }
}

// ✅ Correct: retain the handle and cancel it (or use .task in SwiftUI)
final class ViewModel {
    private var streamTask: Task<Void, Never>?

    func onAppear() {
        streamTask = Task { [weak self] in
            await self?.stream()
        }
    }

    func onDisappear() {
        streamTask?.cancel()
    }
}
```

### 5.7 Use Structured Concurrency for Parallelism

```swift
// ❌ Wrong: sequential awaits where work could run concurrently
let a = await loadA()
let b = await loadB()   // waits for A to finish first

// ✅ Correct: async let runs them concurrently
async let a = loadA()
async let b = loadB()
let (resultA, resultB) = await (a, b)

// ✅ For a dynamic number of children, use a task group
try await withThrowingTaskGroup(of: Item.self) { group in
    for id in ids {
        group.addTask { try await fetch(id) }
    }
    for try await item in group {
        store(item)
    }
}
```

---

## 6. SwiftUI

### 6.1 Choose the Right State Wrapper

```swift
// ✅ @State: simple value-type state owned by this view
struct Toggle: View {
    @State private var isOn = false
    var body: some View { /* ... */ }
}

// ✅ @StateObject: the view CREATES and OWNS a reference-type model
struct ProfileScreen: View {
    @StateObject private var model = ProfileViewModel()
    var body: some View { /* ... */ }
}

// ✅ @ObservedObject: the model is OWNED elsewhere and passed in
struct ProfileHeader: View {
    @ObservedObject var model: ProfileViewModel
    var body: some View { /* ... */ }
}

// ✅ @Binding: a two-way reference to state owned by a parent
struct SearchField: View {
    @Binding var text: String
    var body: some View { /* ... */ }
}
```

### 6.2 @StateObject vs @ObservedObject

```swift
// ❌ Wrong: @ObservedObject for an object the view itself creates.
//    SwiftUI may recreate the view, re-instantiating the model and
//    losing its state on every re-render.
struct CounterView: View {
    @ObservedObject var model = CounterModel()   // recreated unexpectedly
}

// ✅ Correct: @StateObject ties the model's lifetime to the view
struct CounterView: View {
    @StateObject private var model = CounterModel()
}
```

### 6.3 Preserve View Identity

```swift
// ❌ Wrong: index-based id reuses identity when the array reorders,
//    causing wrong animations and stale state.
ForEach(0..<items.count, id: \.self) { i in
    ItemRow(item: items[i])
}

// ✅ Correct: use a stable, unique identifier
ForEach(items) { item in   // Item: Identifiable
    ItemRow(item: item)
}

// ✅ Use .id(...) to deliberately reset a view's state
ProfileView(user: user)
    .id(user.id)   // new identity per user -> fresh state
```

### 6.4 Avoid Over-Rendering

```swift
// ❌ Wrong: a single huge body re-renders everything on any change
struct Dashboard: View {
    @ObservedObject var model: DashboardModel
    var body: some View {
        VStack {
            // header + heavy chart + list all recompute together
        }
    }
}

// ✅ Correct: extract subviews so only the affected part re-renders.
//    Each child observes only the state it needs.
struct Dashboard: View {
    var body: some View {
        VStack {
            HeaderView()
            ChartView()
            ItemList()
        }
    }
}
```

### 6.5 Do Async Work with .task

```swift
// ❌ Wrong: kicking off work in onAppear without cancellation
.onAppear {
    Task { await model.load() }   // not cancelled when view disappears
}

// ✅ Correct: .task is tied to the view's lifetime and auto-cancels
.task {
    await model.load()
}

// ✅ Re-run when an input changes
.task(id: query) {
    await model.search(query)
}
```

---

## 7. Protocols and Generics

### 7.1 Protocol-Oriented Design

```swift
// ✅ Compose behavior with protocols and default implementations
protocol Identifiable2 {
    var id: String { get }
}

protocol Describable {
    var description: String { get }
}

extension Describable {
    var description: String { "no description" }   // default
}
```

### 7.2 Prefer some Over any

```swift
// ❌ Slower: `any` is an existential box with dynamic dispatch
func makeShape() -> any Shape { Circle() }

// ✅ Faster: `some` is an opaque type resolved at compile time,
//    preserving the concrete type and enabling static dispatch.
func makeShape() -> some Shape { Circle() }

// Use `any` only when you genuinely need heterogeneous values:
let shapes: [any Shape] = [Circle(), Square()]
```

### 7.3 Generic Constraints Over Existentials

```swift
// ❌ Wrong: existential parameter loses the concrete type and is slower
func logTotal(_ items: [any Numeric]) {
    // awkward: the concrete numeric type is erased, so arithmetic needs casts
}

// ✅ Correct: a generic constraint keeps full type information
func total<T: Numeric>(_ items: [T]) -> T {
    items.reduce(.zero, +)
}
```

### 7.4 Associated Types with Primary Associated Types

```swift
// ✅ Primary associated types (Swift 5.7+) allow lightweight constraints
protocol Container<Item> {
    associatedtype Item
    var count: Int { get }
    subscript(_ index: Int) -> Item { get }
}

// Constrain the element type without a where-clause:
func first(in container: some Container<Int>) -> Int {
    container[0]
}
```

---

## 8. Access Control and API Design

### 8.1 Use the Narrowest Access Level

```swift
// ❌ Wrong: everything public exposes internal details as API surface
public class Service {
    public var cache: [String: Data] = [:]
    public func reset() {}
}

// ✅ Correct: expose only the intended API; hide the rest
public final class Service {
    private var cache: [String: Data] = [:]
    public func reset() { cache.removeAll() }
}
```

### 8.2 private vs fileprivate vs internal vs public/open

```swift
// private:     visible only within the enclosing declaration (and its extensions in the same file)
// fileprivate: visible within the same source file
// internal:    visible within the module (the default)
// public:      visible outside the module, but not subclassable/overridable
// open:        visible outside the module AND subclassable/overridable

// ✅ Use private(set) to expose read-only state
public final class Account {
    public private(set) var balance: Decimal = 0
}
```

### 8.3 Follow the Swift API Design Guidelines

```swift
// ❌ Wrong: redundant words, unclear argument roles
func insertObject(_ object: Element, atIndex index: Int)
list.removeElement(at: 0)

// ✅ Correct: read at the call site like a phrase; omit needless words
func insert(_ element: Element, at index: Int)
list.insert(item, at: 0)        // reads as "insert item at 0"
list.remove(at: 0)

// ✅ Boolean properties read as assertions
var isEmpty: Bool
var hasChanges: Bool
```

### 8.4 Name Methods by Side Effects

```swift
// ✅ Mutating verb vs non-mutating noun pairs (the "ed/ing" rule)
var sorted = array.sorted()   // returns a new value (non-mutating)
array.sort()                  // mutates in place (imperative verb)

let reversed = text.reversed()
text.reverse()
```

---

## 9. Collections and Functional Style

### 9.1 Prefer map/filter/compactMap

```swift
// ❌ Verbose: manual loop with mutable accumulator
var names: [String] = []
for user in users {
    if user.isActive {
        names.append(user.name)
    }
}

// ✅ Correct: declarative transform
let names = users.filter(\.isActive).map(\.name)
```

### 9.2 compactMap to Drop nils

```swift
// ❌ Wrong: map leaves an [Int?] you then have to unwrap
let numbers = strings.map { Int($0) }   // [Int?]

// ✅ Correct: compactMap removes nils and unwraps
let numbers = strings.compactMap { Int($0) }   // [Int]
```

### 9.3 Avoid O(n^2) Membership Checks

```swift
// ❌ Wrong: contains on an Array is O(n); the loop is O(n*m)
let result = candidates.filter { blocked.contains($0) }   // blocked: [ID]

// ✅ Correct: a Set makes membership O(1)
let blockedSet = Set(blocked)
let result = candidates.filter { blockedSet.contains($0) }
```

### 9.4 reduce and Dictionary Grouping

```swift
// ✅ Group with Dictionary(grouping:)
let byFirstLetter = Dictionary(grouping: words) { $0.first }

// ❌ Wrong: reduce(into:) is preferred over reduce that copies each step
let total = numbers.reduce(0) { $0 + $1 }   // fine for scalars

// ✅ Use reduce(into:) when accumulating into a collection (avoids copies)
let counts = words.reduce(into: [:]) { acc, word in
    acc[word, default: 0] += 1
}
```

### 9.5 Use lazy for Chained Transforms on Large Sequences

```swift
// ❌ Wrong: each step allocates an intermediate array
let firstMatch = bigArray.map(expensive).filter(isValid).first

// ✅ Correct: lazy avoids intermediate arrays and stops early
let firstMatch = bigArray.lazy.map(expensive).filter(isValid).first
```

---

## 10. Testing

### 10.1 Arrange-Act-Assert with XCTest

```swift
import XCTest
@testable import MyApp

final class PriceCalculatorTests: XCTestCase {
    func testDiscountApplied() {
        // Arrange
        let calculator = PriceCalculator(discount: 0.1)
        // Act
        let total = calculator.total(for: 100)
        // Assert
        XCTAssertEqual(total, 90, accuracy: 0.001)
    }
}
```

### 10.2 Testing async Code

```swift
// ✅ Mark the test method async and await directly
func testFetchUser() async throws {
    let service = UserService(client: MockClient())
    let user = try await service.fetchUser(id: "42")
    XCTAssertEqual(user.id, "42")
}

// ✅ Assert that an async call throws the expected error
func testFetchUserUnauthorized() async {
    let service = UserService(client: UnauthorizedClient())
    do {
        _ = try await service.fetchUser(id: "42")
        XCTFail("expected to throw")
    } catch NetworkError.unauthorized {
        // expected
    } catch {
        XCTFail("unexpected error: \(error)")
    }
}
```

### 10.3 Inject Dependencies via Protocols

```swift
// ✅ Depend on a protocol so tests can substitute a mock
protocol HTTPClient {
    func get(_ url: URL) async throws -> Data
}

struct MockClient: HTTPClient {
    var result: Result<Data, Error>
    func get(_ url: URL) async throws -> Data {
        try result.get()
    }
}
```

### 10.4 Avoid Sleeps; Await Expectations or Values

```swift
// ❌ Wrong: arbitrary sleep makes tests slow and flaky
func testCallback() {
    var done = false
    object.run { done = true }
    Thread.sleep(forTimeInterval: 1)
    XCTAssertTrue(done)
}

// ✅ Correct: use XCTestExpectation for callback APIs
func testCallback() {
    let expectation = expectation(description: "callback fired")
    object.run { expectation.fulfill() }
    wait(for: [expectation], timeout: 1.0)
}

// ✅ Better: refactor to async and await the value directly
func testCallback() async {
    let value = await object.run()
    XCTAssertEqual(value, expected)
}
```

---

## References

- [Swift API Design Guidelines](https://www.swift.org/documentation/api-design-guidelines/)
- [The Swift Programming Language](https://docs.swift.org/swift-book/)
- [Swift Concurrency (TSPL)](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/)
- [Migrating to Swift 6](https://www.swift.org/migration/documentation/migrationguide/)
- [Apple: Managing Model Data in Your App (SwiftUI)](https://developer.apple.com/documentation/swiftui/managing-model-data-in-your-app)
- [Apple: Automatic Reference Counting](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/automaticreferencecounting/)
- [WWDC: Protocol-Oriented Programming in Swift](https://developer.apple.com/videos/play/wwdc2015/408/)
- [Swift Evolution](https://github.com/apple/swift-evolution)
