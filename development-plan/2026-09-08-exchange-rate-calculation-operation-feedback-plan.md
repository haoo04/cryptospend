# CryptoSpend 汇率/金额自动计算与操作反馈优化开发计划

- 日期：2026-09-08
- 状态：已实施（2026-09-08）
- 评审基线：`84ddc4b Add fixed expense management UI`
- 目标版本：下一次前端体验与交易正确性迭代

## 1. 结论与优先级

本轮建议按以下顺序实施：

1. **P0：完成 Trade 表单的精确自动计算。** 当交易对包含 MYR 时，用户按常见方式输入 `1 USDT = 4.05797 MYR` 和 `2800 MYR`，系统自动填入约 `690.000172500043... USDT`，并自动得到 `gross_value_myr = 2800`。
2. **P0：统一成功、失败和部分成功反馈。** 所有用户主动触发的写操作使用非阻塞 popup/toast；成功与失败必须清楚区分。
3. **P0：修复“失败后表单仍被清空/关闭”。** 当前 action 包装器捕获异常后不再向表单返回失败状态，Trade、Transfer、Card、Category、Fixed expenses、Journey 等表单会把失败当成成功并重置。
4. **P0：增加服务端交叉校验。** 前端自动计算只是录入便利，后端仍需防止数量、汇率和 MYR gross value 互相矛盾的数据进入账本和汇率快照。
5. **P1/P2：分批处理本次审查发现的其他功能、逻辑与界面问题。** 这些问题列在第 8 节，不应扩大第一批改动的范围。

第一批不需要数据库迁移，不引入状态管理框架、UI 组件库或浮点金额依赖。

## 2. 当前实现基线

### 2.1 技术与金额约束

- 前端为 React 19 + TypeScript + Vite，主要导航、操作包装器和 Add transaction 页面集中在 `frontend/src/App.tsx`。
- 后端为 FastAPI + SQLAlchemy + SQLite。
- API 金额和数量均使用十进制字符串；MYR 权威账面金额以整数 micros 保存。
- 项目既有约定为 `rate = quote_asset / base_asset`。例如 `USD/MYR = 4.25` 表示 `1 USD = 4.25 MYR`。
- `RateSnapshot` 已明确保存 base、quote、rate、时间、来源和类型，不应新增无方向的 rate 字段。

### 2.2 Trade 表单现状

`frontend/src/App.tsx` 的 `TradeForm` 当前要求用户分别手填：

- Sell asset / Sell quantity；
- Buy asset / Net buy quantity；
- Execution rate；
- Gross transaction value (MYR)；
- 可选 fee 数量和 MYR value。

现有问题：

- 字段之间没有自动计算。
- 页面只提示 `buy asset / sell asset`，没有把已选币种代入汇率方向。
- 当 Sell=MYR、Buy=USDT 时，后端内部方向需要 `USDT / MYR`，但用户通常输入的是 `USDT/MYR = 4.05797`，即“每 1 USDT 值多少 MYR”。两者互为倒数，极易录反。
- 前端与后端均没有验证 `sell_quantity`、`buy_quantity`、`execution_rate`、`gross_value_myr` 是否一致。
- 当前 `buy_quantity` 表示扣除买入资产内含手续费后的净到账数量；execution rate 与 gross value 表示手续费前的成交事实。界面没有把这层关系讲清楚。

### 2.3 操作反馈现状

- `App` 只有一个页面顶部的 `error` 红色横幅，没有成功提示。
- `runAction`、`runRecurringAction` 和 `runReportAction` 捕获异常后只更新 `error`，调用方得到的 Promise 仍正常完成。
- 多个子表单在 `await onSubmit(...)` 后直接执行 `form.reset()`、清空 state、关闭编辑表单或关闭确认区，因此 API 失败也会丢失用户输入。
- FastAPI 的普通业务错误是 `{ detail: string }`，但 422 schema 校验通常返回 `detail` 数组；`frontend/src/api.ts` 目前只按字符串读取，复杂校验错误可能显示成不可读内容。
- “交易已保存、收据上传失败”是部分成功，不应被表现成普通失败，也不能鼓励用户再次提交整笔交易。

