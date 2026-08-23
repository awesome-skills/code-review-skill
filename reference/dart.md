# Dart / Flutter Code Review Guide

> Code review guidelines for Dart 3 and Flutter focusing on widget rebuilds, const constructors, null safety, isolates, async in `build`, Riverpod/Bloc state pitfalls, platform channels, keys, disposal, and testability. Not a language tutorial.

## Table of Contents

- [Widget Rebuilds & Const Constructors](#widget-rebuilds--const-constructors)
- [Null Safety & `late`](#null-safety--late)
- [Isolates](#isolates)
- [Async in `build`](#async-in-build)
- [State Management: Riverpod & Bloc](#state-management-riverpod--bloc)
- [Platform Channels](#platform-channels)
- [Keys](#keys)
- [Disposal & Lifecycle](#disposal--lifecycle)
- [Testability](#testability)
- [Review Checklist](#review-checklist)
- [References](#references)

---

## Widget Rebuilds & Const Constructors

Flutter rebuilds are cheap only when the Element tree can skip work. A review should flag widgets that allocate new subtrees, closures, or Theme lookups on every frame when a `const` constructor or an extracted widget would keep the child Element.

### Prefer `const` constructors where the subtree is static

```dart
// ❌ Bad: every parent rebuild allocates a new Text and Icon.
Widget build(BuildContext context) {
  return Row(
    children: [
      Icon(Icons.star),
      Text('Favorites'),
    ],
  );
}

// ✅ Good: const widgets can be canonicalized and skipped on rebuild.
Widget build(BuildContext context) {
  return const Row(
    children: [
      Icon(Icons.star),
      Text('Favorites'),
    ],
  );
}
```

Review questions:
- Are leaf widgets (`Text`, `Icon`, `SizedBox`, `Padding` with constant insets) `const`?
- Does a missing `const` on a parent block `const` on an entire subtree?
- Is `const` omitted because a single non-const argument (color from `Theme.of`, a closure) poisons the constructor?

### Extract widgets, not helper methods, when state should be isolated

A private method that returns a `Widget` is inlined into the caller's `build`. The returned widgets have no Element identity of their own, so they rebuild whenever the caller rebuilds.

```dart
class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key, required this.user});
  final User user;

  // ❌ Bad: `_header()` rebuilds with ProfilePage even when `user` is unchanged.
  Widget _header() => Header(title: user.name);

  @override
  Widget build(BuildContext context) {
    return Column(children: [_header(), const Feed()]);
  }
}

// ✅ Good: a separate widget gets its own Element; Feed stays const.
class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key, required this.user});
  final User user;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Header(title: user.name),
        const Feed(),
      ],
    );
  }
}
```

### Do not call `setState` for derived values

```dart
// ❌ Bad: derived data stored in State, forcing a rebuild to recompute a getter.
class CartBadge extends StatefulWidget { /* ... */ }

class _CartBadgeState extends State<CartBadge> {
  int _count = 0;

  void didUpdateWidget(CartBadge old) {
    super.didUpdateWidget(old);
    setState(() => _count = widget.items.length);
  }
}

// ✅ Good: derive in build; setState only when the source data changes.
class CartBadge extends StatelessWidget {
  const CartBadge({super.key, required this.items});
  final List<Item> items;

  @override
  Widget build(BuildContext context) {
    return Text('${items.length}');
  }
}
```

### Rebuild scope

- `setState` on a high `State` object rebuilds that subtree. Prefer lifting only the state that must be shared, and wrapping expensive children in `RepaintBoundary` or extracting them.
- `ListView(children: [...])` builds every child. Prefer `ListView.builder` / `SliverList` for long lists.
- Passing a newly allocated `List`/`Map` or a new callback instance into a child that is otherwise `const`-eligible defeats child skip. Capture stable callbacks (`void Function()` stored on State) or use `Widget.canUpdate` identity via `const` / extracted widgets.

For general UI performance patterns see [Performance Review Guide](performance-review-guide.md).

---

## Null Safety & `late`

Dart's null safety is only as strong as the holes the code leaves (`!`, `late`, `as`). Treat those as review signals, not as style.

### Avoid `!` on values the compiler cannot prove

```dart
// ❌ Bad: bang operator hides a possible null and crashes at runtime.
void openProfile(User? user) {
  Navigator.pushNamed(context, '/user/${user!.id}');
}

// ✅ Good: promote with a local or return early.
void openProfile(User? user) {
  final id = user?.id;
  if (id == null) return;
  Navigator.pushNamed(context, '/user/$id');
}
```

### `late` is a delayed crash, not a type

`late` without an initializer throws `LateInitializationError` on first read. `late final` with an initializer is lazy and is the usual legitimate case (expensive, once).

```dart
class Session {
  // ❌ Bad: `late` field is read from another method with no constructor guarantee.
  late String token;

  bool get isReady => token.isNotEmpty;
}

class Session {
  // ✅ Good: nullable until assigned; API makes absence visible.
  String? token;

  bool get isReady => token != null && token!.isNotEmpty;
}

class ThemeCache {
  // ✅ Good: lazy `late final` with initializer; first read computes once.
  late final Map<String, Color> _colors = _loadColors();
}
```

Review questions:
- Is `late` used because the author did not want `?` / a constructor argument?
- Is a `late` field assigned in `initState` but read from a listener that can fire earlier (animation, platform callback)?
- Are `as Foo` casts used where a pattern (`if (x case final Foo foo)`) or `is` promotion would fail loudly and locally?

### Fields do not promote

```dart
class ProfileTile extends StatelessWidget {
  const ProfileTile({super.key, required this.user});
  final User? user;

  @override
  Widget build(BuildContext context) {
    // ❌ Bad: field promotion does not apply; this is a lint (`unchecked_use_of_nullable_value`).
    // return Text(user.name);

    // ✅ Good: promote a local.
    final user = this.user;
    if (user == null) return const SizedBox.shrink();
    return Text(user.name);
  }
}
```

Null-related crashes are still crashes. See [Error Handling Guide](cross-cutting/error-handling-principles.md) for fail-fast vs. swallowing.

---

## Isolates

> 📖 Cross-language concurrency patterns: [Async & Concurrency Guide](cross-cutting/async-concurrency-patterns.md)

Flutter's UI isolate must stay free of heavy JSON, image, and crypto work. Dart isolates do not share memory; messages must be sendable.

### Do not block the UI isolate

```dart
// ❌ Bad: large JSON decode on the UI isolate janks frames.
final users = (jsonDecode(raw) as List)
    .map((e) => User.fromJson(e as Map<String, dynamic>))
    .toList();

// ✅ Good: `Isolate.run` (Dart 2.19+) / `compute` for one-shot work.
final users = await Isolate.run(() {
  return (jsonDecode(raw) as List)
      .map((e) => User.fromJson(e as Map<String, dynamic>))
      .toList();
});
```

### Message restrictions

```dart
// ❌ Bad: closures, ReceivePorts, and many plugin types are not sendable.
await Isolate.run(() => widget.onParsed());

// ✅ Good: send plain data; map back to UI types on the main isolate.
final dto = await Isolate.run(() => parseReport(bytes));
setState(() => report = Report.fromDto(dto));
```

Review questions:
- Is `jsonDecode` / image decode / encryption of non-trivial payloads on the UI isolate?
- Does the isolate callback capture `BuildContext`, `State`, or plugin controllers?
- If a long-lived isolate is spawned, is `kill` / `pause` paired with widget disposal?
- Are isolate failures surfaced, or does `await Isolate.run` lack error handling?

`compute` from `flutter/foundation.dart` is a thin wrapper; prefer `Isolate.run` in Dart-only code. Neither is a thread pool — spawning per tiny call is more expensive than doing the work inline.

---

## Async in `build`

`build` must stay synchronous and side-effect free. Futures created in `build` restart on every rebuild.

### Do not start I/O or create a new `Future` in `build`

```dart
// ❌ Bad: new Future every rebuild; the previous request is abandoned.
Widget build(BuildContext context) {
  return FutureBuilder<Profile>(
    future: api.fetchProfile(id),
    builder: (context, snap) { /* ... */ },
  );
}

// ✅ Good: cache the Future in State; refetch when `id` changes.
class ProfileView extends StatefulWidget {
  const ProfileView({super.key, required this.id});
  final String id;
  @override
  State<ProfileView> createState() => _ProfileViewState();
}

class _ProfileViewState extends State<ProfileView> {
  late Future<Profile> _future = api.fetchProfile(widget.id);

  @override
  void didUpdateWidget(ProfileView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.id != widget.id) {
      _future = api.fetchProfile(widget.id);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Profile>(
      future: _future,
      builder: (context, snap) { /* ... */ },
    );
  }
}
```

Keying `ProfileView` with `ValueKey(id)` also remounts State and starts a new fetch. Either approach is fine; a cached `late final` future with no `didUpdateWidget` goes stale when `id` changes.

The same rule applies to `StreamBuilder`: do not open a new stream in `build`. Create it once (`initState`, a provider, a Bloc) and cancel on dispose.

### `setState` after `await` must check `mounted`

```dart
Future<void> _load() async {
  final data = await api.fetch();
  // ❌ Bad: widget may have been disposed during the await.
  setState(() => _data = data);
}

Future<void> _load() async {
  final data = await api.fetch();
  if (!mounted) return;
  setState(() => _data = data);
}
```

Use `context.mounted` (Flutter 3.7+) before using `BuildContext` after an async gap (`Navigator`, `ScaffoldMessenger`, `showDialog`). The `use_build_context_synchronously` lint exists because this is a crash class, not a style issue.

### Do not mark `build` `async`

```dart
// ❌ Bad: build cannot be async; this does not compile, or a helper is abused.
Widget build(BuildContext context) async {
  final user = await repo.user();
  return Text(user.name);
}

// ✅ Good: hold async state in State / a notifier; build only reads it.
```

Fire-and-forget `unawaited(load())` inside `build` is the same bug with extra steps.

---

## State Management: Riverpod & Bloc

These examples use Riverpod and Bloc because they dominate Flutter reviews. The same pitfalls apply to Provider, GetX, Signals, and raw `InheritedWidget`: rebuild scope, side effects in build, and lifetime.

### Riverpod: `watch` vs `read`, and rebuild scope

```dart
class CartButton extends ConsumerWidget {
  const CartButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // ❌ Bad: watches the whole cart; button rebuilds on every item mutation.
    final cart = ref.watch(cartProvider);

    // ✅ Good: watch only the field this widget needs.
    final count = ref.watch(cartProvider.select((c) => c.items.length));
    return Badge(label: Text('$count'));
  }
}
```

```dart
void onPressed() {
  // ❌ Bad: `watch` in a callback / listener; it is not a rebuild subscription.
  // ref.watch(cartProvider).add(item);

  // ✅ Good: `read` for one-shot, `watch`/`select` only in `build` / `build` of a listen widget.
  ref.read(cartProvider.notifier).add(item);
}
```

Review questions:
- Is `ref.watch` used in `initState`, a gesture handler, or a `Provider`'s constructor?
- Does a widget `watch` a large object when `select` / a derived provider would do?
- Are providers that capture `ref` after `dispose` (`ref.onDispose` missing for controllers, streams)?
- Is `autoDispose` omitted on screen-scoped providers so they leak after pop?

### Bloc: `create` vs `value`, `buildWhen`, closed cubits

`BlocProvider(create: ...)` inside `build` is the documented pattern: `create` runs once per Element, not on every rebuild. `updateShouldNotify` does not control `create`. The bug is constructing a new bloc instance in `build` and handing it to `BlocProvider.value` (no ownership, no dispose, new object every rebuild). Because `create` captures `id` once, a parent that later passes a new `id` will not reload unless the Element remounts or you dispatch an update.

```dart
// ❌ Bad: new ProfileBloc() every rebuild; `value` does not dispose it.
Widget build(BuildContext context) {
  return BlocProvider.value(
    value: ProfileBloc()..add(ProfileStarted(id)),
    child: const ProfileBody(),
  );
}

// ❌ Bad: UniqueKey remounts every rebuild — `create` runs again each time.
Widget build(BuildContext context) {
  return BlocProvider(
    key: UniqueKey(),
    create: (_) => ProfileBloc()..add(ProfileStarted(id)),
    child: const ProfileBody(),
  );
}

// ✅ Good: `create` owns one instance; ValueKey(id) remounts only when id changes.
class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key, required this.id});
  final String id;

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      key: ValueKey(id),
      create: (_) => ProfileBloc()..add(ProfileStarted(id)),
      child: const ProfileBody(),
    );
  }
}
```

Alternatively, keep the same bloc and in `didUpdateWidget` dispatch `ProfileRequested(id)` when `id` changes — do not construct a replacement `ProfileBloc()` there.

```dart
// ❌ Bad: listener work inside builder; also rebuilds on every state.
BlocBuilder<ProfileBloc, ProfileState>(
  builder: (context, state) {
    if (state is ProfileFailure) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ScaffoldMessenger.of(context).showSnackBar(/* ... */);
      });
    }
    return ProfileBody(state: state);
  },
)

// ✅ Good: side effects in BlocListener; rebuilds filtered with buildWhen.
BlocConsumer<ProfileBloc, ProfileState>(
  listenWhen: (p, c) => c is ProfileFailure && p is! ProfileFailure,
  listener: (context, state) {
    final message = (state as ProfileFailure).message;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  },
  buildWhen: (p, c) => p.user != c.user || p.loading != c.loading,
  builder: (context, state) => ProfileBody(state: state),
)
```

Review questions:
- Is a `Cubit`/`Bloc` closed (`BlocProvider` does this if `lazy`/`create` owns it; a manually constructed bloc must `close`)?
- Are events dispatched from `build`?
- Is `Equatable` / `==` missing on state so every `emit` rebuilds even when fields did not change?
- Is business logic in the widget (`context.read<FooBloc>().add` mixed with parsing, I/O) instead of the bloc?

Do not treat GetX `Obx` / `GetBuilder` as exempt: the same "who owns the controller, who rebuilds, who disposes" questions apply.

---

## Platform Channels

Method channels, event channels, and Pigeon are a trust and lifetime boundary. Failures look like "missing plugin" at runtime, not at compile time.

```dart
// ❌ Bad: untyped maps, ignored errors, UI isolate blocked on a heavy native call.
final result = await MethodChannel('app.wallet').invokeMethod('sign', {'tx': raw});
final signature = result as String;

// ✅ Good: typed API (Pigeon or a wrapper), errors handled, no UI-thread assumption.
try {
  final signature = await walletHost.sign(SignRequest(tx: raw));
  if (!mounted) return;
  onSigned(signature);
} on PlatformException catch (e) {
  onSignFailed(e.code, e.message);
}
```

Review questions:
- Is the channel name a collision-prone generic string (`app`, `native`) without a domain prefix?
- Are Android/iOS implementations of the same method covering all argument types and null?
- Does the Dart side assume the plugin is registered (tests, background isolates, and add-to-app engines often are not)?
- Is binary data passed as `List<int>` copies instead of `Uint8List` / Pigeon bytes?
- Are EventChannel subscriptions cancelled in `dispose`?
- Does native code do disk/network work on the platform main thread?

Platform data is untrusted input: validate it the same way you would a network payload. See [Security Review Guide](security-review-guide.md).

---

## Keys

Keys preserve `State` / `Element` identity across rebuilds. Wrong keys cause state to attach to the wrong row; missing keys cause state to reset when the list reorders.

```dart
// ❌ Bad: no keys; after delete/reorder, TextField state sticks to the index.
ListView(
  children: items.map((item) => TodoRow(item: item)).toList(),
)

// ❌ Bad: UniqueKey() in build: every rebuild is a new identity; state is always reset.
TodoRow(key: UniqueKey(), item: item)

// ✅ Good: a stable id from the model.
ListView(
  children: [
    for (final item in items)
      TodoRow(key: ValueKey(item.id), item: item),
  ],
)
```

```dart
// ❌ Bad: GlobalKey created in `build` — a new key every rebuild, plus GlobalKey cost.
Widget build(BuildContext context) {
  final key = GlobalKey<FormState>();
  return Form(key: key, child: /* ... */);
}

// ✅ Good: GlobalKey is rare; hold it on State when FormState is actually needed.
class _EditorState extends State<Editor> {
  final _formKey = GlobalKey<FormState>();
  @override
  Widget build(BuildContext context) => Form(key: _formKey, child: /* ... */);
}
```

Review questions:
- Do reorderable / dismissible / animated lists use `ValueKey` / `ObjectKey` from a stable model id?
- Is `GlobalKey` used to reach into a child's `State` when a callback / `ValueNotifier` would do?
- Are keys on widgets whose `runtimeType` already uniquely identifies them (usually unnecessary)?

---

## Disposal & Lifecycle

Anything with `addListener`, a subscription, a ticker, or a native peer needs a matching `dispose`. Flutter will not save you.

```dart
class SearchField extends StatefulWidget {
  const SearchField({super.key});
  @override
  State<SearchField> createState() => _SearchFieldState();
}

class _SearchFieldState extends State<SearchField> with SingleTickerProviderStateMixin {
  late final TextEditingController _controller;
  late final AnimationController _anim;
  StreamSubscription<Query>? _sub;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController();
    _anim = AnimationController(vsync: this, duration: const Duration(milliseconds: 200));
    _sub = queryStream.listen((q) {
      if (mounted) _controller.text = q.text;
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    _anim.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => TextField(controller: _controller);
}
```

Review questions:
- `TextEditingController`, `ScrollController`, `FocusNode`, `AnimationController`, `TabController`, `PageController` — created? disposed?
- `StreamSubscription`, `Timer`, `ChangeNotifier` listeners, `WidgetsBindingObserver` — removed?
- `AnimationController` uses a `TickerProvider` that dies with the `State` (`SingleTickerProviderStateMixin`), not a leaked vsync?
- Route-level controllers created in `BlocProvider`/`Provider` — `dispose` callback set?
- `Image.network` / video / camera controllers stopped when the route is covered, not only when popped?

`dispose` must not use `BuildContext` (the element is unmounted). Do not call `setState` there.

---

## Testability

Review the tests the same way as the product code. Flutter tests that pump the whole app to assert a string are a smell that logic is trapped in widgets.

```dart
// ❌ Bad: parsing and I/O live in the widget; tests must pump and mock everything.
class PriceLabel extends StatelessWidget {
  const PriceLabel({super.key, required this.raw});
  final String raw;

  @override
  Widget build(BuildContext context) {
    final n = NumberFormat.simpleCurrency().parse(raw);
    return Text(n.toString());
  }
}

// ✅ Good: pure function / mapper is unit-tested; widget only renders.
String formatPrice(String raw, NumberFormat format) => format.format(format.parse(raw));

class PriceLabel extends StatelessWidget {
  const PriceLabel({super.key, required this.text});
  final String text;

  @override
  Widget build(BuildContext context) => Text(text);
}
```

```dart
// ❌ Bad: test depends on real time and network.
testWidgets('loads profile', (tester) async {
  await tester.pumpWidget(const ProfilePage(id: '1'));
  await tester.pumpAndSettle();
  expect(find.text('Ada'), findsOneWidget);
});

// ✅ Good: inject a fake; pump until the Future you control completes.
testWidgets('loads profile', (tester) async {
  final api = FakeProfileApi()..completeWith(Profile(name: 'Ada'));
  await tester.pumpWidget(ProfilePage(id: '1', api: api));
  await tester.pump();
  expect(find.text('Ada'), findsOneWidget);
});
```

Review questions:
- Can the new logic be tested with `flutter test` without `IntegrationTestWidgetsFlutterBinding`?
- Are `Key`s present on interactive widgets the test (and the reviewer) needs to find, without painting `UniqueKey` in `build`?
- Are platform channels mocked (`TestDefaultBinaryMessengerBinding`)?
- Does `pumpAndSettle` hang because an infinite animation / polling stream never idles?
- Is `late` in tests hiding missing setup?

---

## Review Checklist

### Widgets & rebuilds
- [ ] Static subtrees use `const` constructors
- [ ] Expensive children are extracted widgets, not `_buildFoo()` methods
- [ ] Long lists use lazy builders, not a fully-materialized `children:` list
- [ ] `setState` is not used to store values that can be derived in `build`

### Null safety & `late`
- [ ] `!` and `as` are not used to silence the type system
- [ ] `late` is lazy-init (`late final x = ...`) or truly guaranteed before first read
- [ ] Nullable fields are promoted via locals, not assumed non-null

### Isolates & async
- [ ] Heavy JSON / image / crypto work is off the UI isolate
- [ ] Isolate messages are sendable plain data
- [ ] `build` does not create Futures/Streams or start I/O
- [ ] `FutureBuilder`/`StreamBuilder` reuse a cached future/stream; refetch when the id/input changes
- [ ] `setState` / `BuildContext` after `await` check `mounted` / `context.mounted`

### State management
- [ ] `ref.watch` / `context.watch` only in `build`; `read` in callbacks
- [ ] Rebuilds are narrowed (`select`, `buildWhen`)
- [ ] Do not construct a `Bloc`/`Cubit`/`ChangeNotifier` in `build` and pass it to `*.value` — use `create`; key with `ValueKey(id)` (not `UniqueKey()`) or `didUpdateWidget` so a new id reloads
- [ ] Providers/blocs that own controllers are disposed (`autoDispose`, `close`)

### Platform, keys, disposal
- [ ] Platform channel calls handle `PlatformException` and missing plugins
- [ ] EventChannel / native subscriptions are cancelled
- [ ] List children that hold `State` have stable `ValueKey`s (not `UniqueKey()` in `build`)
- [ ] Controllers, tickers, and subscriptions are disposed; `dispose` does not use `context`

### Tests
- [ ] Domain logic is unit-tested without pumping widgets
- [ ] Widget tests inject fakes; they do not hit network or real platform channels
- [ ] `pumpAndSettle` is not used on never-idle animations

---

## References

- [Dart language tour (null safety)](https://dart.dev/null-safety)
- [Effective Dart](https://dart.dev/effective-dart)
- [Flutter performance: best practices](https://docs.flutter.dev/perf/best-practices)
- [FutureBuilder class](https://api.flutter.dev/flutter/widgets/FutureBuilder-class.html)
- [Isolate.run](https://api.dart.dev/stable/dart-isolate/Isolate/run.html)
- [Riverpod: Refs (`watch` vs `read`)](https://riverpod.dev/docs/concepts2/refs)
- [Bloc: BlocListener vs BlocBuilder](https://bloclibrary.dev/bloc-concepts/)
- [Key class](https://api.flutter.dev/flutter/foundation/Key-class.html)
- [Error Handling Guide](cross-cutting/error-handling-principles.md)
- [Async & Concurrency Guide](cross-cutting/async-concurrency-patterns.md)
- [Performance Review Guide](performance-review-guide.md)
- [Security Review Guide](security-review-guide.md)
