# CryptoSpend 固定开销（周费、月费、年费）开发计划

- 日期：2026-09-07
- 状态：已完成
- 前置依赖：先完成并提交 `2026-09-07-receipt-category-analytics-plan.md` 对应的分类、收据和分析功能；本计划从 Alembic revision `0006_event_receipts` 继续。

## 1. 目标

为房租、订阅费、会员费、保险等重复且金额固定的开销增加独立管理能力：

1. 新建、编辑、暂停和恢复固定开销模板。
2. 支持 `WEEKLY`、`MONTHLY`、`YEARLY` 三种周期。
3. 明确显示下一到期日、逾期状态和按周期汇总的固定成本。
4. 用户确认付款后，由后端生成一笔正式、平衡的 `EXPENSE` 账本事件。
5. 允许跳过当前一期，并保留处理历史。
6. 保持现有 MYR micros 精度、复式记账、分类约束、冲销和报表口径不变。

## 2. 当前实现基线

- 后端是 FastAPI + SQLAlchemy + Alembic + SQLite；权威金额以 MYR micros 整数保存，API 金额使用十进制字符串。
- `POST /api/events/manual` 已能生成一笔借记 EXPENSE、贷记 ASSET 的平衡事件，但每次都需要手工填写完整表单。
- 支出分类已由 `categories` 管理；新支出必须选择一个活跃的 `EXPENSE` 分类。
- `transaction_events` 是实际财务报表的唯一账本事实来源，已入账事件通过新增 reversal event 冲销，不直接修改历史金额。
- 前端是 React 19 + TypeScript + Vite，主导航和共享状态位于 `frontend/src/App.tsx`，API 类型及请求集中在 `frontend/src/api.ts`。
- 系统是 local-first 应用，关闭期间没有可靠的常驻进程，因此不能依赖后台定时任务在到期日自动执行。
- Google Drive 会备份完整 SQLite 数据库；新增的固定开销表会自然进入现有备份，不需要单独的文件同步流程。

## 3. 已确定的产品边界

| 主题 | 本期决定 |
| --- | --- |
| 固定开销的含义 | 固定开销首先是“计划模板”，不是实际账本交易 |
| 入账时机 | 用户点击 **Record payment** 并确认后才生成实际 `EXPENSE` event |
| 自动处理 | 不后台自动入账；应用重新打开后只显示逾期，不静默补账 |
| 支持周期 | 每周、每月、每年；本期不支持“每 N 周/月”、每日或季度 |
| 金额与资产 | 仅支持固定 MYR 金额，账本资产必须是一个活跃的 `MYR` asset |
| 账户 | 付款账户必须是未关闭的 `ASSET` account；支出账户必须是未关闭的 `EXPENSE` account |
| 分类 | 必须选择活跃的 `EXPENSE` category |
| 日期语义 | 到期日是 `settings.timezone` 下的本地日历日期，不是 UTC 时间点 |
| 提前付款 | 允许提前记录“下一期”；实际报表按用户填写的实际发生时间统计 |
| 逾期 | 只处理当前 `next_due_on`；记录或跳过后才推进到下一期，避免一次打开应用就批量补账 |
| 生命周期 | 支持编辑、暂停、恢复；本期不提供硬删除 |
| 历史修改 | 编辑模板只影响尚未处理的当前及未来期次，既有 event 和 occurrence 不变 |
| 跳过 | 跳过不生成账本 event，但会保存一期 `SKIPPED` 记录并推进日期 |
| 冲销 | 冲销已生成的 event 会抵消实际报表，但不会回拨模板的下一到期日，也不会自动重开该期 |
| 计划金额统计 | 固定开销页面单独显示；未记录的计划金额不进入 Overview、Reports 或 Analytics 的实际收入支出 |

## 4. 非目标

本期不包含：

- 银行、银行卡、订阅服务或日历的自动扣款与同步。
- Windows 后台服务、系统通知、邮件提醒或推送通知。
- 自动在到期日创建交易、应用启动时批量追加入账或离线计划任务。
- 浮动账单、阶梯价格、试用期、折扣、税费拆分、按使用量计费或金额自动增长。
- 外币或 crypto 定价、动态汇率、卡授权/结算、分期付款或一笔费用拆分到多个账户。
- 每日、工作日、双周、季度、自定义间隔或复杂 RRULE。
- 模板附件；实际付款生成 event 后仍可使用现有 Transactions 页面上传收据。
- 预算上限、余额预测、现金流告警或把计划金额混入实际财务报表。
- 为历史手工支出自动推断并创建固定开销模板。
- 固定开销硬删除、完整审计日志查看器或无限滚动历史分页。

