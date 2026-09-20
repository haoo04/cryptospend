# 单账户资金流水页面开发计划

## 1. 目标

新增一个只读的 **Account ledger** 页面，让用户从 Accounts 或 Overview 中打开任意单个 account，查看该账户的当前账面余额、可用余额和完整资金变动历史。

本功能需要回答四个核心问题：

1. 这个账户当前持有哪些资产，各自账面余额和可用余额是多少；
2. 哪一笔交易在什么时间让哪种资产增加或减少；
3. 每笔变动完成后，该资产在此账户中的账面余额是多少；
4. 这笔变动对应哪个 transaction event、对方账户及冲销状态。

页面只展示账本事实，不在前端重新推导财务结果，不修改 ledger entry，也不新增记账入口。

## 2. 当前实现基线

### 2.1 后端

- `GET /api/accounts` 返回全部账户及 `balances`、`available_balances`，但没有单账户详情或流水接口。
- `GET /api/events/search` 是事件级搜索，支持关键词、事件类型、状态、分类、日期和分页；它不能按账户筛选，也不返回逐笔账户余额。
- `EventRead.entries` 已包含 account、asset、direction、quantity 和 book amount，可用于事件详情，但不能直接作为分页账户流水：
  - 一个 event 可以有多个 asset；
  - 同一个 account + asset 在一个 event 中可能有多条 entry，例如交易本金和手续费；
  - 只对某一页 events 做前端累计，会得到错误的 running balance。
- `account_balances()` 的余额口径是所有非 `DRAFT` event：原始 `REVERSED` event 与对应 `REVERSAL` event 都保留，因此冲销前后的历史可追踪且最终净额为零。
- quantity 以十进制字符串保存，MYR book amount 以整数 micros 保存；任何新查询都必须延续这一精度约束，不能通过 JavaScript number 或 SQLite 浮点计算余额。
- `ledger_entries.account_id`、`transaction_events.occurred_at` 已有索引。当前 local-first SQLite 使用场景不需要新增 migration。

### 2.2 前端

- 应用没有 URL router，页面通过 `App.tsx` 的 `View` state 切换。
- Accounts 页面已显示每个账户的余额卡片；Overview 也有 ASSET account 列表，二者都可以作为入口。
- Transactions 页面已有完整 event 详情、收据、重分类和冲销操作，Account ledger 不应复制这些写操作。
- 全局 Refresh 当前刷新 accounts、events 和 reports，但不会自动刷新一个新页面自己的分页请求。

## 3. 产品范围与导航

### 3.1 页面入口

- Accounts 每张 account 卡片增加 `View activity` 按钮。
- Overview 的账户行增加可访问的 `View activity for {account name}` 按钮或链接。
- 打开后记录 `selectedAccountId`，切换到新的 `account-ledger` view。
- Sidebar 仍将 Accounts 标记为 active，因为 Account ledger 是 Accounts 的下钻页面，不新增一级导航项。
- 页面顶部提供 `Back to accounts`，返回 Accounts 列表。
- 账户已关闭时仍可查看全部历史，并在标题区域显示 `Closed` 标记。

当前项目没有 router，本期继续使用现有 view state，不引入 React Router。刷新浏览器后回到默认 Overview 是已知行为；URL 深链接不在本期范围。

### 3.2 支持的账户

所有 account type 都可以打开：

- `ASSET`
- `LIABILITY`
- `INCOME`
- `EXPENSE`
- `EQUITY`
- `GAIN_LOSS`
- `CLEARING`

页面名称使用 `Account ledger`，而不是仅使用 `Cash flow`，避免把收入、费用、权益等账户误解成真实钱包或银行账户。

## 4. 会计与展示口径

### 4.1 一行流水的粒度

一行定义为同一个：

```text
account_id + event_id + asset_id
```

对应的净变动。

这样可以：

