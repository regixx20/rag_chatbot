import { useCallback, useEffect, useRef, useState } from 'react'
import { Menu, SquarePen } from 'lucide-react'
import { Sidebar } from './components/Sidebar'
import { EmptyState } from './components/EmptyState'
import { Message } from './components/Message'
import { Composer } from './components/Composer'
import { Toast } from './components/Toast'
import {
  ApiError,
  UPLOAD_TIMEOUT_MS,
  WAKE_TIMEOUT_MS,
  apiFetch,
  resolveApiBase,
  streamChat,
} from './lib/api'
import { useTheme } from './lib/useTheme'

// Extensions the backend knows how to load (see ragchat/chatbot.py)
export const ACCEPTED_FILE_TYPES = '.pdf,.txt,.docx,.md,.html,.htm,.xml,.json,.csv'

function createId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function normaliseDocument(apiDocument) {
  if (!apiDocument) return null
  const name = apiDocument.original_name || 'Document'
  return {
    id: String(apiDocument.id ?? createId('doc')),
    name,
    extension: name.includes('.') ? name.split('.').pop().toLowerCase() : '',
    isDemo: Boolean(apiDocument.is_demo),
    uploadedAt: apiDocument.uploaded_at ? new Date(apiDocument.uploaded_at) : null,
  }
}

