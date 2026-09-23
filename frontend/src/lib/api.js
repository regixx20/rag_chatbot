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

export async function apiFetch(url, { timeout = CHAT_TIMEOUT_MS, signal, ...options } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort('timeout'), timeout)
  const onAbort = () => controller.abort(signal.reason)
  signal?.addEventListener('abort', onAbort)

  try {
    const response = await fetch(url, { ...options, signal: controller.signal })
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