- 将同一 event 中相同 account + asset 的多条 entry 合并，避免任意的 entry 内部顺序影响 running balance；
- 对 trade 等多资产事件分别显示每种资产的变动；
- 仍以 event 为用户可理解的业务事实，并可跳转到原始 double-entry 明细。

如果合并后的净变动为零，仍保留该行，因为它代表真实账本活动；UI 显示 `No net change`，原始 entry 可在 event detail 中检查。

### 4.2 带符号变动

API 返回的 `quantity_change` 与 `book_amount_myr_change` 使用账户的自然余额方向，而不是简单把 DEBIT 永远显示为正数：

| Account type | 增加自然余额 | 减少自然余额 |
| --- | --- | --- |
| ASSET、EXPENSE、CLEARING | DEBIT | CREDIT |
| LIABILITY、INCOME、EQUITY、GAIN_LOSS | CREDIT | DEBIT |

这一规则必须与现有 `account_balances()` 完全一致。建议在 `backend/app/ledger.py` 提取一个很小的自然余额 sign helper，由余额汇总和账户流水共同使用，防止两处公式漂移。

前端直接展示服务端返回的有符号字符串：正数带 `+`，负数带 `−`，零值为中性色。对于非 ASSET 账户，正负表示“自然余额增加/减少”，不宣称是现金流入/流出。

### 4.3 Running balance

- `balance_after_quantity` 和 `balance_after_book_amount_myr` 表示该 event 的该 asset 变动全部完成后的账面余额。
- 余额按 `occurred_at ASC, created_at ASC, event_id ASC, asset_id ASC` 的稳定顺序计算，页面再以最新优先展示。
- Running balance 始终基于该账户的完整非草稿历史，不能因搜索、日期、资产筛选或分页而重置。
- 最后一笔历史变动后的余额必须与 `GET /api/accounts` 的 book balance 相同。
- `available_balances` 可能因 card hold 小于 book balance；hold 不是正式 ledger movement，因此流水的 running balance 只对应 book balance。页面需要用辅助文案明确这一点。

### 4.4 Event 状态和冲销

- `DRAFT` 不进入页面，也不参与余额。
- `POSTED` 正常显示。
- 被冲销的原 event 以 `REVERSED` 显示，其原始变动仍位于原发生时间。
- 对应 `REVERSAL` event 作为一笔反向变动显示在冲销发生时间。
- 原 event 与 reversal event 均提供关联 ID，UI 使用状态标记提示，但不隐藏任何一边。

该口径与不可变账本一致，并确保历史余额能解释当前余额。

## 5. 页面信息架构

### 5.1 Account header

标题区域展示：

- account name；
- account type、channel type、provider；
- Open / Closed 状态；
- `Back to accounts`；
- 页面局部 loading/error 状态。

### 5.2 Balance summary

按 asset 展示当前余额：

- `Book balance`：quantity + asset symbol，以及 MYR book amount；
- `Available balance`：只有与 book balance 不同时重点展示；
- 没有非草稿记录时显示 `No posted balance`；
- 当前余额始终为全部历史口径，不受下方筛选影响。

不把不同 asset 的 quantity 相加，也不新增未经定义的“账户总余额”。

### 5.3 筛选区

第一版支持：

- 关键词 `q`：匹配 description、event type、category、source、external/event ID、asset symbol 和对方账户名称；
- asset；
- event type；
- from date；
- to date；
- Clear；
- server-side result count 与分页，每页 50 条。

日期按 Settings 中的 timezone 解释，起止日均包含，后端使用 `[start, next_day_after_end)` 边界。`from_date > to_date` 时前端立即提示，后端仍返回 422 作为最终校验。

第一版不增加 status、category、金额范围和排序控件。状态不会被过滤掉，确保 reversal history 完整；更高级筛选可在有实际需求后再增加。

### 5.4 流水表

桌面端列为：

1. Date/time
2. Transaction（description + event type）
3. Other accounts
4. Asset
5. Quantity change
6. Book value change
7. Balance after
8. Status
9. Inspect

