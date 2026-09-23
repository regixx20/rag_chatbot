import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Badge } from './ui/Badge'
import { ScrollArea } from './ui/ScrollArea'
import { UploadIcon, FileTextIcon, CloseIcon, FileIcon } from './icons'

function getFileIcon(type = '') {
  const normalised = type.toLowerCase()
  if (['pdf', 'docx', 'txt', 'md'].some((ext) => normalised.includes(ext))) return FileTextIcon
  return FileIcon
}

export function DocumentPanel({
  documents,
  isRagEnabled,
  isUploading,
  canUpload,
  onUpload,
  onDelete,
  onClose,
}) {
  return (
    <aside className="document-panel" aria-label="Documents RAG">
      <div className="document-header">
        <div>
          <h2>Documents RAG</h2>
          <p>Ajoutez vos sources pour enrichir les réponses.</p>
        </div>
        <Badge variant="outline" className="document-count">
          {documents.length}
        </Badge>
        <Button
          variant="ghost"
          size="sm"
          className="document-panel-close"
          onClick={onClose}
          aria-label="Fermer le panneau des documents"
        >
          <CloseIcon />
        </Button>
      </div>

      <Button className="document-upload" onClick={onUpload} disabled={!canUpload || isUploading}>
        {isUploading ? <span className="spinner spinner-light" aria-hidden="true" /> : <UploadIcon />}
        <span>{isUploading ? 'Analyse en cours…' : 'Ajouter des documents'}</span>
      </Button>
      <p className="document-formats">PDF, DOCX, TXT, Markdown, HTML, CSV, JSON, XML</p>

      <ScrollArea className="document-list">
        {documents.length === 0 ? (
          <div className="document-empty">
            <FileTextIcon />
            <p>Aucun document</p>
            <span>Ajoutez un fichier : le mode RAG s'activera automatiquement.</span>
          </div>
        ) : (
          documents.map((doc) => {
            const Icon = getFileIcon(doc.type || doc.name)
            return (
              <Card key={doc.id} className="document-card">
                <div className="document-icon">
                  <Icon />
                </div>
                <div className="document-info">
                  <p className="document-name" title={doc.name}>
                    {doc.name}
                  </p>
                  <div className="document-meta">
                    <span>{doc.type ? doc.type.toUpperCase() : 'Fichier'}</span>
                    <span>•</span>
                    <span>{new Date(doc.uploadedAt).toLocaleDateString('fr-FR')}</span>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="document-delete"
                  onClick={() => onDelete?.(doc.id)}
                  aria-label={`Supprimer ${doc.name}`}
                >
                  <CloseIcon />
                </Button>
              </Card>
            )
          })
        )}
      </ScrollArea>

      {documents.length > 0 && (
        <div className="document-footer">
          {isRagEnabled
            ? 'Ces documents sont utilisés pour répondre.'
            : 'Activez le mode RAG pour utiliser ces documents.'}
        </div>
      )}
    </aside>
  )
}
