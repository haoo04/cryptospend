type DecimalParts = {
  coefficient: bigint
  scale: number
}

const decimalPattern = /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))$/

function powerOfTen(exponent: number) {
  if (!Number.isInteger(exponent) || exponent < 0) throw new Error('Invalid decimal scale')
  return 10n ** BigInt(exponent)
}

function parseDecimal(value: string): DecimalParts {
  const match = decimalPattern.exec(value.trim())
  if (!match) throw new Error('Enter a valid decimal value')

  const fraction = match[3] ?? match[4] ?? ''
  const whole = match[2] ?? '0'
  const sign = match[1] === '-' ? -1n : 1n
  return {
    coefficient: sign * BigInt(`${whole}${fraction}`),
    scale: fraction.length,
  }
}

function roundCoefficient(coefficient: bigint, currentScale: number, targetScale: number) {
  if (targetScale >= currentScale) return coefficient * powerOfTen(targetScale - currentScale)

  const divisor = powerOfTen(currentScale - targetScale)
  const negative = coefficient < 0n
  const absolute = negative ? -coefficient : coefficient
  let quotient = absolute / divisor
  const remainder = absolute % divisor
  const doubled = remainder * 2n
  if (doubled > divisor || (doubled === divisor && quotient % 2n !== 0n)) quotient += 1n
  return negative ? -quotient : quotient
}

function renderDecimal({ coefficient, scale }: DecimalParts) {
  if (coefficient === 0n) return '0'

  const negative = coefficient < 0n
  const digits = (negative ? -coefficient : coefficient).toString().padStart(scale + 1, '0')
  const whole = scale ? digits.slice(0, -scale) : digits
  const fraction = scale ? digits.slice(-scale).replace(/0+$/, '') : ''
  return `${negative ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}`
}

export function addDecimal(left: string, right: string) {
  const first = parseDecimal(left)
  const second = parseDecimal(right)
  const scale = Math.max(first.scale, second.scale)
  return renderDecimal({
    coefficient:
      first.coefficient * powerOfTen(scale - first.scale)
      + second.coefficient * powerOfTen(scale - second.scale),
    scale,
  })
}

export function subtractDecimal(left: string, right: string) {
  const second = parseDecimal(right)
  return addDecimal(left, renderDecimal({ coefficient: -second.coefficient, scale: second.scale }))
}

export function multiplyDecimal(left: string, right: string, scale: number) {
  const first = parseDecimal(left)
  const second = parseDecimal(right)
  const coefficient = roundCoefficient(
    first.coefficient * second.coefficient,
    first.scale + second.scale,
    scale,
  )
  return renderDecimal({ coefficient, scale })
}

export function divideDecimal(left: string, right: string, scale: number) {
  const first = parseDecimal(left)
  const second = parseDecimal(right)
  if (second.coefficient === 0n) throw new Error('Rate must be greater than zero')

  const negative = (first.coefficient < 0n) !== (second.coefficient < 0n)
  const numerator = (first.coefficient < 0n ? -first.coefficient : first.coefficient)
    * powerOfTen(scale + second.scale)
  const denominator = (second.coefficient < 0n ? -second.coefficient : second.coefficient)
    * powerOfTen(first.scale)
  let quotient = numerator / denominator
  const remainder = numerator % denominator
  const doubled = remainder * 2n
  if (doubled > denominator || (doubled === denominator && quotient % 2n !== 0n)) quotient += 1n
  return renderDecimal({ coefficient: negative ? -quotient : quotient, scale })
}

export function isPositiveDecimal(value: string) {
  try {
    return parseDecimal(value).coefficient > 0n
  } catch {
    return false
  }
}
