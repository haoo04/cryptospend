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
  channel_type: string
  provider: string | null
  closed: boolean
  balances: Balance[]
  available_balances: Balance[]
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

export type FeeComponent = {
  id: string
  component_type: string
  asset_id: string
  asset_symbol: string
  amount: string
  value_myr: string
  source_kind: string
  included_in_funding_amount: boolean
  accounting_treatment: string
  calculation_method: string | null
  confidence: string
}

export type Category = {
  id: string
  name: string
  kind: 'INCOME' | 'EXPENSE'
  active: boolean
  created_at: string
  updated_at: string
}

export type ReceiptMetadata = {
  id: string
  original_filename: string
  content_type: string
  byte_size: number
  created_at: string
  updated_at: string
}

export type TransactionEvent = {
  id: string
  event_type: string
  status: string
  occurred_at: string
  time_precision: string
  description: string
  category: string | null
  category_id: string | null
  category_kind: 'INCOME' | 'EXPENSE' | null
  source: string
  external_id: string | null
  transaction_value_myr: string | null
  reference_value_myr: string | null
  reverses_event_id: string | null
  reversed_by_event_id: string | null
  posted_at: string | null
  entries: LedgerEntry[]
  fees: FeeComponent[]
  receipt: ReceiptMetadata | null
}

export type EventSearchFilters = {
  q?: string
  event_type?: string
  status?: string
  category_id?: string
  from_date?: string
  to_date?: string
  page?: number
  page_size?: number
}

export type EventSearchPage = {
  items: TransactionEvent[]
  total: number
  page: number
  page_size: number
}

export type Summary = {
  net_worth_myr: string
  income_myr: string
  expense_myr: string
  gross_spending_myr: string
  net_spending_myr: string
}

export type PortfolioPosition = {
  asset_id: string
  symbol: string
  quantity: string
  cost_basis_myr: string
  average_cost_myr: string | null
  market_rate_myr: string | null
  market_rate_source: string | null
  market_rate_observed_at: string | null
  market_rate_confidence: string | null
  market_value_myr: string | null
  unrealized_gain_loss_myr: string | null
  realized_gain_loss_myr: string
  basis_complete: boolean
}

export type FeeReport = {
  total_myr: string
  components: { component_type: string; value_myr: string }[]
}

export type Reward = {
  id: string
  asset_id: string
  amount: string
  status: string
  value_myr: string | null
}

export type CardRecord = {
  id: string
  event_id: string | null
  parent_card_transaction_id: string | null
  original_transaction_id: string | null
  provider: string
  external_id: string | null
  transaction_type: 'AUTHORIZATION' | 'PURCHASE' | 'REFUND'
  merchant_name: string
  merchant_amount: string
  merchant_asset_id: string
  billing_amount: string
  billing_asset_id: string
  merchant_value_myr: string
  status: string
  authorized_at: string | null
  settled_at: string | null
  hold: { account_id: string; asset_id: string; amount: string; value_myr: string; status: string } | null
  rewards: Reward[]
}

export type CardCost = {
  id: string
  provider: string
  merchant_name: string
  merchant_amount: string
  merchant_value_myr: string
  billing_amount: string
  funding_value_myr: string
  separate_fee_value_myr: string
  gross_economic_cost_myr: string
  refunded_value_myr: string
  credited_cashback_value_myr: string
  net_economic_cost_myr: string
  total_leakage_myr: string
  fx_deviation_myr: string | null
  conversion_deviation_myr: string | null
  residual_myr: string | null
  breakdown_confidence: string
  status: string
  settled_at: string
  funding_legs: { asset_id: string; asset_symbol: string; quantity: string; reference_value_myr: string }[]
  fees: { component_type: string; value_myr: string; included_in_funding_amount: boolean }[]
}

export type SpendingChannel = {
  channel_type: string
  gross_spending_myr: string
  refunds_myr: string
  cashback_myr: string
  net_spending_myr: string
  source: string
  calculation_method: string
  confidence: string
}

export type FeeLeakage = {
  explicit_myr: string
  derived_myr: string
  total_leakage_myr: string
  components: {
    component_type: string
    value_myr: string
    source_kind: string
    source: string
    calculation_method: string
    confidence: string
  }[]
}