export default function App() {
  const [apiBase] = useState(resolveApiBase)
  const [theme, toggleTheme] = useTheme()
  const [serverState, setServerState] = useState('waking') // waking | online | offline
  const [documents, setDocuments] = useState([])
  const [messages, setMessages] = useState([])
  const [isRagEnabled, setIsRagEnabled] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [toast, setToast] = useState(null)

  const fileInputRef = useRef(null)
  const scrollRef = useRef(null)
  const composerRef = useRef(null)
  const dragDepth = useRef(0)

  const notify = useCallback((text, tone = 'info') => setToast({ text, tone, id: Date.now() }), [])

  const fetchDocuments = useCallback(async () => {
    try {
      const data = await apiFetch(`${apiBase}/documents/`, { timeout: WAKE_TIMEOUT_MS })
      if (Array.isArray(data)) setDocuments(data.map(normaliseDocument).filter(Boolean))
    } catch (error) {
      console.error('Impossible de charger les documents', error)
    }
  }, [apiBase])

  // Wake the (possibly sleeping) server up as soon as the page opens
  const wakeServer = useCallback(async () => {
    setServerState('waking')
    try {
      await apiFetch(`${apiBase}/health/`, { timeout: WAKE_TIMEOUT_MS })
    } catch (error) {
      // Any HTTP answer means the server is up; only network errors/timeouts mean it's not
      if (!(error instanceof ApiError) || error.status === undefined) {
        setServerState('offline')
        return
      }
    }
    setServerState('online')
    fetchDocuments()
  }, [apiBase, fetchDocuments])

  useEffect(() => {
    wakeServer()
  }, [wakeServer])

  // Keep the latest message in view while an answer streams in
  useEffect(() => {
    const container = scrollRef.current
    if (!container) return
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 240
    if (nearBottom || isLoading) container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
  }, [messages, isLoading])

  const sendMessage = useCallback(
    async (content, baseMessages = messages) => {
      const trimmed = content.trim()
      if (!trimmed || isLoading) return

      const history = baseMessages
        .filter((entry) => entry.status !== 'error')
        .map(({ role, content: text }) => ({ role, content: text }))
      const mode = isRagEnabled ? 'rag' : 'direct'
      const assistantId = createId('assistant')

      setMessages([
        ...baseMessages,
        { id: createId('user'), role: 'user', content: trimmed },
        { id: assistantId, role: 'assistant', content: '', mode, status: 'searching', sources: [] },
      ])
      setIsLoading(true)

      const update = (patch) =>
        setMessages((previous) =>
          previous.map((entry) => (entry.id === assistantId ? { ...entry, ...patch(entry) } : entry))
        )

      try {
        await streamChat(
          apiBase,
          { message: trimmed, mode, history },
          {
            onMeta: ({ intent, sources }) =>
              update(() => ({ intent, sources: sources ?? [], status: 'writing' })),
            onToken: (token) => update((entry) => ({ content: entry.content + token, status: 'writing' })),
          }
        )
        setServerState('online')
        update((entry) => ({
          status: 'done',
          content: entry.content || "Je n'ai pas pu formuler de réponse.",
        }))
      } catch (error) {
        console.error("Erreur lors de l'envoi du message", error)
        update(() => ({ status: 'error', content: error.message, retryContent: trimmed }))
      } finally {
        setIsLoading(false)
      }
    },
    [apiBase, isLoading, isRagEnabled, messages]
  )

  const retry = useCallback(
    (message) => {
      // Resend the same question with the history that preceded it
      const index = messages.findIndex((entry) => entry.id === message.id)
      if (index > 0) sendMessage(message.retryContent, messages.slice(0, index - 1))
    },
    [messages, sendMessage]
  )

  const uploadDocuments = useCallback(
    async (fileList) => {
      const files = Array.from(fileList ?? [])
      if (files.length === 0 || serverState !== 'online') return

      setIsUploading(true)
      const uploaded = []
      for (const file of files) {
        const formData = new FormData()
        formData.append('file', file)
        try {
          const data = await apiFetch(`${apiBase}/documents/`, {
            method: 'POST',
            body: formData,
            timeout: UPLOAD_TIMEOUT_MS,
          })
          const parsed = normaliseDocument(data)
          if (parsed) uploaded.push(parsed)
        } catch (error) {
          console.error('Erreur de téléversement', error)
          notify(`« ${file.name} » : ${error.message}`, 'error')
        }
      }
      setIsUploading(false)

      if (uploaded.length > 0) {
        setDocuments((previous) => [...uploaded, ...previous])
        setIsRagEnabled(true)
        notify(
          uploaded.length > 1
            ? `${uploaded.length} documents ajoutés à votre base`
            : `« ${uploaded[0].name} » ajouté à votre base`,
          'success'
        )
      }
    },
    [apiBase, notify, serverState]
  )

  const deleteDocument = useCallback(
    async (doc) => {
      try {
        await apiFetch(`${apiBase}/documents/${doc.id}/`, { method: 'DELETE', timeout: UPLOAD_TIMEOUT_MS })
        setDocuments((previous) => previous.filter((entry) => entry.id !== doc.id))
        notify(`« ${doc.name} » supprimé`)
      } catch (error) {
        notify(`Suppression impossible : ${error.message}`, 'error')
      }
    },
    [apiBase, notify]
  )

  const openFilePicker = () => fileInputRef.current?.click()

  const newConversation = () => {
    setMessages([])
    setIsSidebarOpen(false)
    composerRef.current?.focus()
  }

  // Drag & drop anywhere on the page
  const dragHandlers = {
    onDragEnter: (event) => {
      if (!event.dataTransfer?.types?.includes('Files')) return
      dragDepth.current += 1
      setIsDragging(true)
    },
    onDragLeave: () => {
      dragDepth.current = Math.max(0, dragDepth.current - 1)
      if (dragDepth.current === 0) setIsDragging(false)
    },
    onDragOver: (event) => event.preventDefault(),
    onDrop: (event) => {
      event.preventDefault()
      dragDepth.current = 0
      setIsDragging(false)
      uploadDocuments(event.dataTransfer.files)
    },
  }

  const isEmpty = messages.length === 0

  return (
    <div className={`app ${isSidebarOpen ? 'sidebar-open' : ''}`} {...dragHandlers}>
      <input
        ref={fileInputRef}
        type="file"
        hidden
        multiple
        accept={ACCEPTED_FILE_TYPES}
        onChange={(event) => {
          uploadDocuments(event.target.files)
          event.target.value = ''
        }}
      />

      <Sidebar
        documents={documents}
        serverState={serverState}
        isUploading={isUploading}
        theme={theme}
        onToggleTheme={toggleTheme}
        onNewConversation={newConversation}
        onUpload={openFilePicker}
        onDelete={deleteDocument}
        onRetryServer={wakeServer}
        onClose={() => setIsSidebarOpen(false)}
      />
      <div className="sidebar-backdrop" onClick={() => setIsSidebarOpen(false)} aria-hidden="true" />

      <main className="main">
        <header className="topbar">
          <button className="icon-button" onClick={() => setIsSidebarOpen(true)} aria-label="Ouvrir le menu">
            <Menu size={20} />
          </button>
          <span className="topbar-title">Assistant RAG</span>
          <button className="icon-button" onClick={newConversation} aria-label="Nouvelle conversation">
            <SquarePen size={19} />
          </button>
        </header>

        <div className="thread" ref={scrollRef}>
          <div className="thread-inner">
            {isEmpty ? (
              <EmptyState
                isRagEnabled={isRagEnabled}
                documents={documents}
                disabled={serverState !== 'online'}
                onPick={(question) => sendMessage(question)}
              />
            ) : (
              messages.map((message) => (
                <Message key={message.id} message={message} onRetry={retry} />
              ))
            )}
          </div>
        </div>

        <div className="composer-dock">
          <Composer
            ref={composerRef}
            serverState={serverState}
            isRagEnabled={isRagEnabled}
            onToggleRag={setIsRagEnabled}
            documentCount={documents.length}
            isBusy={isLoading}
            isUploading={isUploading}
            onSend={sendMessage}
            onAttach={openFilePicker}
            onRetryServer={wakeServer}
          />
        </div>
      </main>

      {isDragging && (
        <div className="drop-overlay">
          <div className="drop-card">
            <p>Déposez vos fichiers</p>
            <span>PDF, DOCX, TXT, Markdown, HTML, CSV, JSON, XML · 10 Mo max</span>
          </div>
        </div>
      )}

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  )
}
