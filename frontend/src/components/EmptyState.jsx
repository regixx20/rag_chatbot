import { ArrowUpRight, Baby, Copyright, Gavel, Lightbulb, Scale, Sparkles, UserX } from 'lucide-react'
import { Logo } from './Logo'

const DEMO_QUESTIONS = [
  { icon: Copyright, text: 'TikTok peut-il réutiliser mes vidéos ?' },
  { icon: Baby, text: 'À partir de quel âge peut-on créer un compte ?' },
  { icon: Gavel, text: 'Comment sont réglés les litiges avec TikTok ?' },
  { icon: UserX, text: 'Dans quels cas mon compte peut-il être suspendu ?' },
]

const GENERAL_QUESTIONS = [
  { icon: Lightbulb, text: "Explique-moi le RAG comme si j'avais 12 ans" },
  { icon: Scale, text: 'RAG ou fine-tuning : lequel choisir et quand ?' },
  { icon: Sparkles, text: "C'est quoi un embedding, concrètement ?" },
  { icon: ArrowUpRight, text: 'Donne-moi 3 idées de projets avec un LLM' },
]

export function EmptyState({ isRagEnabled, documents, disabled, onPick }) {
  const ownDocuments = documents.filter((doc) => !doc.isDemo)
  const questions = isRagEnabled && ownDocuments.length === 0 ? DEMO_QUESTIONS : GENERAL_QUESTIONS

  return (
    <div className="empty">
      <Logo size={44} />
      <h1 className="empty-title">
        {isRagEnabled ? 'Interrogez vos documents' : 'Que voulez-vous savoir ?'}
      </h1>
      <p className="empty-subtitle">
        {isRagEnabled ? (
          ownDocuments.length > 0 ? (
            <>Les réponses s'appuient sur vos {documents.length} documents, avec leurs sources.</>
          ) : (
            <>
              Un document de démo est prêt : les <strong>conditions d'utilisation de TikTok</strong>. Posez
              une question, ou ajoutez vos propres fichiers.
            </>
          )
        ) : (
          <>Mode modèle seul : les réponses viennent des connaissances générales du modèle.</>
        )}
      </p>

      {!(isRagEnabled && ownDocuments.length > 0) && (
        <div className="suggestions">
          {questions.map(({ icon: Icon, text }) => (
            <button key={text} className="suggestion" onClick={() => onPick(text)} disabled={disabled}>
              <Icon size={17} className="suggestion-icon" />
              <span>{text}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
