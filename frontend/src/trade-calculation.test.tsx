// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TradeForm } from './App'
import type { Account, Asset } from './api'

const assets: Asset[] = [
  { id: 'myr', symbol: 'MYR', name: 'Malaysian Ringgit', decimals: 6, chain: null, contract_address: null, active: true },
  { id: 'usdt', symbol: 'USDT', name: 'Tether', decimals: 18, chain: null, contract_address: null, active: true },
  { id: 'eth', symbol: 'ETH', name: 'Ether', decimals: 18, chain: null, contract_address: null, active: true },
  { id: 'btc', symbol: 'BTC', name: 'Bitcoin', decimals: 8, chain: null, contract_address: null, active: true },
]

const accounts: Account[] = [
  { id: 'wallet', name: 'Wallet', account_type: 'ASSET', channel_type: 'CRYPTO_WALLET', provider: null, closed: false, balances: [], available_balances: [] },
  { id: 'gain', name: 'Gain/Loss', account_type: 'GAIN_LOSS', channel_type: 'OTHER', provider: null, closed: false, balances: [], available_balances: [] },
  { id: 'fee', name: 'Trading Fees', account_type: 'EXPENSE', channel_type: 'OTHER', provider: null, closed: false, balances: [], available_balances: [] },
]

afterEach(cleanup)

