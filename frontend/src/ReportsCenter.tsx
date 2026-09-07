import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type {
  Asset,
  AnalyticsReport,
  ChannelComparison,
  JourneyReport,
  MonthlyReport,
  ReportSnapshot,
  TransactionEvent,
} from './api'
import { formatMyr, localDateTimeValue } from './format'

type PathDraft = {
  name: string
  mode: 'ACTUAL' | 'SIMULATED'
  explicit: string
  deviation: string
  cashback: string
  source: string
  confidence: string
}

type Props = {
  assets: Asset[]
  events: TransactionEvent[]
  monthly: MonthlyReport | null
  journeys: JourneyReport[]
  snapshots: ReportSnapshot[]
  busy: boolean
  onLoadMonth: (month: string) => Promise<void>
  onSnapshot: (month: string) => Promise<boolean>
  onCreateJourney: (payload: Record<string, unknown>) => Promise<boolean>
  onAllocate: (id: string, payload: Record<string, unknown>) => Promise<boolean>
  onCompare: (payload: Record<string, unknown>) => Promise<ChannelComparison>
  onLoadAnalytics: (period: AnalyticsReport['period'], anchor: string) => Promise<AnalyticsReport>
}

function currentMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function currentDate() {
  return new Date().toISOString().slice(0, 10)
}

export default function ReportsCenter({
  assets,
  events,
  monthly,
  journeys,
  snapshots,
  busy,
  onLoadMonth,
  onSnapshot,
  onCreateJourney,
  onAllocate,
  onCompare,
  onLoadAnalytics,
}: Props) {
  const [tab, setTab] = useState<'MONTHLY' | 'JOURNEYS' | 'COMPARE' | 'ANALYTICS'>('MONTHLY')
  const [month, setMonth] = useState(currentMonth())
  const [comparison, setComparison] = useState<ChannelComparison | null>(null)
  const [analytics, setAnalytics] = useState<AnalyticsReport | null>(null)
  const [analyticsPeriod, setAnalyticsPeriod] = useState<AnalyticsReport['period']>('month')
  const [analyticsAnchor, setAnalyticsAnchor] = useState(currentDate())
  const [analyticsLoading, setAnalyticsLoading] = useState(false)
  const [analyticsError, setAnalyticsError] = useState('')

  useEffect(() => {
    if (tab !== 'ANALYTICS') return
    let active = true
    void Promise.resolve()
      .then(() => {
        if (!active) return null
        setAnalytics(null)
        setAnalyticsError('')
        setAnalyticsLoading(true)
        return onLoadAnalytics(analyticsPeriod, analyticsAnchor)
      })
      .then((next) => { if (active && next) setAnalytics(next) })
      .catch((reason) => { if (active) setAnalyticsError(reason instanceof Error ? reason.message : 'Unable to load analytics') })
      .finally(() => { if (active) setAnalyticsLoading(false) })
    return () => { active = false }
  }, [analyticsAnchor, analyticsPeriod, onLoadAnalytics, tab])

  return (
    <div className="reports-center stack">
      <section className="panel report-tabs">
        {(['MONTHLY', 'ANALYTICS', 'JOURNEYS', 'COMPARE'] as const).map((item) => (
          <button className={tab === item ? 'active' : ''} key={item} onClick={() => setTab(item)}>
            {item === 'MONTHLY' ? 'Monthly & as-of' : item === 'ANALYTICS' ? 'Analytics' : item === 'JOURNEYS' ? 'Fund journeys' : 'Channel comparison'}
          </button>
        ))}
      </section>

      {tab === 'MONTHLY' && (
        <MonthlyPanel
          month={month}
          setMonth={setMonth}
          report={monthly}
          snapshots={snapshots}
          busy={busy}
          onLoad={onLoadMonth}
          onSnapshot={onSnapshot}
        />
      )}
      {tab === 'ANALYTICS' && (
        <AnalyticsPanel
          period={analyticsPeriod}
          anchor={analyticsAnchor}
          report={analytics}
          loading={analyticsLoading}
          error={analyticsError}
          busy={busy}
          onPeriodChange={setAnalyticsPeriod}
          onAnchorChange={setAnalyticsAnchor}
        />
      )}
      {tab === 'JOURNEYS' && (
        <JourneyPanel
          assets={assets}
          events={events}
          journeys={journeys}
          busy={busy}
          onCreate={onCreateJourney}
          onAllocate={onAllocate}
        />
      )}
      {tab === 'COMPARE' && (
        <ComparisonPanel
          busy={busy}
          comparison={comparison}
          onCompare={async (payload) => setComparison(await onCompare(payload))}
        />
      )}
    </div>
  )
}

