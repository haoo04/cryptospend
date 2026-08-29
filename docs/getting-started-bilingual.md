# CryptoSpend 新手教学 / Bilingual Getting Started Guide

> 面向第一次运行 CryptoSpend 的用户。界面目前以英文显示，因此本文保留按钮和字段的英文原名，并在旁边提供中文说明。
>
> For first-time CryptoSpend users. The current interface is in English, so this guide keeps the exact English labels and explains them in both Chinese and English.

## 1. 先了解 CryptoSpend / Understand CryptoSpend first

### 中文

CryptoSpend 是一个本地优先的个人加密资产记账工具，默认以马来西亚令吉（MYR）作为报告货币。你可以把银行、现金、交易所、钱包和卡片相关的活动记录到同一个账本，再查看净资产、收入支出、FIFO 成本基础、已实现/未实现盈亏、费用和月度报表。

它不是交易所，也不会替你执行买卖。当前的主要工作方式是：根据交易所、钱包、银行或卡片账单，手动录入已经发生的事实。

### English

CryptoSpend is a local-first personal crypto accounting tool. Malaysian Ringgit (MYR) is the default reporting currency. You can record activity from banks, cash accounts, exchanges, wallets, and cards in one ledger, then review net worth, income and expenses, FIFO cost basis, realized and unrealized gain/loss, fees, and monthly reports.

It is not an exchange and it does not execute trades. The main workflow is to enter completed facts from your exchange, wallet, bank, or card statements.

### 核心概念 / Core concepts

| 概念 / Concept | 中文说明 | English explanation |
| --- | --- | --- |
| Local-first | 数据库默认保存在本机；Google Drive 备份是可选项。 | The database is stored locally by default; Google Drive backup is optional. |
| MYR book amount | 每笔资产活动都会记录一个 MYR 账面金额，用于统一比较不同资产。 | Each asset movement has an MYR book amount so different assets can be compared consistently. |
| Double-entry | 每笔已入账事件都有借方和贷方，账面金额必须平衡。 | Every posted event has a debit and a credit, and the book amounts must balance. |
| FIFO | 卖出或花费资产时，系统按先进先出消耗成本批次。 | When assets are sold or spent, the system consumes cost lots first-in, first-out. |
| Posted / Reversed | 已入账记录不会直接删除；更正时创建冲销事件。 | Posted records are not deleted directly; corrections create reversing events. |
| Available balance | 卡片授权会先减少可用余额，但不立即生成费用。 | A card authorization reduces available balance first, but does not create an expense yet. |

## 2. 开始前 / Before you start

### 中文

建议使用以下环境：

- Windows PowerShell 7。
- Python 3.13；项目 CI 使用此版本。
- Node.js 22；项目 CI 使用此版本。
- 一个可写的项目目录。

项目的重要目录如下：

| 目录 / Directory | 用途 / Purpose |
| --- | --- |
| backend | FastAPI 后端、SQLite 数据库、迁移和后端测试。 |
| frontend | React + TypeScript + Vite 前端。 |
| backend/data | 默认数据库和本地备份目录；通常被 Git 忽略。 |
| docs | 项目文档。 |

### English

Recommended environment:

- Windows PowerShell 7.
- Python 3.13; this is the version used by CI.
- Node.js 22; this is the version used by CI.
- A writable project directory.

The important directories are:

- backend: FastAPI backend, SQLite database, migrations, and backend tests.
- frontend: React, TypeScript, and Vite frontend.
- backend/data: the default database and local backup directory; normally ignored by Git.
- docs: project documentation.

## 3. 一次性安装 / One-time setup

先在项目根目录打开 PowerShell。以下命令中的当前目录假设为项目根目录。

Open PowerShell in the repository root. The commands below assume the current directory is the repository root.

### 3.1 创建后端虚拟环境 / Create the backend virtual environment

~~~powershell
Set-Location .\backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Set-Location ..
~~~

### 3.2 安装前端依赖 / Install frontend dependencies

~~~powershell
npm.cmd --prefix frontend ci
~~~