### 2.4 当前质量基线

本次审查时结果：

- 前端：4 个测试文件、9 个测试全部通过。
- 前端 ESLint：通过。
- 后端：29 个测试全部通过。
- 后端测试有 1 条 Starlette `TestClient/httpx` 弃用警告，不影响本轮功能。

## 3. 本期目标

### 3.1 必须完成

- Trade 表单支持由资产组合、一个金额和汇率自动计算另一侧金额。
- 当任一交易资产为 MYR 时，自动计算 `gross_value_myr`。
- 用户修改任一侧金额后可以反算汇率，且不会形成 state 更新循环。
- 计算使用精确十进制字符串，不使用 `Number`、`parseFloat` 或 `toFixed` 生成财务 payload。
- 动态展示汇率方向和公式，避免正向/反向误解。
- 服务端拒绝数量、汇率与 MYR gross value 存在实质矛盾的交易。
- 所有用户写操作都有成功/失败 popup；部分成功使用 warning popup。
- 写操作失败时保留表单内容和当前上下文；只有确实落库成功后才清空。
- popup 对键盘、读屏和移动端可用。

### 3.2 推荐一并完成的小范围修正

- 同一资产不能同时作为 Sell 和 Buy，前端直接禁用/过滤，后端继续兜底。
- 保存成功后把日期时间重置为“当下”，不能回到组件首次挂载时的旧时间。
- 对 FastAPI 422 错误做可读化处理。
- 区分“写入失败”和“写入已成功但刷新失败”，不能把后者提示成交易失败。

## 4. 汇率方向与数据契约

### 4.1 术语

令：

- `S`：卖出数量，即 `sell_quantity`。
- `B_net`：实际净到账数量，即当前 API 的 `buy_quantity`。
- `F_buy`：以 Buy asset 收取、且已包含在净到账数量中的手续费；其他手续费按 `0` 处理。
- `B_gross = B_net + F_buy`：手续费前应获得的 Buy asset 数量。
- `R_internal = B_gross / S`：后端现有 canonical execution rate，即 `quote(Buy) / base(Sell)`。
- `R_myr`：当交易对包含 MYR 时，界面统一展示的常见报价，即 `MYR / 非 MYR 资产`。

数据库/API 的 canonical 方向保持不变：Trade 产生的 `RateSnapshot.base_asset_id = sell_asset_id`、`quote_asset_id = buy_asset_id`，`rate = R_internal`。本期只改善显示和输入，不做数据迁移，也不改变已保存历史交易。

### 4.2 MYR 交易对公式

| 方向 | 用户看到的报价 | 自动计算 gross Buy | 自动计算 net Buy | `gross_value_myr` | 提交的 `execution_rate` |
| --- | --- | --- | --- | --- | --- |
| Sell MYR → Buy X | `1 X = R_myr MYR` | `S / R_myr` | `B_gross - F_buy` | `S` | `1 / R_myr` |
| Sell X → Buy MYR | `1 X = R_myr MYR` | `S × R_myr` | `B_gross - F_buy` | `B_gross` | `R_myr` |

示例：

```text
Sell asset: MYR
Sell amount: 2800
Buy asset: USDT
Displayed rate: 1 USDT = 4.05797 MYR
Fee: none

Gross/Net USDT = 2800 / 4.05797
               ≈ 690.000172500043125011 USDT（按资产精度舍入）
Gross value MYR = 2800
Internal rate    = 1 / 4.05797
                 ≈ 0.2464286330357296875 USDT per MYR
```

用户不需要看到或手工输入 internal inverse rate；提交前由前端精确转换。界面必须明确显示 `1 USDT = 4.05797 MYR`，不能只显示“Rate”。

### 4.3 非 MYR 交易对

当 Sell 和 Buy 都不是 MYR：

