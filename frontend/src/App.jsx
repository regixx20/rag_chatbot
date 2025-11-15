import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChatInput } from './components/ChatInput'
import { ChatMessage } from './components/ChatMessage'
import { DocumentPanel } from './components/DocumentPanel'
import { Badge } from './components/ui/Badge'
import { Switch } from './components/ui/Switch'
import { Label } from './components/ui/Label'
import { SparklesIcon, DatabaseIcon } from './components/icons'

const DEFAULT_API_BASE = 'http://localhost:8000/api'

const INITIAL_ASSISTANT_MESSAGE = {
  id: 'welcome',
  content:
    "Bonjour ! Posez votre question et activez le mode RAG pour enrichir les réponses avec vos documents.",
  role: 'assistant',
  timestamp: new Date(),
  intent: 'System',
}

function createMessageId(prefix = 'msg') {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function normaliseDocument(apiDocument) {
  if (!apiDocument) {
    return null
  }

  const id = apiDocument.id ?? createMessageId('doc')
  const name = apiDocument.original_name || apiDocument.file || 'Document'
  const filePath = apiDocument.file || ''
  const extension = typeof name === 'string' && name.includes('.') ? name.split('.').pop() ?? '' : ''

  return {
    id: String(id),
    name,
    size: Number(apiDocument.size ?? 0),
    type: apiDocument.type || extension,
    uploadedAt: apiDocument.uploaded_at ? new Date(apiDocument.uploaded_at) : new Date(),
    path: filePath,
  }
}

export default function App() {
  const [apiBase] = useState(() => import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE)
  const [documents, setDocuments] = useState([])
  const [messages, setMessages] = useState([INITIAL_ASSISTANT_MESSAGE])
  const [isRagEnabled, setIsRagEnabled] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [statusMessage, setStatusMessage] = useState('')

  const fetchDocuments = useCallback(async () => {
    try {
      const response = await fetch(`${apiBase}/documents/`)
      if (!response.ok) {
        throw new Error('Réponse réseau invalide')
      }
      const data = await response.json()
      const results = Array.isArray(data?.results) ? data.results : data
      if (!Array.isArray(results)) {
        setDocuments([])
        return
      }
      const parsed = results
        .map(normaliseDocument)
        .filter(Boolean)
        .sort((a, b) => b.uploadedAt.getTime() - a.uploadedAt.getTime())
      setDocuments(parsed)
    } catch (error) {
      console.error('Impossible de charger les documents', error)
      setDocuments([])
    }
  }, [apiBase, refreshKey])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  useEffect(() => {
    setMessages([INITIAL_ASSISTANT_MESSAGE])
  }, [refreshKey])

  const buildHistoryPayload = useCallback(
    (historyMessages) =>
      historyMessages
        .filter((entry) => entry.role === 'user' || entry.role === 'assistant')
        .map(({ role, content }) => ({ role, content })),
    []
  )

  const handleSendMessage = useCallback(
    async (content) => {
      const trimmed = content.trim()
      if (!trimmed || isLoading) {
        return
      }

      const userMessage = {
        id: createMessageId('user'),
        content: trimmed,
        role: 'user',
        timestamp: new Date(),
        intent: 'User',
      }

      setMessages((previous) => [...previous, userMessage])
      setIsLoading(true)
      setStatusMessage('')

      const historyPayload = buildHistoryPayload([...messages, userMessage])

      try {
        const response = await fetch(`${apiBase}/chat/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: trimmed,
            mode: isRagEnabled ? 'rag' : 'direct',
            history: historyPayload,
          }),
        })

        if (!response.ok) {
          throw new Error('Réponse du serveur invalide')
        }

        const data = await response.json()
        const assistantMessage = {
          id: createMessageId('assistant'),
          content: data.response || "Je n'ai pas pu formuler de réponse.",
          role: 'assistant',
          timestamp: new Date(),
          usedDocuments: Array.isArray(data.used_documents) ? data.used_documents : [],
          intent: data.intent || 'Direct',
        }

        setMessages((previous) => [...previous, assistantMessage])
      } catch (error) {
        console.error('Erreur lors de lenvoi du message', error)
        setStatusMessage("Une erreur est survenue lors de l'appel au serveur.")
        const fallbackMessage = {
          id: createMessageId('assistant-error'),
          content: "Une erreur est survenue. Vérifiez votre connexion à l'API.",
          role: 'assistant',
          timestamp: new Date(),
          intent: 'Error',
        }
        setMessages((previous) => [...previous, fallbackMessage])
      } finally {
        setIsLoading(false)
      }
    },
    [apiBase, buildHistoryPayload, isLoading, isRagEnabled, messages]
  )

  const handleUploadDocuments = useMemo(
    () =>
      async (fileList) => {
        if (!fileList || fileList.length === 0) {
          return
        }

        const files = Array.from(fileList)
        const uploaded = []

        for (const file of files) {
          const formData = new FormData()
          formData.append('file', file)

          try {
            const response = await fetch(`${apiBase}/documents/`, {
              method: 'POST',
              body: formData,
            })

            if (!response.ok) {
              throw new Error('Téléversement refusé')
            }

            const data = await response.json()
            const parsedDocument = normaliseDocument(data)
            if (parsedDocument) {
              uploaded.push(parsedDocument)
            }
          } catch (error) {
            console.error('Erreur de téléversement', error)
            setStatusMessage('Impossible de téléverser un des fichiers.')
            break
          }
        }

        if (uploaded.length > 0) {
          setDocuments((previous) => [...uploaded, ...previous])
          setRefreshKey((key) => key + 1)
          setStatusMessage('Téléversement terminé et documents ingérés.')
        }
      },
    [apiBase]
  )

  const handleDeleteDocument = useCallback(
    async (id) => {
      if (!id) return
      try {
        const response = await fetch(`${apiBase}/documents/${id}/`, { method: 'DELETE' })
        if (!response.ok && response.status !== 204) {
          throw new Error('Suppression refusée')
        }
        setDocuments((previous) => previous.filter((doc) => doc.id !== id))
        setStatusMessage('Document supprimé.')
      } catch (error) {
        console.error('Erreur de suppression', error)
        setStatusMessage('Impossible de supprimer le document.')
      }
    },
    [apiBase]
  )

  return (
    <div className="app-shell">
      <DocumentPanel
        documents={documents}
        isRagEnabled={isRagEnabled}
        onUpload={handleUploadDocuments}
        onDelete={handleDeleteDocument}
      />

      <div className="chat-surface">
        <header className="chat-header">
          <div className="chat-brand">
            <div className="chat-brand-icon">
              <SparklesIcon aria-hidden="true" />
            </div>
            <div className="chat-brand-text">
              <h1>Assistant IA</h1>
              <p>Propulsé par votre base de connaissances</p>
            </div>
          </div>
          <div className="rag-toggle">
            <DatabaseIcon aria-hidden="true" />
            <Label htmlFor="rag-switch">Mode RAG</Label>
            <Switch
              id="rag-switch"
              checked={isRagEnabled}
              onCheckedChange={setIsRagEnabled}
              aria-label="Activer le mode RAG"
            />
            {isRagEnabled ? <Badge variant="accent">Activé</Badge> : <Badge variant="muted">Inactif</Badge>}
          </div>
        </header>

        <div className="chat-status">
          {isRagEnabled ? (
            <div className="status-rag">
              <span className="status-dot" />
              Recherche augmentée activée — {documents.length}{' '}
              document{documents.length > 1 ? 's' : ''} disponible{documents.length > 1 ? 's' : ''}
            </div>
          ) : (
            <div className="status-standard">
              <span className="status-dot" />
              Mode standard — réponses basées sur le modèle
            </div>
          )}
        </div>

        <div className="chat-messages">
          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}
          {isLoading && (
            <div className="chat-loading">
              <div className="chat-loading-icon">
                <SparklesIcon aria-hidden="true" />
              </div>
              <div className="chat-loading-dots">
                <span />
                <span />
                <span />
              </div>
            </div>
          )}
        </div>

        <footer className="chat-input">
          <ChatInput onSend={handleSendMessage} disabled={isLoading} />
          {statusMessage && <p className="status-message">{statusMessage}</p>}
        </footer>
      </div>
    </div>
  )
}
