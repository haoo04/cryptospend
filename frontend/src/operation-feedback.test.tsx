// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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
  onboard: vi.fn(),
  createManualEvent: vi.fn(),
  uploadReceipt: vi.fn(),
}))

vi.mock('./api', () => ({ api: apiMock }))

import App from './App'

const recurringExpenses = {
  as_of: '2026-09-08',
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
}

beforeEach(() => {
  apiMock.assets.mockReset().mockResolvedValue([])
  apiMock.accounts.mockReset().mockResolvedValue([])
  apiMock.categories.mockReset().mockResolvedValue([])
  apiMock.recurringExpenses.mockReset().mockResolvedValue(recurringExpenses)
  apiMock.events.mockReset().mockResolvedValue([])
  apiMock.summary.mockReset().mockResolvedValue({
    net_worth_myr: '0',
    income_myr: '0',
    expense_myr: '0',
    gross_spending_myr: '0',
    net_spending_myr: '0',
  })
  apiMock.portfolio.mockReset().mockResolvedValue([])
  apiMock.fees.mockReset().mockResolvedValue({ total_myr: '0', components: [] })
  apiMock.cards.mockReset().mockResolvedValue([])
  apiMock.cardCosts.mockReset().mockResolvedValue([])
  apiMock.monthly.mockReset().mockResolvedValue(null)
  apiMock.journeys.mockReset().mockResolvedValue([])
  apiMock.snapshots.mockReset().mockResolvedValue([])
  apiMock.googleDriveBackupStatus.mockReset().mockResolvedValue({
    configured: false,
    supported: true,
    connected: false,
    folder_name: 'CryptoSpend Backups',
    message: null,
  })
  apiMock.onboard.mockReset().mockResolvedValue(undefined)
  apiMock.createManualEvent.mockReset().mockResolvedValue({ id: 'event-1' })
  apiMock.uploadReceipt.mockReset().mockResolvedValue(undefined)
})

afterEach(cleanup)

describe('operation result handling', () => {
  it('shows a success popup after a persisted operation and refresh', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Initialize CryptoSpend' }))

    const notice = await screen.findByRole('status')
    expect(notice.textContent).toContain('CryptoSpend initialized successfully.')
  })

  it('shows an API failure as a persistent error popup', async () => {
    apiMock.onboard.mockRejectedValueOnce(new Error('Database is locked'))
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Initialize CryptoSpend' }))

    const notice = await screen.findByRole('alert')
    expect(notice.textContent).toContain('Unable to initialize CryptoSpend')
    expect(notice.textContent).toContain('Database is locked')
  })

  it('reports a refresh failure as warning after the write succeeds', async () => {
    render(<App />)
    const initialize = await screen.findByRole('button', { name: 'Initialize CryptoSpend' })
    apiMock.assets.mockRejectedValueOnce(new Error('Refresh is offline'))
    fireEvent.click(initialize)

    const notice = await screen.findByRole('alert')
    expect(notice.textContent).toContain('Saved, but refresh failed')
    expect(notice.textContent).toContain('CryptoSpend initialized successfully.')
    expect(notice.textContent).toContain('Refresh is offline')
  })

  it('warns without encouraging a duplicate transaction when receipt upload fails', async () => {
    apiMock.assets.mockResolvedValue([
      { id: 'myr', symbol: 'MYR', name: 'Malaysian Ringgit', decimals: 6, chain: null, contract_address: null, active: true },
    ])
    apiMock.accounts.mockResolvedValue([
      { id: 'bank', name: 'Bank', account_type: 'ASSET', channel_type: 'BANK', provider: null, closed: false, balances: [], available_balances: [] },
      { id: 'income', name: 'Income', account_type: 'INCOME', channel_type: 'OTHER', provider: null, closed: false, balances: [], available_balances: [] },
    ])
    apiMock.uploadReceipt.mockRejectedValueOnce(new Error('Image is too large'))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Add transaction' }))
    fireEvent.change(screen.getByLabelText('Debit account'), { target: { value: 'bank' } })
    fireEvent.change(screen.getByLabelText('Credit account'), { target: { value: 'income' } })
    fireEvent.change(screen.getByLabelText('Asset'), { target: { value: 'myr' } })
    fireEvent.change(screen.getByLabelText('MYR amount'), { target: { value: '100.50' } })
    fireEvent.change(screen.getByLabelText('Receipt image (optional)'), {
      target: { files: [new File(['receipt'], 'receipt.png', { type: 'image/png' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Post balanced event' }))

    const notice = await screen.findByRole('alert')
    expect(notice.textContent).toContain('Transaction saved, but receipt upload failed')
    expect(notice.textContent).toContain('Transaction event-1 was saved')
    expect(notice.textContent).toContain('Open the transaction to retry the receipt')
    expect(screen.getByLabelText('MYR amount')).toHaveProperty('value', '')
  })
})