## 5. 核心概念和状态

### 5.1 模板与实际支出分离

固定开销模板保存“以后应该发生什么”，`TransactionEvent` 保存“已经确认发生什么”。

```text
固定开销模板
    ├─ Record payment ─> occurrence: RECORDED ─> POSTED EXPENSE event ─> 实际报表
    └─ Skip           ─> occurrence: SKIPPED  ─> 不生成 event       ─> 不影响报表
```

这条边界必须由后端保证。读取固定开销列表、应用启动或日期跨天都不得自行创建账本事件。

### 5.2 模板状态

API 根据 `active`、`next_due_on` 和设置时区中的今天返回一个派生状态：

| 状态 | 条件 | 页面行为 |
| --- | --- | --- |
| `PAUSED` | `active = false` | 不计入活跃汇总，不允许记录或跳过，可编辑或恢复 |
| `OVERDUE` | active 且 `next_due_on < today` | 高优先级显示，可记录或跳过 |
| `DUE_TODAY` | active 且 `next_due_on = today` | 显示今天到期，可记录或跳过 |
| `UPCOMING` | active 且 `next_due_on > today` | 显示剩余天数，允许提前记录或跳过 |

数据库不保存这些派生状态，避免状态随日期变化后失真。

### 5.3 一期 occurrence

- 数据库不预生成未来的 `PENDING` 行；模板的 `next_due_on` 就是唯一待处理期次。
- 用户记录或跳过时才新增 occurrence。
- `(recurring_expense_id, due_on)` 唯一，确保同一期最多处理一次。
- occurrence 保存当期金额快照；之后修改模板金额不会改写历史。
- `RECORDED` occurrence 关联一个账本 event；`SKIPPED` occurrence 不关联 event。

## 6. 用户体验设计

### 6.1 导航与页面布局

主导航在 **Add transaction** 之后增加 **Fixed expenses** 页面。页面包含：

1. 汇总卡片：Active、Overdue、Weekly total、Monthly total、Yearly total、Annualized estimate。
2. 筛选：Active / Paused / All。
3. 模板列表：先按状态排序，再按下一到期日和名称排序。
4. 新建/编辑表单。
5. 选中模板后的最近处理历史。

小屏幕改为单列，操作按钮换行，但金额、周期、下一到期日和状态不能被隐藏。

### 6.2 新建与编辑字段

| 字段 | 规则 | 示例 |
| --- | --- | --- |
| Name | 必填；去除首尾空白并合并连续空白；1～120 字符；不要求唯一 | `房租`、`Netflix` |
| Amount (MYR) | 必填；使用现有十进制字符串校验；转为 micros 后必须大于 0 | `1800`、`55.90` |
| Frequency | `WEEKLY`、`MONTHLY`、`YEARLY` | `MONTHLY` |
| First due date | 必填的本地日历日期；允许过去日期 | `2026-09-15` |
| MYR asset | 只显示 active 且 symbol 为 `MYR` 的资产；仅有一个时自动选择 | `MYR` |
| Pay from | 只显示未关闭的 `ASSET` account | `Bank` |
| Expense account | 只显示未关闭的 `EXPENSE` account | `General Expense` |
| Category | 只显示 active 的 `EXPENSE` category | `Subscription` |

表单补充说明：

- `First due date` 同时确定第一期待处理日期和后续日历锚点。
- 若当前没有可用支出分类，显示前往 Categories 页的入口，不退回自由输入。
- 若没有可用 MYR 资产、ASSET 账户或 EXPENSE 账户，禁用提交并指出缺少的配置。
- 名称可重复，因为同一服务可能由不同账户支付，或存在家庭与个人两份订阅。
- 编辑 Name、Amount、Asset、Account、Category 只影响未来记录。
- 修改 Frequency 或到期规则时，界面要求用户输入一个新的 **Next due date**；后端将其作为新的锚点和下一期，不回算或删除历史。
- 暂停不改变 `next_due_on`；恢复后若日期已过去，模板立即显示 OVERDUE。

