"""Simple CLI entry point for the RAG chatbot engine (questions the demo documents)."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from backend.ragchat.chatbot import get_engine  # noqa: E402  (needs the env loaded first)


def main() -> None:
    engine = get_engine()
    history: list[dict[str, str]] = []
    print("RAG Chatbot CLI prêt. Tapez 'quit' pour sortir.")
    while True:
        user_input = input("Vous: ").strip()
        if user_input.lower() in {"quit", "exit", "q"}:
            print("À bientôt !")
            break
        if not user_input:
            continue
        answer, intent, sources = engine.chat(user_input, mode="rag", history=history)
        print(f"Mode : {intent}")
        for source in sources:
            page = f", page {source.page}" if source.page else ""
            print(f" [{source.number}] {source.document}{page} (score {source.score:.2f})")
        print(f"Assistant: {answer}\n")
        history += [{"role": "user", "content": user_input}, {"role": "assistant", "content": answer}]


if __name__ == "__main__":
    main()
