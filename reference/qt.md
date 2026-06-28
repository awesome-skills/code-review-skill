# Qt Code Review Guide

> Code review guidelines focusing on object model, signals/slots, Model/View, QML, Qt6 migration, event loop, testing, and GUI performance. Examples based on Qt 5.15 / Qt 6.

## Table of Contents

- [Object Model & Memory Management](#object-model--memory-management)
- [Signals & Slots](#signals--slots)
- [Containers & Strings](#containers--strings)
- [Threads & Concurrency](#threads--concurrency)
- [GUI & Widgets](#gui--widgets)
- [Model/View Architecture](#modelview-architecture)
- [Meta-Object System](#meta-object-system)
- [QML / Qt Quick](#qml--qt-quick)
- [Qt5 → Qt6 Migration](#qt5--qt6-migration)
- [Testing](#testing)
- [Review Checklist](#review-checklist)

---

## Object Model & Memory Management

### Use Parent-Child Ownership Mechanism
Qt's `QObject` hierarchy automatically manages memory. For `QObject`, prefer setting a parent object over manual `delete` or smart pointers.

```cpp
// ❌ Manual management prone to memory leaks
QWidget* w = new QWidget();
QLabel* l = new QLabel();
l->setParent(w);
// ... If w is deleted, l is automatically deleted. But if w leaks, l also leaks.

// ✅ Specify parent in constructor
QWidget* w = new QWidget(this); // Owned by 'this'
QLabel* l = new QLabel(w);      // Owned by 'w'
```

### Use Smart Pointers with QObject
If a `QObject` has no parent, use `QScopedPointer` or `std::unique_ptr` with a custom deleter (use `deleteLater` if cross-thread). Avoid `std::shared_ptr` for `QObject` unless necessary, as it confuses the parent-child ownership system.

```cpp
// ✅ Scoped pointer for local/member QObject without parent
QScopedPointer<MyObject> obj(new MyObject());

// ✅ Safe pointer to prevent dangling pointers
QPointer<MyObject> safePtr = obj.data();
if (safePtr) {
    safePtr->doSomething();
}
```

### Use `deleteLater()`
For asynchronous deletion, especially in slots or event handlers, use `deleteLater()` instead of `delete` to ensure pending events in the event loop are processed.

```cpp
// ❌ Bad: delete in a slot may invalidate sender during signal emission
void MyWidget::onFinished() {
    delete this;  // UB: may be called from within a signal chain
}

// ✅ Good: safe deferred deletion
void MyWidget::onFinished() {
    deleteLater();
}
```

### Avoid double ownership

```cpp
// ❌ Bad: parent owns the dialog, but we also store it in unique_ptr
auto dialog = std::make_unique<QDialog>(this);  // 'this' is parent AND unique_ptr owns it

// ✅ Good: parent owns it, raw pointer for access
auto* dialog = new QDialog(this);
```

---

## Signals & Slots

### Prefer Function Pointer Syntax
Use compile-time checked syntax (Qt 5+).

```cpp
// ❌ String-based (runtime check only, slower)
connect(sender, SIGNAL(valueChanged(int)), receiver, SLOT(updateValue(int)));

// ✅ Compile-time check
connect(sender, &Sender::valueChanged, receiver, &Receiver::updateValue);
```

### Lambda connections — specify context object

```cpp
// ❌ Bad: lambda captures `this` raw; crashes if object is deleted
connect(timer, &QTimer::timeout, [this]() {
    update();  // crashes if 'this' was destroyed
});

// ✅ Good: context object disconnects automatically on destruction
connect(timer, &QTimer::timeout, this, [this]() {
    update();
});
```

### Connection Types
Be explicit or aware of connection types when crossing threads.
- `Qt::AutoConnection` (Default): Direct if same thread, Queued if different thread.
- `Qt::QueuedConnection`: Always posts event (thread-safe across threads).
- `Qt::DirectConnection`: Immediate call (dangerous if accessing non-thread-safe data across threads).

### Avoid Loops
Check logic that might cause infinite signal loops (e.g., `valueChanged` -> `setValue` -> `valueChanged`). Block signals or check for equality before setting values.

```cpp
void MyClass::setValue(int v) {
    if (m_value == v) return; // ✅ Good: Break loop
    m_value = v;
    emit valueChanged(v);
}
```

### Disconnect when appropriate

```cpp
// ✅ Good: explicit disconnect before changing target
disconnect(oldSource, &Source::data, this, &Receiver::onData);
connect(newSource, &Source::data, this, &Receiver::onData);
```

---

## Containers & Strings

### QString Efficiency
- Use `QStringLiteral("...")` for compile-time string creation to avoid runtime allocation.
- Use `QLatin1String` for comparison with ASCII literals (in Qt 5).
- Prefer `arg()` for formatting (or `QStringBuilder`'s `%` operator).

```cpp
// ❌ Runtime conversion
if (str == "test") ...

// ✅ Prefer QLatin1String for comparison with ASCII literals (in Qt 5)
if (str == QLatin1String("test")) ... // Qt 5
if (str == u"test"_s) ...             // Qt 6
```

### Container Selection
- **Qt 6**: `QList` is now the default choice (unified with `QVector`).
- **Qt 5**: Prefer `QVector` over `QList` for contiguous memory and cache performance, unless stable references are needed.
- Be aware of Implicit Sharing (Copy-on-Write). Passing containers by value is cheap *until* modified. Use `const &` for read-only access.

```cpp
// ❌ Forces deep copy if function modifies 'list'
void process(QVector<int> list) {
    list[0] = 1;
}

// ✅ Read-only reference
void process(const QVector<int>& list) { ... }
```

### Use constBegin/constEnd for read-only iteration

```cpp
// ❌ Bad: begin()/end() may trigger detach
for (auto it = list.begin(); it != list.end(); ++it) {
    qDebug() << *it;
}

// ✅ Good: const iteration avoids detach
for (auto it = list.constBegin(); it != list.constEnd(); ++it) {
    qDebug() << *it;
}

// ✅ Best: range-based for with const ref (Qt 5.7+)
for (const auto& item : list) {
    qDebug() << item;
}
```

---

## Threads & Concurrency

### Subclassing QThread vs Worker Object
Prefer the "Worker Object" pattern over subclassing `QThread` implementation details.

```cpp
// ❌ Business logic inside QThread::run()
class MyThread : public QThread {
    void run() override { ... }
};

// ✅ Worker object moved to thread
QThread* thread = new QThread;
Worker* worker = new Worker;
worker->moveToThread(thread);
connect(thread, &QThread::started, worker, &Worker::process);
connect(thread, &QThread::finished, worker, &QObject::deleteLater);
thread->start();
```

### GUI Thread Safety
**NEVER** access UI widgets (`QWidget` and subclasses) from a background thread. Use signals/slots to communicate updates to the main thread.

```cpp
// ❌ Bad: accessing widget from worker thread
void Worker::onResult(Data data) {
    label->setText(data.toString());  // CRASH: not in GUI thread
}

// ✅ Good: signal to GUI thread
void Worker::onResult(Data data) {
    emit resultReady(data);  // connected via QueuedConnection
}
// In main thread:
connect(worker, &Worker::resultReady, this, [this](const Data& d) {
    label->setText(d.toString());
});
```

### QtConcurrent for simple parallelism

```cpp
// ✅ Good: simple parallel computation
auto future = QtConcurrent::run([data]() {
    return heavyComputation(data);
});

// ✅ Good: map-reduce pattern
auto results = QtConcurrent::mappedReduced(
    inputList,
    [](const Item& item) { return process(item); },
    [](int& result, int value) { result += value; }
);
```

---

## GUI & Widgets

### Logic Separation
Keep business logic out of UI classes (`MainWindow`, `Dialog`). UI classes should only handle display and user input forwarding.

### Layouts
Avoid fixed sizes (`setGeometry`, `resize`). Use layouts (`QVBoxLayout`, `QGridLayout`) to handle different DPIs and window resizing gracefully.

### Blocking Event Loop
Never execute long-running operations on the main thread (freezes GUI).
- **Bad**: `Sleep()`, `while(busy)`, synchronous network calls.
- **Good**: `QProcess`, `QThread`, `QtConcurrent`, or asynchronous APIs (`QNetworkAccessManager`).

### High-DPI scaling

```cpp
// ✅ Qt 5: enable high-DPI scaling
QGuiApplication::setAttribute(Qt::AA_EnableHighDpiScaling);

// ✅ Qt 6: enabled by default, but verify icons and custom painting scale correctly
```

---

## Model/View Architecture

### Subclass QAbstractItemModel correctly

When implementing a custom model, the following methods are **required**:

```cpp
class TaskModel : public QAbstractTableModel {
    Q_OBJECT
public:
    int rowCount(const QModelIndex& parent = {}) const override {
        if (parent.isValid()) return 0;  // table model has no tree
        return m_tasks.size();
    }

    int columnCount(const QModelIndex& parent = {}) const override {
        if (parent.isValid()) return 0;
        return 3;  // title, priority, status
    }

    QVariant data(const QModelIndex& index, int role) const override {
        if (!index.isValid() || index.row() >= m_tasks.size())
            return {};

        if (role == Qt::DisplayRole) {
            switch (index.column()) {
                case 0: return m_tasks[index.row()].title;
                case 1: return m_tasks[index.row()].priority;
                case 2: return m_tasks[index.row()].status;
            }
        }
        return {};
    }

    // Required for headers
    QVariant headerData(int section, Qt::Orientation orientation, int role) const override {
        if (role != Qt::DisplayRole) return {};
        if (orientation == Qt::Horizontal) {
            switch (section) {
                case 0: return "Title";
                case 1: return "Priority";
                case 2: return "Status";
            }
        }
        return section + 1;  // row numbers
    }

private:
    QVector<Task> m_tasks;
};
```

### Notify the view of changes

```cpp
// ❌ Bad: modifying data without notifying the view
void TaskModel::addTask(const Task& task) {
    m_tasks.append(task);  // view doesn't know about the change
}

// ✅ Good: emit proper signals
void TaskModel::addTask(const Task& task) {
    beginInsertRows({}, m_tasks.size(), m_tasks.size());
    m_tasks.append(task);
    endInsertRows();
}

void TaskModel::updateStatus(int row, const QString& status) {
    m_tasks[row].status = status;
    emit dataChanged(index(row, 2), index(row, 2), {Qt::DisplayRole});
}

void TaskModel::clearAll() {
    beginResetModel();
    m_tasks.clear();
    endResetModel();
}
```

### Delegate pattern for custom rendering

```cpp
class PriorityDelegate : public QStyledItemDelegate {
    Q_OBJECT
public:
    void paint(QPainter* painter, const QStyleOptionViewItem& option,
               const QModelIndex& index) const override {
        QStyleOptionViewItem opt = option;
        initStyleOption(&opt, index);

        // Color-code by priority
        QString priority = index.data().toString();
        if (priority == "High") {
            opt.backgroundBrush = QColor("#ffcccc");
        } else if (priority == "Low") {
            opt.backgroundBrush = QColor("#ccffcc");
        }

        QStyledItemDelegate::paint(painter, opt, index);
    }
};

// Usage:
tableView->setItemDelegateForColumn(1, new PriorityDelegate(this));
```

### Performance with large datasets

- Use `beginInsertRows`/`endInsertRows` for batch inserts, not one row at a time.
- For 100K+ rows, consider `QSortFilterProxyModel` for filtering instead of re-querying.
- Use `model()->fetchMore()` for lazy loading / pagination.
- Avoid `Qt::UserRole + N` with heavy objects; use a lightweight key and look up externally.

---

## Meta-Object System

### Properties & Enums
Use `Q_PROPERTY` for values exposed to QML or needing introspection.
Use `Q_ENUM` to enable string conversion for enums.

```cpp
class MyObject : public QObject {
    Q_OBJECT
    Q_PROPERTY(int value READ value WRITE setValue NOTIFY valueChanged)
public:
    enum State { Idle, Running };
    Q_ENUM(State)
    // ...
};
```

### qobject_cast
Use `qobject_cast<T*>` for QObjects instead of `dynamic_cast`. It is faster and doesn't require RTTI.

### Q_GADGET for value types

```cpp
// ✅ Good: introspection without QObject overhead
struct Coordinate {
    Q_GADGET
    Q_PROPERTY(double x MEMBER x)
    Q_PROPERTY(double y MEMBER y)
public:
    double x = 0.0;
    double y = 0.0;
};
Q_DECLARE_METATYPE(Coordinate)
```

---

## QML / Qt Quick

### C++/QML boundary design

```cpp
// ✅ Good: expose C++ model to QML via context property (Qt 5) or QML_SINGLETON (Qt 6)

// Qt 6: QML_ELEMENT + QML_SINGLETON
class AppSettings : public QObject {
    Q_OBJECT
    QML_ELEMENT
    QML_SINGLETON
    Q_PROPERTY(QString theme READ theme WRITE setTheme NOTIFY themeChanged)
public:
    QString theme() const { return m_theme; }
    void setTheme(const QString& t) {
        if (m_theme != t) {
            m_theme = t;
            emit themeChanged();
        }
    }
signals:
    void themeChanged();
private:
    QString m_theme;
};
```

### QML performance best practices

```qml
// ❌ Bad: JavaScript in onCompleted blocks UI thread
Component.onCompleted: {
    for (var i = 0; i < 10000; i++) {
        model.append({"value": i});  // slow, blocks rendering
    }
}

// ✅ Good: use C++ model, or WorkerScript for heavy JS
// Prefer C++ QAbstractListModel for large datasets
```

```qml
// ❌ Bad: frequent property bindings cause re-evaluation
Rectangle {
    width: parent.width * 0.8 + someComplexCalc()
    height: parent.height * 0.6 + anotherCalc()
}

// ✅ Good: minimize binding complexity
Rectangle {
    width: parent.width * 0.8
    height: parent.height * 0.6
}
```

### QML object lifecycle

- QML-created objects are owned by the QML engine.
- `Qt.createComponent()` + `createObject()` — caller manages lifetime.
- Use `Loader` for lazy instantiation of heavy components.
- `property var myObj: QtObject {}` — the QML engine owns it.

```qml
// ✅ Good: Loader for conditional heavy UI
Loader {
    id: detailLoader
    active: selectedItem !== null
    sourceComponent: active ? detailComponent : null
}
```

---

## Qt5 → Qt6 Migration

### Key breaking changes

| Qt 5 | Qt 6 | Notes |
|------|------|-------|
| `QList` ≠ `QVector` | `QList` = `QVector` | Unified; QList is now QVector internally |
| `QStringRef` | `QStringView` | QStringView is non-owning, more like string_view |
| `QLatin1String` | `QLatin1StringView` | Or use `u"..."_s` string literals |
| `QTextStream(stream)` | `QTextStream(&string)` | Constructor changes |
| `QMouseEvent::pos()` | `QMouseEvent::position()` | Returns QPointF instead of QPoint |
| `QWheelEvent::delta()` | `QWheelEvent::angleDelta()` | Already deprecated in Qt 5 |
| `QComboBox::activated(int)` | `QComboBox::textActivated(QString)` | Overload disambiguation |

### CMake replaces qmake

```cmake
# ✅ Qt 6 CMakeLists.txt
cmake_minimum_required(VERSION 3.16)
project(MyApp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets Quick Core)

qt_add_executable(MyApp
    main.cpp
    MainWindow.cpp
    MainWindow.h
    resources.qrc
)

target_link_libraries(MyApp PRIVATE
    Qt6::Widgets
    Qt6::Quick
    Qt6::Core
)
```

### Qt6 new APIs and improvements

```cpp
// ✅ Qt 6: QStringView instead of QStringRef
void process(QStringView sv);  // non-owning, efficient

// ✅ Qt 6: QCalendar API for date handling
QCalendar cal(QCalendar::System::Gregorian);
QDate date = cal.dateFromParts(2024, 3, 15);

// ✅ Qt 6: Qt Concurrent improvements
auto future = QtConcurrent::run(QThreadPool::globalInstance(),
                                 []() { return heavyWork(); });

// ✅ Qt 6: Compare API for containers
QList<int> a = {1, 2, 3};
QList<int> b = {1, 2, 3};
bool eq = a == b;  // works correctly in Qt 6
```

### Migration checklist

- [ ] Replace `qmake` with `CMake` (or use `qt-cmake`)
- [ ] Replace `QStringRef` with `QStringView`
- [ ] Replace deprecated event accessors (`pos()` → `position()`)
- [ ] Update signal/slot connections for overloaded signals (use `qOverload`)
- [ ] Verify `QList`/`QVector` interchangeability
- [ ] Test with Qt 6 compatibility module: `find_package(Qt6 COMPONENTS Core5Compat)`

---

## Testing

### QTest framework

```cpp
#include <QtTest>
#include "parser.h"

class TestParser : public QObject {
    Q_OBJECT
private slots:
    void testEmptyInput() {
        Parser p("");
        QVERIFY(p.nextToken().isNull());
    }

    void testIntegerToken() {
        Parser p("42");
        auto token = p.nextToken();
        QCOMPARE(token.type(), Token::Integer);
        QCOMPARE(token.value().toInt(), 42);
    }

    void testNegativeNumber() {
        Parser p("-7");
        auto token = p.nextToken();
        QCOMPARE(token.value().toInt(), -7);
    }

    // Data-driven test
    void testValidTokens_data() {
        QTest::addColumn<QString>("input");
        QTest::addColumn<int>("expectedType");

        QTest::newRow("integer") << "42" << static_cast<int>(Token::Integer);
        QTest::newRow("string") << "\"hello\"" << static_cast<int>(Token::String);
        QTest::newRow("operator") << "+" << static_cast<int>(Token::Operator);
    }

    void testValidTokens() {
        QFETCH(QString, input);
        QFETCH(int, expectedType);

        Parser p(input);
        auto token = p.nextToken();
        QCOMPARE(token.type(), static_cast<Token::Type>(expectedType));
    }
};

QTEST_MAIN(TestParser)
#include "test_parser.moc"
```

### GUI testing with QTest

```cpp
class TestLoginDialog : public QObject {
    Q_OBJECT
private slots:
    void testLoginButtonDisabledWhenEmpty() {
        LoginDialog dialog;
        dialog.show();
        QVERIFY(QTest::qWaitForWindowExposed(&dialog));

        // Initially, login button should be disabled
        QPushButton* loginBtn = dialog.findChild<QPushButton*>("loginButton");
        QVERIFY(loginBtn != nullptr);
        QVERIFY(!loginBtn->isEnabled());
    }

    void testLoginEnabledAfterInput() {
        LoginDialog dialog;
        dialog.show();
        QVERIFY(QTest::qWaitForWindowExposed(&dialog));

        QLineEdit* userField = dialog.findChild<QLineEdit*>("usernameField");
        QLineEdit* passField = dialog.findChild<QLineEdit*>("passwordField");

        QTest::keyClicks(userField, "alice");
        QTest::keyClicks(passField, "secret123");

        QPushButton* loginBtn = dialog.findChild<QPushButton*>("loginButton");
        QVERIFY(loginBtn->isEnabled());
    }

    void testSubmitOnEnter() {
        LoginDialog dialog;
        dialog.show();
        QVERIFY(QTest::qWaitForWindowExposed(&dialog));

        QLineEdit* userField = dialog.findChild<QLineEdit*>("usernameField");
        QTest::keyClicks(userField, "alice");
        QTest::keyClick(userField, Qt::Key_Return);

        // Verify the dialog emitted the accepted signal
        QTRY_COMPARE(dialog.result(), static_cast<int>(QDialog::Accepted));
    }
};
```

### Mock Qt objects for unit testing

```cpp
// ✅ Good: inject dependencies for testability
class NetworkService {
public:
    virtual ~NetworkService() = default;
    virtual QJsonObject fetchUser(int id) = 0;
};

class MockNetworkService : public NetworkService {
public:
    QJsonObject fetchUser(int id) override {
        return m_responses.value(id, {});
    }
    void setResponse(int id, const QJsonObject& json) {
        m_responses[id] = json;
    }
private:
    QHash<int, QJsonObject> m_responses;
};

// In test:
void testProfileDisplay() {
    MockNetworkService mock;
    mock.setResponse(1, {{"name", "Alice"}, {"role", "admin"}});

    ProfileController controller(&mock);
    controller.loadProfile(1);
    QCOMPARE(controller.name(), "Alice");
    QCOMPARE(controller.role(), "admin");
}
```

### CI integration

```bash
# Qt 6 test runner
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON
cmake --build .
ctest --output-on-failure

# With Xvfb for GUI tests on headless CI
xvfb-run -a ctest --output-on-failure
```

---

## Review Checklist

### Memory
- [ ] Is parent-child relationship correct? Are dangling pointers avoided (using `QPointer`)?
- [ ] No double ownership (parent + smart pointer)
- [ ] `deleteLater()` used instead of `delete` in slots

### Signals & Slots
- [ ] Function pointer syntax used (compile-time checked)
- [ ] Lambda connections have context object for auto-disconnect
- [ ] No signal loops (guard with equality check or blockSignals)
- [ ] Proper disconnect when changing signal sources

### Threads
- [ ] Is UI accessed only from main thread?
- [ ] Are long tasks offloaded (QThread worker, QtConcurrent)?
- [ ] Worker object pattern preferred over QThread subclassing
- [ ] Proper cleanup: thread quit + wait before delete

### Strings & Containers
- [ ] `QStringLiteral` or `u"..."_s` used for compile-time strings
- [ ] `const &` used for read-only container access
- [ ] No implicit detach in loops (use const iterators or range-for with const ref)

### Model/View
- [ ] begin/end Insert/Remove/Reset signals emitted correctly
- [ ] dataChanged emitted for individual item updates
- [ ] Delegate used for custom rendering (not subclassing view)

### QML
- [ ] C++/QML boundary uses QML_ELEMENT (Qt 6) or registered types
- [ ] Heavy computation not in QML JS
- [ ] Loader used for conditional/lazy component instantiation

### Testing
- [ ] QTest unit tests for core logic
- [ ] GUI tests use QTest::keyClicks / qWaitForWindowExposed
- [ ] Dependencies injected for mockability
- [ ] Tests run in CI (with Xvfb for GUI tests)

### Style
- [ ] Naming conventions (camelCase for methods, PascalCase for classes)
- [ ] Resources loaded from `.qrc`
- [ ] `Q_OBJECT` macro present in all QObject subclasses
