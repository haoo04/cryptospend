import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import type { Account, Asset, CardCost, CardRecord, Category } from './api'
import { formatMyr, localDateTimeValue } from './format'

type CardMode = 'OVERVIEW' | 'AUTHORIZE' | 'SETTLE' | 'REFUND' | 'REWARD'

type Props = {
  assets: Asset[]
  accounts: Account[]
  categories: Category[]
  cards: CardRecord[]
  costs: CardCost[]
  busy: boolean
  onAuthorize: (payload: Record<string, unknown>) => Promise<void>
  onReverseAuthorization: (id: string) => Promise<void>
  onSettle: (payload: Record<string, unknown>) => Promise<void>
  onRefund: (id: string, payload: Record<string, unknown>) => Promise<void>
  onReward: (id: string, payload: Record<string, unknown>) => Promise<void>
  onCreditReward: (id: string, payload: Record<string, unknown>) => Promise<void>
}

function values(form: HTMLFormElement) {
  const data = new FormData(form)
  return (key: string) => String(data.get(key) ?? '')
}

function assetOptions(assets: Asset[]) {
  return assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol} · {asset.name}</option>)
}

function accountOptions(accounts: Account[], type: string) {
  return accounts.filter((account) => account.account_type === type).map((account) => (
    <option value={account.id} key={account.id}>{account.name}</option>
  ))
}

function categoryOptions(categories: Category[], kind: Category['kind']) {
  return categories.filter((category) => category.active && category.kind === kind).map((category) => (
    <option value={category.id} key={category.id}>{category.name}</option>
  ))
}

export default function CardCenter(props: Props) {
  const [mode, setMode] = useState<CardMode>('OVERVIEW')
  return (
    <div className="stack">
      <section className="panel card-center">
        <div className="mode-tabs card-tabs">
          {(['OVERVIEW', 'AUTHORIZE', 'SETTLE', 'REFUND', 'REWARD'] as const).map((item) => (
            <button type="button" className={mode === item ? 'active' : ''} onClick={() => setMode(item)} key={item}>
              {item}
            </button>
          ))}
        </div>
        {mode === 'OVERVIEW' && <CardOverview {...props} />}
        {mode === 'AUTHORIZE' && <AuthorizationForm {...props} />}
        {mode === 'SETTLE' && <SettlementForm {...props} />}
        {mode === 'REFUND' && <RefundForm {...props} />}
        {mode === 'REWARD' && <RewardForms {...props} />}
      </section>
    </div>
  )
}

