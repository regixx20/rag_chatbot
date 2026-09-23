import ReactMarkdown from 'react-markdown'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { UserIcon, SparklesIcon, DatabaseIcon, AlertIcon, FileTextIcon } from './icons'

const documentName = (source) => source.document.replace(/\.[a-z0-9]+$/i, '').replace(/_/g, ' ')
const sourceLabel = (source) => `${documentName(source)}${source.page ? ` · p. ${source.page}` : ''}`
// Compact chip: the page is enough when it exists, the full label stays in the tooltip
const sourceChip = (source) => (source.page ? `p. ${source.page}` : documentName(source))

const markdownComponents = {
  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
}

export function ChatMessage({ message, onRetry }) {
  const isUser = message.role === 'user'
  const intent = message.intent || ''
  const isError = intent === 'Error'
  const sources = !isUser ? message.sources ?? [] : []
  const isWaitingFirstToken = message.isStreaming && !message.content

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
        {!isUser && (intent === 'Rag' || intent === 'NoContext') && (
          <div className="chat-message-badge">
            {intent === 'Rag' ? (
              <Badge variant="outline" className="chat-message-rag">
                <DatabaseIcon />
                <span>RAG</span>
              </Badge>
            ) : (
              <Badge variant="muted" className="chat-message-warning">
                Aucun passage pertinent
              </Badge>
            )}
          </div>
        )}

        <div className="chat-message-bubble">
          {isUser ? (
            <p>{message.content}</p>
          ) : isWaitingFirstToken ? (
            <div className="chat-loading-dots" aria-label="Rédaction en cours">
              <span />
              <span />
              <span />
            </div>
          ) : (
            <div className={`markdown ${message.isStreaming ? 'markdown-streaming' : ''}`}>
              <ReactMarkdown components={markdownComponents}>{message.content}</ReactMarkdown>
              {message.isStreaming && <span className="stream-cursor" aria-hidden="true" />}
            </div>
          )}
          {isError && message.retryContent && (
            <Button variant="outline" size="sm" className="chat-message-retry" onClick={() => onRetry?.(message)}>
              Réessayer
            </Button>
          )}
        </div>

        {sources.length > 0 && !message.isStreaming && (
          <details className="chat-message-sources">
            <summary>
              <span>Sources</span>
              {sources.map((source) => (
                <span key={source.number} className="chat-message-source" title={sourceLabel(source)}>
                  <FileTextIcon aria-hidden="true" />[{source.number}] {sourceChip(source)}
                </span>
              ))}
            </summary>
            <ol className="chat-message-excerpts">
              {sources.map((source) => (
                <li key={source.number} value={source.number}>
                  <p className="chat-message-excerpt-title">
                    {sourceLabel(source)}
                    <span>pertinence {Math.round(source.score * 100)} %</span>
                  </p>
                  <blockquote>{source.excerpt}</blockquote>
                </li>
              ))}
            </ol>
          </details>
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
