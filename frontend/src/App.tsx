import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import type { Account, Asset, FeeReport, PortfolioPosition, Summary, TransactionEvent } from './api'
import './App.css'

type View = 'dashboard' | 'transactions' | 'add' | 'accounts' | 'portfolio'

const emptySummary: Summary = {
  net_worth_myr: '0',
  income_myr: '0',
  expense_myr: '0',
  gross_spending_myr: '0',
  net_spending_myr: '0',
}

function localDateTimeValue() {
  const date = new Date()
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

function formatMyr(value: string) {
  const negative = value.startsWith('-')
  const unsigned = negative ? value.slice(1) : value
  const [whole, fraction = ''] = unsigned.split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const decimals = fraction ? `.${fraction}` : '.00'
  return `RM ${negative ? '-' : ''}${grouped}${decimals}`
}

function App() {
  const [view, setView] = useState<View>('dashboard')
  const [assets, setAssets] = useState<Asset[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [events, setEvents] = useState<TransactionEvent[]>([])
  const [summary, setSummary] = useState<Summary>(emptySummary)
  const [portfolio, setPortfolio] = useState<PortfolioPosition[]>([])
  const [feeReport, setFeeReport] = useState<FeeReport>({ total_myr: '0', components: [] })
  const [selected, setSelected] = useState<TransactionEvent | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [nextAssets, nextAccounts, nextEvents, nextSummary, nextPortfolio, nextFees] = await Promise.all([
        api.assets(),
        api.accounts(),
        api.events(),
        api.summary(),
        api.portfolio(),
        api.fees(),
      ])
      setAssets(nextAssets)
      setAccounts(nextAccounts)
      setEvents(nextEvents)
      setSummary(nextSummary)
      setPortfolio(nextPortfolio)
      setFeeReport(nextFees)
      setSelected((current) => (current ? nextEvents.find((event) => event.id === current.id) ?? null : null))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load CryptoSpend')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0)
    return () => window.clearTimeout(timer)
  }, [refresh])

  async function initialize() {
    setBusy(true)
    setError('')
    try {
      await api.onboard()
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Initialization failed')
    } finally {
      setBusy(false)
    }
  }

  async function runAction(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await action()
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  const ready = assets.length > 0 && accounts.length > 0

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">C</div>
          <div>
            <strong>CryptoSpend</strong>
            <span>MYR accounting</span>
          </div>
        </div>
        <nav aria-label="Main navigation">
          {(
            [
              ['dashboard', 'Overview'],
              ['transactions', 'Transactions'],
              ['add', 'Add transaction'],
              ['portfolio', 'Portfolio'],
              ['accounts', 'Accounts'],
            ] as [View, string][]
          ).map(([key, label]) => (
            <button className={view === key ? 'active' : ''} key={key} onClick={() => setView(key)}>
              <span className="nav-dot" />
              {label}
            </button>
          ))}
        </nav>
        <div className="local-note">
          <span className="status-dot" />
          Local-first ledger
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <span className="eyebrow">PERSONAL FINANCE / MYR</span>
            <h1>{view === 'dashboard' ? 'Financial overview' : view}</h1>
          </div>
          <button className="secondary" onClick={() => void refresh()} disabled={loading || busy}>
            Refresh
          </button>
        </header>

        {error && <div className="alert">{error}</div>}
        {!ready && !loading && (
          <section className="onboarding panel">
            <span className="eyebrow">FIRST RUN</span>
            <h2>Set up the local ledger</h2>
            <p>Create the default MYR, USD and crypto assets plus the core double-entry accounts.</p>
            <button className="primary" onClick={() => void initialize()} disabled={busy}>
              {busy ? 'Initializing…' : 'Initialize CryptoSpend'}
            </button>
          </section>
        )}

        {ready && view === 'dashboard' && (
          <Dashboard summary={summary} feeReport={feeReport} accounts={accounts} events={events} />
        )}
        {ready && view === 'transactions' && (
          <Transactions
            events={events}
            selected={selected}
            onSelect={setSelected}
            onReverse={(event) => {
              const reason = window.prompt('Why are you reversing this posted event?')
              if (reason) void runAction(() => api.reverseEvent(event.id, reason))
            }}
          />
        )}
        {ready && view === 'add' && (
          <AddTransaction
            assets={assets}
            accounts={accounts}
            busy={busy}
            onSubmit={(payload) => runAction(() => api.createManualEvent(payload))}
            onTrade={(payload) => runAction(() => api.createTrade(payload))}
            onTransfer={(payload) => runAction(() => api.createTransfer(payload))}
          />
        )}
        {ready && view === 'portfolio' && (
          <Portfolio
            positions={portfolio}
            feeReport={feeReport}
            assets={assets}
            busy={busy}
            onRate={(payload) => runAction(() => api.createRate(payload))}
          />
        )}
        {ready && view === 'accounts' && (
          <Accounts
            assets={assets}
            accounts={accounts}
            busy={busy}
            onCreateAccount={(payload) => runAction(() => api.createAccount(payload))
            }
            onCreateAsset={(payload) => runAction(() => api.createAsset(payload))}
          />
        )}
      </main>
    </div>
  )
}

