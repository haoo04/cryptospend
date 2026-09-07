# CryptoSpend 收据、分类与图表分析开发计划

- 日期：2026-09-07
- 状态：待实施

## 1. 目标

在不改变现有复式账本、MYR micros 精度和历史交易冲销原则的前提下，完成三个相互配合的能力：

1. 交易可选附上一张收据图片，作为超市购物单、餐厅账单等凭证。
2. 报表中心新增图表分析，可按 day、week、month、year、all 查看收入、支出趋势和分类构成。
3. 新增分类管理页面；录入会影响收入或支出的交易时，从预设分类中选择，不再自由输入文字。

## 2. 当前实现基线

- 前端是 React 19 + TypeScript + Vite，主导航和大部分交易界面位于 `frontend/src/App.tsx`，现有报表页位于 `frontend/src/ReportsCenter.tsx`。
- 后端是 FastAPI + SQLAlchemy + Alembic + SQLite，所有权威金额由后端按 MYR micros 整数计算，API 金额使用十进制字符串。
- `transaction_events.category` 当前是可空字符串，只有 MANUAL 表单直接输入该字段，没有分类实体或约束。
- 收入与支出已有服务端汇总，月报支持配置时区边界、冲销后的净额和不可变快照，但尚无按分类及多时间粒度的图表数据接口。
- `GET /api/events` 默认只返回最近 100 笔，因此图表不能依赖前端已加载的事件列表，必须由后端直接聚合完整范围。
- Google Drive 备份上传 SQLite 一致性快照。收据若保存在 SQLite 内，即可自动进入现有备份与恢复流程。

## 3. 已确定的产品边界

| 主题 | 本期决定 |
| --- | --- |
| 收据数量 | 每个 `TransactionEvent` 最多一张；支持新增、预览、替换和删除 |
| 图片格式 | JPEG、PNG、WebP；不接受 PDF、GIF、HEIC 或远程图片 URL |
| 图片大小 | 最大 10 MiB；空文件拒绝 |
| 图片存储 | 原始二进制存入 SQLite BLOB，不以 Base64 放入事件 JSON |
| 可附加范围 | 已存在的 ledger event，包括 MANUAL、卡结算、草稿和已冲销原事件；收据不复制到 reversal event |
| 分类类型 | `INCOME` 和 `EXPENSE` |
| 分类生命周期 | 新建、重命名、停用、重新启用；本期不做硬删除 |
| 分类选择 | 用户可分类的收入/消费流程使用预设项；SALARY、INCOME、EXPENSE、CARD_SETTLEMENT、REWARD 必选，系统费用等其他事件不强制 |
| 历史重分类 | 允许通过专用接口修改分类；只改报表元数据并写审计日志，不改金额、分录或交易状态 |
| 图表入口 | 复用 Reports 页面，新增 Analytics 标签；分类管理作为独立主导航页面 |
| 图表实现 | 使用 React + CSS/SVG 的基础柱状图，不新增第三方前端图表依赖 |
| 统计口径 | 与现有账本一致：收入账户 credit 为正，支出账户 debit 为正；退款和冲销按相反方向抵减 |
| 时区 | 使用 `settings.timezone`；所有区间均为左闭右开 `[start, end)` |

## 4. 非目标

本期不包含以下能力：

- OCR、自动识别商户、金额或分类。
- 一笔交易多张图片、多页票据或 PDF 文档。
- 图片裁剪、压缩、旋转、去 EXIF 或云端图片库。
- 预算、分类层级、标签、多分类拆分、商户自动分类规则。
- 修改已保存的月度快照；历史快照继续保持不可变。
- 直接修改任何账本金额或分录来实现分类调整。

## 5. 用户体验设计

### 5.1 分类管理

主导航新增 **Categories** 页面，页面分为 Income 和 Expense 两组。

每组提供：

- 活跃分类列表。
- 新建分类表单。
- 重命名操作。
- 停用操作；停用分类不再出现在新交易下拉框中，但历史交易和图表仍保留。
- 显示已停用分类并允许重新启用。

分类名规则：

- 去除首尾空白并合并连续空白。
- 长度 1～100 个字符。
- 同一类型内按 Unicode case-fold 后不可重名，例如 `Food` 和 `food` 视为同名。
- Income 与 Expense 可以存在同名分类。

初始分类：

- Expense：Food、Grocery、Utilities、Transport、Shopping、Subscription、Entertainment、Travel、Healthcare、Other Expense。
- Income：Salary、Bonus、Cashback、Crypto Reward、Other Income。

