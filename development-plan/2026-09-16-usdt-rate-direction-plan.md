# 调整 USDT 交易对汇率显示方向开发计划

- 日期：2026-09-16
- 状态：已完成（2026-09-16）
- 目标：统一 Trade 页面中非 MYR USDT 交易对的显示方向，同时保持 MYR 例外和后端 canonical 汇率契约不变。

## 实施范围

- 非 MYR 且包含 USDT 的交易对统一显示为 `1 非USDT资产 = x USDT`。
- 所有 MYR 交易对继续显示为 `1 非MYR资产 = x MYR`，MYR 规则优先于 USDT 规则。
- 其他交易对保持 `1 Sell asset = x Buy asset`。
- `execution_rate` 继续提交 `buy_quantity / sell_quantity`；不修改 API schema、RateSnapshot、数据库或历史交易。

## 实现方式

- 在 `TradeForm` 中根据显示的 base/quote 资产确定汇率方向。
- 当 Sell asset 是显示汇率的 quote asset 时，用 `sell ÷ displayed rate` 计算 gross buy；否则使用 `sell × displayed rate`。
- 从到账数量反算汇率时使用相同方向规则。
- 提交时继续依据 gross buy 和 sell quantity 生成后端 canonical `execution_rate`。
- 保留现有精确十进制运算、Buy asset 内含手续费扣除、MYR gross 自动计算和最后编辑字段行为。

## 验证

- 覆盖 Sell USDT → Buy 非 MYR、Sell 非 MYR → Buy USDT、USDT/MYR 两种方向、普通交易对、到账数量反算和 Buy asset 内含手续费。
- 运行前端测试、lint、build 以及后端 pytest。
- 前端测试 9 个文件、32 个测试全部通过；lint、build 和后端交易专项测试全部通过。
- 后端全量测试 30 项中 29 项通过；1 项 recurring expense 测试因当前日期超过固定 weekly due date 而失败，与本次改动无关。