function Dashboard({ summary, feeReport, accounts, events }: {
  summary: Summary
  feeReport: FeeReport
  accounts: Account[]
  events: TransactionEvent[]
}) {
  const assetAccounts = accounts.filter((account) => account.account_type === 'ASSET')
  return (
    <div className="stack">
      <section className="metric-grid">
        <Metric label="Net worth (book)" value={formatMyr(summary.net_worth_myr)} accent />
        <Metric label="Income" value={formatMyr(summary.income_myr)} />
        <Metric label="Gross spending" value={formatMyr(summary.gross_spending_myr)} />
        <Metric label="Explicit fees" value={formatMyr(feeReport.total_myr)} />
      </section>
      <section className="dashboard-grid">
        <div className="panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">BOOK BALANCES</span>
              <h2>Accounts</h2>
            </div>
            <span className="count">{assetAccounts.length}</span>
          </div>
          <div className="balance-list">
            {assetAccounts.map((account) => (
              <div className="balance-row" key={account.id}>
                <div>
                  <strong>{account.name}</strong>
                  <span>{account.provider ?? 'Manual account'}</span>
                </div>
                <div className="balance-values">
                  {account.balances.length ? (
                    account.balances.map((balance) => (
                      <span key={balance.asset_id}>
                        {balance.quantity} {balance.asset_symbol}
                      </span>
                    ))
                  ) : (
                    <span className="muted">No balance</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">LATEST ACTIVITY</span>
              <h2>Posted events</h2>
            </div>
          </div>
          <div className="activity-list">
            {events.slice(0, 6).map((event) => (
              <div className="activity-row" key={event.id}>
                <span className="event-icon">{event.event_type.slice(0, 1)}</span>
                <div>
                  <strong>{event.description || event.event_type.replaceAll('_', ' ')}</strong>
                  <span>{new Date(event.occurred_at).toLocaleString()}</span>
                </div>
                <span className={`pill ${event.status.toLowerCase()}`}>{event.status}</span>
              </div>
            ))}
            {!events.length && <Empty text="No ledger events yet." />}
          </div>
        </div>
      </section>
    </div>
  )
}

function Metric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`metric ${accent ? 'accent' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>Authoritative ledger value</small>
    </div>
  )
}

function Transactions({
  events,
  selected,
  onSelect,
  onReverse,
}: {
  events: TransactionEvent[]
  selected: TransactionEvent | null
  onSelect: (event: TransactionEvent | null) => void
  onReverse: (event: TransactionEvent) => void
}) {
  return (
    <section className="transactions-layout">
      <div className="panel table-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">IMMUTABLE HISTORY</span>
            <h2>Ledger events</h2>
          </div>
          <span className="count">{events.length}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Description</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr className={selected?.id === event.id ? 'selected' : ''} key={event.id}>
                  <td>{new Date(event.occurred_at).toLocaleDateString()}</td>
                  <td>{event.event_type.replaceAll('_', ' ')}</td>
                  <td>{event.description || '—'}</td>
                  <td>
                    <span className={`pill ${event.status.toLowerCase()}`}>{event.status}</span>
                  </td>
                  <td>
                    <button className="text-button" onClick={() => onSelect(event)}>
                      Inspect
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!events.length && <Empty text="Your first transaction will appear here." />}
        </div>
      </div>
      {selected && (
        <aside className="panel detail-panel">
          <button className="close" aria-label="Close details" onClick={() => onSelect(null)}>
            ×
          </button>
          <span className="eyebrow">EVENT DETAIL</span>
          <h2>{selected.description || selected.event_type.replaceAll('_', ' ')}</h2>
          <dl>
            <div><dt>Status</dt><dd>{selected.status}</dd></div>
            <div><dt>Occurred</dt><dd>{new Date(selected.occurred_at).toLocaleString()}</dd></div>
            <div><dt>Source</dt><dd>{selected.source}</dd></div>
          </dl>
          <h3>Double-entry lines</h3>
          <div className="entry-list">
            {selected.entries.map((entry) => (
              <div key={entry.id}>
                <span className={entry.direction === 'DEBIT' ? 'debit' : 'credit'}>{entry.direction}</span>
                <strong>{entry.account_name}</strong>
                <span>{entry.quantity} {entry.asset_symbol}</span>
                <span>{formatMyr(entry.book_amount_myr)}</span>
              </div>
            ))}
          </div>
          {!!selected.fees.length && (
            <>
              <h3 className="detail-subtitle">Explicit fees</h3>
              <div className="fee-list">
                {selected.fees.map((fee) => (
                  <div key={fee.id}>
                    <strong>{fee.component_type.replaceAll('_', ' ')}</strong>
                    <span>{fee.amount} {fee.asset_symbol}</span>
                    <span>{formatMyr(fee.value_myr)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          {selected.status === 'POSTED' && !selected.reverses_event_id && (
            <button className="danger" onClick={() => onReverse(selected)}>Reverse event</button>
          )}
        </aside>
      )}
    </section>
  )
}

function AddTransaction({
  assets,
  accounts,
  busy,
  onSubmit,
  onTrade,
  onTransfer,
}: {
  assets: Asset[]
  accounts: Account[]
  busy: boolean
  onSubmit: (payload: Record<string, unknown>) => Promise<void>
  onTrade: (payload: Record<string, unknown>) => Promise<void>
  onTransfer: (payload: Record<string, unknown>) => Promise<void>
}) {
  const [mode, setMode] = useState<'MANUAL' | 'TRADE' | 'TRANSFER'>('MANUAL')
  const [eventType, setEventType] = useState('SALARY')
  const [occurredAt, setOccurredAt] = useState(localDateTimeValue())
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [debit, setDebit] = useState('')
  const [credit, setCredit] = useState('')
  const [asset, setAsset] = useState('')
  const [quantity, setQuantity] = useState('')
  const [bookAmount, setBookAmount] = useState('')
  const [rate, setRate] = useState('')
  const [rateSource, setRateSource] = useState('Manual')

  const allowed = useMemo(() => {
    if (eventType === 'SALARY' || eventType === 'INCOME') return { debit: ['ASSET'], credit: ['INCOME'] }
    if (eventType === 'EXPENSE') return { debit: ['EXPENSE'], credit: ['ASSET'] }
    if (eventType === 'TRANSFER') return { debit: ['ASSET', 'CLEARING'], credit: ['ASSET', 'CLEARING'] }
    if (eventType === 'OPENING_BALANCE') return { debit: ['ASSET'], credit: ['EQUITY'] }
    return {
      debit: ['ASSET', 'EXPENSE', 'LIABILITY', 'CLEARING'],
      credit: ['ASSET', 'INCOME', 'EQUITY', 'GAIN_LOSS', 'CLEARING'],
    }
  }, [eventType])

  if (mode === 'TRADE') {
    return (
      <section className="panel form-panel">
        <EntryModeTabs mode={mode} onChange={setMode} />
        <TradeForm assets={assets} accounts={accounts} busy={busy} onSubmit={onTrade} />
      </section>
    )
  }
  if (mode === 'TRANSFER') {
    return (
      <section className="panel form-panel">
        <EntryModeTabs mode={mode} onChange={setMode} />
        <TransferForm assets={assets} accounts={accounts} busy={busy} onSubmit={onTransfer} />
      </section>
    )
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    await onSubmit({
      event_type: eventType,
      occurred_at: new Date(occurredAt).toISOString(),
      description,
      category: category || null,
      debit_account_id: debit,
      credit_account_id: credit,
      asset_id: asset,
      quantity,
      book_amount_myr: bookAmount,
      valuation_rate: rate || null,
      valuation_source: rate ? rateSource : null,
    })
    setDescription('')
    setQuantity('')
    setBookAmount('')
    setRate('')
  }

  return (
    <section className="panel form-panel">
      <EntryModeTabs mode={mode} onChange={setMode} />
      <div className="section-title">
        <div><span className="eyebrow">CONTROLLED COMMAND</span><h2>Add a balanced event</h2></div>
      </div>
      <p className="form-intro">The server creates both sides and rejects any event that is not exactly balanced in MYR micros.</p>
      <form onSubmit={(event) => void submit(event)}>
        <label>
          Event type
          <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
            {['SALARY', 'INCOME', 'EXPENSE', 'TRANSFER', 'OPENING_BALANCE', 'ADJUSTMENT'].map((type) => <option key={type}>{type}</option>)}
          </select>
        </label>
        <label>
          Occurred at
          <input type="datetime-local" value={occurredAt} onChange={(event) => setOccurredAt(event.target.value)} required />
        </label>
        <label className="wide">
          Description
          <input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What happened?" />
        </label>
        <label>
          Debit account
          <select value={debit} onChange={(event) => setDebit(event.target.value)} required>
            <option value="">Select account</option>
            {accounts.filter((account) => allowed.debit.includes(account.account_type)).map((account) => (
              <option value={account.id} key={account.id}>{account.name} · {account.account_type}</option>
            ))}
          </select>
        </label>
        <label>
          Credit account
          <select value={credit} onChange={(event) => setCredit(event.target.value)} required>
            <option value="">Select account</option>
            {accounts.filter((account) => allowed.credit.includes(account.account_type)).map((account) => (
              <option value={account.id} key={account.id}>{account.name} · {account.account_type}</option>
            ))}
          </select>
        </label>
        <label>
          Asset
          <select value={asset} onChange={(event) => setAsset(event.target.value)} required>
            <option value="">Select asset</option>
            {assets.map((item) => <option value={item.id} key={item.id}>{item.symbol} · {item.name}</option>)}
          </select>
        </label>
        <label>
          Original quantity
          <input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} placeholder="1000.00000000" required />
        </label>
        <label>
          Book amount (MYR)
          <input inputMode="decimal" value={bookAmount} onChange={(event) => setBookAmount(event.target.value)} placeholder="4250.00" required />
        </label>
        <label>
          Asset/MYR rate
          <input inputMode="decimal" value={rate} onChange={(event) => setRate(event.target.value)} placeholder="4.25" />
          <small>quote asset / base asset</small>
        </label>
        <label>
          Rate source
          <input value={rateSource} onChange={(event) => setRateSource(event.target.value)} disabled={!rate} />
        </label>
        <label>
          Category
          <input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Food, Salary…" />
        </label>
        <div className="wide form-actions"><button className="primary" disabled={busy}>{busy ? 'Posting…' : 'Post balanced event'}</button></div>
      </form>
    </section>
  )
}

function EntryModeTabs({ mode, onChange }: {
  mode: 'MANUAL' | 'TRADE' | 'TRANSFER'
  onChange: (mode: 'MANUAL' | 'TRADE' | 'TRANSFER') => void
}) {
  return (
    <div className="mode-tabs">
      {(['MANUAL', 'TRADE', 'TRANSFER'] as const).map((item) => (
        <button type="button" className={mode === item ? 'active' : ''} onClick={() => onChange(item)} key={item}>
          {item}
        </button>
      ))}
    </div>
  )
}

function TradeForm({ assets, accounts, busy, onSubmit }: {
  assets: Asset[]
  accounts: Account[]
  busy: boolean
  onSubmit: (payload: Record<string, unknown>) => Promise<void>
}) {
  const assetAccounts = accounts.filter((account) => account.account_type === 'ASSET')
  const expenseAccounts = accounts.filter((account) => account.account_type === 'EXPENSE')
  const gainAccounts = accounts.filter((account) => account.account_type === 'GAIN_LOSS')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    const value = (key: string) => String(data.get(key) ?? '')
    const feeAmount = value('fee_amount')
    await onSubmit({
      occurred_at: new Date(value('occurred_at')).toISOString(),
      account_id: value('account_id'),
      sell_asset_id: value('sell_asset_id'),
      sell_quantity: value('sell_quantity'),
      buy_asset_id: value('buy_asset_id'),
      buy_quantity: value('buy_quantity'),
      execution_rate: value('execution_rate'),
      gross_value_myr: value('gross_value_myr'),
      order_id: value('order_id') || null,
      description: value('description'),
      gain_loss_account_id: value('gain_loss_account_id'),
      fee: feeAmount ? {
        component_type: value('fee_type'),
        asset_id: value('fee_asset_id'),
        amount: feeAmount,
        value_myr: value('fee_value_myr'),
        accounting_treatment: value('fee_treatment'),
        included_in_funding_amount: value('fee_included') === 'on',
        expense_account_id: value('fee_expense_account_id') || null,
      } : null,
    })
    form.reset()
  }

  return (
    <>
      <div className="section-title">
        <div><span className="eyebrow">FIFO DISPOSAL + ACQUISITION</span><h2>Record a trade</h2></div>
      </div>
      <p className="form-intro">Buy quantity is the net asset actually received. Gross MYR, explicit fee and FIFO basis remain separate.</p>
      <form onSubmit={(event) => void submit(event)}>
        <label>Occurred at<input name="occurred_at" type="datetime-local" defaultValue={localDateTimeValue()} required /></label>
        <label>Exchange account<select name="account_id" required><option value="">Select account</option>{assetAccounts.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label>
        <label>Sell asset<select name="sell_asset_id" required><option value="">Select asset</option>{assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol}</option>)}</select></label>
        <label>Sell quantity<input name="sell_quantity" inputMode="decimal" placeholder="0.25" required /></label>
        <label>Buy asset<select name="buy_asset_id" required><option value="">Select asset</option>{assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol}</option>)}</select></label>
        <label>Net buy quantity<input name="buy_quantity" inputMode="decimal" placeholder="4241.50" required /></label>
        <label>Execution rate<input name="execution_rate" inputMode="decimal" placeholder="17000" required /><small>buy asset / sell asset</small></label>
        <label>Gross transaction value (MYR)<input name="gross_value_myr" inputMode="decimal" placeholder="4250" required /></label>
        <label>Gain/loss account<select name="gain_loss_account_id" required><option value="">Select account</option>{gainAccounts.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label>
        <label>Order ID<input name="order_id" placeholder="Optional" /></label>
        <label className="wide">Description<input name="description" placeholder="Hata ETH/MYR sale" /></label>
        <fieldset className="wide fee-fields">
          <legend>Optional explicit fee</legend>
          <label>Fee type<input name="fee_type" defaultValue="TRADING_FEE" /></label>
          <label>Fee asset<select name="fee_asset_id"><option value="">Select asset</option>{assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol}</option>)}</select></label>
          <label>Fee quantity<input name="fee_amount" inputMode="decimal" placeholder="8.50" /></label>
          <label>Fee value (MYR)<input name="fee_value_myr" inputMode="decimal" placeholder="8.50" /></label>
          <label>Treatment<select name="fee_treatment" defaultValue="EXPENSED"><option>EXPENSED</option><option>REDUCE_PROCEEDS</option><option>CAPITALIZED</option></select></label>
          <label>Expense account<select name="fee_expense_account_id"><option value="">Select account</option>{expenseAccounts.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label>
          <label className="checkbox"><input name="fee_included" type="checkbox" /> Fee is already included in the funding/net amount</label>
        </fieldset>
        <div className="wide form-actions"><button className="primary" disabled={busy}>{busy ? 'Posting…' : 'Post trade'}</button></div>
      </form>
    </>
  )
}

function TransferForm({ assets, accounts, busy, onSubmit }: {
  assets: Asset[]
  accounts: Account[]
  busy: boolean
  onSubmit: (payload: Record<string, unknown>) => Promise<void>
}) {
  const assetAccounts = accounts.filter((account) => account.account_type === 'ASSET')
  const expenseAccounts = accounts.filter((account) => account.account_type === 'EXPENSE')
  const gainAccounts = accounts.filter((account) => account.account_type === 'GAIN_LOSS')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    const value = (key: string) => String(data.get(key) ?? '')
    const feeAmount = value('fee_amount')
    await onSubmit({
      occurred_at: new Date(value('occurred_at')).toISOString(),
      source_account_id: value('source_account_id'),
      destination_account_id: value('destination_account_id'),
      asset_id: value('asset_id'),
      sent_quantity: value('sent_quantity'),
      received_quantity: value('received_quantity'),
      network: value('network') || null,
      tx_hash: value('tx_hash') || null,
      description: value('description'),
      gain_loss_account_id: value('gain_loss_account_id'),
      fee: feeAmount ? {
        component_type: value('fee_type'),
        asset_id: value('fee_asset_id'),
        amount: feeAmount,
        value_myr: value('fee_value_myr'),
        accounting_treatment: 'EXPENSED',
        expense_account_id: value('fee_expense_account_id'),
      } : null,
    })
    form.reset()
  }

  return (
    <>
      <div className="section-title">
        <div><span className="eyebrow">COST-PRESERVING MOVE</span><h2>Record an own-account transfer</h2></div>
      </div>
      <p className="form-intro">Transferred lots keep their original acquisition date and basis. Only an actual fee reduces global quantity.</p>
      <form onSubmit={(event) => void submit(event)}>
        <label>Occurred at<input name="occurred_at" type="datetime-local" defaultValue={localDateTimeValue()} required /></label>
        <label>Asset<select name="asset_id" required><option value="">Select asset</option>{assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol}</option>)}</select></label>
        <label>Source account<select name="source_account_id" required><option value="">Select account</option>{assetAccounts.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label>
        <label>Destination account<select name="destination_account_id" required><option value="">Select account</option>{assetAccounts.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label>
        <label>Sent quantity<input name="sent_quantity" inputMode="decimal" placeholder="1000" required /></label>
        <label>Received quantity<input name="received_quantity" inputMode="decimal" placeholder="1000" required /></label>
        <label>Network<input name="network" placeholder="Ethereum" /></label>
        <label>Transaction hash<input name="tx_hash" placeholder="Optional" /></label>
        <label>Gain/loss account<select name="gain_loss_account_id" required><option value="">Select account</option>{gainAccounts.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label>
        <label>Description<input name="description" placeholder="Wallet to Hata" /></label>
        <fieldset className="wide fee-fields">
          <legend>Optional withdrawal / network fee</legend>
          <label>Fee type<select name="fee_type" defaultValue="NETWORK_FEE"><option>NETWORK_FEE</option><option>WITHDRAWAL_FEE</option></select></label>
          <label>Fee asset<select name="fee_asset_id"><option value="">Select asset</option>{assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol}</option>)}</select></label>
          <label>Fee quantity<input name="fee_amount" inputMode="decimal" placeholder="0.0003" /></label>
          <label>Fee value (MYR)<input name="fee_value_myr" inputMode="decimal" placeholder="3.00" /></label>
          <label>Expense account<select name="fee_expense_account_id"><option value="">Select account</option>{expenseAccounts.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label>
        </fieldset>
        <div className="wide form-actions"><button className="primary" disabled={busy}>{busy ? 'Posting…' : 'Post transfer'}</button></div>
      </form>
    </>
  )
}

function Portfolio({ positions, feeReport, assets, busy, onRate }: {
  positions: PortfolioPosition[]
  feeReport: FeeReport
  assets: Asset[]
  busy: boolean
  onRate: (payload: Record<string, unknown>) => Promise<void>
}) {
  async function submitRate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    await onRate({
      base_asset_id: String(data.get('base_asset_id')),
      quote_asset_id: String(data.get('quote_asset_id')),
      rate: String(data.get('rate')),
      observed_at: new Date(String(data.get('observed_at'))).toISOString(),
      source: String(data.get('source')),
      rate_type: 'MARKET',
    })
  }

  return (
    <div className="stack">
      <section className="panel table-panel">
        <div className="section-title"><div><span className="eyebrow">FIFO PORTFOLIO</span><h2>Holdings and P&amp;L</h2></div><span className="count">{positions.length}</span></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Asset</th><th>Quantity</th><th>Cost basis</th><th>Average cost</th><th>Market value</th><th>Unrealized</th><th>Realized</th><th>Quality</th></tr></thead>
            <tbody>{positions.map((position) => (
              <tr key={position.asset_id}>
                <td><strong>{position.symbol}</strong></td>
                <td>{position.quantity}</td>
                <td>{formatMyr(position.cost_basis_myr)}</td>
                <td>{position.average_cost_myr ? formatMyr(position.average_cost_myr) : '—'}</td>
                <td>{position.market_value_myr ? formatMyr(position.market_value_myr) : 'Missing rate'}</td>
                <td>{position.unrealized_gain_loss_myr ? formatMyr(position.unrealized_gain_loss_myr) : '—'}</td>
                <td>{formatMyr(position.realized_gain_loss_myr)}</td>
                <td><span className={`pill ${position.basis_complete ? '' : 'reversed'}`}>{position.basis_complete ? 'EXACT' : 'INCOMPLETE'}</span></td>
              </tr>
            ))}</tbody>
          </table>
          {!positions.length && <Empty text="Post an acquisition to create the first FIFO lot." />}
        </div>
      </section>
      <section className="split-forms">
        <div className="panel">
          <span className="eyebrow">EXPLICIT COSTS</span><h2>Fee leakage</h2>
          <strong className="large-value">{formatMyr(feeReport.total_myr)}</strong>
          <div className="fee-breakdown">{feeReport.components.map((fee) => <div key={fee.component_type}><span>{fee.component_type.replaceAll('_', ' ')}</span><strong>{formatMyr(fee.value_myr)}</strong></div>)}</div>
          {!feeReport.components.length && <Empty text="No explicit fees recorded." />}
        </div>
        <form className="panel compact-form" onSubmit={(event) => void submitRate(event)}>
          <span className="eyebrow">REFERENCE PRICE</span><h2>Add market rate</h2>
          <label>Base asset<select name="base_asset_id" required><option value="">Select asset</option>{assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol}</option>)}</select></label>
          <label>Quote asset<select name="quote_asset_id" required><option value="">Select asset</option>{assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol}</option>)}</select></label>
          <label>Rate<input name="rate" inputMode="decimal" placeholder="17000" required /><small>quote asset / base asset</small></label>
          <label>Observed at<input name="observed_at" type="datetime-local" defaultValue={localDateTimeValue()} required /></label>
          <label>Source<input name="source" defaultValue="Manual market reference" required /></label>
          <button className="primary" disabled={busy}>Save snapshot</button>
        </form>
      </section>
    </div>
  )
}

function Accounts({ assets, accounts, busy, onCreateAccount, onCreateAsset }: {
  assets: Asset[]
  accounts: Account[]
  busy: boolean
  onCreateAccount: (payload: { name: string; account_type: string; provider: string | null }) => Promise<void>
  onCreateAsset: (payload: { symbol: string; name: string; decimals: number }) => Promise<void>
}) {
  const [accountName, setAccountName] = useState('')
  const [accountType, setAccountType] = useState('ASSET')
  const [provider, setProvider] = useState('')
  const [symbol, setSymbol] = useState('')
  const [assetName, setAssetName] = useState('')
  const [decimals, setDecimals] = useState('8')

  return (
    <div className="stack">
      <section className="panel table-panel">
        <div className="section-title">
          <div><span className="eyebrow">CHART OF ACCOUNTS</span><h2>Accounts and balances</h2></div>
          <span className="count">{accounts.length}</span>
        </div>
        <div className="account-cards">
          {accounts.map((account) => (
            <article key={account.id}>
              <span className="account-type">{account.account_type}</span>
              <h3>{account.name}</h3>
              <small>{account.provider ?? 'Local/manual'}</small>
              <div className="account-balances">
                {account.balances.map((balance) => (
                  <div key={balance.asset_id}>
                    <span>{balance.quantity} {balance.asset_symbol}</span>
                    <strong>{formatMyr(balance.book_amount_myr)}</strong>
                  </div>
                ))}
                {!account.balances.length && <span className="muted">No posted balance</span>}
              </div>
            </article>
          ))}
        </div>
      </section>
      <section className="split-forms">
        <form className="panel compact-form" onSubmit={(event) => {
          event.preventDefault()
          void onCreateAccount({ name: accountName, account_type: accountType, provider: provider || null }).then(() => {
            setAccountName('')
            setProvider('')
          })
        }}>
          <span className="eyebrow">NEW ACCOUNT</span><h2>Add account</h2>
          <label>Name<input value={accountName} onChange={(event) => setAccountName(event.target.value)} required /></label>
          <label>Type<select value={accountType} onChange={(event) => setAccountType(event.target.value)}>
            {['ASSET', 'LIABILITY', 'INCOME', 'EXPENSE', 'EQUITY', 'GAIN_LOSS', 'CLEARING'].map((type) => <option key={type}>{type}</option>)}
          </select></label>
          <label>Provider<input value={provider} onChange={(event) => setProvider(event.target.value)} placeholder="Optional" /></label>
          <button className="primary" disabled={busy}>Add account</button>
        </form>
        <form className="panel compact-form" onSubmit={(event) => {
          event.preventDefault()
          void onCreateAsset({ symbol, name: assetName, decimals: Number.parseInt(decimals, 10) }).then(() => {
            setSymbol('')
            setAssetName('')
          })
        }}>
          <span className="eyebrow">NEW ASSET</span><h2>Add asset</h2>
          <label>Symbol<input value={symbol} onChange={(event) => setSymbol(event.target.value)} required /></label>
          <label>Name<input value={assetName} onChange={(event) => setAssetName(event.target.value)} required /></label>
          <label>Decimal places<input type="number" min="0" max="30" value={decimals} onChange={(event) => setDecimals(event.target.value)} required /></label>
          <button className="primary" disabled={busy}>Add asset</button>
          <small className="footnote">Asset symbols are labels, not unique identities.</small>
        </form>
      </section>
      <section className="panel asset-strip">
        <span className="eyebrow">ACTIVE ASSETS</span>
        <div>{assets.map((asset) => <span key={asset.id}>{asset.symbol}</span>)}</div>
      </section>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>
}

export default App
