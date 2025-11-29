# Python Code Review Guide

> Python 代码审查指南，覆盖常见陷阱和最佳实践。

---

## 常见陷阱

### 可变默认参数

```python
# ❌ Mutable default arguments
def add_item(item, items=[]):  # Bug! Shared across calls
    items.append(item)
    return items

# ✅ Use None as default
def add_item(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items
```

### 异常捕获过宽

```python
# ❌ Catching too broad
try:
    result = risky_operation()
except:  # Catches everything, even KeyboardInterrupt!
    pass

# ✅ Catch specific exceptions
try:
    result = risky_operation()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
    raise
```

### 可变类属性

```python
# ❌ Using mutable class attributes
class User:
    permissions = []  # Shared across all instances!

# ✅ Initialize in __init__
class User:
    def __init__(self):
        self.permissions = []
```

---

## Python Review Checklist

### 数据结构
- [ ] 没有使用可变默认参数（list、dict、set）
- [ ] 类属性不是可变对象
- [ ] 理解浅拷贝和深拷贝的区别

### 异常处理
- [ ] 捕获特定异常类型，不使用裸 `except:`
- [ ] 异常信息有意义，便于调试
- [ ] 必要时重新抛出异常（`raise`）

### 性能
- [ ] 大数据集使用生成器而非列表
- [ ] 避免循环中重复创建对象
- [ ] 使用 `collections` 模块的高效数据结构

### 代码风格
- [ ] 遵循 PEP 8 风格指南
- [ ] 使用类型注解（type hints）
- [ ] 函数和类有 docstring