- 汇率显示为 `1 {Sell} = R {Buy}`。
- `B_gross = S × R`，`B_net = B_gross - F_buy`。
- `execution_rate = R`。
- 因为交易对本身不能给出 MYR 估值，`gross_value_myr` 仍由用户依据实际订单/结算记录填写。
- 本期不自动抓取市场价格，也不使用“最新价格”替代历史成交时点的事实。

### 4.4 手续费规则

- 只有“手续费资产等于 Buy asset”且勾选 included 的费用会从自动计算的 gross Buy 中扣除，得到 net Buy。
- 费用由其他资产支付、或未包含在到账数量时，不改变自动计算的 `B_net`。
- 用户修改 fee asset、fee amount 或 included 状态后，自动重算 net Buy。
- `gross_value_myr` 始终表示手续费前成交价值，不能因为 fee 改为净值。
- 保留现有 `EXPENSED`、`REDUCE_PROCEEDS`、`CAPITALIZED` 会计处理；本轮只计算录入字段，不改变成本基础算法。

## 5. Trade 表单交互设计

### 5.1 字段与布局

将现有抽象标签改成带资产符号的标签：

- `Pay amount (MYR)` / `Sell amount (USDT)`；
- `Receive amount (USDT, net)`；
- `Rate: 1 USDT = [4.05797] MYR`；
- `Gross transaction value (MYR)`；
- derived 字段旁显示 `Calculated`，用户手工覆盖后显示 `Manual`。

在金额区域下方显示一行实时摘要：

```text
RM 2,800.00 ÷ 4.05797 = 690.0001725 USDT · Fee 0 · Net 690.0001725 USDT
```

移动端按 Sell amount → Rate → Receive amount → MYR gross value 的顺序单列显示。可选费用继续放在独立 fieldset 中，不与主要成交金额混排。

### 5.2 计算触发与输入所有权

采用明确的“最后手工编辑字段”规则，避免三个字段互相更新形成循环：

1. 选好不同的 Sell/Buy asset 后才启用计算。
2. 默认主流程是用户输入 Sell amount 和 Rate，系统计算 Receive amount。
3. 用户手工修改 Receive amount 后，该字段成为事实输入，系统反算 Rate。
4. 用户再次修改 Rate 时，系统以 Sell amount 为锚点重新计算 Receive amount。
5. 切换任一资产时清除旧的 derived 值和旧方向 rate，保留不会造成币种歧义的字段。
6. 输入为空、非十进制、等于零或小于零时不计算，并在字段下显示具体原因。
7. 计算值可被用户按实际交易所回单覆盖；覆盖后需重新计算关联 rate/gross，保证最终提交字段一致。

### 5.3 精度与舍入

- 新增一个小型、无依赖的十进制字符串运算工具，使用 `BigInt + scale` 完成乘、除、倒数和比较。
- 目标数量按 Buy asset 的 `decimals` 舍入；MYR gross value 按现有 6 micros 精度舍入。
- 舍入模式与后端保持 `ROUND_HALF_EVEN`。
- 展示时可以移除无意义的尾随零，但提交值必须是规范化十进制字符串。
- 禁止用 JS 二进制浮点结果生成提交 payload；`Number` 只可继续用于现有图表相对宽度等非权威展示。

### 5.4 服务端校验

在 `create_trade` 落库前增加交叉校验：

1. 用 Python `Decimal` 计算 `B_gross` 和 canonical `R_internal`。
2. 按提交 rate 的小数位精度比较 `R_internal`，允许输入 rate 自身造成的最后一位舍入，不允许方向录反或明显不一致。
3. Sell 或 Buy 为 MYR 时，按第 4.2 节验证 `gross_value_myr`。
4. 含 Buy asset 内扣 fee 时，把 fee amount 加回 net Buy 后再验证 gross execution rate。
5. 错误返回 422 和可操作信息，例如：`Execution rate does not match MYR 2800 and net USDT 690...`。
6. 不静默改写用户提供的实际成交数据。

前端 calculator 与服务端 validator 使用同一组 golden examples，避免公式随时间分叉。

