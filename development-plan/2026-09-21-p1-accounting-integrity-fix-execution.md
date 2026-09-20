# P1 记账完整性修复执行记录

依据：`2026-09-21-p1-accounting-integrity-fix-plan.md`

## 提交边界

- [x] P1-0：只读完整性审计与备份门禁
- [x] P1-1：封闭通用记账旁路并统一估值派生
- [x] P1-2：验证 linked card settlement
- [ ] P1-3：由服务器控制退款与 reward rate
- [ ] P1-5：支持多腿卡片表单
- [ ] 完整回归、真实数据库审计基线与最终工作树检查

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
