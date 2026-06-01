# Kotlin / Android Code Review Guide

> Kotlin/Android 代码审查指南，覆盖协程作用域与取消、Flow 陷阱、Compose 重组、空安全、内存泄漏、架构分层与密封类状态建模等核心主题。

## 目录

- [协程：作用域与取消](#协程作用域与取消)
- [Flow 陷阱](#flow-陷阱)
- [Jetpack Compose 重组](#jetpack-compose-重组)
- [空安全模式](#空安全模式)
- [内存泄漏](#内存泄漏)
- [架构：ViewModel 与 Repository](#架构viewmodel-与-repository)
- [密封类与状态管理](#密封类与状态管理)
- [Review Checklist](#review-checklist)

---

## 协程：作用域与取消

### 避免 GlobalScope

```kotlin
// ❌ GlobalScope 生命周期不受控，Activity/Fragment 销毁后协程仍在运行
GlobalScope.launch {
    val data = api.fetchData()
    binding.textView.text = data.title // Crash: view destroyed
}

// ✅ 使用 viewModelScope，ViewModel 清除时自动取消
class MyViewModel(private val repo: Repository) : ViewModel() {
    fun loadData() {
        viewModelScope.launch {
            val data = repo.fetchData()
            _uiState.value = UiState.Success(data)
        }
    }
}

// ✅ 在 Activity/Fragment 中使用 lifecycleScope
class MyActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        lifecycleScope.launch {
            val data = repo.fetchData()
            binding.textView.text = data.title
        }
    }
}
```

### CancellationException 不能吞掉

```kotlin
// ❌ 捕获所有异常导致取消信号丢失
viewModelScope.launch {
    try {
        repo.fetchData()
    } catch (e: Exception) {
        // CancellationException 被吞掉，协程无法取消
        showError(e)
    }
}

// ✅ 重新抛出 CancellationException
viewModelScope.launch {
    try {
        repo.fetchData()
    } catch (e: CancellationException) {
        throw e // Must rethrow
    } catch (e: Exception) {
        showError(e)
    }
}

// ✅ 或使用 catch 配合 ensureActive
viewModelScope.launch {
    try {
        repo.fetchData()
    } catch (e: Exception) {
        ensureActive() // Rethrows if cancelled
        showError(e)
    }
}
```

### CPU-bound 任务需要检查取消

```kotlin
// ❌ CPU 密集计算不响应取消，即使协程已取消也会跑完
viewModelScope.launch(Dispatchers.Default) {
    for (item in largeList) {
        heavyComputation(item)
    }
}

// ✅ 定期检查 isActive 或调用 ensureActive
viewModelScope.launch(Dispatchers.Default) {
    for (item in largeList) {
        ensureActive() // Throws CancellationException if cancelled
        heavyComputation(item)
    }
}

// ✅ 或使用 yield 让出执行权
viewModelScope.launch(Dispatchers.Default) {
    for (item in largeList) {
        yield() // Checks cancellation + yields to other coroutines
        heavyComputation(item)
    }
}
```

### 阻塞操作使用 runInterruptible

```kotlin
// ❌ 在协程中直接调用阻塞 I/O，阻塞线程池线程
viewModelScope.launch(Dispatchers.IO) {
    val result = blockingLibraryCall() // Blocks IO thread
}

// ✅ 使用 runInterruptible 包装阻塞调用，支持取消中断
viewModelScope.launch(Dispatchers.IO) {
    val result = runInterruptible {
        blockingLibraryCall() // Interrupted on cancellation
    }
}
```

### 正确选择调度器

```kotlin
// ❌ CPU 密集任务用了 IO 调度器（线程池过大，浪费资源）
viewModelScope.launch(Dispatchers.IO) {
    val bitmap = decodeImage(byteArray) // CPU-bound on IO pool
}

// ✅ CPU 密集用 Default，I/O 操作用 IO
viewModelScope.launch(Dispatchers.Default) {
    val bitmap = decodeImage(byteArray) // CPU-bound on Default pool
}

// ❌ IO 操作用了 Default 调度器（线程池太小，容易饥饿）
viewModelScope.launch(Dispatchers.Default) {
    val response = okHttpClient.newCall(request).execute() // I/O on Default pool
}

// ✅ I/O 操作用 IO 调度器
viewModelScope.launch(Dispatchers.IO) {
    val response = okHttpClient.newCall(request).execute()
}
```

### launch vs async

```kotlin
// ❌ async 只用于"发个火"，不需要返回值
viewModelScope.launch {
    async { analytics.trackEvent("click") } // Overkill
}

// ✅ 不需要返回值用 launch
viewModelScope.launch {
    launch { analytics.trackEvent("click") }
}

// ✅ 需要返回值且可能并行时用 async
viewModelScope.launch {
    val deferredA = async { api.fetchA() }
    val deferredB = async { api.fetchB() }
    val result = combine(deferredA.await(), deferredB.await())
}
```

### 不要用 Job() 破坏父子关系

```kotlin
// ❌ Job() 切断了父协程的取消传播
viewModelScope.launch {
    launch(Job()) { // Detached from parent scope!
        importantWork() // Will NOT be cancelled when viewModelScope cancels
    }
}

// ✅ 保持默认的父子关系
viewModelScope.launch {
    launch { // Child of viewModelScope
        importantWork() // Cancelled when viewModelScope cancels
    }
}

// ✅ 如果确实需要独立生命周期，显式管理并说明原因
class MyManager(private val scope: CoroutineScope) {
    // Independent lifecycle managed by MyManager.shutdown()
    private val managerJob = Job(scope.coroutineContext[Job])
    private val managerScope = scope + managerJob + Dispatchers.IO

    fun shutdown() {
        managerJob.cancel()
    }
}
```

### NonCancellable 的正确使用

```kotlin
// ❌ 整个协程都包在 withContext(NonCancellable) 中，无法取消
viewModelScope.launch {
    withContext(NonCancellable) { // Entire block is uncancellable!
        val data = repo.fetchData() // Cannot be cancelled
        db.saveData(data) // Cannot be cancelled
        analytics.track("saved")
    }
}

// ✅ NonCancellable 只用于清理操作
viewModelScope.launch {
    try {
        val data = repo.fetchData()
        db.saveData(data)
    } catch (e: CancellationException) {
        throw e
    } finally {
        withContext(NonCancellable) {
            db.cleanup() // Only cleanup is uncancellable
        }
    }
}
```

---

## Flow 陷阱

### 冷流与热流混淆

```kotlin
// ❌ 每次 collect 都重新执行 flow {} 块（冷流特性被误解）
val userFlow = flow {
    emit(api.fetchUser()) // Called once per collector!
}

// Two collectors = two network requests
lifecycleScope.launch { userFlow.collect { } }
lifecycleScope.launch { userFlow.collect { } }

// ✅ 共享数据用 StateFlow/SharedFlow（热流）
class MyViewModel(private val repo: Repository) : ViewModel() {
    private val _uiState = MutableStateFlow<UiState>(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            _uiState.value = UiState.Success(repo.fetchUser())
        }
    }
}
// Multiple collectors share the same StateFlow
```

### 不要在 flow {} 中切换上下文

```kotlin
// ❌ 在 flow builder 中使用 withContext，违反约束
val dataFlow = flow {
    withContext(Dispatchers.IO) { // IllegalStateException!
        emit(api.fetchData())
    }
}

// ✅ 使用 flowOn 操作符切换上游上下文
val dataFlow = flow {
    emit(api.fetchData()) // Runs on IO via flowOn
}.flowOn(Dispatchers.IO)

// ✅ 或使用 channelFlow / callbackFlow 需要切换时
val dataFlow = channelFlow {
    withContext(Dispatchers.IO) {
        send(api.fetchData()) // send() is safe in channelFlow
    }
}
```

### collect 需要生命周期感知

```kotlin
// ❌ 在 Activity/Fragment 中 collect 不感知生命周期
lifecycleScope.launch {
    viewModel.uiState.collect { state ->
        binding.textView.text = state.title // Crash if view destroyed
    }
}

// ✅ 在 Fragment 中使用 viewLifecycleOwner.lifecycleScope + repeatOnLifecycle
viewLifecycleOwner.lifecycleScope.launch {
    viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.uiState.collect { state ->
            binding.textView.text = state.title
        }
    }
}

// ✅ 在 Compose 中使用 collectAsStateWithLifecycle
@Composable
fun MyScreen(viewModel: MyViewModel) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    // ...
}
```

### 异常透明性：使用 catch 操作符

```kotlin
// ❌ 在 collect 中 try-catch 处理上游异常
viewModelScope.launch {
    try {
        dataFlow.collect { data ->
            processData(data)
        }
    } catch (e: Exception) {
        // This also catches exceptions from processData, not just upstream
        showError(e)
    }
}

// ✅ 使用 catch 操作符保持异常透明性
viewModelScope.launch {
    dataFlow
        .catch { e -> showError(e) } // Only catches upstream exceptions
        .collect { data ->
            processData(data) // Exceptions here propagate normally
        }
}
```

### StateFlow vs SharedFlow 选择

```kotlin
// ❌ 用 SharedFlow 模拟 StateFlow，丢失最新值语义
private val _state = MutableSharedFlow<UiState>()
val state: SharedFlow<UiState> = _state

// ✅ UI 状态用 StateFlow：总是有值、新订阅者立即获得最新值
class MyViewModel : ViewModel() {
    private val _uiState = MutableStateFlow(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()
}

// ✅ 事件（一次性通知）用 SharedFlow + replay(0)
class MyViewModel : ViewModel() {
    private val _navigationEvent = MutableSharedFlow<NavTarget>(extraBufferCapacity = 1)
    val navigationEvent: SharedFlow<NavTarget> = _navigationEvent.asSharedFlow()

    fun navigate(target: NavTarget) {
        _navigationEvent.tryEmit(target)
    }
}

// ✅ Channel 用于一次性事件（替代方案）
private val _navigationEvent = Channel<NavTarget>(Channel.BUFFERED)
val navigationEvent = _navigationEvent.receiveAsFlow()
```

---

## Jetpack Compose 重组

### 不稳定参数导致多余重组

```kotlin
// ❌ 使用不稳定的类作为参数，Compose 无法判断是否变化
data class UserProfile(
    val name: String,
    val friends: List<String>, // Unstable! List is not @Stable
)

@Composable
fun ProfileCard(profile: UserProfile) { // Recomposes even if profile didn't change
    Text(profile.name)
}

// ✅ 使用 @Immutable 标注或使用稳定的集合类型
@Immutable
data class UserProfile(
    val name: String,
    val friends: ImmutableList<String>, // kotlinx.collections.immutable
)

// ✅ 或将不稳定属性提取为单独的参数
@Composable
fun ProfileCard(
    name: String, // Stable: String is primitive
    friendCount: Int, // Stable: Int is primitive
) {
    Text(name)
    Text("$friendCount friends")
}
```

### Lambda 不稳定与记忆化

```kotlin
// ❌ 每次重组都创建新的 Lambda，导致子组件不必要的重组
@Composable
fun MyScreen(viewModel: MyViewModel) {
    LazyColumn {
        items(items, key = { it.id }) { item ->
            ItemRow(
                item = item,
                onClick = { viewModel.handleClick(item.id) } // New lambda each recomposition!
            )
        }
    }
}

// ✅ 使用 remember 包装 Lambda，或让 ViewModel 暴露稳定回调
@Composable
fun MyScreen(viewModel: MyViewModel) {
    LazyColumn {
        items(items, key = { it.id }) { item ->
            ItemRow(
                item = item,
                onClick = remember(item.id) { { viewModel.handleClick(item.id) } }
            )
        }
    }
}
```

### 使用 derivedStateOf 避免高频率重组

```kotlin
// ❌ 每次滚动都重组整个组件
@Composable
fun ScrollToTopButton(lazyListState: LazyListState) {
    val showButton = lazyListState.firstVisibleItemIndex > 0 // Recomposes on every scroll
    if (showButton) {
        Button(onClick = { /* scroll to top */ }) {
            Text("Top")
        }
    }
}

// ✅ 使用 derivedStateOf 只在结果变化时触发重组
@Composable
fun ScrollToTopButton(lazyListState: LazyListState) {
    val showButton by remember {
        derivedStateOf { lazyListState.firstVisibleItemIndex > 0 }
    }
    if (showButton) {
        Button(onClick = { /* scroll to top */ }) {
            Text("Top")
        }
    }
}
```

### 不要在 Composable 函数体中执行副作用

```kotlin
// ❌ 在 Composable 函数体中直接触发副作用，每次重组都会执行
@Composable
fun MyScreen(userId: String, viewModel: MyViewModel) {
    viewModel.loadUser(userId) // Called on every recomposition!
    val user by viewModel.user.collectAsStateWithLifecycle()
    Text(user?.name ?: "Loading...")
}

// ✅ 使用 LaunchedEffect 在 key 变化时执行副作用
@Composable
fun MyScreen(userId: String, viewModel: MyViewModel) {
    LaunchedEffect(userId) {
        viewModel.loadUser(userId) // Only when userId changes
    }
    val user by viewModel.user.collectAsStateWithLifecycle()
    Text(user?.name ?: "Loading...")
}

// ✅ 一次性初始化用 remember { ... }
@Composable
fun MyScreen(viewModel: MyViewModel) {
    val initialData = remember { viewModel.getInitialData() }
}
```

### 状态提升

```kotlin
// ❌ 状态和逻辑耦合在 Composable 内部，无法复用和测试
@Composable
fun ToggleButton() {
    var isChecked by remember { mutableStateOf(false) }
    Switch(
        checked = isChecked,
        onCheckedChange = { isChecked = it }
    )
}

// ✅ 状态提升：调用者控制状态
@Composable
fun ToggleButton(
    isChecked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    Switch(
        checked = isChecked,
        onCheckedChange = onCheckedChange,
        modifier = modifier,
    )
}

// ✅ 调用者持有状态
@Composable
fun ParentScreen() {
    var enabled by rememberSaveable { mutableStateOf(false) }
    ToggleButton(
        isChecked = enabled,
        onCheckedChange = { enabled = it },
    )
}
```

---

## 空安全模式

### 避免非空断言 !!

```kotlin
// ❌ 非空断言：如果为 null 直接 NPE
val user = getUser()!!
val name = user.name!!

// ✅ 安全调用 + 空合并
val name = getUser()?.name ?: "Unknown"

// ✅ requireNotNull 提供有意义的错误信息
val user = requireNotNull(getUser()) { "User must not be null at this point" }

// ✅ 提前返回
fun process(user: User?) {
    val nonNullUser = user ?: return
    nonNullUser.doSomething()
}
```

### lateinit vs nullable vs lazy

```kotlin
// ❌ lateinit 用于可能为 null 的值（语义不对）
lateinit var optionalConfig: Config // Might never be set

// ✅ lateinit 用于一定会在使用前初始化的值
class MyActivity : AppCompatActivity() {
    lateinit var binding: ActivityMainBinding // Set in onCreate

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
    }
}

// ✅ nullable + lateinit 取决于初始化时机
// lateinit: 生命周期保证在使用前初始化
// nullable: 不确定是否初始化，需要 null 检查
// lazy: 确定在首次访问时初始化

class MyViewModel(private val repo: Repository) : ViewModel() {
    // lazy: 首次访问时初始化，线程安全
    val expensiveObject by lazy { ExpensiveObject(repo) }

    // nullable: 可能不会初始化
    var cachedData: Data? = null
        private set
}
```

### Java 互操作：平台类型泄漏

```kotlin
// ❌ Java 返回平台类型（可能 null），Kotlin 当作非空使用
// Java:
// public User getUser() { return null; }
val name: String = javaService.getUser().name // NPE!

// ✅ 使用可空类型接收 Java 返回值
val user: User? = javaService.getUser()
val name = user?.name ?: "Unknown"

// ✅ 在 Kotlin 侧包装 Java API，提供安全的类型
class SafeUserService(private val delegate: JavaUserService) {
    fun getUser(): User? = delegate.getUser() // Explicitly nullable
}
```

---

## 内存泄漏

### 避免在长生命周期协程中捕获 Context/View

```kotlin
// ❌ 协程捕获了 Activity Context，Activity 销毁后无法回收
class MyActivity : AppCompatActivity() {
    fun loadData() {
        // Leaking Activity via coroutine
        GlobalScope.launch {
            val data = repo.fetchData()
            // 'this' (Activity) is captured
            binding.textView.text = data // Activity leaked!
        }
    }
}

// ✅ 使用 viewModelScope + 生命周期感知
class MyViewModel(private val repo: Repository) : ViewModel() {
    private val _uiState = MutableStateFlow<UiState>(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    fun loadData() {
        viewModelScope.launch {
            val data = repo.fetchData()
            _uiState.value = UiState.Success(data) // No Activity reference
        }
    }
}
```

### 注销监听器

```kotlin
// ❌ 注册监听器但从不注销
class MyFragment : Fragment() {
    private val sensorListener = object : SensorEventListener {
        override fun onSensorChanged(event: SensorEvent) { }
        override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) { }
    }

    override fun onResume() {
        super.onResume()
        sensorManager.registerListener(sensorListener, sensor, SensorManager.SENSOR_DELAY_UI)
        // Never unregistered!
    }
}

// ✅ 在 onPause/onDestroyView 中注销
override fun onResume() {
    super.onResume()
    sensorManager.registerListener(sensorListener, sensor, SensorManager.SENSOR_DELAY_UI)
}

override fun onPause() {
    super.onPause()
    sensorManager.unregisterListener(sensorListener)
}
```

### 取消自定义 CoroutineScope

```kotlin
// ❌ 创建 CoroutineScope 但从不取消
class MyManager(private val scope: CoroutineScope) {
    private val job = SupervisorJob()
    private val managerScope = scope + job + Dispatchers.IO

    fun start() {
        managerScope.launch {
            while (isActive) {
                pollServer()
                delay(5000)
            }
        }
    }
    // Never cancelled! job lives forever.
}

// ✅ 提供关闭方法并取消 Job
class MyManager(private val scope: CoroutineScope) {
    private val job = SupervisorJob()
    private val managerScope = scope + job + Dispatchers.IO

    fun start() {
        managerScope.launch {
            while (isActive) {
                pollServer()
                delay(5000)
            }
        }
    }

    fun shutdown() {
        job.cancel()
    }
}

// ✅ ViewModel 里直接用内置的 viewModelScope，不用自己管生命周期
class MyViewModel : ViewModel() {
    private val scope = viewModelScope + Dispatchers.IO
    // Automatically cancelled when ViewModel is cleared
}
```

---

## 架构：ViewModel 与 Repository

### ViewModel 不暴露可变状态

```kotlin
// ❌ 直接暴露 MutableStateFlow，外部可以随意修改
class MyViewModel : ViewModel() {
    val uiState = MutableStateFlow<UiState>(UiState.Loading) // Mutable!

    fun load() {
        viewModelScope.launch {
            uiState.value = UiState.Success(repo.fetchData())
        }
    }
}

// ✅ 暴露不可变接口，内部持有可变版本
class MyViewModel(private val repo: Repository) : ViewModel() {
    private val _uiState = MutableStateFlow<UiState>(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    fun load() {
        viewModelScope.launch {
            _uiState.value = UiState.Success(repo.fetchData())
        }
    }
}
```

### 业务逻辑下沉到 Repository

```kotlin
// ❌ ViewModel 中包含数据处理和业务规则逻辑
class UserViewModel(private val api: Api) : ViewModel() {
    private val _users = MutableStateFlow<List<User>>(emptyList())
    val users: StateFlow<List<User>> = _users.asStateFlow()

    fun loadUsers() {
        viewModelScope.launch {
            val raw = api.getUsers()
            val filtered = raw.filter { it.isActive }
            val sorted = filtered.sortedBy { it.name.lowercase() }
            val enriched = sorted.map { user ->
                user.copy(displayName = "${user.firstName} ${user.lastName}")
            }
            _users.value = enriched
        }
    }
}

// ✅ ViewModel 只做状态管理，逻辑下沉到 Repository
class UserRepository(private val api: Api) {
    suspend fun getActiveUsersSorted(): List<User> {
        return api.getUsers()
            .filter { it.isActive }
            .sortedBy { it.name.lowercase() }
            .map { it.copy(displayName = "${it.firstName} ${it.lastName}") }
    }
}

class UserViewModel(private val repo: UserRepository) : ViewModel() {
    private val _users = MutableStateFlow<List<User>>(emptyList())
    val users: StateFlow<List<User>> = _users.asStateFlow()

    fun loadUsers() {
        viewModelScope.launch {
            _users.value = repo.getActiveUsersSorted()
        }
    }
}
```

### 单一数据源（Offline-First）

```kotlin
// ❌ ViewModel 直接从网络获取，无缓存，离线不可用
class MyViewModel(private val api: Api) : ViewModel() {
    fun load() {
        viewModelScope.launch {
            _uiState.value = UiState.Success(api.fetchData())
        }
    }
}

// ✅ Repository 作为单一数据源，先展示本地缓存再更新网络数据
class MyRepository(
    private val api: Api,
    private val dao: DataDao,
) {
    val data: Flow<List<Data>> = dao.getAll()
        .map { entities -> entities.map { it.toDomain() } }

    suspend fun refresh() {
        val remote = api.fetchData()
        dao.replaceAll(remote.map { it.toEntity() })
    }
}

class MyViewModel(private val repo: MyRepository) : ViewModel() {
    val uiState = repo.data.map { UiState.Success(it) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), UiState.Loading)

    fun refresh() {
        viewModelScope.launch { repo.refresh() }
    }
}
```

### Use Case 用于复杂业务逻辑

```kotlin
// ❌ Repository 方法名变成动词短语，职责膨胀
class OrderRepository {
    suspend fun validateAndSubmitOrder(order: Order) { }
    suspend fun calculateOrderTotalWithDiscounts(order: Order): Money { }
    suspend fun checkInventoryAndReserve(items: List<Item>) { }
}

// ✅ 使用 Use Case 封装复杂业务逻辑，Repository 只做数据访问
class SubmitOrderUseCase(
    private val orderRepo: OrderRepository,
    private val inventoryRepo: InventoryRepository,
    private val paymentRepo: PaymentRepository,
) {
    suspend operator fun invoke(order: Order): Result<OrderConfirmation> {
        val validated = order.validate()
        inventoryRepo.reserve(validated.items)
        val total = CalculateOrderTotalUseCase().invoke(validated)
        return paymentRepo.charge(total).map { confirmation ->
            orderRepo.save(validated.copy(status = OrderStatus.CONFIRMED))
            confirmation
        }
    }
}

class OrderRepository {
    suspend fun save(order: Order) { }
    suspend fun getById(id: String): Order? { }
    fun observeOrders(): Flow<List<Order>> { }
}
```

---

## 密封类与状态管理

### UI 状态建模：让不可能的状态无法表达

```kotlin
// ❌ 用 nullable 组合表示状态，可能产生无效组合
data class UiState(
    val isLoading: Boolean = false,
    val data: List<Item>? = null,
    val error: String? = null,
)
// Invalid: isLoading=true AND error != null
// Invalid: data != null AND error != null

// ✅ 使用密封类建模，每种状态互斥
sealed interface UiState {
    data object Loading : UiState
    data class Success(val data: List<Item>) : UiState
    data class Error(val message: String, val cause: Throwable? = null) : UiState
}

class MyViewModel(private val repo: Repository) : ViewModel() {
    private val _uiState = MutableStateFlow<UiState>(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()
}

// ✅ Compose 中 exhaustive when
@Composable
fun MyScreen(viewModel: MyViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    when (state) {
        is UiState.Loading -> CircularProgressIndicator()
        is UiState.Success -> DataList((state as UiState.Success).data)
        is UiState.Error -> ErrorMessage((state as UiState.Error).message)
    }
}
```

### 导航事件建模

```kotlin
// ❌ 用枚举或字符串表示导航事件，无法携带参数
sealed class NavEvent {
    object ToDetail : NavEvent()
    object ToSettings : NavEvent()
}
// How to pass orderId to ToDetail?

// ✅ 密封类携带类型安全参数
sealed interface NavEvent {
    data class ToDetail(val orderId: String) : NavEvent
    data class ToSettings(val tab: SettingsTab) : NavEvent
    data class ToProfile(val userId: String, val mode: ProfileMode) : NavEvent
}

// ✅ 处理导航事件
navController.handleNavEvent { event ->
    when (event) {
        is NavEvent.ToDetail -> navController.navigate(DetailRoute(event.orderId))
        is NavEvent.ToSettings -> navController.navigate(SettingsRoute(event.tab))
        is NavEvent.ToProfile -> navController.navigate(ProfileRoute(event.userId, event.mode))
    }
}
```

### 网络结果包装

```kotlin
// ❌ 用 Result? 或 nullable 表示网络结果，丢失错误信息
suspend fun fetchUser(id: String): User? {
    return try {
        api.getUser(id)
    } catch (e: Exception) {
        null // What went wrong?
    }
}

// ✅ 使用密封类包装网络结果
sealed interface NetworkResult<out T> {
    data class Success<T>(val data: T) : NetworkResult<T>
    data class Error(val code: Int, val message: String) : NetworkResult<Nothing>
    data class Exception(val cause: Throwable) : NetworkResult<Nothing>
}

suspend fun fetchUser(id: String): NetworkResult<User> {
    return try {
        val response = api.getUser(id)
        if (response.isSuccessful) {
            NetworkResult.Success(response.body()!!)
        } else {
            NetworkResult.Error(response.code(), response.message())
        }
    } catch (e: Exception) {
        NetworkResult.Exception(e)
    }
}

// ✅ 在 ViewModel 中映射为 UI 状态
fun loadUser(id: String) {
    viewModelScope.launch {
        when (val result = repo.fetchUser(id)) {
            is NetworkResult.Success -> _uiState.value = UiState.Success(result.data)
            is NetworkResult.Error -> _uiState.value = UiState.Error("Server error: ${result.code}")
            is NetworkResult.Exception -> _uiState.value = UiState.Error(result.cause.message ?: "Unknown")
        }
    }
}
```

---

## Review Checklist

### 协程

- [ ] 不使用 `GlobalScope`，使用 `viewModelScope` / `lifecycleScope`
- [ ] `CancellationException` 被正确重新抛出，未被吞掉
- [ ] CPU 密集任务使用 `Dispatchers.Default`，I/O 操作使用 `Dispatchers.IO`
- [ ] 长时间运行的 CPU 任务定期调用 `ensureActive()` 或 `yield()`
- [ ] 阻塞调用使用 `runInterruptible` 包装
- [ ] 不使用 `Job()` 破坏父子协程关系
- [ ] `NonCancellable` 仅用于 `finally` 块中的清理操作
- [ ] 不需要返回值用 `launch`，需要并行结果用 `async`

### Flow

- [ ] 理解冷流（`flow {}`）与热流（`StateFlow`/`SharedFlow`）的区别
- [ ] 不在 `flow {}` builder 中使用 `withContext`，使用 `flowOn` 操作符
- [ ] `collect` 配合 `repeatOnLifecycle` 或 `collectAsStateWithLifecycle` 使用
- [ ] 异常处理使用 `.catch` 操作符而非 `try-catch` 包裹 `collect`
- [ ] UI 状态用 `StateFlow`，一次性事件用 `SharedFlow` 或 `Channel`

### Compose

- [ ] Composable 参数使用稳定类型，避免不必要重组
- [ ] Lambda 参数使用 `remember` 包装，避免每次重组创建新实例
- [ ] 派生状态使用 `derivedStateOf` 避免高频率重组
- [ ] 副作用使用 `LaunchedEffect` / `SideEffect`，不在函数体中直接调用
- [ ] 状态正确提升（state hoisting），Composable 无状态且可复用

### 空安全

- [ ] 不滥用非空断言 `!!`，使用安全调用 `?.` 或空合并 `?:`
- [ ] `lateinit` 仅用于生命周期保证初始化的属性
- [ ] Java 互操作返回值使用可空类型接收
- [ ] `lazy` 用于首次访问时初始化的昂贵对象

### 内存泄漏

- [ ] 协程不捕获 `Context` / `View` 等短生命周期对象
- [ ] 监听器在 `onPause` / `onDestroyView` 中正确注销
- [ ] 自定义 `CoroutineScope` 提供取消机制
- [ ] 单例不持有 `Activity` / `Fragment` 引用

### 架构

- [ ] ViewModel 不暴露 `MutableStateFlow` / `MutableLiveData`，使用不可变接口
- [ ] 业务逻辑下沉到 Repository / Use Case，ViewModel 只做状态管理
- [ ] 实现 offline-first：Repository 作为单一数据源
- [ ] 复杂业务逻辑封装为独立的 Use Case 类

### 密封类与状态

- [ ] UI 状态使用密封类建模，让不可能的状态无法表达
- [ ] 导航事件使用密封类携带类型安全参数
- [ ] 网络请求结果使用密封类包装，不丢失错误信息
- [ ] `when` 表达式覆盖所有分支（exhaustive check）
