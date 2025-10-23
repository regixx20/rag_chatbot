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
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    setMessages([])
  }, [refreshKey])

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
        body: JSON.stringify({ message: input })
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

  return (
    <div className="chat-window">
      <div className="messages">
        {messages.map((message, index) => (
          <Message key={`${message.author}-${index}`} {...message} />
        ))}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={handleSubmit} className="chat-form">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Posez votre question..."
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Envoi...' : 'Envoyer'}
        </button>
      </form>
    </div>
  )
}
