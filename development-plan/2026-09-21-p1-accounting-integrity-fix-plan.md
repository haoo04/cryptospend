# CryptoSpend P1 记账完整性修复计划

> 制定日期：2026-09-21
>
> 来源：[前后端与记账流程审查报告](./2026-09-21-project-audit.md)
>
> 覆盖范围：CS-01 至 CS-05
>
> 本文是实施计划，不包含业务代码修改。

## 1. 目标与边界

### 1.1 本轮目标

本轮只处理可能保存错误会计事实、错误卡片状态，或无法准确表达合法卡片流水的 P1 问题：

1. 封闭所有可绕过 FIFO cost lot/disposal/transfer 的通用录入入口。
2. 确保 linked card settlement 只能结算它所关联的授权。
3. 确保累计退款不超过原购买，并由服务器推导退款状态。
4. 确保数量、MYR 账面值和估值汇率只有一个权威关系。
5. 让卡片界面能够提交后端已经支持的多资金腿、多退款腿和多费用。
6. 在改变写入规则前，以只读方式识别可能已经受影响的历史记录。

### 1.2 明确不在本轮处理

- 不重做整体 UI 视觉设计。
- 不处理报表柱状图、全局时区、搜索竞态、Journey 和金额格式等 P2 项目。
- 不新增第三方状态管理、表单、Decimal 或数据迁移依赖。
- 不自动改写历史总账、cost lot、disposal 或退款事件。
- 不在 P1 阶段实现多次 partial capture。linked authorization 暂时只允许一次 final capture；完整的 partial capture 模型另行规划。
- 不改变现有 FIFO 计算方法、复式分录方向或报表定义，除非是修复本计划明确列出的错误状态。

### 1.3 成功标准

完成后必须同时满足：

- 任意公开 API 都不能保存没有相应 cost projection 的非 MYR 资产减少或账户间转移。
- linked settlement 的身份字段不能由客户端换成另一笔卡片交易。
- 活跃退款的交易价值合计永远不大于原购买价值。
- `PARTIALLY_REFUNDED`/`REFUNDED` 不再由客户端布尔值决定。
- acquisition/reward 的 rate 由服务器从 quantity 和 MYR value 推导；客户端无法保存矛盾值。
- 卡片表单能提交 1..N 个 funding/refund/fee rows，并向用户显示合计校验。
- 所有拒绝路径都具有“零副作用”：不产生 event、lot、disposal、hold 更新或部分状态更新。

## 2. 复核后的补充发现

原审查报告聚焦手工表单，但代码复核显示旁路范围更大，实施时必须一起处理。

### 2.1 通用 draft/post API 是另一个旁路

`POST /api/events/drafts` 接收任意 `EventType` 和任意 entries，`POST /api/events/{id}/post` 只检查平衡、数量非负和类别绑定：

- `backend/app/api.py:753-770`
- `backend/app/ledger.py:75-158`
- `backend/app/schemas.py:243-280`

它没有执行 trade disposal、transfer lot move、card disposal 或相应身份校验。前端没有调用这两个路由，只有 `backend/tests/test_ledger.py` 使用。因此 P1 修复不能只隐藏前端选项；应移除这两个公开路由，并保留 `create_draft()`/`post_event()` 作为专用后端服务的内部构建块。

### 2.2 非 MYR ADJUSTMENT 也会破坏 cost projection

手工 `ADJUSTMENT` 可以让 ASSET 账户借记或贷记非 MYR 资产，但 `create_event_acquisition_lots()` 不为 adjustment 建 lot，也不会做 disposal。因此 P1 阶段只允许 MYR adjustment。若以后需要库存盘盈/盘亏，应建立专用 adjustment 命令，并明确 lot 取得成本或 FIFO disposal 规则。

### 2.3 来源字段不能可靠识别历史手工事件

`EventDraftCreate.source` 默认是 `MANUAL`，现有 trade、transfer 和 card service 创建 draft 时也没有覆盖它。因此历史审计不能只筛选 `transaction_events.source = 'MANUAL'`，必须根据 event type、专用业务表、lot/disposal/transfer 记录和 ledger entries 交叉判断。

### 2.4 退款撤销也必须使用服务器推导状态

当前创建退款时直接读取 `full_refund`；撤销退款时则只根据“是否还有其他退款”设置原购买状态：`backend/app/cards.py:526`、`backend/app/cost_basis.py:318-333`。存在其他退款不代表仍有未退余额。因此创建和撤销必须复用同一个退款状态重算函数。

## 3. 修复后必须保持的领域不变量

这些不变量是服务端规则，不依赖前端是否隐藏字段。

### INV-01：非 MYR 资产减少必须有成本去向

任何 posted event 中，ASSET account 的非 MYR CREDIT quantity 都必须满足以下一种情况：

