"""Simple CLI entry point for the RAG chatbot engine."""
from __future__ import annotations

from backend.ragchat.chatbot import get_engine
from dotenv import load_dotenv
load_dotenv()  


def main() -> None:
    engine = get_engine()
    print("RAG Chatbot CLI prêt. Tapez 'quit' pour sortir.")
    while True:
        user_input = input("Vous: ")
        if user_input.lower().strip() in {"quit", "exit", "q"}:
            print("À bientôt !")
            break
        answer, intent, sources = engine.chat(user_input)
        print(f"Intent détecté: {intent}")
        if sources:
            print("Documents utilisés:")
            for source in sources:
                print(f" - {source}")
        print(f"Assistant: {answer}\n")


if __name__ == "__main__":
    main()
