# -*- coding: utf-8 -*-
import os
import hashlib
from typing import List, Dict, Any
import chromadb
from sentence_transformers import SentenceTransformer


class AileyRAG:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.collection_name = f"ailey_user_{hashlib.md5(user_id.encode()).hexdigest()[:12]}"

        self.chroma_path = "ailey_system/chromadb"
        os.makedirs(self.chroma_path, exist_ok=True)

        self.client = chromadb.PersistentClient(path=self.chroma_path)
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
        except Exception:
            self.collection = self.client.create_collection(name=self.collection_name, metadata={"user_id": user_id})

        # Lazy load embedder to avoid startup cost
        self._embedder = None

    def _embedder_get(self) -> SentenceTransformer:
        if self._embedder is None:
            # multilingual model as in HiHo
            self._embedder = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        return self._embedder

    def add_document(self, title: str, text: str, doc_type: str = "general") -> int:
        text = (text or "").strip()
        if not text:
            return 0
        # simple chunking by ~512 chars
        chunks: List[str] = []
        step = 512
        for i in range(0, len(text), step):
            chunks.append(text[i:i+step])
        ids = [f"{title}-{i:04d}" for i in range(len(chunks))]
        metas = [{"title": title, "doc_type": doc_type} for _ in chunks]

        # create embeddings
        embeddings = self._embedder_get().encode(chunks, convert_to_numpy=True).tolist()
        self.collection.add(ids=ids, documents=chunks, metadatas=metas, embeddings=embeddings)
        return len(chunks)

    def search(self, query: str, n_results: int = 5, threshold: float = 0.5) -> List[Dict[str, Any]]:
        if not query:
            return []
        res = self.collection.query(query_texts=[query], n_results=max(1, int(n_results)), include=["documents", "metadatas", "distances"])
        out: List[Dict[str, Any]] = []
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            rel = max(0.0, min(1.0, 1.0 - float(dist)))  # convert distance to similarity-ish
            if rel >= threshold:
                out.append({
                    "text": doc,
                    "document": doc,
                    "metadata": meta or {},
                    "relevance": rel,
                })
        return out

    def stats(self) -> Dict[str, Any]:
        try:
            total = self.collection.count()
            all_meta = self.collection.get(include=["metadatas"]).get("metadatas", [])
            doc_types: Dict[str, int] = {}
            titles = set()
            for m in all_meta:
                if not m:
                    continue
                t = m.get("doc_type", "general")
                doc_types[t] = doc_types.get(t, 0) + 1
                titles.add(m.get("title", "unknown"))
            return {"total_chunks": total, "unique_documents": len(titles), "document_types": doc_types}
        except Exception as e:
            return {"error": str(e)}

    def wipe(self) -> Dict[str, Any]:
        """Delete entire collection for this user (recreate empty)."""
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        # recreate
        try:
            self.collection = self.client.create_collection(name=self.collection_name, metadata={"user_id": self.user_id})
            return {"wiped": True}
        except Exception as e:
            return {"wiped": False, "error": str(e)}

    # Prune older research_auto (or other) documents keeping last N by timestamp inferred from title
    def prune(self, doc_type: str = "research_auto", keep_last: int = 200) -> Dict[str, Any]:
        try:
            # Fetch metadatas and ids filtered by doc_type
            res = self.collection.get(include=["metadatas", "documents"], where={"doc_type": doc_type})
            metas = res.get('metadatas', []) or []
            ids = res.get('ids', []) or []
            pairs = []
            for _id, meta in zip(ids, metas):
                title = (meta or {}).get('title') or _id
                # Extract numeric part (timestamp) if present
                import re, time
                ts_match = re.search(r'(?:search_|diary_|merged_|research_|agent_)(\d{9,})', title)
                if ts_match:
                    ts_val = int(ts_match.group(1))
                else:
                    ts_val = int(time.time())  # fallback current
                pairs.append((ts_val, _id))
            pairs.sort(key=lambda x: x[0])
            if len(pairs) <= keep_last:
                return {"pruned": 0, "kept": len(pairs)}
            to_delete = [pid for _, pid in pairs[:-keep_last]]
            if to_delete:
                self.collection.delete(ids=to_delete)
            return {"pruned": len(to_delete), "kept": len(pairs) - len(to_delete)}
        except Exception as e:
            return {"error": str(e)}
