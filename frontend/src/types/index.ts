export type MessageRole = 'user' | 'assistant'

export interface TranscriptMessage {
  role: MessageRole
  text: string
  timestamp: number
}

export type ConnectionStatus =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'error'