停用正在使用的分类是允许的。这样不会破坏历史引用；它只影响之后的新选择。

### 5.2 交易录入与重分类

MANUAL 表单现有 Category 文本框改为下拉选择：

- SALARY、INCOME 只显示活跃 Income 分类并要求选择。
- EXPENSE 只显示活跃 Expense 分类并要求选择。
- ADJUSTMENT 若选择了 Income/Expense 账户，则显示相应类型的可选分类；未选择时归入 Uncategorized。
- TRANSFER、TRADE、OPENING_BALANCE 等不属于用户收入/消费分类的事件隐藏分类字段。
- 需要分类但没有可用分类时，显示前往 Categories 页的明确入口，而不是退回自由输入。

卡业务补充规则：

- Card authorization 尚未形成正式 ledger event，不要求分类。
- Card settlement 录入时选择 Expense 分类。
- Card refund 自动沿用原 purchase 的分类。
- Credited reward 录入时选择 Income 分类。
- Reversal 在统计时沿用被冲销原事件的分类。

Transactions 列表新增 Category 列和收据图标。事件详情中可以：

- 查看当前分类。
- 对收入或支出事件重新选择分类。
- 查看历史遗留但尚未迁移成功的分类文字。

重分类后只刷新事件与图表数据，不重算或重写 ledger entries。

### 5.3 收据上传

MANUAL 交易表单增加可选的 Receipt image 文件选择器：

- 选中后显示文件名、大小和本地缩略预览。
- 提交前可移除选择。
- 前端先创建交易，再用返回的 event ID 上传图片。
- 如果交易创建成功但图片上传失败，明确提示“交易已保存，收据上传失败”，保留 event ID，并提供从交易详情重试的路径；绝不再次创建交易。

事件详情提供收据区域：

- 没有收据时显示 Upload receipt。
- 有收据时按需加载缩略预览，不在事件列表请求中下载图片数据。
- 支持打开原图、替换和删除；删除前要求确认。
- 已冲销交易的收据仍显示在原事件上，作为历史凭证。

### 5.4 图表分析

Reports 页面新增 **Analytics** 标签，默认选择当前 month。顶部包含时间范围按钮和对应日期选择器。

| 选择 | 查询范围 | 时间趋势桶 |
| --- | --- | --- |
| day | 选定本地日期 00:00 到次日 00:00 | 小时 |
| week | 包含选定日期的周一 00:00 到下周一 00:00 | 天 |
| month | 选定月份首日到下月首日 | 天 |
| year | 选定年份 1 月 1 日到下一年 1 月 1 日 | 月 |
| all | 最早至最晚的非草稿事件，包含未来已录入事件 | 年 |

页面内容：

1. Summary cards：Income、Expense、Net income。
2. Income vs Expense：同一时间桶内的并列柱状图。
3. Expense by category：按净支出降序的横向柱状图。
4. Income by category：按净收入降序的横向柱状图。
5. 无数据时显示明确空状态，不能绘制假数据或保留上一范围的旧图。

图表要求：

- 柱体、图例、轴标签和 tooltip 在桌面与窄屏均可读。
- 同时提供可访问的文本数值；颜色不是区分收入和支出的唯一方式。
- API 的精确金额字符串用于卡片、标签和 tooltip。前端只允许将副本转换为 `number` 计算柱体相对宽高，转换结果不得回写、求和或参与任何财务结论。
- 负的净分类金额（例如所选期间退款大于消费）显示为反向柱，不静默截断为零。

## 6. 数据模型

### 6.1 `categories`

新增表：

| 字段 | 类型 | 约束/用途 |
| --- | --- | --- |
| `id` | `String(32)` | UUID hex 主键 |
| `name` | `String(100)` | 用户显示名称 |
| `normalized_name` | `String(100)` | 规范化后用于唯一性检查 |
| `kind` | `String(16)` | `INCOME` 或 `EXPENSE` |
| `active` | `Boolean` | 默认 `true` |
| `created_at` | `String(40)` | UTC ISO 时间 |
| `updated_at` | `String(40)` | UTC ISO 时间 |

约束和索引：

- `CHECK kind IN ('INCOME', 'EXPENSE')`。
- `UNIQUE(kind, normalized_name)`。
- `(kind, active, name)` 查询索引。

### 6.2 `transaction_events.category_id`

在 `transaction_events` 增加可空 `category_id`，外键指向 `categories.id` 并建立索引。

现有 `category` 文本列本期保留为历史录入标签与降级保护：

