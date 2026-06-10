class RecorderProcessor extends AudioWorkletProcessor {
  private readonly targetRate = 24000
  private readonly fromRate: number

  constructor(options?: AudioWorkletNodeOptions) {
    super(options)
    this.fromRate = options?.processorOptions?.sampleRate ?? 48000
  }

  process(inputs: Float32Array[][]) {
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

  private resample(input: Float32Array, from: number, to: number): Float32Array {
    const ratio = from / to
    const outLen = Math.round(input.length / ratio)
    const out = new Float32Array(outLen)
    for (let i = 0; i < outLen; i++) {
      const pos = i * ratio
      const idx = Math.floor(pos)
      const frac = pos - idx
      out[i] =
        idx + 1 < input.length
          ? input[idx] + frac * (input[idx + 1] - input[idx])
          : input[idx]
    }
    return out
  }
}

registerProcessor('pcm-recorder', RecorderProcessor)
