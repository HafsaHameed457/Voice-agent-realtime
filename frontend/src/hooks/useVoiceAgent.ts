import { useCallback, useEffect, useRef, useState } from 'react'
import type { ConnectionStatus, TranscriptMessage } from '../types'
import { useAudioRecorder } from './useAudioRecorder'
import { useAudioPlayer } from './useAudioPlayer'
import { int16ToBase64 } from '../utils/base64'

export function useVoiceAgent() {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [messages, setMessages] = useState<TranscriptMessage[]>([])
  const [isSpeaking, setIsSpeaking] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const sessionIdRef = useRef(`browser_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(null)
  const retryCount = useRef(0)
  const isCallActive = useRef(false)
  const isConnecting = useRef(false)
  const doConnectRef = useRef<(() => Promise<void>) | null>(null)
  const pendingAudioRef = useRef<string[]>([])

  const recorder = useAudioRecorder()
  const player = useAudioPlayer()

  recorder.onChunk((pcmBuffer) => {
    const arr = new Int16Array(pcmBuffer)
    let sum = 0
    for (let i = 0; i < arr.length; i++) {
      sum += Math.abs(arr[i])
    }
    if (sum / arr.length < 500) return
    const b64 = int16ToBase64(arr)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'audio', audio: b64 }))
    } else {
      pendingAudioRef.current.push(b64)
    }
  })

  const addMessage = useCallback((role: 'user' | 'assistant', text: string) => {
    setMessages((prev) => [...prev, { role, text, timestamp: Date.now() }])
  }, [])

  const cleanup = useCallback(() => {
    isCallActive.current = false
    isConnecting.current = false
    retryCount.current = 0
    pendingAudioRef.current = []
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }
    recorder.stop()
    player.stop()
    if (wsRef.current) {
      wsRef.current.onopen = null
      wsRef.current.onmessage = null
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      if (wsRef.current.readyState !== WebSocket.CONNECTING) {
        wsRef.current.close()
      }
      wsRef.current = null
    }
    setStatus('disconnected')
    setIsSpeaking(false)
    setMessages([])
  }, [recorder, player])

  const scheduleReconnect = useCallback(() => {
    if (!isCallActive.current) return
    const delay = Math.min(1000 * 2 ** retryCount.current, 30000)
    retryCount.current++
    setStatus('connecting')
    reconnectTimer.current = setTimeout(() => doConnectRef.current?.(), delay)
  }, [])

  doConnectRef.current = useCallback(async () => {
    if (isConnecting.current) return
    isConnecting.current = true
    if (!isCallActive.current) {
      cleanup()
      return
    }

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host
    const url = `${proto}//${host}/browser-stream?session_id=${sessionIdRef.current}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      for (const b64 of pendingAudioRef.current) {
        ws.send(JSON.stringify({ type: 'audio', audio: b64 }))
      }
      pendingAudioRef.current = []
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      switch (data.type) {
        case 'session.ready':
          isConnecting.current = false
          setStatus('connected')
          break
        case 'transcript':
          addMessage(data.role, data.text)
          if (data.role === 'assistant') {
            setIsSpeaking(false)
          }
          break
        case 'audio.delta':
          if (data.audio) {
            setIsSpeaking(true)
            player.play(data.audio)
          }
          break
        case 'error':
          addMessage('assistant', `[Error] ${data.message ?? 'Unknown error'}`)
          break
      }
    }

    ws.onclose = () => {
      if (isCallActive.current) {
        scheduleReconnect()
      }
    }

    ws.onerror = () => {
      if (isCallActive.current) {
        setStatus('error')
      }
    }

    try {
      await Promise.all([
        player.init(),
        recorder.start(),
      ])
    } catch (err) {
      console.error('[VoiceAgent] Failed to start audio:', err)
      addMessage('assistant', `[Error] Microphone access denied: ${err}`)
      cleanup()
      return
    }

    if (!isCallActive.current) {
      cleanup()
      return
    }
  }, [addMessage, player, recorder, cleanup, scheduleReconnect])

  const connect = useCallback(() => {
    if (isConnecting.current) return
    cleanup()
    isCallActive.current = true
    retryCount.current = 0
    setStatus('connecting')
    setMessages([])
    doConnectRef.current?.()
  }, [cleanup])

  const disconnect = useCallback(() => {
    cleanup()
  }, [cleanup])

  const cleanupRef = useRef(cleanup)
  cleanupRef.current = cleanup
  useEffect(() => () => cleanupRef.current(), [])

  return { status, messages, isSpeaking, connect, disconnect }
}
