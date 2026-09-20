import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import type { AccountLedgerFilters, AccountLedgerItem, AccountLedgerPage, Asset } from './api'
import { formatMyr } from './format'

const ledgerEventTypes = [
  'OPENING_BALANCE',
  'SALARY',
  'INCOME',
  'EXPENSE',
  'TRANSFER',
  'TRADE',
  'CARD_SETTLEMENT',
  'CARD_REFUND',
  'REWARD',
  'FEE',
  'ADJUSTMENT',
  'REVERSAL',
] as const

const ledgerPageSize = 50

type LedgerFilters = {
  q: string
  asset_id: string
  event_type: string
  from_date: string
  to_date: string
}

const emptyLedgerFilters: LedgerFilters = {
  q: '',
  asset_id: '',
  event_type: '',
  from_date: '',
  to_date: '',
}

function reasonMessage(reason: unknown, fallback: string) {
  if (!(reason instanceof Error)) return fallback
  return reason.message === 'account not found' ? 'Account not found' : reason.message
}

function signedQuantity(value: string) {
  if (value.startsWith('-')) return `−${value.slice(1)}`
  return value === '0' ? value : `+${value}`
}

function signedMyr(value: string) {
  if (value.startsWith('-')) return `−${formatMyr(value.slice(1))}`
  return value === '0' ? formatMyr(value) : `+${formatMyr(value)}`
}

function formatOccurredAt(item: AccountLedgerItem, timezone: string) {
  const occurredAt = new Date(item.occurred_at)
  if (Number.isNaN(occurredAt.getTime())) return item.occurred_at
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timezone,
      dateStyle: 'medium',
      ...(item.time_precision === 'EXACT' ? { timeStyle: 'short' as const } : {}),
    }).format(occurredAt)
  } catch {
    return item.occurred_at
  }
}

function accountBalanceRows(account: AccountLedgerPage['account']) {
  const balances = new Map(account.balances.map((balance) => [balance.asset_id, balance]))
  const available = new Map(account.available_balances.map((balance) => [balance.asset_id, balance]))
  const assetIds = new Set([...balances.keys(), ...available.keys()])
  return [...assetIds].map((assetId) => ({
    balance: balances.get(assetId) ?? {
      asset_id: assetId,
      asset_symbol: available.get(assetId)?.asset_symbol ?? assetId,
      quantity: '0',
      book_amount_myr: '0',
    },
    available: available.get(assetId),
  }))
}

function accountLedgerQuery(filters: LedgerFilters, page: number): AccountLedgerFilters {
  const query: AccountLedgerFilters = { page, page_size: ledgerPageSize }
  if (filters.q.trim()) query.q = filters.q.trim()
  if (filters.asset_id) query.asset_id = filters.asset_id
  if (filters.event_type) query.event_type = filters.event_type
  if (filters.from_date) query.from_date = filters.from_date
  if (filters.to_date) query.to_date = filters.to_date
  return query
}

