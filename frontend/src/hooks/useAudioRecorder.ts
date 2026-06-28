import { useCallback, useEffect, useMemo, useRef } from 'react'

let sharedCtx: AudioContext | null = null
let recorderModuleLoaded = false

function getAudioContext() {
  if (!sharedCtx || sharedCtx.state === 'closed') {
    sharedCtx = new AudioContext({ sampleRate: 24000 })
  }
  return sharedCtx
}

export function useAudioRecorder() {
  const analyserRef = useRef<AnalyserNode | null>(null)
  const nodeRef = useRef<AudioWorkletNode | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const onChunkRef = useRef<((pcmBuffer: ArrayBufferLike) => void) | null>(null)

  useEffect(() => {
    const ctx = getAudioContext()
    if (!recorderModuleLoaded) {
      ctx.audioWorklet.addModule(
        new URL('../workers/recorder.worklet.ts', import.meta.url),
      ).then(() => {
        recorderModuleLoaded = true
      }).catch(() => {})
    }
  }, [])

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
    analyserRef.current = analyser
  }, [])

  const stop = useCallback(() => {
    nodeRef.current?.disconnect()
    nodeRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    analyserRef.current = null
  }, [])

  useEffect(() => () => stop(), [stop])

  return useMemo(() => ({ start, stop, onChunk }), [start, stop, onChunk])
}
