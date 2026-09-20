from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext

MYR_MICROS = Decimal("1000000")


def parse_decimal(value: str | int | Decimal) -> Decimal:
    if isinstance(value, float):
        raise ValueError("binary floating-point values are not accepted")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("invalid decimal value") from exc
    if not result.is_finite():
        raise ValueError("decimal value must be finite")
    return result


def canonical_decimal(value: str | int | Decimal) -> str:
    number = parse_decimal(value)
    if number == 0:
        return "0"
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def myr_to_micros(value: str | int | Decimal) -> int:
    return int((parse_decimal(value) * MYR_MICROS).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def micros_to_myr(value: int) -> str:
    return canonical_decimal(Decimal(value) / MYR_MICROS)


def derive_rate_from_micros(quantity: str | int | Decimal, value_myr_micros: int) -> str:
    amount = parse_decimal(quantity)
    if amount <= 0:
        raise ValueError("quantity must be greater than zero")
    if value_myr_micros <= 0:
        raise ValueError("MYR value must be greater than zero")
    with localcontext() as context:
        context.prec = 50
        rate = Decimal(value_myr_micros) / MYR_MICROS / amount
    return canonical_decimal(rate)
