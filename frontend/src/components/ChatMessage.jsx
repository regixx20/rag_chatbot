import ReactMarkdown from 'react-markdown'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { UserIcon, SparklesIcon, DatabaseIcon, AlertIcon, FileTextIcon } from './icons'

// "…/media/uploads/2025/12/15/tiktok_laws.pdf" -> "tiktok_laws.pdf"
const fileName = (source) => String(source).split(/[\\/]/).pop()

const markdownComponents = {
  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
}

export function ChatMessage({ message, onRetry }) {
  const isUser = message.role === 'user'
  const intent = message.intent || ''
  const isError = intent === 'Error'
  const sources = !isUser ? [...new Set((message.usedDocuments ?? []).map(fileName))] : []

  return (
    <div
      className={`chat-message ${isUser ? 'chat-message-user' : 'chat-message-assistant'} ${
        isError ? 'chat-message-error' : ''
      }`}
    >
      <div className="chat-message-avatar" aria-hidden="true">
        {isUser ? <UserIcon /> : isError ? <AlertIcon /> : <SparklesIcon />}
      </div>
      <div className="chat-message-body">
        {!isUser && (intent === 'Rag' || intent === 'NoDocuments') && (
          <div className="chat-message-badge">
            {intent === 'Rag' ? (
              <Badge variant="outline" className="chat-message-rag">
                <DatabaseIcon />
                <span>RAG</span>
              </Badge>
            ) : (
              <Badge variant="muted" className="chat-message-warning">
                Aucun document
              </Badge>
            )}
          </div>
        )}

        <div className="chat-message-bubble">
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <div className="markdown">
              <ReactMarkdown components={markdownComponents}>{message.content}</ReactMarkdown>
            </div>
          )}
          {isError && message.retryContent && (
            <Button variant="outline" size="sm" className="chat-message-retry" onClick={() => onRetry?.(message)}>
              Réessayer
            </Button>
          )}
        </div>

        {sources.length > 0 && (
          <div className="chat-message-sources">
            <span>Sources :</span>
            {sources.map((source) => (
              <span key={source} className="chat-message-source" title={source}>
                <FileTextIcon aria-hidden="true" />
                {source}
              </span>
            ))}
          </div>
        )}

        <span className="chat-message-time">
          {message.timestamp
            ? new Date(message.timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
            : ''}
        </span>
      </div>
    </div>
  )
}