function CardOverview({ cards, costs, assets, onReverseAuthorization, busy }: Props) {
  const assetSymbols = Object.fromEntries(assets.map((asset) => [asset.id, asset.symbol]))
  return (
    <>
      <div className="section-title">
        <div><span className="eyebrow">SETTLED ECONOMICS</span><h2>Card cost waterfall</h2></div>
        <span className="count">{costs.length}</span>
      </div>
      <div className="card-cost-grid">
        {costs.map((cost) => (
          <article className="card-cost" key={cost.id}>
            <div className="card-cost-head">
              <div><span>{cost.provider}</span><h3>{cost.merchant_name}</h3></div>
              <span className={`pill ${cost.status.toLowerCase()}`}>{cost.status}</span>
            </div>
            <div className="waterfall">
              <div><span>Merchant value</span><strong>{formatMyr(cost.merchant_value_myr)}</strong></div>
              <div><span>Funding reference</span><strong>{formatMyr(cost.funding_value_myr)}</strong></div>
              {cost.fees.map((fee) => <div key={fee.component_type}><span>{fee.component_type.replaceAll('_', ' ')}</span><strong>{formatMyr(fee.value_myr)}</strong></div>)}
              {cost.fx_deviation_myr !== null && <div><span>FX deviation</span><strong>{formatMyr(cost.fx_deviation_myr)}</strong></div>}
              {cost.conversion_deviation_myr !== null && <div><span>Conversion deviation</span><strong>{formatMyr(cost.conversion_deviation_myr)}</strong></div>}
              {cost.refunded_value_myr !== '0' && <div className="offset"><span>Refunded assets</span><strong>− {formatMyr(cost.refunded_value_myr)}</strong></div>}
              {cost.credited_cashback_value_myr !== '0' && <div className="offset"><span>Credited cashback</span><strong>− {formatMyr(cost.credited_cashback_value_myr)}</strong></div>}
              <div className="total"><span>Net economic cost</span><strong>{formatMyr(cost.net_economic_cost_myr)}</strong></div>
            </div>
            <div className="funding-tags">{cost.funding_legs.map((leg) => <span key={`${leg.asset_id}-${leg.quantity}`}>{leg.quantity} {leg.asset_symbol}</span>)}</div>
            <small>{cost.breakdown_confidence} breakdown · {new Date(cost.settled_at).toLocaleDateString()}</small>
          </article>
        ))}
        {!costs.length && <div className="empty">Settled purchases will show their cost breakdown here.</div>}
      </div>
      <div className="section-title card-history-title">
        <div><span className="eyebrow">EXTERNAL STATE</span><h2>Authorizations, captures and refunds</h2></div>
      </div>
      <div className="table-wrap card-history">
        <table>
          <thead><tr><th>Provider</th><th>Type</th><th>Merchant</th><th>Amount</th><th>Status</th><th>Hold / action</th></tr></thead>
          <tbody>{cards.map((card) => (
            <tr key={card.id}>
              <td>{card.provider}</td><td>{card.transaction_type}</td><td>{card.merchant_name}</td>
              <td>{card.merchant_amount} {assetSymbols[card.merchant_asset_id] ?? ''}</td>
              <td><span className={`pill ${card.status.toLowerCase()}`}>{card.status}</span></td>
              <td>{card.status === 'AUTHORIZED' ? <button className="text-button" disabled={busy} onClick={() => void onReverseAuthorization(card.id)}>Reverse hold</button> : card.hold?.status ?? '—'}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </>
  )
}

function AuthorizationForm({ assets, accounts, busy, onAuthorize }: Props) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const value = values(form)
    await onAuthorize({
      provider: value('provider'), provider_account_id: value('provider_account_id'), external_id: value('external_id') || null,
      card_account_id: value('card_account_id'), merchant_name: value('merchant_name'), merchant_country: value('merchant_country') || null,
      merchant_asset_id: value('merchant_asset_id'), merchant_amount: value('merchant_amount'), billing_asset_id: value('billing_asset_id'),
      billing_amount: value('billing_amount'), merchant_value_myr: value('merchant_value_myr'), hold_account_id: value('hold_account_id'),
      hold_asset_id: value('hold_asset_id'), hold_amount: value('hold_amount'), hold_value_myr: value('hold_value_myr'),
      authorized_at: new Date(value('authorized_at')).toISOString(),
    })
    form.reset()
  }
  return (
    <><div className="section-title"><div><span className="eyebrow">NO LEDGER ENTRY</span><h2>Record authorization hold</h2></div></div>
      <p className="form-intro">Authorization reduces available balance only. Settlement later creates the expense and FIFO disposal.</p>
      <form onSubmit={(event) => void submit(event)}>
        <label>Provider<input name="provider" placeholder="Bybit" required /></label><label>Provider account ID<input name="provider_account_id" required /></label>
        <label>External ID<input name="external_id" /></label><label>Authorized at<input name="authorized_at" type="datetime-local" defaultValue={localDateTimeValue()} required /></label>
        <label>Card account<select name="card_account_id" required><option value="">Select</option>{accountOptions(accounts, 'ASSET')}</select></label>
        <label>Merchant<input name="merchant_name" required /></label><label>Merchant country<input name="merchant_country" maxLength={2} placeholder="MY" /></label>
        <label>Merchant asset<select name="merchant_asset_id" required><option value="">Select</option>{assetOptions(assets)}</select></label>
        <label>Merchant amount<input name="merchant_amount" inputMode="decimal" required /></label><label>Merchant value MYR<input name="merchant_value_myr" inputMode="decimal" required /></label>
        <label>Billing asset<select name="billing_asset_id" required><option value="">Select</option>{assetOptions(assets)}</select></label><label>Billing amount<input name="billing_amount" inputMode="decimal" required /></label>
        <label>Hold account<select name="hold_account_id" required><option value="">Select</option>{accountOptions(accounts, 'ASSET')}</select></label><label>Hold asset<select name="hold_asset_id" required><option value="">Select</option>{assetOptions(assets)}</select></label>
        <label>Hold quantity<input name="hold_amount" inputMode="decimal" required /></label><label>Hold value MYR<input name="hold_value_myr" inputMode="decimal" required /></label>
        <div className="wide form-actions"><button className="primary" disabled={busy}>Create hold</button></div>
      </form></>
  )
}

function SettlementForm({ assets, accounts, categories, cards, busy, onSettle }: Props) {
  const authorizations = cards.filter((card) => ['AUTHORIZED', 'PARTIALLY_SETTLED'].includes(card.status))
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const value = values(form)
    const feeAmount = value('fee_amount')
    await onSettle({
      authorization_id: value('authorization_id') || null, provider: value('provider'), provider_account_id: value('provider_account_id'), external_id: value('external_id') || null,
      card_account_id: value('card_account_id'), merchant_name: value('merchant_name'), merchant_country: value('merchant_country') || null,
      merchant_asset_id: value('merchant_asset_id'), merchant_amount: value('merchant_amount'), billing_asset_id: value('billing_asset_id'), billing_amount: value('billing_amount'),
      merchant_value_myr: value('merchant_value_myr'), reference_fx_rate: value('reference_fx_rate') || null, expense_account_id: value('expense_account_id'), category_id: value('category_id'),
      gain_loss_account_id: value('gain_loss_account_id'), settled_at: new Date(value('settled_at')).toISOString(), final_capture: value('final_capture') === 'on',
      funding_legs: [{ account_id: value('funding_account_id'), asset_id: value('funding_asset_id'), quantity: value('funding_quantity'), transaction_value_myr: value('funding_transaction_value_myr'), reference_value_myr: value('funding_reference_value_myr'), actual_conversion_rate: value('actual_conversion_rate') || null }],
      fees: feeAmount ? [{ component_type: value('fee_type'), asset_id: value('fee_asset_id'), amount: feeAmount, value_myr: value('fee_value_myr'), accounting_treatment: 'EXPENSED', included_in_funding_amount: value('fee_included') === 'on', expense_account_id: value('fee_expense_account_id'), funding_account_id: value('fee_funding_account_id') || null }] : [],
    })
    form.reset()
  }
  return (
    <><div className="section-title"><div><span className="eyebrow">POSTED CARD EVENT</span><h2>Settle card purchase</h2></div></div>
      <p className="form-intro">Funding transaction values must equal merchant value plus fees already included in the deducted asset.</p>
      <form onSubmit={(event) => void submit(event)}>
        <label>Authorization<select name="authorization_id"><option value="">Manual settlement</option>{authorizations.map((card) => <option value={card.id} key={card.id}>{card.provider} · {card.merchant_name}</option>)}</select></label>
        <label>Settled at<input name="settled_at" type="datetime-local" defaultValue={localDateTimeValue()} required /></label>
        <label>Provider<input name="provider" placeholder="Bybit" required /></label><label>Provider account ID<input name="provider_account_id" required /></label><label>Settlement external ID<input name="external_id" /></label>
        <label>Card account<select name="card_account_id" required><option value="">Select</option>{accountOptions(accounts, 'ASSET')}</select></label>
        <label>Merchant<input name="merchant_name" required /></label><label>Country<input name="merchant_country" maxLength={2} /></label>
        <label>Merchant asset<select name="merchant_asset_id" required><option value="">Select</option>{assetOptions(assets)}</select></label><label>Merchant amount<input name="merchant_amount" inputMode="decimal" required /></label>
        <label>Billing asset<select name="billing_asset_id" required><option value="">Select</option>{assetOptions(assets)}</select></label><label>Billing amount<input name="billing_amount" inputMode="decimal" required /></label>
        <label>Merchant value MYR<input name="merchant_value_myr" inputMode="decimal" required /></label><label>Reference FX rate<input name="reference_fx_rate" inputMode="decimal" /><small>merchant asset / billing asset</small></label>
        <label>Expense account<select name="expense_account_id" required><option value="">Select</option>{accountOptions(accounts, 'EXPENSE')}</select></label><label>Category<select name="category_id" required><option value="">Select</option>{categoryOptions(categories, 'EXPENSE')}</select></label><label>Gain/loss account<select name="gain_loss_account_id" required><option value="">Select</option>{accountOptions(accounts, 'GAIN_LOSS')}</select></label>
        <fieldset className="wide fee-fields"><legend>Funding leg</legend>
          <label>Account<select name="funding_account_id" required><option value="">Select</option>{accountOptions(accounts, 'ASSET')}</select></label><label>Asset<select name="funding_asset_id" required><option value="">Select</option>{assetOptions(assets)}</select></label>
          <label>Actual deducted quantity<input name="funding_quantity" inputMode="decimal" required /></label><label>Settlement value MYR<input name="funding_transaction_value_myr" inputMode="decimal" required /></label>
          <label>Reference value MYR<input name="funding_reference_value_myr" inputMode="decimal" required /></label><label>Actual conversion rate<input name="actual_conversion_rate" inputMode="decimal" /></label>
        </fieldset>
        <fieldset className="wide fee-fields"><legend>Optional explicit fee</legend>
          <label>Type<input name="fee_type" defaultValue="CRYPTO_CONVERSION_FEE" /></label><label>Asset<select name="fee_asset_id"><option value="">Select</option>{assetOptions(assets)}</select></label>
          <label>Quantity<input name="fee_amount" inputMode="decimal" /></label><label>Value MYR<input name="fee_value_myr" inputMode="decimal" /></label>
          <label>Expense account<select name="fee_expense_account_id"><option value="">Select</option>{accountOptions(accounts, 'EXPENSE')}</select></label><label>Separate funding account<select name="fee_funding_account_id"><option value="">Only when not included</option>{accountOptions(accounts, 'ASSET')}</select></label>
          <label className="checkbox"><input name="fee_included" type="checkbox" /> Included in funding quantity</label>
        </fieldset>
        <label className="checkbox wide"><input name="final_capture" type="checkbox" defaultChecked /> Final capture; release hold</label>
        <div className="wide form-actions"><button className="primary" disabled={busy}>Post settlement</button></div>
      </form></>
  )
}

