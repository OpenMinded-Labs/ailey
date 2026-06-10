# -*- coding: utf-8 -*-
"""
DeferredStore: thread-safe, crash-resistant append-only JSONL store for
deferred proactive notifications.

Usage:
    from ailey_system.proactive_store import DeferredStore
    store = DeferredStore()
    store.append(notification_dict)
    msgs = store.pop_all()
"""
import json
import os
import threading
from typing import List, Dict, Any


class DeferredStore:
    def __init__(self, path: str = None, max_items: int = 2000):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_dir = os.path.join(root, 'ailey_users')
        os.makedirs(default_dir, exist_ok=True)
        if path is None:
            path = os.path.join(default_dir, 'deferred_notifications.jsonl')
        self.path = path
        self.lock = threading.RLock()
        self._mem: List[Dict[str, Any]] = []
        self.max_items = int(max_items)
        self._disk_ok = True
        # load existing file if present
        self.load_from_disk()

    def append(self, notif: Dict[str, Any]) -> None:
        """Append notification to in-memory queue and persist a JSONL line.

        This method is thread-safe.
        """
        line = json.dumps(notif, ensure_ascii=False) + "\n"
        with self.lock:
            self._mem.append(notif)
            # enforce bound
            if self.max_items and len(self._mem) > self.max_items:
                # drop oldest
                overflow = len(self._mem) - self.max_items
                if overflow > 0:
                    self._mem = self._mem[overflow:]
            # try append to disk using O_APPEND for atomicity
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
                try:
                    os.write(fd, line.encode('utf-8'))
                    try:
                        os.fsync(fd)
                    except Exception:
                        # fsync is best-effort; ignore if not supported
                        pass
                finally:
                    os.close(fd)
                self._disk_ok = True
            except Exception:
                # record failure, keep in-memory copy
                self._disk_ok = False

    def pop_all(self) -> List[Dict[str, Any]]:
        """Return all deferred messages (in order) and clear both memory and disk.

        This operation is atomic w.r.t. other append/pop operations via a lock.
        """
        with self.lock:
            items = list(self._mem)
            self._mem.clear()
            # truncate file atomically
            try:
                tmp = self.path + '.tmp'
                # create an empty tmp file then replace
                with open(tmp, 'w', encoding='utf-8') as fh:
                    fh.write('')
                os.replace(tmp, self.path)
                self._disk_ok = True
            except Exception:
                # If truncation failed, mark disk unreliable but keep memory cleared
                self._disk_ok = False
            return items

    def count(self) -> int:
        with self.lock:
            return len(self._mem)

    def peek(self, n: int = 50) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self._mem[:n])

    def load_from_disk(self) -> None:
        with self.lock:
            if not os.path.exists(self.path):
                return
            try:
                with open(self.path, 'r', encoding='utf-8') as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            self._mem.append(obj)
                        except Exception:
                            # skip corrupted lines
                            continue
                # enforce bound
                if self.max_items and len(self._mem) > self.max_items:
                    self._mem = self._mem[-self.max_items:]
                self._disk_ok = True
            except Exception:
                self._disk_ok = False

    def persist_all_to_disk(self) -> None:
        """Overwrite disk file with the current in-memory queue (atomic)."""
        with self.lock:
            try:
                tmp = self.path + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as fh:
                    for item in self._mem:
                        fh.write(json.dumps(item, ensure_ascii=False) + '\n')
                    fh.flush()
                    try:
                        os.fsync(fh.fileno())
                    except Exception:
                        pass
                os.replace(tmp, self.path)
                self._disk_ok = True
            except Exception:
                self._disk_ok = False

    def clear_disk(self) -> None:
        with self.lock:
            try:
                open(self.path, 'w', encoding='utf-8').close()
                self._disk_ok = True
            except Exception:
                self._disk_ok = False
