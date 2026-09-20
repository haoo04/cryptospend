# P1 记账完整性修复执行记录

依据：`2026-09-21-p1-accounting-integrity-fix-plan.md`

## 提交边界

- [x] P1-0：只读完整性审计与备份门禁
- [x] P1-1：封闭通用记账旁路并统一估值派生
- [x] P1-2：验证 linked card settlement
- [x] P1-3：由服务器控制退款与 reward rate
- [x] P1-5：支持多腿卡片表单
- [x] 完整回归、真实数据库审计基线与最终工作树检查

## 约束

- 不修改历史总账、cost lot、disposal 或退款事件。
- 不新增数据库字段或迁移。
- 每个逻辑单元独立本地提交，不推送远程。
- 保留工作区中任务开始前已有的未跟踪文件。

## 验证记录

- P1-0 临时数据库样本：`ruff check app tests`、`pytest tests/test_foundation.py` 通过。
- P1-0 真实库备份：系统临时目录 `cryptospend-p1-accounting-integrity-20260921/pre-p1-integrity.db`，备份 integrity check 通过。
- P1-0 真实库基线：同目录 `before.json`，exit code 2；AUD-01=1、AUD-03=1、AUD-04=2，共 4 条待人工核对记录。
- 真实数据库、备份和审计 JSON 不纳入 Git。
- P1-1：后端 Ruff 与 11 个相关后端测试通过；前端 lint、手工录入 3 个测试和 TypeScript 检查通过。
- P1-2：后端 Ruff 通过；卡片授权 hold 与 linked settlement 身份/最终结算零副作用测试通过（2 个测试）。
- P1-3：后端 Ruff 与 6 个卡片测试通过；退款总额、状态重算、退款撤销、expense account 派生及 reward rate 冲突校验均覆盖。
- P1-5：卡片前端 4 个工作流测试、TypeScript、Lint、Prettier 通过；前端串行全量 45 个测试通过；Vite 生产构建在系统临时目录通过。后端卡片测试扩展为 7 个，覆盖两资金腿、两退款腿和多费用。
- 全量回归记录：后端 `37 passed, 1 failed`，唯一失败是既有 `test_recurring_expense_list_summary_and_validation` 的固定日期 overdue 断言（当前日期导致 `1` vs 预期 `0`）；前端默认并行模式有 2 个既有 App 初始化测试受共享状态影响，串行模式为 `45 passed`。
- 修复后真实库只读审计：after JSON 仍为 4 条既有记录，规则与 event IDs 与 before JSON 完全一致（AUD-01=1、AUD-03=1、AUD-04=2）；本轮未修改真实账务数据。
- 最终提交前工作树检查：任务范围内改动均已提交；保留任务开始前已有的未跟踪文档、根 `node_modules/`、根 `package-lock.json` 和 `开发规划.md`。
