// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AddTransaction } from './App'
import type { Account, Asset } from './api'

const assets: Asset[] = [
  { id: 'myr', symbol: 'MYR', name: 'Malaysian Ringgit', decimals: 2, chain: null, contract_address: null, active: true },
  { id: 'usdt', symbol: 'USDT', name: 'Tether', decimals: 6, chain: null, contract_address: null, active: true },
]

const accounts: Account[] = [
  { id: 'asset-account', name: 'Bank', account_type: 'ASSET', channel_type: 'BANK', provider: null, closed: false, balances: [], available_balances: [] },
  { id: 'income-account', name: 'Income', account_type: 'INCOME', channel_type: 'OTHER', provider: null, closed: false, balances: [], available_balances: [] },
]

afterEach(cleanup)

describe('manual MYR transaction entry', () => {
  it('uses one MYR amount for both quantity and book amount', async () => {
    const onSubmit = vi.fn(async () => undefined)

    render(
      <AddTransaction
        assets={assets}
        accounts={accounts}
        busy={false}
        onSubmit={onSubmit}
        onTrade={vi.fn(async () => undefined)}
        onTransfer={vi.fn(async () => undefined)}
      />,
    )

    fireEvent.change(screen.getByLabelText('Asset'), { target: { value: 'myr' } })
    fireEvent.change(screen.getByLabelText('Debit account'), { target: { value: 'asset-account' } })
    fireEvent.change(screen.getByLabelText('Credit account'), { target: { value: 'income-account' } })
    fireEvent.change(screen.getByLabelText('MYR amount'), { target: { value: '100.50' } })

    expect(screen.queryByLabelText('Original quantity')).toBeNull()
    expect(screen.queryByLabelText('Book amount (MYR)')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Post balanced event' }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: 'myr',
          quantity: '100.50',
          book_amount_myr: '100.50',
        }),
      ),
    )
  })

  it('keeps separate quantity and book amount fields for non-MYR assets', () => {
    render(
      <AddTransaction
        assets={assets}
        accounts={accounts}
        busy={false}
        onSubmit={vi.fn(async () => undefined)}
        onTrade={vi.fn(async () => undefined)}
        onTransfer={vi.fn(async () => undefined)}
      />,
    )

    fireEvent.change(screen.getByLabelText('Asset'), { target: { value: 'usdt' } })

    expect(screen.getByLabelText('Original quantity')).toBeTruthy()
    expect(screen.getByLabelText('Book amount (MYR)')).toBeTruthy()
    expect(screen.queryByLabelText('MYR amount')).toBeNull()
  })
})
