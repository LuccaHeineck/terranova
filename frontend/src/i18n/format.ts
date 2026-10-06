import { getLocale } from './store'

// Numbers in the UI language: "1,234.5" in English, "1.234,5" in Portuguese.

/** A fixed number of decimals, in the UI language's separators. Float noise around zero prints as 0, not "-0.0". */
export function num(value: number, digits = 0): string {
  const shown = Math.abs(value) < 0.5 * 10 ** -digits ? 0 : value
  return shown.toLocaleString(getLocale(), { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/** Up to `maxDigits` decimals, trailing zeros dropped. */
export function upTo(value: number, maxDigits: number): string {
  return value.toLocaleString(getLocale(), { maximumFractionDigits: maxDigits })
}

/** A whole number with thousands separators. */
export function int(value: number): string {
  return Math.round(value).toLocaleString(getLocale())
}

/** Scientific notation ("-2.3e-13"), with a decimal comma in Portuguese. */
export function exp(value: number, digits = 1): string {
  const text = value.toExponential(digits)
  return getLocale() === 'pt-BR' ? text.replace('.', ',') : text
}
