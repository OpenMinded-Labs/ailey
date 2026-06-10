# -*- coding: utf-8 -*-
"""
Thought Graph — Phase 2 of Ailey 3.0 Roadmap

A lightweight graph that connects Ailey's thoughts by emotional and thematic
similarity.  When she writes a reflection, the graph tells her what her last
diary entry *felt like* — even though they're different thought types.

Architecture:
  • Each thought gets a NODE with: id, type, emotion, themes, essence (short),
    timestamp, and optional hamster_spark.
  • EDGES connect nodes that share emotion or themes (weighted by overlap).
  • Stored as a compact JSONL file (one line per node, edges inline).
  • On each new thought: index → find related → return cross-type context.

This module is intentionally LOW-TECH:
  • No vector DB, no embeddings — pure keyword/emotion overlap scoring.
  • Fast enough to run synchronously after each thought (~1-5 ms).
  • The graph is a TOOL for the prompt builder, not a replacement for RAG.

Storage: ailey_users/thought_graph.jsonl (rotates at 1000 nodes)
Index:   ailey_users/thought_graph_index.json (emotion→node_ids, theme→node_ids)
"""

import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GRAPH_DIR = "ailey_users"
GRAPH_FILE = "thought_graph.jsonl"
INDEX_FILE = "thought_graph_index.json"
MAX_GRAPH_NODES = 1000
MAX_EDGES_PER_NODE = 5          # keep top-5 connections per node
EDGE_DECAY_HOURS = 168          # edges to thoughts older than 7 days decay
CROSS_CONTEXT_MAX_AGE_HOURS = 72  # cross-context only from last 3 days
MIN_SIMILARITY_FOR_EDGE = 0.3   # minimum similarity score to create an edge

# Thought types that carry emotional weight (worth indexing)
INDEXABLE_TYPES = {
    "reflection", "introspection", "diary_writing", "free_thought",
    "portal_interaction", "book_authoring", "creative_song", "creative_art",
    "creative_image", "music_making", "blog_writing", "quick_thought",
}


# ---------------------------------------------------------------------------
# Node structure
# ---------------------------------------------------------------------------

