// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  searchEvents: vi.fn(),
  receiptUrl: vi.fn(),
}))

vi.mock('./api', () => ({ api: apiMock }))

import { Transactions } from './App'
import type { Category, EventSearchPage, TransactionEvent } from './api'

const categories: Category[] = [
  { id: 'food', name: 'Food', kind: 'EXPENSE', active: true, created_at: '', updated_at: '' },
  { id: 'subscription', name: 'Subscription', kind: 'EXPENSE', active: false, created_at: '', updated_at: '' },
]

function event(overrides: Partial<TransactionEvent> = {}): TransactionEvent {
  return {
    id: 'event-1',
    event_type: 'EXPENSE',
    status: 'POSTED',
    occurred_at: '2026-08-01T04:00:00+00:00',
    time_precision: 'EXACT',
    description: 'Lunch',
    category: 'Food',
    category_id: 'food',
    category_kind: 'EXPENSE',
    source: 'MANUAL',
    external_id: null,
    transaction_value_myr: '25.50',
    reference_value_myr: null,
    reverses_event_id: null,
    reversed_by_event_id: null,
    posted_at: '2026-08-01T04:00:00+00:00',
    entries: [],
    fees: [],
    receipt: null,
    ...overrides,
  }
}

function page(items: TransactionEvent[], total = items.length, currentPage = 1): EventSearchPage {
  return { items, total, page: currentPage, page_size: 50 }
}

function renderTransactions() {
  return render(
    <Transactions
      categories={categories}
      busy={false}
      selected={null}
      onSelect={vi.fn()}
      onChangeCategory={vi.fn(async () => true)}
      onUploadReceipt={vi.fn(async () => true)}
      onDeleteReceipt={vi.fn(async () => true)}
      onReverse={vi.fn(async () => true)}
    />,
  )
}

beforeEach(() => {
  apiMock.searchEvents.mockReset().mockResolvedValue(page([event()]))
  apiMock.receiptUrl.mockReset().mockReturnValue('/api/events/event-1/receipt')
})

afterEach(cleanup)

describe('transaction search and filters', () => {
  it('loads transactions and sends all applied filters to the search API', async () => {
    const filtered = event({ id: 'event-2', description: 'Cloud hosting', category: 'Subscription', category_id: 'subscription' })
    apiMock.searchEvents
      .mockResolvedValueOnce(page([event(), filtered], 2))
      .mockResolvedValueOnce(page([filtered]))
    renderTransactions()

    expect(await screen.findByText('Cloud hosting')).toBeTruthy()
    expect(screen.getByText('Showing 1–2 of 2')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Search transactions'), { target: { value: 'cloud' } })
    fireEvent.change(screen.getByLabelText('Transaction type'), { target: { value: 'EXPENSE' } })
    fireEvent.change(screen.getByLabelText('Transaction status'), { target: { value: 'POSTED' } })
    fireEvent.change(screen.getByLabelText('Transaction category'), { target: { value: 'subscription' } })
    fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-08-01' } })
    fireEvent.change(screen.getByLabelText('To date'), { target: { value: '2026-08-31' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() => expect(apiMock.searchEvents).toHaveBeenLastCalledWith({
      q: 'cloud',
      event_type: 'EXPENSE',
      status: 'POSTED',
      category_id: 'subscription',
      from_date: '2026-08-01',
      to_date: '2026-08-31',
      page: 1,
      page_size: 50,
    }))
    expect(await screen.findByText('Showing 1–1 of 1')).toBeTruthy()
  })

  it('clears filters and loads the next page', async () => {
    const secondPageEvent = event({ id: 'event-2', description: 'Second page' })
    apiMock.searchEvents
      .mockResolvedValueOnce(page([event()], 51))
      .mockResolvedValueOnce(page([secondPageEvent], 51, 2))
      .mockResolvedValueOnce(page([event()], 1))
    renderTransactions()

    await screen.findByText('Lunch')
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Second page')).toBeTruthy()
    expect(apiMock.searchEvents).toHaveBeenLastCalledWith({ page: 2, page_size: 50 })

    fireEvent.change(screen.getByLabelText('Search transactions'), { target: { value: 'lunch' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
    await waitFor(() => expect(apiMock.searchEvents).toHaveBeenLastCalledWith({
      q: 'lunch',
      page: 1,
      page_size: 50,
    }))

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    await waitFor(() => expect(apiMock.searchEvents).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 50,
    }))
  })

  it('shows a filtered empty state for a search with no matches', async () => {
    apiMock.searchEvents
      .mockResolvedValueOnce(page([event()]))
      .mockResolvedValueOnce(page([], 0))
    renderTransactions()

    await screen.findByText('Lunch')
    fireEvent.change(screen.getByLabelText('Search transactions'), { target: { value: 'missing' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

    expect((await screen.findAllByText('No transactions match the current filters.')).length).toBeGreaterThan(0)
  })
})