如果你还想使用根目录提供的“一条命令启动前后端”脚本，再安装根目录的开发依赖：

If you also want to use the root-level “start frontend and backend together” script, install its development dependency too:

~~~powershell
npm.cmd install
~~~

只使用两个终端分别启动时，不需要根目录的开发依赖。

The root dependency is not required when you start the two services in separate terminals.

## 4. 启动应用 / Start the application

### 方案 A：两个终端（推荐理解项目时使用） / Option A: two terminals

第一次启动前，先执行数据库迁移。迁移会创建或升级本地 SQLite 数据库。

Before the first launch, run the database migration. It creates or upgrades the local SQLite database.

终端 1：启动后端 / Terminal 1: start the backend

~~~powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.maintenance migrate
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
~~~

终端 2：启动前端 / Terminal 2: start the frontend

~~~powershell
Set-Location .\frontend
npm.cmd run dev
~~~

在浏览器打开：

Open this URL in your browser:

http://127.0.0.1:5173

可选的后端健康检查：

Optional backend health check:

~~~powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
~~~

预期结果是 status 为 ok。FastAPI 的接口说明也可以在 http://127.0.0.1:8000/docs 查看。

The expected result has status set to ok. FastAPI's API reference is also available at http://127.0.0.1:8000/docs.

### 方案 B：根目录一条命令 / Option B: one root command

如果已经完成迁移并安装了根目录依赖，可以在项目根目录运行：

After migration and installation of the root dependency, run this from the repository root:

~~~powershell
npm.cmd run dev
~~~

这个脚本会同时启动前端和后端。按 Ctrl+C 可以停止它们。

This script starts the frontend and backend together. Press Ctrl+C to stop them.

### 数据库位置 / Database location

默认数据库是 backend/data/cryptospend.db。不要把这个文件或其中的本地凭据提交到 Git。

The default database is backend/data/cryptospend.db. Do not commit this file or local credentials from it to Git.

## 5. 第一次进入应用 / First run in the UI

### 中文

1. 打开左侧导航中的 Overview。
2. 如果看到 FIRST RUN 和 Set up the local ledger，点击 Initialize CryptoSpend。
3. 等待刷新完成。初始化会创建默认 MYR、USD、USDT、BTC、ETH 资产，以及一套核心账户。
4. 如果下拉框为空，先点击初始化，再点击右上角 Refresh。

初始化操作会补齐缺少的默认项目；如果数据库已经初始化，不需要反复点击。

### English

1. Open Overview from the left navigation.
2. If you see FIRST RUN and Set up the local ledger, click Initialize CryptoSpend.
3. Wait for the refresh to finish. Initialization creates the default MYR, USD, USDT, BTC, and ETH assets plus the core accounts.
4. If a selector is empty, initialize first and then click Refresh in the top-right corner.

Initialization fills in missing defaults. You do not need to click it repeatedly after setup.

### 初始化后的默认内容 / Defaults after initialization

| 类型 / Type | 默认项目 / Default items |
| --- | --- |
| 资产 / Assets | MYR, USD, USDT, BTC, ETH |
| 资产账户 / Asset accounts | Bank, Cash, Crypto Wallet |
| 收入账户 / Income accounts | Salary, Other Income |
| 费用账户 / Expense accounts | General Expense, Trading Fees, Network Fees, Withdrawal Fees |
| 其他账户 / Other accounts | Opening Balances, Realized Gain/Loss, Clearing |

## 6. 最短成功路径：记一笔收入 / The shortest successful path: record income

下面的示例假设你收到 1,000 USDT，入账时采用 1 USDT = 4.25 MYR，因此账面金额是 4,250 MYR。

The example below assumes that you received 1,000 USDT and the entry price was 1 USDT = 4.25 MYR, so the book amount is 4,250 MYR.

### 6.1 在 Add transaction 中填写 / Fill in Add transaction

左侧点击 Add transaction，保持 MANUAL 模式，填写：

Click Add transaction on the left, keep MANUAL mode, and enter:

