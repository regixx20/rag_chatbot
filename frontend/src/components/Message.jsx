import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { AlertCircle, BookOpen, Brain, Check, Copy, FileText, RotateCcw, SearchX } from 'lucide-react'
import { Logo } from './Logo'

const documentName = (source) => source.document.replace(/\.[a-z0-9]+$/i, '').replace(/[_-]+/g, ' ')

// "[1]", "[1][2]" and "[1, 2]" become links the markdown renderer turns into citation chips
function linkCitations(text) {
  return text.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_, numbers) =>
    numbers
      .split(',')
      .map((n) => `[${n.trim()}](#cite-${n.trim()})`)
      .join('')
  )
}

function SourceCard({ source, isActive, onSelect }) {
  return (
    <button className={`source-card ${isActive ? 'is-active' : ''}`} onClick={onSelect} aria-pressed={isActive}>
      <span className="source-card-top">
        <span className="source-number">{source.number}</span>
        <span className="source-doc">{documentName(source)}</span>
      </span>
      <span className="source-excerpt">{source.excerpt}</span>
      <span className="source-meta">
        <FileText size={12} />
        {source.page ? `Page ${source.page}` : 'Extrait'}
        <span className="source-score" title="Similarité avec la question">
          {Math.round(source.score * 100)} %
        </span>
      </span>
    </button>
  )
}

function AssistantStatus({ message }) {
  if (message.status === 'searching') {
    return (
      <p className="thinking">
        <span className="thinking-dot" />
        {message.mode === 'rag' ? 'Recherche dans vos documents…' : 'Réflexion…'}
      </p>
    )
  }
  return null
}

export function Message({ message, onRetry }) {
  const [activeSource, setActiveSource] = useState(null)
  const [copied, setCopied] = useState(false)

  if (message.role === 'user') {
    return (
      <div className="msg msg-user">
        <div className="user-bubble">{message.content}</div>
      </div>
    )
  }

  if (message.status === 'error') {
    return (
      <div className="msg msg-assistant">
        <div className="msg-avatar msg-avatar-error">
          <AlertCircle size={16} />
        </div>
        <div className="msg-body">
          <div className="error-box">
            <p>{message.content}</p>
            {message.retryContent && (
              <button className="button-ghost" onClick={() => onRetry(message)}>
                <RotateCcw size={14} /> Réessayer
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  const sources = message.sources ?? []
  const selected = sources.find((source) => source.number === activeSource)
  const isStreaming = message.status === 'writing'
  const isDone = message.status === 'done'

  const markdownComponents = {
    a: ({ node, href, children, ...props }) => {
      if (href?.startsWith('#cite-')) {
        const number = Number(href.slice(6))
        const source = sources.find((entry) => entry.number === number)
        if (!source) return <span>[{number}]</span>
        return (
          <button
            className={`cite ${activeSource === number ? 'is-active' : ''}`}
            onClick={() => setActiveSource(activeSource === number ? null : number)}
            title={`${documentName(source)}${source.page ? `, page ${source.page}` : ''}`}
          >
            {number}
          </button>
        )
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" {...props}>
          {children}
        </a>
      )
    },
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard unavailable (insecure context): nothing to do
    }
  }

  return (
    <div className="msg msg-assistant">
      <div className="msg-avatar">
        <Logo size={28} />
      </div>
      <div className="msg-body">
        <AssistantStatus message={message} />

        {sources.length > 0 && (
          <section className="sources" aria-label="Sources">
            <h3 className="sources-title">
              <BookOpen size={14} /> Sources
            </h3>
            <div className="source-grid">
              {sources.map((source) => (
                <SourceCard
                  key={source.number}
                  source={source}
                  isActive={activeSource === source.number}
                  onSelect={() => setActiveSource(activeSource === source.number ? null : source.number)}
                />
              ))}
            </div>
          </section>
        )}

        {message.content && (
          <div className={`answer ${isStreaming ? 'is-streaming' : ''}`}>
            <ReactMarkdown components={markdownComponents}>{linkCitations(message.content)}</ReactMarkdown>
          </div>
        )}

        {selected && (
          <blockquote className="source-detail">
            <header>
              <span className="source-number">{selected.number}</span>
              {documentName(selected)}
              {selected.page && <span className="source-detail-page">· page {selected.page}</span>}
            </header>
            <p>{selected.excerpt}</p>
          </blockquote>
        )}

        {isDone && (
          <div className="msg-actions">
            <button className="icon-button" onClick={copy} aria-label="Copier la réponse" title="Copier">
              {copied ? <Check size={15} /> : <Copy size={15} />}
            </button>
            <span className="msg-tag">
              {message.intent === 'Rag' && (
                <>
                  <BookOpen size={13} /> Basé sur {sources.length} extrait{sources.length > 1 ? 's' : ''}
                </>
              )}
              {message.intent === 'NoContext' && (
                <>
                  <SearchX size={13} /> Aucun passage pertinent dans les documents
                </>
              )}
              {message.intent === 'Direct' && (
                <>
                  <Brain size={13} /> Connaissances générales du modèle
                </>
              )}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
