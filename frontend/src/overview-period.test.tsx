// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  assets: vi.fn(),
  accounts: vi.fn(),
  categories: vi.fn(),
  recurringExpenses: vi.fn(),
  events: vi.fn(),
  summary: vi.fn(),
  portfolio: vi.fn(),
  fees: vi.fn(),
  cards: vi.fn(),
  cardCosts: vi.fn(),
  monthly: vi.fn(),
  journeys: vi.fn(),
  snapshots: vi.fn(),
  googleDriveBackupStatus: vi.fn(),
}))

vi.mock('./api', () => ({ api: apiMock }))

import App from './App'
import type { Account, Asset, MonthlyReport, Summary, TransactionEvent } from './api'

const allTimeSummary: Summary = {
  net_worth_myr: '1000.00',
  income_myr: '200.00',
  expense_myr: '150.00',
  gross_spending_myr: '160.00',
  net_spending_myr: '140.00',
}

const asset: Asset = {
  id: 'myr',
  symbol: 'MYR',
  name: 'Malaysian Ringgit',
  decimals: 2,
  chain: null,
  contract_address: null,
  active: true,
}

const account: Account = {
  id: 'cash',
  name: 'Cash account',
  account_type: 'ASSET',
  channel_type: 'CASH',
  provider: null,
  closed: false,
  balances: [{ asset_id: 'myr', asset_symbol: 'MYR', quantity: '1000.00', book_amount_myr: '1000.00' }],
  available_balances: [{ asset_id: 'myr', asset_symbol: 'MYR', quantity: '1000.00', book_amount_myr: '1000.00' }],
}

const ledgerEvent: TransactionEvent = {
  id: 'event-1',
  event_type: 'SALARY',
  status: 'POSTED',
  occurred_at: '2026-08-15T04:00:00Z',
  time_precision: 'SECOND',
  description: 'Salary posted',
  category: null,
  category_id: null,
  category_kind: null,
  source: 'MANUAL',
  external_id: null,
  transaction_value_myr: '200.00',
  reference_value_myr: null,
  reverses_event_id: null,
  reversed_by_event_id: null,
  posted_at: '2026-08-15T04:00:00Z',
  entries: [],
  fees: [],
  receipt: null,
}

function monthlyReport(
  month: string,
  summary: Summary = {
    net_worth_myr: '0',
    income_myr: '0',
    expense_myr: '0',
    gross_spending_myr: '0',
    net_spending_myr: '0',
  },
  feeTotal = '0',
): MonthlyReport {
  return {
    month,
    timezone: 'Asia/Kuala_Lumpur',
    period_start: `${month}-01T00:00:00+08:00`,
    period_end: `${month}-28T00:00:00+08:00`,
    summary,
    fees: { total_myr: feeTotal, components: [] },
    fee_leakage: { explicit_myr: feeTotal, derived_myr: '0', total_leakage_myr: feeTotal, components: [] },
    channels: [],
    portfolio: [],
  }
}

