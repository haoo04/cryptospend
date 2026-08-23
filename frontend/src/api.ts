export type Asset = {
  id: string
  symbol: string
  name: string
  decimals: number
  chain: string | null
  contract_address: string | null
  active: boolean
}

export type Balance = {
  asset_id: string
  asset_symbol: string
  quantity: string
  book_amount_myr: string
}

export type Account = {
  id: string
  name: string
  account_type: string
  provider: string | null
  closed: boolean
  balances: Balance[]
}

export type LedgerEntry = {
  id: string
  account_id: string
  account_name: string
  asset_id: string
  asset_symbol: string
  direction: 'DEBIT' | 'CREDIT'
  quantity: string
  book_amount_myr: string
  valuation_rate: string | null
  valuation_source: string | null
}

export type TransactionEvent = {
  id: string
  event_type: string
  status: string
  occurred_at: string
  description: string
  category: string | null
  source: string
  reverses_event_id: string | null
  reversed_by_event_id: string | null
  entries: LedgerEntry[]
}

export type Summary = {
  net_worth_myr: string
  income_myr: string
  expense_myr: string
  gross_spending_myr: string
  net_spending_myr: string
}

const apiRoot = import.meta.env.VITE_API_URL ?? '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiRoot}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  assets: () => request<Asset[]>('/assets'),
  accounts: () => request<Account[]>('/accounts'),
  events: () => request<TransactionEvent[]>('/events'),
  summary: () => request<Summary>('/reports/summary'),
  onboard: () => request('/onboarding', { method: 'POST', body: '{}' }),
  createAccount: (payload: { name: string; account_type: string; provider: string | null }) =>
    request<Account>('/accounts', { method: 'POST', body: JSON.stringify(payload) }),
  createAsset: (payload: { symbol: string; name: string; decimals: number }) =>
    request<Asset>('/assets', { method: 'POST', body: JSON.stringify(payload) }),
  createManualEvent: (payload: Record<string, string | null>) =>
    request<TransactionEvent>('/events/manual', { method: 'POST', body: JSON.stringify(payload) }),
  reverseEvent: (id: string, reason: string) =>
    request<TransactionEvent>(`/events/${id}/reverse`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
}
