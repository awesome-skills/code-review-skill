# Django / DRF Code Review Guide

> Django / DRF 代码审查指南，覆盖安全审查、N+1 查询优化、Serializer 反模式、ViewSet 最佳实践、异步视图及生产安全配置等核心主题。

## 目录

- [安全审查](#安全审查)
- [N+1 查询优化](#n1-查询优化)
- [Serializer 反模式](#serializer-反模式)
- [ViewSet 最佳实践](#viewset-最佳实践)
- [异步视图](#异步视图)
- [中间件与设置](#中间件与设置)
- [Review Checklist](#review-checklist)

---

## 安全审查

### XSS 防护

Django 模板引擎默认自动转义。审查重点：`mark_safe`、`autoescape off`、`format_html` 的使用。

> **跨框架 XSS 防护详见 [XSS Prevention Guide](cross-cutting/xss-prevention.md)**，含 React/Vue/Angular/Svelte 示例及 CSP 配置。

### CSRF 防护

```python
from django.views.decorators.csrf import csrf_exempt

# ❌ 禁用 CSRF 保护
@csrf_exempt
def process_payment(request):
    # 任何恶意网站都可以提交表单
    amount = request.POST["amount"]
    charge(amount)

# ✅ 保留默认 CSRF 保护
from django.middleware.csrf import CsrfViewMiddleware

# settings.py — 确保 CSRF 中间件已启用
MIDDLEWARE = [
    # ...
    "django.middleware.csrf.CsrfViewMiddleware",
    # ...
]

# ✅ API 使用 token 认证代替 CSRF
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
}

# ✅ 前端 AJAX 请求带上 CSRF token
# JavaScript: fetch("/api/endpoint/", {
#   headers: {"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value}
# })
```

### Cookie 安全设置

```python
# settings.py

# ❌ 不安全的 cookie 配置
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = False

# ✅ 生产环境 cookie 安全配置
SESSION_COOKIE_SECURE = True    # HTTPS only
SESSION_COOKIE_HTTPONLY = True   # JavaScript 无法读取
SESSION_COOKIE_SAMESITE = "Lax"  # 防止 CSRF
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
```

### SQL 注入防护

Django ORM 自动参数化查询。审查重点：`raw()`、`extra()`、`RawSQL`、`connection.cursor()` 中的字符串拼接。

> **跨语言 SQL 注入防护详见 [SQL Injection Prevention Guide](cross-cutting/sql-injection-prevention.md)**，含 Python/Java/Go/Node.js/PHP/C# 示例及 ORM 不安全用法。

### 文件上传安全

```python
# settings.py

# ❌ 默认上传配置不安全
FILE_UPLOAD_MAX_MEMORY_SIZE = 2621440  # 2.5 MB — 可以接受
MEDIA_ROOT = "/var/www/uploads"         # web 根目录下
ALLOWED_UPLOAD_TYPES = None             # 没有类型限制

# ✅ 限制上传大小和位置
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 2621440   # 2.5 MB in-memory
MEDIA_ROOT = "/srv/media/"              # web 根目录之外

# ✅ 验证文件类型
import mimetypes
from pathlib import Path

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}

def validate_upload(file):
    ext = Path(file.name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"File type {ext} is not allowed.")
    mime, _ = mimetypes.guess_type(file.name)
    if mime not in {"image/jpeg", "image/png", "application/pdf"}:
        raise ValidationError("Invalid MIME type.")
```

---

## N+1 查询优化

> 📖 通用原理和跨语言方案详见 [N+1 查询跨语言指南](cross-cutting/n-plus-one-queries.md)

### select_related（ForeignKey / OneToOne）

```python
# ❌ N+1: 每本书查一次出版社
books = Book.objects.all()
for book in books:
    print(book.publisher.name)  # 额外 N 条查询

# ✅ select_related 一次 JOIN 查询
books = Book.objects.select_related("publisher")
for book in books:
    print(book.publisher.name)  # 无额外查询

# ✅ 多层关系
books = Book.objects.select_related("publisher", "publisher__country")

# ✅ 只查需要的字段（延迟加载优化）
books = Book.objects.select_related("publisher").only(
    "title", "publisher__name"
)
```

### prefetch_related（M2M / 反向 ForeignKey）

```python
# ❌ N+1: 每个作者查一次书
authors = Author.objects.all()
for author in authors:
    print(author.books.all())  # 额外 N 条查询

# ✅ prefetch_related 两条查询 + Python 合并
authors = Author.objects.prefetch_related("books")
for author in authors:
    print(list(author.books.all()))  # 无额外查询

# ✅ 嵌套 prefetch
authors = Author.objects.prefetch_related(
    "books",
    "books__publisher",
)

# ✅ Prefetch 对象控制预查行为
from django.db.models import Prefetch

authors = Author.objects.prefetch_related(
    Prefetch(
        "books",
        queryset=Book.objects.filter(published=True).only("title", "author_id"),
        to_attr="published_books",
    )
)
for author in authors:
    print(author.published_books)  # 已过滤，存在 to_attr 中
```

### QuerySet 缓存误用

```python
# ❌ count() 后再迭代 —— 两次查询
qs = Book.objects.all()
count = qs.count()          # 查询 1: SELECT COUNT(*) — 不填充缓存
titles = [b.title for b in qs]  # 查询 2: SELECT * — 重新评估

# ✅ 既要对象又要数量时，用 len() 触发一次评估并复用缓存
qs = Book.objects.all()
count = len(qs)             # 查询 1: SELECT * — 全部加载并缓存
titles = [b.title for b in qs]  # 复用缓存，无新查询

# ✅ 如果需要多次迭代，先转 list
books = list(Book.objects.all())  # 一次查询
count = len(books)
titles = [b.title for b in books]
```

### 切片/索引不填充缓存

```python
# ❌ 反复索引未评估的 QuerySet —— 每次都查库
qs = Book.objects.all()
qs[0]   # 查询 1: SELECT ... LIMIT 1
qs[0]   # 查询 2 — 切片/索引不会填充缓存

# ✅ 先整体评估，缓存保存所有行，之后索引走缓存
qs = Book.objects.all()
list(qs)    # SELECT * — 评估并缓存全部行
qs[0]       # 走缓存，无查询
qs[5]       # 走缓存，无查询

# ✅ 只需要前 N 条时，切一次并转 list
books = list(Book.objects.all()[:10])  # 一次查询：SELECT ... LIMIT 10
first = books[0]
rest = books[1:]   # 已是 Python list，无查询
```

### len() vs count()

```python
# ❌ len() 加载全部对象到内存
total = len(Book.objects.all())  # SELECT * FROM book — 全表加载

# ✅ count() 在数据库端计数
total = Book.objects.count()  # SELECT COUNT(*) — 高效

# ✅ 如果已经需要 QuerySet 结果，再用 len
books = list(Book.objects.filter(published=True))
total = len(books)  # 已在内存中，不需要额外查询
```

### if qs vs qs.exists()

```python
# ❌ if qs 加载全部记录
qs = Book.objects.filter(author_id=author_id)
if qs:  # SELECT * FROM book WHERE ... — 全部加载
    return qs[0]

# ✅ exists() 只检查是否有记录
if Book.objects.filter(author_id=author_id).exists():
    return Book.objects.filter(author_id=author_id).first()

# ✅ 或者直接 get/first 判空
book = Book.objects.filter(author_id=author_id).first()
if book is not None:
    return book
```

---

## Serializer 反模式

### 排除敏感字段

```python
from rest_framework import serializers

# ❌ __all__ 暴露所有字段，包括敏感数据
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"  # 密码 hash、is_superuser 等全部暴露

# ✅ 显式列出允许的字段
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]

# ✅ 使用 exclude 时也要注意
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        exclude = ["internal_notes", "admin_flags"]

# ✅ 密码字段用 write_only
class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]

    def create(self, validated_data):
        user = User(**validated_data)
        user.set_password(validated_data["password"])
        user.save()
        return user
```

### 缺少验证

```python
from rest_framework import serializers

# ❌ 没有验证，信任所有输入
class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["quantity", "price", "discount"]

# ✅ 字段级验证
class OrderSerializer(serializers.ModelSerializer):
    quantity = serializers.IntegerField(min_value=1, max_value=100)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    discount = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=1, required=False
    )

    class Meta:
        model = Order
        fields = ["quantity", "price", "discount"]

# ✅ 对象级验证
class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["quantity", "price", "discount"]

    def validate(self, attrs):
        if attrs.get("discount", 0) > 0.5 and attrs.get("quantity", 0) < 10:
            raise serializers.ValidationError(
                "Bulk discount requires minimum 10 items."
            )
        return attrs

# ✅ 自定义字段验证方法
class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ["start_date", "end_date", "room"]

    def validate_start_date(self, value):
        if value < date.today():
            raise serializers.ValidationError("Start date cannot be in the past.")
        return value

    def validate(self, attrs):
        if attrs["end_date"] <= attrs["start_date"]:
            raise serializers.ValidationError("End date must be after start date.")
        return attrs
```

### 嵌套写入

```python
from rest_framework import serializers

# ❌ 嵌套 Serializer 只读但没有实现 create/update
class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]

class ArticleSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)  # 嵌套写入会失败

    class Meta:
        model = Article
        fields = ["id", "title", "tags"]

# ✅ 方案 1: 嵌套只读 + PrimaryKeyRelatedField 写入
class ArticleSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        many=True,
        write_only=True,
        source="tags",
    )

    class Meta:
        model = Article
        fields = ["id", "title", "tags", "tag_ids"]

# ✅ 方案 2: 实现 create() 处理嵌套
class ArticleSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)

    class Meta:
        model = Article
        fields = ["id", "title", "tags"]

    def create(self, validated_data):
        tags_data = validated_data.pop("tags")
        article = Article.objects.create(**validated_data)
        for tag_data in tags_data:
            tag, _ = Tag.objects.get_or_create(**tag_data)
            article.tags.add(tag)
        return article

    def update(self, instance, validated_data):
        tags_data = validated_data.pop("tags", None)
        instance = super().update(instance, validated_data)
        if tags_data is not None:
            instance.tags.clear()
            for tag_data in tags_data:
                tag, _ = Tag.objects.get_or_create(**tag_data)
                instance.tags.add(tag)
        return instance
```

### read_only_fields 遗漏

```python
from rest_framework import serializers

# ❌ 计算字段和自动字段可被用户覆盖
class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["id", "body", "author", "created_at", "updated_at"]
        # created_at, updated_at, author 可被客户端篡改

# ✅ 标记只读字段
class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["id", "body", "author", "created_at", "updated_at"]
        read_only_fields = ["author", "created_at", "updated_at"]

# ✅ 在视图中设置只读字段（如当前用户）
class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
```

---

## ViewSet 最佳实践

### 选择正确的基类

```python
from rest_framework import viewsets

# ❌ ModelViewSet 提供完整 CRUD，但只需要读取
class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    # 暴露了 destroy, update, create — 标签不应被随意修改

# ✅ 只读场景用 ReadOnlyModelViewSet
class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    # 只提供 list 和 retrieve

# ✅ 需要自定义操作时用 Mixin
from rest_framework import mixins

class TagViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    generics.GenericAPIView,
):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
```

### 用户级数据范围限定

```python
from rest_framework import viewsets

# ❌ 任何用户可以看到所有数据
class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer

# ✅ get_queryset 限定当前用户数据
class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return Document.objects.filter(
            owner=self.request.user
        ).select_related("owner")

# ✅ 管理员看全部，普通用户看自己的
class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        qs = Document.objects.select_related("owner")
        if self.request.user.is_staff:
            return qs
        return qs.filter(owner=self.request.user)

# ✅ perform_create 自动关联当前用户
class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
```

### 权限控制

```python
from rest_framework import permissions, viewsets

# ❌ 没有权限控制
class ArticleViewSet(viewsets.ModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer

# ✅ 类级别权限
class ArticleViewSet(viewsets.ModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [permissions.IsAuthenticated]

# ✅ 操作级别权限
from rest_framework.decorators import action

class ArticleViewSet(viewsets.ModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

# ✅ 自定义对象级权限
class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.owner == request.user
```

### 分页和节流

```python
# settings.py

# ❌ 没有分页和节流配置
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
}

# ✅ 全局分页和节流
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
}

# ✅ 自定义分页器
from rest_framework.pagination import PageNumberPagination

class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

class ArticleViewSet(viewsets.ModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    pagination_class = StandardPagination
```

---

## 异步视图

### 同步 ORM 在异步视图中的正确使用

```python
import asyncio
from asgiref.sync import sync_to_async
from django.http import JsonResponse

# ❌ 在 async 视图中直接调用同步 ORM — 阻塞事件循环
async def user_list(request):
    users = User.objects.all()  # Synchronous ORM call in async context!
    data = [{"id": u.id, "name": u.username} for u in users]
    return JsonResponse(data, safe=False)

# ✅ 使用 async ORM（Django 4.1+）
async def user_list(request):
    users = User.objects.all()
    data = []
    async for user in users:  # async iteration
        data.append({"id": user.id, "name": user.username})
    return JsonResponse(data, safe=False)

# ✅ 使用 aget / afilter / acreate
async def user_detail(request, pk):
    user = await User.objects.aget(pk=pk)
    return JsonResponse({"id": user.id, "name": user.username})

# ✅ 复杂查询用 sync_to_async
@sync_to_async
def get_user_with_profile(pk):
    return User.objects.select_related("profile").get(pk=pk)

async def user_profile(request, pk):
    user = await get_user_with_profile(pk)
    return JsonResponse({
        "id": user.id,
        "name": user.username,
        "bio": user.profile.bio,
    })
```

### 遗漏 await

```python
from django.http import JsonResponse

# ❌ 忘记 await — coroutine 不会执行，返回协程对象而非数据
async def user_detail(request, pk):
    user = User.objects.aget(pk=pk)  # Missing await!
    # user 是一个 coroutine 对象，不是 User 实例
    return JsonResponse({"name": user.username})  # RuntimeError

# ✅ 始终 await 异步 ORM 调用
async def user_detail(request, pk):
    user = await User.objects.aget(pk=pk)
    return JsonResponse({"name": user.username})

# ✅ 使用aget_or_404 的异步版本
from django.shortcuts import aget_object_or_404

async def user_detail(request, pk):
    user = await aget_object_or_404(User, pk=pk)
    return JsonResponse({"name": user.username})
```

### 异步视图中的事务

```python
from django.db import transaction
from asgiref.sync import sync_to_async

# ❌ transaction.atomic() 是同步的，不能直接在 async 中用
async def create_order(request):
    async with transaction.atomic():  # Error! Not async-compatible
        order = await Order.objects.acreate(total=100)
        await OrderItem.objects.acreate(order=order, product_id=1)
    return JsonResponse({"order_id": order.id})

# ✅ 用 sync_to_async 包装事务块
@sync_to_async
def _create_order_with_items():
    with transaction.atomic():
        order = Order.objects.create(total=100)
        OrderItem.objects.create(order=order, product_id=1)
        return order.id

async def create_order(request):
    order_id = await _create_order_with_items()
    return JsonResponse({"order_id": order_id})

# ✅ 多个操作打包到一个 sync_to_async 中
@sync_to_async
def _bulk_create_products(items):
    with transaction.atomic():
        products = Product.objects.bulk_create([Product(**i) for i in items])
        return [p.id for p in products]

async def import_products(request):
    ids = await _bulk_create_products(request.data)
    return JsonResponse({"ids": ids})
```

### 同步中间件拖慢异步性能

```python
# ❌ 同步中间件会把 async 视图降级为同步执行
class TimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):  # sync — blocks async views
        start = time.time()
        response = self.get_response(request)
        elapsed = time.time() - start
        response["X-Elapsed"] = str(elapsed)
        return response

# ✅ async-capable 中间件：async def __call__，并在 __init__ 里标记实例
import time
from asgiref.sync import iscoroutinefunction, markcoroutinefunction

class TimingMiddleware:
    async_capable = True
    sync_capable = False

    def __init__(self, get_response):
        self.get_response = get_response
        # get_response 是协程函数时标记自己，Django 才会 await 这个实例
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    async def __call__(self, request):
        start = time.time()
        response = await self.get_response(request)
        elapsed = time.time() - start
        response["X-Elapsed"] = str(elapsed)
        return response

# ✅ 要同时兼容同步和异步，用工厂函数 + 内置装饰器
from django.utils.decorators import sync_and_async_middleware
```

### async for 迭代模式

```python
from django.http import JsonResponse

# ❌ 同步迭代大型 QuerySet 在 async 视图中阻塞
async def export_users(request):
    users = User.objects.all()
    data = []  # 同步迭代阻塞事件循环
    for user in users:
        data.append({"id": user.id, "name": user.username})
    return JsonResponse(data, safe=False)

# ✅ 使用 async for 异步迭代
async def export_users(request):
    data = []
    async for user in User.objects.all():
        data.append({"id": user.id, "name": user.username})
    return JsonResponse(data, safe=False)

# ✅ 大数据集使用 aiterator() + 分块处理
async def export_large_dataset(request):
    data = []
    async for user in User.objects.all().aiterator(chunk_size=500):
        data.append({"id": user.id, "name": user.username})
    return JsonResponse(data, safe=False)

# ✅ 使用 values() 减少内存
async def lightweight_export(request):
    data = []
    async for row in User.objects.values("id", "username"):
        data.append(row)
    return JsonResponse(data, safe=False)
```

---

## 中间件与设置

### 生产安全配置清单

```python
# settings.py — 生产环境必须的安全设置

# ❌ 开发默认值不应出现在生产环境
DEBUG = True
SECRET_KEY = "django-insecure-..."
ALLOWED_HOSTS = ["*"]
SECURE_SSL_REDIRECT = False

# ✅ 生产环境安全配置

# --- 基础安全 ---
DEBUG = False
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # 从环境变量读取
ALLOWED_HOSTS = ["example.com", "www.example.com"]

# --- HTTPS ---
SECURE_SSL_REDIRECT = True          # HTTP 重定向到 HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# --- 安全头 ---
SECURE_HSTS_SECONDS = 31536000      # 1 year HSTS
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True   # X-Content-Type-Options: nosniff
X_FRAME_OPTIONS = "DENY"             # 防止 clickjacking
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# --- 密码验证 ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
]

# --- Session ---
SESSION_COOKIE_AGE = 3600 * 8  # 8 hours
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
```

### 数据库连接安全

```python
# settings.py

# ❌ 明文密码在代码中
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "mydb",
        "USER": "admin",
        "PASSWORD": "hunter2",  # 不要硬编码密码
        "HOST": "localhost",
        "PORT": "5432",
    }
}

# ✅ 从环境变量读取
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "mydb"),
        "USER": os.environ.get("DB_USER", "mydb_user"),
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "OPTIONS": {
            "sslmode": "require",  # 强制 SSL 连接
        },
        "CONN_MAX_AGE": 60,  # 持久连接
    }
}
```

### CORS 配置

```python
# settings.py (using django-cors-headers)

# ❌ 允许所有来源
CORS_ALLOW_ALL_ORIGINS = True

# ✅ 限制允许的来源
CORS_ALLOWED_ORIGINS = [
    "https://example.com",
    "https://app.example.com",
]

# ✅ 生产环境 CORS 设置
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ORIGINS", "").split(",")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = [
    "authorization",
    "content-type",
    "x-csrftoken",
]
```

### 日志配置

```python
# settings.py

# ❌ 默认日志配置（或不配置）
LOGGING = {}

# ✅ 生产环境日志配置
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/var/log/django/app.log",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["file"],
            "level": "INFO",
            "propagate": False,
        },
        "myapp": {
            "handlers": ["file"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}
```

---

## Review Checklist

### 安全审查

- [ ] 没有使用 `mark_safe` 渲染未转义的用户输入
- [ ] CSRF 中间件已启用，没有 `@csrf_exempt`
- [ ] Session 和 CSRF cookie 设置 `Secure`, `HttpOnly`, `SameSite`
- [ ] SQL 查询使用参数化（ORM 或参数化 `raw()`），无字符串拼接
- [ ] 文件上传有类型和大小限制
- [ ] `SECRET_KEY` 从环境变量读取，不在代码仓库中
- [ ] `DEBUG = False` 在生产环境

### HTTPS 与安全头

- [ ] `SECURE_SSL_REDIRECT = True`
- [ ] `SECURE_HSTS_SECONDS` 已设置（≥ 31536000）
- [ ] `SECURE_CONTENT_TYPE_NOSNIFF = True`
- [ ] `X_FRAME_OPTIONS` 设置为 `DENY` 或 `SAMEORIGIN`
- [ ] `ALLOWED_HOSTS` 不包含 `"*"`
- [ ] 数据库连接使用 SSL

### N+1 查询

- [ ] ForeignKey 关系使用 `select_related`
- [ ] M2M / 反向关系使用 `prefetch_related`
- [ ] 没有在循环中访问关联对象
- [ ] 使用 `count()` 代替 `len(queryset)` 做计数
- [ ] 使用 `exists()` 代替 `if queryset` 做存在性检查
- [ ] 大数据集使用 `only()` / `defer()` 或 `values()` 减少查询字段
- [ ] 切片后的 QuerySet 不重复迭代

### Serializer

- [ ] 不使用 `fields = "__all__"` 在敏感模型上
- [ ] 密码字段标记 `write_only=True`
- [ ] 有字段级和对象级验证
- [ ] 嵌套写入实现了 `create()` / `update()` 或使用 `read_only=True`
- [ ] 计算字段和自动字段在 `read_only_fields` 中
- [ ] Serializer 不包含不应被修改的字段

### ViewSet

- [ ] 只读场景使用 `ReadOnlyModelViewSet`
- [ ] `get_queryset()` 限定当前用户数据范围
- [ ] 设置了 `permission_classes`
- [ ] 创建时用 `perform_create()` 自动设置 owner/author
- [ ] 配置了分页（全局或 ViewSet 级别）
- [ ] 配置了节流（throttling）

### 异步视图

- [ ] async 视图中不直接调用同步 ORM（用 `aget`/`afilter`/`sync_to_async`）
- [ ] 所有异步调用都有 `await`
- [ ] `transaction.atomic()` 用 `sync_to_async` 包装
- [ ] 中间件标记 `async_capable = True` 以避免降级
- [ ] 大型 QuerySet 使用 `async for` + `aiterator()`

### 生产配置

- [ ] `CORS_ALLOWED_ORIGINS` 不使用 `CORS_ALLOW_ALL_ORIGINS = True`
- [ ] 密码验证器已配置（最小长度、常见密码检查）
- [ ] Session 过期时间合理（`SESSION_COOKIE_AGE`）
- [ ] 日志配置使用 RotatingFileHandler，不在生产环境输出到 stdout
- [ ] 数据库连接使用 `CONN_MAX_AGE` 持久连接