### 6.3 列表内容

每个模板至少显示：

- Name 与状态徽标。
- 固定金额和周期，例如 `MYR 55.90 / month`。
- 下一到期日及 `today`、`3 days overdue` 或 `in 12 days`。
- Category。
- `Pay from → Expense account`。
- 标准化年成本。
- Edit、Pause/Resume、Record payment、Skip current occurrence 操作。

Paused 项不显示 Record 和 Skip。所有危险或不可逆操作使用现有简单交互风格确认，不引入新的对话框库。

### 6.4 Record payment

点击后显示确认区域：

- 模板名称。
- 当前 `due_on`，只读。
- 金额、MYR 资产、付款账户、支出账户和分类，只读。
- Actual occurred at，默认当前本地时间，可修改，提交为带时区 ISO datetime。

确认后服务端在同一数据库事务内：

1. 验证客户端提交的 `due_on` 仍等于模板当前 `next_due_on`。
2. 再次验证模板 active、金额、MYR 资产、账户和分类仍可用。
3. 创建并 POST 一笔 `EXPENSE` event：借记 Expense account，贷记 Pay from account。
4. 两边 `quantity` 与 `book_amount_myr` 都使用模板固定 MYR 金额。
5. event `source = "RECURRING_EXPENSE"`，description 使用模板 Name，`external_id` 使用可追踪的模板 ID 与 due date。
6. 新增 `RECORDED` occurrence 并关联 event。
7. 按日历规则推进 `next_due_on`。
8. 写 audit log 后一次 commit。

任一步失败都回滚，不能出现“账本已入账但日期未推进”或相反状态。成功后刷新固定开销、事件、账户余额、Overview 和 Reports 所需数据。

### 6.5 Skip current occurrence

Skip 操作显示当前 due date，并允许填写最多 500 字符的可选原因。确认后：

1. 验证 active 和客户端 due date 未过期。
2. 新增 `SKIPPED` occurrence，保存当期金额快照及原因。
3. 不创建 ledger event。
4. 推进 `next_due_on` 并写 audit log。

连续漏掉多期时，用户逐期 Record 或 Skip。首版不提供“一键跳到今天”，以免误跳仍需补记的账单。

### 6.6 历史与冲销

- 详情区显示最近 50 个 occurrence，按 due date 倒序排列。
- `RECORDED` 项显示 event ID、event status、实际发生时间和金额，并可跳转到 Transactions 后由用户 Inspect。
- `SKIPPED` 项显示跳过原因，不计入任何实际报表。
- 通过现有 Transactions 冲销一个固定开销 event 后，occurrence 仍保持已处理，但显示关联 event 为 `REVERSED`。
- 冲销不会自动把模板 `next_due_on` 回拨，避免下一期开销被重复创建。
- 若用户冲销后确实需要重新记同一期，首版使用普通 Add transaction 录入更正支出；“重新打开 occurrence 并保留多次尝试链”留作后续功能。

## 7. 周期与日期规则

### 7.1 通用规则

- `anchor_on` 和 `next_due_on` 都以严格的 `YYYY-MM-DD` 保存。
- API 使用 Pydantic `date` 解析并拒绝不存在的日期。
- 到期状态中的“今天”由 `settings.timezone` 计算，不使用浏览器时区猜测。
- 修改系统 reporting timezone 不改写既有到期日字符串；之后的状态判断使用新时区。
- 周期推进只处理日历日期，不把日期转换为午夜 UTC，因此不受 DST 小时变化影响。

### 7.2 推进算法

| Frequency | 推进方式 | 边界例子 |
| --- | --- | --- |
| `WEEKLY` | 当前 due date 加 7 个日历日 | `2026-12-29 → 2027-01-05` |
| `MONTHLY` | 进入下一个月，使用 `anchor_on` 的日；目标月没有该日时取月末 | 锚点 31 日：`2027-01-31 → 2027-02-28 → 2027-03-31` |
| `YEARLY` | 进入下一年，使用 `anchor_on` 的月和日；不存在时取该月月末 | 锚点 `2028-02-29`：非闰年用 2 月 28 日，下一闰年恢复 2 月 29 日 |

