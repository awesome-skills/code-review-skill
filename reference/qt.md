# Qt Code Review Guide

> Code review guidelines for Qt 5.15 LTS and Qt 6 (6.2–6.8+) focusing on `QObject` ownership, event-loop reentrancy, signals/slots, implicit sharing, threads, Model/View, QML boundaries, I/O security, CMake/Qt6 migration, and testing. For general C++17/20 RAII and lifetime rules, see [C++ Guide](cpp.md).

## Table of Contents

- [Scope & Version Awareness](#scope--version-awareness)
- [Object Model & Memory Management](#object-model--memory-management)
- [Event Loop & Reentrancy Hazards](#event-loop--reentrancy-hazards)
- [Signals, Slots & Property Bindings](#signals-slots--property-bindings)
- [Containers & Strings](#containers--strings)
- [Threads & Concurrency](#threads--concurrency)
- [GUI, Widgets & Painting](#gui-widgets--painting)
- [Model/View Architecture](#modelview-architecture)
- [Meta-Object System](#meta-object-system)
- [QML / Qt Quick](#qml--qt-quick)
- [Networking, I/O, Process & Security](#networking-io-process--security)
- [Qt5 → Qt6 Migration](#qt5--qt6-migration)
- [Testing & Static Analysis](#testing--static-analysis)
- [Review Checklist](#review-checklist)
- [References](#references)

---

## Scope & Version Awareness

Before applying version-specific feedback, inspect `CMakeLists.txt` or `.pro` files (`find_package(Qt6 ...)` vs `Qt5`), the minimum Qt version (`qt_standard_project_setup(REQUIRES ...)`), and the configured C++ standard (Qt 6 requires C++17+).

- **Do not demand Qt 6-only APIs** (`u"..."_s`, `QBindable`, `qt_add_qml_module`) in repositories still targeting Qt 5.15 LTS unless migration is in scope.
- **Separate correctness/lifetime bugs** (`🔴 [blocking]`, such as dangling lambda captures, cross-thread widget access, or `QObject` double ownership) from modernization suggestions (`🟢 [nit]`).

---

## Object Model & Memory Management

### Pass the Parent in the Constructor

Qt's `QObject` hierarchy automatically deletes children when their parent is destroyed. Prefer passing the parent directly to the constructor over post-hoc `setParent()` or manual `delete`.

On `QWidget`, calling `setParent()` after construction also resets window flags and hides the widget (`setVisible(false)`), requiring an explicit `show()` if the parent is already visible. Adding a widget to a `QLayout` automatically reparents it to the layout's owning widget.

```cpp
// ❌ Bad: unparented allocation leaks on early return; setParent() hides visible widgets
QWidget* panel = new QWidget();
QLabel* title = new QLabel();
if (!initData()) return; // leaks both panel and title!
title->setParent(panel);

// ✅ Good: ownership established immediately at construction
auto* panel = new QWidget(this); // owned by 'this'
auto* layout = new QVBoxLayout(panel);
auto* title = new QLabel(tr("Overview"), panel);
layout->addWidget(title);
```

### Prevent Session-Lifetime Leaks in Long-Lived Parents

Parent ownership prevents process-exit leaks, **not** session-lifetime memory growth. Allocating transient child objects (dialogs, menus, replies, jobs) with `MainWindow` as parent inside repeatable slots accumulates one instance per user action until the window closes.

```cpp
// ❌ Bad: every click allocates another SettingsDialog kept alive by MainWindow
void MainWindow::openSettings() {
    auto* dialog = new SettingsDialog(this);
    dialog->open();
}

// ✅ Good: parent cleans up on shutdown; WA_DeleteOnClose frees it when closed
void MainWindow::openSettings() {
    auto* dialog = new SettingsDialog(this);
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    connect(dialog, &QDialog::accepted, this, [this, dialog]() {
        applySettings(dialog->settings());
    });
    dialog->open();
}
```

### Avoid Double Ownership (`parent` + Smart Pointer / Stack)

Combining Qt parent ownership with `std::unique_ptr` or stack allocation causes a double-free or invalid `delete` on a stack address (`🔴 [blocking]`).

```cpp
// ❌ Bad: both 'this' (~QObject) and std::unique_ptr will delete dialog -> double free
auto dialog = std::make_unique<QDialog>(this);

// ❌ Bad: if parent 'this' is destroyed before scope exit, ~QObject calls delete on stack address!
QLabel statusLabel(this);

// ✅ Good: heap-allocate parented QObjects; use std::unique_ptr only when parent() == nullptr
auto* dialog = new QDialog(this);
dialog->setAttribute(Qt::WA_DeleteOnClose);
```

### Smart Pointers and `QPointer` for Parentless `QObject`s

When a `QObject` has no parent, prefer `std::unique_ptr` (recommended over legacy `QScopedPointer` in Qt 6). If destruction may happen inside a slot or across threads, use a `deleteLater()` custom deleter (requires an active event loop on the object's thread). Avoid `std::shared_ptr<QObject>` unless ownership is genuinely shared outside the `QObject` tree.

```cpp
#include <QObject>
#include <QPointer>
#include <memory>

struct QObjectDeleteLater {
    void operator()(QObject* obj) const noexcept {
        if (obj) obj->deleteLater();
    }
};

template <typename T>
using UniqueQObjectPtr = std::unique_ptr<T, QObjectDeleteLater>;

// ✅ Good: single-owner parentless QObject safe to reset from slots
UniqueQObjectPtr<MyService> service(new MyService());

// ✅ Good: non-owning guarded pointer (clears to nullptr on same-thread destruction)
QPointer<MyService> safeObserver = service.get();
if (safeObserver) {
    safeObserver->refresh();
}
```

> **Note:** `QPointer<T>` is **not** thread-safe against concurrent destruction on another thread; use queued signals/slots instead of polling `QPointer` across threads.

### Use `deleteLater()` Inside Slots and Event Handlers

Deleting a sender or `this` synchronously inside a slot or event handler can invalidate objects still on the call stack inside `QMetaObject::activate` or `QApplication::notify` (`🔴 [blocking]`).

```cpp
// ❌ Bad: synchronous delete inside a slot may UAF the active signal emission chain
void DownloadTask::onFinished() {
    delete this; // UB if caller or Qt internals access 'this' after slot returns
}

// ✅ Good: defer destruction until control returns to the event loop
void DownloadTask::onFinished() {
    deleteLater();
}
```

---

## Event Loop & Reentrancy Hazards

### Never Call `QCoreApplication::processEvents()` to Mask Slow Code

Calling `QCoreApplication::processEvents()` inside a slot or loop re-enters the event dispatcher: user clicks, timers, socket callbacks, and queued `deleteLater()` events can run mid-function and destroy `this` before `processEvents()` returns (`🔴 [blocking]`).

```cpp
// ❌ Bad: reentrant event processing can close the widget and destroy 'this' mid-loop
void ImportWidget::importFiles(const QStringList& files) {
    for (const auto& path : files) {
        parseFile(path);
        QCoreApplication::processEvents(); // UAF if user closes window here!
        m_progressBar->setValue(m_progressBar->value() + 1); // crash!
    }
}

// ✅ Good: run heavy work on a worker thread / QtConcurrent and report progress via signals
```

### Prefer `open()` Over Nested Event Loops (`QDialog::exec()`, `QMenu::exec()`)

`QDialog::exec()` blocks the current stack frame while spinning a nested event loop. If a background event (network reply, D-Bus call, session timeout) closes and deletes the parent widget while `exec()` is waiting, a stack-allocated child dialog (`QMessageBox box(this);`) is `delete`d on a stack pointer, or member access after `exec()` hits freed memory.

```cpp
// ❌ Bad: nested event loop + stack-allocated QWidget with parent
void DocumentEditor::promptClose() {
    QMessageBox box(this);
    box.setText(tr("Save changes before closing?"));
    box.setStandardButtons(QMessageBox::Save | QMessageBox::Cancel);
    if (box.exec() == QMessageBox::Save) { // nested event loop!
        saveDocument(); // UAF if 'this' was destroyed while exec() blocked
    }
}

// ✅ Good: asynchronous modal presentation via open()
void DocumentEditor::promptClose() {
    auto* box = new QMessageBox(
        QMessageBox::Question,
        tr("Close Document"),
        tr("Save changes before closing?"),
        QMessageBox::Save | QMessageBox::Cancel,
        this);
    box->setAttribute(Qt::WA_DeleteOnClose);
    connect(box, &QMessageBox::finished, this, [this](int result) {
        if (result == QMessageBox::Save) {
            saveDocument();
        }
    });
    box->open();
}
```

### Always Pass a Context `QObject` to `QTimer::singleShot`

The 2-argument `QTimer::singleShot(ms, functor)` overload has no receiver context and will invoke the lambda even after `this` has been destroyed (`🔴 [blocking]`).

```cpp
// ❌ Bad: fires on dangling 'this' if widget closes within 500 ms
QTimer::singleShot(500, [this]() {
    reloadPreview();
});

// ✅ Good: auto-cancels timer if 'this' is destroyed
QTimer::singleShot(500, this, &PreviewWidget::reloadPreview);
```

---

## Signals, Slots & Property Bindings

### Prefer Pointer-to-Member-Function (PMF) Syntax

Always use compile-time checked PMF syntax over `SIGNAL()`/`SLOT()` macros. For overloaded signals, disambiguate with `qOverload<...>(...)`.

```cpp
// ❌ Bad: string-based macros bypass compile-time type checks and refactoring tools
connect(sender, SIGNAL(valueChanged(int)), receiver, SLOT(updateValue(int)));

// ✅ Good: compile-time checked PMF connection
connect(sender, &Sender::valueChanged, receiver, &Receiver::updateValue);

// ✅ Good: disambiguating overloaded signals
connect(spinBox, qOverload<int>(&QSpinBox::valueChanged),
        this, &SettingsPane::onCountChanged);
```

### Specify a Receiver Context Object for Lambda Connections

Omitting the 3rd `context` parameter in `connect(sender, signal, lambda)` causes **two** severe bugs (`🔴 [blocking]`):
1. The connection is **not** auto-disconnected when `this` is destroyed (use-after-free).
2. Even when `sender` lives on a background `QThread`, a contextless functor runs via `Qt::DirectConnection` **on the sender's worker thread**, causing data races or GUI crashes!

```cpp
// ❌ Bad: no context object — UAF on destruction AND runs on sender's thread!
connect(worker, &Worker::chunkReady, [this](const QByteArray& chunk) {
    m_statusLabel->setText(tr("Received %1 bytes").arg(chunk.size()));
});

// ✅ Good: 'this' provides auto-disconnect AND queues execution onto this->thread()
connect(worker, &Worker::chunkReady, this, [this](const QByteArray& chunk) {
    m_statusLabel->setText(tr("Received %1 bytes").arg(chunk.size()));
});
```

### Connection Types and Deadlock Pitfalls

- `Qt::AutoConnection` *(default)*: `DirectConnection` if emitter runs on receiver's thread at emission time; `QueuedConnection` otherwise.
- `Qt::QueuedConnection`: Posts a `QMetaCallEvent` to receiver's event loop. Arguments are copied (`qRegisterMetaType<T>()` required in Qt 5; auto-registered in Qt 6 if `T` is complete).
- `Qt::DirectConnection`: Invokes slot synchronously on the emitting thread — dangerous across threads unless the slot is explicitly synchronized.
- `Qt::BlockingQueuedConnection`: Blocks the emitting thread until the receiver's event loop finishes the slot. **Deadlocks immediately** if sender and receiver share the same thread, or if the GUI thread calls `workerThread->wait()` while the worker emits a `BlockingQueuedConnection` back to the GUI thread!
- `Qt::UniqueConnection`: Bitwise-OR with other flags to prevent duplicate connections on repeated setup (`Qt::AutoConnection | Qt::UniqueConnection`; requires PMF slots, not lambdas).

### Guard Against Signal Loops and Use `QSignalBlocker`

Always check for value equality before mutating and emitting change signals. When programmatically syncing widgets without triggering user-edit slots, use RAII `QSignalBlocker` instead of raw `blockSignals(true/false)`.

```cpp
void SliderController::setVolume(int v) {
    if (m_volume == v) return; // ✅ breaks potential A <-> B signal loops
    m_volume = v;
    emit volumeChanged(v);
}

// ❌ Bad: early return leaves slider permanently muted; overwrites outer blockSignals state
void SliderController::syncUi(int v) {
    m_slider->blockSignals(true);
    if (v < 0) return; // BUG: signals stay blocked forever!
    m_slider->setValue(v);
    m_slider->blockSignals(false);
}

// ✅ Good: RAII restores previous signal-blocking state on every exit path
void SliderController::syncUi(int v) {
    const QSignalBlocker blocker(m_slider);
    if (v < 0) return;
    m_slider->setValue(v);
}
```

### Disconnect or Scope Connections When Swapping Sources

When rebinding a view to a new model or document object, disconnect the previous source or store a `QMetaObject::Connection` handle so stale objects stop driving the UI.

```cpp
void DocumentInspector::setDocument(Document* doc) {
    if (m_document == doc) return;
    disconnect(m_docConnection);
    m_document = doc;
    if (m_document) {
        m_docConnection = connect(
            m_document, &Document::modifiedChanged,
            this, &DocumentInspector::updateWindowModified);
    }
}
```

### Qt 6 Bindable Properties (`QProperty` / `QBindable`)

In Qt 6 C++ code, `Q_OBJECT_BINDABLE_PROPERTY` reduces manual signal-forwarding boilerplate while preserving `NOTIFY` compatibility for existing slots and QML.

```cpp
#include <QObject>
#include <QProperty>

class ViewportMetrics : public QObject {
    Q_OBJECT
    Q_PROPERTY(int width READ width WRITE setWidth NOTIFY widthChanged BINDABLE bindableWidth)
public:
    int width() const { return m_width.value(); }
    void setWidth(int w) { m_width.setValue(w); }
    QBindable<int> bindableWidth() { return &m_width; }

signals:
    void widthChanged();

private:
    Q_OBJECT_BINDABLE_PROPERTY(ViewportMetrics, int, m_width, &ViewportMetrics::widthChanged)
};
```

---

## Containers & Strings

### Prevent Implicit-Sharing Detaches in Range-`for` Loops

Qt containers (`QList`, `QString`, `QByteArray`, `QHash`, `QMap`) use **Implicit Sharing** (Copy-on-Write). Calling any non-`const` member (`begin()`, `end()`, `operator[]`, `data()`) when `refCount > 1` deep-copies the entire buffer.

Crucially, `for (const auto& item : list)` on a **non-`const` container variable** calls non-`const` `list.begin()` **before** binding `const auto&`, triggering a hidden detach (`🟡 [important]`, Clazy `range-loop-detach`)!

```cpp
#include <utility> // std::as_const (C++17)

void inspectTags(QStringList tags) { // non-const container sharing buffer with caller
    // ❌ Bad: calls non-const tags.begin() -> detaches and copies the entire QStringList!
    for (const auto& tag : tags) {
        qDebug() << tag;
    }

    // ✅ Good (Qt 6 / C++17): std::as_const selects const begin()/end() — zero copy
    // (In Qt 5.7–6.5, qAsConst(tags) was used; qAsConst is deprecated in Qt 6.6+)
    for (const auto& tag : std::as_const(tags)) {
        qDebug() << tag;
    }

    // ❌ Bad: never wrap a temporary rvalue in qAsConst (dangling; std::as_const deletes rvalues)
    // for (const auto& tag : qAsConst(loadTags())) { ... }

    // ✅ Good: store returned temporary in a const local (safe across C++17 and C++20)
    const QStringList loaded = loadTags();
    for (const auto& tag : loaded) {
        qDebug() << tag;
    }
}
```

### Container Selection (Qt 5 vs Qt 6)

- **Qt 6**: `QList` and `QVector` are unified (`QVector` is an alias for `QList`), backed by a contiguous array with prepending optimization.
  - **Migration caveat:** Unlike Qt 5's `QList` (which heap-allocated elements larger than a pointer and kept element references stable across `append()`), Qt 6's `QList<LargeStruct>` stores elements inline and **invalidates pointers/references on reallocation**! Use `std::list` or index/ID handles if reference stability across insertions is required.
- **Qt 5**: Prefer `QVector<T>` over `QList<T>` for contiguous cache-friendly storage.
- Pass containers by `const T&` (or `QSpan<const T>` in Qt 6.7+ / `std::span<const T>` in C++20) for read-only access.
- Use `.value(key)` or `.constFind(key)` on `QHash`/`QMap` instead of `map[key]` for lookups (`operator[]` on a non-`const` map inserts a default-constructed entry and detaches!).

### `QString`, `QStringView`, and Compile-Time Literals

- **Constructing a `QString` from a literal**: Use `u"..."_s` in Qt 6.4+ (`using namespace Qt::Literals::StringLiterals;`) or `QStringLiteral("...")` in Qt 5/6 to embed UTF-16 data at compile time without heap allocation.
- **Comparing / searching without allocating**: Compare `QString` or `QStringView` directly against UTF-16 literals (`u"..."` in Qt 6) or `QLatin1StringView("...")` (Qt 6) / `QLatin1String("...")` (Qt 5).
- **Read-only parameters**: Prefer `QStringView` (or `QUtf8StringView` in Qt 6) for functions that inspect strings without storing a `QString` copy. Never return a `QStringView` pointing into a local `QString` (`🔴 [blocking]`).

```cpp
using namespace Qt::Literals::StringLiterals; // Qt 6.4+

// ❌ Bad: runtime UTF-8 decoding + temporary QString heap allocation
bool isJsonMime(const QString& mime) {
    return mime == "application/json" || mime.startsWith("application/vnd.");
}

// ✅ Good (Qt 6): non-owning QStringView parameter + zero-allocation literal comparisons
bool isJsonMime(QStringView mime) noexcept {
    return mime == u"application/json" || mime.startsWith(u"application/vnd.");
}

// ✅ Good (Qt 5.15): QLatin1String avoids temporary QString allocation
bool isJsonMimeQt5(const QString& mime) {
    return mime == QLatin1String("application/json")
        || mime.startsWith(QLatin1String("application/vnd."));
}
```

### Safe `QString::arg()` Formatting & `tr()` Localization

Chaining `.arg(a).arg(b)` substitutes sequentially: if `a` contains `"%1"` (e.g., user input or file names), the second `.arg(b)` corrupts `a` (`🟡 [important]`, Clazy `qstring-arg`). Pass multiple string arguments to a **single** `.arg(a, b)` call.

```cpp
// ❌ Bad: if fileName is "report_%1.pdf", role replaces %1 inside fileName!
QString msg = tr("Opened %1 as %2").arg(fileName).arg(role);

// ✅ Good: multi-arg overload replaces all placeholders in one pass
QString msg = tr("Opened %1 as %2").arg(fileName, role);

// ❌ Bad: concatenated translations break word order and plural rules across languages
QString countText = tr("Deleted ") + QString::number(n) + tr(" files");

// ✅ Good: plural-aware tr() with %n
QString countText = tr("Deleted %n file(s)", nullptr, n);
```

---

## Threads & Concurrency

> 📖 Cross-language concurrency patterns: [Async & Concurrency Guide](cross-cutting/async-concurrency-patterns.md)

### Worker-Object Pattern & Clean `QThread` Shutdown

Prefer moving a parentless `QObject` worker onto a `QThread` over putting business logic + slots on a `QThread` subclass (remember: slots on a `QThread` subclass execute on the **creating thread**, not the new thread!).

Always wire **both** worker cleanup and thread shutdown (`🔴 [blocking]`):
1. A `QObject` **cannot** be moved (`moveToThread`) if it already has a `parent()`.
2. Destroying a `QThread` while `isRunning() == true` calls `qFatal("QThread: Destroyed while thread is still running")` and aborts the process!
3. Connect `&QThread::finished` → `worker->deleteLater()` so `worker` is deleted on its affinity thread whether the job finishes normally or the thread is stopped early.

```cpp
// ❌ Bad: leaks both 'thread' and 'worker'; thread event loop never quits; ~QThread aborts if owned
void startBrokenJob() {
    QThread* thread = new QThread;
    Worker* worker = new Worker;
    worker->moveToThread(thread);
    QObject::connect(thread, &QThread::started, worker, &Worker::process);
    QObject::connect(thread, &QThread::finished, worker, &QObject::deleteLater);
    thread->start(); // QThread::quit() is never called!
}

// ✅ Good: complete lifecycle with cooperative cancellation and safe destructor shutdown
class ExportController : public QObject {
    Q_OBJECT
public:
    explicit ExportController(QObject* parent = nullptr) : QObject(parent) {
        m_thread = new QThread(this);
        auto* worker = new ExportWorker(); // nullptr parent required before moveToThread
        worker->moveToThread(m_thread);

        connect(m_thread, &QThread::started, worker, &ExportWorker::process);
        connect(worker, &ExportWorker::progressChanged, this, &ExportController::onProgress);
        connect(worker, &ExportWorker::finished, m_thread, &QThread::quit);
        connect(m_thread, &QThread::finished, worker, &QObject::deleteLater);
        m_thread->start();
    }

    ~ExportController() override {
        m_thread->requestInterruption(); // worker checks QThread::currentThread()->isInterruptionRequested()
        m_thread->quit();
        m_thread->wait(); // prevents qFatal in ~QThread()
    }

private slots:
    void onProgress(int percent);

private:
    QThread* m_thread = nullptr;
};
```

### GUI Thread Affinity (`QWidget`, `QPixmap` vs `QImage`)

**Never** access `QWidget` subclasses, `QQuickItem`, or `QPixmap` from a background thread (`🔴 [blocking]`). `QPixmap` is backed by window-system/GPU resources tied to the GUI thread; decode and manipulate images off-thread with **`QImage`**, then convert via `QPixmap::fromImage()` on the main thread.

```cpp
// ❌ Bad: touching QWidget and QPixmap from a worker thread -> undefined behavior / crash
void ThumbnailWorker::render(const QString& path) {
    QPixmap pix(path);            // CRASH/UB off GUI thread!
    m_previewLabel->setPixmap(pix);
}

// ✅ Good: decode QImage on worker thread; convert to QPixmap in GUI slot
void ThumbnailWorker::render(const QString& path) {
    QImage img(path);
    emit thumbnailDecoded(img.scaled(256, 256, Qt::KeepAspectRatio, Qt::SmoothTransformation));
}

// Connected on GUI thread:
connect(worker, &ThumbnailWorker::thumbnailDecoded, this, [this](const QImage& img) {
    m_previewLabel->setPixmap(QPixmap::fromImage(img));
});
```

### `QtConcurrent` with `QFutureWatcher`

Use `QtConcurrent::run` for CPU-bound tasks that do not need a dedicated `QThread` event loop, and observe completion via `QFutureWatcher` rather than blocking the GUI thread with `future.result()` or `future.waitForFinished()`.

```cpp
// ❌ Bad: future.result() blocks the GUI thread, defeating QtConcurrent::run!
auto future = QtConcurrent::run([path]() { return computeChecksum(path); });
showChecksum(future.result());

// ✅ Good: non-blocking continuation via QFutureWatcher
auto* watcher = new QFutureWatcher<QByteArray>(this);
connect(watcher, &QFutureWatcher<QByteArray>::finished, this, [this, watcher]() {
    watcher->deleteLater();
    try {
        showChecksum(watcher->result());
    } catch (const QException& e) {
        showError(QString::fromUtf8(e.what()));
    }
});
watcher->setFuture(QtConcurrent::run([path]() { return computeChecksum(path); }));
```

---

## GUI, Widgets & Painting

For cross-stack UI responsiveness and rendering complexity, see [Performance Review Guide](performance-review-guide.md).

### Separation of Concerns & Layouts

- Keep domain state, network calls, and persistence out of `QMainWindow` / `QDialog` classes; UI classes should bind to controllers or `QAbstractItemModel`s.
- Avoid hardcoded pixel geometry (`setGeometry()`, fixed `resize()`). Use `QVBoxLayout`, `QHBoxLayout`, `QGridLayout`, `QFormLayout`, and `QSizePolicy` so UIs adapt to translations, font sizes, and DPI changes.

### `paintEvent()` Discipline

- Prefer `update()` (coalesced, asynchronous schedule) over `repaint()` (immediate synchronous paint).
- **Never** mutate widget geometry (`resize()`, `setGeometry()`), modify layouts, allocate heavy fonts/images from disk, or run synchronous I/O inside `paintEvent()` — geometry changes inside `paintEvent()` can trigger infinite repaint recursion (`🔴 [blocking]`).

### High-DPI Scaling (Qt 5 vs Qt 6)

```cpp
int main(int argc, char* argv[]) {
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    // ✅ Qt 5.14/5.15: MUST be called BEFORE constructing QApplication!
    QCoreApplication::setAttribute(Qt::AA_EnableHighDpiScaling);
    QCoreApplication::setAttribute(Qt::AA_UseHighDpiPixmaps);
    QGuiApplication::setHighDpiScaleFactorRoundingPolicy(
        Qt::HighDpiScaleFactorRoundingPolicy::PassThrough);
#endif
    // ✅ Qt 6: High-DPI scaling and PassThrough rounding are enabled by default
    // (AA_EnableHighDpiScaling / AA_UseHighDpiPixmaps are deprecated in Qt 6).
    QApplication app(argc, argv);
    MainWindow window;
    window.show();
    return app.exec();
}
```

When rendering into offscreen `QPixmap` or `QImage` buffers for custom painting, multiply pixel dimensions by `devicePixelRatioF()` and call `pixmap.setDevicePixelRatio(dpr)` so output stays crisp on Retina / 150% / 200% displays.

---

## Model/View Architecture

### Subclass `QAbstractTableModel` / `QAbstractListModel` Safely

Validate `QModelIndex` bounds in `data()`/`setData()` (prefer `checkIndex(index, CheckIndexOption::IndexIsValid)` in Qt 5.11+ / Qt 6). If the model is consumed by QML views (`ListView`, `Repeater`), override `roleNames()` as well.

```cpp
class TaskModel : public QAbstractTableModel {
    Q_OBJECT
public:
    enum Role {
        TitleRole = Qt::UserRole + 1,
        PriorityRole,
        StatusRole,
    };

    using QAbstractTableModel::QAbstractTableModel;

    int rowCount(const QModelIndex& parent = {}) const override {
        return parent.isValid() ? 0 : static_cast<int>(m_tasks.size());
    }

    int columnCount(const QModelIndex& parent = {}) const override {
        return parent.isValid() ? 0 : 3;
    }

    QVariant data(const QModelIndex& index, int role = Qt::DisplayRole) const override {
        if (!checkIndex(index, CheckIndexOption::IndexIsValid))
            return {};

        const Task& task = m_tasks.at(index.row());
        if (role == Qt::DisplayRole) {
            switch (index.column()) {
                case 0: return task.title;
                case 1: return task.priority;
                case 2: return task.status;
            }
        }
        if (role == Qt::BackgroundRole && index.column() == 1) {
            if (task.priority == QLatin1String("High")) return QColor(0xFF, 0xCC, 0xCC);
        }
        // Named roles for QML delegates
        switch (role) {
            case TitleRole:    return task.title;
            case PriorityRole: return task.priority;
            case StatusRole:   return task.status;
        }
        return {};
    }

    QHash<int, QByteArray> roleNames() const override {
        return {
            {TitleRole, "title"},
            {PriorityRole, "priority"},
            {StatusRole, "status"},
        };
    }

private:
    QList<Task> m_tasks;
};
```

### Emit Exact Change Notifications (Mind Inclusive `last` Index!)

- `beginInsertRows(parent, first, last)` and `beginRemoveRows(parent, first, last)` take an **inclusive** `last` index (`first + count - 1`). Calling `beginInsertRows({}, pos, pos - 1)` when `items` is empty triggers `Q_ASSERT(last >= first)` (`🔴 [blocking]`)!
- Guard `update` setters with bounds and equality checks before emitting `dataChanged`.
- Reserve `beginResetModel()` / `endResetModel()` for wholesale replacements — resetting destroys view selection, current index, scroll position, and expanded tree nodes.

```cpp
// ❌ Bad: mutating backing container without model signals leaves views stale or out-of-bounds
void TaskModel::appendTasks(const QList<Task>& items) {
    m_tasks.append(items);
}

// ✅ Good: guard empty batch and pass inclusive last index
void TaskModel::appendTasks(const QList<Task>& items) {
    if (items.isEmpty()) return;
    const int first = static_cast<int>(m_tasks.size());
    const int last = first + static_cast<int>(items.size()) - 1; // inclusive!
    beginInsertRows({}, first, last);
    m_tasks.append(items);
    endInsertRows();
}

// ✅ Good: bounds check + no-op check + targeted role list in dataChanged
void TaskModel::updateStatus(int row, const QString& status) {
    if (row < 0 || row >= m_tasks.size()) return;
    if (m_tasks[row].status == status) return;
    m_tasks[row].status = status;
    const QModelIndex idx = index(row, 2);
    emit dataChanged(idx, idx, {Qt::DisplayRole, StatusRole});
}
```

### Custom Delegates: Save & Restore `QPainter` State

For simple colors, fonts, icons, or alignment, return `Qt::BackgroundRole`, `Qt::ForegroundRole`, `Qt::DecorationRole`, or `Qt::TextAlignmentRole` from `model->data()` instead of writing a custom delegate. When overriding `QStyledItemDelegate::paint()` for custom geometry (badges, progress bars), **always** pair `painter->save()` with `painter->restore()` so pens, brushes, fonts, and clip regions do not bleed into subsequent cells (`🟡 [important]`).

```cpp
class BadgeDelegate : public QStyledItemDelegate {
    Q_OBJECT
public:
    using QStyledItemDelegate::QStyledItemDelegate;

    void paint(QPainter* painter, const QStyleOptionViewItem& option,
               const QModelIndex& index) const override {
        QStyleOptionViewItem opt = option;
        initStyleOption(&opt, index);

        // Let QStyle draw selection/hover background first
        const QWidget* widget = opt.widget;
        QStyle* style = widget ? widget->style() : QApplication::style();
        opt.text.clear();
        style->drawControl(QStyle::CE_ItemViewItem, &opt, painter, widget);

        painter->save(); // ✅ isolate antialiasing/pen/brush state
        painter->setRenderHint(QPainter::Antialiasing, true);
        painter->setPen(Qt::NoPen);
        painter->setBrush(QColor(0x25, 0x63, 0xEB));
        painter->drawRoundedRect(opt.rect.adjusted(6, 4, -6, -4), 6, 6);
        painter->setPen(Qt::white);
        painter->drawText(opt.rect, Qt::AlignCenter, index.data(Qt::DisplayRole).toString());
        painter->restore();
    }
};
```

### Performance with Large Datasets

- Batch insertions/removals into a single `beginInsertRows`/`endInsertRows` range rather than emitting per row.
- Use `QSortFilterProxyModel` with `setDynamicSortFilter(true)` for client-side filtering; for 100K+ rows, consider filtering in the backing store / SQL query instead.
- Implement `canFetchMore()` / `fetchMore()` for incremental lazy loading.
- Keep `QVariant` payloads lightweight; avoid copying large blobs through `data()` on every paint frame.

---

## Meta-Object System

### `Q_OBJECT`, `Q_PROPERTY`, and `Q_ENUM`

- Every `QObject` subclass (even if it adds no signals/slots of its own) **must** include `Q_OBJECT`; omitting it causes `qobject_cast<Derived*>` to fail and `metaObject()->className()` to report the base class (`🔴 [blocking]`).
- Every `Q_PROPERTY` exposed to QML must specify either `NOTIFY <signal>` or `CONSTANT` (otherwise QML emits runtime non-notifyable property warnings when bound).
- Prefer `Q_ENUM` over `enum` without registration so `QMetaEnum`, `qDebug()`, and QML can introspect enumerators cleanly.
- Prefer `qobject_cast<T*>(obj)` over `dynamic_cast<T*>(obj)` for `QObject` hierarchies (faster, works across shared-library boundaries without RTTI).

```cpp
class DeviceSession : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString deviceId READ deviceId CONSTANT)
    Q_PROPERTY(State state READ state NOTIFY stateChanged)
public:
    enum class State { Disconnected, Connecting, Connected };
    Q_ENUM(State)

    QString deviceId() const { return m_deviceId; }
    State state() const { return m_state; }

signals:
    void stateChanged();

private:
    QString m_deviceId;
    State m_state = State::Disconnected;
};
```

### `Q_GADGET` for Lightweight Value Types

Use `Q_GADGET` (plus `QML_VALUE_TYPE` in Qt 6 QML modules) for copyable value structs that need property/enum introspection without `QObject` heap allocation or identity semantics.

```cpp
struct GeoPoint {
    Q_GADGET
    QML_VALUE_TYPE(geoPoint) // Qt 6.2+: lowercase value-type name in QML
    Q_PROPERTY(double latitude MEMBER latitude)
    Q_PROPERTY(double longitude MEMBER longitude)
public:
    double latitude = 0.0;
    double longitude = 0.0;
    bool operator==(const GeoPoint&) const = default; // C++20
};
```

---

## QML / Qt Quick

### Prefer Declarative Registration (`QML_ELEMENT`) Over `setContextProperty()`

In Qt 6, register C++ types via `QML_ELEMENT` / `QML_SINGLETON` inside `qt_add_qml_module()`. Avoid `engine.rootContext()->setContextProperty(...)`:
1. Unqualified context lookups bypass `qmllint`, `qmlls`, and `qmlcachegen` / `qmlsc` ahead-of-time compilation.
2. If a C++ object injected via `setContextProperty` is destroyed before `QQmlApplicationEngine`, QML bindings spam `TypeError: Cannot read property '...' of null` during shutdown.

```cpp
// ✅ Good (Qt 6): declarative compile-time-visible singleton
class AppSettings : public QObject {
    Q_OBJECT
    QML_ELEMENT
    QML_SINGLETON
    Q_PROPERTY(QString theme READ theme WRITE setTheme NOTIFY themeChanged)
public:
    using QObject::QObject;
    QString theme() const { return m_theme; }
    void setTheme(const QString& t) {
        if (m_theme == t) return;
        m_theme = t;
        emit themeChanged();
    }
signals:
    void themeChanged();
private:
    QString m_theme = QStringLiteral("light");
};
```

### Guard Against QML Garbage Collection of C++ `QObject*` (`JavaScriptOwnership`)

This is one of the most common crashes in hybrid C++/QML applications (`🔴 [blocking]`):
- Returning a `QObject*` with **`parent() == nullptr`** from a **`Q_INVOKABLE` method or slot** transfers ownership to **`QQmlEngine::JavaScriptOwnership`** by default! When the QML JS garbage collector runs, it deletes the C++ object while C++ still holds a dangling pointer!
- By contrast, `Q_PROPERTY` `READ` getters retain `QQmlEngine::CppOwnership` by default.

```cpp
class UserDirectory : public QObject {
    Q_OBJECT
    QML_ELEMENT
    // ✅ Safe: Q_PROPERTY READ keeps CppOwnership
    Q_PROPERTY(UserProfile* activeProfile READ activeProfile NOTIFY activeProfileChanged)
public:
    // ❌ Bad: if m_cache[id]->parent() == nullptr, QML GC takes JavaScriptOwnership and deletes it!
    // Q_INVOKABLE UserProfile* findUser(int id) const { return m_cache.value(id, nullptr); }

    // ✅ Good: parent C++-owned objects OR explicitly mark CppOwnership before returning
    Q_INVOKABLE UserProfile* findUser(int id) const {
        UserProfile* profile = m_cache.value(id, nullptr);
        if (profile && !profile->parent()) {
            QQmlEngine::setObjectOwnership(profile, QQmlEngine::CppOwnership);
        }
        return profile;
    }

    UserProfile* activeProfile() const { return m_activeProfile; }

signals:
    void activeProfileChanged();

private:
    UserProfile* m_activeProfile = nullptr;
    QHash<int, UserProfile*> m_cache;
};
```

### QML Performance, Qualified Access, and Lifecycle

- Add `pragma ComponentBehavior: Bound` (Qt 6.5+) at the top of QML files and declare `required property` inside `ListView`/`Repeater` delegates instead of relying on unqualified `model.foo` context injection, enabling `qmlcachegen` to compile delegate bindings to C++.
- Keep heavy loops, sorting, and JSON parsing in C++ (`QAbstractListModel`), not in `Component.onCompleted` JavaScript.
- Watch for **binding loops** (`QML Rectangle: Binding loop detected for property "width"`) when parent and child sizes depend on each other; use `implicitWidth` / `implicitHeight` and `QtQuick.Layouts`.
- Use `Loader` for deferred instantiation of heavy subtrees, and always pass a `parent` when calling `component.createObject(parent, props)` (or call `.destroy()` explicitly).

```qml
pragma ComponentBehavior: Bound
import QtQuick
import com.example.myapp

ListView {
    model: TaskListModel {}
    delegate: Item {
        id: root
        required property string title
        required property string priority
        implicitHeight: 40
        width: ListView.view.width

        Text { text: `${root.title} (${root.priority})` }
    }
}

// ✅ Good: Loader unloads heavy detail component automatically when active becomes false
Loader {
    id: detailLoader
    active: selectedItem !== null
    sourceComponent: detailComponent
}
```

---

## Networking, I/O, Process & Security

> 📖 Cross-language security & error patterns: [SQL Injection Guide](cross-cutting/sql-injection-prevention.md) · [Error Handling Guide](cross-cutting/error-handling-principles.md) · [Security Review Guide](security-review-guide.md)

### `QNetworkAccessManager` Reuse & `QNetworkReply` Leaks

- Reuse a single `QNetworkAccessManager` per service/session so HTTP/2 multiplexing, TCP keep-alive, and TLS session caches work.
- **Always** call `reply->deleteLater()` when `&QNetworkReply::finished` fires (`🔴 [blocking]`); otherwise `QNetworkAccessManager` retains every `QNetworkReply` in memory until the manager itself is destroyed. Connect `finished` → `reply->deleteLater()` directly so the reply is still freed even if the requesting UI object (`this`) closes mid-flight!
- Set a request timeout (`req.setTransferTimeout(15000)` in Qt 5.15+ / Qt 6) and check **both** `reply->error()` and `HttpStatusCodeAttribute`.

```cpp
using namespace Qt::Literals::StringLiterals; // Qt 6.4+

void ApiClient::fetchProfile(int userId) {
    QNetworkRequest req(QUrl(u"https://api.example.com/users/%1"_s.arg(userId)));
    req.setTransferTimeout(15000);

    QNetworkReply* reply = m_nam->get(req);
    // Freed even if 'this' is destroyed before the reply finishes:
    connect(reply, &QNetworkReply::finished, reply, &QObject::deleteLater);

    connect(reply, &QNetworkReply::finished, this, [this, reply]() {
        if (reply->error() != QNetworkReply::NoError) {
            emit requestFailed(reply->errorString());
            return;
        }
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (status < 200 || status >= 300) {
            emit requestFailed(tr("Unexpected HTTP status %1").arg(status));
            return;
        }
        emit profileLoaded(QJsonDocument::fromJson(reply->readAll()).object());
    });
}
```

### Safe External Process Execution (`QProcess`)

- **Never** pass untrusted strings to `QProcess::startCommand()` or `sh -c` / `cmd /c` (`🔴 [blocking]` command injection). Pass the executable path and `QStringList` arguments separately so Qt spawns the process directly without shell expansion.
- **Never** call `process.waitForFinished(-1)` on the GUI thread; handle `&QProcess::finished` and `&QProcess::errorOccurred` asynchronously (note: `finished` is **not** emitted when `FailedToStart` occurs).

```cpp
using namespace Qt::Literals::StringLiterals;

// ❌ Bad: shell command injection + blocks GUI thread indefinitely
QProcess proc;
proc.startCommand(u"ffprobe -i "_s + userFilePath);
proc.waitForFinished(-1);

// ✅ Good: argument array bypasses shell; async signal handling keeps UI responsive
auto* proc = new QProcess(this);
connect(proc, &QProcess::finished, proc, &QObject::deleteLater);
connect(proc, &QProcess::finished, this, [this, proc](int exitCode, QProcess::ExitStatus status) {
    if (status != QProcess::NormalExit || exitCode != 0) {
        showError(QString::fromUtf8(proc->readAllStandardError()));
        return;
    }
    parseProbeOutput(proc->readAllStandardOutput());
});
connect(proc, &QProcess::errorOccurred, this, [this, proc](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) { // finished() is not emitted on FailedToStart
        showError(proc->errorString());
        proc->deleteLater();
    }
});
proc->start(u"ffprobe"_s, {u"-v"_s, u"quiet"_s, u"-i"_s, userFilePath});
```

### Parameterized Queries in `QtSql` (`QSqlQuery`)

Never build SQL statements with `QString::arg()` or `+` (`🔴 [blocking]`). Always use `QSqlQuery::prepare()` with `bindValue()` / `addBindValue()` and check return values (`prepare()` and `exec()` return `false` on syntax/constraint errors).

```cpp
using namespace Qt::Literals::StringLiterals;

// ❌ Bad: SQL injection via QString::arg
QSqlQuery bad(db);
bad.exec(u"SELECT id, role FROM users WHERE email = '%1'"_s.arg(email));

// ✅ Good: prepared statement with bound parameter + error check
QSqlQuery query(db);
if (!query.prepare(u"SELECT id, role FROM users WHERE email = :email"_s)) {
    qWarning() << "Prepare failed:" << query.lastError();
    return std::nullopt;
}
query.bindValue(u":email"_s, email);
if (!query.exec()) {
    qWarning() << "Query failed:" << query.lastError();
    return std::nullopt;
}
```

### Atomic File Writes (`QSaveFile`) & `QLabel` Rich-Text Safety

- **Use `QSaveFile` instead of `QFile::Truncate`** when saving user documents or configuration files: `QSaveFile` writes to a temporary sibling file and atomically renames on `commit()`, preventing 0-byte corrupted files on crash or full disk (`call cancelWriting()` before returning on write errors).
- **Force `Qt::PlainText` on `QLabel` / `QMessageBox` for untrusted text**: `QLabel` defaults to `Qt::AutoText`, which parses HTML tags (`<a href=...>`, `<img src=":/...">`, giant `<font>` spoofing) if the string looks like markup (`🟡 [important]`).

```cpp
// ✅ Good: untrusted user text rendered strictly as plain text
m_usernameLabel->setTextFormat(Qt::PlainText);
m_usernameLabel->setText(untrustedDisplayName);

// ✅ Good: atomic file persistence
bool writeConfigAtomically(const QString& path, const QByteArray& payload) {
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly)) return false;
    if (file.write(payload) != payload.size()) {
        file.cancelWriting();
        return false;
    }
    return file.commit();
}
```

---

## Qt5 → Qt6 Migration

### Key Breaking Changes

| Qt 5 | Qt 6 | Review Notes |
|------|------|--------------|
| `QVector<T>` vs `QList<T>` | Unified (`QVector` = `QList`) | Contiguous array; **references to large elements now invalidate on reallocation** |
| `QStringRef` | `QStringView` | Non-owning UTF-16 view (`#include <QStringView>`) |
| `QLatin1String` | `QLatin1StringView` / `u"..."_s` | `QLatin1String` remains as alias; `u"..."_s` requires `Qt::Literals::StringLiterals` (6.4+) |
| `QRegExp` | `QRegularExpression` | Perl-compatible regex; `QRegExp` moved to `Core5Compat` |
| `QTextStream::setCodec("UTF-8")` | `setEncoding(QStringConverter::Utf8)` | UTF-8 is already default in Qt 6; `endl` → `Qt::endl` |
| `QMouseEvent::pos()` / `globalPos()` | `position()` / `globalPosition()` | Returns `QPointF` instead of `QPoint` (use `.toPoint()` if integer needed) |
| `QWheelEvent::delta()` | `QWheelEvent::angleDelta().y()` | `delta()` removed in Qt 6 |
| `QComboBox::activated(const QString&)` | `QComboBox::textActivated(const QString&)` | `activated(int)` remains unchanged |
| `QDesktopWidget` | `QScreen` (`widget->screen()`) | Query `QScreen::availableGeometry()` for multi-monitor setups |
| `QVariant::type()` (`QVariant::Type`) | `typeId()` / `metaType()` | Compare against `QMetaType::Type` (e.g., `QMetaType::QString`) |
| `qAsConst(container)` | `std::as_const(container)` | `qAsConst` deprecated in Qt 6.6 |

### Modern Qt 6 CMake (`qt_standard_project_setup` & `qt_add_qml_module`)

In Qt 6, prefer CMake with `qt_standard_project_setup()` (enables `CMAKE_AUTOMOC` and `CMAKE_AUTOUIC`) and `qt_add_qml_module()` rather than qmake `.pro` files or hand-written `.qrc` files for QML (`qt_add_qml_module` automatically runs `qmlcachegen`, generates `.qmltypes`/`qmldir`, and exposes `all_qmllint` build targets).

```cmake
# ✅ Good: modern Qt 6.5+ CMakeLists.txt
cmake_minimum_required(VERSION 3.21)
project(MyApp VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Core Gui Quick Widgets)
qt_standard_project_setup(REQUIRES 6.5)

qt_add_executable(MyApp
    src/main.cpp
)

qt_add_qml_module(MyApp
    URI com.example.myapp
    QML_FILES
        qml/Main.qml
    SOURCES
        src/AppSettings.h
        src/AppSettings.cpp
)

target_link_libraries(MyApp PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Quick
    Qt6::Widgets
)
```

### Migration Checklist

- [ ] Replace `qmake` with `CMake` (`qt_standard_project_setup`, `qt_add_executable`, `qt_add_qml_module`)
- [ ] Audit Qt 5 `QList<LargeType>` usages that hold element pointers/references across insertions
- [ ] Replace `QStringRef` with `QStringView`, `QRegExp` with `QRegularExpression`, and `QDesktopWidget` with `QScreen`
- [ ] Replace deprecated event accessors (`pos()` → `position()`, `delta()` → `angleDelta()`) and `QVariant::type()` → `typeId()`
- [ ] Remove `Qt::AA_EnableHighDpiScaling` / `Qt::AA_UseHighDpiPixmaps` when building strictly for Qt 6
- [ ] Treat `Qt6::Core5Compat` as a temporary bridge and track removal of `QTextCodec` / `QRegExp`

---

## Testing & Static Analysis

### Unit & Data-Driven Testing with `QTest`

```cpp
#include <QtTest>
#include "parser.h"

using namespace Qt::Literals::StringLiterals;

class TestParser : public QObject {
    Q_OBJECT
private slots:
    void testEmptyInput() {
        Parser p(u""_s);
        QVERIFY(p.nextToken().isNull());
    }

    void testValidTokens_data() {
        QTest::addColumn<QString>("input");
        QTest::addColumn<Token::Type>("expectedType");

        QTest::newRow("integer")  << u"42"_s        << Token::Type::Integer;
        QTest::newRow("string")   << u"\"hello\""_s << Token::Type::String;
        QTest::newRow("operator") << u"+"_s         << Token::Type::Operator;
    }

    void testValidTokens() {
        QFETCH(QString, input);
        QFETCH(Token::Type, expectedType);

        Parser p(input);
        QCOMPARE(p.nextToken().type(), expectedType);
    }
};

QTEST_MAIN(TestParser)
#include "tst_parser.moc"
```

### GUI & Async Signal Testing (`QSignalSpy` + `QTRY_*`)

- **Always `QVERIFY(widget != nullptr)`** after `findChild<T*>()` before passing the pointer to `QTest::keyClicks` or `QTest::mouseClick`.
- Use **`QSignalSpy`** to verify signal counts and payload arguments.
- Prefer polling assertions (**`QTRY_VERIFY`**, **`QTRY_COMPARE`**) over fixed `QTest::qWait(500)` sleeps, which make CI both slow and flaky (`🟡 [important]`).

```cpp
using namespace Qt::Literals::StringLiterals;

class TestLoginDialog : public QObject {
    Q_OBJECT
private slots:
    void testSubmitEmitsCredentialsAndAccepts() {
        LoginDialog dialog;
        dialog.show();
        QVERIFY(QTest::qWaitForWindowExposed(&dialog));

        auto* userField = dialog.findChild<QLineEdit*>(u"usernameField"_s);
        auto* passField = dialog.findChild<QLineEdit*>(u"passwordField"_s);
        QVERIFY(userField != nullptr);
        QVERIFY(passField != nullptr);

        QSignalSpy loginSpy(&dialog, &LoginDialog::loginRequested);
        QVERIFY(loginSpy.isValid());

        QTest::keyClicks(userField, u"alice"_s);
        QTest::keyClicks(passField, u"secret123"_s);
        QTest::keyClick(passField, Qt::Key_Return);

        QTRY_COMPARE(loginSpy.count(), 1);
        QCOMPARE(loginSpy.takeFirst().at(0).toString(), u"alice"_s);
        QTRY_COMPARE(dialog.result(), static_cast<int>(QDialog::Accepted));
    }
};
```

### Dependency Injection for Testability

Inject abstract service interfaces (network, clock, filesystem) into controllers and models so unit tests run deterministically in milliseconds without sockets or timers.

```cpp
class UserGateway {
public:
    virtual ~UserGateway() = default;
    virtual void fetchUser(int id, std::function<void(QJsonObject)> onSuccess) = 0;
};

class FakeUserGateway : public UserGateway {
public:
    QHash<int, QJsonObject> canned;
    void fetchUser(int id, std::function<void(QJsonObject)> onSuccess) override {
        onSuccess(canned.value(id));
    }
};
```

### Static Analysis (`clazy`, `qmllint`) & Headless CI

Automate Qt-specific static checks in CI so human reviewers can focus on architecture and domain correctness:
- **`clazy`**: Clang plugin with 50+ Qt-specific checks (`connect-non-signal`, `lambda-in-connect`, `range-loop-detach`, `qstring-arg`, `child-event-qobject-cast`, `Incorrectly-parented`).
- **`qmllint`**: Built into Qt 6 (`all_qmllint` CMake target) — catches unqualified lookups, missing properties, and deprecated QML bindings at build time.
- **`QAbstractItemModelTester`**: Attach `new QAbstractItemModelTester(model, QAbstractItemModelTester::FailureReportingMode::QtTest, model)` in unit tests to automatically fuzz-check `index()`, `parent()`, `rowCount()`, and `beginInsertRows`/`endInsertRows` invariants!

```bash
# Configure with Qt tests, ASan/UBSan, and clazy
cmake -B build -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON \
      -DCMAKE_CXX_FLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer"
cmake --build build

# Run QML static checks (Qt 6 qt_add_qml_module)
cmake --build build --target all_qmllint

# Cross-platform headless QTest execution via offscreen QPA plugin
QT_QPA_PLATFORM=offscreen ctest --test-dir build --output-on-failure

# Or under Xvfb on Linux when window-manager focus/exposure semantics are tested
xvfb-run -a ctest --test-dir build --output-on-failure
```

---

## Review Checklist

### Memory & Event Loop
- [ ] Parent passed in constructor; transient child dialogs/widgets use `Qt::WA_DeleteOnClose` or `deleteLater()` so long-lived parents do not leak across sessions
- [ ] No double ownership (`QObject` parent combined with `std::unique_ptr` or stack allocation)
- [ ] `deleteLater()` used instead of `delete` inside slots and event handlers
- [ ] No `QCoreApplication::processEvents()` calls inside business/UI loops; async `open()` preferred over nested `QDialog::exec()`
- [ ] `QTimer::singleShot` calls pass a receiver context `QObject`

### Signals, Slots & Bindings
- [ ] Compile-time PMF `connect()` syntax used (no `SIGNAL`/`SLOT` macros)
- [ ] Every lambda `connect()` specifies a receiver context `QObject` (prevents UAF and cross-thread `DirectConnection` bugs)
- [ ] Setters check equality before emitting `Changed` signals; `QSignalBlocker` used instead of raw `blockSignals(true/false)`
- [ ] Connections to replaceable data sources are disconnected or tracked via `QMetaObject::Connection`
- [ ] No `Qt::BlockingQueuedConnection` deadlock paths

### Threads & Concurrency
- [ ] `QWidget`, `QQuickItem`, and `QPixmap` accessed exclusively on the GUI thread (`QImage` used off-thread)
- [ ] Worker objects have `nullptr` parent before `moveToThread`, `&QThread::finished` cleans up `worker->deleteLater()`, and owning destructors call `quit()` + `wait()`
- [ ] `QtConcurrent::run` results observed asynchronously via `QFutureWatcher` (never `.result()` on GUI thread)

### Strings & Containers
- [ ] Non-`const` Qt containers wrapped in `std::as_const()` in read-only range-`for` loops (no implicit-sharing detach)
- [ ] `u"..."_s` / `QStringLiteral` used for `QString` construction; `u"..."` / `QStringView` / `QLatin1StringView` used for zero-allocation comparisons
- [ ] Multi-argument `QString::arg(a, b)` used instead of chained `.arg(a).arg(b)`; user-facing strings use plural-aware `tr()`

### Model/View & Painting
- [ ] `beginInsertRows` / `beginRemoveRows` guard empty batches and pass an **inclusive** `last` index (`first + count - 1`)
- [ ] `dataChanged` checks bounds and value equality; `beginResetModel()` reserved for full resets
- [ ] Custom `QStyledItemDelegate::paint()` saves/restores `QPainter` state; `paintEvent()` never mutates widget geometry or performs I/O

### QML / Qt Quick
- [ ] C++ types registered via `qt_add_qml_module` + `QML_ELEMENT` / `QML_SINGLETON` (avoid `setContextProperty`)
- [ ] Unparented C++-owned `QObject*` returned from `Q_INVOKABLE` explicitly sets `QQmlEngine::CppOwnership`
- [ ] `pragma ComponentBehavior: Bound` and `required property` used in delegates; heavy logic kept out of QML JS

### Networking, I/O & Security
- [ ] `QNetworkAccessManager` reused; `QNetworkReply` connected to `deleteLater()`, configured with `setTransferTimeout()`, and checked for both network and HTTP errors
- [ ] `QProcess` passes program and `QStringList` arguments separately (never `startCommand` / shell with user input) and avoids `waitForFinished(-1)` on GUI thread
- [ ] `QSqlQuery` uses `prepare()` + `bindValue()` (no string interpolation)
- [ ] `QSaveFile` used for atomic config/document writes; `QLabel` uses `Qt::PlainText` for untrusted strings

### Testing & Tooling
- [ ] `QTest` covers core logic, signals (`QSignalSpy`), and models (`QAbstractItemModelTester`)
- [ ] Async/GUI tests use `QTRY_VERIFY` / `QTRY_COMPARE` instead of `QTest::qWait()` sleeps and `QVERIFY` `findChild` pointers
- [ ] `Q_OBJECT` macro present on every `QObject` subclass; `clazy` and `qmllint` warnings addressed

---

## References

- [Qt 6 Object Trees & Ownership](https://doc.qt.io/qt-6/objecttrees.html)
- [Qt 6 Signals & Slots](https://doc.qt.io/qt-6/signalsandslots.html)
- [Qt 6 Threads and QObjects](https://doc.qt.io/qt-6/threads-qobject.html)
- [Qt 6 Implicit Sharing](https://doc.qt.io/qt-6/implicit-sharing.html)
- [Qt 6 Model/View Programming](https://doc.qt.io/qt-6/model-view-programming.html)
- [Qt 6 Data Type Conversion Between QML and C++ (Ownership)](https://doc.qt.io/qt-6/qtqml-cppintegration-data.html)
- [Porting to Qt 6 Guide](https://doc.qt.io/qt-6/portingguide.html)
- [Qt Test Overview](https://doc.qt.io/qt-6/qtest-overview.html)
- [Clazy — Qt-oriented Clang Static Analyzer](https://invent.kde.org/sdk/clazy)
- [C++ Code Review Guide](cpp.md)
- [Async & Concurrency Guide](cross-cutting/async-concurrency-patterns.md)
- [SQL Injection Prevention Guide](cross-cutting/sql-injection-prevention.md)
- [Error Handling Guide](cross-cutting/error-handling-principles.md)
- [Performance Review Guide](performance-review-guide.md)
- [Security Review Guide](security-review-guide.md)