- 对应 active `LotDisposal`，表示消费、出售或费用；或
- 对应 active `LotTransfer`，表示自有账户之间移动；或
- 是 reversal 对原 projection 的成对恢复。

### INV-02：非 MYR 资产取得必须有成本批次

任何 acquisition event 中，ASSET account 的非 MYR DEBIT quantity 都必须对应一个 active `CostLot`，且：

- lot original quantity 等于 entry quantity；
- lot basis 等于 entry book amount micros；
- lot source event 等于该 event。

### INV-03：MYR 数量与账面金额相等

规范 MYR 资产的 `quantity` 必须等于 `book_amount_myr` 的十进制值。不能只依赖前端把两者设置成同一个字符串。

### INV-04：linked settlement 身份不可漂移

linked settlement 和 authorization 的以下字段必须一致：

- provider：去除首尾空白后按大写比较；
- provider account ID：精确比较；
- card account ID：精确比较；
- merchant name：去除首尾空白、合并连续空白并 case-insensitive 比较；
- merchant country：按大写比较；
- merchant asset ID：精确比较；
- billing asset ID：精确比较。

允许变化的字段只有实际 settled 时间、external settlement ID、merchant/billing 最终金额、MYR value、funding legs、fees、expense category 和参考汇率。

### INV-05：P1 阶段一笔授权最多一个 final settlement

- 有 `authorization_id` 时，`final_capture` 必须为 true。
- 已有 active child PURCHASE 的授权不得再次结算。
- 只有 `AUTHORIZED` 状态可以进入 linked settlement。
- 成功结算后授权为 `SETTLED`，hold 为 `RELEASED`。
- 现存 `PARTIALLY_SETTLED` 授权由 AUD-08 列出，并在人工核对前拒绝继续 capture；不能一边收口新规则，一边让旧的不完整状态继续写入。

这是无数据库迁移的安全收口。未来需要 multi-capture 时，应先为 capture 保存明确的 final/sequence/authorized remaining 状态，再重新开放。

### INV-06：退款上限和状态由服务器推导

定义：

```text
active_refunded_myr = Σ active REFUND.merchant_value_myr
refundable_remaining_myr = PURCHASE.merchant_value_myr - active_refunded_myr
```

- 新退款的 transaction value 合计不得大于提交前的 `refundable_remaining_myr`。
- 剩余值为 0 时状态是 `REFUNDED`；大于 0 时是 `PARTIALLY_REFUNDED`；无活跃退款时是 `SETTLED`。
- 计算使用整数 MYR micros，不使用 float，也不需要模糊 tolerance。
- refund legs 的 `reference_value_myr` 继续只用于经济成本报告，不用于退款上限。

### INV-07：rate 是派生值，不是第三个独立事实

对非 MYR acquisition/reward：

```text
authoritative_value_myr = micros_to_myr(myr_to_micros(input_value_myr))
derived_rate = authoritative_value_myr / quantity
```

- quantity 和 value 必须大于 0。
- 全程使用 `Decimal`；MYR 只在 micros 边界按 HALF_EVEN 舍入。
- 保存的 entry rate 和 RateSnapshot rate 使用服务器派生值。
- 兼容期内若旧客户端仍传 `valuation_rate`，要求 `myr_to_micros(quantity × supplied_rate)` 等于权威 value micros；否则返回 422。
- MYR entry 不保存 RateSnapshot。

## 4. P1-0：历史数据只读审计与备份门禁

这一工作必须先完成，因为新规则只能阻止未来错误，不能证明现有数据库已经一致。

### 4.1 实施方式

在现有 `backend/app/maintenance.py` 增加只读命令：

```powershell
backend\.venv\Scripts\python.exe -m app.maintenance audit-integrity --database backend\data\cryptospend.db
```

命令要求：

- 使用 SQLite URI `mode=ro` 打开目标数据库，不复用会设置 WAL 的应用 engine；不执行 UPDATE/DELETE/INSERT。
- 输出人类可读摘要，并可通过 `--json <path>` 保存机器可读结果。
- 无问题时 exit code 0；发现需要人工确认的问题时 exit code 2；命令或数据库错误时 exit code 1。
- 每条结果至少包含 issue code、event/card ID、occurred time、asset/account、quantity/value 和判断依据。
- 不显示或写出凭据、DPAPI 内容或收据文件。

### 4.2 审计规则