- 新 API 不再接受自由输入的 `category`。
- 新事件根据所选分类自动写入 `category_id`，同时将当时名称保存在现有 `category` 字段。
- 正常展示和统计优先使用 `category_id` 对应的当前分类名；没有 ID 时才展示旧文本。
- 分类重命名不批量修改历史 event 行，聚合仍按稳定 ID，不会把一个分类拆成新旧两组。
- 后续确认所有旧数据迁移完成后再单独评估删除旧文本列，本期不做。

### 6.3 `event_receipts`

新增一对一表：

| 字段 | 类型 | 约束/用途 |
| --- | --- | --- |
| `id` | `String(32)` | UUID hex 主键 |
| `event_id` | `String(32)` | 指向 `transaction_events.id`，唯一，`ON DELETE CASCADE` |
| `original_filename` | `String(255)` | 只作显示，不参与本地路径拼接 |
| `content_type` | `String(32)` | 规范化为 `image/jpeg`、`image/png` 或 `image/webp` |
| `byte_size` | `Integer` | `1..10485760` |
| `data` | `LargeBinary` | 原始图片字节，ORM 默认 deferred load |
| `created_at` | `String(40)` | 首次上传时间 |
| `updated_at` | `String(40)` | 最近替换时间 |

事件 JSON 只返回收据 metadata，不返回 `data`。图片字节仅由专门下载接口读取。

## 7. 数据迁移

按依赖拆分为两次 Alembic migration，便于独立验证和提交。

### 7.1 `0005_categories`

1. 创建 `categories`。
2. 为 `transaction_events` 增加 `category_id` 和索引。
3. 插入默认 Income/Expense 分类；若同类型同名已由旧数据生成则跳过。
4. 遍历非空的旧 `transaction_events.category`：
   - 通过该 event 的 ledger account type 判断是 Income 或 Expense。
   - 按 `(kind, normalized_name)` 创建或复用分类。
   - 回填对应 event 的 `category_id`。
   - 不包含 Income/Expense 分录、无法可靠判断类型的旧值保持 `category_id = NULL`，原文本不丢失。
5. downgrade 只删除新增列、索引和表；现有 `category` 文本保证可回退。

### 7.2 `0006_event_receipts`

1. 创建 `event_receipts` 及唯一外键约束。
2. 不搬运或扫描任何本地图片目录。
3. downgrade 删除该表；执行 downgrade 会删除收据数据，正式操作前必须使用现有数据库备份流程。

同时更新 migration head 测试，期望 revision 为 `0006_event_receipts`。

## 8. API 设计

### 8.1 Category API

`GET /api/categories?kind=EXPENSE&include_inactive=false`

- 默认只返回 active 分类。
- `kind` 可省略；返回按 kind、name 排序的列表。

`POST /api/categories`

```json
{
  "name": "Electric Bill",
  "kind": "EXPENSE"
}
```

- 成功返回 `201`。
- 同类型规范化重名返回 `409`。

`PATCH /api/categories/{category_id}`

```json
{
  "name": "Electricity",
  "active": true
}
```

- 字段均可选，但请求至少包含一个变更。
- 停用被引用分类仍返回成功。
- 重命名冲突返回 `409`。

不提供 category DELETE API，以免破坏历史引用。

### 8.2 Event category contract

`ManualEventCreate`、`CardSettlementCreate` 和 `RewardCreditCreate` 增加 `category_id`；原自由文本 `category` 从可写 schema 移除。

服务端必须验证：

- 分类存在且 active。
- 分类 kind 与实际 Income/Expense ledger account 一致。
- SALARY、INCOME、EXPENSE、CARD_SETTLEMENT、REWARD 新事件必须有相应分类。
- TRADE、TRANSFER、FEE 等系统或资金流事件即使内部含费用分录也不被强制要求用户消费分类。
- 不包含 Income/Expense 分录的交易不得错误绑定分类；ADJUSTMENT 可以不分类。

`PATCH /api/events/{event_id}/category`

```json
{
  "category_id": "category-id"
}
```

- 仅允许有 Income 或 Expense 分录的 event。
- active 分类才能被新绑定；已绑定的 inactive 分类可以继续保留。
- 记录 `EVENT_CATEGORY_CHANGED` audit log，details 包含 old/new category ID，不包含敏感图片数据。
- 分类修正不要求创建 reversal，因为它不改变账本事实。

`EventRead` 保持 `category: string | null` 供当前前端平滑迁移，并增加：

