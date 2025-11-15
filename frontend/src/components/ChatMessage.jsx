import { Badge } from './ui/Badge'
import { UserIcon, SparklesIcon, DatabaseIcon } from './icons'

export function ChatMessage({ message }) {
  const isUser = message.role === 'user'
  const intent = message.intent || ''
  const showRagBadge = !isUser && intent === 'Rag'
  const showNoDocumentsBadge = !isUser && intent === 'NoDocuments'
  const hasSources = !isUser && Array.isArray(message.usedDocuments) && message.usedDocuments.length > 0

  return (
    <div className={`chat-message ${isUser ? 'chat-message-user' : 'chat-message-assistant'}`}>
      <div className="chat-message-avatar">
        {isUser ? <UserIcon /> : <SparklesIcon />}
      </div>
      <div className="chat-message-body">
        {!isUser && (showRagBadge || showNoDocumentsBadge) && (
          <div className="chat-message-badge">
            {showRagBadge && (
              <Badge variant="outline" className="chat-message-rag">
                <DatabaseIcon />
                <span>RAG</span>
              </Badge>
            )}
            {showNoDocumentsBadge && (
              <Badge variant="muted" className="chat-message-warning">
                <span>Aucun document</span>
              </Badge>
            )}
          </div>
        )}
        <div className={`chat-message-bubble ${isUser ? 'bubble-user' : 'bubble-assistant'}`}>
          <p>{message.content}</p>
        </div>
        {hasSources && (
          <div className="chat-message-sources">
            <span>Sources :</span>
            <ul>
              {message.usedDocuments.map((doc) => {
                const label =
                  typeof doc === 'string' ? doc.split(/[\/]/).pop() || doc : 'Document'
                return <li key={doc}>{label}</li>
              })}
            </ul>
          </div>
        )}
        <span className="chat-message-time">
          {message.timestamp
            ? new Date(message.timestamp).toLocaleTimeString('fr-FR', {
                hour: '2-digit',
                minute: '2-digit',
              })
            : ''}
        </span>
      </div>
    </div>
  )
}