function metricValue(label: string) {
  return screen.getByText(label, { selector: '.metric > span' }).parentElement?.querySelector('strong')?.textContent
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

async function renderOverview() {
  render(<App />)
  await screen.findByRole('button', { name: 'Month' })
}

beforeEach(() => {
  apiMock.assets.mockReset().mockResolvedValue([asset])
  apiMock.accounts.mockReset().mockResolvedValue([account])
  apiMock.categories.mockReset().mockResolvedValue([])
  apiMock.recurringExpenses.mockReset().mockResolvedValue({
    as_of: '2026-09-20',
    timezone: 'Asia/Kuala_Lumpur',
    summary: {
      active_count: 0,
      overdue_count: 0,
      weekly_total_myr: '0',
      monthly_total_myr: '0',
      yearly_total_myr: '0',
      annualized_myr: '0',
    },
    items: [],
  })
  apiMock.events.mockReset().mockResolvedValue([ledgerEvent])
  apiMock.summary.mockReset().mockResolvedValue(allTimeSummary)
  apiMock.portfolio.mockReset().mockResolvedValue([])
  apiMock.fees.mockReset().mockResolvedValue({ total_myr: '6.00', components: [] })
  apiMock.cards.mockReset().mockResolvedValue([])
  apiMock.cardCosts.mockReset().mockResolvedValue([])
  apiMock.monthly.mockReset().mockImplementation((month: string) => Promise.resolve(monthlyReport(month)))
  apiMock.journeys.mockReset().mockResolvedValue([])
  apiMock.snapshots.mockReset().mockResolvedValue([])
  apiMock.googleDriveBackupStatus.mockReset().mockResolvedValue({
    configured: false,
    supported: true,
    connected: false,
    folder_name: 'CryptoSpend Backups',
    message: null,
  })
})

afterEach(cleanup)

describe('Overview period selection', () => {
  it('defaults to all time and shows all six ledger metrics', async () => {
    await renderOverview()

    expect(screen.getByRole('button', { name: 'All time' }).getAttribute('aria-pressed')).toBe('true')
    expect(metricValue('Net worth (book)')).toBe('RM 1,000.00')
    expect(metricValue('Income')).toBe('RM 200.00')
    expect(metricValue('Expenses')).toBe('RM 150.00')
    expect(metricValue('Gross spending')).toBe('RM 160.00')
    expect(metricValue('Net spending')).toBe('RM 140.00')
    expect(metricValue('Explicit fees')).toBe('RM 6.00')
    expect(screen.getByText('Cash account')).toBeTruthy()
    expect(screen.getByText('Salary posted')).toBeTruthy()
    expect(apiMock.monthly).toHaveBeenCalledTimes(1)
  })

  it('loads a selected month without changing activity, accounts, or Portfolio fees', async () => {
    const augustSummary: Summary = {
      net_worth_myr: '880.00',
      income_myr: '82.00',
      expense_myr: '72.00',
      gross_spending_myr: '75.00',
      net_spending_myr: '68.00',
    }
    apiMock.monthly.mockImplementation((month: string) => Promise.resolve(
      month === '2026-08' ? monthlyReport(month, augustSummary, '4.00') : monthlyReport(month),
    ))
    await renderOverview()

    fireEvent.click(screen.getByRole('button', { name: 'Month' }))
    const monthInput = await screen.findByLabelText('Overview month') as HTMLInputElement
    await waitFor(() => expect(monthInput.disabled).toBe(false))
    fireEvent.change(monthInput, { target: { value: '2026-08' } })

    await screen.findByText('August 2026 · Asia/Kuala_Lumpur')
    expect(apiMock.monthly).toHaveBeenLastCalledWith('2026-08')
    expect(metricValue('Net worth (book)')).toBe('RM 880.00')
    expect(metricValue('Income')).toBe('RM 82.00')
    expect(metricValue('Expenses')).toBe('RM 72.00')
    expect(metricValue('Gross spending')).toBe('RM 75.00')
    expect(metricValue('Net spending')).toBe('RM 68.00')
    expect(metricValue('Explicit fees')).toBe('RM 4.00')
    expect(screen.getByText('As of month end')).toBeTruthy()
    expect(screen.getAllByText('During selected month')).toHaveLength(5)
    expect(screen.getByText('Cash account')).toBeTruthy()
    expect(screen.getByText('Salary posted')).toBeTruthy()

    apiMock.monthly.mockClear()
    fireEvent.change(monthInput, { target: { value: '' } })
    expect(apiMock.monthly).not.toHaveBeenCalled()
    expect(metricValue('Income')).toBe('RM 82.00')

    fireEvent.click(screen.getByRole('button', { name: 'Portfolio' }))
    await screen.findByRole('heading', { name: 'Fee leakage' })
    expect(screen.getByText('RM 6.00')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
    expect(metricValue('Explicit fees')).toBe('RM 4.00')
    fireEvent.click(screen.getByRole('button', { name: 'All time' }))
    expect(metricValue('Net worth (book)')).toBe('RM 1,000.00')
    expect(metricValue('Explicit fees')).toBe('RM 6.00')
  })

  it('keeps the last successful values on failure and supports retry', async () => {
    await renderOverview()
    apiMock.monthly.mockRejectedValueOnce(new Error('Monthly report offline'))

    fireEvent.click(screen.getByRole('button', { name: 'Month' }))
    const error = await screen.findByRole('alert')
    expect(error.textContent).toContain('Monthly report offline')
    expect(metricValue('Net worth (book)')).toBe('RM 1,000.00')

    const month = (screen.getByLabelText('Overview month') as HTMLInputElement).value
    apiMock.monthly.mockResolvedValueOnce(monthlyReport(month, {
      net_worth_myr: '990.00',
      income_myr: '90.00',
      expense_myr: '80.00',
      gross_spending_myr: '85.00',
      net_spending_myr: '75.00',
    }, '5.00'))
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => expect(metricValue('Net worth (book)')).toBe('RM 990.00'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('ignores an older month response that finishes last', async () => {
    await renderOverview()
    fireEvent.click(screen.getByRole('button', { name: 'Month' }))
    const monthInput = await screen.findByLabelText('Overview month') as HTMLInputElement
    await waitFor(() => expect(monthInput.disabled).toBe(false))

    const january = deferred<MonthlyReport>()
    const february = deferred<MonthlyReport>()
    apiMock.monthly.mockImplementation((month: string) => {
      if (month === '2025-01') return january.promise
      if (month === '2025-02') return february.promise
      return Promise.resolve(monthlyReport(month))
    })

    fireEvent.change(monthInput, { target: { value: '2025-01' } })
    monthInput.removeAttribute('disabled')
    fireEvent.change(monthInput, { target: { value: '2025-02' } })

    await act(async () => february.resolve(monthlyReport('2025-02', {
      net_worth_myr: '202.00',
      income_myr: '20.00',
      expense_myr: '2.00',
      gross_spending_myr: '3.00',
      net_spending_myr: '1.00',
    })))
    await screen.findByText('February 2025 · Asia/Kuala_Lumpur')

    await act(async () => january.resolve(monthlyReport('2025-01', {
      net_worth_myr: '101.00',
      income_myr: '10.00',
      expense_myr: '1.00',
      gross_spending_myr: '2.00',
      net_spending_myr: '1.00',
    })))
    expect(metricValue('Net worth (book)')).toBe('RM 202.00')
    expect(screen.queryByText('January 2025 · Asia/Kuala_Lumpur')).toBeNull()
  })

  it('refreshes the applied month and preserves it until the user returns to all time', async () => {
    const selectedMonth = '2025-05'
    let selectedReport = monthlyReport(selectedMonth, {
      net_worth_myr: '500.00',
      income_myr: '50.00',
      expense_myr: '40.00',
      gross_spending_myr: '45.00',
      net_spending_myr: '35.00',
    }, '3.00')
    apiMock.monthly.mockImplementation((month: string) => Promise.resolve(
      month === selectedMonth ? selectedReport : monthlyReport(month),
    ))
    await renderOverview()

    fireEvent.click(screen.getByRole('button', { name: 'Month' }))
    const monthInput = await screen.findByLabelText('Overview month') as HTMLInputElement
    await waitFor(() => expect(monthInput.disabled).toBe(false))
    fireEvent.change(monthInput, { target: { value: selectedMonth } })
    await screen.findByText('May 2025 · Asia/Kuala_Lumpur')

    selectedReport = monthlyReport(selectedMonth, {
      net_worth_myr: '550.00',
      income_myr: '55.00',
      expense_myr: '44.00',
      gross_spending_myr: '49.00',
      net_spending_myr: '39.00',
    }, '3.50')
    apiMock.summary.mockResolvedValue({ ...allTimeSummary, net_worth_myr: '1100.00' })
    apiMock.fees.mockResolvedValue({ total_myr: '7.00', components: [] })
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => expect(metricValue('Net worth (book)')).toBe('RM 550.00'))
    expect(screen.getByRole('button', { name: 'Month' }).getAttribute('aria-pressed')).toBe('true')
    expect(metricValue('Explicit fees')).toBe('RM 3.50')
    expect(apiMock.monthly.mock.calls.filter(([month]) => month === selectedMonth).length).toBeGreaterThanOrEqual(2)

    fireEvent.click(screen.getByRole('button', { name: 'All time' }))
    expect(metricValue('Net worth (book)')).toBe('RM 1,100.00')
    expect(metricValue('Explicit fees')).toBe('RM 7.00')
  })
})