export type MonthlyReport = {
  month: string
  timezone: string
  period_start: string
  period_end: string
  summary: Summary
  fees: FeeReport
  fee_leakage: FeeLeakage
  channels: SpendingChannel[]
  portfolio: PortfolioPosition[]
}

export type JourneyAllocation = {
  id: string
  event_id: string
  event_type: string
  event_description: string
  occurred_at: string
  relation_type: string
  sequence: number
  asset_id: string
  asset_symbol: string
  allocation_role: string
  quantity: string
  value_myr: string
  source: string
  confidence: string
  active_at_query: boolean
}

export type JourneyReport = {
  id: string
  name: string
  journey_type: string
  status: string
  allocation_method: string
  notes: string
  gross_input_myr: string
  net_output_myr: string
  explicit_cost_myr: string
  derived_deviation_myr: string
  total_path_cost_myr: string
  calculation_method: string
  source: string
  confidence: string
  as_of: string | null
  allocations: JourneyAllocation[]
}

export type ReportSnapshot = {
  id: string
  snapshot_type: string
  period_key: string
  period_start: string
  as_of: string
  timezone: string
  checksum: string
  created_at: string
}

export type ChannelComparison = {
  fixed_conditions: {
    amount_myr: string
    compared_at: string
    reference_rate: string
    reference_source: string
    cashback_eligible: boolean
  }
  paths: {
    name: string
    path_type: string
    mode: string
    explicit_cost_myr: string
    derived_deviation_myr: string
    cashback_myr: string
    effective_cost_myr: string
    net_value_myr: string
    cost_rate_percent: string
    source: string
    confidence: string
    is_lowest_cost: boolean
  }[]
  note: string
}

export type AnalyticsCategory = {
  category_id: string | null
  name: string
  amount_myr: string
}

export type AnalyticsReport = {
  period: 'day' | 'week' | 'month' | 'year' | 'all'
  anchor: string | null
  timezone: string
  period_start: string | null
  period_end: string | null
  bucket_unit: 'hour' | 'day' | 'month' | 'year'
  summary: {
    income_myr: string
    expense_myr: string
    net_income_myr: string
  }
  timeline: {
    bucket_start: string
    label: string
    income_myr: string
    expense_myr: string
  }[]
  expense_categories: AnalyticsCategory[]
  income_categories: AnalyticsCategory[]
}

export type RecurringFrequency = 'WEEKLY' | 'MONTHLY' | 'YEARLY'

export type RecurringExpense = {
  id: string
  name: string
  amount_myr: string
  frequency: RecurringFrequency
  anchor_on: string
  next_due_on: string
  due_status: 'PAUSED' | 'OVERDUE' | 'DUE_TODAY' | 'UPCOMING'
  annualized_amount_myr: string
  asset_id: string
  funding_account_id: string
  expense_account_id: string
  category_id: string
  active: boolean
  created_at: string
  updated_at: string
}

export type RecurringExpenseSummary = {
  active_count: number
  overdue_count: number
  weekly_total_myr: string
  monthly_total_myr: string
  yearly_total_myr: string
  annualized_myr: string
}

export type RecurringExpenseList = {
  as_of: string
  timezone: string
  summary: RecurringExpenseSummary
  items: RecurringExpense[]
}

export type RecurringExpenseOccurrence = {
  id: string
  recurring_expense_id: string
  due_on: string
  action: 'RECORDED' | 'SKIPPED'
  scheduled_amount_myr: string
  event_id: string | null
  event_status: string | null
  occurred_at: string | null
  skip_reason: string | null
  handled_at: string
}

export type RecurringExpenseAction = {
  occurrence: RecurringExpenseOccurrence
  recurring_expense: RecurringExpense
}

export type GoogleDriveBackupStatus = {
  configured: boolean
  supported: boolean
  connected: boolean
  folder_name: string
  message: string | null
}

export type GoogleDriveBackupResult = {
  id: string
  name: string
  web_view_link: string | null
  created_at: string
}

const apiRoot = import.meta.env.VITE_API_URL ?? '/api'

