import { describe, expect, it } from 'vitest'

import { addDecimal, divideDecimal, isPositiveDecimal, multiplyDecimal, subtractDecimal } from './decimal'

describe('exact decimal string arithmetic', () => {
  it('calculates the documented MYR to USDT example without binary floating point', () => {
    expect(divideDecimal('2800', '4.05797', 18)).toBe('690.000172500043125011')
    expect(divideDecimal('690.000172500043125011', '2800', 30)).toBe(
      '0.246428633035729687503928571429',
    )
  })

  it('multiplies, adds, and subtracts decimal strings', () => {
    expect(multiplyDecimal('0.25', '17000', 6)).toBe('4250')
    expect(addDecimal('4241.50', '8.50')).toBe('4250')
    expect(subtractDecimal('4250', '8.5')).toBe('4241.5')
  })

  it('uses half-even rounding', () => {
    expect(divideDecimal('1', '8', 2)).toBe('0.12')
    expect(divideDecimal('3', '8', 2)).toBe('0.38')
  })

  it('recognizes only positive decimal values', () => {
    expect(isPositiveDecimal('.5')).toBe(true)
    expect(isPositiveDecimal('0')).toBe(false)
    expect(isPositiveDecimal('-1')).toBe(false)
    expect(isPositiveDecimal('not-a-number')).toBe(false)
  })
})