## 6. Popup/toast 操作反馈设计

### 6.1 反馈类型

| 类型 | 场景 | 行为 |
| --- | --- | --- |
| Success | 写操作已持久化 | 绿色，约 4 秒自动消失，可手工关闭 |
| Error | 写操作未持久化 | 红色，不自动消失，保留 API 可读原因和关闭按钮 |
| Warning | 主操作成功但附属步骤失败，或成功后刷新失败 | 琥珀色，不自动消失，说明已成功部分及下一步 |

只保留一个当前 toast 即可，因为现有全局 busy 已阻止并发写操作；本期不引入通知队列或第三方组件库。

### 6.2 覆盖范围

以下用户主动操作必须提示结果：

- 初始化账本、手工交易、Trade、Transfer；
- 新增市场 rate；
- 卡授权、撤销授权、结算、退款、pending reward、credit reward；
- 分类新增、重命名、启用/停用；
- 固定支出新增、编辑、启停、记录、跳过；
- 收据上传、替换、删除；
- Event reversal；
- Journey 新增/分配、月度 snapshot；
- Google Drive backup；
- 用户点击的 Refresh。

Analytics 期间切换、初始页面加载等读取成功不弹 success，以免产生噪音；读取失败继续在相关页面保留 inline error，同时可在全局 toast 提示一次。

### 6.3 推荐文案

成功文案使用“对象 + 已完成动作”，例如：

- `Trade posted successfully.`
- `Transaction posted successfully.`
- `Transfer posted successfully.`
- `Category updated successfully.`
- `Fixed expense recorded successfully.`
- `Receipt uploaded successfully.`
- `Database backup uploaded successfully.`

失败标题带操作上下文，例如 `Unable to post trade`；正文优先使用 API detail。不要只显示统一的 `Action failed`。

### 6.4 正确的 action 结果契约

当前 action 包装器不能继续吞掉失败。推荐用最简单的显式结果：

- mutation 成功：返回 `true`；
- mutation 失败：显示 Error toast 并返回 `false`；
- 表单只在返回 `true` 时 reset、清空或关闭；
- 由按钮直接触发且无需 reset 的操作可以忽略返回值；
- mutation 成功后的 refresh 单独捕获。refresh 失败时 mutation 仍返回成功，并显示 Warning，而不是误报“写入失败”。

对于需要返回实体的流程可返回 `{ ok: true, data } | { ok: false }`，但不要为了统一而引入复杂 action framework。

### 6.5 部分成功：交易与收据

如果 event 已保存但 receipt 上传失败：

- toast 类型为 Warning；
- 明确显示 `Transaction {id} was saved, but the receipt upload failed.`；
- 刷新并保留已落库 event；
- 清理已提交交易表单，防止用户重试时创建重复交易；
- 提供 `Open transaction` 或明确提示从 Transactions 详情重试收据；
- 该情况不得使用普通失败结果，也不得把 event 再提交一次。

### 6.6 API 错误标准化

`frontend/src/api.ts` 统一解析：

- `{ detail: string }`：直接显示；
- FastAPI `{ detail: [{ loc, msg, type }, ...] }`：转换成 `字段: 原因`，最多展示前几条；
- 非 JSON、网络中断或 5xx：显示稳定 fallback，并保留 HTTP status；
- popup 不显示 stack trace、原始对象字符串或 `[object Object]`。

### 6.7 可访问性与响应式

- toast 容器固定在主内容右上角；小于 760px 时左右留 16px 并占可用宽度。
- Success 使用 `role="status"` / `aria-live="polite"`；Error/Warning 使用 `role="alert"`。
- 关闭按钮必须有可读 `aria-label`，并支持键盘操作。
- 不只依赖颜色区分状态，必须同时有标题/图标/文本。
- 遵守 `prefers-reduced-motion`；动画只做短距离淡入淡出。
- toast 不夺取当前输入焦点。

## 7. 表单成功、失败与重置规则

所有写表单统一遵循：

