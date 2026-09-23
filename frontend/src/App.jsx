import { useCallback, useEffect, useRef, useState } from 'react'
import { ChatInput } from './components/ChatInput'
import { ChatMessage } from './components/ChatMessage'
import { DocumentPanel } from './components/DocumentPanel'
import { ServerStatus } from './components/ServerStatus'
import { Badge } from './components/ui/Badge'
import { Button } from './components/ui/Button'
import { Switch } from './components/ui/Switch'
import { Label } from './components/ui/Label'
import { SparklesIcon, DatabaseIcon, FileTextIcon, RefreshIcon } from './components/icons'
import {
  ApiError,
  UPLOAD_TIMEOUT_MS,
  WAKE_TIMEOUT_MS,
  apiFetch,
  resolveApiBase,
  streamChat,
} from './lib/api'

// Extensions the backend knows how to load (see ChatbotEngine._load_documents_from_path)
export const ACCEPTED_FILE_TYPES = '.pdf,.txt,.docx,.md,.html,.htm,.xml,.json,.csv'

const SUGGESTIONS = {
  direct: [
    "Explique-moi ce qu'est le RAG en quelques phrases",
    'Quelle est la différence entre un embedding et un token ?',
    'Donne-moi 3 idées de projets utilisant un chatbot',
  ],
  rag: [
    'TikTok peut-il réutiliser mes vidéos ?',
    'À partir de quel âge peut-on créer un compte ?',
    'Comment sont réglés les litiges avec TikTok ?',
  ],
}

function createWelcomeMessage() {
  return {
    id: 'welcome',
    content:
      "Bonjour ! Le **mode RAG** est activé : je réponds à partir des documents disponibles, en citant mes sources. Un document de démo est déjà chargé (les conditions d'utilisation de TikTok) — posez une question, ou ajoutez vos propres fichiers.",
    role: 'assistant',
    timestamp: new Date(),
    intent: 'System',
  }
}

