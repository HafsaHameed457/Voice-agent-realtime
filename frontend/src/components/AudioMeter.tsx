import { type FC, useEffect, useRef } from 'react'
import { useVoiceAgentContext } from '../context/VoiceAgentContext'

export const AudioMeter: FC = () => {
  const { status } = useVoiceAgentContext()
  const barRef = useRef<HTMLDivElement>(null)
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (status !== 'connected') return

    const audioCtx = new AudioContext()
    if (audioCtx.state === 'suspended') {
      audioCtx.resume()
    }

    let stream: MediaStream

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((s) => {
        stream = s
        const source = audioCtx.createMediaStreamSource(s)
        const analyser = audioCtx.createAnalyser()
        analyser.fftSize = 256
        source.connect(analyser)
        const data = new Uint8Array(analyser.frequencyBinCount)

        const tick = () => {
          analyser.getByteFrequencyData(data)
          const avg = data.reduce((a, b) => a + b, 0) / data.length
          if (barRef.current) {
            barRef.current.style.width = `${Math.min(100, avg * 1.4)}%`
          }
          rafRef.current = requestAnimationFrame(tick)
        }
        tick()
      })
      .catch(() => {})

    return () => {
      cancelAnimationFrame(rafRef.current)
      stream?.getTracks().forEach((t) => t.stop())
      audioCtx.close()
    }
  }, [status])

  return (
    <div className="h-1.5 w-48 overflow-hidden rounded-full bg-zinc-800">
      <div
        ref={barRef}
        className="h-full w-0 rounded-full bg-gradient-to-r from-green-400 to-cyan-400 transition-[width] duration-75"
      />
    </div>
  )
}