export function formatApiError(body: unknown, status: number) {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail)) {
      const messages = detail.slice(0, 3).flatMap((item) => {
        if (!item || typeof item !== 'object') return []
        const issue = item as { loc?: unknown; msg?: unknown }
        if (typeof issue.msg !== 'string') return []
        const location = Array.isArray(issue.loc)
          ? issue.loc
            .filter((part) => part !== 'body' && (typeof part === 'string' || typeof part === 'number'))
            .join('.')
          : ''
        return [`${location || 'Request'}: ${issue.msg}`]
      })
      if (messages.length) return `${messages.join('; ')}${detail.length > 3 ? '; …' : ''}`
    }
  }
  return `Request failed (${status})`
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = typeof FormData !== 'undefined' && options?.body instanceof FormData
  const headers = new Headers(options?.headers)
  if (!isFormData && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let response: Response
  try {
    response = await fetch(`${apiRoot}${path}`, {
      ...options,
      headers,
    })
  } catch (reason) {
    throw new Error('Unable to reach CryptoSpend. Check that the server is running and try again.', {
      cause: reason,
    })
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as unknown
    const error = new Error(formatApiError(body, response.status)) as Error & { status?: number }
    error.status = response.status
    throw error
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  assets: () => request<Asset[]>('/assets'),
  accounts: () => request<Account[]>('/accounts'),
  categories: (includeInactive = false) =>
    request<Category[]>(`/categories${includeInactive ? '?include_inactive=true' : ''}`),
  recurringExpenses: (includeInactive = false) =>
    request<RecurringExpenseList>(`/recurring-expenses${includeInactive ? '?include_inactive=true' : ''}`),
  events: () => request<TransactionEvent[]>('/events'),
  searchEvents: (filters: EventSearchFilters = {}) => {
    const query = new URLSearchParams()
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== '') query.set(key, String(value))
    })
    const suffix = query.toString()
    return request<EventSearchPage>(`/events/search${suffix ? `?${suffix}` : ''}`)
  },
  summary: () => request<Summary>('/reports/summary'),
  portfolio: (asOf?: string) =>
    request<PortfolioPosition[]>(`/reports/portfolio${asOf ? `?as_of=${encodeURIComponent(asOf)}` : ''}`),
  fees: () => request<FeeReport>('/reports/fees'),
  cards: () => request<CardRecord[]>('/cards'),
  cardCosts: () => request<CardCost[]>('/reports/card-costs'),
  monthly: (month: string) => request<MonthlyReport>(`/reports/monthly?month=${encodeURIComponent(month)}`),
  analytics: (period: AnalyticsReport['period'], anchor?: string) => {
    const query = new URLSearchParams({ period })
    if (anchor) query.set('anchor', anchor)
    return request<AnalyticsReport>(`/reports/analytics?${query.toString()}`)
  },
  snapshots: () => request<ReportSnapshot[]>('/reports/monthly-snapshots'),
  journeys: () => request<JourneyReport[]>('/journeys'),
  googleDriveBackupStatus: () => request<GoogleDriveBackupStatus>('/backups/google-drive/status'),
  googleDriveConnectUrl: () => `${apiRoot}/backups/google-drive/connect`,
  uploadGoogleDriveBackup: () =>
    request<GoogleDriveBackupResult>('/backups/google-drive/upload', { method: 'POST' }),
  onboard: () => request('/onboarding', { method: 'POST', body: '{}' }),
  createAccount: (payload: {
    name: string
    account_type: string
    channel_type?: string
    provider: string | null
  }) =>
    request<Account>('/accounts', { method: 'POST', body: JSON.stringify(payload) }),
  createAsset: (payload: { symbol: string; name: string; decimals: number }) =>
    request<Asset>('/assets', { method: 'POST', body: JSON.stringify(payload) }),
  createCategory: (payload: { name: string; kind: Category['kind'] }) =>
    request<Category>('/categories', { method: 'POST', body: JSON.stringify(payload) }),
  updateCategory: (id: string, payload: { name?: string; active?: boolean }) =>
    request<Category>(`/categories/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  createRecurringExpense: (payload: {
    name: string
    amount_myr: string
    frequency: RecurringFrequency
    first_due_on: string
    asset_id: string
    funding_account_id: string
    expense_account_id: string
    category_id: string
  }) => request<RecurringExpense>('/recurring-expenses', { method: 'POST', body: JSON.stringify(payload) }),
  updateRecurringExpense: (
    id: string,
    payload: {
      name?: string
      amount_myr?: string
      frequency?: RecurringFrequency
      next_due_on?: string
      asset_id?: string
      funding_account_id?: string
      expense_account_id?: string
      category_id?: string
      active?: boolean
    },
  ) => request<RecurringExpense>(`/recurring-expenses/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  recordRecurringExpense: (id: string, payload: { due_on: string; occurred_at: string }) =>
    request<RecurringExpenseAction>(`/recurring-expenses/${id}/record`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  skipRecurringExpense: (id: string, payload: { due_on: string; reason?: string | null }) =>
    request<RecurringExpenseAction>(`/recurring-expenses/${id}/skip`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  recurringExpenseOccurrences: (id: string, limit = 50) =>
    request<RecurringExpenseOccurrence[]>(
      `/recurring-expenses/${id}/occurrences?limit=${encodeURIComponent(String(limit))}`,
    ),
  createManualEvent: (payload: Record<string, unknown>) =>
    request<TransactionEvent>('/events/manual', { method: 'POST', body: JSON.stringify(payload) }),
  createTrade: (payload: Record<string, unknown>) =>
    request<TransactionEvent>('/trades', { method: 'POST', body: JSON.stringify(payload) }),
  createTransfer: (payload: Record<string, unknown>) =>
    request<TransactionEvent>('/transfers', { method: 'POST', body: JSON.stringify(payload) }),
  createRate: (payload: Record<string, unknown>) =>
    request<{ id: string; rate: string }>('/rates', { method: 'POST', body: JSON.stringify(payload) }),
  authorizeCard: (payload: Record<string, unknown>) =>
    request<CardRecord>('/cards/authorizations', { method: 'POST', body: JSON.stringify(payload) }),
  reverseAuthorization: (id: string) =>
    request<CardRecord>(`/cards/${id}/reverse-authorization`, { method: 'POST' }),
  settleCard: (payload: Record<string, unknown>) =>
    request<CardRecord>('/cards/settlements', { method: 'POST', body: JSON.stringify(payload) }),
  refundCard: (id: string, payload: Record<string, unknown>) =>
    request<CardRecord>(`/cards/${id}/refunds`, { method: 'POST', body: JSON.stringify(payload) }),
  createReward: (id: string, payload: Record<string, unknown>) =>
    request<Reward>(`/cards/${id}/rewards`, { method: 'POST', body: JSON.stringify(payload) }),
  creditReward: (id: string, payload: Record<string, unknown>) =>
    request<Reward>(`/rewards/${id}/credit`, { method: 'POST', body: JSON.stringify(payload) }),
  createJourney: (payload: Record<string, unknown>) =>
    request<JourneyReport>('/journeys', { method: 'POST', body: JSON.stringify(payload) }),
  allocateJourneyEvent: (id: string, payload: Record<string, unknown>) =>
    request<JourneyReport>(`/journeys/${id}/events`, { method: 'POST', body: JSON.stringify(payload) }),
  createSnapshot: (month: string) =>
    request<ReportSnapshot & { report: MonthlyReport }>(
      `/reports/monthly-snapshots?month=${encodeURIComponent(month)}`,
      { method: 'POST' },
    ),
  compareChannels: (payload: Record<string, unknown>) =>
    request<ChannelComparison>('/reports/channel-comparison', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  reverseEvent: (id: string, reason: string) =>
    request<TransactionEvent>(`/events/${id}/reverse`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  updateEventCategory: (id: string, category_id: string) =>
    request<TransactionEvent>(`/events/${id}/category`, {
      method: 'PATCH',
      body: JSON.stringify({ category_id }),
    }),
  uploadReceipt: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ReceiptMetadata>(`/events/${id}/receipt`, { method: 'PUT', body: form })
  },
  receiptUrl: (id: string) => `${apiRoot}/events/${id}/receipt`,
  deleteReceipt: (id: string) => request<void>(`/events/${id}/receipt`, { method: 'DELETE' }),
}