规则：

- `DATE_ONLY` event 只显示日期，`EXACT` event 按 API 返回的 timezone 显示日期与时间；
- Other accounts 是同一 event 中除当前 account 外的去重账户集合；复杂 event 不猜测唯一 payer/payee；
- Book value 明确标记为 MYR book value，不与 event transaction value 或 market value 混用；
- Balance after 同时显示 asset quantity 与该 asset 的 MYR book balance；
- 收据存在时可显示现有收据图标；
- `Inspect event` 调用现有 `GET /api/events/{event_id}`，进入 Transactions view 并复用已有 detail panel；
- 窄屏复用可横向滚动的 table 容器，不引入新的 UI library。

### 5.5 状态设计

- 首次加载：保留 account header，表格区域显示 `Loading account activity…`。
- 无任何流水：`No posted activity for this account yet.`
- 筛选无结果：`No account activity matches the current filters.`
- 请求失败：显示页面内联错误和 Retry，保留最后一次成功数据，避免整页消失。
- account 不存在：后端返回 404；页面显示 `Account not found` 和 `Back to accounts`。
- 快速切换筛选或分页：使用 request sequence 或 AbortController，旧响应不能覆盖新请求。
- 页码在筛选变化后重置为 1；如果刷新后当前页超过最后一页，自动加载新的最后一页。

## 6. API 设计

### 6.1 Endpoint

```http
GET /api/accounts/{account_id}/ledger
```

Query parameters：

| 参数 | 类型与默认值 | 说明 |
| --- | --- | --- |
| `q` | optional string，max 200 | 关键词搜索 |
| `asset_id` | optional string | 只看一种资产 |
| `event_type` | optional `EventType` | 只看一种 event type |
| `from_date` | optional `YYYY-MM-DD` | Settings timezone 中的包含起始日 |
| `to_date` | optional `YYYY-MM-DD` | Settings timezone 中的包含结束日 |
| `page` | int，default 1，min 1 | 页码 |
| `page_size` | int，default 50，1..100 | 每页行数 |

未知 account 返回 404；合法但无记录返回 200 和空 `items`。

### 6.2 Response contract

