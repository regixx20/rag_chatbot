import { useEffect, useMemo, useState } from 'react'
import ChatWindow from './components/ChatWindow'
import UploadPanel from './components/UploadPanel'

const DEFAULT_API_BASE = 'http://localhost:8000/api'

export default function App() {
  const [apiBase] = useState(() => import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE)
  const [documents, setDocuments] = useState([])
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${apiBase}/documents/`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data) => {
        if (Array.isArray(data?.results)) {
          setDocuments(data.results.map((doc) => doc.original_name || doc.file))
        } else if (Array.isArray(data)) {
          setDocuments(data.map((doc) => doc.original_name || doc.file))
        }
      })
      .catch(() => {})
    return () => controller.abort()
  }, [apiBase, refreshKey])

  const handleUploadComplete = useMemo(
    () => (ingested) => {
      setRefreshKey((key) => key + 1)
      if (Array.isArray(ingested) && ingested.length > 0) {
        setDocuments((prev) => [...ingested, ...prev])
      }
    },
    []
  )

  return (
    <div className="app-container">
      <header>
        <h1>RAG Chatbot</h1>
        <p>Discutez avec votre IA et enrichissez-la avec vos propres documents.</p>
      </header>
      <main>
        <section className="chat-section">
          <ChatWindow apiBase={apiBase} refreshKey={refreshKey} />
        </section>
        <section className="sidebar">
          <UploadPanel apiBase={apiBase} onUploadComplete={handleUploadComplete} />
          <div className="document-list">
            <h2>Documents ingérés</h2>
            {documents.length === 0 ? (
              <p className="empty">Aucun document ingéré pour le moment.</p>
            ) : (
              <ul>
                {documents.map((doc) => (
                  <li key={doc}>{doc}</li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </main>
    </div>
  )
}
