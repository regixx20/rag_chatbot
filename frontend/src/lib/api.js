const LOCAL_API_BASE = 'http://localhost:8000/api'
const PROD_API_BASE = 'https://rag-chatbot-shbz.onrender.com/api'

const ENV_KEYS = [
  'VITE_API_BASE_URL',
  'VITE_PUBLIC_API_BASE_URL',
  'PUBLIC_API_BASE_URL',
  'NEXT_PUBLIC_API_BASE_URL',
]

// The free Render instance sleeps after inactivity and needs up to ~1 min to boot.
export const WAKE_TIMEOUT_MS = 100_000
export const CHAT_TIMEOUT_MS = 90_000
export const UPLOAD_TIMEOUT_MS = 180_000

const normaliseBaseUrl = (url) => (url ? url.replace(/\/$/, '') : '')

export function resolveApiBase() {
  for (const key of ENV_KEYS) {
    const value = import.meta.env?.[key]
    if (value) return normaliseBaseUrl(value)
  }

  if (typeof window !== 'undefined') {
    const isLocalhost = ['localhost', '127.0.0.1', '0.0.0.0'].includes(window.location.hostname)
    if (!isLocalhost) return PROD_API_BASE
  }

  return LOCAL_API_BASE
}

// Each visitor gets their own documents: the backend scopes them by this id
const SESSION_STORAGE_KEY = 'rag-chatbot-session-id'
let memorySessionId = null

function createSessionId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `s-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function getSessionId() {
  try {
    let id = localStorage.getItem(SESSION_STORAGE_KEY)
    if (!id) {
      id = createSessionId()
      localStorage.setItem(SESSION_STORAGE_KEY, id)
    }
    return id
  } catch {
    // Storage blocked (private mode…): keep the id for this page only
    memorySessionId ??= createSessionId()
    return memorySessionId
  }
}

export class ApiError extends Error {
  constructor(message, { status, isTimeout = false } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.isTimeout = isTimeout
  }
}

async function readErrorDetail(response) {
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string') return data.detail
    const first = data && Object.values(data)[0]
    if (Array.isArray(first) && typeof first[0] === 'string') return first[0]
  } catch {
    // Non-JSON error body (HTML error page, proxy error…)
  }
  return null
}

// `raw: true` returns the Response as soon as headers arrive (used for streaming)
export async function apiFetch(url, { timeout = CHAT_TIMEOUT_MS, signal, raw = false, ...options } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort('timeout'), timeout)
  const onAbort = () => controller.abort(signal.reason)
  signal?.addEventListener('abort', onAbort)

  try {
    const response = await fetch(url, {
      ...options,
      headers: { 'X-Session-Id': getSessionId(), ...options.headers },
      signal: controller.signal,
    })
    if (raw) return response
    if (!response.ok) {
      const detail = await readErrorDetail(response)
      throw new ApiError(detail || `Le serveur a répondu avec une erreur (${response.status}).`, {
        status: response.status,
      })
    }
    return response.status === 204 ? null : await response.json()
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (controller.signal.aborted && controller.signal.reason === 'timeout') {
      throw new ApiError('Le serveur met trop de temps à répondre.', { isTimeout: true })
    }
    if (signal?.aborted) throw error
    throw new ApiError('Impossible de joindre le serveur. Vérifiez votre connexion.')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }
}

/**
 * Streams an answer from /chat/stream/ (NDJSON). Calls onMeta once with intent and
 * sources, then onToken for each piece of text. Falls back to /chat/ on older backends.
 */
export async function streamChat(apiBase, payload, { onMeta, onToken }) {
  const request = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    timeout: CHAT_TIMEOUT_MS,
  }

  const response = await apiFetch(`${apiBase}/chat/stream/`, { ...request, raw: true })

  if (response.status === 404) {
    const data = await apiFetch(`${apiBase}/chat/`, request)
    onMeta({ intent: data?.intent || 'Direct', sources: data?.sources ?? [] })
    onToken(data?.response || '')
    return
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response)
    throw new ApiError(detail || `Le serveur a répondu avec une erreur (${response.status}).`, {
      status: response.status,
    })
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const handleLine = (line) => {
    if (!line.trim()) return
    const event = JSON.parse(line)
    if (event.type === 'meta') onMeta(event)
    else if (event.type === 'token') onToken(event.content)
    else if (event.type === 'error') throw new ApiError(event.detail, { status: 502 })
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    lines.forEach(handleLine)
  }
  handleLine(buffer + decoder.decode())
}
