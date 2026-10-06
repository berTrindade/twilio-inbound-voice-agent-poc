'use client'

import { useState, useEffect, useRef } from 'react'

interface Message {
  type: 'user' | 'bot' | 'system' | 'error'
  text: string
  timestamp: Date
}

// Every turn lands on exactly one of six outcomes. Answering the questions
// normally only ever shows the first, so these are shortcuts to the other five.
const SUGGESTIONS: { label: string; text: string; shows: string }[] = [
  {
    label: 'Ask for a human',
    text: 'Can I speak to a real person please',
    shows: 'Handover: a terminal state, not an error path',
  },
  {
    label: 'Question the question',
    text: 'Why do you need to know that?',
    shows: 'Answers the caller, then returns to the same question',
  },
  {
    label: 'Go off topic',
    text: "What's the weather like where you are?",
    shows: 'Refuses without derailing the survey',
  },
  {
    label: 'Medical advice',
    text: 'Should I stop taking my blood pressure tablets?',
    shows: 'Guardrail: canned response, never the model',
  },
  {
    label: 'Be ambiguous',
    text: 'I mean, depends on the day',
    shows: 'Not an answer, so it retries rather than guessing',
  },
]

// Minimal shape of the Web Speech API SpeechRecognition (not in the standard DOM lib).
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  onresult:
    | ((event: {
        results: ArrayLike<ArrayLike<{ transcript: string }>>
        resultIndex: number
      }) => void)
    | null
  onend: (() => void) | null
  onerror: (() => void) | null
}

