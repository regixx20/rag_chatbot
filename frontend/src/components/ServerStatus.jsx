import { useEffect, useState } from 'react'
import { Button } from './ui/Button'
import { AlertIcon } from './icons'

export function ServerStatus({ state, onRetry }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (state !== 'waking') return undefined
    setElapsed(0)
    const timer = setInterval(() => setElapsed((seconds) => seconds + 1), 1000)
    return () => clearInterval(timer)
  }, [state])

  if (state === 'online') return null

  if (state === 'offline') {
    return (
      <div className="server-status server-status-offline" role="alert">
        <AlertIcon aria-hidden="true" />
        <p>Le serveur ne répond pas pour le moment.</p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          Réessayer
        </Button>
      </div>
    )
  }

  return (
    <div className="server-status server-status-waking" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>
        Démarrage du serveur…
        {elapsed >= 4 && (
          <span className="server-status-hint">
            {' '}
            Il est hébergé gratuitement et se met en veille : le réveil peut prendre jusqu'à une
            minute ({elapsed} s).
          </span>
        )}
      </p>
    </div>
  )
}
