# ========== 📦 IMPORTS ==========

import os
from dotenv import load_dotenv
import openai
from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import (
    PyPDFLoader, TextLoader, Docx2txtLoader, UnstructuredMarkdownLoader,
    UnstructuredHTMLLoader, UnstructuredXMLLoader, JSONLoader, CSVLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.messages import HumanMessage, AIMessage
from tqdm import tqdm

# ========== 🔐 CONFIGURATION API ==========

load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')
llm_name = "gpt-3.5-turbo"

model = ChatOpenAI(api_key=openai.api_key, model=llm_name)
embedding = OpenAIEmbeddings(openai_api_key=openai.api_key)

# ========== 🧠 LANGGRAPH STATE ==========

class State(TypedDict):
    messages: Annotated[list, add_messages]
    context: str
    has_docs: Literal["yes", "no"]

# ========== TOOLS ==========

def classify_intent(message: str) -> str:
    prompt = f"""
Tu es un classifieur d’intention.

Voici un message utilisateur :
"{message}"

Catégorise-le dans une des classes suivantes :
- playbook_writing
- question
- autre

Réponds uniquement par l’un des trois mots : playbook_writing, question, autre.
"""
    response = model.invoke(prompt)
    label = response.content.strip().lower()
    return label


# ========== 🧩 NODES ==========

def retriever_node(state: State) -> State:
    user_input = state["messages"][-1].content
    docs = retriever.invoke(user_input)
    context = "\n\n".join([doc.page_content for doc in docs])
    has_docs = "yes" if len(context.strip()) > 100 else "no"

    return {
        "messages": state["messages"],
        "context": context,
        "has_docs": has_docs,
    }

def rag_node(state: State) -> State:
    user_input = state["messages"][-1].content
    prompt = f"""Voici des extraits de documents :
{state['context']}

En te basant uniquement sur ces extraits, réponds à cette question :
{user_input}
"""
    response = model.invoke(prompt)
    return {"messages": state["messages"] + [AIMessage(content=response.content)]}

def llm_direct_node(state: State) -> State:
    user_input = state["messages"][-1].content
    response = model.invoke(user_input)
    return {"messages": state["messages"] + [AIMessage(content=response.content)]}

def router(state: State) -> str:
    user_input = state["messages"][-1].content
    intent = classify_intent(user_input)

    print(f"🎯 Intention détectée : {intent}")

    if intent == "playbook_writing":
        return "playbook_generator"
    elif intent == "question":
        return "rag_node" if state.get("has_docs") == "yes" else "llm_direct_node"
    else:
        return "llm_direct_node"
    

def playbook_generator(state: State) -> State:
    user_input = state["messages"][-1].content

    prompt = f"""Voici des extraits de documents :
{state['context']}
Tu es un assistant expert en cybersécurité chargé de créer un playbook automatisé.

En te basant uniquement sur ces extraits et de la demande suivante de l'utilisateur, 
génère un playbook clair en te basant sur 
les instructions pour créer un playbook qui sont dans le fichier "instructions_to_create_a_playbook.txt

                Demande de l'utilisateur :
                \"\"\"{user_input}\"\"\"

                Il faut que tu répondes en écrivant juste le playbook
            
"""
    response = model.invoke(prompt)
    return {"messages": state["messages"] + [AIMessage(content=response.content)]}




# ========== 📂 CHARGEMENT DES DOCUMENTS ==========

def load_all_documents(folder_path):
    docs = []
    for file in os.listdir(folder_path):
        path = os.path.join(folder_path, file)
        try:
            if file.endswith(".pdf"):
                docs.extend(PyPDFLoader(path).load())
            elif file.endswith(".txt"):
                docs.extend(TextLoader(path).load())
            elif file.endswith(".docx"):
                docs.extend(Docx2txtLoader(path).load())
            elif file.endswith(".md"):
                try:
                    docs.extend(UnstructuredMarkdownLoader(path).load())
                except Exception as e:
                    print(f"⚠️ MarkdownLoader échoué, fallback TextLoader : {e}")
                    docs.extend(TextLoader(path).load())
            elif file.endswith(".html") or file.endswith(".htm"):
                docs.extend(UnstructuredHTMLLoader(path).load())
            elif file.endswith(".xml"):
                docs.extend(UnstructuredXMLLoader(path).load())
            elif file.endswith(".json"):
                loader = JSONLoader(path, jq_schema=".", text_content=False)
                data = loader.load()
                for d in data:
                    d.page_content = str(d.page_content)
                docs.extend(data)
            elif file.endswith(".csv"):
                docs.extend(CSVLoader(file_path=path).load())
        except Exception as e:
            print(f"⚠️ Erreur en chargeant {file} : {e}")
    return docs

# ========== 🧠 VECTORIZER FAISS ==========

def build_faiss_vectorstore(docs, embedding, batch_size=100):
    vectorstore = None
    for i in tqdm(range(0, len(docs), batch_size), desc="🔄 Embedding batches"):
        batch = docs[i:i+batch_size]
        if not batch:
            continue
        if vectorstore is None:
            vectorstore = FAISS.from_documents(batch, embedding)
        else:
            vectorstore.add_documents(batch)
    return vectorstore

# ========== 📦 CHARGEMENT / PERSISTENCE FAISS ==========

faiss_index_path = "faiss_index"

if os.path.exists(faiss_index_path):
    print("✅ Index FAISS existant détecté. Chargement...")
    vectordb = FAISS.load_local(
        faiss_index_path,
        embedding,
        allow_dangerous_deserialization=True
    )
else:
    print("📂 Chargement des documents...")
    documents = load_all_documents("docs")

    print("✂️ Découpage en chunks...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = text_splitter.split_documents(documents)

    print("🔎 Vectorisation (embedding + index FAISS)...")
    vectordb = build_faiss_vectorstore(split_docs, embedding)

    print("💾 Sauvegarde de l’index FAISS...")
    vectordb.save_local(faiss_index_path)

retriever = vectordb.as_retriever()

# ========== 🔁 LANGGRAPH SETUP ==========

graph_builder = StateGraph(State)
graph_builder.add_node("retriever", retriever_node)
graph_builder.add_node("rag_node", rag_node)
graph_builder.add_node("llm_direct_node", llm_direct_node)
graph_builder.add_node("playbook_generator", playbook_generator)
graph_builder.add_conditional_edges(
    "retriever",
    router,
    {
        "rag_node": "rag_node",
        "llm_direct_node": "llm_direct_node",
        "playbook_generator": "playbook_generator",
    }
)
graph_builder.set_entry_point("retriever")
graph_builder.set_finish_point("rag_node")
graph_builder.set_finish_point("llm_direct_node")
graph_builder.set_finish_point("playbook_generator")


graph = graph_builder.compile()

# ========== 🎨 GÉNÉRATION AUTO DE L’IMAGE DU GRAPHE (sans dépendance) ==========

try:
    png_bytes = graph.get_graph().draw_mermaid_png()  # génère un PNG en mémoire
    with open("langgraph.png", "wb") as f:
        f.write(png_bytes)
    print("✅ Graphe exporté: langgraph.png")
except Exception as e:
    print(f"⚠️ Génération du graphe échouée: {e}")
    # Affichage de secours en ASCII dans la console
    try:
        graph.get_graph().print_ascii()
    except Exception:
        pass

# ========== 💬 INTERACTION UTILISATEUR ==========

while True:
    user_input = input("User: ")
    if user_input.lower() in ["exit", "quit", "q"]:
        print("Goodbye!")
        break

    state = {"messages": [HumanMessage(content=user_input)]}
    for event in graph.stream(state):
        for step in event.values():
            final_msg = step["messages"][-1]
            print(f"{final_msg.__class__.__name__}: {final_msg.content}")
