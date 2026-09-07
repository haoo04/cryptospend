import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'

import type {
  Account,
  Asset,
  Category,
  RecurringExpense,
  RecurringExpenseList,
  RecurringExpenseOccurrence,
  RecurringFrequency,
} from './api'
import { formatMyr, localDateTimeValue } from './format'

type CreatePayload = {
  name: string
  amount_myr: string
  frequency: RecurringFrequency
  first_due_on: string
  asset_id: string
  funding_account_id: string
  expense_account_id: string
  category_id: string
}

type UpdatePayload = {
  name?: string
  amount_myr?: string
  frequency?: RecurringFrequency
  next_due_on?: string
  asset_id?: string
  funding_account_id?: string
  expense_account_id?: string
  category_id?: string
  active?: boolean
}

type FormState = {
  name: string
  amount_myr: string
  frequency: RecurringFrequency
  due_on: string
  asset_id: string
  funding_account_id: string
  expense_account_id: string
  category_id: string
}

type ScheduleBaseline = { frequency: RecurringFrequency; next_due_on: string } | null
type Filter = 'ACTIVE' | 'PAUSED' | 'ALL'
type Action = { kind: 'record' | 'skip'; expense: RecurringExpense } | null

type Props = {
  assets: Asset[]
  accounts: Account[]
  categories: Category[]
  data: RecurringExpenseList
  busy: boolean
  onCreate: (payload: CreatePayload) => Promise<boolean>
  onUpdate: (id: string, payload: UpdatePayload) => Promise<boolean>
  onRecord: (id: string, payload: { due_on: string; occurred_at: string }) => Promise<boolean>
  onSkip: (id: string, payload: { due_on: string; reason?: string | null }) => Promise<boolean>
  onLoadHistory: (id: string) => Promise<RecurringExpenseOccurrence[]>
  onOpenCategories?: () => void
  onOpenEvent?: (eventId: string) => void
}

function localDateValue() {
  return localDateTimeValue().slice(0, 10)
}

function emptyForm(assets: Asset[], accounts: Account[], categories: Category[]): FormState {
  const myr = assets.find((asset) => asset.active && asset.symbol === 'MYR')
  const funding = accounts.find((account) => account.account_type === 'ASSET' && !account.closed)
  const expense = accounts.find((account) => account.account_type === 'EXPENSE' && !account.closed)
  const category = categories.find((item) => item.kind === 'EXPENSE' && item.active)
  return {
    name: '',
    amount_myr: '',
    frequency: 'MONTHLY',
    due_on: localDateValue(),
    asset_id: myr?.id ?? '',
    funding_account_id: funding?.id ?? '',
    expense_account_id: expense?.id ?? '',
    category_id: category?.id ?? '',
  }
}

function frequencyLabel(frequency: RecurringFrequency) {
  return frequency === 'WEEKLY' ? 'week' : frequency === 'MONTHLY' ? 'month' : 'year'
}

function statusLabel(status: RecurringExpense['due_status']) {
  return status === 'DUE_TODAY'
    ? 'Due today'
    : status === 'OVERDUE'
      ? 'Overdue'
      : status === 'PAUSED'
        ? 'Paused'
        : 'Upcoming'
}

function dueLabel(expense: RecurringExpense, asOf: string) {
  if (expense.due_status === 'PAUSED') return 'Paused'
  const days = Math.round(
    (Date.parse(`${expense.next_due_on}T00:00:00Z`) - Date.parse(`${asOf}T00:00:00Z`)) / 86_400_000,
  )
  if (days === 0) return 'Today'
  if (days < 0) return `${Math.abs(days)} ${Math.abs(days) === 1 ? 'day' : 'days'} overdue`
  return `in ${days} ${days === 1 ? 'day' : 'days'}`
}

function accountName(accounts: Account[], id: string) {
  return accounts.find((account) => account.id === id)?.name ?? 'Unavailable'
}

function categoryName(categories: Category[], id: string) {
  return categories.find((category) => category.id === id)?.name ?? 'Unavailable'
}

