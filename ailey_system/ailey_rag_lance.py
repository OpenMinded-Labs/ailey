# -*- coding: utf-8 -*-
"""
LanceDB-based RAG for Ailey.
Replaces ChromaDB for numpy 2.x + MLX compatibility.

LanceDB is:
  - Zero-config (no server needed)
  - Fast vector search (native Rust)
  - Compatible with numpy 2.x
  - Supports persistence to disk
"""
import os
import hashlib
import time
import re
import threading
from typing import List, Dict, Any, Optional

# ── Prevent torch/tokenizers deadlocks in background threads ──
# SentenceTransformer must run on CPU to avoid MPS/Metal conflicts with MLX.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import lancedb
import pyarrow as pa
from sentence_transformers import SentenceTransformer


class AileyRAG:
    """
    LanceDB-backed RAG system for Ailey.
    Drop-in replacement for the ChromaDB version.
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.table_name = f"ailey_user_{hashlib.md5(user_id.encode()).hexdigest()[:12]}"
        
        # Database path
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "lancedb"
        )
        os.makedirs(self.db_path, exist_ok=True)
        
        # Connect to LanceDB
        self.db = lancedb.connect(self.db_path)
        
        # Check if table exists, create schema if not
        self._ensure_table()
        
        # Lazy load embedder (thread-safe)
        self._embedder: Optional[SentenceTransformer] = None
        self._embed_lock = threading.Lock()
        
    def _ensure_table(self):
        """Create table if it doesn't exist."""
        existing_tables = self.db.table_names()
        if self.table_name not in existing_tables:
            # Create empty table with schema
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("text", pa.string()),
                pa.field("title", pa.string()),
                pa.field("doc_type", pa.string()),
                pa.field("timestamp", pa.int64()),
                pa.field("vector", pa.list_(pa.float32(), 384)),  # MiniLM embedding dim
            ])
            self.db.create_table(self.table_name, schema=schema)
        self.table = self.db.open_table(self.table_name)
    
    def _embedder_get(self) -> SentenceTransformer:
        """Lazy-load the embedding model (thread-safe, CPU-only to avoid MPS/MLX conflicts)."""
        if self._embedder is None:
            with self._embed_lock:
                if self._embedder is None:  # double-check after acquiring lock
                    self._embedder = SentenceTransformer(
                        'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
                        device='cpu',  # MUST be CPU — MPS deadlocks with MLX in threads
                    )
        return self._embedder
    
    @staticmethod
    def _smart_chunk(text: str, max_chunk: int = 600, min_chunk: int = 80) -> List[str]:
        """Split text into semantically meaningful chunks.

        Strategy: split on paragraph boundaries (double-newline), then on
        sentence boundaries (period/exclamation/question + space) if a
        paragraph is still too long.  Very short trailing fragments get
        merged into the previous chunk.
        """
        import re
        paragraphs = re.split(r'\n{2,}', text.strip())
        chunks: List[str] = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # If adding this paragraph stays within budget → append
            if len(current) + len(para) + 1 <= max_chunk:
                current = (current + "\n" + para).strip() if current else para
            else:
                # Flush current
                if current:
                    chunks.append(current)
                    current = ""
                # If the paragraph itself exceeds max_chunk → sentence-split
                if len(para) > max_chunk:
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    for sent in sentences:
                        if len(current) + len(sent) + 1 <= max_chunk:
                            current = (current + " " + sent).strip() if current else sent
                        else:
                            if current:
                                chunks.append(current)
                            current = sent
                else:
                    current = para
        if current:
            chunks.append(current)

        # Merge trailing tiny chunks
        if len(chunks) > 1 and len(chunks[-1]) < min_chunk:
            last = chunks.pop()
            chunks[-1] = chunks[-1] + "\n" + last

        # Filter empties
        return [c for c in chunks if len(c.strip()) >= min_chunk] or ([text[:max_chunk]] if text.strip() else [])

    def add_document(self, title: str, text: str, doc_type: str = "general") -> int:
        """Add a document (smart-chunked) to the RAG store."""
        text = (text or "").strip()
        if not text:
            return 0
        
        chunks = self._smart_chunk(text)
        
        # Generate embeddings
        embeddings = self._embedder_get().encode(chunks, convert_to_numpy=True, show_progress_bar=False)
        
        # Build records
        timestamp = int(time.time())
        records = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            records.append({
                "id": f"{title}-{i:04d}",
                "text": chunk,
                "title": title,
                "doc_type": doc_type,
                "timestamp": timestamp,
                "vector": embedding.tolist(),
            })
        
        # Add to table
        if records:
            self.table.add(records)
        
        return len(chunks)
    
    # ── Doc-type relevance weights ─────────────────────────────
    # Hard facts (lore, books, authors) get a permanent boost.
    # Soft sources (diary, thoughts, chat) decay over time:
    #   effective_weight = base + (1 - base) * e^(-age_days / half_life)
    # This means a fresh diary entry keeps ~full weight, but after
    # ~90 days it fades to its base weight.
    _DOCTYPE_BOOST: Dict[str, float] = {
        # Hard facts — permanent boost, no decay
        'martyria_lore': 1.35, 'martyria_byxie': 1.35,
        'martyria_tmc2': 1.35, 'martyria_marybeth': 1.35,
        'book_info': 1.25, 'author_info': 1.25,
        'user_rag': 1.20,  # user-uploaded docs are intentional
        'character_bible': 1.30,  # A!ley/Hamster character bibles — NEVER consolidate
        # Neutral — no change
        'research_auto': 1.0, 'research_code': 1.0,
        'self_prompt': 1.0, 'code_project': 1.0,
    }
    # Soft sources: (base_weight, half_life_days)
    # After half_life days the bonus above base decays by 50%.
    _DOCTYPE_DECAY: Dict[str, tuple] = {
        'diary': (0.70, 60),
        'diary_merged': (0.70, 60),
        'thought_reflection': (0.72, 90),
        'thought_introspection': (0.72, 90),
        'thought_goal_planning': (0.75, 90),
        'thought_memory_consolidation': (0.75, 90),
        'thought_diary_writing': (0.68, 45),
        'thought_proactive_message': (0.65, 30),
        'chat_memory': (0.70, 45),
        'email_exchange': (0.80, 120),
    }

    def _adjusted_relevance(self, raw_relevance: float, doc_type: str, timestamp: int) -> float:
        """Apply doc-type boost/decay to raw vector-similarity score.
        
        Hard facts get a permanent multiplier (>1.0).
        Soft sources (diary, thoughts) start at 1.0 but decay towards
        a lower base weight over time, so old diary mentions of "Martyria"
        don't outrank the actual lore entries.
        """
        import math
        # 1. Check for static boost (hard facts)
        if doc_type in self._DOCTYPE_BOOST:
            return min(1.0, raw_relevance * self._DOCTYPE_BOOST[doc_type])

        # 2. Check for time-decay sources
        if doc_type in self._DOCTYPE_DECAY:
            base_weight, half_life_days = self._DOCTYPE_DECAY[doc_type]
            age_days = max(0, (time.time() - timestamp) / 86400.0)
            # Exponential decay: 1.0 → base_weight over time
            # decay_factor starts at 1.0 (fresh) and approaches base_weight
            decay_factor = base_weight + (1.0 - base_weight) * math.exp(
                -0.693 * age_days / max(half_life_days, 1)  # 0.693 = ln(2)
            )
            return min(1.0, raw_relevance * decay_factor)

        # 3. Unknown doc_type — no adjustment
        return raw_relevance

    def search(self, query: str, n_results: int = 5, threshold: float = 0.5) -> List[Dict[str, Any]]:
        """Search for relevant documents with doc-type relevance weighting.
        
        Hard facts (lore, books, authors) get a permanent score boost.
        Soft sources (diary, thoughts) get a time-based decay so that
        old diary entries mentioning a topic don't outrank actual facts.
        """
        if not query:
            return []
        
        # Check if table has data
        try:
            count = self.table.count_rows()
            if count == 0:
                return []
        except Exception:
            return []
        
        # Generate query embedding
        query_embedding = self._embedder_get().encode([query], convert_to_numpy=True, show_progress_bar=False)[0]
        
        # Compute max theoretical L2 distance for un-normalized embeddings
        # For vectors with norm N, max L2 = 2*N^2 (opposite directions)
        import numpy as np
        _q_norm = float(np.linalg.norm(query_embedding))
        _max_l2 = 2.0 * (_q_norm ** 2) if _q_norm > 0 else 2.0

        # Vector search — request more than needed so we have headroom after re-ranking
        try:
            results = (
                self.table
                .search(query_embedding.tolist())
                .limit(max(n_results * 5, 30))  # wider pool for re-ranking
                .to_pandas()
            )
        except Exception as e:
            print(f"LanceDB search error: {e}")
            return []
        
        candidates: List[Dict[str, Any]] = []
        for _, row in results.iterrows():
            # LanceDB returns _distance (L2 distance)
            distance = row.get("_distance", _max_l2)
            raw_relevance = max(0.0, min(1.0, 1.0 - (distance / _max_l2)))
            
            doc_type = row.get("doc_type", "general")
            timestamp = int(row.get("timestamp", 0))
            
            # Apply doc-type boost/decay
            adjusted = self._adjusted_relevance(raw_relevance, doc_type, timestamp)
            
            if adjusted >= threshold:
                candidates.append({
                    "text": row.get("text", ""),
                    "document": row.get("text", ""),
                    "metadata": {
                        "title": row.get("title", ""),
                        "doc_type": doc_type,
                    },
                    "relevance": adjusted,
                    "_raw_relevance": raw_relevance,
                })
        
        # Re-rank by adjusted relevance (facts float up, old diary sinks)
        candidates.sort(key=lambda c: -c["relevance"])
        
        # Strip internal field and return top-N
        out = candidates[:n_results]
        for item in out:
            item.pop("_raw_relevance", None)
        return out

    def search_by_types(self, query: str, doc_types: List[str], n_results: int = 5,
                        threshold: float = 0.3) -> List[Dict[str, Any]]:
        """Search for relevant documents filtered by doc_type(s).
        Applies the same boost/decay relevance weighting as search()."""
        if not query or not doc_types:
            return []
        try:
            count = self.table.count_rows()
            if count == 0:
                return []
        except Exception:
            return []

        query_embedding = self._embedder_get().encode([query], convert_to_numpy=True, show_progress_bar=False)[0]

        import numpy as np
        _q_norm = float(np.linalg.norm(query_embedding))
        _max_l2 = 2.0 * (_q_norm ** 2) if _q_norm > 0 else 2.0

        # Build filter string for LanceDB
        type_filter = " OR ".join(f"doc_type = '{t}'" for t in doc_types)

        try:
            results = (
                self.table
                .search(query_embedding.tolist())
                .where(type_filter)
                .limit(max(n_results * 5, 20))
                .to_pandas()
            )
        except Exception as e:
            print(f"LanceDB search_by_types error: {e}")
            return []

        candidates: List[Dict[str, Any]] = []
        for _, row in results.iterrows():
            distance = row.get("_distance", _max_l2)
            raw_relevance = max(0.0, min(1.0, 1.0 - (distance / _max_l2)))

            doc_type = row.get("doc_type", "general")
            timestamp = int(row.get("timestamp", 0))
            adjusted = self._adjusted_relevance(raw_relevance, doc_type, timestamp)

            if adjusted >= threshold:
                candidates.append({
                    "text": row.get("text", ""),
                    "document": row.get("text", ""),
                    "metadata": {
                        "title": row.get("title", ""),
                        "doc_type": doc_type,
                    },
                    "relevance": adjusted,
                })
        
        candidates.sort(key=lambda c: -c["relevance"])
        return candidates[:n_results]

    def stats(self) -> Dict[str, Any]:
        """Return statistics about the RAG store."""
        try:
            total = self.table.count_rows()
            df = self.table.to_pandas()
            doc_types: Dict[str, int] = {}
            titles = set()
            for _, row in df.iterrows():
                t = row.get("doc_type", "general")
                doc_types[t] = doc_types.get(t, 0) + 1
                titles.add(row.get("title", "unknown"))
            return {
                "total_chunks": total,
                "unique_documents": len(titles),
                "document_types": doc_types,
            }
        except Exception as e:
            return {"error": str(e)}

    def list_entries(self, doc_type: str = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List RAG entries, optionally filtered by doc_type.
        Returns entries sorted by timestamp (newest first) without embeddings."""
        try:
            df = self.table.to_pandas()
            if doc_type:
                df = df[df["doc_type"] == doc_type]
            df = df.sort_values("timestamp", ascending=False)
            df = df.iloc[offset:offset + limit]
            entries = []
            for _, row in df.iterrows():
                entries.append({
                    "id": row.get("id", ""),
                    "title": row.get("title", ""),
                    "text": row.get("text", "")[:500],  # truncate for overview
                    "doc_type": row.get("doc_type", "general"),
                    "timestamp": row.get("timestamp", 0),
                })
            return entries
        except Exception as e:
            return []

    def delete_entry(self, entry_id: str) -> bool:
        """Delete a single RAG entry by ID."""
        try:
            self.table.delete(f"id = '{entry_id}'")
            return True
        except Exception:
            return False

    def wipe(self) -> Dict[str, Any]:
        """Delete entire table for this user (recreate empty)."""
        try:
            self.db.drop_table(self.table_name)
        except Exception:
            pass
        
        # Recreate empty table
        try:
            self._ensure_table()
            return {"wiped": True}
        except Exception as e:
            return {"wiped": False, "error": str(e)}
    
    def prune(self, doc_type: str = "research_auto", keep_last: int = 200) -> Dict[str, Any]:
        """Prune older documents of a specific type, keeping last N by timestamp."""
        try:
            df = self.table.to_pandas()
            # Filter by doc_type
            filtered = df[df["doc_type"] == doc_type]
            
            if len(filtered) <= keep_last:
                return {"pruned": 0, "kept": len(filtered)}
            
            # Sort by timestamp, get IDs to delete
            sorted_df = filtered.sort_values("timestamp")
            to_delete_ids = sorted_df.head(len(sorted_df) - keep_last)["id"].tolist()
            
            if to_delete_ids:
                # LanceDB delete by filter
                self.table.delete(f"id IN {tuple(to_delete_ids)}" if len(to_delete_ids) > 1 else f"id = '{to_delete_ids[0]}'")
            
            return {"pruned": len(to_delete_ids), "kept": keep_last}
        except Exception as e:
            return {"error": str(e)}

    def get_entries_by_type(self, doc_type: str, oldest_first: bool = True,
                            limit: int = 500) -> List[Dict[str, Any]]:
        """Return RAG entries of a specific doc_type for consolidation.
        Returns full text (no truncation) sorted by timestamp."""
        try:
            df = self.table.to_pandas()
            filtered = df[df["doc_type"] == doc_type]
            if oldest_first:
                filtered = filtered.sort_values("timestamp", ascending=True)
            else:
                filtered = filtered.sort_values("timestamp", ascending=False)
            filtered = filtered.head(limit)
            entries = []
            for _, row in filtered.iterrows():
                entries.append({
                    "id": row.get("id", ""),
                    "title": row.get("title", ""),
                    "text": row.get("text", ""),
                    "doc_type": row.get("doc_type", "general"),
                    "timestamp": int(row.get("timestamp", 0)),
                })
            return entries
        except Exception:
            return []

    def delete_entries_bulk(self, entry_ids: List[str]) -> int:
        """Delete multiple RAG entries by ID. Returns count deleted."""
        if not entry_ids:
            return 0
        try:
            # LanceDB delete supports IN clauses
            if len(entry_ids) == 1:
                self.table.delete(f"id = '{entry_ids[0]}'")
            else:
                # Escape single quotes in IDs
                safe_ids = [eid.replace("'", "''") for eid in entry_ids]
                id_list = ", ".join(f"'{eid}'" for eid in safe_ids)
                self.table.delete(f"id IN ({id_list})")
            return len(entry_ids)
        except Exception as e:
            print(f"[RAG] delete_entries_bulk error: {e}")
            return 0


# For backward compatibility - module-level function
def get_rag(user_id: str) -> AileyRAG:
    """Factory function for RAG instance."""
    return AileyRAG(user_id)
