import { useCallback, useMemo, useRef } from 'react'
import { base64ToUint8Array } from '../utils/base64'

let sharedCtx: AudioContext | null = null
let playerModuleLoaded = false

function getAudioContext() {
  if (!sharedCtx || sharedCtx.state === 'closed') {
    sharedCtx = new AudioContext()
  }
  return sharedCtx
}

export function useAudioPlayer() {
  const nodeRef = useRef<AudioWorkletNode | null>(null)

  const init = useCallback(async () => {
    if (nodeRef.current) return
    const ctx = getAudioContext()
    if (ctx.state === 'suspended') {
      await ctx.resume()
    }
    if (!playerModuleLoaded) {
      await ctx.audioWorklet.addModule(
        new URL('../workers/player.worklet.ts', import.meta.url),
      )
      playerModuleLoaded = true
    }
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
  }, [clearQueue])

  return useMemo(() => ({ init, play, clearQueue, stop }), [init, play, clearQueue, stop])
}