function hasConfiguration(
  form: FormState,
  assets: Asset[],
  accounts: Account[],
  categories: Category[],
) {
  return Boolean(
    assets.some((asset) => asset.id === form.asset_id && asset.active && asset.symbol === 'MYR') &&
      accounts.some((account) => account.id === form.funding_account_id && account.account_type === 'ASSET' && !account.closed) &&
      accounts.some((account) => account.id === form.expense_account_id && account.account_type === 'EXPENSE' && !account.closed) &&
      categories.some((category) => category.id === form.category_id && category.kind === 'EXPENSE' && category.active),
  )
}

function optionItems<T extends { id: string }>(items: T[], currentId: string) {
  if (currentId && !items.some((item) => item.id === currentId)) {
    const current = items.find((item) => item.id === currentId)
    return current ? [...items, current] : items
  }
  return items
}

export default function FixedExpensesCenter({
  assets,
  accounts,
  categories,
  data,
  busy,
  onCreate,
  onUpdate,
  onRecord,
  onSkip,
  onLoadHistory,
  onOpenCategories,
  onOpenEvent,
}: Props) {
  const [filter, setFilter] = useState<Filter>('ACTIVE')
  const [form, setForm] = useState<FormState>(() => emptyForm(assets, accounts, categories))
  const [editingId, setEditingId] = useState<string | null>(null)
  const [baseline, setBaseline] = useState<ScheduleBaseline>(null)
  const [action, setAction] = useState<Action>(null)
  const [occurredAt, setOccurredAt] = useState(localDateTimeValue())
  const [skipReason, setSkipReason] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [history, setHistory] = useState<RecurringExpenseOccurrence[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')

  const filteredItems = useMemo(
    () => data.items.filter((item) => filter === 'ALL' || (filter === 'ACTIVE' ? item.active : !item.active)),
    [data.items, filter],
  )
  const selected = data.items.find((item) => item.id === selectedId) ?? null
  const availableAssets = assets.filter((asset) => asset.active && asset.symbol === 'MYR')
  const availableFundingAccounts = accounts.filter((account) => account.account_type === 'ASSET' && !account.closed)
  const availableExpenseAccounts = accounts.filter((account) => account.account_type === 'EXPENSE' && !account.closed)
  const availableCategories = categories.filter((category) => category.kind === 'EXPENSE' && category.active)
  const configurationReady = hasConfiguration(form, assets, accounts, categories)
  const editing = editingId !== null

  async function loadHistory(id: string) {
    setSelectedId(id)
    setHistoryLoading(true)
    setHistoryError('')
    try {
      setHistory(await onLoadHistory(id))
    } catch (reason) {
      setHistoryError(reason instanceof Error ? reason.message : 'Unable to load history')
    } finally {
      setHistoryLoading(false)
    }
  }

  function toggleHistory(id: string) {
    if (selectedId === id) {
      setSelectedId(null)
      return
    }
    void loadHistory(id)
  }

  function startCreate() {
    setEditingId(null)
    setBaseline(null)
    setForm(emptyForm(assets, accounts, categories))
    setAction(null)
  }

  function startEdit(expense: RecurringExpense) {
    setEditingId(expense.id)
    setBaseline({ frequency: expense.frequency, next_due_on: expense.next_due_on })
    setForm({
      name: expense.name,
      amount_myr: expense.amount_myr,
      frequency: expense.frequency,
      due_on: expense.next_due_on,
      asset_id: expense.asset_id,
      funding_account_id: expense.funding_account_id,
      expense_account_id: expense.expense_account_id,
      category_id: expense.category_id,
    })
    setAction(null)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!configurationReady) return
    let succeeded: boolean
    if (editingId) {
      const payload: UpdatePayload = {
        name: form.name,
        amount_myr: form.amount_myr,
        asset_id: form.asset_id,
        funding_account_id: form.funding_account_id,
        expense_account_id: form.expense_account_id,
        category_id: form.category_id,
      }
      if (baseline && (baseline.frequency !== form.frequency || baseline.next_due_on !== form.due_on)) {
        payload.frequency = form.frequency
        payload.next_due_on = form.due_on
      }
      succeeded = await onUpdate(editingId, payload)
    } else {
      succeeded = await onCreate({
        name: form.name,
        amount_myr: form.amount_myr,
        frequency: form.frequency,
        first_due_on: form.due_on,
        asset_id: form.asset_id,
        funding_account_id: form.funding_account_id,
        expense_account_id: form.expense_account_id,
        category_id: form.category_id,
      })
    }
    if (succeeded) startCreate()
  }

  async function confirmAction() {
    if (!action) return
    let succeeded: boolean
    if (action.kind === 'record') {
      succeeded = await onRecord(action.expense.id, {
        due_on: action.expense.next_due_on,
        occurred_at: new Date(occurredAt).toISOString(),
      })
    } else {
      succeeded = await onSkip(action.expense.id, {
        due_on: action.expense.next_due_on,
        reason: skipReason.trim() || null,
      })
    }
    if (!succeeded) return
    setAction(null)
    setSkipReason('')
    if (selectedId === action.expense.id) void loadHistory(action.expense.id)
  }

  const formAssets = optionItems(availableAssets, form.asset_id)
  const formFundingAccounts = optionItems(availableFundingAccounts, form.funding_account_id)
  const formExpenseAccounts = optionItems(availableExpenseAccounts, form.expense_account_id)
  const formCategories = optionItems(availableCategories, form.category_id)

  return (
    <div className="stack fixed-expenses-center">
      <section className="metric-grid fixed-expense-summary">
        <div className="metric accent"><span>Active</span><strong>{data.summary.active_count}</strong><small>Templates</small></div>
        <div className="metric"><span>Overdue</span><strong>{data.summary.overdue_count}</strong><small>Need a decision</small></div>
        <div className="metric"><span>Weekly total</span><strong>{formatMyr(data.summary.weekly_total_myr)}</strong><small>Per active weekly plan</small></div>
        <div className="metric"><span>Monthly total</span><strong>{formatMyr(data.summary.monthly_total_myr)}</strong><small>Per active monthly plan</small></div>
        <div className="metric"><span>Yearly total</span><strong>{formatMyr(data.summary.yearly_total_myr)}</strong><small>Per active yearly plan</small></div>
        <div className="metric"><span>Annualized estimate</span><strong>{formatMyr(data.summary.annualized_myr)}</strong><small>52 weeks + 12 months</small></div>
      </section>

      <section className="panel">
        <div className="section-title">
          <div><span className="eyebrow">PLANNED CASH COMMITMENTS</span><h2>Fixed expenses</h2></div>
          <button className="primary" onClick={startCreate} disabled={busy}>New fixed expense</button>
        </div>
        <p className="form-intro">Plans never enter the ledger by themselves. Record a payment only after it actually happens.</p>
        <div className="fixed-expense-filters" role="group" aria-label="Fixed expense filter">
          {(['ACTIVE', 'PAUSED', 'ALL'] as const).map((item) => (
            <button key={item} className={filter === item ? 'active' : ''} onClick={() => setFilter(item)}>{item}</button>
          ))}
        </div>
        <div className="fixed-expense-list">
          {filteredItems.map((expense) => {
            const canRecord = expense.active && hasConfiguration({
              name: expense.name,
              amount_myr: expense.amount_myr,
              frequency: expense.frequency,
              due_on: expense.next_due_on,
              asset_id: expense.asset_id,
              funding_account_id: expense.funding_account_id,
              expense_account_id: expense.expense_account_id,
              category_id: expense.category_id,
            }, assets, accounts, categories)
            return (
              <article className={`fixed-expense-row ${selectedId === expense.id ? 'selected' : ''}`} key={expense.id}>
                <div className="fixed-expense-main">
                  <div className="fixed-expense-heading">
                    <strong>{expense.name}</strong>
                    <span className={`pill fixed-status ${expense.due_status.toLowerCase()}`}>{statusLabel(expense.due_status)}</span>
                  </div>
                  <div className="fixed-expense-amount">{formatMyr(expense.amount_myr)} / {frequencyLabel(expense.frequency)}</div>
                  <div className="fixed-expense-meta">
                    <span>Next due {expense.next_due_on} · {dueLabel(expense, data.as_of)}</span>
                    <span>{categoryName(categories, expense.category_id)}</span>
                    <span>{accountName(accounts, expense.funding_account_id)} → {accountName(accounts, expense.expense_account_id)}</span>
                    <span>Annualized {formatMyr(expense.annualized_amount_myr)}</span>
                  </div>
                  {expense.active && !canRecord && <small className="fixed-expense-warning">Configuration unavailable; edit the template before recording.</small>}
                </div>
                <div className="fixed-expense-actions">
                  <button className="text-button" onClick={() => toggleHistory(expense.id)} disabled={busy}>
                    {selectedId === expense.id ? 'Hide history' : 'History'}
                  </button>
                  <button className="text-button" onClick={() => startEdit(expense)} disabled={busy}>Edit</button>
                  <button className="text-button" onClick={() => void onUpdate(expense.id, { active: !expense.active })} disabled={busy}>
                    {expense.active ? 'Pause' : 'Resume'}
                  </button>
                  {expense.active && <>
                    <button className="text-button" onClick={() => { setAction({ kind: 'record', expense }); setOccurredAt(localDateTimeValue()) }} disabled={busy || !canRecord}>
                      Record payment for {expense.next_due_on}
                    </button>
                    <button className="text-button" onClick={() => { setAction({ kind: 'skip', expense }); setSkipReason('') }} disabled={busy || !canRecord}>
                      Skip {expense.next_due_on}
                    </button>
                  </>}
                </div>
              </article>
            )
          })}
          {!filteredItems.length && <p className="empty">{filter === 'ALL' ? 'No fixed expense templates yet.' : `No ${filter.toLowerCase()} fixed expenses.`}</p>}
        </div>
      </section>

      {(editing || !editingId) && (
        <section className="panel fixed-expense-form-panel">
          <div className="section-title">
            <div><span className="eyebrow">{editing ? 'EDIT TEMPLATE' : 'NEW TEMPLATE'}</span><h2>{editing ? 'Update fixed expense' : 'Add a fixed expense'}</h2></div>
            {editing && <button className="close" onClick={startCreate} aria-label="Close form">×</button>}
          </div>
          <form onSubmit={(event) => void submit(event)}>
            <label>Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} maxLength={120} required placeholder="Rent or streaming subscription" /></label>
            <label>Amount (MYR)<input inputMode="decimal" value={form.amount_myr} onChange={(event) => setForm({ ...form, amount_myr: event.target.value })} required placeholder="55.90" /></label>
            <label>Frequency<select value={form.frequency} onChange={(event) => setForm({ ...form, frequency: event.target.value as RecurringFrequency })}><option value="WEEKLY">Weekly</option><option value="MONTHLY">Monthly</option><option value="YEARLY">Yearly</option></select></label>
            <label>{editing ? 'Next due date' : 'First due date'}<input type="date" value={form.due_on} onChange={(event) => setForm({ ...form, due_on: event.target.value })} required /></label>
            <label>MYR asset<select value={form.asset_id} onChange={(event) => setForm({ ...form, asset_id: event.target.value })} required><option value="">Select MYR asset</option>{formAssets.map((asset) => <option value={asset.id} key={asset.id}>{asset.symbol} · {asset.name}{asset.active ? '' : ' (inactive)'}</option>)}</select></label>
            <label>Pay from<select value={form.funding_account_id} onChange={(event) => setForm({ ...form, funding_account_id: event.target.value })} required><option value="">Select asset account</option>{formFundingAccounts.map((account) => <option value={account.id} key={account.id}>{account.name}{account.closed ? ' (closed)' : ''}</option>)}</select></label>
            <label>Expense account<select value={form.expense_account_id} onChange={(event) => setForm({ ...form, expense_account_id: event.target.value })} required><option value="">Select expense account</option>{formExpenseAccounts.map((account) => <option value={account.id} key={account.id}>{account.name}{account.closed ? ' (closed)' : ''}</option>)}</select></label>
            <label>Category<select value={form.category_id} onChange={(event) => setForm({ ...form, category_id: event.target.value })} required><option value="">Select expense category</option>{formCategories.map((category) => <option value={category.id} key={category.id}>{category.name}{category.active ? '' : ' (inactive)'}</option>)}</select>{!availableCategories.length && <small>No active categories. {onOpenCategories && <button type="button" className="text-button" onClick={onOpenCategories}>Manage categories</button>}</small>}</label>
            {!configurationReady && <p className="fixed-expense-warning wide">An active MYR asset, open ASSET account, open EXPENSE account, and active EXPENSE category are required.</p>}
            <div className="wide form-actions"><button className="primary" disabled={busy || !configurationReady}>{busy ? 'Saving…' : editing ? 'Save fixed expense' : 'Add fixed expense'}</button></div>
          </form>
        </section>
      )}

      {action && (
        <section className="panel fixed-action-panel">
          <span className="eyebrow">CONFIRM PAYMENT WORKFLOW</span>
          <h2>{action.kind === 'record' ? 'Record payment' : 'Skip current occurrence'}</h2>
          <p className="form-intro">{action.expense.name} · {action.expense.next_due_on} · {formatMyr(action.expense.amount_myr)}</p>
          {action.kind === 'record' ? (
            <form className="fixed-action-form" onSubmit={(event) => { event.preventDefault(); void confirmAction() }}>
              <label>Actual occurred at<input aria-label="Actual occurred at" type="datetime-local" value={occurredAt} onChange={(event) => setOccurredAt(event.target.value)} required /></label>
              <div className="form-actions"><button type="button" className="secondary" onClick={() => setAction(null)}>Cancel</button><button className="primary" disabled={busy}>Confirm record payment</button></div>
            </form>
          ) : (
            <form className="fixed-action-form" onSubmit={(event) => { event.preventDefault(); void confirmAction() }}>
              <label>Reason (optional)<input aria-label="Skip reason" value={skipReason} onChange={(event) => setSkipReason(event.target.value)} maxLength={500} placeholder="Why is this occurrence being skipped?" /></label>
              <div className="form-actions"><button type="button" className="secondary" onClick={() => setAction(null)}>Cancel</button><button className="primary" disabled={busy}>Confirm skip</button></div>
            </form>
          )}
        </section>
      )}

      {selected && (
        <section className="panel fixed-history-panel">
          <div className="section-title"><div><span className="eyebrow">PROCESSING HISTORY</span><h2>{selected.name}</h2></div><span className="count">{history.length}</span></div>
          {historyError && <div className="alert">{historyError}</div>}
          {historyLoading ? <p className="empty">Loading history…</p> : history.length ? <div className="fixed-history-list">{history.map((item) => (
            <div className="fixed-history-row" key={item.id}>
              <div><strong>{item.due_on}</strong><small>{item.action === 'RECORDED' ? `Recorded ${item.occurred_at ?? ''}` : `Skipped${item.skip_reason ? ` · ${item.skip_reason}` : ''}`}</small></div>
              <span>{formatMyr(item.scheduled_amount_myr)}</span>
              <span className={item.event_status === 'REVERSED' ? 'pill reversed' : 'pill'}>{item.event_status ?? item.action}</span>
              {item.event_id && (onOpenEvent ? <button className="text-button" onClick={() => onOpenEvent(item.event_id!)}>View event</button> : <code>{item.event_id}</code>)}
            </div>
          ))}</div> : <p className="empty">No processing history yet.</p>}
        </section>
      )}
    </div>
  )
}