```json
{
  "category_id": "category-id",
  "category_kind": "EXPENSE",
  "receipt": {
    "id": "receipt-id",
    "original_filename": "restaurant.jpg",
    "content_type": "image/jpeg",
    "byte_size": 248120,
    "created_at": "2026-09-07T08:00:00+00:00",
    "updated_at": "2026-09-07T08:00:00+00:00"
  }
}
```

### 8.3 Receipt API

安装后端 multipart 解析依赖 `python-multipart`。

`PUT /api/events/{event_id}/receipt`

- 请求为 `multipart/form-data`，字段名 `file`。
- 没有收据时创建，有收据时原位替换，返回 metadata。
- 分块读取到 `10 MiB + 1 byte` 后立即拒绝超限文件，返回 `413`。
- 同时检查声明 MIME、扩展名和 JPEG/PNG/WebP 文件签名字节；不匹配返回 `415`。
- event 不存在返回 `404`。
- 写 `RECEIPT_ATTACHED` 或 `RECEIPT_REPLACED` audit log，只记录文件名、MIME 和大小。

`GET /api/events/{event_id}/receipt`

- 返回原始图片响应，设置正确 `Content-Type`、安全的 inline `Content-Disposition`、`X-Content-Type-Options: nosniff` 和 `Cache-Control: private, no-store`。
- event 或 receipt 不存在返回 `404`。

`DELETE /api/events/{event_id}/receipt`

- 成功返回 `204`，不存在返回 `404`。
- 写 `RECEIPT_REMOVED` audit log。

前端通用 request helper 遇到 `FormData` 时不得强制设置 `Content-Type: application/json`，让浏览器自动生成 multipart boundary。

### 8.4 Analytics API

`GET /api/reports/analytics?period=month&anchor=2026-09-07`

参数：

- `period`: `day | week | month | year | all`，必填。
- `anchor`: `YYYY-MM-DD`；除 `all` 外必填，由服务端按配置时区解释。

响应示例：

```json
{
  "period": "month",
  "anchor": "2026-09-07",
  "timezone": "Asia/Kuala_Lumpur",
  "period_start": "2026-08-31T16:00:00+00:00",
  "period_end": "2026-09-30T16:00:00+00:00",
  "bucket_unit": "day",
  "summary": {
    "income_myr": "8000",
    "expense_myr": "1260.5",
    "net_income_myr": "6739.5"
  },
  "timeline": [
    {
      "bucket_start": "2026-09-01T00:00:00+08:00",
      "label": "1 Sep",
      "income_myr": "8000",
      "expense_myr": "0"
    }
  ],
  "expense_categories": [
    {
      "category_id": "category-id",
      "name": "Grocery",
      "amount_myr": "320.5"
    },
    {
      "category_id": null,
      "name": "Uncategorized",
      "amount_myr": "20"
    }
  ],
  "income_categories": []
}
```

聚合规则：

- 只统计非 `DRAFT` event。
- Income：Income account 的 credit 减 debit。
- Expense：Expense account 的 debit 减 credit。
- 时间趋势和分类汇总从同一批 ledger entries 计算，二者总数必须相等。
- 没有 `category_id` 的相关 event 统一进入 `Uncategorized`，不丢弃。
- reversal 未单独选择分类时解析原 event 分类；card refund 沿用 purchase 分类。
- 所有空时间桶都返回字符串 `"0"`，保证图表横轴连续。
- 金额格式继续复用 `micros_to_myr`，API 不返回浮点财务值。

## 9. 后端实施步骤

### 阶段 A：分类基础

1. 在 `backend/app/enums.py` 增加 `CategoryKind`。
2. 在 `backend/app/models.py` 增加 `Category`，并给 `TransactionEvent` 增加 `category_id` relationship。
3. 在 `backend/app/schemas.py` 增加 category create/update/read schema，并调整事件相关 command/read schema。
4. 创建 `0005_categories` migration、默认分类和旧字符串回填。
5. 在 `backend/app/api.py` 增加分类 CRUD、事件重分类和读取接口。
6. 在 `backend/app/ledger.py`、`backend/app/cards.py` 中集中验证 category kind，并处理 refund/reversal 继承规则。

### 阶段 B：收据

1. 在 `backend/requirements.txt` 增加 `python-multipart`。
2. 在 `backend/app/models.py` 增加 `EventReceipt`，图片列使用 deferred loading。
3. 创建 `0006_event_receipts` migration。
4. 在 `backend/app/api.py` 增加上传、读取、替换和删除接口；校验逻辑保持为少量直接函数，不新增存储抽象层。
5. 扩展 event serializer，只查询 metadata，不在事件列表载入 BLOB。