不得直接对 `next_due_on` 做“加一个月后沿用已截断日”的运算，否则 31 日账单经过 2 月后会永久漂移到 28 日。

### 7.3 重设周期

PATCH 若改变 frequency 或下一到期日，必须同时提交两者。服务端：

1. 验证新的 next due date 晚于该模板最新已处理 due date。
2. 将 `anchor_on` 与 `next_due_on` 都设置为新的日期。
3. 从这个日期开始使用新 frequency。

例如月费改成年费时，提交 `YEARLY + 2027-01-15`；历史月费 occurrence 保持不变。

## 8. 汇总口径

所有汇总由后端使用 micros 计算，前端不得用 JavaScript `number` 重新求和。

### 8.1 周期小计

- `weekly_total_myr`：所有 active WEEKLY 模板的一期金额之和。
- `monthly_total_myr`：所有 active MONTHLY 模板的一期金额之和。
- `yearly_total_myr`：所有 active YEARLY 模板的一期金额之和。
- paused 模板不进入上述小计。

### 8.2 标准化年成本

```text
annualized = weekly_total × 52 + monthly_total × 12 + yearly_total
```

页面必须标为 **Annualized estimate**。它用于比较固定负担，不等同于任何特定自然年的精确到期总额，因为一个具体的 12 个月区间可能包含 52 或 53 个周费日期。

计划小计与 annualized estimate 都不写入 ledger，也不进入现有实际 Summary、Monthly report 或 Analytics。

## 9. 数据模型

### 9.1 `recurring_expenses`

新增表：

| 字段 | 类型 | 约束/用途 |
| --- | --- | --- |
| `id` | `String(32)` | UUID hex 主键 |
| `name` | `String(120)` | 显示名称及生成 event 的 description |
| `amount_myr` | `Integer` | MYR micros，`> 0` |
| `frequency` | `String(16)` | `WEEKLY`、`MONTHLY`、`YEARLY` |
| `anchor_on` | `String(10)` | 当前周期规则的锚点日期 |
| `next_due_on` | `String(10)` | 唯一待处理期次的日期 |
| `asset_id` | `String(32)` | FK → `assets.id`；业务层要求 active MYR |
| `funding_account_id` | `String(32)` | FK → `accounts.id`；业务层要求 open ASSET |
| `expense_account_id` | `String(32)` | FK → `accounts.id`；业务层要求 open EXPENSE |
| `category_id` | `String(32)` | FK → `categories.id`；业务层要求 active EXPENSE |
| `active` | `Boolean` | 默认 true |
| `created_at` | `String(40)` | UTC ISO 时间 |
| `updated_at` | `String(40)` | UTC ISO 时间 |

约束与索引：

- `CHECK amount_myr > 0`。
- `CHECK frequency IN ('WEEKLY','MONTHLY','YEARLY')`。
- `INDEX(active, next_due_on)` 支持页面默认排序与 overdue 统计。
- 不对 Name 建唯一约束。
- 外键不级联删除账本基础数据；本期没有 recurring expense DELETE API。

### 9.2 `recurring_expense_occurrences`

新增表：

| 字段 | 类型 | 约束/用途 |
| --- | --- | --- |
| `id` | `String(32)` | UUID hex 主键 |
| `recurring_expense_id` | `String(32)` | FK → `recurring_expenses.id` |
| `due_on` | `String(10)` | 被处理的本地到期日期 |
| `action` | `String(16)` | `RECORDED` 或 `SKIPPED` |
| `scheduled_amount_myr` | `Integer` | 处理当时的 MYR micros 快照，`> 0` |
| `event_id` | `String(32)` nullable | FK → `transaction_events.id`；RECORDED 必填且唯一 |
| `skip_reason` | `String(500)` nullable | 仅 SKIPPED 可填写 |
| `handled_at` | `String(40)` | 操作发生的 UTC ISO 时间 |

约束与索引：

- `UNIQUE(recurring_expense_id, due_on)`，作为服务端重试与并发请求的最终幂等保护。
- `UNIQUE(event_id)`，一个 event 最多对应一个 occurrence；SQLite 允许多个 NULL。
- `CHECK action IN ('RECORDED','SKIPPED')`。
- `CHECK scheduled_amount_myr > 0`。
- `CHECK ((action = 'RECORDED' AND event_id IS NOT NULL AND skip_reason IS NULL) OR (action = 'SKIPPED' AND event_id IS NULL))`。
- `INDEX(recurring_expense_id, due_on)` 支持最近历史查询；唯一约束已能覆盖时不重复创建等价索引。

