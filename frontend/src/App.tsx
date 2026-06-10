import { useMemo } from 'react'
import type { FC } from 'react'
import { useVoiceAgent } from './hooks/useVoiceAgent'
import { VoiceAgentContext } from './context/VoiceAgentContext'
import { CallButton } from './components/CallButton'
import { TranscriptLog } from './components/TranscriptLog'
import { AudioMeter } from './components/AudioMeter'
import { StatusIndicator } from './components/StatusIndicator'

const App: FC = () => {
  const agent = useVoiceAgent()

  const ctx = useMemo(
    () => ({
      status: agent.status,
      messages: agent.messages,
      isSpeaking: agent.isSpeaking,
      connect: agent.connect,
      disconnect: agent.disconnect,
    }),
    [agent],
  )

  return (
    <VoiceAgentContext.Provider value={ctx}>
      <div className="mx-auto flex h-screen max-w-md flex-col px-6 pb-6 pt-8">
        <header className="mb-4 flex items-center justify-between">
          <h1 className="text-2xl font-semibold tracking-tight text-white">
            Voice Agent
          </h1>
          <StatusIndicator />
        </header>

        <div className="flex flex-col items-center gap-4 py-8">
          <CallButton />
          <AudioMeter />
        </div>

        <TranscriptLog />
      </div>
    </VoiceAgentContext.Provider>
  )
}

export default App
