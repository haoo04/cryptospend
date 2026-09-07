import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import type {
  Account,
  Asset,
  CardCost,
  CardRecord,
  Category,
  ChannelComparison,
  FeeReport,
  GoogleDriveBackupResult,
  GoogleDriveBackupStatus,
  JourneyReport,
  MonthlyReport,
  PortfolioPosition,
  ReportSnapshot,
  Summary,
  TransactionEvent,
  AnalyticsReport,
} from './api'
import CardCenter from './CardCenter'
import CategoryManager from './CategoryManager'
import { formatMyr, localDateTimeValue } from './format'
import ReportsCenter from './ReportsCenter'
import './App.css'

type View = 'dashboard' | 'transactions' | 'add' | 'accounts' | 'portfolio' | 'cards' | 'reports' | 'categories' | 'settings'

const emptySummary: Summary = {
  net_worth_myr: '0',
  income_myr: '0',
  expense_myr: '0',
  gross_spending_myr: '0',
  net_spending_myr: '0',
}

const emptyBackupStatus: GoogleDriveBackupStatus = {
  configured: false,
  supported: true,
  connected: false,
  folder_name: 'CryptoSpend Backups',
  message: null,
}

function reportingMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function App() {
  const [view, setView] = useState<View>('dashboard')
  const [assets, setAssets] = useState<Asset[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [events, setEvents] = useState<TransactionEvent[]>([])
  const [summary, setSummary] = useState<Summary>(emptySummary)
  const [portfolio, setPortfolio] = useState<PortfolioPosition[]>([])
  const [feeReport, setFeeReport] = useState<FeeReport>({ total_myr: '0', components: [] })
  const [cards, setCards] = useState<CardRecord[]>([])
  const [cardCosts, setCardCosts] = useState<CardCost[]>([])
  const [monthly, setMonthly] = useState<MonthlyReport | null>(null)
  const [journeys, setJourneys] = useState<JourneyReport[]>([])
  const [snapshots, setSnapshots] = useState<ReportSnapshot[]>([])
  const [selected, setSelected] = useState<TransactionEvent | null>(null)
  const [backupStatus, setBackupStatus] = useState<GoogleDriveBackupStatus>(emptyBackupStatus)
  const [lastBackup, setLastBackup] = useState<GoogleDriveBackupResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [
        nextAssets,
        nextAccounts,
        nextCategories,
        nextEvents,
        nextSummary,
        nextPortfolio,
        nextFees,
        nextCards,
        nextCardCosts,
        nextMonthly,
        nextJourneys,
        nextSnapshots,
      ] = await Promise.all([
        api.assets(),
        api.accounts(),
        api.categories(true),
        api.events(),
        api.summary(),
        api.portfolio(),
        api.fees(),
        api.cards(),
        api.cardCosts(),
        api.monthly(reportingMonth()),
        api.journeys(),
        api.snapshots(),
      ])
      setAssets(nextAssets)
      setAccounts(nextAccounts)
      setCategories(nextCategories)
      setEvents(nextEvents)
      setSummary(nextSummary)
      setPortfolio(nextPortfolio)
      setFeeReport(nextFees)
      setCards(nextCards)
      setCardCosts(nextCardCosts)
      setMonthly(nextMonthly)
      setJourneys(nextJourneys)
      setSnapshots(nextSnapshots)
      setSelected((current) => (current ? nextEvents.find((event) => event.id === current.id) ?? null : null))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load CryptoSpend')
    } finally {
      setLoading(false)
    }
  }, [])

  const refreshBackupStatus = useCallback(async () => {
    try {
      const nextStatus = await api.googleDriveBackupStatus()
      setBackupStatus(nextStatus)
      return nextStatus
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load Google Drive status')
      return null
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0)
    return () => window.clearTimeout(timer)
  }, [refresh])

  useEffect(() => {
    const timer = window.setTimeout(() => void refreshBackupStatus(), 0)
    return () => window.clearTimeout(timer)
  }, [refreshBackupStatus])

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

  async function runReportAction(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await action()
      const [nextJourneys, nextSnapshots] = await Promise.all([api.journeys(), api.snapshots()])
      setJourneys(nextJourneys)
      setSnapshots(nextSnapshots)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Report action failed')
    } finally {
      setBusy(false)
    }
  }

  async function runBackup() {
    setBusy(true)
    setError('')
    try {
      setLastBackup(await api.uploadGoogleDriveBackup())
      await refreshBackupStatus()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Backup failed')
    } finally {
      setBusy(false)
    }
  }

  function openGoogleDriveConnection() {
    window.open(api.googleDriveConnectUrl(), '_blank', 'noopener,noreferrer')
  }

  async function loadMonthly(month: string) {
    setBusy(true)
    setError('')
    try {
      setMonthly(await api.monthly(month))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load monthly report')
    } finally {
      setBusy(false)
    }
  }

  const loadAnalytics = useCallback(async (period: AnalyticsReport['period'], anchor: string) => {
    setBusy(true)
    setError('')
    try {
      return await api.analytics(period, anchor)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load analytics')
      throw reason
    } finally {
      setBusy(false)
    }
  }, [])

  async function createManualEvent(payload: Record<string, unknown>, receipt?: File) {
    const event = await api.createManualEvent(payload)
    if (receipt) {
      try {
        await api.uploadReceipt(event.id, receipt)
      } catch (reason) {
        const detail = reason instanceof Error ? reason.message : 'unknown upload error'
        await refresh().catch(() => undefined)
        throw new Error(
          `Transaction ${event.id} saved, but receipt upload failed: ${detail}. Open the saved event to retry.`,
          { cause: reason },
        )
      }
    }
  }

  async function compareChannels(payload: Record<string, unknown>): Promise<ChannelComparison> {
    setBusy(true)
    setError('')
    try {
      return await api.compareChannels(payload)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to compare channels')
      throw reason
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
              ['cards', 'Card costs'],
              ['reports', 'Reports'],
              ['categories', 'Categories'],
              ['accounts', 'Accounts'],
              ['settings', 'Settings'],
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
          <div className="topbar-actions">
            <button className="secondary" onClick={() => void refresh()} disabled={loading || busy}>
              Refresh
            </button>
            <button
              className="primary"
              onClick={() => (backupStatus.connected ? void runBackup() : setView('settings'))}
              disabled={loading || busy}
            >
              {backupStatus.connected ? (busy ? 'Backing up…' : 'Backup database') : 'Set up backup'}
            </button>
          </div>
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
            categories={categories}
            busy={busy}
            selected={selected}
            onSelect={setSelected}
            onChangeCategory={(event, categoryId) => runAction(() => api.updateEventCategory(event.id, categoryId))}
            onUploadReceipt={(event, file) => runAction(() => api.uploadReceipt(event.id, file))}
            onDeleteReceipt={(event) => runAction(() => api.deleteReceipt(event.id))}
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
            categories={categories}
            onOpenCategories={() => setView('categories')}
            onSubmit={(payload, receipt) => runAction(() => createManualEvent(payload, receipt))}
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
        {ready && view === 'cards' && (
          <CardCenter
            assets={assets}
            accounts={accounts}
            categories={categories}
            cards={cards}
            costs={cardCosts}
            busy={busy}
            onAuthorize={(payload) => runAction(() => api.authorizeCard(payload))}
            onReverseAuthorization={(id) => runAction(() => api.reverseAuthorization(id))}
            onSettle={(payload) => runAction(() => api.settleCard(payload))}
            onRefund={(id, payload) => runAction(() => api.refundCard(id, payload))}
            onReward={(id, payload) => runAction(() => api.createReward(id, payload))}
            onCreditReward={(id, payload) => runAction(() => api.creditReward(id, payload))}
          />
        )}
        {ready && view === 'reports' && (
          <ReportsCenter
            assets={assets}
            events={events}
            monthly={monthly}
            journeys={journeys}
            snapshots={snapshots}
            busy={busy}
            onLoadAnalytics={loadAnalytics}
            onLoadMonth={loadMonthly}
            onSnapshot={(month) => runReportAction(() => api.createSnapshot(month))}
            onCreateJourney={(payload) => runReportAction(() => api.createJourney(payload))}
            onAllocate={(id, payload) => runReportAction(() => api.allocateJourneyEvent(id, payload))}
            onCompare={compareChannels}
          />
        )}
        {ready && view === 'categories' && (
          <CategoryManager
            categories={categories}
            busy={busy}
            onCreate={(payload) => runAction(() => api.createCategory(payload))}
            onUpdate={(id, payload) => runAction(() => api.updateCategory(id, payload))}
          />
        )}
        {ready && view === 'accounts' && (
          <Accounts
            assets={assets}
            accounts={accounts}
            busy={busy}
            onCreateAccount={(payload) => runAction(() => api.createAccount(payload))}
            onCreateAsset={(payload) => runAction(() => api.createAsset(payload))}
          />
        )}
        {view === 'settings' && (
          <GoogleDriveSettings
            status={backupStatus}
            lastBackup={lastBackup}
            busy={busy}
            onConnect={openGoogleDriveConnection}
            onBackup={runBackup}
            onRefreshStatus={refreshBackupStatus}
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
  categories,
  busy,
  selected,
  onSelect,
  onChangeCategory,
  onUploadReceipt,
  onDeleteReceipt,
  onReverse,
}: {
  events: TransactionEvent[]
  categories: Category[]
  busy: boolean
  selected: TransactionEvent | null
  onSelect: (event: TransactionEvent | null) => void
  onChangeCategory: (event: TransactionEvent, categoryId: string) => Promise<void>
  onUploadReceipt: (event: TransactionEvent, file: File) => Promise<void>
  onDeleteReceipt: (event: TransactionEvent) => Promise<void>
  onReverse: (event: TransactionEvent) => void
}) {
  const selectedCategoryOptions = selected?.category_kind
    ? categories.filter((category) => category.kind === selected.category_kind && (category.active || category.id === selected.category_id))
    : []

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
                <th>Category</th>
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
                  <td>{event.category || 'Uncategorized'} {event.receipt && <span title="Receipt attached" aria-label="Receipt attached">▣</span>}</td>
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
            <div><dt>Category</dt><dd>{selected.category || 'Uncategorized'}</dd></div>
          </dl>
          {selected.category_kind && (
            <label className="detail-control">
              Reclassify
              <select
                value={selected.category_id ?? ''}
                onChange={(event) => { if (event.target.value) void onChangeCategory(selected, event.target.value) }}
                disabled={busy || !selectedCategoryOptions.length}
              >
                <option value="">Select category</option>
                {selectedCategoryOptions.map((category) => <option value={category.id} key={category.id}>{category.name}{category.active ? '' : ' (inactive)'}</option>)}
              </select>
            </label>
          )}
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
          <section className="receipt-detail">
            <h3>Receipt</h3>
            {selected.receipt ? (
              <>
                <img src={api.receiptUrl(selected.id)} alt={selected.receipt.original_filename} />
                <div className="receipt-meta"><strong>{selected.receipt.original_filename}</strong><span>{Math.ceil(selected.receipt.byte_size / 1024)} KB · {selected.receipt.content_type}</span></div>
                <div className="receipt-actions">
                  <a href={api.receiptUrl(selected.id)} target="_blank" rel="noreferrer">Open original</a>
                  <label className="text-button">Replace<input type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void onUploadReceipt(selected, file) }} /></label>
                  <button className="text-button danger-text" disabled={busy} onClick={() => { if (window.confirm('Delete this receipt?')) void onDeleteReceipt(selected) }}>Delete</button>
                </div>
              </>
            ) : (
              <label className="receipt-upload">Upload receipt<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => { const file = event.target.files?.[0]; if (file) void onUploadReceipt(selected, file) }} /></label>
            )}
          </section>
          {selected.status === 'POSTED' && !selected.reverses_event_id && (
            <button className="danger" onClick={() => onReverse(selected)}>Reverse event</button>
          )}
        </aside>
      )}
    </section>
  )
}