| 审计编号 | 查询目标 | 判定规则 |
| --- | --- | --- |
| AUD-01 | 未投影的非 MYR 资产减少 | posted、非 reversal 的 ASSET CREDIT，没有 active disposal/transfer 覆盖相同 event/asset/account/quantity |
| AUD-02 | 缺失 acquisition lot | acquisition 类型的 ASSET DEBIT，没有相同 source event/asset/account/quantity/basis 的 active lot |
| AUD-03 | lot 与 ledger 数量不一致 | 按 account+asset 汇总 active lots remaining quantity，与有效 ledger balance 不相等 |
| AUD-04 | 矛盾 valuation rate | entry 有 rate，`quantity × rate` 舍入 micros 后不等于 entry book amount |
| AUD-05 | 错误授权关联 | PURCHASE 有 parent authorization，但 INV-04 身份字段不一致 |
| AUD-06 | 超额退款 | active refund transaction values 合计大于原 purchase merchant value |
| AUD-07 | 退款状态不一致 | 按 INV-06 推导状态与保存状态不同 |
| AUD-08 | partial capture 历史 | authorization 状态为 `PARTIALLY_SETTLED`，或存在多个 active child purchases |

AUD-01 的实现不能简单要求每个 MYR CREDIT 也有 disposal；MYR lot 政策目前仍沿用现有行为，本轮重点是非 MYR 成本完整性。

### 4.3 历史问题处理原则

1. 先使用现有 backup API 创建数据库备份并通过 integrity check。
2. 保存 audit JSON，作为修复前基线。
3. 若 AUD-01/AUD-02/AUD-03 命中，不自动生成 lot 或 disposal；成本和时间顺序存在歧义，应按发生时间通过 reversal + 正确专用流程重录。
4. AUD-04 不覆盖原始 event。若 lot 尚未使用，可 reversal 后重录；若已使用，新增当前时点的正确 RateSnapshot，并保留审计说明，历史报表修复另案处理。
5. AUD-06 不删除退款。逐笔确认后反转错误 refund，再按正确金额重录。
6. AUD-07 在所有金额核对完成后可以重算状态；状态修正必须写 audit log，但不能改变 ledger entries。
7. 所有历史人工处理完成后再次运行 audit，保存 after JSON。

### 4.4 P1-0 测试

- 用临时 SQLite 构造每个 AUD 规则一个命中和一个不命中样本。
- 验证 audit 前后各表 row count 和数据库文件 hash/mtime 行为不发生写入性变化。
- 验证 exit code 0/1/2 和 JSON schema。
- 继续保留现有 backup/restore/integrity-check 测试。

## 5. P1-1：封闭手工记账和通用 draft 旁路（CS-01）

### 5.1 目标命令矩阵

| Manual event type | 允许资产 | Debit account | Credit account | 成本行为 |
| --- | --- | --- | --- | --- |
| `SALARY` | MYR 或非 MYR | ASSET | INCOME | 非 MYR 建 acquisition lot |
| `INCOME` | MYR 或非 MYR | ASSET | INCOME | 非 MYR 建 acquisition lot |
| `OPENING_BALANCE` | MYR 或非 MYR | ASSET | EQUITY | 非 MYR 建 acquisition lot |
| `EXPENSE` | 仅 MYR | EXPENSE | ASSET | 不涉及非 MYR FIFO |
| `ADJUSTMENT` | 仅 MYR | 现有允许矩阵内的账户 | 现有允许矩阵内的账户 | 不涉及非 MYR lot |
| `TRANSFER` | 不允许 | — | — | 使用 `/api/transfers` |
| `TRADE`/card/refund/reward/fee/reversal | 不允许 | — | — | 使用各自专用 service |

所有 manual quantity/book amount 必须大于 0；MYR 必须满足 INV-03。

`ADJUSTMENT` 的“现有允许矩阵”需要在后端明确写死：debit 只允许 ASSET/EXPENSE/LIABILITY/CLEARING，credit 只允许 ASSET/INCOME/EQUITY/GAIN_LOSS/CLEARING；debit 与 credit account 不能相同。若绑定类别，仍沿用“恰好一个 INCOME 或 EXPENSE account”的现有类别规则。

### 5.2 后端改动

`backend/app/schemas.py`

- 给 `ManualEventCreate` 增加 event type 白名单校验。
- 将 `valuation_rate` 改为兼容期 optional，不再作为权威输入。
- quantity 和 book amount 从“非负”改成“正数”。

`backend/app/ledger.py`

- 在构造 draft 前验证 event type、账户类型矩阵、资产限制和 MYR quantity/value 一致性。
- 对非 MYR acquisition 计算派生 rate，并要求 valuation source 非空。
- 错误在创建 `TransactionEvent` 前抛出，保证零副作用。
- 不把通用限制放进 `post_event()`，避免破坏 trade/card/transfer service 内部构建的合法多分录事件。

`backend/app/api.py`

- 删除公开的 `POST /events/drafts` 和 `POST /events/{event_id}/post` 路由。
- 保留 `create_draft()` 与 `post_event()` 供后端专用流程调用。
- API 文档中不再暴露可任意提交 entries 的入口。

### 5.3 前端改动