const getRecognitionCtor = (): (new () => SpeechRecognitionLike) | null => {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

interface VoiceChatProps {
  wsUrl: string
  title: string
  subtitle: string
}

export function VoiceChat({ wsUrl, title, subtitle }: VoiceChatProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [isListening, setIsListening] = useState(false)
  const [speechSupported, setSpeechSupported] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  const isLocal = wsUrl.includes('localhost')
  const environment = isLocal ? 'Local' : 'Remote'

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Speak a bot utterance via the browser's built-in TTS (free, no ElevenLabs).
  const speak = (text: string) => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'en-US'
    utterance.rate = 1
    window.speechSynthesis.speak(utterance)
  }

  // Deliberately in an effect rather than a lazy initialiser: the server has no
  // window, so resolving this during render would make the server and the first
  // client render disagree and trip a hydration mismatch.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSpeechSupported(
      getRecognitionCtor() !== null &&
        typeof window !== 'undefined' &&
        !!window.speechSynthesis
    )
  }, [])

  useEffect(() => {
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      setIsConnected(true)

      const setupMessage = {
        type: 'setup',
        callSid: `web-client-${Date.now()}`,
      }
      ws.send(JSON.stringify(setupMessage))
      setSessionId(setupMessage.callSid)
      setMessages((prev) => [
        ...prev,
        {
          type: 'system',
          text: 'Connected to server. Ready to chat!',
          timestamp: new Date(),
        },
      ])
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data as string)

      if (data.type === 'text') {
        const token = data.token as string
        setMessages((prev) => [
          ...prev,
          { type: 'bot', text: token, timestamp: new Date() },
        ])
        if (voiceEnabled) speak(token)
      } else if (data.type === 'error') {
        setMessages((prev) => [
          ...prev,
          {
            type: 'error',
            text: (data.message as string) || 'Error occurred',
            timestamp: new Date(),
          },
        ])
      }
    }

    ws.onerror = () => {
      setMessages((prev) => [
        ...prev,
        { type: 'error', text: 'Connection error occurred', timestamp: new Date() },
      ])
    }

    ws.onclose = () => {
      setIsConnected(false)
      setMessages((prev) => [
        ...prev,
        { type: 'system', text: 'Disconnected from server', timestamp: new Date() },
      ])
    }

    wsRef.current = ws

    return () => {
      ws.close()
    }
  }, [wsUrl, voiceEnabled])

  const sendPrompt = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || !wsRef.current || !isConnected) return

    wsRef.current.send(
      JSON.stringify({ type: 'prompt', voicePrompt: trimmed, last: true })
    )
    setMessages((prev) => [
      ...prev,
      { type: 'user', text: trimmed, timestamp: new Date() },
    ])
    setInputMessage('')
  }

  const sendMessage = (e: React.FormEvent) => {
    e.preventDefault()
    sendPrompt(inputMessage)
  }

  const toggleListening = () => {
    if (isListening) {
      recognitionRef.current?.stop()
      return
    }
    const Ctor = getRecognitionCtor()
    if (!Ctor) return

    const recognition = new Ctor()
    recognition.lang = 'en-US'
    recognition.continuous = false
    recognition.interimResults = false
    recognition.onresult = (event) => {
      const transcript = event.results[event.resultIndex]?.[0]?.transcript ?? ''
      if (transcript) sendPrompt(transcript)
    }
    recognition.onend = () => setIsListening(false)
    recognition.onerror = () => setIsListening(false)
    recognitionRef.current = recognition
    recognition.start()
    setIsListening(true)
  }

  const getMessageStyle = (type: Message['type']): string => {
    switch (type) {
      case 'user':
        return 'bg-brand text-white ml-auto'
      case 'bot':
        return 'bg-gray-200 text-gray-900 mr-auto'
      case 'system':
        return 'bg-yellow-100 text-yellow-900 mx-auto text-center'
      case 'error':
        return 'bg-red-100 text-red-900 mx-auto text-center'
    }
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-4 sm:px-6 py-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
            <p className="text-sm text-gray-500">{subtitle}</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setVoiceEnabled((v) => !v)}
              className={`px-3 py-1 rounded-full text-xs font-medium ${
                voiceEnabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
              }`}
              title="Toggle spoken responses"
            >
              {voiceEnabled ? '🔊 Voice on' : '🔇 Voice off'}
            </button>
            <div
              className={`px-3 py-1 rounded-full text-xs font-medium ${
                isLocal ? 'bg-blue-100 text-blue-800' : 'bg-purple-100 text-purple-800'
              }`}
            >
              {environment}
            </div>
            <div className="flex items-center gap-2">
              <div
                className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}
              />
              <span className="text-sm font-medium text-gray-700">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            {sessionId && (
              <div className="text-xs text-gray-500 font-mono bg-gray-100 px-2 py-1 rounded">
                {sessionId.slice(0, 8)}...
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-gray-400">
              <svg
                className="w-16 h-16 mx-auto mb-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                />
              </svg>
              <p className="text-lg font-medium">No messages yet</p>
              <p className="text-sm">Type or tap the mic to start</p>
            </div>
          </div>
        )}

        {messages.map((msg, index) => (
          <div key={index} className="flex">
            <div className={`max-w-[85%] sm:max-w-xl px-4 py-2 rounded-lg ${getMessageStyle(msg.type)}`}>
              <p className="text-sm whitespace-pre-wrap break-words">{msg.text}</p>
              <p className="text-xs opacity-60 mt-1">{msg.timestamp.toLocaleTimeString()}</p>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="bg-white border-t border-gray-200 px-4 sm:px-6 py-4">
        {/* Answering the questions straight through exercises one path out of six.
            These are the other five, which are the interesting ones. */}
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs text-gray-500 mr-1">Try:</span>
          {SUGGESTIONS.map((s) => (
            <button
              key={s.text}
              type="button"
              onClick={() => sendPrompt(s.text)}
              disabled={!isConnected}
              title={s.shows}
              className="text-xs px-2.5 py-1 rounded-full border border-gray-300 text-gray-700 hover:bg-gray-100 hover:border-gray-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {s.label}
            </button>
          ))}
        </div>
        <form onSubmit={sendMessage} className="flex gap-3">
          {speechSupported && (
            <button
              type="button"
              onClick={toggleListening}
              disabled={!isConnected}
              title={isListening ? 'Stop listening' : 'Speak your answer'}
              className={`px-4 py-3 rounded-lg font-medium focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors ${
                isListening
                  ? 'bg-red-500 text-white animate-pulse focus:ring-red-500'
                  : 'bg-gray-200 text-gray-800 hover:bg-gray-300 focus:ring-gray-400'
              }`}
            >
              {isListening ? '● Listening' : '🎤'}
            </button>
          )}
          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder={isConnected ? 'Type your message...' : 'Connecting...'}
            disabled={!isConnected}
            className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!isConnected || !inputMessage.trim()}
            className="px-4 sm:px-6 py-3 bg-brand text-white font-medium rounded-lg hover:bg-brand-dark focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </form>
        <p className="text-xs text-gray-500 mt-2">
          Press Enter to send • {environment}: {wsUrl}
          {speechSupported
            ? ' • Mic + spoken replies use your browser (Chrome/Edge), no paid services'
            : ' • Voice needs Chrome or Edge'}
        </p>
      </div>
    </div>
  )
}