| 结果 | 表单内容 | 当前 panel/modal | 数据刷新 |
| --- | --- | --- | --- |
| 成功 | 清空已提交字段；保留合理默认值 | 可关闭确认区 | 刷新受影响数据 |
| 失败 | 完整保留 | 保持打开 | 通常不刷新；409 可刷新冲突对象 |
| 部分成功 | 防止重复写入主对象；保留可重试附件上下文 | 跳转/指向已保存对象 | 刷新主对象 |
| 写成功、刷新失败 | 按成功处理 | 正常结束 | Warning + 可手工 Refresh |

重置 datetime 时调用新的 `localDateTimeValue()`，不要让原生 `form.reset()` 回到组件首次渲染时的 `defaultValue`。对复杂表单优先改为最小范围的 controlled state 或在成功后显式设置时间。

## 8. 其他审查发现与建议 Backlog

以下项目按收益和风险排序。P0/P1 建议纳入近期迭代；P2/P3 独立排期，避免本轮改动膨胀。

| 优先级 | 类型 | 发现 | 风险/影响 | 建议 |
| --- | --- | --- | --- | --- |
| P0 | 逻辑 | action 包装器吞异常，多个表单失败后仍 reset/关闭 | 丢失输入，用户误以为成功 | 随 toast 一起改为显式成功结果，并补回归测试 |
| P0 | 数据正确性 | Trade 的数量、rate、gross MYR 可互相矛盾 | 错误汇率快照、成本基础和盈亏解释 | 前端精确计算 + 后端交叉校验 |
| P1 | 错误处理 | 422 detail 数组未标准化 | popup 可能不可读 | 在 `api.ts` 统一解析 validation detail |
| P1 | 时间逻辑 | 多个表单 reset 后回到初次挂载时间，MANUAL 也持续保留旧 occurred time | 连续录入会写入错误时间 | 成功后显式刷新当前本地时间 |
| P1 | 金额录入 | MANUAL 非 MYR 仍需手填 quantity、Book MYR 和 rate，三者无关联；MYR 也仍显示无意义 rate | 重复输入、估值不一致 | 复用十进制 calculator：任意两项计算第三项；MYR 固定 rate=1 并隐藏输入 |
| P1 | 选择校验 | 大部分表单显示 inactive asset、closed account，且允许相同 Trade asset/相同 Transfer account | 可制造无效或被服务端拒绝的命令 | 新操作只列 active/open 项；过滤相同选项；后端同步兜底 |
| P1 | 刷新逻辑 | 每次普通写操作都重新请求约 13 组全局数据；Refresh 按钮本身没有独立 loading 状态 | 操作延迟、无关接口失败影响当前体验 | 按操作刷新受影响资源；为手动 Refresh 增加独立状态 |
| P2 | 功能 | Transactions 只取最近 100 条，页面没有搜索、筛选和分页提示 | 历史变多后旧交易不可发现 | 增加 cursor/page、类型/日期/状态/category 筛选和结果总数 |
| P2 | 前端设计 | Card settlement 选择 authorization 后仍需重复填写 provider、merchant、asset、amount 等；页面字段密度高 | 重复录入与字段不一致 | 选择 authorization 后自动预填只读事实；按 Merchant、Funding、Fee 分段/渐进展开 |
| P2 | 交互一致性 | Event reversal 使用 `window.prompt`，收据删除使用 `window.confirm` | 样式、校验、可访问性不一致 | 改为应用内确认 dialog；reversal reason 用必填 textarea |
| P2 | 可访问性 | 多组视觉 tabs 没有完整 tab semantics；现有全局 error 没有 alert/live region | 键盘和读屏反馈不足 | 增加 `tablist/tab/aria-selected`、focus 样式和 live region |
| P2 | 防错 | 金额字段多数仅有 `inputMode="decimal"`，没有即时的正数/精度提示 | 错误只能在提交后发现 | 使用统一 inline validation；仍由后端做最终校验 |
| P3 | 可维护性 | `App.tsx` 已超过 1300 行，Card 表单存在多段单行 JSX | 修改反馈和计算逻辑时回归面较大 | 只在被触及区域提取 `TradeForm`/`Toast`；不进行全量架构重写 |
| P3 | 产品体验 | 应用界面主要是英文，而现有用户文档已中英双语 | 术语学习成本较高 | 后续建立中英术语表和轻量 i18n，不与本轮混做 |
| P3 | 工具链 | 后端测试出现 Starlette TestClient/httpx 弃用警告 | 后续升级可能变成兼容问题 | 独立依赖维护任务处理，不为本轮改依赖 |