```json
{
  "account": {
    "id": "bank-id",
    "name": "Bank",
    "account_type": "ASSET",
    "channel_type": "BANK",
    "provider": "Example Bank",
    "closed": false,
    "balances": [
      {
        "asset_id": "myr-id",
        "asset_symbol": "MYR",
        "quantity": "974.5",
        "book_amount_myr": "974.5"
      }
    ],
    "available_balances": [
      {
        "asset_id": "myr-id",
        "asset_symbol": "MYR",
        "quantity": "974.5",
        "book_amount_myr": "974.5"
      }
    ]
  },
  "timezone": "Asia/Kuala_Lumpur",
  "items": [
    {
      "event_id": "event-id",
      "event_type": "EXPENSE",
      "event_status": "POSTED",
      "occurred_at": "2026-09-21T04:00:00+00:00",
      "time_precision": "EXACT",
      "description": "Lunch",
      "category": "Food",
      "source": "MANUAL",
      "reverses_event_id": null,
      "reversed_by_event_id": null,
      "asset_id": "myr-id",
      "asset_symbol": "MYR",
      "quantity_change": "-25.5",
      "book_amount_myr_change": "-25.5",
      "balance_after_quantity": "974.5",
      "balance_after_book_amount_myr": "974.5",
      "entry_count": 1,
      "counterparties": [
        {
          "account_id": "expense-id",
          "account_name": "General Expense",
          "account_type": "EXPENSE"
        }
      ],
      "receipt_attached": true
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

所有 decimal 和 MYR 值继续使用 JSON string；前端不得转成 `number` 后再计算或格式化高精度 quantity。

### 6.3 Schema

在 `backend/app/schemas.py` 增加最少的 read models：

- `AccountLedgerCounterpartyRead`
- `AccountLedgerItemRead`
- `AccountLedgerPageRead`

前端 `frontend/src/api.ts` 增加对应 TypeScript types、`AccountLedgerFilters`、`api.accountLedger(accountId, filters)` 和对现有 event detail endpoint 的 `api.event(id)` 封装。

## 7. 后端实施方案

### 7.1 账户流水计算

在 `backend/app/ledger.py` 增加一个聚焦的账户流水查询函数，不新增 service class 或通用 repository：

1. 查询目标 account；不存在则抛出 404。
2. 一次读取该 account 的全部非 `DRAFT` ledger entries，并预加载 event、asset、category、receipt 和 event 的其他 account entries。
3. 以 `(event_id, asset_id)` 聚合当前 account 的 entries：
   - quantity 使用 `Decimal`；
   - book amount 使用 integer micros；
   - 使用共享自然余额 sign helper 计算净变动；
   - counterparty accounts 去重并按名称稳定排序。
4. 按发生时间正序计算每个 asset 独立的 running quantity 与 running MYR book amount。
5. 完成 running balance 后再应用关键词、asset、event type 和日期筛选，保证筛选不会改变历史余额。
6. 结果按发生时间倒序、稳定 tie-breaker 排序后计算 `total` 和分页。
7. 用 `canonical_decimal()` 和 `micros_to_myr()` 序列化，绝不经过 float。

选择先计算完整账户历史再筛选，是因为 quantity 当前以 Text 保存，SQLite 的 `CAST`/window sum 不能保证与 Python `Decimal` 相同的精度；同时现有 `account_balances()` 本来就会扫描 ledger。对于本地个人账本，这是比引入快照表或复杂 SQL 更简单且可靠的第一版。

### 7.2 Account 与 available balance

- 复用 `account_balances()` 和 `available_account_balances()` 生成 response 中的 account summary；
- 若实现时抽取 `account_read()` 可减少 `/accounts` 与新 endpoint 的重复序列化，但只保留这一个小 helper，不引入新的 DTO 层；
- 用测试断言每个 asset 的最后一个 running balance 与 account summary 相等；
- available balance 继续由 active card holds 调整，不混入 ledger running balance。

### 7.3 日期和搜索

- 日期边界复用 `/events/search` 的 Settings timezone 规则；可将现有边界计算提取为一个小函数供两个 endpoint 使用。
- 搜索大小写不敏感；空白 query 视为未筛选。
- 搜索仅匹配已加载的明确字段，不做模糊金额解析。
- counterparty 搜索使用同一 event 的其他账户名称；不要把复杂复式分录强行归类为单一 source/destination。

### 7.4 性能与 migration

- 不新增数据库表、字段、第三方依赖或 migration。
- 依赖现有 `ledger_entries.account_id` 索引先缩小到单个账户。
- 页面大小固定默认 50，上限 100。
- 实施时用包含多资产、手续费和至少数千行账户变动的 fixture 做一次人工响应时间检查；不加入脆弱的毫秒级 CI 断言。
- 如果未来单账户历史达到明显影响交互的规模，再单独规划余额快照或精确 decimal 聚合方案；本期不做预优化。

## 8. 前端实施方案

### 8.1 页面组件

新增 `frontend/src/AccountLedger.tsx`，因为该页面包含独立请求、筛选、分页、错误和竞态状态，放入已经较大的 `App.tsx` 会降低可读性。它只是一个页面组件，不新增状态管理层或组件框架。

组件接收：

- `accountId`
- `assets`
- `refreshVersion`
- `onBack`
- `onInspectEvent`

组件自己维护草稿筛选、已应用筛选、page、response、loading 和 error。财务数值完全采用 API response，不在浏览器累计余额。

### 8.2 App 集成

在 `frontend/src/App.tsx`：

1. `View` 增加 `account-ledger`；
2. 增加 `selectedAccountId` 和简单的 `openAccountLedger(id)`；
3. Accounts 与 Dashboard 传入同一个打开回调；
4. Account ledger 时 Sidebar 的 Accounts 保持 active；
5. topbar title 使用选中账户名称或 `Account activity`；
6. 全局 Refresh 成功后递增 `refreshVersion`，当前 Account ledger 以原筛选和页码重新请求；
7. `onInspectEvent` 先调用 `api.event(eventId)`，成功后设置现有 `selected` 并进入 Transactions；失败时留在当前页并显示反馈。

不要把账户流水塞入现有全局 `events` 数组；该数组仍服务 Overview 和 Reports 的最近事件用途。

### 8.3 样式与可访问性

在 `frontend/src/App.css` 中复用现有：

- panel、section-title、pill、button、input；
- table-wrap 横向滚动；
- transaction filters 与 pagination 的布局思路。

只增加 Account ledger 必需的 header、balance summary、change colors 和响应式规则。

可访问性要求：

- View activity 与 Inspect event 都有包含上下文的 accessible name；
- 筛选项使用真实 label；
- loading 使用 `role="status"`，错误使用 `role="alert"`；
- 正负变化不能只依赖颜色，文本中必须有 `+` / `−`；
- Back、Retry、分页和筛选均可键盘操作；
- account card 不把整个 `<article>` 变成不可访问的伪按钮。

## 9. 测试计划

### 9.1 后端测试

在 `backend/tests/test_ledger.py` 增加聚焦测试，覆盖：

1. 未知 account 返回 404；
2. 无流水 account 返回账户资料、timezone、空 items 和 total 0；
3. ASSET/EXPENSE/CLEARING 的 DEBIT 为正、CREDIT 为负；
4. LIABILITY/INCOME/EQUITY/GAIN_LOSS 的 CREDIT 为正、DEBIT 为负；
5. 同 event + account + asset 的多 entry 合并为一行；
6. 同 event 的多个 asset 分成多行，各自维护 running balance；
7. counterparty accounts 正确去重且不包含当前 account；
8. `REVERSED` 原 event 与 `REVERSAL` 都可见，最终余额抵消；
9. `DRAFT` 不可见且不参与 running balance；
10. 搜索覆盖 description、type、category、source、ID、asset 和 counterparty；
11. asset、event type、配置时区日期边界和组合筛选正确；
12. 筛选与翻页不会重置 `balance_after_*`；
13. total、page、page_size 与稳定排序正确；
14. `from_date > to_date` 和非法分页参数返回 422；
15. 大数量和多位小数没有 float 精度损失；
16. 每种 asset 的最终 running balance 与 AccountRead balance 一致；
17. active card hold 只改变 available balance，不改变 ledger running balance。

### 9.2 前端测试

新增 `frontend/src/account-ledger.test.tsx`，覆盖：

1. account metadata、closed 状态、book/available balances 正确显示；
2. 页面加载时使用 account ID、page 1 和 page size 50；
3. 正、负、零变动和 balance after 使用 API 字符串正确显示；
4. asset、type、关键词和日期筛选请求正确，Apply/Clear 会重置页码；
5. 分页 count、Previous/Next 和边界禁用正确；
6. 无历史与筛选无结果使用不同文案；
7. 失败保留最后成功数据，并可 Retry；
8. 较旧请求不会覆盖较新筛选结果；
9. Inspect event 传出正确 event ID；
10. `DATE_ONLY` 与 `EXACT` 使用 response timezone 展示；
11. available 与 book 相同时不制造重复噪音，不同时明确显示；
12. Account 卡片和 Overview 行均能打开对应 account；
13. 全局 Refresh 会按当前筛选重新加载当前账户页面；
14. 键盘可操作，状态与错误具有正确的 ARIA role。

### 9.3 验证命令

```powershell
npm.cmd --prefix frontend run test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
Set-Location backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

