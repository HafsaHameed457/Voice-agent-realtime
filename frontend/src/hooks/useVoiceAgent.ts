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

  const recorder = useAudioRecorder()
  const player = useAudioPlayer()

  recorder.onChunk((pcmBuffer) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return
    const arr = new Int16Array(pcmBuffer)
    const b64 = int16ToBase64(arr)
    wsRef.current.send(JSON.stringify({ type: 'audio', audio: b64 }))
  })

  const addMessage = useCallback((role: 'user' | 'assistant', text: string) => {
    setMessages((prev) => [...prev, { role, text, timestamp: Date.now() }])
  }, [])

  const connect = useCallback(async () => {
    isCallActive.current = true
    retryCount.current = 0
    setStatus('connecting')
    setMessages([])

    try {
      console.log('[VoiceAgent] Starting audio (user gesture)...')
      await player.init()
      await recorder.start()
      console.log('[VoiceAgent] Audio started, connecting WebSocket...')
    } catch (err) {
      console.error('[VoiceAgent] Failed to start audio:', err)
      addMessage('assistant', `[Error] Microphone access denied: ${err}`)
      disconnect()
      return
    }

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host
    const url = `${proto}//${host}/browser-stream?session_id=${sessionIdRef.current}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('[VoiceAgent] WebSocket connected')
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      switch (data.type) {
        case 'session.ready':
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
  }, [addMessage, player, recorder])

  const scheduleReconnect = useCallback(() => {
    const delay = Math.min(1000 * 2 ** retryCount.current, 30000)
    retryCount.current++
    setStatus('connecting')
    reconnectTimer.current = setTimeout(() => connect(), delay)
  }, [connect])

  const disconnect = useCallback(() => {
    isCallActive.current = false
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }
    recorder.stop()
    player.stop()
    wsRef.current?.close()
    wsRef.current = null
    setStatus('disconnected')
    setIsSpeaking(false)
  }, [recorder, player])

  useEffect(() => () => disconnect(), [disconnect])

  return { status, messages, isSpeaking, connect, disconnect }
}