### 阶段 C：分析报表

1. 在 `backend/app/reporting.py` 增加统一 period boundary/bucket 计算和 `analytics_report`。
2. 复用现有 `Setting.timezone`、ledger account type、entry direction 和金额转换函数。
3. 在 `backend/app/api.py` 增加 `/reports/analytics` endpoint 和参数校验。
4. 不复用前端的 100 条 event 列表，不在浏览器做账本汇总。

## 10. 前端实施步骤

### 阶段 A：分类页面与选择器

1. 在 `frontend/src/api.ts` 增加 `Category`、事件 category/receipt metadata 类型和相关 API 方法。
2. `App.tsx` 新增 `categories` view、导航、categories 状态及按需刷新。
3. 新增小型 `CategoryManager.tsx`，实现两类列表、新建、重命名、停用和启用。
4. `AddTransaction` 的自由文本框替换为受控 select，并按账户类型过滤。
5. `CardCenter` 的 settlement 与 reward credit 表单接收并提交相应分类；refund 不重复选择。
6. Transactions 表格和详情显示分类，并允许专用重分类操作。

### 阶段 B：收据交互

1. `api.ts` 支持 FormData 上传、图片 URL 和删除。
2. `AddTransaction` 提交改为可取得已创建 event；随后独立上传可选图片。
3. 正确区分“交易失败”和“交易成功但图片失败”两种错误状态。
4. 详情面板按需加载图片，支持替换和确认删除；及时调用 `URL.revokeObjectURL` 清理本地预览。
5. 列表只展示 metadata 图标，不预取图片。

### 阶段 C：图表

1. `ReportsCenter.tsx` 增加 Analytics tab 和 period/anchor 控件。
2. 仅在 Analytics 打开或筛选条件变化时请求数据，避免加入 App 全局 refresh 的并行请求。
3. 使用两个简单、可复用的本地组件绘制 grouped vertical bars 与 horizontal bars。
4. 添加 loading、error、empty、negative value 和窄屏横向滚动样式。
5. 保持现有 Monthly、Journeys、Channel comparison 行为不变。

## 11. 校验、安全与隐私

- 不信任文件扩展名或浏览器 MIME，后端必须检查签名字节。
- 原始文件名不得用于磁盘路径、SQL 或未转义响应头。
- 收据不通过静态目录公开，必须由精确 event endpoint 读取。
- 收据原始字节可能保留 EXIF；本期数据只保存在本机 SQLite，除非用户主动执行 Google Drive backup。
- Google Drive backup 会因 BLOB 增大；10 MiB 单图上限和一对一约束用于限制增长。
- 审计日志只存 metadata，不存图片内容或 Base64。
- 分类和收据操作均为本地行为，不增加任何第三方数据发送。
- 所有分类与时间参数由服务端校验；错误使用现有 `{ "detail": "..." }` 格式。

## 12. 测试计划

### 12.1 后端

分类测试：

- migration 默认分类和旧 `category` 字符串回填正确。
- 同类型大小写/空白等价名称返回 `409`，不同类型可同名。
- 停用分类不再用于新绑定，但历史 event 仍可读取和聚合。
- Income/Expense kind 与 ledger account 不匹配时返回 `422`。
- 要求分类的 SALARY、INCOME、EXPENSE、CARD_SETTLEMENT、REWARD 缺分类时返回 `422`。
- 重分类改变分类聚合但不改变 event entries、总收入或总支出，并写 audit log。
- card refund 与 reversal 归回原分类。

收据测试：

- JPEG、PNG、WebP 可上传，metadata 与下载字节一致。
- 无收据事件仍正常创建和读取。
- 替换保持一对一，删除后返回 `404`。
- 空文件、伪造 MIME/签名、不支持格式、超过 10 MiB 分别返回预期状态码。
- event 列表不会序列化 BLOB。
- 数据库 backup/restore 后 receipt metadata 与 bytes 仍存在。

分析测试：

- Asia/Kuala_Lumpur 下 day/week/month/year 的 UTC 边界正确，week 从周一开始。
- all 包含完整非草稿历史且按年补齐 bucket。
- 空 bucket 返回零。
- 收入、支出、退款、reward、reversal 的正负方向正确。
- Uncategorized 不被遗漏。
- timeline 总和、category 总和与 summary 精确一致。
- 金额全部为规范化十进制字符串。

### 12.2 前端

