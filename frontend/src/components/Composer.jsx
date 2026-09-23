import { forwardRef, useLayoutEffect, useRef, useState, useImperativeHandle } from 'react'
import { ArrowUp, BookOpen, Loader2, Paperclip, Sparkles } from 'lucide-react'

const MAX_HEIGHT = 220

export const Composer = forwardRef(function Composer(
  {
    serverState,
    isRagEnabled,
    onToggleRag,
    documentCount,
    isBusy,
    isUploading,
    onSend,
    onAttach,
    onRetryServer,
  },
  ref
) {
  const [value, setValue] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const textareaRef = useRef(null)
  const isOnline = serverState === 'online'
  const canSend = isOnline && !isBusy && value.trim().length > 0

  useImperativeHandle(ref, () => ({ focus: () => textareaRef.current?.focus() }))

  useLayoutEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_HEIGHT)}px`
  }, [value])

  // Seconds counter shown while the free-tier server boots
  useLayoutEffect(() => {
    if (serverState !== 'waking') return undefined
    setElapsed(0)
    const timer = setInterval(() => setElapsed((seconds) => seconds + 1), 1000)
    return () => clearInterval(timer)
  }, [serverState])

  const submit = () => {
    if (!canSend) return
    onSend(value)
    setValue('')
  }

  return (
    <div className="composer-wrap">
      {serverState === 'waking' && (
        <div className="server-banner">
          <Loader2 size={15} className="spin" />
          <span>
            Démarrage du serveur{elapsed >= 3 ? ` (${elapsed} s)` : ''}…
            {elapsed >= 3 && (
              <span className="server-banner-hint">
                {' '}
                Hébergé gratuitement, il se met en veille : le réveil peut prendre jusqu'à une minute.
              </span>
            )}
          </span>
        </div>
      )}
      {serverState === 'offline' && (
        <div className="server-banner server-banner-error">
          <span>Le serveur ne répond pas pour le moment.</span>
          <button className="button-ghost" onClick={onRetryServer}>
            Réessayer
          </button>
        </div>
      )}

      <div className={`composer ${isOnline ? '' : 'is-disabled'}`}>
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              submit()
            }
          }}
          placeholder={isRagEnabled ? 'Posez une question sur vos documents…' : 'Posez votre question…'}
          aria-label="Votre message"
        />

        <div className="composer-bar">
          <button
            className="icon-button"
            onClick={onAttach}
            disabled={!isOnline || isUploading}
            aria-label="Ajouter un document"
            title="Ajouter un document"
          >
            {isUploading ? <Loader2 size={18} className="spin" /> : <Paperclip size={18} />}
          </button>

          <div className="mode-switch" role="radiogroup" aria-label="Source des réponses">
            <button
              role="radio"
              aria-checked={isRagEnabled}
              className={isRagEnabled ? 'is-active' : ''}
              onClick={() => onToggleRag(true)}
            >
              <BookOpen size={14} />
              Documents
              <span className="mode-count">{documentCount}</span>
            </button>
            <button
              role="radio"
              aria-checked={!isRagEnabled}
              className={!isRagEnabled ? 'is-active' : ''}
              onClick={() => onToggleRag(false)}
            >
              <Sparkles size={14} />
              Modèle seul
            </button>
          </div>

          <button className="send-button" onClick={submit} disabled={!canSend} aria-label="Envoyer">
            {isBusy ? <Loader2 size={18} className="spin" /> : <ArrowUp size={18} strokeWidth={2.4} />}
          </button>
        </div>
      </div>
      <p className="composer-note">
        Les réponses peuvent contenir des erreurs : vérifiez les sources citées.
      </p>
    </div>
  )
})