function createMessageId(prefix = 'msg') {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function normaliseDocument(apiDocument) {
  if (!apiDocument) return null

  const name = apiDocument.original_name || apiDocument.file || 'Document'
  const extension = typeof name === 'string' && name.includes('.') ? name.split('.').pop() ?? '' : ''

  return {
    id: String(apiDocument.id ?? createMessageId('doc')),
    name,
    type: apiDocument.type || extension,
    isDemo: Boolean(apiDocument.is_demo),
    uploadedAt: apiDocument.uploaded_at ? new Date(apiDocument.uploaded_at) : null,
  }
}

export default function App() {
  const [apiBase] = useState(resolveApiBase)
  const [serverState, setServerState] = useState('waking') // waking | online | offline
  const [documents, setDocuments] = useState([])
  const [messages, setMessages] = useState(() => [createWelcomeMessage()])
  const [isRagEnabled, setIsRagEnabled] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isPanelOpen, setIsPanelOpen] = useState(false)
  const [statusMessage, setStatusMessage] = useState(null)

  const fileInputRef = useRef(null)
  const messagesEndRef = useRef(null)

  const fetchDocuments = useCallback(async () => {
    try {
      const data = await apiFetch(`${apiBase}/documents/`, { timeout: WAKE_TIMEOUT_MS })
      const results = Array.isArray(data?.results) ? data.results : data
      if (!Array.isArray(results)) return
      setDocuments(
        results
          .map(normaliseDocument)
          .filter(Boolean)
          .sort((a, b) => (b.uploadedAt?.getTime() ?? 0) - (a.uploadedAt?.getTime() ?? 0))
      )
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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isLoading])

  const showStatus = (text, tone = 'info') => setStatusMessage({ text, tone })

  const handleSendMessage = useCallback(
    async (content, baseMessages = messages) => {
      const trimmed = content.trim()
      if (!trimmed || isLoading) return

      const userMessage = {
        id: createMessageId('user'),
        content: trimmed,
        role: 'user',
        timestamp: new Date(),
        intent: 'User',
      }

      const history = baseMessages
        .filter((entry) => entry.intent !== 'System' && entry.intent !== 'Error')
        .map(({ role, content: text }) => ({ role, content: text }))

      const assistantId = createMessageId('assistant')
      setMessages([...baseMessages, userMessage])
      setIsLoading(true)
      setStatusMessage(null)

      const updateAssistant = (patch) =>
        setMessages((previous) => {
          const exists = previous.some((entry) => entry.id === assistantId)
          const base = exists
            ? previous
            : [...previous, { id: assistantId, role: 'assistant', content: '', timestamp: new Date() }]
          return base.map((entry) => (entry.id === assistantId ? { ...entry, ...patch(entry) } : entry))
        })

      try {
        await streamChat(
          apiBase,
          { message: trimmed, mode: isRagEnabled ? 'rag' : 'direct', history },
          {
            onMeta: ({ intent, sources }) =>
              updateAssistant(() => ({ intent: intent || 'Direct', sources: sources ?? [], isStreaming: true })),
            onToken: (token) => updateAssistant((entry) => ({ content: entry.content + token })),
          }
        )
        setServerState('online')
        updateAssistant((entry) => ({
          isStreaming: false,
          content: entry.content || "Je n'ai pas pu formuler de réponse.",
        }))
      } catch (error) {
        console.error("Erreur lors de l'envoi du message", error)
        // Drop a partially streamed answer and show the error instead
        setMessages((previous) => [
          ...previous.filter((entry) => entry.id !== assistantId),
          {
            id: createMessageId('assistant-error'),
            content: error.message,
            role: 'assistant',
            timestamp: new Date(),
            intent: 'Error',
            retryContent: trimmed,
          },
        ])
      } finally {
        setIsLoading(false)
      }
    },
    [apiBase, isLoading, isRagEnabled, messages]
  )

  const handleRetry = useCallback(
    (message) => {
      // Drop the failed exchange and resend the same question
      const index = messages.findIndex((entry) => entry.id === message.id)
      if (index < 1) return
      handleSendMessage(message.retryContent, messages.slice(0, index - 1))
    },
    [handleSendMessage, messages]
  )

  const handleUploadDocuments = useCallback(
    async (fileList) => {
      const files = Array.from(fileList ?? [])
      if (files.length === 0) return

      setIsUploading(true)
      showStatus(
        files.length > 1
          ? `Analyse de ${files.length} documents en cours…`
          : `Analyse de « ${files[0].name} » en cours…`
      )

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
          showStatus(`Impossible d'ajouter « ${file.name} » : ${error.message}`, 'error')
          break
        }
      }

      setIsUploading(false)
      if (uploaded.length > 0) {
        setDocuments((previous) => [...uploaded, ...previous])
        setIsRagEnabled(true)
        showStatus(
          `${uploaded.length} document${uploaded.length > 1 ? 's ajoutés' : ' ajouté'}. Le mode RAG est activé.`,
          'success'
        )
      }
    },
    [apiBase]
  )

  const openFilePicker = () => fileInputRef.current?.click()

  const handleDeleteDocument = useCallback(
    async (id) => {
      if (!id) return
      try {
        await apiFetch(`${apiBase}/documents/${id}/`, { method: 'DELETE', timeout: UPLOAD_TIMEOUT_MS })
        setDocuments((previous) => previous.filter((doc) => doc.id !== id))
        showStatus('Document supprimé.', 'success')
      } catch (error) {
        console.error('Erreur de suppression', error)
        showStatus(`Impossible de supprimer le document : ${error.message}`, 'error')
      }
    },
    [apiBase]
  )

  const resetConversation = () => {
    setMessages([createWelcomeMessage()])
    setStatusMessage(null)
  }

  const isConversationEmpty = messages.length === 1
  const canSend = serverState === 'online' && !isLoading

  return (
    <div className={`app-shell ${isPanelOpen ? 'panel-open' : ''}`}>
      <input
        ref={fileInputRef}
        type="file"
        className="document-input"
        multiple
        accept={ACCEPTED_FILE_TYPES}
        onChange={(event) => {
          handleUploadDocuments(event.target.files)
          event.target.value = ''
        }}
      />

      <DocumentPanel
        documents={documents}
        isRagEnabled={isRagEnabled}
        isUploading={isUploading}
        canUpload={serverState === 'online'}
        onUpload={openFilePicker}
        onDelete={handleDeleteDocument}
        onClose={() => setIsPanelOpen(false)}
      />
      {isPanelOpen && <div className="panel-backdrop" onClick={() => setIsPanelOpen(false)} />}

      <main className="chat-surface">
        <header className="chat-header">
          <div className="chat-brand">
            <div className="chat-brand-icon">
              <SparklesIcon aria-hidden="true" />
            </div>
            <div className="chat-brand-text">
              <h1>Assistant IA</h1>
              <p>Réponses augmentées par vos documents</p>
            </div>
          </div>

          <div className="chat-header-actions">
            <Button
              variant="outline"
              size="sm"
              className="documents-toggle"
              onClick={() => setIsPanelOpen(true)}
              aria-label="Afficher les documents"
            >
              <FileTextIcon aria-hidden="true" />
              <span>Documents</span>
              <Badge variant="muted">{documents.length}</Badge>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={resetConversation}
              disabled={isConversationEmpty || isLoading}
              aria-label="Nouvelle conversation"
              title="Nouvelle conversation"
            >
              <RefreshIcon aria-hidden="true" />
            </Button>
            <div className="rag-toggle">
              <DatabaseIcon aria-hidden="true" />
              <Label htmlFor="rag-switch">Mode RAG</Label>
              <Switch id="rag-switch" checked={isRagEnabled} onCheckedChange={setIsRagEnabled} />
            </div>
          </div>
        </header>

        <ServerStatus state={serverState} onRetry={wakeServer} />

        <div className="chat-mode">
          {isRagEnabled ? (
            <span className="status-rag">
              <span className="status-dot" />
              Recherche dans vos documents — {documents.length} document
              {documents.length > 1 ? 's' : ''} disponible{documents.length > 1 ? 's' : ''}
            </span>
          ) : (
            <span className="status-standard">
              <span className="status-dot" />
              Mode standard — réponses du modèle, sans documents
            </span>
          )}
        </div>

        <div className="chat-messages" aria-live="polite">
          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} onRetry={handleRetry} />
          ))}

          {isConversationEmpty && serverState === 'online' && (
            <div className="chat-suggestions">
              {SUGGESTIONS[isRagEnabled ? 'rag' : 'direct'].map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  className="chat-suggestion"
                  onClick={() => handleSendMessage(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}

          {isLoading && !messages.at(-1)?.isStreaming && (
            <div className="chat-loading" role="status">
              <div className="chat-loading-icon">
                <SparklesIcon aria-hidden="true" />
              </div>
              <div className="chat-loading-dots">
                <span />
                <span />
                <span />
              </div>
              <span className="visually-hidden">L'assistant rédige une réponse…</span>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <footer className="chat-input">
          <ChatInput
            onSend={handleSendMessage}
            onAttach={openFilePicker}
            canSend={canSend}
            canAttach={serverState === 'online' && !isUploading}
            placeholder={
              serverState === 'online'
                ? isRagEnabled
                  ? 'Posez une question sur vos documents…'
                  : 'Posez votre question…'
                : 'Connexion au serveur en cours…'
            }
          />
          {statusMessage && (
            <p className={`status-message status-message-${statusMessage.tone}`} role="status">
              {statusMessage.text}
            </p>
          )}
        </footer>
      </main>
    </div>
  )
}
