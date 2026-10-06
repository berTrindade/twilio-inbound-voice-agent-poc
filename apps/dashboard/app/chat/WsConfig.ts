// WebSocket Configuration
// The runner is reached from the browser, not from the compose network, so the
// host is whatever the dashboard itself was opened on. Deriving it at runtime
// means the chat page works over localhost, a LAN address or a tunnel without
// rebuilding: NEXT_PUBLIC_* is inlined at build time, so a value set only in
// docker-compose would never reach the browser.
//
// Set NEXT_PUBLIC_WS_URL at build time to override the whole URL, or
// NEXT_PUBLIC_RUNNER_PORT to keep the derived host and change only the port.

const DEFAULT_RUNNER_PORT = '8080'

export function getWsUrl(): string {
  const override = process.env.NEXT_PUBLIC_WS_URL
  if (override) return override

  const port = process.env.NEXT_PUBLIC_RUNNER_PORT || DEFAULT_RUNNER_PORT
  const { protocol, hostname } = window.location
  const scheme = protocol === 'https:' ? 'wss' : 'ws'

  return `${scheme}://${hostname}:${port}/ws`
}
