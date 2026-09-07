// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TradeForm } from './App'
import type { Account, Asset } from './api'

const assets: Asset[] = [
  { id: 'myr', symbol: 'MYR', name: 'Malaysian Ringgit', decimals: 6, chain: null, contract_address: null, active: true },
  { id: 'usdt', symbol: 'USDT', name: 'Tether', decimals: 18, chain: null, contract_address: null, active: true },
  { id: 'eth', symbol: 'ETH', name: 'Ether', decimals: 18, chain: null, contract_address: null, active: true },
]

const accounts: Account[] = [
  { id: 'wallet', name: 'Wallet', account_type: 'ASSET', channel_type: 'CRYPTO_WALLET', provider: null, closed: false, balances: [], available_balances: [] },
  { id: 'gain', name: 'Gain/Loss', account_type: 'GAIN_LOSS', channel_type: 'OTHER', provider: null, closed: false, balances: [], available_balances: [] },
  { id: 'fee', name: 'Trading Fees', account_type: 'EXPENSE', channel_type: 'OTHER', provider: null, closed: false, balances: [], available_balances: [] },
]

afterEach(cleanup)

function renderTrade(onSubmit = vi.fn(async () => undefined)) {
  render(<TradeForm assets={assets} accounts={accounts} busy={false} onSubmit={onSubmit} />)
  return onSubmit
}

function selectPair(sell: string, buy: string) {
  fireEvent.change(screen.getByLabelText('Sell asset'), { target: { value: sell } })
  fireEvent.change(screen.getByLabelText('Buy asset'), { target: { value: buy } })
}

describe('trade amount calculation', () => {
  it('calculates USDT from MYR and submits the canonical inverse rate', async () => {
    const onSubmit = renderTrade()
    selectPair('myr', 'usdt')
    fireEvent.change(screen.getByLabelText('Exchange account'), { target: { value: 'wallet' } })
    fireEvent.change(screen.getByLabelText('Gain/loss account'), { target: { value: 'gain' } })
    fireEvent.change(screen.getByLabelText('Sell amount'), { target: { value: '2800' } })
    fireEvent.change(screen.getByLabelText('Exchange rate'), { target: { value: '4.05797' } })

    expect(screen.getByText('1 USDT =')).toBeTruthy()
    expect(screen.getByText('MYR', { selector: '.rate-equation > span:last-child' })).toBeTruthy()
    expect(screen.getByLabelText('Receive amount')).toHaveProperty('value', '690.000172500043125011')
    expect(screen.getByLabelText('Gross transaction value (MYR)')).toHaveProperty('value', '2800')

    fireEvent.click(screen.getByRole('button', { name: 'Post trade' }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      sell_asset_id: 'myr',
      sell_quantity: '2800',
      buy_asset_id: 'usdt',
      buy_quantity: '690.000172500043125011',
      execution_rate: '0.246428633035729687503928571429',
      gross_value_myr: '2800',
    })))
  })

  it('recalculates the displayed MYR rate when the received amount is edited', () => {
    renderTrade()
    selectPair('usdt', 'myr')
    fireEvent.change(screen.getByLabelText('Sell amount'), { target: { value: '100' } })
    fireEvent.change(screen.getByLabelText('Exchange rate'), { target: { value: '4.25' } })
    expect(screen.getByLabelText('Receive amount')).toHaveProperty('value', '425')

    fireEvent.change(screen.getByLabelText('Receive amount'), { target: { value: '424' } })
    expect(screen.getByLabelText('Exchange rate')).toHaveProperty('value', '4.24')
    expect(screen.getByLabelText('Gross transaction value (MYR)')).toHaveProperty('value', '424')
  })

  it('subtracts an included fee paid in the buy asset from the net amount', () => {
    renderTrade()
    selectPair('eth', 'myr')
    fireEvent.change(screen.getByLabelText('Sell amount'), { target: { value: '0.25' } })
    fireEvent.change(screen.getByLabelText('Exchange rate'), { target: { value: '17000' } })
    fireEvent.change(screen.getByLabelText('Fee asset'), { target: { value: 'myr' } })
    fireEvent.change(screen.getByLabelText('Fee quantity'), { target: { value: '8.5' } })
    fireEvent.click(screen.getByLabelText('Fee is already included in the funding/net amount'))

    expect(screen.getByLabelText('Receive amount')).toHaveProperty('value', '4241.5')
    expect(screen.getByLabelText('Gross transaction value (MYR)')).toHaveProperty('value', '4250')
  })
})