`frontend/src/App.tsx`

- 从 Manual event type 下拉中移除 `TRANSFER`；顶部已有专用 Transfer tab。
- `EXPENSE`/`ADJUSTMENT` 时资产选择器只显示规范 MYR。
- 非 MYR `SALARY`/`INCOME`/`OPENING_BALANCE` 保留 quantity、book amount、valuation source；rate 改为只读派生预览，不发送为权威值。
- MYR 继续只显示一个 amount 字段。
- 选择 event type 后若当前 asset 不再合法，清空 asset/quantity/rate，避免隐藏旧值被提交。

### 5.4 错误响应

建议保持现有 `DomainError` 格式和 422 状态，错误文本应指出替代入口，例如：

- `manual TRANSFER is not supported; use /transfers`
- `non-MYR EXPENSE requires a disposal-aware flow`
- `non-MYR ADJUSTMENT is not supported`
- `manual SALARY requires ASSET debit and INCOME credit`
- `MYR quantity must equal book amount`

### 5.5 兼容性说明

- 前端没有使用 generic draft/post 路由；代码搜索只发现后端测试，因此移除它们不影响当前 UI。
- 原 `test_unbalanced_draft_cannot_be_posted` 改为 service 层测试 `post_event()` 的不平衡拒绝，保留核心保护但不再公开任意分录 API。
- 现有使用 manual MYR `TRANSFER` 的测试和调用改用 `/api/transfers`；测试 fixture 必须先在来源账户建立足够的 MYR lot，不能继续依赖允许来源余额变负的旧旁路。
- 现有非 MYR salary/opening balance 继续工作，并得到服务器派生 rate。

## 6. P1-2：锁定授权与结算关系（CS-02）

### 6.1 最小安全策略

P1 不增加 capture 表或数据库列。linked authorization 采用“一次 final settlement”策略：

1. 读取 authorization，并要求状态严格等于 `AUTHORIZED`。
2. 在创建任何 draft/disposal 前执行 INV-04 全字段身份比较。
3. 拒绝 `final_capture = false`。
4. 查询是否已有未撤销 child PURCHASE；有则返回 409。
5. 金额允许与 authorization 不同，因为真实结算可能变化。
6. 成功提交 event、disposal 和 card transaction 后，再把 authorization/hold 更新为最终状态；仍在同一数据库事务内。
7. `PARTIALLY_SETTLED` 历史授权直接返回 409，并给出需要先运行 integrity audit 的错误提示。

### 6.2 后端改动

`backend/app/cards.py`

- 新增一个小型、纯验证函数用于 authorization/settlement identity；不要建立新的 service class。
- 校验必须发生在 `plan_fifo()` 和 `post_event()` 之前。
- linked mismatch 返回 409，错误包含第一个不一致字段，但不回显敏感 provider account 完整内容。
- linked settlement 强制 final capture，并检查 active child purchase。
- manual settlement（没有 authorization ID）保留当前输入能力。

`backend/app/api.py::card_read()`

扩充 card response，使 UI 不需要新 endpoint 即可自动填充：

```text
provider_account_id
card_account_id
merchant_country
expense_account_id       # PURCHASE 时从原 event 的 merchant expense entry 推导
refunded_value_myr       # 按 active refund transaction values
refundable_remaining_myr # PURCHASE 才有
```

`expense_account_id` 的推导规则应匹配原 settlement event 中：DEBIT、EXPENSE account、merchant asset、merchant quantity 和 merchant value 的 entry；找不到唯一匹配时返回 null，并阻止自动退款而不是猜测。

### 6.3 前端改动

`frontend/src/api.ts`

- 给 `CardRecord` 加上上述字段，避免继续使用 `Record<string, unknown>` 猜测响应。

`frontend/src/CardCenter.tsx`

- 保存 `selectedAuthorizationId`，从现有 cards 列表取得 authorization。
- 选中后显示只读身份摘要，并自动填充 provider/account/card/merchant/country/assets。
- merchant amount、billing amount 和 merchant value 以授权值作为默认值，但保持可编辑。
- 隐藏 partial/final checkbox，linked settlement 固定发送 `final_capture: true`。
- 切回 Manual settlement 时恢复可编辑身份字段。
- 切换 authorization 时以 authorization ID 作为相关 fieldset 的 React key，避免 uncontrolled input 保留上一个授权值。

### 6.4 不采用的方案

- 不只在前端禁用字段：API 仍可被直接调用。
- 不在 P1 中增加可配置的授权金额 tolerance：授权和最终结算金额本来就可能不同，身份验证与金额差异应分开。
- 不复用 `external_id` 判断同一交易：authorization 和 settlement 通常有不同 external ID。

## 7. P1-3：服务器控制退款额度和状态（CS-03）

### 7.1 简化目标请求

