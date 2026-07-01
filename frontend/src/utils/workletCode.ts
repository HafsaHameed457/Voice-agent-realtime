export const RECORDER_WORKLET = `
class RecorderProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super(options)
    this.targetRate = 24000
    this.fromRate = options?.processorOptions?.sampleRate ?? 48000
  }

  process(inputs) {
    const raw = inputs[0]?.[0]
    if (!raw) return true
    const sliced = this.fromRate === this.targetRate
      ? raw
      : this.resample(raw, this.fromRate, this.targetRate)
    const pcm16 = new Int16Array(sliced.length)
    for (let i = 0; i < sliced.length; i++) {
      const s = Math.max(-1, Math.min(1, sliced[i]))
      pcm16[i] = s < 0 ? s * 32768 : s * 32767
    }
    this.port.postMessage({ type: 'audio', data: pcm16.buffer }, [pcm16.buffer])
    return true
  }

  resample(input, from, to) {
    const ratio = from / to
    const outLen = Math.round(input.length / ratio)
    const out = new Float32Array(outLen)
    for (let i = 0; i < outLen; i++) {
      const pos = i * ratio
      const idx = Math.floor(pos)
      const frac = pos - idx
      out[i] = idx + 1 < input.length
        ? input[idx] + frac * (input[idx + 1] - input[idx])
        : input[idx]
    }
    return out
  }
}

registerProcessor('pcm-recorder', RecorderProcessor)
`

export const PLAYER_WORKLET = `
const BIAS = 0x84
const DECODE_TABLE = new Int16Array(256)
for (let i = 0; i < 256; i++) {
  const sign = i & 0x80 ? -1 : 1
  const exponent = (i >> 4) & 0x07
  const mantissa = i & 0x0f
  const sample = ((mantissa << 3) + BIAS) << exponent
  DECODE_TABLE[i] = sign * (sample - BIAS)
}

class PlayerProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super(options)
    this.queue = []
    this.current = null
    this.offset = 0
    this.port.onmessage = (e) => {
      if (e.data.type === 'audio') {
        const mulaw = new Uint8Array(e.data.data)
        const pcm = new Int16Array(mulaw.length)
        for (let i = 0; i < mulaw.length; i++) pcm[i] = DECODE_TABLE[mulaw[i]]
        this.queue.push(pcm)
      } else if (e.data.type === 'clear') {
        this.queue = []
        this.current = null
        this.offset = 0
      }
    }
  }

  process(_inputs, outputs) {
    const out = outputs[0]?.[0]
    if (!out) return true
    for (let i = 0; i < out.length; i++) {
      if (!this.current || this.offset >= this.current.length) {
        if (this.queue.length === 0) {
          out[i] = 0
          continue
        }
        const pcm = this.queue.shift()
        this.current = new Float32Array(pcm.length)
        for (let j = 0; j < pcm.length; j++) this.current[j] = pcm[j] / 32768
        this.offset = 0
      }
      out[i] = this.current[this.offset++]
    }
    return true
  }
}

registerProcessor('pcm-player', PlayerProcessor)
`