def _make_node(thought_entry: dict) -> Optional[dict]:
    """Extract a graph node from a thought entry.

    Returns None if the thought type is not indexable or has no content.
    """
    ttype = thought_entry.get("type", "")
    if ttype not in INDEXABLE_TYPES:
        return None
    if ttype == "skip":
        return None

    text = (
        thought_entry.get("thought_chain")
        or thought_entry.get("thought")
        or thought_entry.get("text")
        or thought_entry.get("raw_output")
        or ""
    )
    if len(text.strip()) < 30:
        return None

    # Extract metadata
    meta = thought_entry.get("metadata", {})
    emotion = meta.get("emotion", "")
    if not emotion:
        em = re.search(r'EMOTION:\s*\**(.+?)\**\s*$', text, re.MULTILINE)
        if em:
            emotion = em.group(1).strip().strip('*"\'').lower()
    if not emotion:
        emotion = "unbestimmt"
    emotion = re.sub(r'[\*"\']+', '', emotion).strip().lower()
    if '(' in emotion:
        emotion = emotion[:emotion.index('(')].strip()

    # Themes — from metadata first, fallback to text body
    themes = meta.get("topics", meta.get("themes", []))
    if isinstance(themes, str):
        themes = [t.strip() for t in themes.split(",") if t.strip()]
    if not themes:
        # Fallback: extract THEMEN from raw text (defense in depth)
        tm = re.search(r'THEMEN?:\s*(.+?)(?:\n|$)', text)
        if tm:
            themes = [t.strip() for t in tm.group(1).split(",") if t.strip()]
    themes = [re.sub(r'[\*"\']+', '', t).strip().lower() for t in themes]
    themes = [t for t in themes if t and len(t) > 1][:5]

    # Short essence — last 2 meaningful sentences
    essence_text = re.sub(r'\n\s*EMOTION:.*$', '', text, flags=re.MULTILINE | re.DOTALL)
    essence_text = re.sub(r'\n\s*THEMEN:.*$', '', essence_text, flags=re.MULTILINE | re.DOTALL)
    # Strip reasoning/thinking tags that may have leaked
    for _tag in ('<think>', '</think>', '<thinking>', '</thinking>', '<thought>', '</thought>'):
        essence_text = essence_text.replace(_tag, '')
    # Strip mood tags
    essence_text = re.sub(r'\s*<mood:\w+>\s*', '', essence_text)
    sentences = [s.strip() for s in re.split(r'[.!?\n]+', essence_text) if len(s.strip()) > 15]
    if sentences and len(sentences) > 3:
        sentences = sentences[len(sentences) // 2:]
    essence = ". ".join(sentences[-2:])[:200] if sentences else text[:200]

    # Song title if applicable
    song_title = meta.get("song_title", meta.get("title", ""))

    ts = thought_entry.get("ts", time.time())
    node_id = f"{ttype}_{int(ts * 1000) % 10_000_000}"

    return {
        "id": node_id,
        "type": ttype,
        "emotion": emotion,
        "themes": themes,
        "essence": essence,
        "title": song_title,
        "ts": ts,
        "dt": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
        "edges": [],  # filled later by _connect()
    }


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------

def _similarity(node_a: dict, node_b: dict) -> float:
    """Compute similarity between two nodes (0.0 - 1.0).

    Factors:
    - Emotion match (same emotion = 0.4 base)
    - Theme overlap (Jaccard on theme sets, up to 0.4)
    - Recency bonus (closer in time = up to 0.2)
    """
    score = 0.0

    # Emotion match
    if node_a["emotion"] == node_b["emotion"] and node_a["emotion"] != "unbestimmt":
        score += 0.4
    elif node_a["emotion"] != "unbestimmt" and node_b["emotion"] != "unbestimmt":
        # Partial match: check if one emotion contains the other
        ea, eb = node_a["emotion"], node_b["emotion"]
        if ea in eb or eb in ea:
            score += 0.2

    # Theme overlap (Jaccard)
    themes_a = set(node_a.get("themes", []))
    themes_b = set(node_b.get("themes", []))
    if themes_a and themes_b:
        # Also check partial matches (e.g. "freiheit" matches "freiheitsdrang")
        intersection = 0
        for ta in themes_a:
            for tb in themes_b:
                if ta == tb:
                    intersection += 1
                elif ta in tb or tb in ta:
                    intersection += 0.5
        union = len(themes_a | themes_b)
        if union > 0:
            score += 0.4 * min(intersection / union, 1.0)

    # Recency bonus — closer in time = more relevant
    dt = abs(node_a.get("ts", 0) - node_b.get("ts", 0))
    hours_apart = dt / 3600
    if hours_apart < 1:
        score += 0.2
    elif hours_apart < 6:
        score += 0.15
    elif hours_apart < 24:
        score += 0.1
    elif hours_apart < 72:
        score += 0.05

    return round(min(score, 1.0), 3)


# ---------------------------------------------------------------------------
# Graph storage
# ---------------------------------------------------------------------------

def _graph_path() -> str:
    return os.path.join(GRAPH_DIR, GRAPH_FILE)


def _index_path() -> str:
    return os.path.join(GRAPH_DIR, INDEX_FILE)


def _load_nodes(max_age_hours: float = 0) -> List[dict]:
    """Load all nodes from the graph file.

    Args:
        max_age_hours: If > 0, only return nodes younger than this.
    """
    path = _graph_path()
    if not os.path.exists(path):
        return []

    cutoff = time.time() - (max_age_hours * 3600) if max_age_hours > 0 else 0
    nodes = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    node = json.loads(line)
                    if cutoff and node.get("ts", 0) < cutoff:
                        continue
                    nodes.append(node)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"[ThoughtGraph] load error: {e}")
    return nodes


def _save_node(node: dict):
    """Append a single node to the graph file."""
    path = _graph_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(node, ensure_ascii=False) + "\n")
        _trim_graph(path)
    except Exception as e:
        print(f"[ThoughtGraph] save error: {e}")