当前请求中的以下字段删除或停止作为输入：

- `refund_value_myr`：由所有 refund legs 的 `transaction_value_myr` 合计得到。
- `expense_account_id`：从原 purchase event 唯一匹配的 merchant expense entry 得到。
- `full_refund`：由服务器按剩余额度推导。

目标请求仅保留：

```json
{
  "external_id": "refund-2",
  "refunded_at": "2026-09-21T00:00:00Z",
  "description": "Partial merchant refund",
  "refund_legs": [
    {
      "account_id": "receiving-account-id",
      "asset_id": "returned-asset-id",
      "quantity": "10",
      "transaction_value_myr": "42.50",
      "reference_value_myr": "42.20"
    }
  ]
}
```

### 7.2 后端改动

`backend/app/schemas.py`

- `CardRefundCreate` 移除/弃用 `refund_value_myr`、`expense_account_id`、`full_refund`。
- 保持 `refund_legs` 至少一项，所有数值为正。

`backend/app/cards.py`

- 从 legs 的 transaction value 计算本次 refund micros。
- 在建 event/lot 前查询 active refunds，计算 remaining 并拒绝超额。
- 从原 event 唯一解析 merchant expense account；找不到或有多个匹配时返回 409，要求先处理历史数据。
- 用统一函数重算原 purchase 的 refunded transaction value、remaining、status 和 net economic cost。
- EventLink 和新 refund cost lots 继续沿用当前逻辑。

`backend/app/cost_basis.py`

- reversal refund 后调用同一个退款状态重算函数。
- 删除“只要还有任意退款就 PARTIALLY_REFUNDED”的旧判断。

建议统一函数返回以下数据，供 API serializer 和 service 共用：

```text
refunded_transaction_value_myr
refunded_reference_value_myr
refundable_remaining_myr
derived_status
```

交易上限使用 transaction value；card cost waterfall 继续使用 reference value。两种含义不能混为一个字段。

### 7.3 前端改动

- 选择 purchase 后显示 original value、already refunded 和 remaining。
- 自动显示原 expense account/category，只读，不要求重选。
- 删除 `Full refund` checkbox 和顶层 `Refund value MYR` 输入。
- 每次增加/修改 refund leg 时实时计算 transaction total 和 reference total。
- transaction total 大于 remaining 时禁用提交并显示差额；后端仍做最终校验。
- exact remaining refund 成功后，该 purchase 从可退款列表移除。

### 7.4 退款并发与原子性

当前是本地 SQLite 应用，不为 P1 新增分布式锁。检查 remaining、创建 refund/event/lots 和更新 original status 必须在同一 session transaction 完成。若未来允许多个进程并发写入，再针对 purchase 引入串行化策略；不能用前端余额作为并发保护。

## 8. P1-4：由服务器派生估值汇率（CS-04）

### 8.1 统一规则

权威输入只保留两个事实：

- 数量 quantity；
- 该数量在入账时的 MYR 账面价值。

rate 是派生显示和 RateSnapshot 数据。用户仍需提供 valuation source，因为系统无法推断 MYR 价值来自收据、交易所成交价还是其他凭证。

### 8.2 后端改动

`backend/app/money.py`

- 仅在确实复用时增加一个小函数，从 MYR micros 和正 quantity 派生 canonical rate；不引入新 Decimal 库。

`backend/app/ledger.py`

- manual non-MYR acquisition 使用派生 rate 写入两侧 entries。
- 若兼容字段 `valuation_rate` 存在，先按 INV-07 验证，再保存派生值。

`backend/app/cards.py::credit_reward()`

- reward amount 已经存在于 pending reward；由 `value_myr / reward.amount` 派生 rate。
- 兼容字段存在时执行同样校验。

`backend/app/cost_basis.py`

- 继续从 entry 创建 RateSnapshot，无需新增第二套 rate 创建逻辑。

### 8.3 前端改动

`frontend/src/App.tsx`

- rate 输入改为只读预览；quantity 或 book amount 改变时即时更新。
- payload 不再主动发送用户编辑的 rate，兼容字段只供旧客户端。

`frontend/src/CardCenter.tsx`

- Reward credit 表单删除可编辑 rate；选择 pending reward 后，使用 reward amount 和输入 value 显示派生 rate。
- Funding leg 的 `actual_conversion_rate` 若仍显示，也应从 quantity 与 transaction value 派生或留空，不能成为第三个可矛盾输入。该字段当前不参与计算，P1 不扩大其会计含义。

### 8.4 精度验收例

| Quantity | MYR value | 预期 |
| --- | --- | --- |
| `10` | `42.50` | rate `4.25`，micros 复算等于 `42.50` |
| `3` | `10` | 保存 Decimal 派生率，复算到 MYR micros 必须等于 `10` |
| `0.00000001` | `0.01` | 不经过 float，仍可准确通过 micros 复算 |
| `0` | 任意 | 422，不能除以零 |
| `10` | `42.50`，旧客户端 rate `100` | 422，零副作用 |