## 9. 实施步骤

### 阶段 A：锁定计算契约和测试样例

1. 将第 4 节公式写成前后端测试用例。
2. 覆盖无 fee、Buy asset 内扣 fee、Sell=MYR、Buy=MYR、非 MYR pair。
3. 明确资产精度、rate 输入精度和 half-even 舍入。
4. 保持现有 API 字段和数据库结构不变。

### 阶段 B：前端精确计算与 Trade UI

1. 增加最小的十进制字符串 helper 及单元测试。
2. 将 `TradeForm` 的资产、数量、rate、gross value 和 fee 相关字段改为受控状态。
3. 实现动态方向、自动计算、反算、derived/manual 标记和计算摘要。
4. 资产切换时清理有方向歧义的 derived state。
5. 在提交前生成 canonical `execution_rate`。

### 阶段 C：后端一致性保护

1. 在 trading service 中按 Decimal 重建 gross buy、internal rate 和 MYR gross。
2. 对不一致值返回具体 422 DomainError。
3. 保持 FIFO、fee treatment、cost lot 和 RateSnapshot 逻辑不变。
4. 补充反向汇率和 fee 场景测试。

### 阶段 D：操作反馈与结果传播

1. 在 `App` 增加单一 toast state 和轻量渲染组件。
2. action 包装器接收成功/失败上下文，并返回显式结果。
3. 更新所有写操作调用处的成功文案。
4. 更新表单：只在成功时 reset/关闭。
5. 单独处理 receipt 部分成功和 mutation 后 refresh 失败。
6. 在 `api.ts` 标准化 422/网络/非 JSON 错误。

### 阶段 E：验收与小屏检查

1. 跑 frontend test、lint、build。
2. 跑 backend ruff、pytest。
3. 手工验证桌面和 760px 以下布局。
4. 使用键盘完成 Trade、关闭 toast、查看失败信息。
5. 用浏览器刷新确认已成功的数据确实落库。

## 10. 预计改动文件

第一批预计只改以下文件；最终以实现需要为准：

- `frontend/src/App.tsx`：Trade state、公式交互、action 结果、toast 接入。
- `frontend/src/App.css`：calculator 状态、摘要和 toast 响应式/可访问样式。
- `frontend/src/api.ts`：API error detail 标准化；必要时补具体 payload 类型。
- `frontend/src/decimal.ts`：最小精确十进制字符串运算（新增文件确有独立职责时才创建）。
- `frontend/src/*test.tsx` / `frontend/src/decimal.test.ts`：Trade、toast、失败保留输入测试。
- `backend/app/trading.py`：Trade 交叉校验。
- `backend/tests/test_trading.py`：公式与拒绝场景。

不修改 migration、数据库表和历史记录；不执行 `npm install`，不新增第三方依赖。

## 11. 测试矩阵

### 11.1 自动计算

- MYR 2800 → USDT，`1 USDT = 4.05797 MYR`，自动得到约 690.000172500043... USDT 和 MYR gross 2800。
- USDT → MYR 使用同一报价时执行乘法，不错误取倒数。
- 切换 Sell/Buy 方向后 label、显示 rate、internal rate 同步改变。
- Sell 和 Buy 相同不能提交。
- rate 为空、0、负数、非法字符串不能计算/提交。
- 很小数量、很多小数、尾随零和资产最大 30 decimals 不经过二进制浮点。
- Buy asset 内扣 fee 时，net buy = gross buy - fee；其他 fee 不重复扣减。
- 用户覆盖 derived buy quantity 后可以反算 rate。
- Crypto/Crypto 只计算 pair quantity，MYR gross 仍需手填。

