import { useState } from 'react'

export default function UploadPanel({ apiBase, onUploadComplete }) {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!file) {
      setStatus('Sélectionnez au moins un fichier.')
      return
    }

    const formData = new FormData()
    formData.append('file', file)

    setLoading(true)
    setStatus('Téléversement en cours...')

    try {
      const response = await fetch(`${apiBase}/documents/`, {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        throw new Error('Erreur de téléversement')
      }

      const data = await response.json()
      const ingestedSources = [data.original_name || data.file]
      onUploadComplete?.(ingestedSources)
      setStatus('Document téléversé et ingéré avec succès !')
      setFile(null)
    } catch (error) {
      console.error(error)
      setStatus("Impossible de téléverser le fichier. Consultez la console.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="upload-panel">
      <h2>Ajouter des documents</h2>
      <form onSubmit={handleSubmit}>
        <input
          type="file"
          onChange={(event) => setFile(event.target.files?.[0] || null)}
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Chargement...' : 'Téléverser'}
        </button>
      </form>
      {status && <p className="status">{status}</p>}
    </div>
  )
}
