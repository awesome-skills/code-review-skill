# NestJS Code Review Guide

> NestJS 代码审查指南，覆盖依赖注入与分层架构、模块组织、Guard/Interceptor/Pipe、DTO 验证、错误处理、循环依赖及测试模式等核心主题。

## 目录

- [依赖注入与分层架构](#依赖注入与分层架构)
- [模块组织](#模块组织)
- [Guard / Interceptor / Pipe](#guard--interceptor--pipe)
- [验证模式 (DTO)](#验证模式-dto)
- [错误处理](#错误处理)
- [循环依赖](#循环依赖)
- [测试模式](#测试模式)
- [Review Checklist](#review-checklist)

---

## 依赖注入与分层架构

### 三层架构：Controller → Service → Repository

```typescript
// ❌ ORM 直接注入 Controller，跳过 Service 层
@Controller('users')
export class UsersController {
  constructor(private readonly prisma: PrismaService) {}

  @Get()
  findAll() {
    return this.prisma.user.findMany();
  }
}

// ✅ Controller → Service → Repository
@Controller('users')
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  @Get()
  findAll() {
    return this.usersService.findAll();
  }
}

@Injectable()
export class UsersService {
  constructor(private readonly usersRepo: UsersRepository) {}

  findAll() {
    return this.usersRepo.findAll();
  }
}
```

### Repository 之间不应互相注入

```typescript
// ❌ Repository 导入另一个 Repository——编排逻辑属于 Service
@Injectable()
export class OrdersRepository {
  constructor(private readonly usersRepository: UsersRepository) {}
}

// ✅ 跨 Repository 编排在 Service 中完成
@Injectable()
export class OrdersService {
  constructor(
    private readonly ordersRepo: OrdersRepository,
    private readonly usersRepo: UsersRepository,
  ) {}
}
```

### God Service：依赖超过 8 个时拆分

```typescript
// ❌ 9 个依赖的巨型 Service
@Injectable()
export class OrdersService {
  constructor(
    private readonly ordersRepo: OrdersRepository,
    private readonly usersRepo: UsersRepository,
    private readonly productsRepo: ProductsRepository,
    private readonly paymentsService: PaymentsService,
    private readonly mailerService: MailerService,
    private readonly inventoryService: InventoryService,
    private readonly discountService: DiscountService,
    private readonly taxService: TaxService,
    private readonly auditService: AuditService,
  ) {}
}

// ✅ 拆分为 Use-Case Service（一个文件一个操作）
@Injectable()
export class CreateOrderService {
  constructor(
    private readonly ordersRepo: OrdersRepository,
    private readonly paymentsService: PaymentsService,
  ) {}

  async execute(dto: CreateOrderDto) { /* ... */ }
}
```

### Symbol Token 实现依赖反转

```typescript
// ❌ 直接依赖具体实现——测试时无法替换
@Injectable()
export class UsersService {
  constructor(private readonly repo: TypeOrmUserRepository) {}
}

// ✅ 接口 + Symbol Token——可替换为内存实现
export const USER_REPOSITORY = Symbol('USER_REPOSITORY');

export interface UserRepository {
  findAll(): Promise<User[]>;
  findById(id: string): Promise<User | null>;
}

// module:
{
  provide: USER_REPOSITORY,
  useClass: TypeOrmUserRepository,
}

// service:
@Injectable()
export class UsersService {
  constructor(@Inject(USER_REPOSITORY) private readonly repo: UserRepository) {}
}
```

---

## 模块组织

### 推荐四层结构

```
src/
  common/         ← 全局技术基础设施（Guards、Filters、Interceptors、Decorators）
  core/           ← 内部基础设施（Config、Database、Queue 配置）
  integrations/   ← 外部服务封装（Mailer、Storage、Stripe、SMS）
  modules/        ← 按领域组织的业务逻辑
    [feature]/
      dtos/
      repositories/
      services/
        internal/     ← 模块内共享 Service
        use-cases/    ← 一个文件 = 一个操作
      types/
      [feature].controller.ts
      [feature].module.ts
```

### Domain 必须框架无关

```typescript
// ❌ Domain Entity 依赖 NestJS——不可独立测试
import { Injectable } from '@nestjs/common';

@Injectable()
export class User {
  constructor(private readonly email: string) {}
}

// ✅ Domain 是纯类，无框架装饰器
export class User {
  private constructor(private readonly email: string) {}

  static create(email: string): User {
    return new User(email);
  }
}
```

### 关键规则

- `common/` 必须 **不涉及业务**——如果需要知道"订单"，它不属于这里
- `integrations/` 封装每个外部服务；换 SendGrid → AWS SES 只改一个目录
- 使用 **Use-Case Service**（一个文件一个操作）而非 15 个方法的巨型 `XxxService`

---

## Guard / Interceptor / Pipe

### 业务逻辑不应放在 Guard 中

```typescript
// ❌ Guard 中查询数据库 + 业务判断
@Injectable()
export class OrderOwnershipGuard implements CanActivate {
  constructor(private readonly prisma: PrismaService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest();
    const order = await this.prisma.order.findUnique({
      where: { id: req.params.id },
    });
    if (order.userId !== req.user.id) {
      return false; // 数据获取 + 业务规则判断都在 Guard 里
    }
    return true;
  }
}

// ✅ Guard 只做授权检查（角色/权限）
@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.getAllAndOverride<string[]>('roles', [
      context.getHandler(),
      context.getClass(),
    ]);
    if (!requiredRoles) return true;
    const { user } = context.switchToHttp().getRequest();
    return requiredRoles.some((role) => user.roles?.includes(role));
  }
}
```

### Interceptor 只用于横切关注点

```typescript
// ❌ Interceptor 中执行业务逻辑
@Injectable()
export class PricingInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler) {
    // 计算折扣——这不是横切关注点！
    return next.handle().pipe(map(data => applyDiscount(data)));
  }
}

// ✅ Interceptor 用于日志、缓存、响应转换、计时
@Injectable()
export class LoggingInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler) {
    const now = Date.now();
    const req = context.switchToHttp().getRequest();
    return next.handle().pipe(
      tap(() => console.log(`${req.method} ${req.url} - ${Date.now() - now}ms`)),
    );
  }
}
```

### 全局 ValidationPipe 必须配置 whitelist

```typescript
// ❌ 没有 whitelist——请求体中的额外属性直接传入
async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  await app.listen(3000);
}

// ✅ 全局 ValidationPipe + whitelist 过滤未知属性
async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
    }),
  );
  await app.listen(3000);
}
```

---

## 验证模式 (DTO)

### @ValidateNested() 必须搭配 @Type()

```typescript
// ❌ 只有 @ValidateNested——嵌套对象验证被静默跳过！
export class CreateOrderDto {
  @ValidateNested()
  shipping: AddressDto;
}

// ✅ @ValidateNested + @Type 配对使用
import { Type } from 'class-transformer';

export class CreateOrderDto {
  @ValidateNested()
  @Type(() => AddressDto)
  shipping: AddressDto;

  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => OrderItemDto)
  items: OrderItemDto[];
}
```

### 禁止裸 any Body

```typescript
// ❌ 没有 DTO——无验证、无类型安全、无 Swagger 文档
@Post()
create(@Body() body: any) {
  return this.service.create(body);
}

// ✅ 为每个操作创建 DTO
export class CreateUserDto {
  @IsEmail()
  email: string;

  @IsString()
  @MinLength(2)
  @MaxLength(100)
  name: string;
}

@Post()
create(@Body() dto: CreateUserDto) {
  return this.service.create(dto);
}
```

### Create 和 Update 应使用不同 DTO

```typescript
// ❌ PATCH 也要求所有字段——不合理的 API 设计
@Patch(':id')
update(@Body() dto: CreateUserDto) { /* all fields required */ }

// ✅ Update 使用 PartialType
export class UpdateUserDto extends PartialType(CreateUserDto) {}

@Patch(':id')
update(@Body() dto: UpdateUserDto) { /* all fields optional */ }
```

### 可选嵌套对象

```typescript
// ❌ 可选嵌套对象缺少 @IsOptional
export class UpdateOrderDto {
  @ValidateNested()
  @Type(() => AddressDto)
  shipping?: AddressDto; // undefined 时仍尝试验证
}

// ✅ @IsOptional + @ValidateNested + @Type
export class UpdateOrderDto {
  @IsOptional()
  @ValidateNested()
  @Type(() => AddressDto)
  shipping?: AddressDto;
}
```

---

## 错误处理

### 禁止吞掉错误

```typescript
// ❌ catch { return null }——隐藏了问题，调用者无法区分"不存在"和"出错了"
async findOne(id: string) {
  try {
    return await this.repo.findById(id);
  } catch (e) {
    return null;
  }
}

// ✅ 抛出有意义的异常
async findOne(id: string): Promise<User> {
  const user = await this.repo.findById(id);
  if (!user) {
    throw new NotFoundException(`User ${id} not found`);
  }
  return user;
}
```

### 使用内置异常类

```typescript
// ❌ 手动构造 HTTP 响应
throw new HttpException('Bad request', 400);

// ✅ 使用语义化的内置异常
throw new BadRequestException('Invalid email format');
throw new NotFoundException('User not found');
throw new ConflictException('Email already taken');
throw new ForbiddenException('Insufficient permissions');
throw new UnauthorizedException('Invalid credentials');
```

### 自定义异常过滤器

```typescript
// ✅ 全局异常过滤器——统一响应格式
@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  private readonly logger = new Logger(AllExceptionsFilter.name);

  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse();
    const request = ctx.getRequest();

    const status =
      exception instanceof HttpException
        ? exception.getStatus()
        : HttpStatus.INTERNAL_SERVER_ERROR;

    this.logger.error(`${request.method} ${request.url} - ${status}`, exception instanceof Error ? exception.stack : '');

    response.status(status).json({
      statusCode: status,
      timestamp: new Date().toISOString(),
      path: request.url,
    });
  }
}
```

---

## 循环依赖

### 模块间循环引用

```typescript
// ❌ Module A ↔ Module B
@Module({ imports: [UsersModule] })
export class OrdersModule {}

@Module({ imports: [OrdersModule] })
export class UsersModule {}

// ✅ 提取共享逻辑到第三个模块
@Module({
  providers: [SharedService],
  exports: [SharedService],
})
export class SharedModule {}

@Module({ imports: [SharedModule] })
export class OrdersModule {}

@Module({ imports: [SharedModule] })
export class UsersModule {}
```

### forwardRef 是最后手段

```typescript
// ⚠️ forwardRef 表示设计有问题——优先重新设计
@Module({
  imports: [forwardRef(() => UsersModule)],
})
export class OrdersModule {}

// ✅ 重新设计消除循环：
// 1. 提取共享模块
// 2. 使用事件驱动（EventEmitter）代替直接调用
// 3. 将共享逻辑提升到上层 Service
```

---

## 测试模式

### Use-Case 可脱离 NestJS 测试

```typescript
// ✅ 无需 NestFactory——直接 new
describe('CreateUserHandler', () => {
  let handler: CreateUserHandler;
  let repo: InMemoryUserRepository;

  beforeEach(() => {
    repo = new InMemoryUserRepository();
    handler = new CreateUserHandler(repo);
  });

  it('creates a user', async () => {
    const id = await handler.execute(
      new CreateUserCommand('user@example.com', 'Alice'),
    );
    expect(id).toBeDefined();
  });

  it('rejects duplicate email', async () => {
    await handler.execute(new CreateUserCommand('user@example.com', 'Alice'));
    await expect(
      handler.execute(new CreateUserCommand('user@example.com', 'Bob')),
    ).rejects.toThrow('already exists');
  });
});
```

### E2E 测试应配置与生产一致的 Pipes

```typescript
describe('UsersController (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleFixture = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    // 必须与 main.ts 中相同的全局配置
    app.useGlobalPipes(
      new ValidationPipe({
        whitelist: true,
        forbidNonWhitelisted: true,
        transform: true,
      }),
    );
    await app.init();
  });

  it('/POST users - valid', () => {
    return request(app.getHttpServer())
      .post('/users')
      .send({ email: 'test@test.com', name: 'Test' })
      .expect(201);
  });

  it('/POST users - extra fields rejected', () => {
    return request(app.getHttpServer())
      .post('/users')
      .send({ email: 'test@test.com', name: 'Test', role: 'admin' })
      .expect(400);
  });
});
```

---

## Review Checklist

### 分层架构

- [ ] ORM/Prisma 未直接注入 Controller
- [ ] 业务逻辑不在 Controller 中
- [ ] Repository 之间无互相注入
- [ ] Service 依赖数 ≤ 8（超出则拆分为 Use-Case）

### 依赖注入

- [ ] 接口 + Symbol Token 用于可替换的依赖
- [ ] 无 `forwardRef()`（如有，需设计文档说明原因）
- [ ] Scoped 服务未注入到 Singleton 中

### 验证

- [ ] 每个 `@ValidateNested()` 都有对应的 `@Type()`
- [ ] 全局 `ValidationPipe({ whitelist: true, forbidNonWhitelisted: true })` 已配置
- [ ] 无 `@Body() body: any`——必须使用 DTO
- [ ] Create 和 Update 使用不同 DTO（`PartialType`）
- [ ] 数组验证使用 `{ each: true }`
- [ ] 可选嵌套对象使用 `@IsOptional()` + `@ValidateNested()` + `@Type()`

### Guard / Interceptor / Pipe

- [ ] Guard 只做授权检查，不查询数据库
- [ ] Interceptor 只用于横切关注点（日志、缓存、响应转换）
- [ ] 业务规则在 Service 中

### 错误处理

- [ ] 无 `catch { return null }`——抛出有意义的异常
- [ ] 使用 NestJS 内置异常类
- [ ] 自定义异常过滤器在 `common/filters/` 中

### 模块

- [ ] 无循环模块引用
- [ ] Domain Entity 无框架装饰器（`@Injectable` 等）
- [ ] 外部服务调用在 `integrations/` 中

### 测试

- [ ] Use-Case Service 可脱离 NestJS 测试
- [ ] E2E 测试配置与生产一致的全局 Pipes/Guards
- [ ] Domain Entity 零框架依赖