export function AccountLedger({
  accountId,
  assets,
  refreshVersion,
  onBack,
  onInspectEvent,
}: {
  accountId: string
  assets: Asset[]
  refreshVersion: number
  onBack: () => void
  onInspectEvent: (eventId: string) => void
}) {
  const [draftFilters, setDraftFilters] = useState<LedgerFilters>(emptyLedgerFilters)
  const [filters, setFilters] = useState<LedgerFilters>(emptyLedgerFilters)
  const [page, setPage] = useState(1)
  const [result, setResult] = useState<AccountLedgerPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const requestId = useRef(0)

  const loadLedger = useCallback(async (nextFilters: LedgerFilters, nextPage: number) => {
    const currentRequest = ++requestId.current
    setLoading(true)
    setError('')
    try {
      const nextResult = await api.accountLedger(accountId, accountLedgerQuery(nextFilters, nextPage))
      if (currentRequest !== requestId.current) return nextResult
      const lastPage = Math.max(1, Math.ceil(nextResult.total / nextResult.page_size))
      if (nextPage > lastPage) {
        setPage(lastPage)
        return nextResult
      }
      setResult(nextResult)
      return nextResult
    } catch (reason) {
      if (currentRequest === requestId.current) {
        setError(reasonMessage(reason, 'Unable to load account activity'))
      }
      return null
    } finally {
      if (currentRequest === requestId.current) setLoading(false)
    }
  }, [accountId])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadLedger(filters, page), 0)
    return () => window.clearTimeout(timer)
  }, [filters, loadLedger, page, refreshVersion])

  const totalPages = Math.max(1, Math.ceil((result?.total ?? 0) / (result?.page_size ?? ledgerPageSize)))

  function updateDraftFilter(key: keyof LedgerFilters, value: string) {
    setDraftFilters((current) => ({ ...current, [key]: value }))
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (draftFilters.from_date && draftFilters.to_date && draftFilters.from_date > draftFilters.to_date) {
      setError('From date must be on or before to date.')
      return
    }
    setError('')
    setPage(1)
    setFilters({ ...draftFilters, q: draftFilters.q.trim() })
  }

  function clearFilters() {
    setDraftFilters(emptyLedgerFilters)
    setFilters(emptyLedgerFilters)
    setPage(1)
    setError('')
  }

  function changePage(nextPage: number) {
    if (nextPage < 1 || nextPage > totalPages || nextPage === page) return
    setPage(nextPage)
  }

  const hasActiveFilters = Object.values(filters).some((value) => value !== '')
  const emptyText = hasActiveFilters
    ? 'No account activity matches the current filters.'
    : 'No posted activity for this account yet.'
  const account = result?.account

  return (
    <section className="account-ledger-page">
      <div className="panel account-ledger-header">
        <div className="section-title">
          <div>
            <span className="eyebrow">ACCOUNT ACTIVITY</span>
            <h2>{account?.name ?? 'Account activity'}</h2>
            {account && (
              <p className="account-ledger-meta">
                {account.account_type} · {account.channel_type.replaceAll('_', ' ')} · {account.provider ?? 'Local/manual'}
              </p>
            )}
          </div>
          <div className="account-ledger-header-actions">
            {account && <span className={`pill ${account.closed ? 'reversed' : 'posted'}`}>{account.closed ? 'Closed' : 'Open'}</span>}
            <button type="button" className="secondary" onClick={onBack}>Back to accounts</button>
          </div>
        </div>
        {account && (
          <div className="account-ledger-balances" aria-label="Account balances">
            {accountBalanceRows(account).map(({ balance, available }) => {
              const availableMatches = available
                && available.quantity === balance.quantity
                && available.book_amount_myr === balance.book_amount_myr
              return (
                <div className="account-ledger-balance" key={balance.asset_id}>
                  <div>
                    <span className="muted">{balance.asset_symbol}</span>
                    <strong>{balance.quantity}</strong>
                  </div>
                  <small>Book balance · {formatMyr(balance.book_amount_myr)}</small>
                  {available && (
                    <small className={availableMatches ? 'muted' : 'account-ledger-available'}>
                      {availableMatches
                        ? 'Available matches book'
                        : `Available · ${available.quantity} ${balance.asset_symbol} · ${formatMyr(available.book_amount_myr)}`}
                    </small>
                  )}
                </div>
              )
            })}
            {!account.balances.length && !account.available_balances.length && <span className="muted">No posted balance</span>}
          </div>
        )}
      </div>

      <div className="panel account-ledger-filter-panel">
        <div className="section-title">
          <div><span className="eyebrow">FILTER HISTORY</span><h2>Find account activity</h2></div>
          <span className="count">{result?.total ?? 0}</span>
        </div>
        <form className="account-ledger-filters" onSubmit={(event) => applyFilters(event)}>
          <label className="account-ledger-search">Search activity<input aria-label="Search account activity" value={draftFilters.q} onChange={(event) => updateDraftFilter('q', event.target.value)} placeholder="Description, type, counterparty or ID" /></label>
          <label>Asset<select aria-label="Account ledger asset" value={draftFilters.asset_id} onChange={(event) => updateDraftFilter('asset_id', event.target.value)}><option value="">All assets</option>{assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol}</option>)}</select></label>
          <label>Type<select aria-label="Account ledger event type" value={draftFilters.event_type} onChange={(event) => updateDraftFilter('event_type', event.target.value)}><option value="">All types</option>{ledgerEventTypes.map((type) => <option value={type} key={type}>{type.replaceAll('_', ' ')}</option>)}</select></label>
          <label>From date<input aria-label="Account ledger from date" type="date" value={draftFilters.from_date} onChange={(event) => updateDraftFilter('from_date', event.target.value)} /></label>
          <label>To date<input aria-label="Account ledger to date" type="date" value={draftFilters.to_date} onChange={(event) => updateDraftFilter('to_date', event.target.value)} /></label>
          <div className="transaction-filter-actions"><button className="primary" type="submit">Apply filters</button><button className="secondary" type="button" onClick={clearFilters}>Clear</button></div>
        </form>
        {error && <div className="account-ledger-error" role="alert"><span>{error}</span><button type="button" className="secondary" onClick={() => void loadLedger(filters, page)} disabled={loading}>Retry</button></div>}
        <div className="transaction-result-meta">
          <span>{result?.total ? `Showing ${(result.page - 1) * result.page_size + 1}–${Math.min(result.page * result.page_size, result.total)} of ${result.total}` : emptyText}</span>
          {loading && <span role="status">Loading account activity…</span>}
          {!loading && result && result.total > 0 && <span>Page {result.page} of {totalPages}</span>}
        </div>
        {result && result.total > 0 && <div className="transaction-pagination" aria-label="Account ledger pagination"><button className="secondary" type="button" disabled={loading || page === 1} onClick={() => changePage(page - 1)}>Previous</button><span>Page {result.page} of {totalPages}</span><button className="secondary" type="button" disabled={loading || page >= totalPages} onClick={() => changePage(page + 1)}>Next</button></div>}
      </div>

      <div className="panel table-panel">
        <div className="table-wrap account-ledger-table-wrap">
          <table className="account-ledger-table">
            <thead><tr><th>Date</th><th>Event</th><th>Asset change</th><th>Balance after</th><th>Counterparties</th><th>Action</th></tr></thead>
            <tbody>
              {result?.items.map((item) => (
                <tr key={`${item.event_id}-${item.asset_id}`}>
                  <td><strong>{formatOccurredAt(item, result.timezone)}</strong><span className="muted">{item.time_precision === 'DATE_ONLY' ? 'Date only' : item.source}</span></td>
                  <td><strong>{item.description || item.event_type.replaceAll('_', ' ')}</strong><span className="muted">{item.event_type.replaceAll('_', ' ')}{item.category ? ` · ${item.category}` : ''}</span><span className={`pill ${item.event_status.toLowerCase()}`}>{item.event_status}</span></td>
                  <td><strong className={item.quantity_change.startsWith('-') ? 'ledger-change negative' : item.quantity_change === '0' ? 'ledger-change' : 'ledger-change positive'}>{signedQuantity(item.quantity_change)} {item.asset_symbol}</strong><span className="muted">{signedMyr(item.book_amount_myr_change)}</span></td>
                  <td><strong>{item.balance_after_quantity} {item.asset_symbol}</strong><span className="muted">{formatMyr(item.balance_after_book_amount_myr)}</span></td>
                  <td><span className="ledger-counterparties">{item.counterparties.length ? item.counterparties.map((counterparty) => counterparty.account_name).join(', ') : 'No counterparty'}</span>{item.receipt_attached && <span className="muted">Receipt attached</span>}</td>
                  <td><button type="button" className="text-button" onClick={() => onInspectEvent(item.event_id)} aria-label={`Inspect event ${item.event_id}`}>Inspect event</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && result && !result.items.length && <p className="account-ledger-empty">{emptyText}</p>}
          {loading && !result && <p className="account-ledger-empty" role="status">Loading account activity…</p>}
        </div>
      </div>
    </section>
  )
}

export default AccountLedger