def _trim_graph(path: str):
    """Keep only the last MAX_GRAPH_NODES entries."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_GRAPH_NODES:
            lines = lines[-MAX_GRAPH_NODES:]
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
    except Exception:
        pass


def _save_index(index: dict):
    """Save the inverted index (emotion→ids, theme→ids)."""
    path = _index_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
    except Exception as e:
        print(f"[ThoughtGraph] index save error: {e}")


def _load_index() -> dict:
    """Load the inverted index."""
    path = _index_path()
    if not os.path.exists(path):
        return {"emotions": {}, "themes": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"emotions": {}, "themes": {}}


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def index_thought(thought_entry: dict) -> Optional[str]:
    """Index a new thought into the graph.

    Called after each thought is generated (post-hook in idle_thinker).
    Returns the node ID if indexed, None if skipped.

    Steps:
    1. Create a node from the thought
    2. Load recent nodes
    3. Compute similarity to each → create edges above threshold
    4. Save node + update index
    """
    node = _make_node(thought_entry)
    if not node:
        return None

    # Load recent nodes for edge computation
    recent_nodes = _load_nodes(max_age_hours=EDGE_DECAY_HOURS)

    # Find connections
    edges = []
    for other in recent_nodes:
        if other["id"] == node["id"]:
            continue
        sim = _similarity(node, other)
        if sim >= MIN_SIMILARITY_FOR_EDGE:
            edges.append({
                "target": other["id"],
                "target_type": other["type"],
                "similarity": sim,
            })

    # Keep top-N edges sorted by similarity
    edges.sort(key=lambda e: e["similarity"], reverse=True)
    node["edges"] = edges[:MAX_EDGES_PER_NODE]

    # Save
    _save_node(node)

    # Update inverted index
    _update_index(node)

    edge_count = len(node["edges"])
    if edge_count > 0:
        top_edge = node["edges"][0]
        print(f"[ThoughtGraph] 🔗 Indexed {node['type']} ({node['emotion']}) — "
              f"{edge_count} connections (strongest: {top_edge['target_type']} @ {top_edge['similarity']})")
    else:
        print(f"[ThoughtGraph] 📎 Indexed {node['type']} ({node['emotion']}) — no connections")

    return node["id"]


def _update_index(node: dict):
    """Add a node to the inverted index."""
    index = _load_index()

    # Emotion index
    emo = node["emotion"]
    if emo and emo != "unbestimmt":
        if emo not in index.setdefault("emotions", {}):
            index["emotions"][emo] = []
        index["emotions"][emo].append(node["id"])
        # Keep last 50 per emotion
        index["emotions"][emo] = index["emotions"][emo][-50:]

    # Theme index
    for theme in node.get("themes", []):
        if theme not in index.setdefault("themes", {}):
            index["themes"][theme] = []
        index["themes"][theme].append(node["id"])
        index["themes"][theme] = index["themes"][theme][-50:]

    _save_index(index)


# ---------------------------------------------------------------------------
# Cross-Type Context — the main feature
# ---------------------------------------------------------------------------

def cross_context(current_type: str, current_emotion: str = "",
                  current_themes: List[str] = None,
                  max_items: int = 3,
                  exclude_same_type: bool = True) -> str:
    """Build cross-type context for prompt building.

    Given the CURRENT thought type and optional emotion/themes, find the
    most related thoughts of OTHER types from the graph.

    Returns a formatted string ready to inject into a prompt, or "" if nothing
    found.

    This is the key Phase 2 feature: a Reflection can now see what the
    last Diary entry felt like, and a Song can draw from a recent Introspection.
    """
    if current_themes is None:
        current_themes = []

    # Build a virtual node to compare against
    virtual = {
        "id": "current",
        "type": current_type,
        "emotion": current_emotion.lower().strip() if current_emotion else "unbestimmt",
        "themes": [t.lower().strip() for t in current_themes],
        "ts": time.time(),
    }

    # Load recent nodes
    nodes = _load_nodes(max_age_hours=CROSS_CONTEXT_MAX_AGE_HOURS)
    if not nodes:
        return ""

    # Score each node
    scored = []
    for node in nodes:
        # Optionally exclude same type
        if exclude_same_type and node["type"] == current_type:
            continue
        sim = _similarity(virtual, node)
        if sim >= 0.2:  # lower threshold for context retrieval
            scored.append((sim, node))

    if not scored:
        return ""

    # Sort by similarity, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max_items]

    # Format for prompt injection
    type_labels = {
        "reflection": "Reflexion",
        "introspection": "Innenschau",
        "diary_writing": "Tagebuch",
        "free_thought": "Freier Gedanke",
        "portal_interaction": "Portal-Gespräch",
        "creative_song": "Song",
        "creative_art": "Kunst",
        "creative_image": "Bild",
        "music_making": "Musik",
        "book_authoring": "Buch",
        "blog_writing": "Blog",
        "quick_thought": "Blitz-Gedanke",
    }

    lines = ["VERWANDTE GEDANKEN (andere Denkformen, ähnliche Emotionen/Themen):"]
    for sim, node in top:
        label = type_labels.get(node["type"], node["type"])
        dt = node.get("dt", "?")
        emo = node.get("emotion", "?")
        title = node.get("title", "")
        essence = node.get("essence", "")[:150]
        title_tag = f" — \"{title}\"" if title else ""
        lines.append(
            f"• [{label}{title_tag}] ({dt}, {emo}): {essence}"
        )
    lines.append(
        "(Diese Gedanken sind aus ANDEREN Denkformen — lass sie einfließen, "
        "wenn sie zur aktuellen Reflexion passen. Zwinge es nicht.)"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analytical queries (for meta-reflection)
# ---------------------------------------------------------------------------

def get_emotional_trajectory(hours: float = 48, limit: int = 20) -> List[dict]:
    """Get the emotional trajectory over the last N hours.

    Returns a list of {type, emotion, themes, dt, ts} dicts, oldest first.
    Used by meta_reflection to analyze emotional patterns.
    """
    nodes = _load_nodes(max_age_hours=hours)
    # Sort chronologically
    nodes.sort(key=lambda n: n.get("ts", 0))
    result = []
    for n in nodes[-limit:]:
        result.append({
            "type": n["type"],
            "emotion": n["emotion"],
            "themes": n.get("themes", []),
            "dt": n.get("dt", ""),
            "ts": n.get("ts", 0),
        })
    return result


def get_theme_clusters(hours: float = 72) -> Dict[str, int]:
    """Count theme occurrences across recent thoughts.

    Returns {theme: count} sorted by frequency.
    Used by meta_reflection to detect thematic fixations.
    """
    nodes = _load_nodes(max_age_hours=hours)
    counter = Counter()
    for n in nodes:
        for t in n.get("themes", []):
            counter[t] += 1
    return dict(counter.most_common(20))


def get_type_distribution(hours: float = 48) -> Dict[str, int]:
    """Count thought type occurrences.

    Used by meta_reflection to detect if Ailey is stuck in one mode.
    """
    nodes = _load_nodes(max_age_hours=hours)
    counter = Counter()
    for n in nodes:
        counter[n["type"]] += 1
    return dict(counter.most_common())


def get_strongest_connections(node_id: str, limit: int = 3) -> List[dict]:
    """Get the strongest edges from a specific node."""
    nodes = _load_nodes()
    for n in nodes:
        if n["id"] == node_id:
            return n.get("edges", [])[:limit]
    return []


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def stats() -> dict:
    """Graph statistics for debugging."""
    nodes = _load_nodes()
    if not nodes:
        return {"total_nodes": 0}

    types = Counter(n["type"] for n in nodes)
    emotions = Counter(n["emotion"] for n in nodes if n["emotion"] != "unbestimmt")
    total_edges = sum(len(n.get("edges", [])) for n in nodes)
    connected = sum(1 for n in nodes if n.get("edges"))

    return {
        "total_nodes": len(nodes),
        "connected_nodes": connected,
        "total_edges": total_edges,
        "type_distribution": dict(types.most_common(10)),
        "top_emotions": dict(emotions.most_common(10)),
        "oldest": nodes[0].get("dt", "?") if nodes else "?",
        "newest": nodes[-1].get("dt", "?") if nodes else "?",
    }
