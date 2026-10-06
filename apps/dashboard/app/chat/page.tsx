'use client'

import { useState } from 'react'
import { getWsUrl } from './WsConfig'
import { VoiceChat } from '@/components/VoiceChat'
import { useBranding } from '@/components/BrandingProvider'

export default function ChatPage() {
  const branding = useBranding()
  const [wsUrl] = useState<string>(() => (typeof window !== 'undefined' ? getWsUrl() : ''))

  return (
    <VoiceChat
      wsUrl={wsUrl}
      title={branding.appName}
      subtitle="Voice / chat survey client"
    />
  )
}
