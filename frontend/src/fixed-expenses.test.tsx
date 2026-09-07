// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'

import FixedExpensesCenter from './FixedExpensesCenter'
import type {
  Account,
  Asset,
  Category,
  RecurringExpenseList,
} from './api'

const assets: Asset[] = [
  { id: 'myr', symbol: 'MYR', name: 'Malaysian Ringgit', decimals: 6, chain: null, contract_address: null, active: true },
]

const accounts: Account[] = [
  { id: 'bank', name: 'Bank', account_type: 'ASSET', channel_type: 'BANK', provider: null, closed: false, balances: [], available_balances: [] },
  { id: 'expense', name: 'General Expense', account_type: 'EXPENSE', channel_type: 'OTHER', provider: null, closed: false, balances: [], available_balances: [] },
]

const categories: Category[] = [
  { id: 'subscription', name: 'Subscription', kind: 'EXPENSE', active: true, created_at: '', updated_at: '' },
]

function data(overrides: Partial<RecurringExpenseList> = {}): RecurringExpenseList {
  return {
    as_of: '2026-09-07',
    timezone: 'Asia/Kuala_Lumpur',
    summary: {
      active_count: 1,
      overdue_count: 0,
      weekly_total_myr: '0',
      monthly_total_myr: '55.90',
      yearly_total_myr: '0',
      annualized_myr: '670.8',
    },
    items: [],
    ...overrides,
  }
}

const item = {
  id: 'rent',
  name: 'Netflix',
  amount_myr: '55.90',
  frequency: 'MONTHLY' as const,
  anchor_on: '2026-09-01',
  next_due_on: '2026-10-01',
  due_status: 'UPCOMING' as const,
  annualized_amount_myr: '670.8',
  asset_id: 'myr',
  funding_account_id: 'bank',
  expense_account_id: 'expense',
  category_id: 'subscription',
  active: true,
  created_at: '',
  updated_at: '',
}

afterEach(cleanup)

function renderCenter(overrides: Partial<ComponentProps<typeof FixedExpensesCenter>> = {}) {
  return render(
    <FixedExpensesCenter
      assets={assets}
      accounts={accounts}
      categories={categories}
      data={data()}
      busy={false}
      onCreate={vi.fn(async () => undefined)}
      onUpdate={vi.fn(async () => undefined)}
      onRecord={vi.fn(async () => undefined)}
      onSkip={vi.fn(async () => undefined)}
      onLoadHistory={vi.fn(async () => [])}
      {...overrides}
    />,
  )
}

describe('fixed expense management', () => {
  it('submits a string amount and all three schedule fields when creating', async () => {
    const onCreate = vi.fn(async () => undefined)
    renderCenter({ onCreate })

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Cloud storage' } })
    fireEvent.change(screen.getByLabelText('Amount (MYR)'), { target: { value: '12.50' } })
    fireEvent.change(screen.getByLabelText('Frequency'), { target: { value: 'YEARLY' } })
    fireEvent.change(screen.getByLabelText('First due date'), { target: { value: '2027-01-15' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add fixed expense' }))

    await waitFor(() => expect(onCreate).toHaveBeenCalledWith({
      name: 'Cloud storage',
      amount_myr: '12.50',
      frequency: 'YEARLY',
      first_due_on: '2027-01-15',
      asset_id: 'myr',
      funding_account_id: 'bank',
      expense_account_id: 'expense',
      category_id: 'subscription',
    }))
  })

  it('shows due states, server totals, and protects the form when configuration is missing', () => {
    renderCenter({
      assets: [],
      data: data({
        summary: {
          active_count: 3,
          overdue_count: 1,
          weekly_total_myr: '10',
          monthly_total_myr: '55.90',
          yearly_total_myr: '299',
          annualized_myr: '24129.8',
        },
        items: [
          { ...item, due_status: 'OVERDUE', next_due_on: '2026-09-04' },
          { ...item, id: 'today', name: 'Today', due_status: 'DUE_TODAY', next_due_on: '2026-09-07' },
          { ...item, id: 'paused', name: 'Paused', active: false, due_status: 'PAUSED' },
        ],
      }),
    })

    expect(screen.getByText('RM 24,129.8')).toBeTruthy()
    expect(screen.getAllByText('Overdue').length).toBeGreaterThan(0)
    expect(screen.getByText('Due today')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'ALL' }))
    expect(screen.getAllByText('Paused').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Add fixed expense' })).toHaveProperty('disabled', true)
  })

  it('records and skips the current due date with an actual timestamp or reason', async () => {
    const onRecord = vi.fn(async () => undefined)
    const onSkip = vi.fn(async () => undefined)
    renderCenter({ data: data({ items: [item] }), onRecord, onSkip })

    fireEvent.click(screen.getByRole('button', { name: 'Record payment for 2026-10-01' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm record payment' }))
    await waitFor(() => expect(onRecord).toHaveBeenCalledWith('rent', expect.objectContaining({
      due_on: '2026-10-01',
      occurred_at: expect.stringMatching(/Z$/),
    })))

    fireEvent.click(screen.getByRole('button', { name: 'Skip 2026-10-01' }))
    fireEvent.change(screen.getByLabelText('Skip reason'), { target: { value: 'Holiday' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm skip' }))
    await waitFor(() => expect(onSkip).toHaveBeenCalledWith('rent', { due_on: '2026-10-01', reason: 'Holiday' }))
  })

  it('does not reset the schedule when editing ordinary fields', async () => {
    const onUpdate = vi.fn(async () => undefined)
    renderCenter({ data: data({ items: [item] }), onUpdate })

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Netflix family' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save fixed expense' }))

    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith('rent', {
      name: 'Netflix family',
      amount_myr: '55.90',
      asset_id: 'myr',
      funding_account_id: 'bank',
      expense_account_id: 'expense',
      category_id: 'subscription',
    }))
  })
})