| 字段 / Field | 示例值 / Example value | 填写逻辑 / Why |
| --- | --- | --- |
| Event type | SALARY | 这是收入事实；普通非工资收入可选 INCOME。 / Use INCOME for non-salary income. |
| Occurred at | 收款实际时间 / actual receipt time | 使用账单或收款时间。 / Use the time from the statement or receipt. |
| Description | August salary | 便于在 Transactions 中搜索和识别。 / Makes the event easy to identify later. |
| Debit account | Crypto Wallet | 资产增加。 / The asset account increases. |
| Credit account | Salary | 收入增加。 / Income is recognized. |
| Asset | USDT | 选择收到的资产。 / Select the received asset. |
| Original quantity | 1000 | 资产数量。 / Quantity of the asset. |
| Book amount (MYR) | 4250 | 1000 × 4.25。 / 1000 × 4.25. |
| Asset/MYR rate | 4.25 | 如果有可靠估值就填写。 / Enter it when you have a reliable valuation. |
| Rate source | receipt execution | 记录估值来源。 / Record the valuation source. |
| Category | Salary | 可选分类。 / Optional category. |

点击 Post balanced event。

Click Post balanced event.

### 6.2 检查结果 / Check the result

成功后可以看到：

After a successful post, you should see:

- Overview 的 Net worth (book) 增加 4,250 MYR。
- Accounts 中 Crypto Wallet 出现 1,000 USDT 和 4,250 MYR 账面金额。
- Transactions 中出现状态为 POSTED 的 August salary。
- Portfolio 中出现 USDT 的 FIFO 成本批次，成本基础为 4,250 MYR。

如果 Portfolio 显示 Missing rate，不代表入账失败；它表示系统还没有找到用于当前估值时点的市场价。

If Portfolio shows Missing rate, the posting did not fail. It means no market rate has been recorded for the valuation time.

### 6.3 如果是应用启动前已有的持仓 / If the holding existed before using the app

不要把历史持仓伪装成工资。使用 MANUAL 模式的 OPENING_BALANCE：

Do not label an existing holding as salary. Use OPENING_BALANCE in MANUAL mode:

| 字段 / Field | 示例 / Example |
| --- | --- |
| Debit account | Crypto Wallet |
| Credit account | Opening Balances |
| Asset | ETH |
| Original quantity | 0.25 |
| Book amount (MYR) | 4000 |

这样系统会把 0.25 ETH 作为成本为 4,000 MYR 的初始 FIFO 批次。

This creates an opening FIFO lot of 0.25 ETH with a MYR cost basis of 4,000.

## 7. 三种录入模式怎么选 / Choosing among the three entry modes

| 模式 / Mode | 适用场景 / Use it for | 关键结果 / Key result |
| --- | --- | --- |
| MANUAL | 工资、其他收入、普通费用、期初余额和简单内部记账。 / Salary, income, expenses, opening balances, and simple balanced entries. | 你选择借方和贷方账户，服务端生成平衡事件。 / The server creates a balanced event from the debit and credit accounts. |
| TRADE | 一种资产换成另一种资产，例如 ETH 换 MYR。 / One asset exchanged for another, such as ETH for MYR. | 系统应用 FIFO 处置和交易费用。 / FIFO disposal and trading fees are applied. |
| TRANSFER | 自己名下账户之间移动资产，例如钱包转交易所。 / Move assets between accounts you own, such as wallet to exchange. | 保留原成本批次；实际网络费单独计算。 / Original cost lots are preserved; actual network fees are separate. |

### 重要输入规则 / Important input rules

- 手工事件的 Book amount (MYR) 是统一的 MYR 估值，不是把原始数量再填一次。
- TRADE 的 Net buy quantity 是实际收到的净数量。
- TRADE 的 Execution rate 约定为 buy asset / sell asset。
- TRANSFER 的 Sent quantity 和 Received quantity 可以不同；差额通常表示实际扣除的费用或链路差异。
- 费用数量和费用 MYR 金额都要使用非负数；交易数量、转账数量和卡片金额必须为正数。

