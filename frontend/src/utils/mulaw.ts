const BIAS = 0x84

const DECODE_TABLE = new Int16Array(256)
for (let i = 0; i < 256; i++) {
  const sign = i & 0x80 ? -1 : 1
  const exponent = (i >> 4) & 0x07
  const mantissa = i & 0x0f
  const sample = ((mantissa << 3) + BIAS) << exponent
  DECODE_TABLE[i] = sign * (sample - BIAS)
}

export function decodeMulawToPcm16(input: Uint8Array): Int16Array {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    out[i] = DECODE_TABLE[input[i]]
  }
  return out
}
