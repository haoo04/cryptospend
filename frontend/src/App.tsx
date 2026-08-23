import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import type { Account, Asset, Summary, TransactionEvent } from './api'
import './App.css'

type View = 'dashboard' | 'transactions' | 'add' | 'accounts'

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
  const [selected, setSelected] = useState<TransactionEvent | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [nextAssets, nextAccounts, nextEvents, nextSummary] = await Promise.all([
        api.assets(),
        api.accounts(),
        api.events(),
        api.summary(),
      ])
      setAssets(nextAssets)
      setAccounts(nextAccounts)
      setEvents(nextEvents)
      setSummary(nextSummary)
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

        {ready && view === 'dashboard' && <Dashboard summary={summary} accounts={accounts} events={events} />}
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

function Dashboard({ summary, accounts, events }: { summary: Summary; accounts: Account[]; events: TransactionEvent[] }) {
  const assetAccounts = accounts.filter((account) => account.account_type === 'ASSET')
  return (
    <div className="stack">
      <section className="metric-grid">
        <Metric label="Net worth (book)" value={formatMyr(summary.net_worth_myr)} accent />
        <Metric label="Income" value={formatMyr(summary.income_myr)} />
        <Metric label="Gross spending" value={formatMyr(summary.gross_spending_myr)} />
        <Metric label="Net spending" value={formatMyr(summary.net_spending_myr)} />
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
}: {
  assets: Asset[]
  accounts: Account[]
  busy: boolean
  onSubmit: (payload: Record<string, string | null>) => Promise<void>
}) {
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
