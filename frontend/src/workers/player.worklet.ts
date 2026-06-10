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
  private queue: Int16Array[] = []
  private current: Float32Array | null = null
  private offset = 0

  constructor(options?: AudioWorkletNodeOptions) {
    super(options)
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

  process(_inputs: Float32Array[][], outputs: Float32Array[][]) {
    const out = outputs[0]?.[0]
    if (!out) return true
    for (let i = 0; i < out.length; i++) {
      if (!this.current || this.offset >= this.current.length) {
        if (this.queue.length === 0) {
          out[i] = 0
          continue
        }
        const pcm = this.queue.shift()!
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