不执行 `npm.cmd install`；依赖缺失时由用户按项目约定手动安装。

## 10. 实施顺序

### 阶段 A：后端契约与余额语义

1. 增加 read schemas；
2. 提取自然余额 sign helper，并让现有 account balance 使用它；
3. 实现 account + event + asset 聚合及 running balance；
4. 增加 `/accounts/{account_id}/ledger` route；
5. 完成后端测试，先锁定精度、冲销和筛选口径。

### 阶段 B：前端 API 与页面

1. 增加 TypeScript contract 与 API client；
2. 实现 AccountLedger 页面本体；
3. 完成筛选、分页、loading/error/empty states；
4. 完成 event inspect 衔接。

### 阶段 C：导航、刷新与视觉收尾

1. 接入 Accounts 与 Overview；
2. 接入 topbar、sidebar active 和全局 Refresh；
3. 增加响应式与可访问性样式；
4. 完成前端测试和全量回归。

## 11. 预计文件影响

| 文件 | 变更 |
| --- | --- |
| `backend/app/schemas.py` | Account ledger response models |
| `backend/app/ledger.py` | 自然余额 sign、event + asset 聚合、running balance 与筛选 |
| `backend/app/api.py` | 新增单账户 ledger endpoint 与 account response 组装 |
| `backend/tests/test_ledger.py` | 精度、冲销、筛选、分页和余额一致性测试 |
| `frontend/src/api.ts` | Account ledger types/client 与 event detail client |
| `frontend/src/AccountLedger.tsx` | 新页面、筛选、分页和状态处理 |
| `frontend/src/App.tsx` | view、入口、返回、Inspect 和 Refresh 集成 |
| `frontend/src/App.css` | 页面布局、变化值和响应式样式 |
| `frontend/src/account-ledger.test.tsx` | 页面行为与导航测试 |

