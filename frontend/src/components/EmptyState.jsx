import { ArrowRight } from 'lucide-react'

const DEMO_QUESTIONS = [
  'Comment sont réglés les litiges avec TikTok ?',
  'Que se passe-t-il si je supprime mon compte ?',
  'Qui est propriétaire des vidéos que je publie ?',
  'Dans quels cas mon compte peut-il être suspendu ?',
]

const GENERAL_QUESTIONS = [
  "Explique-moi le RAG comme si j'avais 12 ans",
  'RAG ou fine-tuning : lequel choisir et quand ?',
  "C'est quoi un embedding, concrètement ?",
  'Donne-moi 3 idées de projets avec un LLM',
]

export function EmptyState({ isRagEnabled, documents, disabled, onPick }) {
  const ownDocuments = documents.filter((doc) => !doc.isDemo)
  const showDemo = isRagEnabled && ownDocuments.length === 0
  const questions = showDemo ? DEMO_QUESTIONS : GENERAL_QUESTIONS

  return (
    <div className="empty">
      <p className="empty-kicker">{isRagEnabled ? 'Recherche dans les documents' : 'Modèle seul'}</p>
      <h1 className="empty-title">
        {isRagEnabled ? 'Posez une question, obtenez la réponse et sa source.' : 'Posez votre question.'}
      </h1>
      <p className="empty-subtitle">
        {isRagEnabled ? (
          ownDocuments.length > 0 ? (
            <>Les réponses s'appuient sur vos {documents.length} documents et citent les passages utilisés.</>
          ) : (
            <>
              Un document est déjà chargé pour essayer : les{' '}
              <strong>conditions d'utilisation de TikTok</strong> (22 pages). Vous pouvez aussi ajouter vos
              propres fichiers.
            </>
          )
        ) : (
          <>Les réponses viennent des connaissances générales du modèle, sans consulter vos documents.</>
        )}
      </p>

      {!(isRagEnabled && ownDocuments.length > 0) && (
        <div className="suggestions">
          <p className="suggestions-label">{showDemo ? 'Exemples sur le document de démo' : 'Exemples'}</p>
          {questions.map((text) => (
            <button key={text} className="suggestion" onClick={() => onPick(text)} disabled={disabled}>
              <span>{text}</span>
              <ArrowRight size={16} className="suggestion-arrow" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
