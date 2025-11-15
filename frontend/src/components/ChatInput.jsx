import { useState } from 'react'
import { Button } from './ui/Button'
import { Textarea } from './ui/Textarea'
import { PaperclipIcon, SendIcon } from './icons'

export function ChatInput({ onSend, disabled = false }) {
  const [message, setMessage] = useState('')

  const handleSend = () => {
    const trimmed = message.trim()
    if (!trimmed || disabled) return
    onSend?.(trimmed)
    setMessage('')
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-input-bar">
      <div className="chat-input-editor">
        <Textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Posez votre question..."
          disabled={disabled}
        />
        <Button
          variant="ghost"
          size="sm"
          className="chat-input-attach"
          disabled={disabled}
          aria-label="Joindre un fichier (non disponible)"
        >
          <PaperclipIcon />
        </Button>
      </div>
      <Button
        onClick={handleSend}
        disabled={disabled || !message.trim()}
        className="chat-input-send"
        aria-label="Envoyer le message"
      >
        <SendIcon />
      </Button>
    </div>
  )
}
