import {
  FileText,
  FileSpreadsheet,
  FileCode,
  File,
  Loader2,
  Moon,
  Plus,
  SquarePen,
  Sun,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { Logo } from './Logo'

function GithubIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.52-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.56-.29-5.25-1.28-5.25-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.7 5.39-5.27 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z" />
    </svg>
  )
}

const EXTENSION_ICONS = {
  pdf: FileText,
  docx: FileText,
  txt: FileText,
  md: FileText,
  csv: FileSpreadsheet,
  json: FileCode,
  xml: FileCode,
  html: FileCode,
  htm: FileCode,
}

const SERVER_LABELS = {
  online: 'Serveur connecté',
  waking: 'Démarrage du serveur…',
  offline: 'Serveur injoignable',
}

const prettyName = (name) => name.replace(/\.[a-z0-9]+$/i, '').replace(/[_-]+/g, ' ')

export function Sidebar({
  documents,
  serverState,
  isUploading,
  theme,
  onToggleTheme,
  onNewConversation,
  onUpload,
  onDelete,
  onRetryServer,
  onClose,
}) {
  const canUpload = serverState === 'online' && !isUploading

  return (
    <aside className="sidebar" aria-label="Base de connaissances">
      <div className="sidebar-head">
        <div className="brand">
          <Logo />
          <span className="brand-name">Assistant RAG</span>
        </div>
        <button className="icon-button sidebar-close" onClick={onClose} aria-label="Fermer le menu">
          <X size={18} />
        </button>
      </div>

      <button className="new-chat" onClick={onNewConversation}>
        <SquarePen size={17} />
        Nouvelle conversation
      </button>

      <section className="kb">
        <div className="kb-head">
          <h2>Base de connaissances</h2>
          <span className="kb-count">{documents.length}</span>
        </div>

        <button className="dropzone" onClick={onUpload} disabled={!canUpload}>
          {isUploading ? <Loader2 size={18} className="spin" /> : <Upload size={18} />}
          <span className="dropzone-title">{isUploading ? 'Analyse en cours…' : 'Ajouter des documents'}</span>
          <span className="dropzone-hint">PDF, DOCX, TXT… · 10 Mo max</span>
        </button>

        <ul className="doc-list">
          {documents.map((doc) => {
            const Icon = EXTENSION_ICONS[doc.extension] ?? File
            return (
              <li key={doc.id} className="doc-item" title={doc.name}>
                <span className={`doc-icon doc-icon-${doc.extension || 'file'}`}>
                  <Icon size={16} />
                </span>
                <span className="doc-text">
                  <span className="doc-name">{prettyName(doc.name)}</span>
                  <span className="doc-meta">
                    {doc.extension.toUpperCase()}
                    {doc.isDemo ? ' · Document de démo' : ' · Ajouté par vous'}
                  </span>
                </span>
                {!doc.isDemo && (
                  <button
                    className="icon-button doc-delete"
                    onClick={() => onDelete(doc)}
                    aria-label={`Supprimer ${doc.name}`}
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </li>
            )
          })}
          {documents.length === 0 && serverState === 'online' && (
            <li className="doc-empty">
              <Plus size={16} /> Aucun document pour l'instant
            </li>
          )}
        </ul>

        <p className="kb-note">Vos fichiers ne sont visibles que par vous et sont effacés après 24 h.</p>
      </section>

      <div className="sidebar-foot">
        <button
          className={`server-pill server-${serverState}`}
          onClick={serverState === 'offline' ? onRetryServer : undefined}
          title={serverState === 'offline' ? 'Réessayer' : undefined}
        >
          <span className="server-dot" />
          {SERVER_LABELS[serverState]}
        </button>
        <div className="foot-actions">
          <a
            className="icon-button"
            href="https://github.com/regixx20/rag_chatbot"
            target="_blank"
            rel="noreferrer"
            aria-label="Code source sur GitHub"
          >
            <GithubIcon />
          </a>
          <button
            className="icon-button"
            onClick={onToggleTheme}
            aria-label={theme === 'dark' ? 'Passer en thème clair' : 'Passer en thème sombre'}
          >
            {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </div>
      </div>
    </aside>
  )
}