不修改 models、数据库 migration、依赖文件或现有账本写入流程。

## 12. 验收标准

- 用户可从 Accounts 和 Overview 打开正确的单账户流水页面并返回。
- 页面支持所有 account type，包括 closed account。
- 当前 book/available balance 与账户列表一致，并明确 available balance 可能受 hold 影响。
- 每一行代表一个 event + asset 的账户净变动，多资产事件不会混成一个金额。
- 正负号遵循账户自然余额，所有 decimal 保持精确字符串语义。
- 每行 balance after 基于完整非草稿历史，筛选和分页不会改变它。
- `REVERSED` 原记录与 `REVERSAL` 都可追溯，最终余额正确抵消。
- 关键词、asset、event type、日期和分页在服务端生效，日期使用 Settings timezone。
- 用户可以从流水行进入现有 transaction event detail，不复制写操作。
- 空数据、无匹配、404、请求失败、快速切换和超出页码均有稳定行为。
- 桌面与窄屏可用，键盘和辅助技术可以识别控件与状态。
- frontend test/lint/build 与 backend pytest/ruff 全部通过。

## 13. 非目标

- 在账户流水页面新增、编辑、删除或直接修改 ledger entry；
- 导出 CSV/PDF 或打印银行对账单；
- 市场价值、未实现盈亏或实时行情；
- pending card authorization 伪装成正式 ledger movement；
- 对账、外部 statement import 或余额校准；
- 自定义排序、金额范围、category/status 高级筛选；
- URL deep link、浏览器前进/后退路由或新增 router；
- balance snapshot、cursor pagination 或数据库层 decimal window aggregation；
- 修改现有 Transactions 搜索结果的语义。

## 14. 建议提交拆分

实现时建议两个本地提交，便于分别审查财务契约与 UI：

1. `Add account ledger API`
   - schemas、ledger query、route、backend tests；
2. `Add account ledger page`
   - frontend API、页面、导航、样式、frontend tests。

计划文档本身单独提交。所有提交仅保存在本地，不推送远程；暂存时只选择本功能文件，避免带入工作区现有未跟踪文件。
