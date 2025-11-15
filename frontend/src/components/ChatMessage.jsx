import { Badge } from './ui/Badge'
import { UserIcon, SparklesIcon, DatabaseIcon } from './icons'

export function ChatMessage({ message, showRagBadge = false }) {
  const isUser = message.role === 'user'

  return (
    <div className={`chat-message ${isUser ? 'chat-message-user' : 'chat-message-assistant'}`}>
      <div className="chat-message-avatar">
        {isUser ? <UserIcon /> : <SparklesIcon />}
      </div>
      <div className="chat-message-body">
        {!isUser && showRagBadge && (
          <div className="chat-message-badge">
            <Badge variant="outline" className="chat-message-rag">
              <DatabaseIcon />
              <span>RAG</span>
            </Badge>
          </div>
        )}
        <div className={`chat-message-bubble ${isUser ? 'bubble-user' : 'bubble-assistant'}`}>
          <p>{message.content}</p>
        </div>
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
