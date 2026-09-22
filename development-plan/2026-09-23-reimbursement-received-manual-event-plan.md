# `REIMBURSEMENT_RECEIVED` 费用返还手工事件开发计划

> 制定日期：2026-09-23
>
> 来源：朋友代垫款返还需求与 P1 记账完整性修复计划
>
> 本文记录已实施的功能契约与验收标准。

## 1. 设计结论

`REIMBURSEMENT_RECEIVED` 用于记录朋友偿还用户先垫付、且已经记入用户 `EXPENSE` 的费用。

原始支出：

```text
Debit  EXPENSE
Credit ASSET
```

费用返还：

```text
Debit  ASSET
Credit EXPENSE
```

因此 Overview 会表现为：

- `net_worth_myr` 增加返还金额；
- `expense_myr` 减少返还金额；
- `income_myr` 不变；
- `net_income_myr` 增加返还金额；
- `net_spending_myr` 减少返还金额；
- 不需要修改 Overview 报表计算逻辑。

该事件不用于朋友预付款、代收代付、暂存资金或自有账户之间转账。预付款/代收代付未来应使用独立的清算或负债事件；自有账户转账继续使用 `TRANSFER` 和 `/api/transfers`。

## 2. 事件契约

事件类型和界面名称：

```text
REIMBURSEMENT_RECEIVED
Reimbursement received / 代垫款收回
```

固定账户矩阵：

| 方向 | 账户类型 |
| --- | --- |
| Debit | `ASSET` |
| Credit | `EXPENSE` |

服务端约束：

- 资产必须是规范 MYR，即 `symbol == "MYR"` 且 `chain == null`；
- `quantity` 与 `book_amount_myr` 必须为正数且相等；
- `credit_account_id` 必须是 `EXPENSE`；
- `category_id` 必填且必须是活动的 `EXPENSE` 分类；
- `description` 去除空白后不能为空；
- 非法请求在创建 event 前拒绝，不产生 event、entry 或 cost lot；
- 第一版不关联原始 Expense event，也不自动检查返还金额是否超过原始支出金额；用户需要手动选择对应费用账户和分类。

## 3. 实施内容

### 后端

- `backend/app/enums.py` 增加 `EventType.REIMBURSEMENT_RECEIVED`；
- `backend/app/schemas.py` 将事件加入手工事件白名单；
- `backend/app/ledger.py` 增加 `ASSET -> EXPENSE` 账户矩阵、Expense 分类要求、MYR 限制和说明校验；
- `backend/app/cost_basis.py` 将事件加入 acquisition 类型，使收到的 MYR 创建可供后续 FIFO 转账使用的 cost lot；
- 保留现有 `/api/events/manual` API，不新增路由、数据库字段或 migration；
- `TRANSFER` 仍不能通过手工事件 API 创建。

### 前端

- 手工 Event Type 下拉加入 `Reimbursement received`；
- 该类型只显示 MYR、`ASSET` 借方账户和 `EXPENSE` 贷方账户；
- Expense 分类和 Description 设为必填；
- 交易搜索和 Account Ledger 类型筛选支持该事件；
- `TRANSFER` 的显示名称改为 `Internal transfer`，明确表示自有账户转账。

## 4. 测试与验收

后端覆盖：

- 原始 MYR Expense 后创建返还，验证 net worth 增加、expense 减少、income 不变；
- 验证 net income 和 net spending 正确减少/增加；
- 验证事件可搜索并创建正确的 MYR cost lot；
- 验证 reversal 恢复返还前的报表和 cost lot 状态；
- 验证错误账户类型、非 MYR、空说明、缺少分类、错误分类和金额不一致均返回 422；
- 验证失败请求没有账务副作用。

前端覆盖：

- 验证新事件的账户、资产和分类选择器限制；
- 验证 payload 使用同一个 MYR 金额填充 `quantity` 和 `book_amount_myr`；
- 验证 Description、Expense account 和 Expense category 必填；
- 验证交易和账户流水筛选显示 `Reimbursement received` 与 `Internal transfer`。

验证命令：

```powershell
cd backend
.venv\Scripts\python.exe -m pytest
cd ..
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run lint
```

## 5. 明确不包含

- 不重新启用手工 `TRANSFER`；
- 不使用 `ADJUSTMENT` 模拟朋友还款；
- 不实现朋友预付款、代收代付或负债清算；
- 不新增原始费用事件关联字段；
- 不改写已有历史事件或 Overview 报表公式。
