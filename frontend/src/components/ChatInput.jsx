import { useLayoutEffect, useRef, useState } from 'react'
import { Button } from './ui/Button'
import { Textarea } from './ui/Textarea'
import { PaperclipIcon, SendIcon } from './icons'

const MAX_HEIGHT = 200

export function ChatInput({ onSend, onAttach, canSend = true, canAttach = true, placeholder }) {
  const [message, setMessage] = useState('')
  const textareaRef = useRef(null)

  // Grow the textarea with its content, up to MAX_HEIGHT
  useLayoutEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_HEIGHT)}px`
  }, [message])

  const handleSend = () => {
    const trimmed = message.trim()
    if (!trimmed || !canSend) return
    onSend?.(trimmed)
    setMessage('')
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-input-bar">
      <div className="chat-input-editor">
        <Textarea
          ref={textareaRef}
          rows={1}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          aria-label="Votre message"
        />
        <Button
          variant="ghost"
          size="sm"
          className="chat-input-attach"
          onClick={onAttach}
          disabled={!canAttach}
          aria-label="Ajouter un document"
          title="Ajouter un document"
        >
          <PaperclipIcon />
        </Button>
      </div>
      <Button
        onClick={handleSend}
        disabled={!canSend || !message.trim()}
        className="chat-input-send"
        aria-label="Envoyer le message"
      >
        <SendIcon />
      </Button>
    </div>
  )
}