### 9.3 不修改 `transaction_events` 表

首版通过 occurrence 的 `event_id` 关联实际交易，不在每个 transaction event 上新增 recurring 专用列。生成 event 已有的字段足以识别来源：

- `source = RECURRING_EXPENSE`。
- `external_id = recurring-expense:{recurring_expense_id}:{due_on}`。
- occurrence 提供严格的一对一反向关联和唯一性。

这样可保持核心账本表改动最小，也不会让普通事件承担无关字段。

## 10. 数据迁移

新增 `backend/migrations/versions/0007_recurring_expenses.py`：

1. `down_revision = "0006_event_receipts"`。
2. 先创建 `recurring_expenses`，再创建 `recurring_expense_occurrences`。
3. 建立上述 CHECK、UNIQUE、FK 和必要索引。
4. 不扫描历史事件，不猜测订阅，不插入示例模板。
5. 更新 migration head 测试，期望 revision 为 `0007_recurring_expenses`。

Downgrade 顺序相反。Downgrade 会删除固定开销模板与 occurrence 元数据，但已经生成的 ledger events 必须保留；执行前仍使用现有 pre-migration backup 流程。

不要修改可能已被使用的 `0005_categories.py` 或 `0006_event_receipts.py`，避免重写迁移历史。

## 11. API 设计

### 11.1 列表与汇总

`GET /api/recurring-expenses?include_inactive=false`

默认只返回 active；`include_inactive=true` 用于页面 All/Paused 筛选。响应由后端排序并提供权威汇总：

