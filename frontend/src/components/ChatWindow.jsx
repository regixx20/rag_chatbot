import { useEffect, useRef, useState } from 'react'

function Message({ author, content }) {
  return (
    <div className={`message ${author}`}>
      <strong>{author === 'user' ? 'Vous' : 'Assistant'}</strong>
      <p>{content}</p>
    </div>
  )
}

export default function ChatWindow({ apiBase, refreshKey }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState('direct')
  const [showModeMenu, setShowModeMenu] = useState(false)
  const bottomRef = useRef(null)
  const modeSelectorRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    setMessages([])
  }, [refreshKey])

  useEffect(() => {
    if (!showModeMenu) return

    const handleClickOutside = (event) => {
      if (modeSelectorRef.current?.contains(event.target)) return
      setShowModeMenu(false)
    }

    document.addEventListener('mousedown', handleClickOutside)

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showModeMenu])

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!input.trim()) return

    const newMessages = [...messages, { author: 'user', content: input }]
    setMessages(newMessages)
    setInput('')
    setLoading(true)

    try {
      const response = await fetch(`${apiBase}/chat/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input, mode })
      })

      if (!response.ok) {
        throw new Error('La requête a échoué')
      }

      const data = await response.json()
      setMessages((prev) => [
        ...prev,
        { author: 'assistant', content: data.response }
      ])
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { author: 'assistant', content: "Une erreur est survenue. Vérifiez l'API." }
      ])
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  const handleModeChange = (nextMode) => {
    setMode(nextMode)
    setShowModeMenu(false)
  }

  const clearMode = () => {
    setMode('direct')
    setShowModeMenu(false)
  }

  const modeLabel = mode === 'rag' ? 'Mode RAG' : 'Mode Libre'

  return (
    <div className="chat-window">
      <div className="messages">
        {messages.map((message, index) => (
          <Message key={`${message.author}-${index}`} {...message} />
        ))}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={handleSubmit} className="chat-form">
        <div className="input-wrapper">
          {mode === 'rag' && (
            <span className="mode-chip">
              {modeLabel}
              <button
                type="button"
                onClick={clearMode}
                aria-label="Désactiver le mode RAG"
                disabled={loading}
              >
                ×
              </button>
            </span>
          )}
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Posez votre question..."
            disabled={loading}
          />
          <div className="mode-selector" ref={modeSelectorRef}>
            <button
              type="button"
              className="mode-button"
              onClick={() => setShowModeMenu((open) => !open)}
              aria-haspopup="menu"
              aria-expanded={showModeMenu}
              aria-label="Choisir le mode de réponse"
              disabled={loading}
            >
              +
            </button>
            {showModeMenu && (
              <div className="mode-menu" role="menu">
                <button
                  type="button"
                  onClick={() => handleModeChange('rag')}
                  className={mode === 'rag' ? 'active' : ''}
                  role="menuitemradio"
                  aria-checked={mode === 'rag'}
                  disabled={loading}
                >
                  Mode RAG
                </button>
                <button
                  type="button"
                  onClick={() => handleModeChange('direct')}
                  className={mode === 'direct' ? 'active' : ''}
                  role="menuitemradio"
                  aria-checked={mode === 'direct'}
                  disabled={loading}
                >
                  Mode Libre
                </button>
              </div>
            )}
          </div>
        </div>
        <button type="submit" disabled={loading}>
          {loading ? 'Envoi...' : 'Envoyer'}
        </button>
      </form>
    </div>
  )
}