- MANUAL Book amount (MYR) is the common MYR valuation, not another copy of the asset quantity.
- In TRADE, Net buy quantity is the net quantity actually received.
- TRADE Execution rate uses the convention buy asset / sell asset.
- TRANSFER Sent quantity and Received quantity may differ; the difference usually represents a fee or a path difference.
- Fee quantities and fee MYR values are non-negative; trade, transfer, and card amounts must be positive.

## 8. 示例：记录一次交易 / Example: record a trade

假设你已有一笔 0.25 ETH、成本 4,000 MYR 的初始批次，之后以 4,250 MYR 的总价值卖出，支付 8.50 MYR 交易费，最终收到 4,241.50 MYR。

Assume you already have an opening lot of 0.25 ETH with a cost basis of 4,000 MYR. You sell it for a gross value of 4,250 MYR, pay an 8.50 MYR trading fee, and receive 4,241.50 MYR.

在 Add transaction 中切换到 TRADE：

In Add transaction, switch to TRADE:

| 字段 / Field | 示例值 / Example value |
| --- | --- |
| Exchange account | Crypto Wallet |
| Sell asset / Sell quantity | ETH / 0.25 |
| Buy asset / Net buy quantity | MYR / 4241.50 |
| Execution rate | 17000 |
| Gross transaction value (MYR) | 4250 |
| Gain/loss account | Realized Gain/Loss |
| Description | Hata ETH/MYR sale |
| Fee type | TRADING_FEE |
| Fee asset / Fee quantity | MYR / 8.50 |
| Fee value (MYR) | 8.50 |
| Treatment | REDUCE_PROCEEDS |
| Expense account | Trading Fees |
| Fee is already included in the funding/net amount | 勾选 / checked |

点击 Post trade。

Click Post trade.

在这个例子中，系统会把总价值 4,250、交易费 8.50 和实际收到的 4,241.50 分开记录。因为原始成本是 4,000 MYR，示例中的已实现盈亏为 250 MYR；你的结果会根据实际 FIFO 批次不同而变化。

The system keeps the gross value of 4,250, the 8.50 fee, and the 4,241.50 received amount distinct. With a 4,000 MYR cost basis, the example produces 250 MYR of realized gain; your result will depend on your actual FIFO lots.

不要把一次资产兑换同时录成一笔 MANUAL 费用和一笔 TRADE，否则可能重复计算。

Do not record the same asset exchange as both a MANUAL expense and a TRADE, or you may count it twice.

## 9. 示例：记录钱包到交易所的转账 / Example: transfer from wallet to exchange

### 9.1 先创建目标账户（如需要） / Create the destination account if needed

进入 Accounts，选择 Add account：

Go to Accounts and choose Add account:

| 字段 / Field | 示例值 / Example value |
| --- | --- |
| Name | Hata |
| Type | ASSET |
| Spending channel | EXCHANGE |
| Provider | HATA |

### 9.2 录入 TRANSFER / Enter the TRANSFER

切换到 Add transaction → TRANSFER：

Switch to Add transaction → TRANSFER:

| 字段 / Field | 示例值 / Example value |
| --- | --- |
| Asset | USDT |
| Source account | Crypto Wallet |
| Destination account | Hata |
| Sent quantity / Received quantity | 1000 / 1000 |
| Network | Ethereum |
| Transaction hash | 0xabc（示例） / example |
| Gain/loss account | Realized Gain/Loss |
| Description | Wallet to Hata |
| Fee type | NETWORK_FEE |
| Fee asset / Fee quantity | ETH / 0.0003 |
| Fee value (MYR) | 3 |
| Expense account | Network Fees |

点击 Post transfer。

Click Post transfer.

转账会把原 USDT 成本批次移动到 Hata，并保留原取得时间和成本基础。0.0003 ETH 的网络费才会减少钱包中的 ETH 数量，并计入 Network Fees。

The transfer moves the original USDT cost lot to Hata while preserving its acquisition date and basis. Only the 0.0003 ETH network fee reduces the wallet's ETH quantity and is reported under Network Fees.

