import { type FC } from 'react'
import { useVoiceAgentContext } from '../context/VoiceAgentContext'

export const CallButton: FC = () => {
  const { status, connect, disconnect } = useVoiceAgentContext()
  const isCalling = status !== 'disconnected' && status !== 'error'
  const isLoading = status === 'connecting'

  if (!isCalling) {
    return (
      <button
        onClick={connect}
        className="flex h-28 w-28 flex-col items-center justify-center gap-1 rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-white shadow-xl shadow-blue-500/30 transition-all hover:scale-105 hover:shadow-blue-500/40 active:scale-95"
      >
        <span className="text-3xl">📞</span>
        <span className="text-xs font-semibold">Call Agent</span>
      </button>
    )
  }

  return (
    <button
      onClick={disconnect}
      disabled={isLoading}
      className="flex h-28 w-28 flex-col items-center justify-center gap-1 rounded-full bg-gradient-to-br from-red-500 to-red-700 text-white shadow-xl shadow-red-500/30 transition-all hover:scale-105 hover:shadow-red-500/40 active:scale-95 disabled:opacity-60"
    >
      <span className="text-3xl">{isLoading ? '⏳' : '📞'}</span>
      <span className="text-xs font-semibold">{isLoading ? 'Connecting' : 'End Call'}</span>
    </button>
  )
}