function RefundForm({ assets, accounts, cards, busy, onRefund }: Props) {
  const purchases = cards.filter((card) => card.transaction_type === 'PURCHASE' && ['SETTLED', 'PARTIALLY_REFUNDED'].includes(card.status))
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const value = values(form); const cardId = value('card_id')
    await onRefund(cardId, { external_id: value('external_id') || null, refund_value_myr: value('refund_value_myr'), expense_account_id: value('expense_account_id'), refunded_at: new Date(value('refunded_at')).toISOString(), full_refund: value('full_refund') === 'on', refund_legs: [{ account_id: value('account_id'), asset_id: value('asset_id'), quantity: value('quantity'), transaction_value_myr: value('transaction_value_myr'), reference_value_myr: value('reference_value_myr') }] })
    form.reset()
  }
  return <><div className="section-title"><div><span className="eyebrow">NEW REVERSING FACT</span><h2>Record actual refund</h2></div></div><p className="form-intro">The returned asset may differ from the original funding asset and creates a new cost lot.</p>
    <form onSubmit={(event) => void submit(event)}><label>Purchase<select name="card_id" required><option value="">Select</option>{purchases.map((card) => <option value={card.id} key={card.id}>{card.merchant_name} · {formatMyr(card.merchant_value_myr)}</option>)}</select></label><label>Refunded at<input name="refunded_at" type="datetime-local" defaultValue={localDateTimeValue()} required /></label><label>External ID<input name="external_id" /></label><label>Refund value MYR<input name="refund_value_myr" inputMode="decimal" required /></label><label>Original expense account<select name="expense_account_id" required><option value="">Select</option>{accountOptions(accounts, 'EXPENSE')}</select></label><label>Receiving account<select name="account_id" required><option value="">Select</option>{accountOptions(accounts, 'ASSET')}</select></label><label>Returned asset<select name="asset_id" required><option value="">Select</option>{assetOptions(assets)}</select></label><label>Returned quantity<input name="quantity" inputMode="decimal" required /></label><label>Transaction value MYR<input name="transaction_value_myr" inputMode="decimal" required /></label><label>Reference value MYR<input name="reference_value_myr" inputMode="decimal" required /></label><label className="checkbox"><input name="full_refund" type="checkbox" /> Full refund</label><div className="wide form-actions"><button className="primary" disabled={busy}>Post refund</button></div></form></>
}