export function AddTransaction({
  assets,
  accounts,
  busy,
  categories = [],
  onOpenCategories,
  onSubmit,
  onTrade,
  onTransfer,
}: {
  assets: Asset[]
  accounts: Account[]
  busy: boolean
  categories?: Category[]
  onOpenCategories?: () => void
  onSubmit: (payload: Record<string, unknown>, receipt?: File) => Promise<void>
  onTrade: (payload: Record<string, unknown>) => Promise<void>
  onTransfer: (payload: Record<string, unknown>) => Promise<void>
}) {
  const [mode, setMode] = useState<'MANUAL' | 'TRADE' | 'TRANSFER'>('MANUAL')
  const [eventType, setEventType] = useState('SALARY')
  const [occurredAt, setOccurredAt] = useState(localDateTimeValue())
  const [description, setDescription] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [receiptFile, setReceiptFile] = useState<File | null>(null)
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
  const categoryKind = useMemo<Category['kind'] | null>(() => {
    if (eventType === 'SALARY' || eventType === 'INCOME') return 'INCOME'
    if (eventType === 'EXPENSE') return 'EXPENSE'
    if (eventType === 'ADJUSTMENT') {
      const debitType = accounts.find((account) => account.id === debit)?.account_type
      const creditType = accounts.find((account) => account.id === credit)?.account_type
      if (debitType === 'INCOME' || creditType === 'INCOME') return 'INCOME'
      if (debitType === 'EXPENSE' || creditType === 'EXPENSE') return 'EXPENSE'
    }
    return null
  }, [accounts, credit, debit, eventType])
  const categoryOptions = categories.filter((category) => category.active && category.kind === categoryKind)
  const categoryRequired = ['SALARY', 'INCOME', 'EXPENSE'].includes(eventType)
  const selectedCategoryId = categoryOptions.some((category) => category.id === categoryId) ? categoryId : ''
  const selectedAsset = assets.find((item) => item.id === asset)
  const isMyrAsset = selectedAsset?.symbol === 'MYR'

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
    const payload = {
      event_type: eventType,
      occurred_at: new Date(occurredAt).toISOString(),
      description,
      category_id: selectedCategoryId || null,
      debit_account_id: debit,
      credit_account_id: credit,
      asset_id: asset,
      quantity: isMyrAsset ? bookAmount : quantity,
      book_amount_myr: bookAmount,
      valuation_rate: rate || null,
      valuation_source: rate ? rateSource : null,
    }
    if (receiptFile) await onSubmit(payload, receiptFile)
    else await onSubmit(payload)
    setDescription('')
    setQuantity('')
    setBookAmount('')
    setRate('')
    setCategoryId('')
    setReceiptFile(null)
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
        {isMyrAsset ? (
          <label>
            MYR amount
            <input inputMode="decimal" value={bookAmount} onChange={(event) => setBookAmount(event.target.value)} placeholder="4250.00" required />
          </label>
        ) : (
          <>
            <label>
              Original quantity
              <input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} placeholder="1000.00000000" required />
            </label>
            <label>
              Book amount (MYR)
              <input inputMode="decimal" value={bookAmount} onChange={(event) => setBookAmount(event.target.value)} placeholder="4250.00" required />
            </label>
          </>
        )}
        <label>
          Asset/MYR rate
          <input inputMode="decimal" value={rate} onChange={(event) => setRate(event.target.value)} placeholder="4.25" />
          <small>quote asset / base asset</small>
        </label>
        <label>
          Rate source
          <input value={rateSource} onChange={(event) => setRateSource(event.target.value)} disabled={!rate} />
        </label>
        {categoryKind && (
          <label>
            Category
            <select value={selectedCategoryId} onChange={(event) => setCategoryId(event.target.value)} required={categoryRequired && categories.length > 0}>
              <option value="">Select category</option>
              {categoryOptions.map((category) => <option value={category.id} key={category.id}>{category.name}</option>)}
            </select>
            {!categoryOptions.length && <small>No active categories. {onOpenCategories && <button type="button" className="text-button" onClick={onOpenCategories}>Manage categories</button>}</small>}
          </label>
        )}
        <label className="wide receipt-picker">
          Receipt image (optional)
          <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setReceiptFile(event.target.files?.[0] ?? null)} />
          {receiptFile && <small>{receiptFile.name} · {Math.ceil(receiptFile.size / 1024)} KB <button type="button" className="text-button" onClick={() => setReceiptFile(null)}>Remove</button></small>}
          {receiptFile && <ReceiptPreview file={receiptFile} />}
        </label>
        <div className="wide form-actions"><button className="primary" disabled={busy}>{busy ? 'Posting…' : 'Post balanced event'}</button></div>
      </form>
    </section>
  )
}

