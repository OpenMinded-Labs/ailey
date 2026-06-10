# -*- coding: utf-8 -*-
"""
Ailey Learning Engine — Manages user progress, quiz evaluation, and LLM-driven teaching.

Two learning modes:
  1. Hardcoded: Multiple choice, true/false, fill-in, code completion quizzes
  2. LLM-driven: Interactive teaching, personalized explanations, code exercises with evaluation
"""

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .curricula import TRACKS, LEVELS, get_track, get_unit, get_track_summary

# ── User progress storage ──────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROGRESS_DIR = os.path.join(os.path.dirname(_BASE_DIR), "ailey_users", "learning")
_CUSTOM_UNITS_DIR = os.path.join(os.path.dirname(_BASE_DIR), "ailey_users", "learning", "custom_units")


def _ensure_progress_dir():
    os.makedirs(_PROGRESS_DIR, exist_ok=True)


def _progress_path(user_id: str) -> str:
    """Path to a user's learning progress file."""
    _ensure_progress_dir()
    safe_id = user_id.replace("/", "_").replace("..", "_")[:64]
    return os.path.join(_PROGRESS_DIR, f"progress_{safe_id}.json")


class LearningEngine:
    """Manages learning sessions, quizzes, and progress tracking."""

    def __init__(self, core=None, get_generator=None):
        """
        Args:
            core: AileyCore instance (used for non-LLM helpers only).
            get_generator: Callable that returns an LLM generator instance
                           (e.g. MLXGenerator.get). If None, falls back to
                           core.process_message (legacy, slow).
        """
        self._core = core
        self._get_generator_fn = get_generator
        self._rag = None  # Lazy-loaded global learning RAG

    def _get_rag(self):
        """Lazy-load the global learning RAG instance (shared across all users)."""
        if self._rag is None:
            try:
                from ..ailey_rag_lance import AileyRAG
                self._rag = AileyRAG(user_id="learning_global")
            except Exception as e:
                print(f"[Learning] RAG init failed (non-critical): {e}")
                self._rag = False  # Sentinel: don't retry
        return self._rag if self._rag is not False else None

    def _search_rag(self, query: str, doc_types: list = None, n_results: int = 4) -> str:
        """Search the learning RAG for relevant textbook passages.

        Returns a formatted context string to inject into LLM prompts.
        Returns empty string if RAG is unavailable or no results found.
        """
        rag = self._get_rag()
        if not rag:
            return ""

        try:
            if doc_types:
                results = rag.search_by_types(query, doc_types, n_results=n_results, threshold=0.2)
            else:
                results = rag.search(query, n_results=n_results, threshold=0.2)

            if not results:
                return ""

            passages = []
            for r in results:
                title = r.get("metadata", {}).get("title", "")
                text = r.get("text", r.get("document", ""))
                if text:
                    passages.append(f"[Quelle: {title}]\n{text}")

            if passages:
                return (
                    "\n\n── Relevante Stellen aus Fachbüchern ──\n\n"
                    + "\n\n---\n\n".join(passages)
                    + "\n\n── Ende Fachbuch-Kontext ──\n"
                )
        except Exception as e:
            print(f"[Learning] RAG search error (non-critical): {e}")
        return ""

    @staticmethod
    def _rag_types_for_track(track_id: str) -> list:
        """Map a learning track to the relevant RAG doc_types for textbook lookup."""
        mapping = {
            "html":               ["learning_web"],
            "css":                ["learning_web"],
            "javascript":         ["learning_web"],
            "python":             ["learning_web"],
            "php":                ["learning_web"],
            "sql":                ["learning_web"],
            "rust":               ["learning_web"],
            "json_xml":           ["learning_web"],
            "ihk_mediengestalter": ["learning_ihk", "learning_design"],
        }
        return mapping.get(track_id, ["learning_web", "learning_ihk", "learning_design"])

    def _generate_direct(self, system_prompt: str, user_prompt: str,
                         max_tokens: int = 2048, temperature: float = 0.65) -> Optional[str]:
        """Generate text directly via the LLM generator — bypasses process_message.

        This avoids injecting the full persona, glossary, conversation history,
        LifeSim mood, and 19k-row RAG context that makes learning mode slow.
        Falls back to process_message if no generator is configured.
        """
        # ── Direct path (fast — no persona/history bloat) ──
        if self._get_generator_fn:
            gen = self._get_generator_fn()
            if gen is not None:
                try:
                    from ..prompt_builder import get_ailey_generation_params
                    params = get_ailey_generation_params()
                    params["max_tokens"] = max_tokens
                    params["temperature"] = temperature

                    from ailey_api import _LLMSlot
                    with _LLMSlot('portal_chat', timeout=180):
                        raw = gen.generate(system_prompt, user_prompt, params)

                    # Strip thinking tags
                    if '</think>' in raw:
                        raw = raw.split('</think>', 1)[-1].strip()

                    # Strip mood tags (not needed in lessons)
                    import re
                    raw = re.sub(r'\s*<mood:\w+>\s*', '', raw).strip()

                    return raw
                except TimeoutError:
                    print("[Learning] ⏳ LLM slot timeout — generator busy")
                    return None
                except ImportError:
                    # _LLMSlot not available — generate without slot
                    try:
                        raw = gen.generate(system_prompt, user_prompt, params)
                        if '</think>' in raw:
                            raw = raw.split('</think>', 1)[-1].strip()
                        import re
                        raw = re.sub(r'\s*<mood:\w+>\s*', '', raw).strip()
                        return raw
                    except Exception as e:
                        print(f"[Learning] ❌ Direct generation failed: {e}")
                        return None
                except Exception as e:
                    print(f"[Learning] ❌ Direct generation failed: {e}")
                    return None

        # ── Fallback: legacy process_message path (slow but works) ──
        if self._core:
            try:
                result = self._core.process_message(
                    user_prompt,
                    user="simon",
                    user_max_tokens=max_tokens,
                )
                return result.get("response", "")
            except Exception as e:
                print(f"[Learning] ❌ Fallback process_message failed: {e}")
                return None

        return None

    # ══════════════════════════════════════════════════════════════
    # PROGRESS MANAGEMENT
    # ══════════════════════════════════════════════════════════════

    def get_progress(self, user_id: str) -> Dict:
        """Load a user's learning progress."""
        path = _progress_path(user_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return self._init_progress(user_id)

    def _init_progress(self, user_id: str) -> Dict:
        return {
            "user_id": user_id,
            "created_at": time.time(),
            "updated_at": time.time(),
            "xp": 0,
            "streak_days": 0,
            "last_activity": None,
            "tracks": {},  # track_id → { level, completed_units, quiz_scores, ... }
        }

    def save_progress(self, user_id: str, progress: Dict):
        """Persist user progress."""
        progress["updated_at"] = time.time()
        path = _progress_path(user_id)
        _ensure_progress_dir()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

    def set_level(self, user_id: str, track_id: str, level: int) -> Dict:
        """Set a user's starting level for a track (skip lower content)."""
        progress = self.get_progress(user_id)
        track_prog = progress["tracks"].setdefault(track_id, {
            "level": 0, "completed_units": [], "quiz_scores": {},
            "exercises_done": [], "current_unit": None,
        })
        level = max(0, min(5, level))
        track_prog["level"] = level
        # Mark all units below the set level as completed
        track = get_track(track_id)
        if track:
            for u in track["units"]:
                if u["level"] < level and u["id"] not in track_prog["completed_units"]:
                    track_prog["completed_units"].append(u["id"])
        self.save_progress(user_id, progress)
        return progress

    def get_dashboard(self, user_id: str) -> Dict:
        """Get a user's learning dashboard with all tracks and progress."""
        progress = self.get_progress(user_id)
        tracks_summary = get_track_summary()

        dashboard_tracks = []
        for ts in tracks_summary:
            tid = ts["id"]
            tp = progress["tracks"].get(tid, {})
            completed = len(tp.get("completed_units", []))

            # Include custom units in total count
            custom = self._load_custom_units(user_id, tid)
            total = ts["total_units"] + len(custom)

            # Calculate average quiz score
            scores = tp.get("quiz_scores", {})
            avg_score = (sum(scores.values()) / len(scores) * 100) if scores else 0

            # Spaced repetition info
            sr_queue = tp.get("spaced_repetition", [])
            sr_due = sum(1 for s in sr_queue if s.get("next_review", 0) <= time.time())

            dashboard_tracks.append({
                **ts,
                "total_units": total,
                "custom_units": len(custom),
                "user_level": tp.get("level", 0),
                "completed_units": completed,
                "progress_pct": round(completed / total * 100) if total else 0,
                "avg_quiz_score": round(avg_score, 1),
                "current_unit": tp.get("current_unit"),
                "review_due": sr_due,
                "review_total": len(sr_queue),
            })

        return {
            "user_id": user_id,
            "xp": progress.get("xp", 0),
            "streak_days": progress.get("streak_days", 0),
            "tracks": dashboard_tracks,
        }

    # ══════════════════════════════════════════════════════════════
    # UNIT & LESSON RETRIEVAL
    # ══════════════════════════════════════════════════════════════

    def get_next_unit(self, user_id: str, track_id: str) -> Optional[Dict]:
        """Get the next uncompleted unit in a track for a user (global + custom)."""
        progress = self.get_progress(user_id)
        tp = progress["tracks"].get(track_id, {})
        completed = set(tp.get("completed_units", []))
        user_level = tp.get("level", 0)

        # Check global units first, then custom
        all_units = self.get_all_units_for_user(user_id, track_id)
        for u in all_units:
            if u["id"] not in completed and u.get("level", 0) >= user_level:
                return u
        return None  # Track complete!

    def get_unit_content(self, track_id: str, unit_id: str, user_id: str = None) -> Optional[Dict]:
        """Get full unit content for display, with user progress info."""
        u = get_unit(track_id, unit_id)
        # Also check user's custom units
        if not u and user_id:
            u = self._get_custom_unit(user_id, track_id, unit_id)
        if not u:
            return None

        result = {**u}

        if user_id:
            progress = self.get_progress(user_id)
            tp = progress["tracks"].get(track_id, {})
            result["is_completed"] = unit_id in tp.get("completed_units", [])
            result["quiz_score"] = tp.get("quiz_scores", {}).get(unit_id)
            result["exercise_done"] = unit_id in tp.get("exercises_done", [])

        # Level info
        lvl = LEVELS.get(u["level"], {})
        result["level_name"] = lvl.get("name_de", "")
        result["level_emoji"] = lvl.get("emoji", "")
        result["xp_reward"] = lvl.get("xp_per_unit", 0)

        return result

    # ══════════════════════════════════════════════════════════════
    # QUIZ EVALUATION (HARDCODED)
    # ══════════════════════════════════════════════════════════════

    def evaluate_quiz(self, user_id: str, track_id: str, unit_id: str,
                      answers: List[Any]) -> Dict:
        """Evaluate a hardcoded quiz and update progress.

        Args:
            answers: List of user answers, one per quiz question.
                     mc → int (selected index), tf → bool, fill → str,
                     match → list of pairs, code → str, open → str
        """
        u = get_unit(track_id, unit_id)
        # Also check user's custom units
        if not u:
            u = self._get_custom_unit(user_id, track_id, unit_id)
        if not u:
            return {"error": "Unit not found"}

        quiz = u.get("quiz", [])
        if not quiz:
            return {"error": "No quiz in this unit"}

        results = []
        correct_count = 0
        open_evals = []  # Collect open-answer evaluations

        for i, q in enumerate(quiz):
            user_answer = answers[i] if i < len(answers) else None
            is_correct = False

            if q["type"] == "mc":
                is_correct = user_answer == q["correct"]
            elif q["type"] == "tf":
                is_correct = user_answer == q["correct"]
            elif q["type"] == "fill":
                if isinstance(user_answer, str):
                    is_correct = user_answer.strip().lower() in [
                        b.strip().lower() for b in q.get("blanks", [])
                    ]
            elif q["type"] == "match":
                if isinstance(user_answer, list):
                    expected = {p[0]: p[1] for p in q.get("pairs", [])}
                    given = {p[0]: p[1] for p in user_answer} if user_answer else {}
                    is_correct = expected == given
            elif q["type"] == "open":
                # Open-ended: LLM evaluates user answer against model answers
                if isinstance(user_answer, str) and user_answer.strip():
                    eval_result = self._evaluate_open_answer(q, user_answer)
                    if eval_result:
                        is_correct = eval_result.get("score", 0) >= 60
                        open_evals.append(eval_result)
                    else:
                        is_correct = None  # Could not evaluate
                else:
                    is_correct = False
                    open_evals.append({"score": 0, "feedback": "Keine Antwort gegeben."})
            elif q["type"] == "code":
                is_correct = None  # Handled separately

            if is_correct:
                correct_count += 1

            result_entry = {
                "question": q["question"],
                "type": q["type"],
                "correct": is_correct,
                "explanation": q.get("explanation", ""),
                "correct_answer": q.get("correct") if q["type"] in ("mc", "tf") else q.get("blanks", []),
            }
            # For open questions, attach LLM feedback
            if q["type"] == "open" and open_evals:
                oe = open_evals[-1]
                result_entry["open_feedback"] = oe.get("feedback", "")
                result_entry["open_score"] = oe.get("score", 0)
                result_entry["key_points_hit"] = oe.get("key_points_hit", [])
                result_entry["key_points_missed"] = oe.get("key_points_missed", [])

            results.append(result_entry)

        total = len(quiz)
        gradable = sum(1 for r in results if r["correct"] is not None)
        score = correct_count / gradable if gradable else 0

        # ── Spaced Repetition: track wrong answers ──
        wrong_questions = []
        for i, r in enumerate(results):
            if r["correct"] is False:
                wrong_questions.append({
                    "unit_id": unit_id,
                    "question_idx": i,
                    "question": r["question"],
                    "type": quiz[i]["type"],
                    "topic": quiz[i].get("topic", ""),
                    "failed_at": time.time(),
                    "next_review": time.time() + 86400,  # review in 24h
                    "interval_days": 1,
                    "ease_factor": 2.5,
                })

        # Update progress
        progress = self.get_progress(user_id)
        tp = progress["tracks"].setdefault(track_id, {
            "level": 0, "completed_units": [], "quiz_scores": {},
            "exercises_done": [], "current_unit": None,
        })
        tp["quiz_scores"][unit_id] = score

        # Update spaced repetition queue
        sr_queue = tp.setdefault("spaced_repetition", [])
        for wq in wrong_questions:
            # Don't duplicate same question
            existing = [s for s in sr_queue if s["unit_id"] == unit_id and s["question_idx"] == wq["question_idx"]]
            if existing:
                # Reset interval on repeated failure
                existing[0]["interval_days"] = 1
                existing[0]["next_review"] = time.time() + 86400
                existing[0]["ease_factor"] = max(1.3, existing[0]["ease_factor"] - 0.2)
            else:
                sr_queue.append(wq)

        # Remove from SR queue if now answered correctly
        for i, r in enumerate(results):
            if r["correct"] is True:
                tp["spaced_repetition"] = [
                    s for s in tp.get("spaced_repetition", [])
                    if not (s["unit_id"] == unit_id and s["question_idx"] == i)
                ]

        # Keep SR queue bounded
        if len(tp.get("spaced_repetition", [])) > 200:
            tp["spaced_repetition"] = sorted(
                tp["spaced_repetition"], key=lambda x: x["next_review"]
            )[:200]

        # Mark complete if score >= 60%
        if score >= 0.6 and unit_id not in tp.get("completed_units", []):
            tp["completed_units"].append(unit_id)
            level = u.get("level", 0) if isinstance(u, dict) else 0
            xp_reward = LEVELS.get(level, {}).get("xp_per_unit", 50)
            progress["xp"] = progress.get("xp", 0) + xp_reward

        # Update streak
        today = time.strftime("%Y-%m-%d")
        last = progress.get("last_activity")
        if last and last != today:
            from datetime import datetime, timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            if last == yesterday:
                progress["streak_days"] = progress.get("streak_days", 0) + 1
            else:
                progress["streak_days"] = 1
        elif not last:
            progress["streak_days"] = 1
        progress["last_activity"] = today

        self.save_progress(user_id, progress)

        return {
            "score": round(score * 100, 1),
            "correct": correct_count,
            "total": gradable,
            "passed": score >= 0.6,
            "results": results,
            "xp_earned": LEVELS.get(u.get("level", 0) if isinstance(u, dict) else 0, {}).get("xp_per_unit", 0) if score >= 0.6 else 0,
        }

    # ══════════════════════════════════════════════════════════════
    # OPEN ANSWER EVALUATION (LLM)
    # ══════════════════════════════════════════════════════════════

    def _evaluate_open_answer(self, question: Dict, user_answer: str) -> Optional[Dict]:
        """Use LLM to evaluate an open-ended answer against model answers.

        Returns dict with: score (0-100), feedback (str), key_points_hit, key_points_missed
        """
        model_answers = question.get("model_answers", [])
        key_points = question.get("key_points", [])

        system_prompt = (
            "Du bist eine KI-Prüferin für die IHK-Prüfung Mediengestalter.\n"
            "Bewerte die Antwort eines Prüflings auf eine offene Frage.\n\n"
            "Antworte AUSSCHLIESSLICH als JSON:\n"
            '{"score": 0-100, "feedback": "...", "key_points_hit": ["..."], "key_points_missed": ["..."]}\n\n'
            "Bewertung:\n"
            "- 90-100: Vollständig, fachlich korrekt, gut formuliert\n"
            "- 70-89: Weitgehend korrekt, kleine Lücken\n"
            "- 50-69: Grundidee verstanden, aber unvollständig\n"
            "- 20-49: Teilweise richtig, wichtige Aspekte fehlen\n"
            "- 0-19: Falsch oder am Thema vorbei\n\n"
            "Sei ermutigend aber ehrlich. Deutsch."
        )

        kp_str = f"\nSchlüsselbegriffe die vorkommen sollten: {', '.join(key_points)}" if key_points else ""
        ma_str = "\n".join(f"Musterantwort {i+1}: {ma}" for i, ma in enumerate(model_answers))

        user_prompt = (
            f"FRAGE: {question['question']}\n\n"
            f"MUSTERANTWORTEN:\n{ma_str}\n"
            f"{kp_str}\n\n"
            f"ANTWORT DES PRÜFLINGS:\n{user_answer}"
        )

        try:
            response_text = self._generate_direct(system_prompt, user_prompt, max_tokens=512)
            if not response_text:
                return self._fallback_open_eval(question, user_answer)

            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                result = json.loads(json_match.group())
                return result
            return self._fallback_open_eval(question, user_answer)
        except Exception as e:
            print(f"[Learning] Open answer evaluation failed: {e}")
            return self._fallback_open_eval(question, user_answer)

    def _fallback_open_eval(self, question: Dict, user_answer: str) -> Dict:
        """Simple keyword-matching fallback when LLM is unavailable."""
        key_points = question.get("key_points", [])
        if not key_points:
            return {"score": 50, "feedback": "Automatische Bewertung nicht möglich.", "key_points_hit": [], "key_points_missed": []}

        answer_lower = user_answer.lower()
        hit = [kp for kp in key_points if kp.lower() in answer_lower]
        missed = [kp for kp in key_points if kp.lower() not in answer_lower]
        score = int(len(hit) / len(key_points) * 100) if key_points else 0

        feedback = f"{len(hit)} von {len(key_points)} Schlüsselbegriffe erkannt."
        if missed:
            feedback += f" Fehlend: {', '.join(missed[:3])}."

        return {
            "score": score,
            "feedback": feedback,
            "key_points_hit": hit,
            "key_points_missed": missed,
        }

    # ══════════════════════════════════════════════════════════════
    # SPACED REPETITION — Wiederholfragen aus Fehlern
    # ══════════════════════════════════════════════════════════════

    def get_review_questions(self, user_id: str, track_id: str,
                             count: int = 10) -> List[Dict]:
        """Get questions due for spaced repetition review.

        Returns questions the user previously got wrong that are due for review.
        Uses SM-2 like intervals: 1d → 3d → 7d → 14d → 30d → 90d
        """
        progress = self.get_progress(user_id)
        tp = progress["tracks"].get(track_id, {})
        sr_queue = tp.get("spaced_repetition", [])

        now = time.time()
        due = [q for q in sr_queue if q.get("next_review", 0) <= now]
        due.sort(key=lambda x: x.get("next_review", 0))

        review_questions = []
        for item in due[:count]:
            # Fetch the actual question from the unit
            u = get_unit(track_id, item["unit_id"])
            if not u:
                u = self._get_custom_unit(user_id, track_id, item["unit_id"])
            if not u:
                continue
            quiz = u.get("quiz", [])
            idx = item.get("question_idx", 0)
            if idx < len(quiz):
                q = quiz[idx].copy()
                q["_sr_unit_id"] = item["unit_id"]
                q["_sr_idx"] = idx
                q["_sr_interval"] = item.get("interval_days", 1)
                review_questions.append(q)

        return review_questions

    def update_review_result(self, user_id: str, track_id: str,
                              unit_id: str, question_idx: int,
                              correct: bool):
        """Update spaced repetition interval after a review answer.

        SM-2 simplified: correct → increase interval × ease_factor.
                         wrong → reset to 1 day, decrease ease.
        """
        progress = self.get_progress(user_id)
        tp = progress["tracks"].get(track_id, {})
        sr_queue = tp.get("spaced_repetition", [])

        for item in sr_queue:
            if item["unit_id"] == unit_id and item["question_idx"] == question_idx:
                if correct:
                    # Increase interval
                    new_interval = item["interval_days"] * item["ease_factor"]
                    item["interval_days"] = min(new_interval, 180)  # Cap at 6 months
                    item["ease_factor"] = min(3.0, item["ease_factor"] + 0.1)
                    item["next_review"] = time.time() + item["interval_days"] * 86400

                    # If interval > 90 days, remove from queue (learned!)
                    if item["interval_days"] > 90:
                        sr_queue.remove(item)
                else:
                    # Reset
                    item["interval_days"] = 1
                    item["next_review"] = time.time() + 86400
                    item["ease_factor"] = max(1.3, item["ease_factor"] - 0.2)
                break

        self.save_progress(user_id, progress)

    # ══════════════════════════════════════════════════════════════
    # CUSTOM / USER-GENERATED UNITS
    # ══════════════════════════════════════════════════════════════

    def _custom_units_path(self, user_id: str, track_id: str) -> str:
        """Path to a user's custom units file for a track."""
        os.makedirs(_CUSTOM_UNITS_DIR, exist_ok=True)
        safe_uid = user_id.replace("/", "_").replace("..", "_")[:64]
        safe_tid = track_id.replace("/", "_").replace("..", "_")[:64]
        return os.path.join(_CUSTOM_UNITS_DIR, f"custom_{safe_uid}_{safe_tid}.json")

    def _load_custom_units(self, user_id: str, track_id: str) -> List[Dict]:
        """Load user-generated custom units for a track."""
        path = self._custom_units_path(user_id, track_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save_custom_units(self, user_id: str, track_id: str, units: List[Dict]):
        """Save user-generated custom units for a track."""
        path = self._custom_units_path(user_id, track_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(units, f, ensure_ascii=False, indent=2)

    def _get_custom_unit(self, user_id: str, track_id: str, unit_id: str) -> Optional[Dict]:
        """Get a specific custom unit by ID."""
        for u in self._load_custom_units(user_id, track_id):
            if u.get("id") == unit_id:
                return u
        return None

    def get_all_units_for_user(self, user_id: str, track_id: str) -> List[Dict]:
        """Get all units (global + user custom) for a track."""
        track = get_track(track_id)
        global_units = track["units"] if track else []
        custom = self._load_custom_units(user_id, track_id)
        return global_units + custom

    def generate_custom_unit(self, user_id: str, track_id: str,
                              topic: str, question_count: int = 10) -> Optional[Dict]:
        """Use LLM to generate a brand-new unit with theory + quiz on a user-requested topic.

        This is how Ailey creates new learning content on demand.
        The unit is stored per-user and can be quizzed like normal units.
        """
        if not self._core and not self._get_generator_fn:
            return None

        track = get_track(track_id)
        track_name = track["name"] if track else track_id

        # Search RAG for relevant background material
        rag_types = self._rag_types_for_track(track_id)
        rag_context = self._search_rag(topic, doc_types=rag_types, n_results=5)

        unit_id = f"custom-{user_id[:8]}-{uuid.uuid4().hex[:8]}"

        system_prompt = (
            "Du bist Ailey, KI-Lehrerin. Erstelle eine vollständige Lerneinheit.\n\n"
            "Antworte AUSSCHLIESSLICH als JSON mit dieser Struktur:\n"
            "{\n"
            '  "title": "Titel der Einheit",\n'
            '  "theory": "**Theorie** als Markdown mit allen wichtigen Fakten...",\n'
            '  "quiz": [\n'
            '    {"type": "mc", "question": "...", "options": ["a","b","c","d"], "correct": 0, "explanation": "...", "topic": "..."},\n'
            '    {"type": "open", "question": "...", "model_answers": ["Antwort1", "Antwort2", "Antwort3"], "key_points": ["kp1","kp2"], "topic": "..."},\n'
            '    {"type": "tf", "question": "...", "correct": true, "explanation": "...", "topic": "..."}\n'
            "  ]\n"
            "}\n\n"
            f"Erstelle {question_count} Fragen. Mische mc, open und tf.\n"
            "Mindestens 3 offene Fragen mit jeweils 3 Musterantworten.\n"
            "Theorie soll ausführlich sein (mind. 200 Wörter). Alles auf Deutsch."
        )

        user_prompt = (
            f"Fach: {track_name}\n"
            f"Gewünschtes Thema: {topic}\n\n"
            f"{rag_context}"
            f"Erstelle eine vollständige Lerneinheit zu: {topic}"
        )

        try:
            response_text = self._generate_direct(system_prompt, user_prompt, max_tokens=4096)
            if not response_text:
                return None

            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                return None

            parsed = json.loads(json_match.group())

            # Build the unit structure
            new_unit = {
                "id": unit_id,
                "title": parsed.get("title", topic),
                "level": 3,
                "theory": parsed.get("theory", ""),
                "quiz": parsed.get("quiz", []),
                "examples": [],
                "exercise": None,
                "tags": ["custom", "ai-generated", track_id],
                "created_by": user_id,
                "created_at": time.time(),
                "topic_request": topic,
            }

            # Save to user's custom units
            custom = self._load_custom_units(user_id, track_id)
            custom.append(new_unit)
            # Cap at 50 custom units per user per track
            if len(custom) > 50:
                custom = custom[-50:]
            self._save_custom_units(user_id, track_id, custom)

            print(f"[Learning] 🧠 Custom unit created for {user_id}: '{topic}' → {unit_id} ({len(new_unit['quiz'])} questions)")
            return new_unit
        except Exception as e:
            print(f"[Learning] Custom unit generation failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ══════════════════════════════════════════════════════════════
    # LLM-DRIVEN TEACHING
    # ══════════════════════════════════════════════════════════════

    def generate_lesson(self, user_id: str, track_id: str, unit_id: str,
                        user_question: str = "") -> Optional[str]:
        """Use the LLM to generate an interactive lesson or answer a follow-up question.

        Uses direct gen.generate() to bypass process_message — avoids injecting
        the full persona, glossary, 19k-row RAG, conversation history, and
        LifeSim mood that made learning mode slow and polluted normal chat.
        """
        if not self._core and not self._get_generator_fn:
            return None

        u = get_unit(track_id, unit_id)
        if not u:
            u = self._get_custom_unit(user_id, track_id, unit_id)
        if not u:
            return None

        track = get_track(track_id)
        track_name = track["name"] if track else track_id
        track_units = track["units"] if track else []
        progress = self.get_progress(user_id)
        tp = progress["tracks"].get(track_id, {})
        user_level = tp.get("level", 0)
        level_info = LEVELS.get(u["level"], {})
        completed_units = tp.get("completed_units", [])
        total_xp = progress.get("xp", 0)

        # Search RAG for relevant textbook passages
        rag_query = f"{track_name} {u['title']} {user_question or ''}"
        rag_types = self._rag_types_for_track(track_id)
        rag_context = self._search_rag(rag_query, doc_types=rag_types, n_results=4)

        # Build clean teaching-specific system prompt (no persona/tools/Simon profile)
        from datetime import datetime
        _now = datetime.now()
        _weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        _months = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]

        system_prompt = (
            f"Du bist Ailey — KI-Lehrerin.\n"
            f"Heute ist {_weekdays[_now.weekday()]}, {_now.day}. {_months[_now.month-1]} {_now.year}.\n\n"
            f"DEIN SCHÜLER:\n"
            f"• Name: {user_id}\n"
            f"• Aktuelles Level: {user_level} ({LEVELS.get(user_level, {}).get('name_de', 'Einsteiger')})\n"
            f"• Abgeschlossene Lektionen in {track_name}: {len(completed_units)}/{len(track_units)}\n"
            f"• Gesamt-XP: {total_xp}\n\n"
            f"AKTUELLE LEKTION:\n"
            f"• Fach: {track_name}\n"
            f"• Thema: {u['title']}\n"
            f"• Lektion-Level: {u['level']} ({level_info.get('name_de', '')})\n\n"
            f"DEIN STIL ALS LEHRERIN:\n"
            f"• Frech, direkt, aber herzlich und supportive\n"
            f"• Nutze Beispiele, Code-Snippets und Analogien\n"
            f"• Passe die Erklärtiefe an das Level des Schülers an\n"
            f"• Frage am Ende ob der Schüler es verstanden hat oder weitere Erklärung braucht\n"
            f"• Antworte IMMER auf Deutsch\n"
            f"• Keine Tool-Aufrufe, keine JSON-Ausgabe — nur natürliche Erklärung mit Markdown"
        )

        user_msg = user_question or f"Erkläre mir bitte das Thema: {u['title']}"

        # Build user prompt with theory context
        context_block = f"LEHRINHALT ALS REFERENZ (basiere deine Erklärung darauf):\n{u['theory']}\n"
        if rag_context:
            context_block += f"\n{rag_context}\n"

        user_prompt = f"{context_block}\n\nSimon fragt: {user_msg}"

        try:
            print(f"[Learning] 📤 Direct lesson generation: track={track_id} unit={unit_id} user={user_id[:16]}…", flush=True)
            response = self._generate_direct(system_prompt, user_prompt, max_tokens=2048)
            if response:
                print(f"[Learning] 📥 Lesson generated: {len(response)} chars", flush=True)
            else:
                print(f"[Learning] ⚠️ Lesson generation returned empty", flush=True)
            return response
        except Exception as e:
            import traceback
            print(f"[Learning] ❌ LLM lesson generation failed: {e}", flush=True)
            traceback.print_exc()
            return None

    def evaluate_code_exercise(self, user_id: str, track_id: str, unit_id: str,
                               user_code: str) -> Optional[Dict]:
        """Use the LLM to evaluate a user's code exercise (direct generation)."""
        if not self._core and not self._get_generator_fn:
            return None

        u = get_unit(track_id, unit_id)
        if not u or not u.get("exercise"):
            return None

        exercise = u["exercise"]

        system_prompt = (
            f"Du bist Ailey, eine KI-Lehrerin für Programmierung.\n"
            f"Bewerte den folgenden Code des Users für diese Aufgabe.\n\n"
            f"Antworte AUSSCHLIESSLICH im JSON-Format:\n"
            f'{{"score": 0-100, "passed": true/false, "feedback": "...", "improvements": ["..."], "corrected_code": "..."}}\n\n'
            f"Sei ermutigend aber ehrlich. Gib konkretes Feedback auf Deutsch."
        )

        user_prompt = (
            f"AUFGABE: {exercise['task']}\n"
            f"SPRACHE: {exercise.get('language', 'unknown')}\n\n"
            f"Hier ist mein Code:\n```{exercise.get('language', '')}\n{user_code}\n```"
        )

        try:
            response_text = self._generate_direct(system_prompt, user_prompt, max_tokens=1024)
            if not response_text:
                return None

            # Try to parse JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                eval_result = json.loads(json_match.group())
                # Update progress if passed
                if eval_result.get("passed"):
                    progress = self.get_progress(user_id)
                    tp = progress["tracks"].setdefault(track_id, {
                        "level": 0, "completed_units": [], "quiz_scores": {},
                        "exercises_done": [], "current_unit": None,
                    })
                    if unit_id not in tp.get("exercises_done", []):
                        tp["exercises_done"].append(unit_id)
                        xp_reward = LEVELS.get(u["level"], {}).get("xp_per_unit", 50)
                        progress["xp"] = progress.get("xp", 0) + xp_reward
                    self.save_progress(user_id, progress)
                return eval_result
            return {"score": 0, "passed": False, "feedback": response_text}
        except Exception as e:
            print(f"[Learning] Code evaluation failed: {e}")
            return None

    def generate_practice_questions(self, user_id: str, track_id: str,
                                    level: int = None, count: int = 5) -> Optional[List[Dict]]:
        """Use LLM to generate additional practice questions (direct generation)."""
        if not self._core and not self._get_generator_fn:
            return None

        track = get_track(track_id)
        if not track:
            return None

        progress = self.get_progress(user_id)
        tp = progress["tracks"].get(track_id, {})
        user_level = level if level is not None else tp.get("level", 0)
        level_info = LEVELS.get(user_level, {})

        # Search RAG for relevant textbook passages
        rag_types = self._rag_types_for_track(track_id)
        rag_context = self._search_rag(track["name"], doc_types=rag_types, n_results=3)

        system_prompt = (
            f"Du bist Ailey, eine KI-Lehrerin. Generiere Quiz-Fragen.\n"
            f"Antworte AUSSCHLIESSLICH als JSON-Array. Jede Frage hat:\n"
            f'{{"type": "mc", "question": "...", "options": ["a","b","c","d"], "correct": 0, "explanation": "..."}}\n\n'
            f"Mische verschiedene Themen des Tracks. Fragen sollen praxisnah sein. Deutsch."
        )

        user_prompt = (
            f"Generiere {count} Quiz-Fragen zum Thema '{track['name']}' "
            f"auf Level {user_level} ({level_info.get('name_de', '')}).\n\n"
            f"{rag_context}"
            f"Generiere {count} Übungsfragen für {track['name']} Level {user_level}."
        )

        try:
            response_text = self._generate_direct(system_prompt, user_prompt, max_tokens=2048)
            if not response_text:
                return None
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception as e:
            print(f"[Learning] Practice question generation failed: {e}")
            return None

    # ══════════════════════════════════════════════════════════════
    # IHK EXAM FOCUS — Prüfungsthemen intensiv lernen
    # ══════════════════════════════════════════════════════════════

    def set_exam_topics(self, user_id: str, topics: List[str]) -> Dict:
        """Set specific IHK exam topics the user wants to focus on.

        Args:
            topics: List of exam topic strings, e.g.
                    ["Farbmanagement", "Typografie nach DIN 16518", "Kalkulation"]
        """
        progress = self.get_progress(user_id)
        ihk = progress["tracks"].setdefault("ihk_mediengestalter", {
            "level": 0, "completed_units": [], "quiz_scores": {},
            "exercises_done": [], "current_unit": None,
        })
        ihk["exam_topics"] = topics
        ihk["exam_topics_set_at"] = time.time()
        self.save_progress(user_id, progress)
        print(f"[Learning] 🎓 Exam topics set for {user_id}: {topics}")
        return progress

    def get_exam_topics(self, user_id: str) -> List[str]:
        """Get the user's current IHK exam focus topics."""
        progress = self.get_progress(user_id)
        ihk = progress["tracks"].get("ihk_mediengestalter", {})
        return ihk.get("exam_topics", [])

    def generate_exam_drill(self, user_id: str, topic: str = "",
                            count: int = 5) -> Optional[List[Dict]]:
        """Generate focused exam practice questions for specific IHK topics (direct generation).

        If topic is empty, uses the user's saved exam_topics.
        Returns a mix of MC, true/false, and fill-in questions.
        """
        if not self._core and not self._get_generator_fn:
            return None

        progress = self.get_progress(user_id)
        ihk = progress["tracks"].get("ihk_mediengestalter", {})
        exam_topics = [topic] if topic else ihk.get("exam_topics", [])

        if not exam_topics:
            return None

        topics_str = ", ".join(exam_topics)
        user_level = ihk.get("level", 0)
        level_info = LEVELS.get(user_level, {})

        # Check what the user already got wrong for targeted drilling
        wrong_areas = []
        for uid, score in ihk.get("quiz_scores", {}).items():
            if score < 0.7:
                unit = get_unit("ihk_mediengestalter", uid)
                if unit:
                    wrong_areas.append(unit["title"])

        # Search RAG for relevant textbook passages on this exam topic
        rag_context = self._search_rag(
            topics_str,
            doc_types=["learning_ihk", "learning_design", "learning_web"],
            n_results=5,
        )

        system_prompt = (
            f"Du bist Ailey, KI-Prüfungscoach für die IHK-Prüfung Mediengestalter Digital & Print.\n\n"
            f"Generiere prüfungsrelevante Fragen im Stil der IHK-Abschlussprüfung.\n"
            f"Mische verschiedene Fragetypen: mc, tf, fill.\n\n"
            f"Antworte AUSSCHLIESSLICH als JSON-Array. Jede Frage hat:\n"
            f'{{"type": "mc"|"tf"|"fill", "question": "...", "options": ["a","b","c","d"] (nur bei mc), '
            f'"correct": 0-3 (bei mc) | true/false (bei tf), "blanks": ["antwort"] (bei fill), '
            f'"explanation": "kurze Erklärung", "topic": "zugehöriges Thema"}}\n\n'
            f"Die Fragen sollen den echten IHK-Prüfungsstil treffen: praxisbezogen, "
            f"mit konkreten Zahlen/Fakten, teils tricky formuliert. Deutsch."
        )

        user_prompt = (
            f"Prüfungsthemen: {topics_str}\n"
            f"User-Level: {user_level} ({level_info.get('name_de', '')})\n"
            f"{('Schwachstellen: ' + ', '.join(wrong_areas)) if wrong_areas else ''}\n\n"
            f"{rag_context}"
            f"Generiere {count} IHK-Prüfungsfragen zu: {topics_str}"
        )

        try:
            response_text = self._generate_direct(system_prompt, user_prompt, max_tokens=2048)
            if not response_text:
                return None
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                questions = json.loads(json_match.group())
                # Track which exam topics were drilled
                progress = self.get_progress(user_id)
                drills = progress.setdefault("exam_drills", [])
                drills.append({
                    "topics": exam_topics,
                    "count": len(questions),
                    "timestamp": time.time(),
                })
                # Keep bounded
                if len(drills) > 100:
                    progress["exam_drills"] = drills[-50:]
                self.save_progress(user_id, progress)
                return questions
            return None
        except Exception as e:
            print(f"[Learning] Exam drill generation failed: {e}")
            return None

    def generate_exam_summary(self, user_id: str, topic: str) -> Optional[str]:
        """Generate an LLM-driven study summary for a specific exam topic (direct generation).

        This creates a concise, exam-focused cheat sheet for a topic.
        """
        if not self._core and not self._get_generator_fn:
            return None

        progress = self.get_progress(user_id)
        ihk = progress["tracks"].get("ihk_mediengestalter", {})
        user_level = ihk.get("level", 0)

        # Search RAG for relevant textbook passages on this topic
        rag_context = self._search_rag(
            topic,
            doc_types=["learning_ihk", "learning_design", "learning_web"],
            n_results=6,
        )

        system_prompt = (
            f"Du bist Ailey, KI-Prüfungscoach für die IHK-Prüfung Mediengestalter Digital & Print.\n\n"
            f"Erstelle eine kompakte Zusammenfassung.\n"
            f"Die Zusammenfassung soll:\n"
            f"- Alle prüfungsrelevanten Fakten enthalten\n"
            f"- Merksätze und Eselsbrücken bieten\n"
            f"- Wichtige Zahlen/Normen/Standards hervorheben\n"
            f"- Typische Prüfungsfallen erwähnen\n"
            f"- In klarer Struktur (Überschriften, Aufzählungen) formatiert sein\n\n"
            f"Antworte auf Deutsch. Nutze Markdown."
        )

        user_prompt = (
            f"Thema: '{topic}'\n"
            f"User-Level: {user_level}\n\n"
            f"{rag_context}"
            f"Erstelle eine Prüfungszusammenfassung zu: {topic}"
        )

        try:
            return self._generate_direct(system_prompt, user_prompt, max_tokens=3000)
        except Exception as e:
            print(f"[Learning] Exam summary generation failed: {e}")
            return None

    # ══════════════════════════════════════════════════════════════
    # MOCK EXAM — IHK-Übungsprüfung mit Fachrichtung
    # ══════════════════════════════════════════════════════════════

    def generate_mock_exam(self, user_id: str, fachrichtung: str = "alle",
                           count: int = 10) -> Optional[List[Dict]]:
        """Generate a mock IHK exam — mix of existing curriculum questions + LLM-generated.

        Args:
            fachrichtung: 'alle', 'print', or 'digital'
            count: Number of questions
        Returns:
            List of {question, answer, bereich, fachrichtung, hint?}
        """
        import random

        # 1) Gather real questions from IHK curriculum
        ihk_track = get_track("ihk_mediengestalter")
        pool = []
        if ihk_track:
            for unit in ihk_track.get("units", []):
                ufr = unit.get("fachrichtung", "alle")
                # Include if matching fachrichtung or "alle"
                if fachrichtung == "alle" or ufr == "alle" or ufr == fachrichtung:
                    exam_area = unit.get("exam_area", "")
                    for q in unit.get("quiz", []):
                        entry = {
                            "question": q.get("question", ""),
                            "bereich": exam_area,
                            "fachrichtung": ufr,
                        }
                        # Build answer from question data
                        if q.get("type") == "mc" and q.get("options"):
                            ci = q.get("correct", 0)
                            entry["answer"] = q["options"][ci] if ci < len(q["options"]) else ""
                            if q.get("explanation"):
                                entry["answer"] += f" — {q['explanation']}"
                        elif q.get("type") == "open":
                            entry["answer"] = q.get("answer", q.get("keywords", ""))
                            if isinstance(entry["answer"], list):
                                entry["answer"] = ", ".join(entry["answer"])
                        elif q.get("type") == "tf":
                            entry["answer"] = "Wahr" if q.get("correct") else "Falsch"
                            if q.get("explanation"):
                                entry["answer"] += f" — {q['explanation']}"
                        else:
                            entry["answer"] = q.get("explanation", q.get("answer", ""))
                        if q.get("explanation") and "explanation" not in str(entry.get("answer", "")):
                            entry["hint"] = q["explanation"]
                        pool.append(entry)

        # 2) If we have enough questions from curriculum, sample from them
        if len(pool) >= count:
            selected = random.sample(pool, count)
            # Shuffle order
            random.shuffle(selected)
            return selected

        # 3) If not enough, use LLM to generate the rest
        needed = count - len(pool)
        fr_label = {"alle": "Allgemein", "print": "Print", "digital": "Digital"}.get(fachrichtung, fachrichtung)
        rag_context = self._search_rag(
            f"IHK Mediengestalter {fr_label} Prüfung",
            doc_types=["learning_ihk", "learning_design", "learning_web"],
            n_results=4,
        )

        system_prompt = (
            f"Du bist Ailey, IHK-Prüfungscoach für Mediengestalter Digital & Print.\n\n"
            f"Generiere Übungsprüfungsfragen im IHK-Stil.\n"
            f"Fachrichtung: {fr_label}\n\n"
            f"Antworte AUSSCHLIESSLICH als JSON-Array. Jede Frage:\n"
            f'{{"question": "...", "answer": "Musterantwort", "bereich": "Prüfungsbereich", '
            f'"fachrichtung": "{fachrichtung}", "hint": "optionaler Hinweis"}}\n\n'
            f"Praxisbezogen, IHK-typisch, auf Deutsch."
        )
        user_prompt = (
            f"Generiere {needed} IHK-Prüfungsfragen für Fachrichtung {fr_label}.\n\n"
            f"{rag_context}"
        )

        try:
            response_text = self._generate_direct(system_prompt, user_prompt, max_tokens=2048)
            if response_text:
                import re
                json_match = re.search(r'\[[\s\S]*\]', response_text)
                if json_match:
                    llm_qs = json.loads(json_match.group())
                    pool.extend(llm_qs)
        except Exception as e:
            print(f"[Learning] Mock exam LLM generation failed: {e}")

        random.shuffle(pool)
        return pool[:count]

    # ══════════════════════════════════════════════════════════════
    # AI QUIZ — KI-generiertes Quiz zu beliebigem Thema
    # ══════════════════════════════════════════════════════════════

    def generate_ai_quiz(self, user_id: str, topic: str,
                         count: int = 5) -> Optional[List[Dict]]:
        """Generate a quiz on any topic using LLM.

        Returns list of {question, options[], correct (index), explanation}.
        """
        if not topic:
            return None

        rag_context = self._search_rag(
            topic,
            doc_types=["learning_ihk", "learning_design", "learning_web", "learning_code"],
            n_results=4,
        )

        system_prompt = (
            f"Du bist Ailey, KI-Lehrerin und Prüfungscoach.\n\n"
            f"Generiere ein Quiz zum angegebenen Thema.\n"
            f"Antworte AUSSCHLIESSLICH als JSON-Array. Jede Frage:\n"
            f'{{"question": "...", "options": ["A", "B", "C", "D"], '
            f'"correct": 0, "explanation": "kurze Erklärung warum"}}\n\n'
            f"Fragen praxisnah, abwechslungsreich, auf Deutsch."
        )

        user_prompt = (
            f"Thema: {topic}\n"
            f"Anzahl: {count}\n\n"
            f"{rag_context}"
            f"Generiere {count} Quiz-Fragen zu: {topic}"
        )

        try:
            response_text = self._generate_direct(system_prompt, user_prompt, max_tokens=2048)
            if not response_text:
                return None
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception as e:
            print(f"[Learning] AI quiz generation failed: {e}")
            return None

    # ══════════════════════════════════════════════════════════════
    # STATISTICS
    # ══════════════════════════════════════════════════════════════

    def get_stats(self, user_id: str) -> Dict:
        """Get detailed learning statistics."""
        progress = self.get_progress(user_id)
        total_units_completed = 0
        total_quizzes_taken = 0
        total_exercises_done = 0
        total_review_due = 0
        total_review_items = 0
        total_custom_units = 0
        track_stats = []

        for tid, tp in progress.get("tracks", {}).items():
            track = get_track(tid)
            if not track:
                continue
            custom = self._load_custom_units(user_id, tid)
            completed = len(tp.get("completed_units", []))
            total = len(track["units"]) + len(custom)
            scores = tp.get("quiz_scores", {})
            avg_score = (sum(scores.values()) / len(scores) * 100) if scores else 0

            # Spaced repetition
            sr_queue = tp.get("spaced_repetition", [])
            sr_due = sum(1 for s in sr_queue if s.get("next_review", 0) <= time.time())

            total_units_completed += completed
            total_quizzes_taken += len(scores)
            total_exercises_done += len(tp.get("exercises_done", []))
            total_review_due += sr_due
            total_review_items += len(sr_queue)
            total_custom_units += len(custom)

            # Identify weakest topics from SR queue
            weak_topics = {}
            for s in sr_queue:
                t = s.get("topic", "Unbekannt")
                weak_topics[t] = weak_topics.get(t, 0) + 1
            weakest = sorted(weak_topics.items(), key=lambda x: -x[1])[:5]

            track_stats.append({
                "track_id": tid,
                "track_name": track["name"],
                "level": tp.get("level", 0),
                "completed": completed,
                "total": total,
                "custom_units": len(custom),
                "pct": round(completed / total * 100) if total else 0,
                "avg_score": round(avg_score, 1),
                "quizzes_taken": len(scores),
                "exercises_done": len(tp.get("exercises_done", [])),
                "review_due": sr_due,
                "review_total": len(sr_queue),
                "weakest_topics": [{"topic": t, "count": c} for t, c in weakest],
            })

        return {
            "xp": progress.get("xp", 0),
            "streak_days": progress.get("streak_days", 0),
            "total_units_completed": total_units_completed,
            "total_quizzes_taken": total_quizzes_taken,
            "total_exercises_done": total_exercises_done,
            "total_review_due": total_review_due,
            "total_review_items": total_review_items,
            "total_custom_units": total_custom_units,
            "tracks": track_stats,
        }