## 9. P1-5：多资金腿、多退款腿和多费用 UI（CS-05）

后端 schema/service 已经使用 list 和循环处理，本项主要是前端能力补齐及针对多行的回归测试。

### 9.1 UI 状态结构

在 `CardCenter.tsx` 内分别维护三个本地数组，不引入表单库或全局状态：

```text
fundingLegs: FundingLegDraft[]  # 初始一行，至少一行
fees: FeeDraft[]                # 初始空，可添加
refundLegs: RefundLegDraft[]    # 初始一行，至少一行
```

每行有仅用于 React key 的本地 ID；提交 payload 不包含该 ID。删除最后一个 funding/refund row 时改为清空该行，不允许数组变为 0 行。

### 9.2 Settlement 行为

- `Add funding asset` 增加一行；每行包含 account、asset、quantity、transaction value、reference value。
- transaction value 合计必须等于 merchant value + included fees。
- reference value 合计只显示，不强制等于 transaction value。
- fees 支持 0..N 行；只有添加 fee 后才显示其 asset/account/amount/value/treatment fields。
- included fee 不要求 separate funding account；not-included fee 必须要求 funding account。
- 提交保持数组顺序，后端现有 sequence 字段继续记录该顺序。

### 9.3 Refund 行为

- `Add returned asset` 增加一行。
- transaction total 是本次退款价值，并与服务器 remaining 比较。
- reference total 是实际收到资产的经济参考价值，供 net economic cost 使用。
- 每一行都可以使用不同 receiving account 和 asset。

### 9.4 可访问性与错误定位

- Add/remove 按钮使用明确的 `type="button"` 和包含行号/资产的 aria-label。
- 每行错误显示在对应 fieldset 内；总计错误显示在提交按钮前。
- 删除行后焦点移动到前一行的 Add 按钮或同类字段，不能丢到页面顶部。
- 后端返回错误时保留全部行输入，不自动 reset。
- 成功后恢复为一条空 funding/refund row 和零 fee rows。

### 9.5 样式约束

只在现有 `frontend/src/App.css` 增加必要的 row、totals 和 remove button 样式；复用当前 panel、fieldset、button、error token，不建立新的设计系统。

## 10. API 契约变化总览

| API | 当前 | P1 后 | 兼容处理 |
| --- | --- | --- | --- |
| `POST /events/drafts` | 公开任意 entries | 移除公开路由 | 当前前端无调用 |
| `POST /events/{id}/post` | 可发布任意 draft | 移除公开路由 | service 内部能力保留 |
| `POST /events/manual` | 接受任意 EventType/资产组合 | 白名单、账户矩阵、非 MYR 限制、派生 rate | 旧 matching rate 可接受 |
| `GET /cards` | 缺少自动填充/剩余额度字段 | 扩展 card response | 仅新增字段 |
| `POST /cards/settlements` | linked identity 未校验、可 partial | identity 校验、P1 仅 final capture | manual settlement 保留 |
| `POST /cards/{id}/refunds` | 客户端传 total/account/full flag | total/account/status 全部服务器推导 | 旧额外字段可暂时忽略 |
| `POST /rewards/{id}/credit` | 用户传 value + rate | 用户传 value，服务器派生 rate | matching legacy rate 可接受 |

如果项目已有未记录的外部 API 客户端，实施前必须确认 generic draft/post 和 refund request 的使用情况；当前仓库搜索未发现前端调用。

## 11. 文件级改动清单

| 文件 | 计划改动 | 对应工作包 |
| --- | --- | --- |
| `backend/app/maintenance.py` | 增加只读 integrity audit 命令与输出 | P1-0 |
| `backend/app/schemas.py` | 收紧 manual/refund/reward command | P1-1、P1-3、P1-4 |
| `backend/app/ledger.py` | manual 账户/资产矩阵和派生 rate | P1-1、P1-4 |
| `backend/app/api.py` | 移除 generic write routes，扩展 card response | P1-1、P1-2、P1-3 |
| `backend/app/cards.py` | authorization identity、退款上限/状态、reward rate | P1-2、P1-3、P1-4 |
| `backend/app/cost_basis.py` | refund reversal 复用状态重算 | P1-3 |
| `backend/app/money.py` | 可选的小型派生 rate 函数 | P1-4 |
| `backend/tests/test_foundation.py` | audit/backup 只读性测试 | P1-0 |
| `backend/tests/test_ledger.py` | manual matrix、旁路封闭、派生率测试 | P1-1、P1-4 |
| `backend/tests/test_cards.py` | identity、退款、多腿、reward rate 测试 | P1-2 至 P1-5 |
| `frontend/src/api.ts` | 扩展 CardRecord 类型 | P1-2、P1-3 |
| `frontend/src/App.tsx` | manual 选项限制和只读 rate | P1-1、P1-4 |
| `frontend/src/CardCenter.tsx` | 自动填充、退款简化、多行编辑 | P1-2 至 P1-5 |
| `frontend/src/App.css` | 最少的多行表单样式 | P1-5 |
| `frontend/src/card-workflows.test.tsx` | 新增卡片表单行为测试 | P1-2、P1-3、P1-5 |
| `frontend/src/manual-myr-transaction.test.tsx` | 更新 manual 限制与 rate 行为 | P1-1、P1-4 |