function ReceiptPreview({ file }: { file: File }) {
  const imageRef = useRef<HTMLImageElement>(null)

  useEffect(() => {
    const url = URL.createObjectURL(file)
    if (imageRef.current) imageRef.current.src = url
    return () => URL.revokeObjectURL(url)
  }, [file])

  return <img ref={imageRef} className="receipt-preview" alt="Receipt preview" />
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
      confidence: String(data.get('confidence')),
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
          <label>Confidence<select name="confidence" defaultValue="EXACT"><option>EXACT</option><option>HIGH</option><option>ESTIMATED</option><option>MISSING_INPUT</option></select></label>
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
  onCreateAccount: (payload: {
    name: string
    account_type: string
    channel_type: string
    provider: string | null
  }) => Promise<void>
  onCreateAsset: (payload: { symbol: string; name: string; decimals: number }) => Promise<void>
}) {
  const [accountName, setAccountName] = useState('')
  const [accountType, setAccountType] = useState('ASSET')
  const [channelType, setChannelType] = useState('OTHER')
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
              <small>{account.channel_type.replaceAll('_', ' ')} · {account.provider ?? 'Local/manual'}</small>
              <div className="account-balances">
                {account.balances.map((balance) => (
                  <div key={balance.asset_id}>
                    <span>Book · {balance.quantity} {balance.asset_symbol}</span>
                    <strong>{formatMyr(balance.book_amount_myr)}</strong>
                  </div>
                ))}
                {account.available_balances.map((balance) => (
                  <div className="available-row" key={`available-${balance.asset_id}`}>
                    <span>Available · {balance.quantity} {balance.asset_symbol}</span>
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
          void onCreateAccount({
            name: accountName,
            account_type: accountType,
            channel_type: channelType,
            provider: provider || null,
          }).then(() => {
            setAccountName('')
            setProvider('')
          })
        }}>
          <span className="eyebrow">NEW ACCOUNT</span><h2>Add account</h2>
          <label>Name<input value={accountName} onChange={(event) => setAccountName(event.target.value)} required /></label>
          <label>Type<select value={accountType} onChange={(event) => setAccountType(event.target.value)}>
            {['ASSET', 'LIABILITY', 'INCOME', 'EXPENSE', 'EQUITY', 'GAIN_LOSS', 'CLEARING'].map((type) => <option key={type}>{type}</option>)}
          </select></label>
          <label>Spending channel<select value={channelType} onChange={(event) => setChannelType(event.target.value)}>
            {['OTHER', 'BANK', 'CASH', 'EWALLET', 'EXCHANGE', 'CRYPTO_WALLET', 'CARD'].map((type) => <option key={type}>{type}</option>)}
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

export function GoogleDriveSettings({
  status,
  lastBackup,
  busy,
  onConnect,
  onBackup,
  onRefreshStatus,
}: {
  status: GoogleDriveBackupStatus
  lastBackup: GoogleDriveBackupResult | null
  busy: boolean
  onConnect: () => void
  onBackup: () => Promise<void>
  onRefreshStatus: () => Promise<GoogleDriveBackupStatus | null>
}) {
  const [connecting, setConnecting] = useState(false)

  useEffect(() => {
    if (!connecting) return
    let attempts = 0
    const timer = window.setInterval(() => {
      attempts += 1
      void onRefreshStatus().then((nextStatus) => {
        if (nextStatus?.connected || attempts >= 30) setConnecting(false)
      })
    }, 2000)
    return () => window.clearInterval(timer)
  }, [connecting, onRefreshStatus])

  function connect() {
    setConnecting(true)
    onConnect()
  }

  return (
    <div className="stack">
      <section className="panel backup-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">CLOUD BACKUP</span>
            <h2>Google Drive</h2>
          </div>
          <span className={`pill ${status.connected ? 'posted' : 'reversed'}`}>
            {status.connected ? 'CONNECTED' : status.configured ? 'READY TO CONNECT' : 'NOT CONFIGURED'}
          </span>
        </div>
        <p className="form-intro">
          Database snapshots are uploaded to the <strong>{status.folder_name}</strong> folder. Each backup is kept as a new file.
        </p>
        {!status.supported && <p className="backup-message">{status.message}</p>}
        {status.supported && !status.configured && (
          <p className="backup-message">
            Set <code>CRYPTOSPEND_GOOGLE_CLIENT_SECRETS_FILE</code> to your Google Desktop OAuth JSON file before connecting.
          </p>
        )}
        {status.supported && status.configured && !status.connected && status.message && (
          <p className="backup-message">{status.message}</p>
        )}
        <div className="backup-actions">
          <button className="secondary" onClick={() => void onRefreshStatus()} disabled={busy || connecting}>
            Refresh status
          </button>
          <button className="primary" onClick={connect} disabled={busy || connecting || !status.supported || !status.configured}>
            {connecting ? 'Waiting for Google…' : status.connected ? 'Reconnect Google Drive' : 'Connect Google Drive'}
          </button>
          <button className="primary" onClick={() => void onBackup()} disabled={busy || !status.connected}>
            {busy ? 'Uploading…' : 'Backup database'}
          </button>
        </div>
        {lastBackup && (
          <div className="backup-result" role="status">
            <strong>{lastBackup.name}</strong>
            <span>Uploaded at {new Date(lastBackup.created_at).toLocaleString()}</span>
            {lastBackup.web_view_link && (
              <a href={lastBackup.web_view_link} target="_blank" rel="noreferrer">
                Open in Google Drive
              </a>
            )}
          </div>
        )}
      </section>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>
}

export default App
