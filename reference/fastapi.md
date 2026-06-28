# FastAPI Code Review Guide

> FastAPI code review guide covering dependency injection (`Depends`), Pydantic v2 validation boundaries, async correctness, database session lifecycle and N+1, security, and a test-driven verification workflow that turns the reviewer's in-process test client into a tool for *proving* bugs rather than guessing at them.

## Table of Contents

- [Dependency Injection (`Depends`)](#dependency-injection-depends)
- [Pydantic v2 Models & Validation](#pydantic-v2-models--validation)
- [Async Correctness](#async-correctness)
- [Database Sessions & N+1](#database-sessions--n1)
- [Security](#security)
- [Test-Driven Verification](#test-driven-verification)
- [Review Checklist](#review-checklist)
- [References](#references)

---

## Dependency Injection (`Depends`)

FastAPI's `Depends` is the seam that keeps routes thin and testable. Most review problems here come from doing real work in the route function instead of behind a dependency.

### Business logic belongs behind a dependency or service, not in the route

```python
# ❌ Bad — DB access, auth, and business rules all inline in the route
@app.get("/orders/{order_id}")
async def get_order(order_id: int):
    conn = await asyncpg.connect(DATABASE_URL)  # connection created per request
    row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
    await conn.close()
    if row is None:
        raise HTTPException(404)
    return dict(row)

# ✅ Good — the route declares what it needs; the session is injected and pooled
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

@app.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, session: AsyncSession = Depends(get_session)):
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
```

The injected version is also the version you can override in tests (see [Test-Driven Verification](#test-driven-verification)).

### `yield` dependencies must clean up, and cleanup runs even on error

```python
# ❌ Bad — no cleanup; the session leaks if the route raises
async def get_session() -> AsyncSession:
    return SessionLocal()

# ✅ Good — the context manager closes the session on success AND on exception
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

Review point: confirm any `yield` dependency holding a resource (DB session, file handle, lock) releases it through a context manager or `try/finally`, so an exception in the route does not leak it.

### Don't re-create singletons per request

```python
# ❌ Bad — a new HTTP client (and connection pool) per request
@app.get("/proxy")
async def proxy(client: httpx.AsyncClient = Depends(lambda: httpx.AsyncClient())):
    ...

# ✅ Good — one client for the app lifetime, injected by reference
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient()
    yield
    await app.state.http.aclose()

def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http
```

### Prefer the `Annotated` form and async dependencies

Since FastAPI 0.95 the idiomatic way to declare a dependency is `Annotated[T, Depends(...)]`, not the default-value form. It is reusable across routes and plays well with type checkers. Also prefer `async def` dependencies: a sync (`def`) dependency runs in the threadpool, which is wasted overhead for a small non-I/O check.

```python
# ⚠️ Older form — still works, but not the current idiom
@app.get("/items")
async def list_items(session: AsyncSession = Depends(get_session)): ...

# ✅ Good — Annotated form; define once, reuse everywhere
SessionDep = Annotated[AsyncSession, Depends(get_session)]

@app.get("/items")
async def list_items(session: SessionDep): ...
```

### Use dependencies to validate existence and permissions — they're cached per request

A dependency is the natural place to answer "does this resource exist and may this caller touch it?" Pydantic validates *shape*; a dependency validates against the database. FastAPI caches each dependency's result within a single request, so chaining small dependencies costs nothing extra and removes duplicated lookups.

```python
# ✅ Good — small dependencies chain; valid_post is resolved once per request
async def valid_post(post_id: int, session: SessionDep) -> Post:
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

async def owned_post(post: Annotated[Post, Depends(valid_post)], user: CurrentUser) -> Post:
    if post.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return post

@app.delete("/posts/{post_id}", status_code=204)
async def delete_post(post: Annotated[Post, Depends(owned_post)], session: SessionDep):
    await session.delete(post)        # existence + ownership already enforced
    await session.commit()
```

This is also the cleanest place to fix the auth-vs-authorization bug from the [Security](#security) section: the ownership check moves into a reusable `owned_post` dependency.

---

## Pydantic v2 Models & Validation

### Separate input and output models; never echo the ORM object directly

```python
# ❌ Bad — response_model is the DB model, so hashed_password leaks to the client
@app.post("/users", response_model=UserTable)
async def create_user(user: UserTable):  # also accepts client-set id, is_admin...
    ...

# ✅ Good — distinct schemas draw the trust boundary
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    model_config = ConfigDict(from_attributes=True)  # read from ORM safely

@app.post("/users", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    ...
```

`response_model` is a filter, not just documentation — fields absent from the output model are stripped from the response. Reusing the DB model as the response is the most common way sensitive fields leak.

### Use distinct Create and Update schemas

```python
# ❌ Bad — one schema for create and update means every field is required on PATCH
class ItemSchema(BaseModel):
    name: str
    price: float

# ✅ Good — update is a partial; create requires the full payload
class ItemCreate(BaseModel):
    name: str
    price: float = Field(gt=0)

class ItemUpdate(BaseModel):
    name: str | None = None
    price: float | None = Field(default=None, gt=0)
```

### Validate at the boundary, not after the DB write

```python
# ❌ Bad — negative quantity reaches the database before anything checks it
@app.post("/cart")
async def add_to_cart(item_id: int, quantity: int):
    await save(item_id, quantity)  # quantity = -5 silently accepted

# ✅ Good — the type system rejects it before the handler body runs
class CartLine(BaseModel):
    item_id: int
    quantity: int = Field(gt=0)

@app.post("/cart")
async def add_to_cart(line: CartLine):
    await save(line.item_id, line.quantity)
```

---

## Async Correctness

This is the axis on which FastAPI differs most from Django and Flask, and the one most worth a reviewer's attention. FastAPI's throughput comes from a single event loop interleaving many concurrent requests. That model only holds if the loop is **never blocked**: one synchronous call on the loop stalls *every* in-flight request, not just its own. Get this wrong across the codebase and FastAPI does not just lose its edge — it performs *worse* than a sync framework like Flask, because Flask's worker-per-request model has no shared loop to choke. The reviewer's job is to keep work on the loop genuinely non-blocking and to treat every escape hatch as a cost, not a fix.

### Never call blocking code inside an `async def` route

```python
# ❌ Bad — blocking I/O on the loop freezes ALL concurrent requests, not just this one
@app.get("/report")
async def report():
    data = requests.get("https://slow-api.example.com").json()  # blocking socket
    time.sleep(2)                                                # blocks the loop
    return data

# ✅ Good — await a native-async client; the loop serves other requests meanwhile
@app.get("/report")
async def report(client: httpx.AsyncClient = Depends(get_http)):
    resp = await client.get("https://slow-api.example.com")
    return resp.json()
```

### Prefer native-async SDKs over sync libraries

The right fix for blocking I/O is almost always a library that speaks `async` natively — not wrapping a sync one. Reach for the async client first; the threadpool is the last resort, not the default.

| Sync (blocks the loop) | Native-async replacement |
|------------------------|--------------------------|
| `requests`             | `httpx.AsyncClient`, `aiohttp` |
| `psycopg2` (sync)      | `asyncpg`, SQLAlchemy async engine |
| `redis-py` (sync)      | `redis.asyncio` |
| `pymongo`              | `motor` |
| `boto3`                | `aioboto3` |

If you find `asyncio.run(...)`, a new event loop, or a manually started thread *inside* a route, that is a red flag — it's an attempt to bolt sync code onto the loop. `asyncio.run()` inside a running loop raises `RuntimeError` outright; the rest quietly burns the performance you adopted FastAPI for.

```python
# ❌ Bad — spinning up a loop/thread to call an async SDK from a sync context
@app.get("/users/{uid}")
def get_user(uid: int):
    return asyncio.run(repo.fetch(uid))  # RuntimeError under the running loop

# ✅ Good — let the route be async and await the native client directly
@app.get("/users/{uid}")
async def get_user(uid: int):
    return await repo.fetch(uid)
```

### The threadpool is a bounded escape hatch, not a default

A plain `def` route — and `run_in_threadpool(...)` — does not run on the loop; FastAPI runs it in a **bounded** worker threadpool (AnyIO's default cap is 40 threads). For an occasional, genuinely-unavoidable blocking call this is the correct tool:

```python
from fastapi.concurrency import run_in_threadpool

@app.get("/legacy")
async def legacy():
    return await run_in_threadpool(blocking_library_call)  # only if no async SDK exists
```

But it does not scale the way the loop does. Route every hot path through the threadpool and, under load, all workers block at once; further requests queue behind the cap and throughput collapses. Spawning your own threads or processes to "add concurrency" makes it worse: once live threads exceed the machine's core count, context-switch and GIL contention degrade performance sharply rather than improving it. The escape hatch is for the rare blocking dependency you cannot replace — not a substitute for choosing async SDKs.

Review heuristic: a `def` route is acceptable for a low-traffic endpoint with no async equivalent. A high-traffic endpoint doing blocking work in a `def` route (or via `run_in_threadpool`) is a scaling bug — flag it and ask for an async SDK.

### CPU-bound work belongs in a worker process, not the loop or the threadpool

Neither the event loop nor the threadpool helps CPU-bound work: under the GIL only one thread runs Python bytecode at a time, so a heavy computation blocks just as badly from a threadpool as from the loop. Offload it to a separate process (Celery, Arq, RQ, or `multiprocessing`).

```python
# ❌ Bad — a CPU-heavy job pins a worker; throughput drops for everyone
@app.post("/render")
async def render(doc: Doc):
    return heavy_pdf_render(doc)            # seconds of pure CPU on the loop

# ✅ Good — enqueue to a worker process; return a job handle
@app.post("/render", status_code=202)
async def render(doc: Doc):
    job = await queue.enqueue(heavy_pdf_render, doc)
    return {"job_id": job.id}
```

### Don't fire-and-forget unawaited coroutines

```python
# ❌ Bad — coroutine never awaited; the email is never sent (and no error surfaces)
@app.post("/signup")
async def signup(user: UserCreate):
    send_welcome_email(user.email)  # returns a coroutine, silently dropped

# ✅ Good — defer post-response work with BackgroundTasks
@app.post("/signup")
async def signup(user: UserCreate, tasks: BackgroundTasks):
    tasks.add_task(send_welcome_email, user.email)
```

`BackgroundTasks` runs in-process and offers no retries or persistence — use it only for short, fire-and-forget work (send an email, log an event). Anything long-running or retry-critical (data processing, payments) belongs in a real task queue (Celery/Arq/RQ).

---

## Database Sessions & N+1

> 📖 For cross-language N+1 patterns and solutions, see [N+1 Queries Guide](cross-cutting/n-plus-one-queries.md)

### One session per request, injected — not a global

```python
# ❌ Bad — a module-level session is shared across concurrent requests (not safe)
session = SessionLocal()

# ✅ Good — request-scoped session via dependency (see get_session above)
@app.get("/items")
async def list_items(session: AsyncSession = Depends(get_session)):
    ...
```

### Eager-load relationships to avoid N+1

```python
# ❌ Bad — one query for orders, then one query per order for its customer
orders = (await session.execute(select(Order))).scalars().all()
return [{"id": o.id, "customer": o.customer.name} for o in orders]  # N+1

# ✅ Good — a single query with the relationship eager-loaded
stmt = select(Order).options(selectinload(Order.customer))
orders = (await session.execute(stmt)).scalars().all()
return [{"id": o.id, "customer": o.customer.name} for o in orders]
```

With async SQLAlchemy, lazy attribute access outside the session often raises instead of silently querying — but the design issue is the same. Look for relationship access inside a loop without an `options(...)` eager load.

### Paginate list endpoints

```python
# ❌ Bad — returns every row; degrades as the table grows
@app.get("/users")
async def list_users(session: AsyncSession = Depends(get_session)):
    return (await session.execute(select(User))).scalars().all()

# ✅ Good — bounded page with a sane cap
@app.get("/users", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(User).limit(limit).offset(offset)
    return (await session.execute(stmt)).scalars().all()
```

### Aggregate and join in SQL, not in Python

If a handler pulls rows into memory and then loops to group, count, or join them, the database is being used as dumb storage. Push the work down — the database does set operations far faster, and you transfer less data.

```python
# ❌ Bad — fetch every order, then tally per customer in Python
orders = (await session.execute(select(Order))).scalars().all()
totals: dict[int, float] = {}
for o in orders:
    totals[o.customer_id] = totals.get(o.customer_id, 0) + o.amount

# ✅ Good — let the database group and sum
stmt = select(Order.customer_id, func.sum(Order.amount)).group_by(Order.customer_id)
totals = dict((await session.execute(stmt)).all())
```

---

## Security

### A declared auth dependency is not an enforced authorization check

This is the highest-value thing to look for. `Depends(get_current_user)` proves *who* the caller is — it does **not** prove they may touch *this* resource.

```python
# ❌ Bad — any authenticated user can delete any other user's document
@app.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await session.get(Document, doc_id)
    await session.delete(doc)            # never checks doc.owner_id == user.id
    await session.commit()

# ✅ Good — ownership is verified before the mutation
@app.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Not found")
    if doc.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    await session.delete(doc)
    await session.commit()
```

The [Test-Driven Verification](#test-driven-verification) section reproduces exactly this bug with a failing test.

### Parameterize SQL; never f-string user input

> **跨语言 SQL 注入防护详见 [SQL Injection Prevention Guide](cross-cutting/sql-injection-prevention.md)**，含 Python/Java/Go/Node.js/PHP/C# 示例及 ORM 不安全用法。

### Don't widen CORS to credentials + wildcard

```python
# ❌ Bad — wildcard origin together with credentials is rejected by browsers and unsafe
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)

# ✅ Good — enumerate trusted origins when credentials are allowed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],
    allow_credentials=True,
)
```

Also check: secrets read from config/env (not hard-coded), `HTTPException` details that don't leak internals (stack traces, SQL), and rate limiting on auth endpoints.

---

## Test-Driven Verification

> Inspired by the test-driven development discipline: *if you didn't watch the test fail, you don't know it tests the right thing.* This matters even more for a coding agent than for a human reviewer. An agent's reading and reasoning are fallible — it can misread control flow, hallucinate a guarantee that isn't there, or rationalize a comfortable conclusion — so a prose verdict like "this looks safe" carries little weight on its own. An executable test is the one piece of **objective ground truth** the agent fully controls: it either passes or it doesn't, regardless of how confident the reasoning felt. That is what makes tests the agent's anchor of confidence. Reviewing the same way the discipline writes code — reproduce, don't assert — turns a hunch into proof.

A natural-language review comment ("this might let users delete each other's data") is exactly that kind of fallible hypothesis. FastAPI makes the ground truth cheap to obtain: an in-process client (`httpx.AsyncClient` over `ASGITransport`) runs the whole app, and `app.dependency_overrides` swaps out auth and the database without patching internals. So instead of trusting its own read of the code, the agent settles the question by reproduction.

### Reproduce a suspected bug with a failing test (Verify RED)

Suppose the reviewer suspects the `DELETE /documents/{doc_id}` route above never checks ownership. Write the test that asserts the *secure* behavior, then run it and **watch it fail** — the failure is the proof.

```python
# test_document_authorization.py
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import Header
from app.main import app
from app.deps import get_current_user, get_session

# Two users; the override picks one based on a test header.
USERS = {"alice": User(id=1, email="alice@example.com"),
         "bob":   User(id=2, email="bob@example.com")}

def fake_current_user(x_test_user: str = Header(default="alice")) -> User:
    return USERS[x_test_user]

@pytest.mark.asyncio
async def test_user_cannot_delete_another_users_document(session):  # async fixture
    # Arrange: a document owned by Alice (id=1)
    session.add(Document(id=10, owner_id=1, title="Alice's doc"))
    await session.commit()

    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_session] = lambda: session

    # Act: Bob tries to delete Alice's document
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/documents/10", headers={"X-Test-User": "bob"})

    # Assert the SECURE behavior we expect
    assert resp.status_code == 403

    app.dependency_overrides.clear()
```

Run it against the unfixed code and confirm the failure is the bug, not a typo:

```bash
$ pytest test_document_authorization.py
FAILED  assert 204 == 403
#       ^ the endpoint deleted Alice's document for Bob — vulnerability confirmed
```

A failure of `204 == 403` (not an import error, not a 404) is what makes the finding credible: the route returned success for an action that should have been forbidden. Now the fix from the [Security](#security) section turns it green:

```bash
$ pytest test_document_authorization.py
PASSED
```

Attach this test to the review. It documents the vulnerability, proves the fix, and guards against regression — far stronger than "consider checking ownership here."

### Prefer `dependency_overrides` over `patch`/`mock`

FastAPI's DI is the seam the TDD discipline asks for: when something is hard to test without mocking everything, that usually signals coupling — and `Depends` already gives you the injection point, so you rarely need `unittest.mock.patch`.

```python
# ❌ Bad — patching internals: brittle, couples the test to import paths
@patch("app.routes.orders.asyncpg.connect")
def test_get_order(mock_connect): ...

# ✅ Good — override the dependency with a real in-memory fake
app.dependency_overrides[get_session] = lambda: in_memory_session
app.dependency_overrides[get_current_user] = lambda: test_user
```

Always reset overrides between tests (`app.dependency_overrides.clear()` in a fixture teardown) so state doesn't leak across tests.

The reproduction above uses `httpx.AsyncClient` over `ASGITransport` with `@pytest.mark.asyncio` — the community convention for an async app, so the suite shares the app's event loop and you avoid loop-mismatch errors later. The synchronous `TestClient` is simpler and fine for a fully sync app, but standardizing on the async client from the start saves a painful migration once any route or fixture becomes async.

### Critique the PR's own tests, not just its source

A PR that ships tests is not automatically safe. Apply these checks to the *tests* in the diff:

```python
# ❌ Bad — happy-path only. Proves the route works when everything is correct,
#          says nothing about the validation and authorization paths.
def test_create_item():
    resp = client.post("/items", json={"name": "x", "price": 5})
    assert resp.status_code == 201

# ✅ Good — the boundary and failure paths are where bugs live
def test_create_item_rejects_negative_price():
    resp = client.post("/items", json={"name": "x", "price": -5})
    assert resp.status_code == 422

def test_create_item_requires_authentication():
    resp = client_without_auth.post("/items", json={"name": "x", "price": 5})
    assert resp.status_code == 401
```

Review questions for the test suite:

- **Does it test behavior, or the mock?** An assertion that only confirms a mock was called proves the test's own setup, not the endpoint.
- **Are the failure paths covered?** 401/403/404/422 — not just 200/201. Bugs cluster at the boundaries.
- **Is the mock complete?** A partial mock of an external API response that omits fields the handler reads passes in the test and fails in production.
- **Were the tests written after the fact?** Tests added alongside an implementation and passing on the first run never demonstrated that they can fail — and so prove little. A test that reproduces the bug (fails first, then passes) is worth more than one that was green from birth.

---

## Review Checklist

### Dependency Injection

- [ ] Routes stay thin — DB access and business rules live behind `Depends`/services
- [ ] `yield` dependencies release resources via context manager or `try/finally`
- [ ] Singletons (HTTP clients, pools) created once in `lifespan`, not per request
- [ ] `Annotated[T, Depends(...)]` form used; dependencies are `async def` unless they do blocking I/O
- [ ] Existence/permission checks live in (cached) dependencies, not copy-pasted into routes
- [ ] Dependencies are overridable in tests (no resources created inline in the route)

### Validation

- [ ] Input and output use distinct Pydantic models; ORM objects are not the `response_model`
- [ ] `response_model` set so sensitive fields can't leak
- [ ] Separate Create vs Update schemas (update is partial)
- [ ] Constraints (`gt`, `le`, `EmailStr`, ...) enforced at the boundary, before the DB write

### Async

- [ ] No blocking calls (`requests`, `time.sleep`, blocking DB drivers) inside `async def`
- [ ] Native-async SDKs preferred (`httpx`, `asyncpg`, `redis.asyncio`, ...) over sync ones
- [ ] No `asyncio.run`/manual event loops/manual threads inside routes
- [ ] `run_in_threadpool`/`def` routes used only as a last resort, not on hot paths
- [ ] CPU-bound work offloaded to a worker process (Celery/Arq/RQ), not the loop or threadpool
- [ ] No unawaited coroutines; `BackgroundTasks` only for short fire-and-forget work

### Database

- [ ] One request-scoped session via dependency; no module-level shared session
- [ ] Relationships eager-loaded (`selectinload`/`joinedload`) where accessed in a loop
- [ ] Joins/aggregations done in SQL, not by looping in Python
- [ ] List endpoints are paginated with a capped `limit`

### Security

- [ ] Authentication dependency is backed by an explicit **authorization** check (ownership/role)
- [ ] All SQL parameterized; no f-string interpolation of user input
- [ ] CORS does not combine `allow_origins=["*"]` with `allow_credentials=True`
- [ ] Secrets come from config/env; error responses don't leak internals

### Tests

- [ ] Suspected bugs reproduced with a failing test (`TestClient`/`AsyncClient`) before being claimed
- [ ] `dependency_overrides` used instead of patching internals; overrides reset between tests
- [ ] Failure paths covered (401/403/404/422), not just the happy path
- [ ] Mocks of external responses are complete, not partial
- [ ] New tests demonstrate they can fail (reproduce-then-fix), not green from birth

---

## References

- [FastAPI official documentation](https://fastapi.tiangolo.com/) — async, dependencies, testing
- [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices) — production conventions (async routes, dependency caching, project structure)
