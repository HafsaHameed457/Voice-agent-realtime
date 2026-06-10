import { type FC } from 'react'
import { useVoiceAgentContext } from '../context/VoiceAgentContext'

const colors: Record<string, string> = {
  disconnected: 'bg-zinc-700 text-zinc-400',
  connecting: 'bg-yellow-900/60 text-yellow-400',
  connected: 'bg-green-900/60 text-green-400',
  error: 'bg-red-900/60 text-red-400',
}

const labels: Record<string, string> = {
  disconnected: 'Disconnected',
  connecting: 'Connecting',
  connected: 'Connected',
  error: 'Error',
}

export const StatusIndicator: FC = () => {
  const { status, isSpeaking } = useVoiceAgentContext()

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-1.5 text-xs text-zinc-500">
        <span
          className={`inline-block h-2 w-2 rounded-full transition-colors ${
            status === 'connected' ? 'bg-green-500' : 'bg-zinc-600'
          }`}
        />
        Listening
      </div>
      <div className="flex items-center gap-1.5 text-xs text-zinc-500">
        <span
          className={`inline-block h-2 w-2 rounded-full transition-colors ${
            isSpeaking ? 'bg-amber-400' : 'bg-zinc-600'
          }`}
        />
        Speaking
      </div>
      <span
        className={`rounded-full px-3 py-1 text-[11px] font-medium ${colors[status] ?? colors.disconnected}`}
      >
        {labels[status] ?? labels.disconnected}
      </span>
    </div>
  )
}