预期无需 Alembic migration，因为不增加或修改数据库列/约束。若实施过程中发现必须持久化 capture final 状态，应停止并另建 migration 计划，不能把字段偷偷塞进本工作包。

## 12. 自动化测试矩阵

### 12.1 Manual 与成本批次

| 场景 | 期望 |
| --- | --- |
| MYR salary/income/opening/expense | 201，quantity=book amount，报表保持现状 |
| 非 MYR salary/income/opening | 201，创建正确 lot 和派生 RateSnapshot |
| 非 MYR expense | 422，无 event/lot/disposal |
| 任意 manual transfer | 422，并提示 `/transfers` |
| 非 MYR adjustment | 422，无 event/lot |
| 错误 debit/credit account type | 422，无 event |
| quantity 或 value 为 0 | 422 |
| MYR quantity != value | 422 |
| generic draft/post route | 404 |
| 不平衡 event service 调用 | `post_event()` 仍拒绝 |
| legacy rate 与 value 一致 | 接受但保存服务器派生值 |
| legacy rate 与 value 不一致 | 422，无 event/RateSnapshot |

### 12.2 Authorization 与 settlement

对 provider、provider account、card account、merchant、country、merchant asset、billing asset 分别做参数化 mismatch 测试：

- 每次都返回 409。
- authorization 保持 `AUTHORIZED`。
- hold 保持 `ACTIVE`。
- event、card purchase、disposal 数量不增加。

另测：

- 最终金额不同但身份相同可以成功。
- `final_capture=false` 被拒绝。
- 同一 authorization 第二次 settlement 被拒绝。
- manual settlement 不受 authorization identity 规则影响。
- UI 选择授权后字段正确预填，切换授权不会保留旧值。

### 12.3 Refund

以 RM100 purchase 为基准：

| 操作 | 期望状态 | Remaining |
| --- | --- | --- |
| refund 40 | `PARTIALLY_REFUNDED` | 60 |
| 再 refund 60 | `REFUNDED` | 0 |
| 再 refund 0.000001 | 409 | 0 |
| refund 40 后尝试 60.000001 | 409，零副作用 | 60 |
| reverse 60 refund | `PARTIALLY_REFUNDED` | 60 |
| reverse 40 refund | `SETTLED` | 100 |

还需覆盖：

- 两条 refund legs 的 transaction values 正确合计。
- expense account 从原 event 唯一推导。
- 原 event 无法唯一解析 expense account 时 409。
- reference total 与 transaction total 不同仍按各自语义进入 card cost report。
- 两次完全相同的 external ID 仍受现有唯一约束保护。

### 12.4 多行前端与后端 FIFO

- UI 添加、删除、编辑第二条 funding/refund/fee row，payload 顺序和内容正确。
- Funding transaction total 不平衡时按钮禁用并显示差额。
- 两个 funding assets 各自调用 FIFO，分别产生 disposals，basis/gain 合计正确。
- 两个 refund assets 各自建立 cost lot。
- included 与 separate fee 混合时只记一次费用和一次资金减少。
- 后端错误后表单内容保留；成功后表单重置。

### 12.5 必跑回归

```powershell
backend\.venv\Scripts\python.exe -m ruff check .
backend\.venv\Scripts\python.exe -m pytest
npm.cmd run lint
npm.cmd run test -- --maxWorkers=1
npm.cmd run test
npm.cmd run build
```

串行和默认并行前端测试都要记录；若默认并行仍出现原审查报告中的偶发 loading 超时，不能把它误判成 P1 功能失败，但合并前应单独记录为已知 P2 测试稳定性问题。

## 13. 实施顺序与本地提交划分

### Commit 1：增加只读完整性审计

建议主题：`Add accounting integrity audit`

- P1-0 命令、规则和测试。
- 对真实数据库只运行只读 audit；不修历史数据。
- 保存基线结果和备份位置，但不要提交数据库/备份/含真实数据的 JSON。

门禁：知道现有数据库是否已有受影响记录，且 audit 自身被证明不写数据库。

### Commit 2：封闭通用记账旁路并统一估值派生

