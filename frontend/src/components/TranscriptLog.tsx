import { type FC, useEffect, useRef } from 'react'
import { useVoiceAgentContext } from '../context/VoiceAgentContext'

export const TranscriptLog: FC = () => {
  const { messages } = useVoiceAgentContext()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  return (
    <div className="flex-1 overflow-y-auto rounded-xl bg-zinc-900/50 p-3">
      <div className="flex flex-col gap-2">
        {messages.map((msg, i) => {
          const time = new Date(msg.timestamp).toLocaleTimeString()
          const isUser = msg.role === 'user'
          return (
            <div
              key={i}
              className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
                  isUser
                    ? 'bg-blue-900/60 text-blue-200'
                    : 'bg-zinc-800 text-zinc-200'
                }`}
              >
                <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider opacity-50">
                  {isUser ? 'You' : 'Agent'}
                </div>
                <div>{msg.text}</div>
                <div className="mt-1 text-[10px] opacity-30">{time}</div>
              </div>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