## 10. 更正记录：使用冲销 / Correcting a record with reversal

### 中文

如果已经 POSTED 的记录有误：

1. 打开 Transactions。
2. 点击该事件右侧的 Inspect 查看详情。
3. 在详情面板中点击 Reverse event。
4. 在提示框中填写原因，例如 duplicate receipt 或 wrong destination。
5. 刷新后检查原事件状态和报表。

冲销不会修改历史记录的原始内容，也不是物理删除。原事件会标记为 REVERSED，并生成一笔对应的反向事件。一个事件不能重复冲销。

### English

When a POSTED record is wrong:

1. Open Transactions.
2. Click Inspect next to the event to view its details.
3. Click Reverse event in the detail panel.
4. Enter a reason, such as duplicate receipt or wrong destination.
5. Refresh and verify the original event status and reports.

Reversal does not rewrite or physically delete the original record. The original event becomes REVERSED and a corresponding reverse event is created. An event cannot be reversed twice.

## 11. 卡片流程：授权、结算、退款、奖励 / Card flow: authorization, settlement, refund, reward

卡片模块位于 Card costs。它把外部卡片状态与正式账本事件分开。

The card module is under Card costs. It separates external card states from posted ledger events.

| 状态 / Action | 中文 | English |
| --- | --- | --- |
| AUTHORIZE | 记录预授权 hold，只减少 available balance，不产生费用。 | Records an authorization hold, reduces available balance only, and creates no expense. |
| SETTLE | 商户真正扣款时入账，产生费用并应用 FIFO。 | Posts the real capture, recognizes the expense, and applies FIFO. |
| REFUND | 记录实际退款；退回资产可以与原扣款资产不同。 | Records an actual refund; the returned asset may differ from the original funding asset. |
| REWARD | 先保存 pending reward，到账后再 credit；到账前不降低卡片成本。 | Save a pending reward first, then credit it; pending rewards do not lower card cost. |

### 11.1 授权示例 / Authorization example

假设 Crypto Wallet 有 100 USDT。Bybit 卡片预授权一笔 100 MYR 的 Dinner 消费，系统暂时锁定 23.96 USDT，锁定价值 101.83 MYR。

Assume Crypto Wallet has 100 USDT. A Bybit card authorizes a 100 MYR Dinner purchase, temporarily holding 23.96 USDT valued at 101.83 MYR.

在 Card costs → AUTHORIZE 中填写：

In Card costs → AUTHORIZE, enter:

| 字段 / Field | 示例值 / Example value |
| --- | --- |
| Provider / Provider account ID | Bybit / card-main |
| Card account | Crypto Wallet |
| Merchant / Merchant country | Dinner / MY |
| Merchant asset / Merchant amount | MYR / 100 |
| Merchant value MYR | 100 |
| Billing asset / Billing amount | USD / 23.70 |
| Hold account / Hold asset | Crypto Wallet / USDT |
| Hold quantity / Hold value MYR | 23.96 / 101.83 |

点击 Create hold。预期结果是 Book balance 仍为 100 USDT，但 Available balance 变为 76.04 USDT；Income/Expense 不应因授权本身增加费用。

Click Create hold. The expected result is that Book balance remains 100 USDT while Available balance becomes 76.04 USDT. Authorization alone should not increase Income/Expense.

### 11.2 结算示例 / Settlement example

在 SETTLE 中选择对应的授权，或选择 Manual settlement 直接录入正式扣款：

In SETTLE, select the authorization, or choose Manual settlement to enter a completed capture directly:

| 字段 / Field | 示例值 / Example value |
| --- | --- |
| Merchant asset / Merchant amount / Merchant value MYR | MYR / 100 / 100 |
| Billing asset / Billing amount | USD / 23.70 |
| Reference FX rate | 4.25 |
| Expense account | General Expense |
| Gain/loss account | Realized Gain/Loss |
| Funding account / Funding asset | Crypto Wallet / USDT |
| Actual deducted quantity | 23.96 |
| Settlement value MYR | 100.89 |
| Reference value MYR | 101.83 |
| Actual conversion rate | 4.21076794657763 |
| Optional fee | 0.21 USDT / 0.89 MYR |
| Fee treatment | EXPENSED; included in funding quantity |
| Final capture; release hold | 勾选 / checked |