function MonthlyPanel({
  month,
  setMonth,
  report,
  snapshots,
  busy,
  onLoad,
  onSnapshot,
}: {
  month: string
  setMonth: (value: string) => void
  report: MonthlyReport | null
  snapshots: ReportSnapshot[]
  busy: boolean
  onLoad: (month: string) => Promise<void>
  onSnapshot: (month: string) => Promise<boolean>
}) {
  return (
    <>
      <section className="panel report-controls">
        <div>
          <span className="eyebrow">TIMEZONE-AWARE PERIOD</span>
          <h2>Monthly reporting</h2>
          <p>Month boundaries follow the configured local timezone. Saved snapshots remain immutable.</p>
        </div>
        <label>
          Month
          <input type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
        </label>
        <button className="secondary" disabled={busy} onClick={() => void onLoad(month)}>
          Load month
        </button>
        <button className="primary" disabled={busy} onClick={() => void onSnapshot(month)}>
          Save snapshot
        </button>
      </section>

      {report && (
        <>
          <section className="metric-grid">
            <ReportMetric label="Net worth at month end" value={report.summary.net_worth_myr} />
            <ReportMetric label="Income" value={report.summary.income_myr} />
            <ReportMetric label="Gross spending" value={report.summary.gross_spending_myr} />
            <ReportMetric label="Net spending" value={report.summary.net_spending_myr} />
          </section>
          <section className="panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">{report.timezone}</span>
                <h2>Spending by channel</h2>
              </div>
              <span className="count">{report.channels.length}</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Channel</th><th>Gross</th><th>Refunds</th><th>Cashback</th><th>Net</th><th>Quality</th></tr>
                </thead>
                <tbody>
                  {report.channels.map((channel) => (
                    <tr key={channel.channel_type}>
                      <td>{channel.channel_type.replaceAll('_', ' ')}</td>
                      <td>{formatMyr(channel.gross_spending_myr)}</td>
                      <td>{formatMyr(channel.refunds_myr)}</td>
                      <td>{formatMyr(channel.cashback_myr)}</td>
                      <td>{formatMyr(channel.net_spending_myr)}</td>
                      <td><span className="quality">{channel.confidence} · {channel.source}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!report.channels.length && <p className="empty">No spending in this month.</p>}
            </div>
          </section>
          <section className="panel leakage-panel">
            <div className="section-title">
              <div><span className="eyebrow">EXPLICIT + NON-OVERLAPPING ESTIMATES</span><h2>Fee leakage</h2></div>
              <strong>{formatMyr(report.fee_leakage.total_leakage_myr)}</strong>
            </div>
            <div className="leakage-summary">
              <span>Explicit <strong>{formatMyr(report.fee_leakage.explicit_myr)}</strong></span>
              <span>Derived <strong>{formatMyr(report.fee_leakage.derived_myr)}</strong></span>
            </div>
            <div className="journey-steps">
              {report.fee_leakage.components.map((component, index) => (
                <div key={`${component.component_type}-${index}`}>
                  <span>{component.source_kind} · {component.confidence}</span>
                  <strong>{component.component_type.replaceAll('_', ' ')} · {formatMyr(component.value_myr)}</strong>
                  <small>{component.source} · {component.calculation_method}</small>
                </div>
              ))}
            </div>
            {!report.fee_leakage.components.length && <p className="empty">No explicit or derived leakage in this month.</p>}
          </section>
          <section className="panel">
            <div className="section-title">
              <div><span className="eyebrow">AS OF {new Date(report.period_end).toLocaleString()}</span><h2>Portfolio valuation</h2></div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Asset</th><th>Quantity</th><th>Basis</th><th>Market value</th><th>P&amp;L</th><th>Rate source</th></tr>
                </thead>
                <tbody>
                  {report.portfolio.map((position) => (
                    <tr key={position.asset_id}>
                      <td>{position.symbol}</td>
                      <td>{position.quantity}</td>
                      <td>{formatMyr(position.cost_basis_myr)}</td>
                      <td>{position.market_value_myr ? formatMyr(position.market_value_myr) : 'Missing rate'}</td>
                      <td>{position.unrealized_gain_loss_myr ? formatMyr(position.unrealized_gain_loss_myr) : '—'}</td>
                      <td>
                        <span className="quality">
                          {position.market_rate_source ?? 'No source'} · {position.market_rate_confidence ?? 'MISSING_INPUT'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <section className="panel snapshot-list">
        <div className="section-title"><div><span className="eyebrow">SHA-256 VERIFIED</span><h2>Saved snapshots</h2></div></div>
        {snapshots.map((snapshot) => (
          <div key={snapshot.id}>
            <strong>{snapshot.period_key}</strong>
            <span>{new Date(snapshot.created_at).toLocaleString()} · {snapshot.timezone}</span>
            <code>{snapshot.checksum}</code>
          </div>
        ))}
        {!snapshots.length && <p className="empty">No monthly snapshot saved yet.</p>}
      </section>
    </>
  )
}

function ReportMetric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{formatMyr(value)}</strong><small>Server-calculated</small></div>
}

function AnalyticsPanel({
  period,
  anchor,
  report,
  loading,
  error,
  busy,
  onPeriodChange,
  onAnchorChange,
}: {
  period: AnalyticsReport['period']
  anchor: string
  report: AnalyticsReport | null
  loading: boolean
  error: string
  busy: boolean
  onPeriodChange: (period: AnalyticsReport['period']) => void
  onAnchorChange: (anchor: string) => void
}) {
  const hasValues = report && (report.timeline.some((item) => item.income_myr !== '0' || item.expense_myr !== '0') || report.expense_categories.length > 0 || report.income_categories.length > 0)
  return (
    <>
      <section className="panel report-controls analytics-controls">
        <div>
          <span className="eyebrow">SERVER-AGGREGATED LEDGER</span>
          <h2>Income and expense analytics</h2>
          <p>Amounts and period boundaries follow the configured {report?.timezone ?? 'local'} timezone.</p>
        </div>
        <div className="mode-tabs analytics-periods" role="group" aria-label="Analytics period">
          {(['day', 'week', 'month', 'year', 'all'] as const).map((item) => (
            <button type="button" className={period === item ? 'active' : ''} key={item} onClick={() => onPeriodChange(item)} disabled={busy}>{item}</button>
          ))}
        </div>
        {period !== 'all' && <label>Anchor date<input type="date" value={anchor} onChange={(event) => onAnchorChange(event.target.value)} disabled={busy} /></label>}
      </section>

      {loading && <section className="panel empty">Loading analytics…</section>}
      {!loading && error && <section className="panel empty">{error}</section>}
      {!loading && !error && report && (
        <>
          <section className="metric-grid">
            <ReportMetric label="Income" value={report.summary.income_myr} />
            <ReportMetric label="Expense" value={report.summary.expense_myr} />
            <ReportMetric label="Net income" value={report.summary.net_income_myr} />
          </section>
          {!hasValues ? <section className="panel empty">No posted income or expense data in this period.</section> : (
            <>
              <section className="panel analytics-panel">
                <div className="section-title"><div><span className="eyebrow">{report.bucket_unit.toUpperCase()} BUCKETS</span><h2>Income vs expense</h2></div><span className="count">{report.timeline.length}</span></div>
                <div className="analytics-timeline">
                  {report.timeline.map((item) => <AnalyticsTimelineRow key={item.bucket_start} label={item.label} income={item.income_myr} expense={item.expense_myr} />)}
                </div>
                <div className="analytics-legend"><span className="income-dot" /> Income <span className="expense-dot" /> Expense</div>
              </section>
              <section className="analytics-chart-grid">
                <AnalyticsCategoryChart title="Expense by category" rows={report.expense_categories} kind="expense" />
                <AnalyticsCategoryChart title="Income by category" rows={report.income_categories} kind="income" />
              </section>
            </>
          )}
        </>
      )}
    </>
  )
}

function amountMagnitude(value: string) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? Math.abs(numeric) : 0
}

function AnalyticsTimelineRow({ label, income, expense }: { label: string; income: string; expense: string }) {
  const scale = Math.max(amountMagnitude(income), amountMagnitude(expense), 1)
  return (
    <div className="analytics-timeline-row">
      <strong className="analytics-timeline-label">{label}</strong>
      <div className="analytics-bars">
        <div className="analytics-bar-line"><span className="analytics-bar income" style={{ width: `${amountMagnitude(income) / scale * 100}%` }} /><span>{formatMyr(income)}</span></div>
        <div className="analytics-bar-line"><span className={`analytics-bar expense ${expense.startsWith('-') ? 'negative' : ''}`} style={{ width: `${amountMagnitude(expense) / scale * 100}%` }} /><span>{formatMyr(expense)}</span></div>
      </div>
    </div>
  )
}

function AnalyticsCategoryChart({ title, rows, kind }: { title: string; rows: AnalyticsReport['expense_categories']; kind: 'income' | 'expense' }) {
  const scale = Math.max(...rows.map((row) => amountMagnitude(row.amount_myr)), 1)
  return (
    <section className="panel analytics-panel">
      <div className="section-title"><div><span className="eyebrow">CATEGORY TOTALS</span><h2>{title}</h2></div><span className="count">{rows.length}</span></div>
      <div className="analytics-category-list">
        {rows.map((row) => (
          <div className="analytics-category-row" key={`${row.category_id ?? 'uncategorized'}-${row.name}`}>
            <strong className="analytics-category-label">{row.name}</strong>
            <div className="analytics-category-track"><span className={`analytics-bar ${kind} ${row.amount_myr.startsWith('-') ? 'negative' : ''}`} style={{ width: `${amountMagnitude(row.amount_myr) / scale * 100}%` }} /></div>
            <span className="analytics-category-amount">{formatMyr(row.amount_myr)}</span>
          </div>
        ))}
        {!rows.length && <p className="empty">No {kind} categories in this period.</p>}
      </div>
    </section>
  )
}

function JourneyPanel({
  assets,
  events,
  journeys,
  busy,
  onCreate,
  onAllocate,
}: {
  assets: Asset[]
  events: TransactionEvent[]
  journeys: JourneyReport[]
  busy: boolean
  onCreate: (payload: Record<string, unknown>) => Promise<boolean>
  onAllocate: (id: string, payload: Record<string, unknown>) => Promise<boolean>
}) {
  const [name, setName] = useState('')
  const [journeyType, setJourneyType] = useState('WITHDRAWAL')
  const [method, setMethod] = useState('Manual event allocation')
  const [journeyConfidence, setJourneyConfidence] = useState('EXACT')
  const [journeyId, setJourneyId] = useState('')
  const [eventId, setEventId] = useState('')
  const [assetId, setAssetId] = useState('')
  const [role, setRole] = useState('INPUT')
  const [quantity, setQuantity] = useState('')
  const [value, setValue] = useState('')
  const [source, setSource] = useState('Posted ledger event')
  const [allocationConfidence, setAllocationConfidence] = useState('EXACT')

  async function create(event: FormEvent) {
    event.preventDefault()
    const succeeded = await onCreate({
      name,
      journey_type: journeyType,
      status: 'CONFIRMED',
      allocation_method: method,
      confidence: journeyConfidence,
    })
    if (succeeded) setName('')
  }

  async function allocate(event: FormEvent) {
    event.preventDefault()
    const succeeded = await onAllocate(journeyId, {
      event_id: eventId,
      relation_type: role === 'INPUT' ? 'SOURCE' : role === 'OUTPUT' ? 'DESTINATION' : 'STEP',
      sequence: 0,
      allocations: [{
        asset_id: assetId,
        allocation_role: role,
        quantity,
        value_myr: value,
        source,
        confidence: allocationConfidence,
      }],
    })
    if (!succeeded) return
    setQuantity('')
    setValue('')
  }

  return (
    <>
      <section className="split-forms">
        <form className="panel compact-form" onSubmit={(event) => void create(event)}>
          <span className="eyebrow">MANUAL ATTRIBUTION</span><h2>Create journey</h2>
          <label>Name<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
          <label>Journey type<select value={journeyType} onChange={(event) => setJourneyType(event.target.value)}><option>FUNDS</option><option>PAYMENT</option><option>WITHDRAWAL</option></select></label>
          <label>Allocation method<input value={method} onChange={(event) => setMethod(event.target.value)} required /></label>
          <label>Confidence<select value={journeyConfidence} onChange={(event) => setJourneyConfidence(event.target.value)}><option>EXACT</option><option>HIGH</option><option>ESTIMATED</option><option>MISSING_INPUT</option></select></label>
          <button className="primary" disabled={busy}>Create journey</button>
        </form>
        <form className="panel compact-form" onSubmit={(event) => void allocate(event)}>
          <span className="eyebrow">PARTIAL EVENT ALLOCATION</span><h2>Link ledger value</h2>
          <label>Journey<select value={journeyId} onChange={(event) => setJourneyId(event.target.value)} required><option value="">Select journey</option>{journeys.map((journey) => <option value={journey.id} key={journey.id}>{journey.name}</option>)}</select></label>
          <label>Posted event<select value={eventId} onChange={(event) => setEventId(event.target.value)} required><option value="">Select event</option>{events.filter((item) => item.status !== 'DRAFT' && !item.reverses_event_id).map((item) => <option value={item.id} key={item.id}>{new Date(item.occurred_at).toLocaleDateString()} · {item.description || item.event_type}</option>)}</select></label>
          <label>Asset<select value={assetId} onChange={(event) => setAssetId(event.target.value)} required><option value="">Select asset</option>{assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol}</option>)}</select></label>
          <label>Role<select value={role} onChange={(event) => setRole(event.target.value)}><option>INPUT</option><option>INTERMEDIATE</option><option>OUTPUT</option><option>COST</option></select></label>
          <label>Quantity<input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} required /></label>
          <label>Allocated MYR value<input inputMode="decimal" value={value} onChange={(event) => setValue(event.target.value)} required /></label>
          <label>Evidence source<input value={source} onChange={(event) => setSource(event.target.value)} required /></label>
          <label>Confidence<select value={allocationConfidence} onChange={(event) => setAllocationConfidence(event.target.value)}><option>EXACT</option><option>HIGH</option><option>ESTIMATED</option><option>MISSING_INPUT</option></select></label>
          <button className="primary" disabled={busy || !journeys.length}>Add allocation</button>
        </form>
      </section>

      <section className="journey-grid">
        {journeys.map((journey) => (
          <article className="panel journey-card" key={journey.id}>
            <div className="card-cost-head"><div><span>{journey.journey_type} · {journey.status}</span><h3>{journey.name}</h3></div><span className={`pill ${journey.confidence.toLowerCase()}`}>{journey.confidence}</span></div>
            <div className="waterfall">
              <div><span>Gross input</span><strong>{formatMyr(journey.gross_input_myr)}</strong></div>
              <div><span>Explicit cost</span><strong>{formatMyr(journey.explicit_cost_myr)}</strong></div>
              <div><span>Derived deviation</span><strong>{formatMyr(journey.derived_deviation_myr)}</strong></div>
              <div className="total"><span>Net output</span><strong>{formatMyr(journey.net_output_myr)}</strong></div>
            </div>
            <p className="quality">{journey.allocation_method} · {journey.source}</p>
            <div className="journey-steps">
              {journey.allocations.map((allocation) => (
                <div key={allocation.id}>
                  <span>{allocation.sequence} · {allocation.allocation_role}</span>
                  <strong>{allocation.quantity} {allocation.asset_symbol} / {formatMyr(allocation.value_myr)}</strong>
                  <small>{allocation.source} · {allocation.confidence}</small>
                </div>
              ))}
            </div>
          </article>
        ))}
        {!journeys.length && <section className="panel empty">Create a journey, then allocate posted events to its input, output and cost roles.</section>}
      </section>
    </>
  )
}

function ComparisonPanel({
  busy,
  comparison,
  onCompare,
}: {
  busy: boolean
  comparison: ChannelComparison | null
  onCompare: (payload: Record<string, unknown>) => Promise<void>
}) {
  const [amount, setAmount] = useState('100')
  const [comparedAt, setComparedAt] = useState(localDateTimeValue())
  const [pathType, setPathType] = useState('PAYMENT')
  const [referenceRate, setReferenceRate] = useState('1')
  const [referenceSource, setReferenceSource] = useState('Market midpoint at comparison time')
  const [cashbackEligible, setCashbackEligible] = useState(false)
  const [first, setFirst] = useState<PathDraft>({ name: 'Actual path', mode: 'ACTUAL', explicit: '0', deviation: '0', cashback: '0', source: 'Statements', confidence: 'EXACT' })
  const [second, setSecond] = useState<PathDraft>({ name: 'Alternative path', mode: 'SIMULATED', explicit: '0', deviation: '0', cashback: '0', source: 'Published fee schedule', confidence: 'ESTIMATED' })

  async function submit(event: FormEvent) {
    event.preventDefault()
    const path = (draft: PathDraft) => ({
      name: draft.name,
      path_type: pathType,
      mode: draft.mode,
      explicit_cost_myr: draft.explicit,
      derived_deviation_myr: draft.deviation,
      cashback_myr: draft.cashback,
      source: draft.source,
      confidence: draft.confidence,
    })
    try {
      await onCompare({
        amount_myr: amount,
        compared_at: new Date(comparedAt).toISOString(),
        reference_rate: referenceRate,
        reference_source: referenceSource,
        cashback_eligible: cashbackEligible,
        paths: [path(first), path(second)],
      })
    } catch {
      return
    }
  }

  return (
    <>
      <form className="panel comparison-form" onSubmit={(event) => void submit(event)}>
        <div className="section-title wide"><div><span className="eyebrow">FIXED COMPARABLE CONDITIONS</span><h2>Payment or withdrawal path</h2></div></div>
        <label>Comparable amount (MYR)<input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} required /></label>
        <label>Comparison time<input type="datetime-local" value={comparedAt} onChange={(event) => setComparedAt(event.target.value)} required /></label>
        <label>Path type<select value={pathType} onChange={(event) => setPathType(event.target.value)}><option>PAYMENT</option><option>WITHDRAWAL</option></select></label>
        <label>Reference rate<input inputMode="decimal" value={referenceRate} onChange={(event) => setReferenceRate(event.target.value)} required /></label>
        <label className="wide">Reference source<input value={referenceSource} onChange={(event) => setReferenceSource(event.target.value)} required /></label>
        <label className="checkbox wide"><input type="checkbox" checked={cashbackEligible} onChange={(event) => setCashbackEligible(event.target.checked)} /><span>Cashback conditions are available to both paths</span></label>
        <PathEditor title="Path A" value={first} onChange={setFirst} />
        <PathEditor title="Path B" value={second} onChange={setSecond} />
        <button className="primary wide" disabled={busy}>Compare fixed conditions</button>
      </form>
      {comparison && (
        <section className="comparison-results">
          {comparison.paths.map((path) => (
            <article className={`panel comparison-result ${path.is_lowest_cost ? 'winner' : ''}`} key={path.name}>
              <span className="eyebrow">{path.mode} · {path.confidence}</span>
              <h2>{path.name}</h2>
              <strong>{formatMyr(path.effective_cost_myr)}</strong>
              <p>Effective cost · {path.cost_rate_percent}% of the fixed amount</p>
              <small>{path.source}</small>
              {path.is_lowest_cost && <span className="best-path">Lowest comparable cost</span>}
            </article>
          ))}
          <p className="quality wide">{comparison.note}</p>
        </section>
      )}
    </>
  )
}

function PathEditor({ title, value, onChange }: { title: string; value: PathDraft; onChange: (value: PathDraft) => void }) {
  const update = (field: keyof PathDraft, next: string) => onChange({ ...value, [field]: next })
  return (
    <fieldset className="comparison-path">
      <legend>{title}</legend>
      <label>Name<input value={value.name} onChange={(event) => update('name', event.target.value)} required /></label>
      <label>Mode<select value={value.mode} onChange={(event) => update('mode', event.target.value)}><option>ACTUAL</option><option>SIMULATED</option></select></label>
      <label>Explicit cost<input inputMode="decimal" value={value.explicit} onChange={(event) => update('explicit', event.target.value)} required /></label>
      <label>Derived deviation<input inputMode="decimal" value={value.deviation} onChange={(event) => update('deviation', event.target.value)} required /></label>
      <label>Cashback<input inputMode="decimal" value={value.cashback} onChange={(event) => update('cashback', event.target.value)} required /></label>
      <label>Confidence<select value={value.confidence} onChange={(event) => update('confidence', event.target.value)}><option>EXACT</option><option>HIGH</option><option>ESTIMATED</option><option>MISSING_INPUT</option></select></label>
      <label className="wide">Evidence source<input value={value.source} onChange={(event) => update('source', event.target.value)} required /></label>
    </fieldset>
  )
}
