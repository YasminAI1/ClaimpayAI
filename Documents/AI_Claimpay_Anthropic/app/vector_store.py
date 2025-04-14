# app/vector_store.py
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Dict, Any
from datetime import datetime
import logging
from .encryption import DataEncryption

class EnhancedVectorStore:
    def __init__(self, encryption_manager: DataEncryption):
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2",
            model_kwargs={'device': 'cpu'}
        )
        self.vector_store = None
        self.encryption = encryption_manager
        self.cache = {}
    def create_vector_store(self, documents: List[str], table_name: str):
        """Create and persist vector store with encryption"""
        try:
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50,
                separators=["\n\n", "\n", ". ", ", ", " ", ""]
            )
            
            # Encrypt documents before processing
            encrypted_docs = []
            for doc in documents:
                doc_hash = self.encryption.hash_value(doc)
                encrypted_text = self.encryption.encrypt_text(doc)
                self.cache[doc_hash] = encrypted_text
                encrypted_docs.append(doc)
                
            texts = text_splitter.create_documents(encrypted_docs)
            
            # Create FAISS index
            self.vector_store = FAISS.from_documents(
                texts,
                self.embeddings,
            )
            
            # Save index with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            index_path = f"vector_store_{table_name}_{timestamp}"
            self.vector_store.save_local(index_path)
            
        except Exception as e:
            logging.error(f"Error creating vector store: {str(e)}")
            raise

    def query(self, question: str, k: int = 3) -> List[Dict[str, Any]]:
        """Query the vector store with encryption handling"""
        if not self.vector_store:
            raise ValueError("Vector store not initialized")
            
        try:
            # Encrypt query for consistency
            encrypted_question = self.encryption.encrypt_text(question)
            
            # Get similar documents
            docs = self.vector_store.similarity_search(
                question,
                k=k,
                fetch_k=10
            )
            
            # Decrypt results
            decrypted_results = []
            for doc in docs:
                doc_hash = self.encryption.hash_value(doc.page_content)
                if doc_hash in self.cache:
                    decrypted_text = self.encryption.decrypt_text(self.cache[doc_hash])
                    decrypted_results.append({
                        'content': decrypted_text,
                        'metadata': doc.metadata
                    })
                    
            return decrypted_results
                
        except Exception as e:
            logging.error(f"Error querying vector store: {str(e)}")
            raise