点击 Post settlement。结算会生成正式费用，并释放对应的 hold。

Click Post settlement. Settlement creates the formal expense and releases the corresponding hold.

### 11.3 退款和奖励 / Refunds and rewards

- REFUND 中要填写 Purchase、Refund value MYR、Receiving account、Returned asset、Returned quantity、Transaction value MYR 和 Reference value MYR。部分退款不要勾选 Full refund。
- REWARD 中先点击 Save pending；只有奖励实际到账后，才使用 Credit reward 填写 MYR 价值、Asset/MYR rate 和估值来源。

- In REFUND, fill Purchase, Refund value MYR, Receiving account, Returned asset, Returned quantity, Transaction value MYR, and Reference value MYR. Leave Full refund unchecked for a partial refund.
- In REWARD, click Save pending first. Use Credit reward only after the reward is actually credited, with its MYR value, Asset/MYR rate, and valuation source.

## 12. 查看组合和报表 / Review portfolio and reports

### 12.1 Portfolio

Portfolio 显示每项资产的 Quantity、Cost basis、Average cost、Market value、Unrealized、Realized 和 Quality。

Portfolio shows Quantity, Cost basis, Average cost, Market value, Unrealized, Realized, and Quality for each asset.

如果需要市场估值：

To add a market valuation:

1. 打开 Portfolio。
2. 在 Add market rate 中选择 Base asset 和 Quote asset。
3. 输入 Rate。约定是 quote asset / base asset，例如 USDT → MYR 的 4.30 表示 1 USDT = 4.30 MYR。
4. 填写 Observed at、Source 和 Confidence。
5. 点击当前按钮文字为 Save snapshot 的按钮。

1. Open Portfolio.
2. In Add market rate, choose Base asset and Quote asset.
3. Enter Rate. The convention is quote asset / base asset; for example, 4.30 for USDT → MYR means 1 USDT = 4.30 MYR.
4. Fill in Observed at, Source, and Confidence.
5. Click the button currently labeled Save snapshot.

示例：如果持有 1,000 USDT，成本是 4,250 MYR，新增 4.30 的市场价后，市场价值约为 4,300 MYR，未实现盈亏约为 50 MYR。实际结果还取决于估值时间和账户状态。

Example: if you hold 1,000 USDT with a 4,250 MYR basis, adding a market rate of 4.30 gives an approximate market value of 4,300 MYR and unrealized gain of 50 MYR. The actual result also depends on the valuation time and account state.

### 12.2 Monthly & as-of

Reports → Monthly & as-of 提供按月的：

Reports → Monthly & as-of provides:

- Net worth at month end
- Income
- Gross spending
- Net spending
- Spending by channel
- Fee leakage，包括 explicit 和 derived 部分
- 截止月末的 Portfolio valuation

操作步骤 / Steps:

1. 选择 Month，例如 2026-08。
2. 点击 Load month。
3. 检查月份边界和显示的 Asia/Kuala_Lumpur 时区。
4. 确认内容后点击 Save snapshot，保存不可变的月度快照。

1. Choose a Month, such as 2026-08.
2. Click Load month.
3. Check the period boundary and the displayed Asia/Kuala_Lumpur timezone.
4. After review, click Save snapshot to save an immutable monthly snapshot.

### 12.3 Fund journeys

Fund journeys 用于把多笔账本事件串成一个资金路径，例如“工资到账 → 交易 → 提现到交易所”。

Fund journeys connect multiple ledger events into one path, such as “salary received → trade → withdrawal to an exchange”.

示例 / Example:

