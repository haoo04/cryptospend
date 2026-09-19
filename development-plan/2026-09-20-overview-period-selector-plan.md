# Overview 时间周期选择开发计划

## 1. 目标

在 Overview 增加统计周期选择，让用户可以查看：

- **All time**：全部已入账记录的累计统计；
- **指定月份**：按系统配置时区计算的某个自然月统计。

本次统一覆盖 Overview 的 Net worth、Income、Expenses、Gross spending、Net spending 和 Explicit fees，并明确净资产与期间流量的不同口径，避免把“月内净资产”误解为可累加金额。

## 2. 当前实现基线

- Overview 当前直接展示 `GET /api/reports/summary` 的 Net worth、Income、Gross spending，以及 `GET /api/reports/fees` 的 Explicit fees。
- `Summary` 已包含但 Overview 尚未展示：`expense_myr` 和 `net_spending_myr`。
- Overview 调用 summary 和 fees 时不传日期，因此当前展示的是全部时间数据。
- `GET /api/reports/monthly?month=YYYY-MM` 已返回指定月的：
  - `summary`：Net worth、Income、Expenses、Gross spending、Net spending；
  - `fees`：Explicit fees；
  - `timezone`、`period_start` 和 `period_end`。
- 月报边界已经由后端按配置时区计算，并采用 `[period_start, period_end)`，无需在浏览器自行换算 UTC。
- Overview 的 Accounts 是当前账户余额，Latest activity 是最近事件；它们目前不是期间报表。
- 全局 `feeReport` 同时供 Portfolio 使用，Portfolio 需要继续显示全部时间费用，不能被 Overview 的月份选择覆盖。

## 3. 产品口径

### 3.1 指标定义

| 指标 | All time | 指定月份 |
| --- | --- | --- |
| Net worth (book) | 当前全部账本记录形成的账面净资产 | 截至所选月份结束边界的账面净资产 |
| Income | 全部时间的收入账户净额 | 所选自然月内的收入账户净额 |
| Expenses | 全部时间的费用账户净额 | 所选自然月内的费用账户净额 |
| Gross spending | 退款与返现抵扣前的全部支出 | 所选月退款与返现抵扣前的支出 |
| Net spending | Gross spending 减退款与已入账返现 | 所选月 Gross spending 减退款与已入账返现 |
| Explicit fees | 全部有效显式费用组件 | 所选月内的有效显式费用组件 |

Net worth 是某个时点的存量：选择月份时展示“截至月末”，而不是只把该月资产变动相加。Income、Expenses、Spending 和 Fees 是期间流量，只统计所选月内发生的记录。

所有金额继续由后端账本与报表接口计算；前端只选择响应字段和格式化显示，不在浏览器重新计算财务结果。

### 3.2 筛选范围

周期选择只作用于顶部统计卡片。

- Accounts 保持展示当前账户余额；
- Latest activity 保持展示最近 6 条事件；
- Portfolio 的费用汇总保持 All time；
- Reports 页自己的月份选择保持独立，不与 Overview 相互修改。

这样可以避免“历史月份”筛选后仍把当前账户余额误标为历史余额，也避免为了本需求扩展事件和账户 API。

### 3.3 默认与切换行为

- 默认选择 **All time**，保持现有用户进入 Overview 时的行为。
- 切换到 **Month** 时，月份输入默认使用浏览器当前 `YYYY-MM`，并加载该月报表。
- 修改有效月份后立即加载新月份；空值或无效值不发请求。
- 切回 All time 时恢复已加载的全部时间统计，不必重新加载整个应用。
- 本期不把选择写入 localStorage；刷新页面后回到 All time。
- 无数据是有效状态，六项金额均可显示 `MYR 0`，不显示错误提示。

## 4. Overview 交互设计

在统计卡片上方增加一个紧凑的 period toolbar：

- 标题：`Overview period`；
- 分段按钮：`All time`、`Month`；
- 选择 Month 时显示原生 `<input type="month">`；
- 辅助文案显示实际已加载范围：
  - All time：`All posted records`；
  - Month：`August 2026 · Asia/Kuala_Lumpur`；
- 月份模式下，Net worth 卡片说明改为 `As of month end`，其他卡片说明为 `During selected month`；
- All time 下卡片说明为 `All posted records`。

统计卡片调整为：

1. Net worth (book)
2. Income
3. Expenses
4. Gross spending
5. Net spending
6. Explicit fees

现有自适应 `metric-grid` 可以承载六张卡片；只为 period toolbar 增加必要样式，并在窄屏下改为单列或可换行布局。

### 4.1 加载与失败状态

- 周期请求使用独立的 `overviewLoading`，不触发全页首次加载状态，也不禁用无关页面操作。
- 加载时只禁用周期控件，并显示 `Updating…`；Accounts 与 Latest activity 保持可见。
- 保留“最后一次成功响应”的周期标签与数值，直到新响应成功，避免新月份标签搭配旧月份金额。
- 请求失败时显示 Overview 内联错误和 Retry；不得把失败请求的月份标记为已经生效。
- 快速切换月份时采用递增请求序号或等价的 last-request-wins 保护，较早响应不得覆盖较新的选择。

## 5. 数据与 API 方案

不新增后端接口、schema、迁移或依赖，直接复用已有 API：

| 模式 | 请求 | 使用字段 |
| --- | --- | --- |
| All time | `GET /api/reports/summary` | `net_worth_myr`、`income_myr`、`expense_myr`、`gross_spending_myr`、`net_spending_myr` |
| All time | `GET /api/reports/fees` | `total_myr` |
| Month | `GET /api/reports/monthly?month=YYYY-MM` | `summary`、`fees.total_myr`、`timezone`、`period_start`、`period_end` |