```json
{
  "as_of": "2026-09-07",
  "timezone": "Asia/Kuala_Lumpur",
  "summary": {
    "active_count": 3,
    "overdue_count": 1,
    "weekly_total_myr": "30",
    "monthly_total_myr": "1855.9",
    "yearly_total_myr": "299",
    "annualized_myr": "24129.8"
  },
  "items": [
    {
      "id": "...",
      "name": "房租",
      "amount_myr": "1800",
      "frequency": "MONTHLY",
      "anchor_on": "2026-09-01",
      "next_due_on": "2026-10-01",
      "due_status": "UPCOMING",
      "annualized_amount_myr": "21600",
      "asset_id": "...",
      "funding_account_id": "...",
      "expense_account_id": "...",
      "category_id": "...",
      "active": true,
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### 11.2 新建模板

`POST /api/recurring-expenses`

```json
{
  "name": "房租",
  "amount_myr": "1800",
  "frequency": "MONTHLY",
  "first_due_on": "2026-09-01",
  "asset_id": "myr-asset-id",
  "funding_account_id": "bank-account-id",
  "expense_account_id": "general-expense-account-id",
  "category_id": "housing-category-id"
}
```

- 成功返回 `201` 和 `RecurringExpenseRead`。
- 服务端将 `anchor_on`、`next_due_on` 都设为 `first_due_on`。
- first due date 可在过去；创建后立即显示 OVERDUE，但不自动处理。
- 服务端根据数据库实体校验资产、账户与分类，不能信任前端筛选。

### 11.3 编辑、暂停和恢复

`PATCH /api/recurring-expenses/{id}`

普通编辑：

```json
{
  "name": "新房租",
  "amount_myr": "1900",
  "funding_account_id": "new-bank-id",
  "category_id": "housing-category-id"
}
```

重设周期：

```json
{
  "frequency": "YEARLY",
  "next_due_on": "2027-01-15"
}
```

暂停或恢复：

```json
{ "active": false }
```

- 请求至少包含一个变更。
- `frequency` 与 `next_due_on` 在重设周期时必须一起出现。
- 重设时 `anchor_on = next_due_on`。
- 恢复前重新验证完整配置；配置已失效时返回 409 并要求先编辑。

### 11.4 记录当前一期

`POST /api/recurring-expenses/{id}/record`

```json
{
  "due_on": "2026-09-01",
  "occurred_at": "2026-09-01T08:30:00+08:00"
}
```

成功返回 `201`：

```json
{
  "occurrence": {
    "id": "...",
    "due_on": "2026-09-01",
    "action": "RECORDED",
    "scheduled_amount_myr": "1800",
    "event_id": "...",
    "event_status": "POSTED",
    "skip_reason": null,
    "handled_at": "..."
  },
  "recurring_expense": {
    "id": "...",
    "next_due_on": "2026-10-01"
  }
}
```

示例中的 `recurring_expense` 只节选了本次操作最关心的字段；实际响应返回完整 `RecurringExpenseRead`，避免维护第二套模板响应类型。

客户端必须提交当前看到的 due date。若另一窗口已经处理或重设周期，返回 409，不得替客户端处理新的下一期。

### 11.5 跳过当前一期

`POST /api/recurring-expenses/{id}/skip`

```json
{
  "due_on": "2026-09-01",
  "reason": "本月免租"
}
```

成功返回结构与 record 相同，但 occurrence action 为 `SKIPPED`、event_id 和 event_status 为 null。

### 11.6 处理历史

`GET /api/recurring-expenses/{id}/occurrences?limit=50`

- `limit` 范围 1～200，默认 50。
- 按 `due_on DESC, handled_at DESC` 返回。
- RECORDED 项附带当前 event status 和实际 `occurred_at`；SKIPPED 项不伪造 event 数据。
- 模板不存在返回 404。

### 11.7 统一错误语义

| HTTP 状态 | 场景 |
| --- | --- |
| `404` | 模板、asset、account 或 category 不存在 |
| `409` | 模板 paused、due date 已变化/已处理、恢复配置无效、重设日期不晚于历史 |
| `422` | 金额/日期/枚举格式错误，账户类型错误，非 MYR/inactive asset，inactive/wrong-kind category |

错误信息应指出具体字段和期望值，例如 `funding_account_id must reference an open ASSET account`，避免只返回“invalid configuration”。

## 12. 后端实现计划

### 12.1 枚举与 schema

- 在 `backend/app/enums.py` 增加 `RecurringFrequency` 和 `RecurringOccurrenceAction`。
- 在 `backend/app/schemas.py` 增加 create、update、record、skip、read、summary、list response 和 occurrence read schemas。
- 复用 `canonical_decimal`、`parse_decimal`、`myr_to_micros`、`micros_to_myr`，不新增第二套金额处理逻辑。
- create/update model validator 负责字段组合规则；数据库实体类型与 active/closed 校验由 service 完成。

### 12.2 模型与业务服务

- 在 `backend/app/models.py` 增加两个模型及最小必要 relationship。
- 新增 `backend/app/recurring_expenses.py`，集中放置配置校验、日期推进、列表汇总、record 和 skip 事务逻辑；日期边界逻辑不塞入 `api.py`。
- 复用 `create_draft` + `post_event` 生成账本 event；不要复制平衡校验、category 校验或审计逻辑。
- 如需让内部调用覆盖来源，以最小改动为 `create_manual_event` 增加 keyword-only 的 `source`/`external_id` 参数，公开的 manual API 仍固定为 MANUAL，不能让客户端伪造 source。
- record/skip 在 flush occurrence 的唯一约束失败时回滚并转换为 409。
- 审计 action 使用 `RECURRING_EXPENSE_CREATED`、`RECURRING_EXPENSE_UPDATED`、`RECURRING_EXPENSE_RECORDED`、`RECURRING_EXPENSE_SKIPPED`；details 保存模板 ID、due date 和变更字段，不保存不必要的敏感信息。

### 12.3 路由

- 在 `backend/app/api.py` 只保留请求解析、service 调用、commit/rollback 和响应序列化。
- 路由注册顺序把静态 `/recurring-expenses` 路径集中放置，避免与动态 `{id}` 路由混淆。
- 列表查询 eager-load 必需关系，避免逐行查询 asset/account/category。

## 13. 前端实现计划

### 13.1 API 与应用状态

- 在 `frontend/src/api.ts` 增加严格的 recurring expense 类型和对应请求方法，金额继续使用 string。
- `App.tsx` 增加 `fixed-expenses` View、导航项、列表 state 和 refresh 请求。
- record/skip 成功后刷新 recurring list、events、accounts、summary 和当前报表数据；普通编辑只需刷新 recurring list 及依赖显示数据。
- 若全局 refresh 继续一次加载过多资源，可在不改变现有行为的前提下为固定开销操作做最小的定向刷新；本期不重构全局数据层。

### 13.2 页面组件

- 新增 `frontend/src/FixedExpensesCenter.tsx`。页面逻辑足够独立，单独文件比继续扩大 `App.tsx` 更清晰。
- 使用现有 panel、metric、pill、form 和 table 样式；只在 `App.css` 增加固定开销页面所需的少量规则。
- 账户、资产和分类名称由现有已加载集合按 ID 映射；缺失引用显示 `Unavailable` 并禁用 Record，而不是崩溃。
- 日期输入用 `YYYY-MM-DD`，发生时间沿用 `localDateTimeValue()` 和现有 ISO 转换方式。
- Amount 仅作为字符串提交和格式化；所有合计直接显示服务端返回值。
- 最近历史中的 event ID 提供按钮：切换到 Transactions，并选中当前全局 event 列表中可找到的 event；若 event 超出当前 100 条，先通过现有 event detail API 获取后再选中，或首版显示明确的 ID 而不伪装成功跳转。

### 13.3 交互与可访问性

- 每个输入都有可见 label，状态不仅靠颜色区分。
- Record 和 Skip 的按钮文案包含当前 due date 或由相邻文本明确关联。
- loading 时禁用会重复提交的操作。
- 409 stale response 显示服务端错误并立即刷新该列表，防止用户继续操作旧 due date。
- 空状态分别覆盖“尚无模板”“筛选下无模板”“尚无处理历史”。

## 14. 测试计划

### 14.1 后端单元与 API 测试

新增 `backend/tests/test_recurring_expenses.py`，至少覆盖：

1. 创建 WEEKLY、MONTHLY、YEARLY 模板并按 due date 排序。
2. 名称清理、零/负数金额、无效 frequency 和无效日期。
3. 拒绝非 MYR 或 inactive asset。
4. 拒绝错误/关闭的 funding account、错误/关闭的 expense account。
5. 拒绝 INCOME 或 inactive category。
6. paused、overdue、due today、upcoming 状态使用 setting timezone 判定。
7. 周费跨年仍精确加 7 日。
8. 月费锚点 31 日经过 2 月后恢复 31 日；同时覆盖闰年 2 月 29 日。
9. 年费锚点 2 月 29 日在非闰年取 2 月 28 日并在闰年恢复。
10. Record 原子生成 POSTED EXPENSE event，检查 source、external_id、description、category 和两条 ledger entries。
11. Record 后实际 Summary/Monthly/Analytics 增加支出，未处理计划不增加支出。
12. 提前 Record 使用实际 occurred_at 进入对应报表期间，而不是 due date。
13. Skip 不生成 event，保存原因并正确推进日期。
14. 同一 due date 重复 Record、重复 Skip 以及 Record/Skip 竞态均返回 409 且不产生孤立 event。
15. 客户端 due date 已过期时返回 409，不能误处理新的 next due。
16. 修改金额/账户/分类只影响未来，历史 occurrence 金额和 event 不变。
17. 重设 frequency 要求 next due，日期必须晚于最新处理历史。
18. Pause 保留 next due；paused 不能 Record/Skip；恢复后状态正确。
19. 冲销已生成 event 后实际报表抵消、occurrence 显示 REVERSED、模板日期不回拨。
20. 周/月/年和 annualized 汇总全由后端精确计算，paused 项不计入。
21. occurrence history limit 边界、倒序和 event status 序列化。
22. migration head 更新为 `0007_recurring_expenses`，backup/restore 仍保留新增表数据。

日期推进函数使用纯 `date` 输入输出，可直接做快速单元测试，不通过 HTTP 才能验证每个边界。

### 14.2 前端测试

新增 `frontend/src/fixed-expenses.test.tsx`，至少覆盖：

1. 三种 frequency 的表单提交 payload。
2. 缺少 MYR asset、账户或分类时的禁用状态和引导。
3. Active/Paused/All 筛选及四种 due status 文案。
4. 服务端汇总金额原样显示，不在前端重新计算。
5. Record 使用当前 due_on 和实际 occurred_at，成功后触发刷新。
6. Skip 确认、可选原因和重复点击保护。
7. 编辑未来配置与重设 schedule 的字段组合。
8. 409 后展示错误并刷新，旧 due date 不再可提交。
9. 历史中的 RECORDED、SKIPPED、REVERSED 三种展示。
10. 窄屏关键字段仍可访问，按钮与 label 有可读名称。

同时运行现有 manual transaction、category、reporting、ledger 和 backup 回归测试，确认未改变既有入账口径。

## 15. 实施顺序与本地提交建议

### 阶段 0：确认前置基线

- 先完成当前工作区中的 category/receipt/analytics 变更和 `0005`、`0006` 迁移。
- 确认其测试通过并独立提交，不把已有未提交变更混入固定开销提交。

### 阶段 1：数据库与后端

- 增加 `0007` migration、ORM model、enum、schema、service、routes 和后端测试。
- 验证日期算法、原子入账、幂等、报表与 backup/restore。
- 建议提交：`Add recurring fixed expense backend`。

### 阶段 2：前端

- 增加 API 类型、应用 state/navigation、Fixed expenses 页面、样式和前端测试。
- 验证创建、编辑、暂停/恢复、Record、Skip、历史与错误状态。
- 建议提交：`Add fixed expense management UI`。

不为了遵循阶段名称拆分人工微提交；如果后端改动规模仍小，可将 migration、service、API 和对应测试放在同一个可审查提交中。

## 16. 验证命令

不执行 `npm.cmd install`。使用仓库现有环境：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .

cd ..\frontend
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

再做一次手工 smoke test：

1. 创建一项过去到期的月费，确认显示 OVERDUE 且实际报表不变。
2. Record 后确认出现一笔支出、账户余额与报表更新、下一到期日推进。
3. 创建一项周费并 Skip，确认没有交易且下一日期加 7 日。
4. Pause 后跨过到期日，再恢复并确认显示 OVERDUE。
5. 备份数据库并恢复到测试位置，确认模板、occurrence 和生成 event 均存在。

## 17. 验收标准

- 用户可以创建、编辑、暂停和恢复周费、月费、年费模板。
- 每个模板明确显示固定 MYR 金额、账户、分类、下一到期日和状态。
- 月末与闰年推进符合第 7 节规则，不发生 31 日永久漂移。
- 应用启动、刷新、跨日和读取列表都不会自动创建账本交易。
- Record 一次且只一次地生成平衡 POSTED EXPENSE event，并原子推进模板日期。
- Skip 保存处理记录、推进日期且不影响实际账本或报表。
- stale/重复请求返回 409，不产生重复或孤立 event。
- 未处理计划只出现在固定开销页面；现有 Overview、Reports、Analytics 仍只统计实际 ledger events。
- 编辑模板不修改既有 event 或 occurrence；冲销遵守现有不可变账本原则。
- 所有金额计算由后端用 micros 完成，前端不重新求和。
- 新表包含在 SQLite 和现有 Google Drive backup 中。
- 后端 pytest/ruff 与前端 test/lint/build 全部通过。
- 固定开销实现按逻辑边界本地提交，未推送远端，且不包含工作区中用户的其他改动。

## 18. 预计改动文件

| 文件 | 目的 |
| --- | --- |
| `backend/migrations/versions/0007_recurring_expenses.py` | 新增模板与 occurrence 表 |
| `backend/app/enums.py` | 新增 frequency/action 枚举 |
| `backend/app/models.py` | 新增 ORM models |
| `backend/app/schemas.py` | 新增 API contracts 与字段组合校验 |
| `backend/app/recurring_expenses.py` | 日期、验证、汇总、Record/Skip 业务逻辑 |
| `backend/app/ledger.py` | 仅在必要时允许内部调用设置受控 source/external_id |
| `backend/app/api.py` | 注册 recurring expense endpoints |
| `backend/tests/test_recurring_expenses.py` | 后端功能与边界测试 |
| `backend/tests/test_foundation.py` | migration head 期望更新为 0007 |
| `frontend/src/api.ts` | 类型和 API client |
| `frontend/src/App.tsx` | 导航、state、刷新与页面接线 |
| `frontend/src/FixedExpensesCenter.tsx` | 固定开销页面 |
| `frontend/src/App.css` | 最小必要响应式样式 |
| `frontend/src/fixed-expenses.test.tsx` | 前端交互测试 |

除上述范围外不重构账本、报表、卡交易、全局状态管理或 CSS 架构。
