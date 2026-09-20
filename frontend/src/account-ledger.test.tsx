// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  accountLedger: vi.fn(),
}))

vi.mock('./api', () => ({ api: apiMock }))

import AccountLedger from './AccountLedger'
import type { Account, AccountLedgerItem, AccountLedgerPage, Asset } from './api'

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
  provider: 'Wallet',
  closed: false,
  balances: [{ asset_id: 'myr', asset_symbol: 'MYR', quantity: '90.00', book_amount_myr: '90.00' }],
  available_balances: [{ asset_id: 'myr', asset_symbol: 'MYR', quantity: '90.00', book_amount_myr: '90.00' }],
}

function item(overrides: Partial<AccountLedgerItem> = {}): AccountLedgerItem {
  return {
    event_id: 'event-1',
    event_type: 'EXPENSE',
    event_status: 'POSTED',
    occurred_at: '2026-08-01T04:00:00+00:00',
    time_precision: 'EXACT',
    description: 'Lunch',
    category: 'Food',
    source: 'MANUAL',
    reverses_event_id: null,
    reversed_by_event_id: null,
    asset_id: 'myr',
    asset_symbol: 'MYR',
    quantity_change: '-10.00',
    book_amount_myr_change: '-10.00',
    balance_after_quantity: '90.00',
    balance_after_book_amount_myr: '90.00',
    entry_count: 1,
    counterparties: [{ account_id: 'food', account_name: 'Food expense', account_type: 'EXPENSE' }],
    receipt_attached: false,
    ...overrides,
  }
}

function page(items: AccountLedgerItem[], total = items.length, currentPage = 1): AccountLedgerPage {
  return { account, timezone: 'Asia/Kuala_Lumpur', items, total, page: currentPage, page_size: 50 }
}

function renderLedger(refreshVersion = 0, onInspectEvent = vi.fn()) {
  return render(
    <AccountLedger
      accountId="cash"
      assets={[asset]}
      refreshVersion={refreshVersion}
      onBack={vi.fn()}
      onInspectEvent={onInspectEvent}
    />,
  )
}

beforeEach(() => {
  apiMock.accountLedger.mockReset().mockResolvedValue(page([item()]))
})

afterEach(cleanup)

describe('account ledger page', () => {
  it('loads exact balances, applies filters, paginates, and inspects events', async () => {
    const second = item({ event_id: 'event-2', description: 'Dinner', quantity_change: '+20.00000000', book_amount_myr_change: '20', balance_after_quantity: '110.00000000' })
    apiMock.accountLedger.mockResolvedValueOnce(page([item()], 51)).mockResolvedValueOnce(page([item({ description: 'Filtered lunch' })], 51)).mockResolvedValueOnce(page([second], 51, 2))
    const onInspectEvent = vi.fn()
    renderLedger(0, onInspectEvent)

    expect(await screen.findByRole('heading', { name: 'Cash account' })).toBeTruthy()
    expect(screen.getByText('−10.00 MYR')).toBeTruthy()
    expect(screen.getByText('−RM 10.00')).toBeTruthy()
    expect(apiMock.accountLedger).toHaveBeenLastCalledWith('cash', { page: 1, page_size: 50 })

    fireEvent.change(screen.getByLabelText('Search account activity'), { target: { value: 'dinner' } })
    fireEvent.change(screen.getByLabelText('Account ledger asset'), { target: { value: 'myr' } })
    fireEvent.change(screen.getByLabelText('Account ledger event type'), { target: { value: 'EXPENSE' } })
    fireEvent.change(screen.getByLabelText('Account ledger from date'), { target: { value: '2026-08-01' } })
    fireEvent.change(screen.getByLabelText('Account ledger to date'), { target: { value: '2026-08-31' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() => expect(apiMock.accountLedger).toHaveBeenLastCalledWith('cash', {
      q: 'dinner',
      asset_id: 'myr',
      event_type: 'EXPENSE',
      from_date: '2026-08-01',
      to_date: '2026-08-31',
      page: 1,
      page_size: 50,
    }))

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Dinner')).toBeTruthy()
    expect(apiMock.accountLedger).toHaveBeenLastCalledWith('cash', {
      q: 'dinner',
      asset_id: 'myr',
      event_type: 'EXPENSE',
      from_date: '2026-08-01',
      to_date: '2026-08-31',
      page: 2,
      page_size: 50,
    })

    fireEvent.click(screen.getByRole('button', { name: 'Inspect event event-2' }))
    expect(onInspectEvent).toHaveBeenCalledWith('event-2')
  })

  it('keeps the last successful data on failure and retries', async () => {
    apiMock.accountLedger.mockResolvedValueOnce(page([item()])).mockRejectedValueOnce(new Error('Ledger offline')).mockResolvedValueOnce(page([item({ description: 'Recovered' })]))
    renderLedger()
    await screen.findByText('Lunch')

    fireEvent.change(screen.getByLabelText('Search account activity'), { target: { value: 'offline' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Ledger offline')
    expect(screen.getByText('Lunch')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Recovered')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('does not let an older response replace a newer filter result', async () => {
    let resolveFirst!: (value: AccountLedgerPage) => void
    let resolveSecond!: (value: AccountLedgerPage) => void
    const first = new Promise<AccountLedgerPage>((resolve) => { resolveFirst = resolve })
    const second = new Promise<AccountLedgerPage>((resolve) => { resolveSecond = resolve })
    apiMock.accountLedger.mockReset().mockReturnValueOnce(first).mockReturnValueOnce(second)
    renderLedger()
    await waitFor(() => expect(apiMock.accountLedger).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByLabelText('Search account activity'), { target: { value: 'new' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
    await waitFor(() => expect(apiMock.accountLedger).toHaveBeenCalledTimes(2))

    await act(async () => resolveSecond(page([item({ description: 'New result' })])))
    expect(await screen.findByText('New result')).toBeTruthy()
    await act(async () => resolveFirst(page([item({ description: 'Old result' })])))
    expect(screen.getByText('New result')).toBeTruthy()
    expect(screen.queryByText('Old result')).toBeNull()
  })
})