| 操作 / Action | 示例 / Example |
| --- | --- |
| Create journey → Name | Salary to Hata MYR |
| Journey type | WITHDRAWAL |
| Allocation method | Manual exact event allocation |
| Confidence | EXACT |
| 第一个事件 / first event | 100 USDT salary，分配角色 INPUT，价值 425 MYR |
| 第二个事件 / second event | 交易收到 416.5 MYR，分配角色 OUTPUT，价值 416.5 MYR |
| 费用 / cost | 8.5 MYR，分配角色 COST |

角色可选 INPUT、INTERMEDIATE、OUTPUT、COST。只有已经 POSTED 且未被冲销的事件适合分配。

Roles are INPUT, INTERMEDIATE, OUTPUT, and COST. Allocate only POSTED events that have not been reversed.

### 12.4 Channel comparison

Channel comparison 在固定金额、时间、参考汇率和返现资格下，对比实际路径与模拟路径。不要把不同时间或不同金额的路径直接比较。

Channel comparison compares actual and simulated paths under the same amount, time, reference rate, and cashback eligibility. Do not compare paths with different conditions.

示例：固定 100 MYR、参考价 4.25：

Example: fixed amount 100 MYR and reference rate 4.25:

| 路径 / Path | Mode | Explicit cost | Derived deviation | Cashback | 结果 / Result |
| --- | --- | ---: | ---: | ---: | --- |
| Bank withdrawal | ACTUAL | 1.00 | 0.50 | 0 | Effective cost 1.50 MYR |
| Alternative exchange | SIMULATED | 0.50 | 0.25 | 1.00 | Effective cost -0.25 MYR |

有效成本大致等于 explicit cost + derived deviation - cashback；返现高于其他成本时，结果可能为负数。SIMULATED 路径应把 Confidence 设为 ESTIMATED，并注明 Evidence source。

Effective cost is approximately explicit cost + derived deviation - cashback. It can be negative when cashback exceeds the other costs. Mark a SIMULATED path as ESTIMATED and provide an Evidence source.

## 13. Google Drive 备份（可选） / Google Drive backup (optional)

### 中文

不配置 Google Drive 也不影响本地记账。若要启用：

1. 在 Google Cloud 创建或选择项目。
2. 启用 Google Drive API。
3. 配置 OAuth consent screen。
4. 创建 Desktop app 类型的 OAuth client，并把下载的 JSON 放在仓库外，例如 C:/private/google-drive-client.json。
5. 在 backend/.env 中加入：

~~~dotenv
CRYPTOSPEND_GOOGLE_CLIENT_SECRETS_FILE=C:/private/google-drive-client.json
~~~

6. 重启后端。
7. 打开 Settings → Google Drive → Connect Google Drive。
8. 在浏览器中授权后，返回应用点击 Backup database。

备份会以新的时间戳文件上传到 CryptoSpend Backups 文件夹。OAuth client JSON 不要提交；本地 refresh token 默认保存在 backend/data/google-drive-token.dpapi，并由 Windows DPAPI 保护。

### English

Local accounting works without Google Drive. To enable it:

1. Create or select a project in Google Cloud.
2. Enable the Google Drive API.
3. Configure the OAuth consent screen.
4. Create a Desktop app OAuth client and store the downloaded JSON outside the repository, for example C:/private/google-drive-client.json.
5. Add this to backend/.env:

~~~dotenv
CRYPTOSPEND_GOOGLE_CLIENT_SECRETS_FILE=C:/private/google-drive-client.json
~~~

6. Restart the backend.
7. Open Settings → Google Drive → Connect Google Drive.
8. Approve access in the browser, then click Backup database in the app.

Each backup is uploaded as a new timestamped file in the CryptoSpend Backups folder. Do not commit the OAuth client JSON. The refresh token is normally stored as backend/data/google-drive-token.dpapi and protected by Windows DPAPI.

### 本地数据库备份和恢复 / Local database backup and restore

即使不使用云端，也可以在后端目录执行 SQLite 快照：

You can create a SQLite snapshot from the backend directory even without cloud backup:

~~~powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.maintenance backup C:\private\cryptospend-backup.db
~~~

