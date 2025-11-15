import { useRef } from 'react'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Badge } from './ui/Badge'
import { ScrollArea } from './ui/ScrollArea'
import {
  UploadIcon,
  FileTextIcon,
  CloseIcon,
  FileIcon,
  ImageIcon,
  ArchiveIcon,
} from './icons'

function formatFileSize(bytes) {
  if (!bytes || Number.isNaN(bytes)) return 'Taille inconnue'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  return `${Math.round(size * 100) / 100} ${units[unitIndex]}`
}

function getFileIcon(type = '') {
  const normalised = type.toLowerCase()
  if (normalised.includes('pdf') || normalised.includes('doc')) return FileTextIcon
  if (normalised.includes('png') || normalised.includes('jpg') || normalised.includes('jpeg')) return ImageIcon
  if (normalised.includes('zip') || normalised.includes('rar')) return ArchiveIcon
  return FileIcon
}

export function DocumentPanel({ documents, isRagEnabled, onUpload, onDelete }) {
  const fileInputRef = useRef(null)

  const handleChange = (event) => {
    const files = event.target.files
    if (files && files.length > 0) {
      onUpload?.(files)
      event.target.value = ''
    }
  }

  return (
    <aside className="document-panel">
      <div className="document-header">
        <div>
          <h2>Documents RAG</h2>
          <p>Ajoutez vos sources pour enrichir l'IA.</p>
        </div>
        <Badge variant="outline" className="document-count">
          {documents.length}
        </Badge>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        className="document-input"
        onChange={handleChange}
        multiple
        accept=".pdf,.txt,.doc,.docx,.md,.png,.jpg,.jpeg,.zip"
      />

      {isRagEnabled ? (
        <Button className="document-upload" onClick={() => fileInputRef.current?.click()}>
          <UploadIcon />
          <span>Téléverser des documents</span>
        </Button>
      ) : (
        <div className="document-disabled">
          Activez le mode RAG pour téléverser des documents.
        </div>
      )}

      <ScrollArea className="document-list">
        {documents.length === 0 ? (
          <div className="document-empty">
            <FileTextIcon />
            <p>Aucun document ingéré</p>
            <span>
              {isRagEnabled
                ? 'Ajoutez des fichiers pour enrichir les réponses.'
                : 'Activez le mode RAG pour commencer.'}
            </span>
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
                    <span>{formatFileSize(doc.size)}</span>
                    <span>•</span>
                    <span>
                      {doc.uploadedAt
                        ? new Date(doc.uploadedAt).toLocaleDateString('fr-FR')
                        : 'Date inconnue'}
                    </span>
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

      {isRagEnabled && documents.length > 0 && (
        <div className="document-footer">Ces documents seront utilisés pour enrichir les réponses.</div>
      )}
    </aside>
  )
}