function renderTrade(onSubmit = vi.fn(async () => true)) {
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
    expect(screen.getByLabelText('Sell amount')).toHaveProperty('value', '')
  })

  it('recalculates the displayed MYR rate when the received amount is edited', () => {
    renderTrade()
    selectPair('usdt', 'myr')
    expect(screen.getByText('1 USDT =')).toBeTruthy()
    expect(screen.getByText('MYR', { selector: '.rate-equation > span:last-child' })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Sell amount'), { target: { value: '100' } })
    fireEvent.change(screen.getByLabelText('Exchange rate'), { target: { value: '4.25' } })
    expect(screen.getByLabelText('Receive amount')).toHaveProperty('value', '425')

    fireEvent.change(screen.getByLabelText('Receive amount'), { target: { value: '424' } })
    expect(screen.getByLabelText('Exchange rate')).toHaveProperty('value', '4.24')
    expect(screen.getByLabelText('Gross transaction value (MYR)')).toHaveProperty('value', '424')
  })

  it('displays non-USDT per USDT when selling USDT and submits the canonical inverse rate', async () => {
    const onSubmit = renderTrade()
    selectPair('usdt', 'eth')
    fireEvent.change(screen.getByLabelText('Exchange account'), { target: { value: 'wallet' } })
    fireEvent.change(screen.getByLabelText('Gain/loss account'), { target: { value: 'gain' } })
    fireEvent.change(screen.getByLabelText('Sell amount'), { target: { value: '100' } })
    fireEvent.change(screen.getByLabelText('Exchange rate'), { target: { value: '2000' } })

    expect(screen.getByText('1 ETH =')).toBeTruthy()
    expect(screen.getByText('USDT', { selector: '.rate-equation > span:last-child' })).toBeTruthy()
    expect(screen.getByLabelText('Receive amount')).toHaveProperty('value', '0.05')
    expect(screen.getByRole('status').textContent).toContain('100 USDT ÷ 2000 = 0.05 ETH net')

    fireEvent.change(screen.getByLabelText('Receive amount'), { target: { value: '0.04' } })
    expect(screen.getByLabelText('Exchange rate')).toHaveProperty('value', '2500')
    fireEvent.change(screen.getByLabelText('Gross transaction value (MYR)'), { target: { value: '100' } })
    fireEvent.click(screen.getByRole('button', { name: 'Post trade' }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      sell_asset_id: 'usdt',
      sell_quantity: '100',
      buy_asset_id: 'eth',
      buy_quantity: '0.04',
      execution_rate: '0.0004',
      gross_value_myr: '100',
    })))
  })

  it('displays non-USDT per USDT when buying USDT and submits the canonical rate', async () => {
    const onSubmit = renderTrade()
    selectPair('eth', 'usdt')
    fireEvent.change(screen.getByLabelText('Exchange account'), { target: { value: 'wallet' } })
    fireEvent.change(screen.getByLabelText('Gain/loss account'), { target: { value: 'gain' } })
    fireEvent.change(screen.getByLabelText('Sell amount'), { target: { value: '0.05' } })
    fireEvent.change(screen.getByLabelText('Exchange rate'), { target: { value: '2000' } })

    expect(screen.getByText('1 ETH =')).toBeTruthy()
    expect(screen.getByText('USDT', { selector: '.rate-equation > span:last-child' })).toBeTruthy()
    expect(screen.getByLabelText('Receive amount')).toHaveProperty('value', '100')
    expect(screen.getByRole('status').textContent).toContain('0.05 ETH × 2000 = 100 USDT net')

    fireEvent.change(screen.getByLabelText('Receive amount'), { target: { value: '120' } })
    expect(screen.getByLabelText('Exchange rate')).toHaveProperty('value', '2400')
    fireEvent.change(screen.getByLabelText('Gross transaction value (MYR)'), { target: { value: '1200' } })
    fireEvent.click(screen.getByRole('button', { name: 'Post trade' }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      sell_asset_id: 'eth',
      sell_quantity: '0.05',
      buy_asset_id: 'usdt',
      buy_quantity: '120',
      execution_rate: '2400',
      gross_value_myr: '1200',
    })))
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

  it('subtracts an included buy fee with the normalized sell-USDT rate', () => {
    renderTrade()
    selectPair('usdt', 'eth')
    fireEvent.change(screen.getByLabelText('Sell amount'), { target: { value: '100' } })
    fireEvent.change(screen.getByLabelText('Exchange rate'), { target: { value: '2000' } })
    fireEvent.change(screen.getByLabelText('Fee asset'), { target: { value: 'eth' } })
    fireEvent.change(screen.getByLabelText('Fee quantity'), { target: { value: '0.001' } })
    fireEvent.click(screen.getByLabelText('Fee is already included in the funding/net amount'))

    expect(screen.getByLabelText('Receive amount')).toHaveProperty('value', '0.049')
    expect(screen.getByRole('status').textContent).toContain('100 USDT ÷ 2000 = 0.049 ETH net')
  })

  it('keeps sell-to-buy direction for pairs without USDT or MYR', () => {
    renderTrade()
    selectPair('eth', 'btc')
    fireEvent.change(screen.getByLabelText('Sell amount'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('Exchange rate'), { target: { value: '0.5' } })

    expect(screen.getByText('1 ETH =')).toBeTruthy()
    expect(screen.getByText('BTC', { selector: '.rate-equation > span:last-child' })).toBeTruthy()
    expect(screen.getByLabelText('Receive amount')).toHaveProperty('value', '1')
    expect(screen.getByRole('status').textContent).toContain('2 ETH × 0.5 = 1 BTC net')
  })

  it('keeps all trade inputs when posting fails', async () => {
    const onSubmit = renderTrade(vi.fn(async () => false))
    selectPair('myr', 'usdt')
    fireEvent.change(screen.getByLabelText('Exchange account'), { target: { value: 'wallet' } })
    fireEvent.change(screen.getByLabelText('Gain/loss account'), { target: { value: 'gain' } })
    fireEvent.change(screen.getByLabelText('Sell amount'), { target: { value: '2800' } })
    fireEvent.change(screen.getByLabelText('Exchange rate'), { target: { value: '4.05797' } })

    fireEvent.click(screen.getByRole('button', { name: 'Post trade' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))

    expect(screen.getByLabelText('Sell asset')).toHaveProperty('value', 'myr')
    expect(screen.getByLabelText('Buy asset')).toHaveProperty('value', 'usdt')
    expect(screen.getByLabelText('Sell amount')).toHaveProperty('value', '2800')
    expect(screen.getByLabelText('Exchange rate')).toHaveProperty('value', '4.05797')
    expect(screen.getByLabelText('Receive amount')).toHaveProperty('value', '690.000172500043125011')
  })
})
