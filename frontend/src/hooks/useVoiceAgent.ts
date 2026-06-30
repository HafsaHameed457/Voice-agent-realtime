import { useCallback, useEffect, useRef, useState } from 'react'
import type { ConnectionStatus, TranscriptMessage } from '../types'
import { useAudioRecorder } from './useAudioRecorder'
import { useAudioPlayer } from './useAudioPlayer'
import { int16ToBase64 } from '../utils/base64'

interface VoiceAgentConfig {
  vadThreshold: number
  silenceTimeout: number
}

const DEFAULT_CONFIG: VoiceAgentConfig = {
  vadThreshold: 500,
  silenceTimeout: 1000,
}

function generateSessionId(): string {
  return `browser_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
}

export function useVoiceAgent(config: Partial<VoiceAgentConfig> = {}) {
  const cfg = { ...DEFAULT_CONFIG, ...config }
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [messages, setMessages] = useState<TranscriptMessage[]>([])
  const [isSpeaking, setIsSpeaking] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const sessionIdRef = useRef<string>(generateSessionId())
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(null)
  const retryCount = useRef(0)
  const isCallActive = useRef(false)
  const isConnecting = useRef(false)
  const doConnectRef = useRef<(() => Promise<void>) | null>(null)
  const pendingAudioRef = useRef<string[]>([])

  const recorder = useAudioRecorder()
  const player = useAudioPlayer()
  const localAudioRef = useRef<Int16Array[]>([])
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout>>(null)

  const sendAudioBlob = useCallback(() => {
    const chunks = localAudioRef.current
    localAudioRef.current = []
    if (chunks.length === 0) return

    const totalLen = chunks.reduce((acc, a) => acc + a.length, 0)
    const combined = new Int16Array(totalLen)
    let offset = 0
    for (const chunk of chunks) {
      combined.set(chunk, offset)
      offset += chunk.length
    }
    const b64 = int16ToBase64(combined)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'audio', audio: b64 }))
    } else {
      pendingAudioRef.current.push(b64)
    }
  }, [])

  useEffect(() => {
    recorder.onChunk((pcmBuffer) => {
      const arr = new Int16Array(pcmBuffer)
      let sum = 0
      for (let i = 0; i < arr.length; i++) {
        sum += Math.abs(arr[i])
      }
      if (sum / arr.length < cfg.vadThreshold) return

      localAudioRef.current.push(arr)

      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current)
      }
      silenceTimerRef.current = setTimeout(sendAudioBlob, cfg.silenceTimeout)
    })

    return () => {
      recorder.onChunk(() => {})
    }
  }, [cfg.vadThreshold, cfg.silenceTimeout, recorder, sendAudioBlob])

  const addMessage = useCallback((role: 'user' | 'assistant', text: string) => {
    setMessages((prev) => [...prev, { role, text, timestamp: Date.now() }])
  }, [])

  const cleanup = useCallback(() => {
    isCallActive.current = false
    isConnecting.current = false
    retryCount.current = 0
    pendingAudioRef.current = []
    localAudioRef.current = []
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
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

  useEffect(() => {
    doConnectRef.current = async () => {
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

  useEffect(() => {
    return () => cleanup()
  }, [cleanup])

  return { status, messages, isSpeaking, connect, disconnect }
}