### 11.2 服务端一致性

- canonical rate 与数量一致时接受。
- rate 方向取反、gross MYR 不符、net/gross 未加回内扣 fee 时拒绝。
- 合理的小数位舍入可通过。
- 现有 Hata ETH/MYR gross 4250、fee 8.50、net 4241.50 场景继续通过。
- 现有 FIFO shortfall、reversal、cost lot 测试继续通过。

### 11.3 操作反馈

- 成功写入显示 Success toast，并只在成功后清空表单。
- API 422/409/500 和网络失败显示 Error toast，输入不丢失。
- FastAPI detail 数组转换为可读字段错误。
- toast 可手工关闭；Success 自动消失；Error/Warning 不自动消失。
- 快速开始第二个操作时旧 toast 被安全替换，不残留旧 timer。
- 交易成功但收据失败显示 Warning，不重复创建交易。
- 写入成功但 refresh 失败显示 Warning，不误报写入失败。
- datetime 成功重置为当前时间。

## 12. 验收标准

- 选择 MYR 与 USDT，输入 `MYR 2800` 和 `4.05797 MYR/USDT` 后，USDT 字段自动填入按资产精度计算的值。
- UI 始终显示完整方向，例如 `1 USDT = 4.05797 MYR`；用户无需理解 internal inverse rate。
- 提交 payload 的 `execution_rate` 保持后端 canonical `Buy/Sell` 方向。
- 含 MYR 的 trade 自动填入正确 `gross_value_myr`。
- 前后端不使用二进制浮点产生权威财务值。
- 明显矛盾的 quantity/rate/gross value 无法通过 API 写入。
- 每个用户写操作均有明确 Success、Error 或 Warning popup。
- 写入失败不会清空、关闭或悄悄改变表单；写入成功才 reset。
- 收据部分失败不会造成重复交易风险。
- popup 在桌面、移动端、键盘和读屏场景可用。
- frontend test/lint/build 与 backend ruff/pytest 全部通过。
- 不新增数据库 migration，不改变历史交易，不新增第三方依赖。

## 13. 风险与控制

| 风险 | 控制措施 |
| --- | --- |
| 汇率方向仍被误解 | 动态完整等式 + MYR pair 固定常见报价 + 后端交叉校验 |
| 浮点误差进入账本 | BigInt/scale 字符串运算；后端 Decimal 复核 |
| fee 导致 gross/net 错算 | 明确 `B_gross`、`B_net`、`F_buy`，加入现有 ETH/MYR fee 回归样例 |
| action 结果改动影响大量表单 | 先补“失败不 reset”测试，再逐个迁移调用点 |
| 成功写入但刷新失败导致重复提交 | mutation 与 refresh 分开反馈；前者成功即视为已持久化 |
| toast timer 更新到旧消息 | 每条消息使用 id/key，effect cleanup 旧 timer |
| 新 validator 拒绝合法的 rate 舍入 | 按输入 rate 精度比较并加入小数舍入 golden tests |

## 14. 建议提交拆分

实施时建议拆成两个本地 commit：

1. `Add exact trade amount calculation`
   - 前端 calculator、Trade UI、后端一致性校验及测试。
2. `Add operation result popups`
   - toast、API 错误解析、action 结果传播、失败保留输入及测试。

第 8 节 P1/P2/P3 backlog 应另开任务和独立 commit，不与本轮必做项混在一起。

## 15. 非目标

- 不接入实时行情、交易所 API 或自动下单。
- 不用最新市场价重算历史交易。
- 不修改历史 RateSnapshot 或已有 Trade。
- 不在本轮实现完整 Transactions 分页、Card 表单重构或全站 i18n。
- 不引入 Redux、表单框架、toast 库、decimal 第三方包或新的后端 endpoint，除非实现阶段证明现有方案无法满足正确性。
