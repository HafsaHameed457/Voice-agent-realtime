import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

let sharedCtx: AudioContext | null = null
let recorderModuleLoaded = false

function getAudioContext() {
  if (!sharedCtx || sharedCtx.state === 'closed') {
    sharedCtx = new AudioContext()
  }
  return sharedCtx
}

export function useAudioRecorder() {
  const [analyserNode, setAnalyserNode] = useState<AnalyserNode | null>(null)
  const nodeRef = useRef<AudioWorkletNode | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const onChunkRef = useRef<((pcmBuffer: ArrayBufferLike) => void) | null>(null)

  const onChunk = useCallback(
    (cb: (pcmBuffer: ArrayBufferLike) => void) => {
      onChunkRef.current = cb
    },
    [],
  )

  const start = useCallback(async () => {
    const ctx = getAudioContext()
    if (ctx.state === 'suspended') {
      await ctx.resume()
    }
    if (!recorderModuleLoaded) {
      await ctx.audioWorklet.addModule(
        new URL('../workers/recorder.worklet.ts', import.meta.url),
      )
      recorderModuleLoaded = true
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: { ideal: 24000 },
        channelCount: { ideal: 1 },
        echoCancellation: { ideal: true },
      },
    })
    streamRef.current = stream

    const source = ctx.createMediaStreamSource(stream)
    const node = new AudioWorkletNode(ctx, 'pcm-recorder', {
      processorOptions: { sampleRate: ctx.sampleRate },
    })
    node.port.onmessage = (e) => {
      if (e.data.type === 'audio') {
        onChunkRef.current?.(e.data.data)
      }
    }
    node.connect(ctx.destination)
    nodeRef.current = node
    source.connect(node)

    const analyser = ctx.createAnalyser()
    analyser.fftSize = 256
    source.connect(analyser)
    setAnalyserNode(analyser)
  }, [])

  const stop = useCallback(() => {
    nodeRef.current?.disconnect()
    nodeRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    setAnalyserNode(null)
  }, [])

  useEffect(() => () => stop(), [stop])

  return useMemo(() => ({ start, stop, onChunk, analyserNode }), [start, stop, onChunk, analyserNode])
}
