import { createContext, useContext } from 'react'
import type { ConnectionStatus, TranscriptMessage } from '../types'

export interface VoiceAgentContextValue {
  status: ConnectionStatus
  messages: TranscriptMessage[]
  isSpeaking: boolean
  connect: () => void
  disconnect: () => void
}

export const VoiceAgentContext = createContext<VoiceAgentContextValue | null>(null)

export function useVoiceAgentContext(): VoiceAgentContextValue {
  const ctx = useContext(VoiceAgentContext)
  if (!ctx) throw new Error('useVoiceAgentContext must be used within VoiceAgentProvider')
  return ctx
}
