import os
import json
from typing import List, Dict, Any


class AileyMemoryManager:
    def __init__(self, base_path: str = "ailey_users"):
        self.base_path = base_path
        self.conversation_history: List[Dict[str, Any]] = []
        self.relationship_memories: List[Dict[str, Any]] = []
        self.creative_projects: List[Dict[str, Any]] = []

        os.makedirs(self.base_path, exist_ok=True)

    def load_ailey_documents(self) -> List[str]:
        """Lade alle Ailey-spezifischen Dokumente (Stub)."""
        documents = [
            "character_matrix.txt",
            "digital_existence_logs.txt",
            "song_collaborations.txt",
            "relationship_timeline.txt",
        ]
        existing = []
        for doc in documents:
            p = os.path.join(self.base_path, doc)
            if os.path.exists(p):
                existing.append(p)
        return existing

    # Simple persistence helpers
    def _user_dir(self, user_id: str) -> str:
        d = os.path.join(self.base_path, f"{user_id}_profile")
        os.makedirs(d, exist_ok=True)
        return d

    def add_relationship_memory(self, user_id: str, memory: Dict[str, Any]) -> None:
        d = os.path.join(self._user_dir(user_id), "relationship_history")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"mem_{len(os.listdir(d)) + 1:06d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)

    def add_conversation_log(self, user_id: str, item: Dict[str, Any]) -> None:
        d = os.path.join(self._user_dir(user_id), "conversation_logs")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"conv_{len(os.listdir(d)) + 1:06d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)

    # --- Diary Entries -------------------------------------------------
    def add_diary_entry(self, user_id: str, diary: Dict[str, Any]) -> str:
        d = os.path.join(self._user_dir(user_id), "diaries")
        os.makedirs(d, exist_ok=True)
        # Use timestamp-based filenames to prevent collisions from auto-merge
        # deleting files and len(listdir) producing duplicate indices.
        import time as _t
        ts = int(_t.time() * 1000)  # millisecond precision
        path = os.path.join(d, f"diary_{ts}.json")
        # In the unlikely event of a collision, append a counter
        _attempt = 0
        while os.path.exists(path):
            _attempt += 1
            path = os.path.join(d, f"diary_{ts}_{_attempt}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(diary, f, ensure_ascii=False, indent=2)
        return path

    def list_diaries(self, user_id: str) -> list:
        d = os.path.join(self._user_dir(user_id), "diaries")
        if not os.path.exists(d):
            return []
        out = []
        for name in sorted(os.listdir(d)):
            if not name.endswith('.json'): continue
            p = os.path.join(d, name)
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    j = json.load(f)
                j['_file'] = name
                out.append(j)
            except Exception:
                pass
        return out

    def delete_diary_files(self, user_id: str, filenames: list):
        """Delete specific diary files by filename."""
        d = os.path.join(self._user_dir(user_id), "diaries")
        for name in filenames:
            if not name:
                continue
            p = os.path.join(d, name)
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    # --- Session State (Conversation Focus) -----------------------------------
    def _session_state_path(self, user_id: str) -> str:
        return os.path.join(self._user_dir(user_id), 'session_state.json')

    def load_session_state(self, user_id: str) -> Dict[str, Any]:
        path = self._session_state_path(user_id)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError
                # defaults
                data.setdefault('message_count', 0)
                data.setdefault('session_focus', '')
                data.setdefault('focus_updated_at', 0)
                return data
            except Exception:
                pass
        return {'message_count': 0, 'session_focus': '', 'focus_updated_at': 0}

    def save_session_state(self, user_id: str, state: Dict[str, Any]):
        try:
            path = self._session_state_path(user_id)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