恢复前先停止后端，并把当前数据库复制到一个安全位置；恢复目标是默认的 backend/data/cryptospend.db：

Stop the backend before restoring and copy the current database to a safe location first. Restore targets the default backend/data/cryptospend.db:

~~~powershell
.\.venv\Scripts\python.exe -m app.maintenance restore C:\private\cryptospend-backup.db
~~~

恢复后重新启动后端，必要时再次执行 migrate。

Restart the backend after restoring and run migrate again if needed.

## 14. 常见问题 / Troubleshooting

| 现象 / Symptom | 处理 / Fix |
| --- | --- |
| 浏览器打不开 5173 | 确认前端终端仍在运行；运行 npm.cmd run dev；不要关闭 Vite 终端。 / Make sure the frontend terminal is still running and restart Vite if needed. |
| 页面提示 Failed to fetch | 检查后端 8000 端口和 /api/health；两个服务都必须运行。 / Check port 8000 and /api/health; both services must be running. |
| 页面一直显示 FIRST RUN | 先完成 migrate，再点击 Initialize CryptoSpend，最后 Refresh。 / Run migrate, initialize the app, then Refresh. |
| 资产或账户下拉框为空 | 初始化尚未完成，或请求失败；先看页面错误提示和后端终端。 / Initialization or loading failed; inspect the UI error and backend terminal. |
| 交易被拒绝或 FIFO 不完整 | 先录入历史取得、工资或 OPENING_BALANCE；卖出数量不能超过可用成本批次。 / Record acquisitions, salary, or OPENING_BALANCE first; the sold quantity cannot exceed available cost lots. |
| Portfolio 显示 Missing rate | 在 Portfolio 添加对应的 market rate，并检查 Base/Quote 方向。 / Add a market rate and check the Base/Quote direction. |
| 费用好像被计算两次 | 交易费是否已经包含在 Net buy quantity 或 funding quantity 中；同一事实只录入一次。 / Check whether the fee is included in the net or funding quantity and record the fact only once. |
| Google Drive 显示 NOT CONFIGURED | 检查 backend/.env 的 JSON 路径，确保文件在仓库外，并重启后端。 / Check the JSON path in backend/.env, keep the file outside the repository, and restart the backend. |
| 端口已被占用 | 关闭之前启动的前端/后端终端，确认没有重复运行的服务。 / Stop older frontend/backend processes and avoid running duplicate services. |

## 15. 给首次使用者的建议 / Practical advice for first-time users

### 中文

1. 先只录入一笔小额或历史示例，确认 Overview、Accounts、Transactions 和 Portfolio 的结果，再批量录入。
2. 保留交易所、钱包和银行卡的原始账单；Description、External ID、Transaction hash 和 Evidence source 尽量填写。
3. 真实持仓从 OPENING_BALANCE 或实际取得事件开始，避免用当前市价代替历史成本。
4. 费用是事实的一部分。区分交易费、网络费、提现费、兑换偏差和返现，不要把它们都塞进一个数字。
5. 在做月度结算前先保存本地数据库备份；Google Drive 备份是额外保护，不替代核对。

### English

1. Start with one small or historical example and verify Overview, Accounts, Transactions, and Portfolio before entering everything.
2. Keep original exchange, wallet, and bank statements. Fill in Description, External ID, Transaction hash, and Evidence source where possible.
3. Start real holdings with OPENING_BALANCE or actual acquisition events; do not replace historical cost with today's market price.
4. Treat fees as facts. Keep trading fees, network fees, withdrawal fees, conversion deviation, and cashback distinct.
5. Create a local database backup before monthly close. Google Drive is an additional safeguard, not a substitute for reconciliation.

完成这些步骤后，你已经可以完成 CryptoSpend 的核心循环：初始化账本 → 录入事实 → 检查平衡 → 查看 FIFO 和 MYR 报表 → 备份数据库。

After these steps, you can complete the core CryptoSpend loop: initialize the ledger → record facts → check balance → review FIFO and MYR reports → back up the database.