function RewardForms({ assets, accounts, categories, cards, busy, onReward, onCreditReward }: Props) {
  const purchases = cards.filter((card) => card.transaction_type === 'PURCHASE' && card.status !== 'REVERSED')
  const pending = useMemo(() => purchases.flatMap((card) => card.rewards.filter((reward) => reward.status === 'PENDING').map((reward) => ({ ...reward, merchant: card.merchant_name }))), [purchases])
  async function add(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = event.currentTarget; const value = values(form); await onReward(value('card_id'), { reward_type: value('reward_type'), account_id: value('account_id'), asset_id: value('asset_id'), amount: value('amount'), earned_at: new Date(value('earned_at')).toISOString() }); form.reset() }
  async function credit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = event.currentTarget; const value = values(form); await onCreditReward(value('reward_id'), { income_account_id: value('income_account_id'), category_id: value('category_id'), value_myr: value('value_myr'), valuation_rate: value('valuation_rate'), valuation_source: value('valuation_source'), credited_at: new Date(value('credited_at')).toISOString() }); form.reset() }
  return <><div className="section-title"><div><span className="eyebrow">PENDING ≠ CREDITED</span><h2>Cashback and rewards</h2></div></div><div className="split-forms reward-forms"><form className="compact-form" onSubmit={(event) => void add(event)}><h3>Record pending reward</h3><label>Purchase<select name="card_id" required><option value="">Select</option>{purchases.map((card) => <option value={card.id} key={card.id}>{card.merchant_name}</option>)}</select></label><label>Type<input name="reward_type" defaultValue="CASHBACK" required /></label><label>Receiving account<select name="account_id" required><option value="">Select</option>{accountOptions(accounts, 'ASSET')}</select></label><label>Asset<select name="asset_id" required><option value="">Select</option>{assetOptions(assets)}</select></label><label>Amount<input name="amount" inputMode="decimal" required /></label><label>Earned at<input name="earned_at" type="datetime-local" defaultValue={localDateTimeValue()} required /></label><button className="primary" disabled={busy}>Save pending</button></form>
     <form className="compact-form" onSubmit={(event) => void credit(event)}><h3>Credit reward</h3><label>Pending reward<select name="reward_id" required><option value="">Select</option>{pending.map((reward) => <option value={reward.id} key={reward.id}>{reward.merchant} · {reward.amount}</option>)}</select></label><label>Income account<select name="income_account_id" required><option value="">Select</option>{accountOptions(accounts, 'INCOME')}</select></label><label>Category<select name="category_id" required><option value="">Select</option>{categoryOptions(categories, 'INCOME')}</select></label><label>Value MYR<input name="value_myr" inputMode="decimal" required /></label><label>Asset/MYR rate<input name="valuation_rate" inputMode="decimal" required /></label><label>Valuation source<input name="valuation_source" defaultValue="Credited price" required /></label><label>Credited at<input name="credited_at" type="datetime-local" defaultValue={localDateTimeValue()} required /></label><button className="primary" disabled={busy}>Post credited reward</button></form></div></>
}
