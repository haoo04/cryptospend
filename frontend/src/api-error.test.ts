import { describe, expect, it } from 'vitest'

import { formatApiError } from './api'

describe('API error formatting', () => {
  it('uses a string detail from business errors', () => {
    expect(formatApiError({ detail: 'Insufficient USDT balance' }, 422)).toBe(
      'Insufficient USDT balance',
    )
  })

  it('turns FastAPI validation issues into readable field messages', () => {
    expect(formatApiError({
      detail: [
        { loc: ['body', 'sell_quantity'], msg: 'Input should be greater than 0', type: 'greater_than' },
        { loc: ['body', 'fee', 'amount'], msg: 'Input should be a valid decimal', type: 'decimal_parsing' },
      ],
    }, 422)).toBe(
      'sell_quantity: Input should be greater than 0; fee.amount: Input should be a valid decimal',
    )
  })

  it('uses a stable fallback for non-JSON responses', () => {
    expect(formatApiError(null, 500)).toBe('Request failed (500)')
  })
})
