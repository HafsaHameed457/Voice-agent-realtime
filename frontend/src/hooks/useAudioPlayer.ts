import { useRef, useCallback } from 'react'
import { base64ToUint8Array } from '../utils/base64'

export function useAudioPlayer() {
  const ctxRef = useRef<AudioContext | null>(null)
  const nodeRef = useRef<AudioWorkletNode | null>(null)

  const init = useCallback(async () => {
    if (ctxRef.current) return
    const ctx = new AudioContext()
    ctxRef.current = ctx

    await ctx.audioWorklet.addModule(
      new URL('../workers/player.worklet.ts', import.meta.url),
    )

    const node = new AudioWorkletNode(ctx, 'pcm-player')
    node.connect(ctx.destination)
    nodeRef.current = node
  }, [])

  const play = useCallback((mulawB64: string) => {
    const node = nodeRef.current
    if (!node) return
    const bytes = base64ToUint8Array(mulawB64)
    node.port.postMessage({ type: 'audio', data: bytes.buffer }, [bytes.buffer])
  }, [])

  const clearQueue = useCallback(() => {
    nodeRef.current?.port.postMessage({ type: 'clear' })
  }, [])

  const stop = useCallback(() => {
    clearQueue()
    nodeRef.current?.disconnect()
    nodeRef.current = null
    ctxRef.current?.close()
    ctxRef.current = null
  }, [clearQueue])

  return { init, play, clearQueue, stop }
}