建议主题：`Guard manual asset postings`

- P1-1 与 manual 部分 P1-4。
- 移除 generic draft/post routes。
- 更新 manual UI 与测试。

门禁：INV-01 至 INV-03、INV-07 对所有公开 manual API 生效。

### Commit 3：验证 linked card settlement

建议主题：`Validate card authorization settlements`

- P1-2 后端验证、card response 和自动填充 UI。
- P1 阶段禁用新 partial capture。

门禁：所有 identity mismatch 测试证明零副作用。

### Commit 4：由服务器控制退款与 reward rate

建议主题：`Derive card refund and reward values`

- P1-3 和 reward 部分 P1-4。
- 创建/撤销共用退款状态重算。
- UI 删除冗余输入。

门禁：超额退款、状态推导、撤销重算和派生 rate 全部通过。

### Commit 5：支持多腿卡片表单

建议主题：`Support multiple card funding legs`

- P1-5 前端 rows、totals、可访问性和回归测试。
- 后端补多腿集成测试，但不重写已经支持 list 的 service。

门禁：两个资金腿、两个退款腿和多个费用均能端到端正确记录。

每个提交必须只包含该逻辑单元；不得使用 `git add -A` 或把现有未跟踪文档、根 `node_modules/`、根 `package-lock.json` 一并提交。

## 14. 上线、回滚与历史修复流程

### 14.1 上线前

1. 停止应用写入。
2. 运行 `PRAGMA integrity_check`。
3. 使用现有 maintenance backup 创建带时间戳备份。
4. 运行 `audit-integrity` 并保存基线到工作区外的安全位置。
5. 若存在 AUD-01、AUD-02、AUD-03 或 AUD-06，先决定逐笔处理方案，不直接继续批量改数据。
6. 在复制数据库上运行完整测试/审计流程。

### 14.2 上线后烟雾测试

- 新建一笔 MYR 手工支出。
- 新建一笔非 MYR opening balance，确认 lot/rate。
- 尝试非 MYR manual expense，确认被拒绝且事件数量不变。
- 授权→结算，确认身份预填、hold release 和 FIFO disposal。
- RM100 purchase 做 RM40 + RM60 两次退款，确认状态与 remaining。
- 两资产 funding settlement，确认两组 lots 都正确减少。
- 再次运行 audit，新增数据不得产生新问题。

### 14.3 回滚

- 计划不含数据库 schema migration，代码可回滚到上一提交。
- 已按新规则创建的合法 events 不因代码回滚而删除。
- 任何历史财务纠正使用 reversal 和重录，不执行直接 SQL DELETE/UPDATE ledger rows。
- 如果新版本产生无法解释的数据，先停止写入并恢复上线前完整备份；不要在原库上尝试多轮不可逆修补。

## 15. Definition of Done

- [ ] 已生成真实数据库 P1 audit 基线，且没有把真实数据提交进 Git。
- [ ] 已创建并验证上线前数据库备份。
- [ ] `/events/drafts` 和 `/events/{id}/post` 不再是公开写入入口。
- [ ] Manual event type、账户类型、资产和正数约束均在后端强制执行。
- [ ] 非 MYR manual expense/adjustment 与 manual transfer 均无法绕过专用流程。
- [ ] linked settlement 的身份 mismatch 全部被服务器拒绝且零副作用。
- [ ] P1 阶段不再产生新的 partial capture。
- [ ] 累计退款不会超过 purchase transaction value。
- [ ] 创建、追加、撤销退款后状态和 remaining 都由同一函数推导。
- [ ] Manual acquisition 和 reward 的 rate 由服务器派生，矛盾 legacy rate 被拒绝。
- [ ] Settlement/refund 支持多 legs，fees 支持多行，合计提示正确。
- [ ] 后端 Ruff、pytest，前端 lint、串行/默认测试和生产 build 已执行并记录。
- [ ] 修复后 audit 不产生新的 P1 命中；已有命中都有明确的人工处置记录。
- [ ] 每个逻辑单元独立本地提交，未推送远端，未包含用户现有未跟踪文件。

## 16. 实施时的停止条件

遇到以下任一情况，应暂停对应工作包并重新评审，不得自行扩大范围：

- 发现真实外部客户端依赖 generic draft/post API。
- 业务确认必须立即支持多次 partial capture。
- 历史退款的“可退上限”不能用 purchase MYR transaction value 表达。
- 同一 purchase event 无法唯一识别 merchant expense entry。
- 历史 audit 显示大量 lot 与 ledger 不一致，无法通过逐笔 reversal 安全修正。
- 修复需要新数据库字段、批量重写历史 event 或改变报表口径。

这些情况需要单独的 schema/数据迁移方案及用户确认；不应为了按时完成 P1 而静默猜测历史会计事实。