选择月份时不能把月报的 `fees` 写入现有全局 `feeReport`，否则 Portfolio 会错误显示月度费用。Overview 应保留独立的月报响应，例如 `overviewMonthly: MonthlyReport | null`，展示时按当前已应用模式选择：

- All time：现有 `summary` + 全局 `feeReport`；
- Month：`overviewMonthly.summary` + `overviewMonthly.fees`。

`frontend/src/api.ts` 已具有 `Summary`、`FeeReport`、`MonthlyReport` 类型及 `api.monthly()`，预计无需修改。

## 6. 前端实施步骤

### 阶段 A：周期状态与数据加载

在 `frontend/src/App.tsx`：

1. 增加 Overview 模式、月份草稿、最后成功应用的周期、月报响应、局部 loading/error 状态；
2. 增加只加载 Overview 月报的函数，调用 `api.monthly(month)`；
3. 初始 All time 继续使用现有 `summary` 和 `feeReport` 请求；
4. 切换月份只刷新 Overview 统计，不重复请求 assets、accounts、events、cards 等无关数据；
5. 全局 Refresh 或成功写入交易后：
   - 始终刷新 All time 的 summary 与 fees；
   - 若 Overview 当前应用的是 Month，再刷新该已应用月份；
   - 保持用户当前应用的模式，不自动跳回 All time；
6. 使用最后请求序号忽略过期响应，并在组件卸载后避免写入 state。

不复用 Reports 页的 `monthly` state，避免 Overview 的月份操作改变 Reports 当前查看的月份。

### 阶段 B：组件与文案

调整 `Dashboard` props 与渲染逻辑：

1. 在指标卡片上方加入周期 toolbar；
2. 渲染六项指标，补上 `Expenses` 和 `Net spending`；
3. 让 `Metric` 接受按周期变化的辅助说明，不再为所有卡片固定显示同一句文案；
4. 月份标签以服务端返回的 `month` 和 `timezone` 为准；
5. Net worth 在月度模式明确标记为 month end；
6. 增加 loading、错误、Retry 和无数据状态；
7. 为按钮组、月份输入和状态信息提供可访问名称与 `aria-live` 反馈。

### 阶段 C：样式

在 `frontend/src/App.css`：

- 为 period toolbar、模式按钮、月份输入、loading/error 状态增加少量样式；
- 复用现有 panel、button、input 和响应式规则；
- 在桌面端保持控件紧凑，在移动端允许换行且月份输入占满可用宽度；
- 不引入新的组件库。

## 7. 测试计划

新增一个聚焦的前端测试文件，例如 `frontend/src/overview-period.test.tsx`，覆盖：

1. 默认 All time，展示 summary 和全部时间 fees；
2. `Expenses` 与 `Net spending` 两张新增卡片使用正确字段；
3. 切换 Month 时以 `YYYY-MM` 调用 `api.monthly()`；
4. 月报成功后六项指标全部来自同一个月报响应；
5. 月度 Net worth 显示 month-end 语义，并显示服务端 timezone；
6. 切回 All time 后恢复全部时间数据；
7. Overview 月份费用不会覆盖 Portfolio 的全部时间费用；
8. 月份请求期间显示局部 loading，失败时保留最后成功数据并可 Retry；
9. 较早的慢响应不会覆盖较新的月份响应；
10. 全局 Refresh 后保持当前模式，并刷新当前应用月份；
11. 月份无数据时正常显示零值；
12. Accounts 与 Latest activity 不随周期选择变化。

后端本期不改代码。现有 `backend/tests/test_reporting.py::test_timezone_month_report_as_of_portfolio_and_immutable_snapshot` 已覆盖配置时区的月边界与月末净资产；实施时运行完整后端测试作为回归验证，不重复增加等价用例。

验证命令：

```powershell
npm.cmd --prefix frontend run test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
Set-Location backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

## 8. 验收标准

- Overview 默认仍显示 All time 统计。
- 用户可以选择任意有效 `YYYY-MM` 并看到该自然月的统计。
- 月份边界由后端配置时区决定，不由浏览器拼接 UTC 时间。
- 月度 Net worth 是截至月末的账面净资产，其他五项是月内流量。
- 六张卡片始终来自同一个已成功加载的周期，不出现标签与金额错配。
- Expenses、Gross spending 和 Net spending 的含义与数值彼此区分。
- 切换周期不会改变 Accounts、Latest activity、Reports 月份或 Portfolio 全部时间费用。
- 快速切换、空月份、无数据和请求失败都有明确且稳定的表现。
- 桌面与移动端布局可用，键盘可操作，状态变化可被辅助技术识别。
- 前端 test、lint、build 与后端 pytest、ruff 全部通过。

## 9. 非目标

- 自定义起止日期；
- 日、周、季度或年度快捷周期；
- 按月份过滤 Accounts 或 Latest activity；
- 新增趋势图、同比/环比或分类明细；
- 修改 Reports 页现有 Monthly/Analytics 功能；
- 保存用户上次选择；
- 修改账本、月报算法、数据库 schema 或历史快照格式。

## 10. 预计文件影响

| 文件 | 变更 |
| --- | --- |
| `frontend/src/App.tsx` | Overview 周期状态、月报加载、刷新衔接、toolbar 与六项指标 |
| `frontend/src/App.css` | 周期控件、局部状态和响应式样式 |
| `frontend/src/overview-period.test.tsx` | 周期切换、口径、隔离、失败与竞态测试 |

预计不修改 backend、数据库迁移或 `frontend/src/api.ts`。

## 11. 建议实施提交

功能实现、样式与聚焦测试属于同一项用户能力，建议一个本地提交：

`Add Overview period selection`

提交前只暂存本功能相关文件，不包含工作区中既有的未跟踪文件，也不推送远程。