- MANUAL 分类字段按 debit/credit 账户类型过滤并提交 category ID，不再出现自由文本输入。
- 无 active 分类时显示 Categories 导航提示。
- MYR 单金额输入的现有回归测试继续通过。
- 分类新建、重命名、停用、启用及历史重分类交互正确。
- 可选收据不影响无图片提交；有图片时严格按“创建 event → 上传 receipt”执行。
- 上传失败不会重复创建 event，详情可重试。
- period/anchor 组合形成正确 analytics 请求；快速切换不会显示较早请求的过期结果。
- 图表正确处理零数据、负值、长分类名和窄屏。

### 12.3 全量验证命令

实施完成后按仓库现有流程执行：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .

cd ..\frontend
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

按仓库约束，若新增依赖尚未安装，由用户手动执行安装；实现过程不运行 `npm.cmd install`。

## 13. 验收标准

### 收据

- 不选择图片即可照常创建交易。
- 支持格式内、10 MiB 以内的图片可以从新建交易或详情上传、预览、替换和删除。
- 上传失败不会回滚或重复创建已成功的交易，并有明确提示。
- 收据图片二进制不出现在 event JSON 中，事件列表只返回 metadata，不会批量下载图片。
- 数据库备份包含收据。

### 分类

- Categories 页面可管理 Income/Expense 分类及 active 状态。
- SALARY、INCOME、EXPENSE、CARD_SETTLEMENT、REWARD 只能选择 active 预设分类，不能自由输入。
- 历史分类不会因停用而丢失；重命名不会把历史统计拆成多个名称。
- 历史重分类不改变任何金额或分录，并留下审计记录。
- 旧数据库升级后，能够可靠识别的自由文本分类被自动映射。

### 图表分析

- day、week、month、year、all 五种范围均可选择，边界符合配置时区。
- 页面至少展示收入/支出时间趋势、支出分类和收入分类三组图表。
- 图表、summary 和已有收入/支出口径一致，退款与冲销不会被重复计算。
- Uncategorized、无数据和负净额均有明确展示。
- 所有权威金额仍由后端以整数 micros 计算并以字符串返回。

### 回归

- 现有账本、交易、卡、portfolio、monthly snapshot、Google Drive backup 功能不退化。
- 后端 pytest 与 Ruff、前端 Vitest、ESLint 和 production build 全部通过。

## 14. 建议提交顺序

1. `Add managed transaction categories`

   包含 category migration、model/schema/API、分类页面、所有录入选择器及聚焦测试。

2. `Add optional transaction receipt images`

   包含 receipt migration、multipart dependency、API、前端上传/详情及聚焦测试。

3. `Add period-based income and expense charts`

   包含 analytics 聚合接口、Reports 图表、时间选择器及聚焦测试。

每次提交前只暂存该功能相关文件并检查 staged diff；最后运行 `git status`，不得纳入用户现有的 `node_modules/`、根目录 `package-lock.json` 或 `开发规划.md`，也不得推送远端。

## 15. 预计文件影响

| 文件 | 预计修改 |
| --- | --- |
| `backend/app/enums.py` | `CategoryKind` |
| `backend/app/models.py` | Category、EventReceipt、event relationships |
| `backend/app/schemas.py` | category/receipt/analytics contracts |
| `backend/app/ledger.py` | category validation、reversal resolution |
| `backend/app/cards.py` | settlement/reward category、refund inheritance |
| `backend/app/reporting.py` | 时间范围与分类聚合 |
| `backend/app/api.py` | category、receipt、analytics endpoints |
| `backend/requirements.txt` | `python-multipart` |
| `backend/migrations/versions/0005_categories.py` | 分类 schema、defaults、旧数据回填 |
| `backend/migrations/versions/0006_event_receipts.py` | 收据 schema |
| `backend/tests/*` | migration、分类、收据、统计回归 |
| `frontend/src/api.ts` | 新类型与 API 调用 |
| `frontend/src/App.tsx` | 导航、状态、交易分类与收据详情 |
| `frontend/src/CardCenter.tsx` | 卡结算/reward 分类选择 |
| `frontend/src/CategoryManager.tsx` | 独立分类管理页面 |
| `frontend/src/ReportsCenter.tsx` | Analytics tab、筛选和图表 |
| `frontend/src/App.css` | 分类、收据预览和响应式图表样式 |
| `frontend/src/*.test.tsx` | 关键前端交互回归 |

计划实施时应继续遵循“后端是财务计算权威、历史账本不直接修改、选择最小可行改动”的现有项目原则。
