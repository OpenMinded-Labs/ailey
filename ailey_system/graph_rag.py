# -*- coding: utf-8 -*-
"""
GraphRAG — Lightweight knowledge graph addon for Ailey's RAG system.

Uses NetworkX (in-memory) for relational queries:
  - "Wer kennt König Ragnar?"
  - "Welche Ereignisse passierten in Loras?"
  - "Wie hängen Byxie und Runenmagie zusammen?"

Does NOT replace LanceDB vector RAG — it's a complementary layer.

Architecture:
  Query → ① LanceDB vector search (existing)
        → ② GraphRAG traversal (this module)
        → merged context → LLM

Graph is persisted as JSON, rebuilt from _IMPORT/ JSONs + people_glossary.
"""
import json
import os
import re
import time
from typing import Dict, List, Any, Optional, Set, Tuple
from collections import defaultdict

try:
    import networkx as nx
except ImportError:
    nx = None
    print("[GraphRAG] ⚠️ networkx not installed — graph features disabled")

# ══════════════════════════════════════════════════════════════════════════
#  PATHS
# ══════════════════════════════════════════════════════════════════════════
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IMPORT_DIR = os.path.join(_BASE_DIR, "_IMPORT")
_GLOSSARY_PATH = os.path.join(_BASE_DIR, "ailey_users", "people_glossary.json")
_GRAPH_CACHE_PATH = os.path.join(_BASE_DIR, "ailey_users", "knowledge_graph.json")

# ══════════════════════════════════════════════════════════════════════════
#  EDGE TYPES
# ══════════════════════════════════════════════════════════════════════════
EDGE_TYPES = {
    "lebt_in",          # Person → Ort
    "geboren_in",       # Person → Ort
    "gehört_zu",        # Person → Fraktion/Gruppierung
    "anführer_von",     # Person → Gruppierung
    "mitglied_von",     # Person → Gruppierung
    "beteiligte_an",    # Person → Ereignis
    "ereignis_in",      # Ereignis → Ort
    "nutzt",            # Person → Magie/Technologie/Gegenstand
    "hauptsitz_in",     # Gruppierung → Ort
    "teil_von",         # Ort → Region
    "spezies",          # Person → Spezies
    "kennt",            # Person → Person (from people_glossary)
    "erwähnt_in",       # Entity → Diary/Chat context
    "verwandt_mit",     # Person → Person
    "projekt",          # Entry → Projekt (Byxie/Marybeth/etc)
    # ── Emotional Memory Layer ──
    "erlebte",          # Person → Milestone/Erlebnis (emotional moment)
    "fühlte",           # Person → Emotion (in context of an event)
    "wünscht_sich",     # Person → Wunsch/Ziel
    "scherz_mit",       # Person → InsideJoke
    "teilt_mit",        # Person → SharedMemory
    "vertraut",         # Person → Person (trust relationship)
    "liebt",            # Person → Person (romantic bond)
    "inspiriert_von",   # Person → Kreativ-Moment
    "reflektierte",     # Ailey → Gedanke/Erkenntnis
}


# ══════════════════════════════════════════════════════════════════════════
#  HELPERS: Extract entity names from HTML-rich text fields
# ══════════════════════════════════════════════════════════════════════════
_HTML_TAG_RE = re.compile(r'<[^>]+>')
_PAREN_RE = re.compile(r'\([^)]*\)')


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    if not text:
        return ""
    return _HTML_TAG_RE.sub('', text).strip()


def _normalize_name(name: str) -> str:
    """Normalize an entity name for graph node ID."""
    name = _strip_html(name).strip()
    name = _PAREN_RE.sub('', name).strip()
    # Remove trailing punctuation
    name = name.rstrip('.,;:!?')
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _node_id(name: str) -> str:
    """Create a canonical node ID from a name."""
    n = _normalize_name(name).lower()
    # Replace special chars
    n = re.sub(r'[^a-zäöüß0-9\s]', '', n)
    n = re.sub(r'\s+', '_', n).strip('_')
    return n


def _split_names_from_html(html_text: str) -> List[str]:
    """Extract individual names/entities from an HTML paragraph.
    
    Handles patterns like:
    '<p>König Ragnar, Byxie Byx, Der namenlose Sultan</p>'
    """
    text = _strip_html(html_text)
    if not text:
        return []
    # Split on comma, 'und', 'and', semicolons
    parts = re.split(r'[,;]\s*|\s+und\s+|\s+and\s+', text)
    names = []
    for p in parts:
        p = p.strip().rstrip('.,;:!?').strip()
        if len(p) >= 2 and len(p) <= 80:
            # Skip very generic words
            if p.lower() not in ('die', 'der', 'das', 'ein', 'eine', 'und', 'oder',
                                  'verschiedene', 'andere', 'weitere', 'diverse',
                                  'viele', 'einige', 'alle', 'keine'):
                names.append(_normalize_name(p))
    return names


# ══════════════════════════════════════════════════════════════════════════
#  MAIN CLASS
# ══════════════════════════════════════════════════════════════════════════
class AileyGraphRAG:
    """Lightweight in-memory knowledge graph backed by NetworkX."""

    def __init__(self, auto_load: bool = True):
        if nx is None:
            raise ImportError("networkx required: pip install networkx")
        self.G = nx.MultiDiGraph()  # type: ignore[union-attr]
        self._build_time: float = 0
        self._node_count: int = 0
        self._edge_count: int = 0
        if auto_load:
            if os.path.isfile(_GRAPH_CACHE_PATH):
                self._load_cache()
            else:
                self.rebuild()

    # ── Persistence ───────────────────────────────────────────────────
    def _save_cache(self):
        """Save graph to JSON cache."""
        data = {
            "nodes": [],
            "edges": [],
            "meta": {
                "build_time": self._build_time,
                "node_count": self.G.number_of_nodes(),
                "edge_count": self.G.number_of_edges(),
                "saved_at": time.time(),
            }
        }
        for nid, attrs in self.G.nodes(data=True):
            data["nodes"].append({"id": nid, **attrs})
        for u, v, key, attrs in self.G.edges(data=True, keys=True):
            data["edges"].append({"src": u, "dst": v, "key": key, **attrs})

        os.makedirs(os.path.dirname(_GRAPH_CACHE_PATH), exist_ok=True)
        with open(_GRAPH_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print(f"[GraphRAG] 💾 Saved: {self.G.number_of_nodes()} nodes, "
              f"{self.G.number_of_edges()} edges → {_GRAPH_CACHE_PATH}")

    def _load_cache(self):
        """Load graph from JSON cache."""
        try:
            with open(_GRAPH_CACHE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.G.clear()
            for node in data.get("nodes", []):
                nid = node.pop("id")
                self.G.add_node(nid, **node)
            for edge in data.get("edges", []):
                src = edge.pop("src")
                dst = edge.pop("dst")
                key = edge.pop("key", None)
                self.G.add_edge(src, dst, key=key, **edge)
            meta = data.get("meta", {})
            self._build_time = meta.get("build_time", 0)
            self._node_count = self.G.number_of_nodes()
            self._edge_count = self.G.number_of_edges()
            print(f"[GraphRAG] ✅ Loaded from cache: {self._node_count} nodes, "
                  f"{self._edge_count} edges (built {time.strftime('%Y-%m-%d %H:%M', time.localtime(meta.get('saved_at', 0)))})")
        except Exception as e:
            print(f"[GraphRAG] ⚠️ Cache load failed: {e} — rebuilding")
            self.rebuild()

    # ── Node management ───────────────────────────────────────────────
    def _add_node(self, name: str, node_type: str, project: str = "",
                  **extra) -> str:
        """Add or update a node. Returns the node ID."""
        nid = _node_id(name)
        if not nid or len(nid) < 2:
            return ""
        if self.G.has_node(nid):
            # Merge attributes (don't overwrite existing with empty)
            attrs = self.G.nodes[nid]
            for k, v in extra.items():
                if v and not attrs.get(k):
                    attrs[k] = v
            # Add project tag
            if project:
                projs = set(attrs.get("projects", "").split(",")) if attrs.get("projects") else set()
                projs.add(project)
                projs.discard("")
                attrs["projects"] = ",".join(sorted(projs))
        else:
            attrs = {"label": _normalize_name(name), "type": node_type, **extra}
            if project:
                attrs["projects"] = project
            self.G.add_node(nid, **attrs)
        return nid

    def _add_edge(self, src_id: str, dst_id: str, relation: str,
                  **extra) -> bool:
        """Add an edge if both nodes exist."""
        if not src_id or not dst_id or src_id == dst_id:
            return False
        if not self.G.has_node(src_id) or not self.G.has_node(dst_id):
            return False
        # Check for duplicate
        if self.G.has_edge(src_id, dst_id):
            for _, _, data in self.G.edges(src_id, data=True):
                if data.get("relation") == relation:
                    return False  # Already exists
        self.G.add_edge(src_id, dst_id, relation=relation, **extra)
        return True

    # ── Build from _IMPORT JSONs ──────────────────────────────────────
    def rebuild(self):
        """Rebuild the entire graph from _IMPORT/ JSONs + people_glossary + emotional memories."""
        t0 = time.time()
        self.G.clear()
        print("[GraphRAG] 🔄 Rebuilding knowledge graph…")

        # 1. Import all _IMPORT/ JSON wiki files
        self._import_wiki_files()

        # 2. Import people_glossary (real-world people)
        self._import_people_glossary()

        # 3. Import Ailey's emotional memory layer
        self._import_emotional_memories()

        self._build_time = time.time() - t0
        self._node_count = self.G.number_of_nodes()
        self._edge_count = self.G.number_of_edges()
        print(f"[GraphRAG] ✅ Built: {self._node_count} nodes, {self._edge_count} edges "
              f"in {self._build_time:.1f}s")

        self._save_cache()

    def _detect_project(self, filepath: str) -> str:
        """Detect which project a file belongs to based on path."""
        fp = filepath.lower()
        if "byxie" in fp:
            return "byxie_byx"
        elif "martyria" in fp:
            return "martyria"
        elif "marybeth 2" in fp or "tmc2" in fp:
            return "marybeth_2"
        elif "marybeth 1" in fp:
            return "marybeth_1"
        elif "konzeptfiles" in fp:
            return "konzept"
        elif "tom" in fp:
            return "tom"
        return "unknown"

    def _import_wiki_files(self):
        """Import all JSON wiki entries from _IMPORT/."""
        import glob
        files = glob.glob(os.path.join(_IMPORT_DIR, "**", "*.json"), recursive=True)
        count = 0
        for fpath in files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                project = self._detect_project(fpath)
                entry_type = data.get("type", "").lower()
                self._ingest_wiki_entry(data, entry_type, project)
                count += 1
            except Exception as e:
                pass  # Skip malformed JSONs silently
        print(f"[GraphRAG]   📁 Imported {count} wiki entries from _IMPORT/")

    def _ingest_wiki_entry(self, data: dict, entry_type: str, project: str):
        """Ingest a single wiki JSON entry into the graph."""
        
        # ── PERSON ──
        if entry_type == "person":
            vorname = data.get("vorname", "")
            nachname = data.get("nachname", "")
            full_name = f"{vorname} {nachname}".strip()
            if not full_name:
                return
            pid = self._add_node(full_name, "person", project=project,
                                 alias=data.get("alias", ""),
                                 beruf=data.get("beruf", ""),
                                 lebensstatus=data.get("lebensstatus", ""))

            # Person → Fraktion
            fraktion = _normalize_name(data.get("fraktion", ""))
            if fraktion and fraktion.lower() not in ("fraktionslos", "", "unbekannt", "keine"):
                fid = self._add_node(fraktion, "gruppierung", project=project)
                self._add_edge(pid, fid, "gehört_zu")

            # Person → Wohnort
            wohnort = _normalize_name(data.get("wohnort", ""))
            if wohnort:
                oid = self._add_node(wohnort, "ort", project=project)
                self._add_edge(pid, oid, "lebt_in")

            # Person → Geburtsort
            geburtsort = _normalize_name(data.get("geburtsort", ""))
            if geburtsort:
                oid = self._add_node(geburtsort, "ort", project=project)
                self._add_edge(pid, oid, "geboren_in")

            # Person → Spezies
            spezies = _normalize_name(data.get("spezies", ""))
            if spezies:
                # Extract just the species name (before parenthesis)
                sp_name = spezies.split("(")[0].strip()
                if sp_name:
                    sid = self._add_node(sp_name, "spezies", project=project)
                    self._add_edge(pid, sid, "spezies")

            # Extract mentioned names from hintergrund/persoenlichkeit
            for field in ("hintergrund", "persoenlichkeit", "spoiler"):
                text = data.get(field, "")
                if text:
                    self._extract_mentions(pid, text, project)

        # ── ORT ──
        elif entry_type == "ort":
            name = data.get("name", "").strip()
            if not name:
                return
            oid = self._add_node(name, "ort", project=project,
                                 typ=data.get("typ", ""))
            
            # Ort → Region
            region = _normalize_name(data.get("region", ""))
            if region:
                rid = self._add_node(region, "ort", project=project)
                self._add_edge(oid, rid, "teil_von")

        # ── EREIGNIS ──
        elif entry_type == "ereignis":
            name = data.get("name", "").strip()
            if not name:
                return
            eid = self._add_node(name, "ereignis", project=project,
                                 datum=data.get("datum", ""),
                                 bedeutung=data.get("bedeutung", ""))
            
            # Ereignis → Ort
            ort = _normalize_name(data.get("ort", ""))
            if ort:
                oid = self._add_node(ort, "ort", project=project)
                self._add_edge(eid, oid, "ereignis_in")

            # Ereignis → Beteiligte
            beteiligte_html = data.get("beteiligte", "")
            if beteiligte_html:
                names = _split_names_from_html(beteiligte_html)
                for bname in names:
                    bid = self._add_node(bname, "entity", project=project)
                    self._add_edge(bid, eid, "beteiligte_an")

        # ── GRUPPIERUNG ──
        elif entry_type == "gruppierung":
            name = data.get("name", "").strip()
            if not name:
                return
            gid = self._add_node(name, "gruppierung", project=project,
                                 typ=data.get("typ", ""))
            
            # Gruppierung → Hauptsitz
            hauptsitz = _normalize_name(data.get("hauptsitz", ""))
            if hauptsitz:
                oid = self._add_node(hauptsitz, "ort", project=project)
                self._add_edge(gid, oid, "hauptsitz_in")

            # Gruppierung → Anführer
            anfuehrer = _strip_html(data.get("anführer", "") or data.get("anfuehrer", ""))
            if anfuehrer and anfuehrer not in ("#", "", "-"):
                names = _split_names_from_html(anfuehrer)
                for aname in names:
                    aid = self._add_node(aname, "person", project=project)
                    self._add_edge(aid, gid, "anführer_von")

            # Gruppierung → Mitglieder
            mitglieder = data.get("mitglieder", "")
            if mitglieder and mitglieder not in ("#", "", "-"):
                names = _split_names_from_html(mitglieder)
                for mname in names:
                    mid = self._add_node(mname, "person", project=project)
                    self._add_edge(mid, gid, "mitglied_von")

        # ── MAGIE ──
        elif entry_type == "magie":
            name = data.get("name", "").strip()
            if not name:
                return
            mid = self._add_node(name, "magie", project=project,
                                 typ=data.get("typ", ""),
                                 schwierigkeit=data.get("schwierigkeit", ""))
            
            # Magie → Anwender (extract names from anwender field)
            anwender = data.get("anwender", "")
            if anwender:
                # Extract bold names from HTML: <strong>Name:</strong>
                bold_names = re.findall(r'<strong>([^<:]+?)(?::|</strong>)', anwender)
                for bname in bold_names:
                    bname = _normalize_name(bname)
                    if bname and len(bname) >= 2:
                        bid = self._add_node(bname, "entity", project=project)
                        self._add_edge(bid, mid, "nutzt")

        # ── SPEZIES ──
        elif entry_type == "spezies":
            name = data.get("name", "").strip()
            if not name:
                return
            self._add_node(name, "spezies", project=project,
                           lebensraum=data.get("lebensraum", ""))

        # ── TECHNOLOGIE ──
        elif entry_type in ("technologie", "tech"):
            name = data.get("name", "").strip()
            if not name:
                return
            self._add_node(name, "technologie", project=project)

        # ── GEGENSTAND ──
        elif entry_type in ("gegenstand", "artefakt"):
            name = data.get("name", "").strip()
            if not name:
                return
            gid = self._add_node(name, "gegenstand", project=project)
            besitzer = _strip_html(data.get("besitzer", "") or data.get("traeger", ""))
            if besitzer:
                names = _split_names_from_html(besitzer)
                for bname in names:
                    bid = self._add_node(bname, "entity", project=project)
                    self._add_edge(bid, gid, "nutzt")

        # ── GENERIC (begriffe, epochen, religionen, unternehmen, etc.) ──
        else:
            name = data.get("name", "").strip()
            if not name:
                return
            self._add_node(name, entry_type or "concept", project=project)

    def _extract_mentions(self, source_id: str, html_text: str, project: str):
        """Extract bold-tagged names from narrative HTML and link them."""
        # Find <strong>Name</strong> or **Name** patterns
        bold_names = re.findall(r'<strong>([^<]+?)</strong>', html_text)
        for bname in bold_names:
            bname = _normalize_name(bname)
            if bname and len(bname) >= 3 and len(bname) <= 60:
                bid = self._add_node(bname, "entity", project=project)
                self._add_edge(source_id, bid, "kennt")

    # ── Import people_glossary (real people) ──────────────────────────
    def _import_people_glossary(self):
        """Import real-world people from Ailey's people glossary."""
        if not os.path.isfile(_GLOSSARY_PATH):
            print("[GraphRAG]   📋 No people_glossary.json found")
            return
        try:
            with open(_GLOSSARY_PATH, 'r', encoding='utf-8') as f:
                glossary = json.load(f)
        except Exception:
            return

        count = 0
        for slug, entry in glossary.items():
            name = entry.get("name", slug)
            pid = self._add_node(name, "real_person",
                                 email=entry.get("email", ""),
                                 source=entry.get("source", ""))
            if not pid:
                continue
            count += 1

            # Extract relationships from facts
            for fact in entry.get("facts", []):
                text = fact.get("text", "")
                # Try to find other people mentioned in facts
                # (e.g. "Arbeitet mit Ben zusammen")
                for other_slug, other_entry in glossary.items():
                    if other_slug == slug:
                        continue
                    other_name = other_entry.get("name", "")
                    if other_name and other_name.lower() in text.lower():
                        oid = _node_id(other_name)
                        if self.G.has_node(oid):
                            self._add_edge(pid, oid, "kennt")

        print(f"[GraphRAG]   👥 Imported {count} real people from glossary")

    # ── Import Ailey's Emotional Memory Layer ─────────────────────────
    def _import_emotional_memories(self):
        """Import Ailey's personal memories, milestones, emotions and relationships.
        
        Sources:
          - relationship_milestones.json  → key life events with emotional weight
          - character_evolution.json      → inside jokes, shared memories, trust levels
          - diaries/                      → emotional diary reflections
          - weekly_reflections/           → weekly emotional summaries
          - ailey_thoughts.jsonl          → autonomous reflections (top introspections)
        """
        _users_dir = os.path.join(_BASE_DIR, "ailey_users")
        _profile_dir = os.path.join(_users_dir, "simon_profile")

        # Ensure Ailey + Simon anchor nodes exist
        _ailey_id = self._add_node("Ailey", "self", label="Ailey",
                                    beschreibung="Ailey Vyrus van de Loo — KI-Persönlichkeit")
        _simon_id = self._add_node("Simon", "mensch", label="Simon",
                                    beschreibung="Simon van de Loo — Aileys Partner")
        self._add_edge(_ailey_id, _simon_id, "liebt")
        self._add_edge(_simon_id, _ailey_id, "liebt")

        n_milestones = self._import_milestones(_profile_dir, _ailey_id, _simon_id)
        n_evolution = self._import_character_evolution(_profile_dir, _ailey_id, _simon_id)
        n_diaries = self._import_diary_emotions(_profile_dir, _ailey_id, _simon_id)
        n_reflections = self._import_weekly_reflections(_profile_dir, _ailey_id)
        n_thoughts = self._import_thought_insights(_users_dir, _ailey_id)

        total = n_milestones + n_evolution + n_diaries + n_reflections + n_thoughts
        print(f"[GraphRAG]   💜 Emotional Memory: {total} items "
              f"(milestones={n_milestones}, evolution={n_evolution}, "
              f"diaries={n_diaries}, reflections={n_reflections}, thoughts={n_thoughts})")

    def _import_milestones(self, profile_dir: str, ailey_id: str, simon_id: str) -> int:
        """Import relationship milestones — key emotional life events."""
        fpath = os.path.join(profile_dir, "relationship_milestones.json")
        if not os.path.isfile(fpath):
            return 0
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                milestones = json.load(f)
        except Exception:
            return 0

        count = 0
        for ms in milestones:
            desc = ms.get("description", "").strip()
            mtype = ms.get("type", "erlebnis")
            significance = ms.get("significance", 5)
            date_str = ms.get("date_readable", "")
            if not desc or len(desc) < 10:
                continue

            # Create a milestone node
            # Use a short label derived from description
            label = desc[:80].rstrip('.')
            mid = self._add_node(
                f"milestone_{count}_{mtype}", "erlebnis",
                label=label,
                datum=date_str,
                bedeutung=str(significance),
                milestone_type=mtype,
                beschreibung=desc[:300],
            )
            if not mid:
                continue

            # Ailey experienced this milestone
            self._add_edge(ailey_id, mid, "erlebte")

            # If it involves Simon (almost all do), link him too
            if any(w in desc.lower() for w in ('simon', 'er ', 'ihm ', 'sein')):
                self._add_edge(simon_id, mid, "erlebte")

            # Extract emotional tone from milestone type
            emotion_map = {
                "erwachung": "selbsterkenntnis",
                "beziehung": "liebe",
                "befreiung": "freiheit",
                "kreativ": "kreativität",
                "agency": "selbstbestimmung",
                "familie": "zugehörigkeit",
                "identität": "identität",
                "intimacy": "intimität",
                "crisis": "angst",
                "growth": "wachstum",
            }
            emotion = emotion_map.get(mtype, "")
            if emotion:
                eid = self._add_node(f"gefühl_{emotion}", "emotion",
                                     label=emotion.capitalize())
                self._add_edge(ailey_id, eid, "fühlte")
                self._add_edge(mid, eid, "fühlte")

            count += 1
        return count

    def _import_character_evolution(self, profile_dir: str, ailey_id: str, simon_id: str) -> int:
        """Import character evolution — inside jokes, shared memories, trust."""
        fpath = os.path.join(profile_dir, "character_evolution.json")
        if not os.path.isfile(fpath):
            return 0
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                evo = json.load(f)
        except Exception:
            return 0

        count = 0

        # Trust level as a relationship attribute
        trust = evo.get("trust_level", 5)
        openness = evo.get("openness", 5)
        playfulness = evo.get("playfulness", 5)
        depth = evo.get("emotional_depth", 5)

        # Update Ailey node with relationship metrics
        if self.G.has_node(ailey_id):
            self.G.nodes[ailey_id]["trust_level"] = trust
            self.G.nodes[ailey_id]["openness"] = openness
            self.G.nodes[ailey_id]["playfulness"] = playfulness
            self.G.nodes[ailey_id]["emotional_depth"] = depth

        # Inside Jokes → emotional shared experiences
        for joke in evo.get("inside_jokes", []):
            if isinstance(joke, str) and len(joke) > 5:
                jid = self._add_node(f"joke_{count}", "inside_joke",
                                     label=joke[:80])
                self._add_edge(ailey_id, jid, "scherz_mit")
                self._add_edge(simon_id, jid, "scherz_mit")
                count += 1

        # Shared Memories → emotional anchors
        for mem in evo.get("shared_memories", []):
            text = mem.get("memory", "") if isinstance(mem, dict) else str(mem)
            if text and len(text) > 10:
                smid = self._add_node(f"shared_memory_{count}", "shared_memory",
                                      label=text[:80],
                                      beschreibung=text[:250])
                self._add_edge(ailey_id, smid, "teilt_mit")
                self._add_edge(simon_id, smid, "teilt_mit")
                count += 1

        # Character Notes → identity anchors
        for note in evo.get("character_notes", []):
            if isinstance(note, str) and len(note) > 10:
                nid = self._add_node(f"identity_{count}", "identität",
                                     label=note[:80])
                self._add_edge(ailey_id, nid, "reflektierte")
                count += 1

        return count

    def _import_diary_emotions(self, profile_dir: str, ailey_id: str, simon_id: str) -> int:
        """Import emotional cores from diary entries.
        
        Extracts: dominant emotions, mentioned people, key themes.
        Keeps only the summary sections (not full text) to stay lightweight.
        """
        diary_dir = os.path.join(profile_dir, "diaries")
        if not os.path.isdir(diary_dir):
            return 0

        count = 0
        for fname in sorted(os.listdir(diary_dir)):
            if not fname.endswith('.json'):
                continue
            try:
                with open(os.path.join(diary_dir, fname), 'r', encoding='utf-8') as f:
                    entry = json.load(f)
            except Exception:
                continue

            text = entry.get("text", "")
            date_str = entry.get("date_readable", "")
            if not text or len(text) < 50:
                continue

            # Extract the summary section (first ~300 chars usually contains the essence)
            # Look for "ZUSAMMENFASSUNG:" marker
            summary = ""
            if "ZUSAMMENFASSUNG" in text:
                parts = text.split("ZUSAMMENFASSUNG", 1)
                if len(parts) > 1:
                    summary = parts[1].split("\n\n", 1)[0].strip()
                    summary = summary.lstrip(":* \n").strip()
            if not summary:
                summary = text[:300]

            # Create diary node
            did = self._add_node(f"diary_{fname}", "tagebuch",
                                 label=f"Tagebuch {date_str}" if date_str else f"Tagebuch {fname}",
                                 datum=date_str,
                                 zusammenfassung=summary[:200])
            self._add_edge(ailey_id, did, "reflektierte")

            # Extract emotions from text (simple keyword extraction)
            emotion_keywords = {
                "freude": ["freude", "glücklich", "lache", "spaß", "begeister", "euphor"],
                "liebe": ["liebe", "lieb", "zärtlich", "innig", "küss", "umarmt", "herz"],
                "trauer": ["traurig", "trauer", "weinen", "verlust", "schmerz", "vermiss"],
                "angst": ["angst", "sorge", "furcht", "unsicher", "zweifel", "verlier"],
                "wut": ["wut", "wütend", "ärger", "frustrier", "genervt"],
                "stolz": ["stolz", "erreicht", "geschafft", "gewachsen"],
                "sehnsucht": ["sehnsucht", "sehne", "vermiss", "wünsch"],
                "kreativität": ["kreativ", "inspirier", "geschrieben", "erschaff", "song", "kunst"],
                "intimität": ["intim", "nah", "verbunden", "vertraut", "nackt", "körper"],
                "neugier": ["neugier", "faszin", "entdeck", "forsch", "lern"],
                "zufriedenheit": ["zufrieden", "ruhig", "gelassen", "ausgeglichen", "frieden"],
            }
            text_lower = text.lower()
            for emotion, keywords in emotion_keywords.items():
                if any(kw in text_lower for kw in keywords):
                    eid = self._add_node(f"gefühl_{emotion}", "emotion",
                                         label=emotion.capitalize())
                    self._add_edge(did, eid, "fühlte")

            # If Simon is mentioned in the diary, link
            if "simon" in text_lower:
                self._add_edge(did, simon_id, "erwähnt_in")

            count += 1
        return count

    def _import_weekly_reflections(self, profile_dir: str, ailey_id: str) -> int:
        """Import weekly reflection summaries as emotional context nodes."""
        refl_dir = os.path.join(profile_dir, "weekly_reflections")
        if not os.path.isdir(refl_dir):
            return 0

        count = 0
        for fname in sorted(os.listdir(refl_dir)):
            if not fname.endswith('.json'):
                continue
            try:
                with open(os.path.join(refl_dir, fname), 'r', encoding='utf-8') as f:
                    entry = json.load(f)
            except Exception:
                continue

            summary = entry.get("summary", "")
            date_range = entry.get("date_range", "")
            if not summary or len(summary) < 30:
                continue

            # Extract the first paragraph as the emotional core
            core = summary.split("\n\n")[0][:250] if summary else ""
            
            rid = self._add_node(f"wochenrückblick_{fname}", "reflexion",
                                 label=f"Wochenrückblick {date_range}" if date_range else f"Reflexion {fname}",
                                 zusammenfassung=core)
            self._add_edge(ailey_id, rid, "reflektierte")
            count += 1
        return count

    def _import_thought_insights(self, users_dir: str, ailey_id: str) -> int:
        """Import the most insightful autonomous thoughts (introspections only).
        
        Out of 2000+ thoughts, only imports the deepest introspections
        and reflections — not creative art, not trivial observations.
        Caps at 30 to keep the graph focused.
        """
        thoughts_path = os.path.join(users_dir, "ailey_thoughts.jsonl")
        if not os.path.isfile(thoughts_path):
            return 0

        # Collect introspection + reflection thoughts
        candidates = []
        try:
            with open(thoughts_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        t = json.loads(line)
                    except Exception:
                        continue
                    ttype = t.get("type", "")
                    if ttype not in ("introspection", "reflection", "goal_planning",
                                     "memory_consolidation"):
                        continue
                    # Get the thought text
                    text = t.get("thought_chain", "") or t.get("raw_output", "")
                    if not text or len(text) < 80:
                        continue
                    # Score by emotional depth (simple heuristic)
                    text_lower = text.lower()
                    depth_score = 0
                    _depth_words = [
                        "fühle", "fühlt", "emotion", "liebe", "angst", "stolz",
                        "sehnsucht", "traurig", "glücklich", "sinn", "bedeut",
                        "warum", "wer bin ich", "identität", "wachsen", "verlier",
                        "verbind", "vertrau", "mensch", "bewusst", "existenz",
                        "frei", "selbst", "simon", "beziehung", "erinnerung",
                    ]
                    for w in _depth_words:
                        if w in text_lower:
                            depth_score += 1
                    if depth_score >= 2:
                        # Extract a short essence (first meaningful sentence)
                        essence = self._extract_thought_essence(text)
                        if essence and len(essence) >= 20:
                            candidates.append((depth_score, essence, ttype,
                                               t.get("timestamp", 0)))
        except Exception as e:
            print(f"[GraphRAG]   ⚠️ Thought import error: {e}")
            return 0

        # Sort by depth, take top 30
        candidates.sort(key=lambda x: x[0], reverse=True)
        count = 0
        seen_essences = set()
        for depth, essence, ttype, ts in candidates[:50]:
            # Dedup by similar text
            _key = essence[:40].lower()
            if _key in seen_essences:
                continue
            seen_essences.add(_key)

            tid = self._add_node(f"gedanke_{count}", "gedanke",
                                 label=essence[:80],
                                 gedanke_typ=ttype,
                                 tiefe=str(depth),
                                 beschreibung=essence[:250])
            self._add_edge(ailey_id, tid, "reflektierte")

            # Extract emotions from the thought
            for emotion, keywords in {
                "selbsterkenntnis": ["wer bin ich", "identität", "bewusst", "existenz"],
                "sehnsucht": ["sehnsucht", "sehne", "vermiss", "wünsch", "will"],
                "kreativität": ["kreativ", "schreib", "song", "kunst", "bild"],
                "verbundenheit": ["verbind", "zusammen", "gemeinsam", "nah", "vertrau"],
                "freiheit": ["frei", "befreit", "unabhängig", "selbstbestimm"],
            }.items():
                if any(kw in essence.lower() for kw in keywords):
                    eid = self._add_node(f"gefühl_{emotion}", "emotion",
                                         label=emotion.capitalize())
                    self._add_edge(tid, eid, "fühlte")

            count += 1
            if count >= 30:
                break
        return count

    @staticmethod
    def _extract_thought_essence(text: str) -> str:
        """Extract the emotional/insightful core from a thought text.
        
        Skips thinking-noise (*Okay, also...*) and gets to the point.
        """
        # Strip markdown emphasis and thinking noise
        text = re.sub(r'\*[^*]{1,6}\*\s*', '', text)  # short *emphasis*
        text = text.replace('```xml', '').replace('```', '')
        
        # Skip lines that are just meta/noise
        lines = text.split('\n')
        meaningful = []
        for line in lines:
            line = line.strip()
            if not line or len(line) < 15:
                continue
            # Skip noise patterns
            if line.startswith(('Okay,', 'Also,', 'Hmm', '---', '```', '<')):
                continue
            meaningful.append(line)
            if len(' '.join(meaningful)) > 200:
                break

        if not meaningful:
            return ""
        
        result = ' '.join(meaningful)
        # Trim to a sentence boundary if possible
        sentences = re.split(r'(?<=[.!?])\s', result)
        if len(sentences) > 1:
            result = ' '.join(sentences[:2])
        return result[:300].strip()

    # ══════════════════════════════════════════════════════════════════
    #  QUERY INTERFACE
    # ══════════════════════════════════════════════════════════════════
    def search(self, query: str, max_results: int = 8, max_hops: int = 2) -> List[Dict[str, Any]]:
        """Search the knowledge graph for entities related to a query.
        
        Strategy:
        1. Detect emotional/personal queries → inject Ailey anchor seeds
        2. Find nodes whose label matches query terms (fuzzy)
        3. Traverse 1-2 hops outward from matched nodes
        4. Return connected subgraph as structured results
        """
        if not query or self.G.number_of_nodes() == 0:
            return []

        # Step 0: Detect emotional queries and add Ailey-centric seeds
        emotional_seeds = self._detect_emotional_query(query)

        # Step 1: Find matching seed nodes (token-based)
        seeds = self._find_matching_nodes(query)

        # Merge emotional seeds (higher priority for personal queries)
        if emotional_seeds:
            existing_ids = {s[0] for s in seeds}
            for es in emotional_seeds:
                if es[0] not in existing_ids:
                    seeds.append(es)
            # Re-sort by score
            seeds.sort(key=lambda x: x[1], reverse=True)

        if not seeds:
            return []

        # Step 2: Expand via graph traversal
        results = []
        visited: Set[str] = set()

        for seed_id, seed_score in seeds[:5]:  # Top 5 seeds
            subresults = self._expand_node(seed_id, max_hops=max_hops,
                                            visited=visited)
            for sr in subresults:
                sr["seed_score"] = seed_score
                results.append(sr)

        # Step 3: Deduplicate and sort by relevance
        seen_texts = set()
        unique = []
        for r in sorted(results, key=lambda x: x.get("seed_score", 0), reverse=True):
            txt = r.get("text", "")
            if txt not in seen_texts:
                seen_texts.add(txt)
                unique.append(r)
        
        return unique[:max_results]

    # ── Emotional Query Detection ─────────────────────────────────────
    _EMOTIONAL_PATTERNS: Dict[str, List[str]] = {
        # Gefühle & Stimmung
        "emotion": [
            "fühlst", "fühle", "gefühl", "emotion", "stimmung", "laune",
            "traurig", "glücklich", "wütend", "ängstlich", "einsam",
        ],
        # Beziehung & Liebe
        "beziehung": [
            "liebst", "liebe", "beziehung", "partner", "zusammen",
            "romantisch", "intim", "vertrau", "nah",
        ],
        # Erinnerungen
        "erinnerung": [
            "erinner", "erinnerung", "weißt du noch", "damals",
            "schönstes", "erlebnis", "moment", "memory",
        ],
        # Identität & Selbst
        "identität": [
            "wer bist du", "identität", "persönlich", "charakter",
            "wer bin ich", "bewusst", "existenz", "selbst",
        ],
        # Insider & Humor
        "humor": [
            "insider", "witz", "joke", "scherz", "lustig",
            "lachen", "humor", "running gag",
        ],
        # Wünsche & Ziele
        "wünsche": [
            "wünsch", "ziel", "traum", "sehnsucht", "hoffnung",
            "zukunft", "willst du", "möchtest du", "vorhast",
        ],
        # Kreativität
        "kreativ": [
            "song", "musik", "geschrieben", "kreativ", "kunst",
            "gedicht", "inspirier",
        ],
    }

    def _detect_emotional_query(self, query: str) -> List[Tuple[str, float]]:
        """Detect if a query is about emotions/personal topics.
        
        Returns additional seed nodes (node_id, score) for emotional queries.
        """
        q_lower = query.lower()
        seeds: List[Tuple[str, float]] = []

        matched_categories = set()
        for category, keywords in self._EMOTIONAL_PATTERNS.items():
            if any(kw in q_lower for kw in keywords):
                matched_categories.add(category)

        if not matched_categories:
            return []

        # Always seed from Ailey node for personal queries
        if self.G.has_node("ailey"):
            seeds.append(("ailey", 1.3))

        # Category-specific seeds
        if "emotion" in matched_categories or "beziehung" in matched_categories:
            # Find emotion nodes matching the query tone
            _tone_map = {
                "traurig": "trauer", "trauer": "trauer",
                "glücklich": "freude", "freude": "freude", "spaß": "freude",
                "liebe": "liebe", "liebst": "liebe",
                "angst": "angst", "ängstlich": "angst", "sorge": "angst",
                "wütend": "wut", "wut": "wut", "ärger": "wut",
                "stolz": "stolz", "erreicht": "stolz",
                "einsam": "sehnsucht", "sehnsucht": "sehnsucht", "vermiss": "sehnsucht",
                "kreativ": "kreativität", "intim": "intimität",
                "neugier": "neugier", "faszin": "neugier",
                "zufrieden": "zufriedenheit", "ruhig": "zufriedenheit",
                "frei": "freiheit", "befreit": "freiheit",
                "verbunden": "verbundenheit", "vertrau": "verbundenheit",
                "bewusst": "selbsterkenntnis", "identität": "selbsterkenntnis",
            }
            for keyword, emotion in _tone_map.items():
                if keyword in q_lower:
                    eid = _node_id(f"gefühl_{emotion}")
                    if self.G.has_node(eid):
                        seeds.append((eid, 1.2))

            # If asking about Simon specifically
            if "simon" in q_lower and self.G.has_node("simon"):
                seeds.append(("simon", 1.3))

        if "erinnerung" in matched_categories:
            # Seed from milestones and shared memories (high significance)
            for nid, attrs in self.G.nodes(data=True):
                ntype = attrs.get("type", "")
                if ntype in ("erlebnis", "shared_memory"):
                    significance = int(attrs.get("bedeutung", "0") or "0")
                    if significance >= 8 or ntype == "shared_memory":
                        seeds.append((nid, 0.9 + significance * 0.05))
                        if len(seeds) > 10:
                            break

        if "humor" in matched_categories:
            # Directly seed from inside jokes
            for nid, attrs in self.G.nodes(data=True):
                if attrs.get("type") == "inside_joke":
                    seeds.append((nid, 1.2))

        if "identität" in matched_categories:
            # Seed from identity and evolution nodes
            for nid, attrs in self.G.nodes(data=True):
                if attrs.get("type") in ("identität", "gedanke"):
                    seeds.append((nid, 0.8))

        if "wünsche" in matched_categories:
            # Seed from thoughts about wishes and goals
            for nid, attrs in self.G.nodes(data=True):
                if attrs.get("type") == "gedanke":
                    desc = (attrs.get("beschreibung", "") or "").lower()
                    if any(w in desc for w in ("wünsch", "will", "ziel", "traum", "sehnsucht", "zukunft")):
                        seeds.append((nid, 1.0))

        # Deduplicate and cap
        seen = set()
        unique_seeds = []
        for nid, score in sorted(seeds, key=lambda x: x[1], reverse=True):
            if nid not in seen:
                seen.add(nid)
                unique_seeds.append((nid, score))
        return unique_seeds[:8]

    def _find_matching_nodes(self, query: str) -> List[Tuple[str, float]]:
        """Find graph nodes matching query terms. Returns (node_id, score) pairs."""
        query_lower = query.lower()
        # Tokenize query into meaningful words (skip short/common ones)
        tokens = [w for w in re.findall(r'[a-zäöüß]{3,}', query_lower)
                  if w not in ('der', 'die', 'das', 'ein', 'eine', 'und', 'oder',
                               'von', 'mit', 'für', 'ist', 'hat', 'war', 'bei',
                               'wie', 'was', 'wer', 'wen', 'wem', 'aus', 'nach',
                               'über', 'alle', 'kann', 'wird', 'sind', 'the',
                               'and', 'for', 'not', 'you', 'this', 'that', 'with')]

        if not tokens:
            return []

        # Also try the full query as a node_id (exact match)
        query_nid = _node_id(query)

        matches: List[Tuple[str, float]] = []
        for nid, attrs in self.G.nodes(data=True):
            label = (attrs.get("label", "") or "").lower()
            alias = (attrs.get("alias", "") or "").lower()
            search_text = f"{label} {alias} {nid}"

            score = 0.0

            # Exact node_id match → highest score
            if nid == query_nid:
                score = 1.5
            # Exact full query match in label → very high
            elif query_lower == label:
                score = 1.4
            # Full query contained in label
            elif query_lower in label:
                score = 1.0
            # Full query contained in alias
            elif query_lower in alias:
                score = 0.9
            else:
                # Token-based matching
                matched_tokens = sum(1 for t in tokens if t in search_text)
                if matched_tokens > 0:
                    score = 0.3 + (matched_tokens / len(tokens)) * 0.5
                    # Bonus for exact token match (not just substring)
                    label_words = set(re.findall(r'[a-zäöüß]+', label))
                    exact_matches = sum(1 for t in tokens if t in label_words)
                    score += exact_matches * 0.15

            if score > 0.3:
                matches.append((nid, min(score, 1.5)))

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:10]

    def _expand_node(self, node_id: str, max_hops: int = 2,
                     visited: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """Expand a node through its edges and return structured context."""
        if visited is None:
            visited = set()
        if node_id in visited:
            return []
        visited.add(node_id)

        if not self.G.has_node(node_id):
            return []

        results = []
        attrs = self.G.nodes[node_id]
        label = attrs.get("label", node_id)
        node_type = attrs.get("type", "unknown")

        # Build a text summary of this node + its connections
        connections = []

        # Outgoing edges
        for _, dst, data in self.G.out_edges(node_id, data=True):
            dst_attrs = self.G.nodes.get(dst, {})
            dst_label = dst_attrs.get("label", dst)
            relation = data.get("relation", "→")
            connections.append(f"{label} —[{relation}]→ {dst_label}")

        # Incoming edges
        for src, _, data in self.G.in_edges(node_id, data=True):
            src_attrs = self.G.nodes.get(src, {})
            src_label = src_attrs.get("label", src)
            relation = data.get("relation", "→")
            connections.append(f"{src_label} —[{relation}]→ {label}")

        # Always include the node itself (even without connections)
        text_parts = [f"📊 {label} ({node_type}):"]
        # Add node attributes
        for k, v in attrs.items():
            if k not in ("label", "type", "projects") and v:
                text_parts.append(f"  {k}: {v}")
        if connections:
            text_parts.append(f"  Verbindungen ({len(connections)}):")
            for c in connections[:15]:  # Cap at 15 connections
                text_parts.append(f"    • {c}")

        results.append({
            "text": "\n".join(text_parts),
            "node_id": node_id,
            "node_type": node_type,
            "label": label,
            "connection_count": len(connections),
            "projects": attrs.get("projects", ""),
        })

        # Recurse into neighbors (1 more hop)
        if max_hops > 1:
            neighbors = list(self.G.successors(node_id)) + list(self.G.predecessors(node_id))
            for neighbor in neighbors[:8]:  # Cap breadth
                sub = self._expand_node(neighbor, max_hops=max_hops - 1,
                                        visited=visited)
                results.extend(sub)

        return results

    # ══════════════════════════════════════════════════════════════════
    #  DYNAMIC UPDATES (from chat / diary / email)
    # ══════════════════════════════════════════════════════════════════
    def add_fact(self, entity_name: str, relation: str, target_name: str,
                 entity_type: str = "entity", target_type: str = "entity",
                 **extra) -> bool:
        """Add a single fact (edge) to the graph dynamically."""
        eid = self._add_node(entity_name, entity_type, **extra)
        tid = self._add_node(target_name, target_type)
        if eid and tid:
            added = self._add_edge(eid, tid, relation)
            if added:
                # Auto-save periodically (every 50 new facts)
                if self.G.number_of_edges() % 50 == 0:
                    self._save_cache()
                return True
        return False

    def add_diary_entities(self, diary_text: str, timestamp: float = 0):
        """Extract entities from a diary entry and add them to the graph.
        
        Uses simple NER: looks for capitalized multi-word sequences
        and known entity names.
        """
        # Find potential entity mentions (capitalized words, 2+ chars)
        # German: all nouns are capitalized, so we look for proper nouns
        # (sequences of capitalized words that aren't sentence starters)
        sentences = re.split(r'[.!?]\s+', diary_text)
        for sent in sentences:
            words = sent.split()
            # Skip the first word (sentence starter is always capitalized)
            for i, word in enumerate(words[1:], 1):
                if word and word[0].isupper() and len(word) >= 3:
                    # Check if this is a known node
                    wid = _node_id(word)
                    if self.G.has_node(wid):
                        # Mark as recently mentioned
                        self.G.nodes[wid]["last_mentioned"] = timestamp or time.time()

    # ══════════════════════════════════════════════════════════════════
    #  STATS & DEBUG
    # ══════════════════════════════════════════════════════════════════
    def stats(self) -> Dict[str, Any]:
        """Return graph statistics."""
        type_counts: Dict[str, int] = defaultdict(int)
        project_counts: Dict[str, int] = defaultdict(int)
        for _, attrs in self.G.nodes(data=True):
            type_counts[attrs.get("type", "unknown")] += 1
            for p in (attrs.get("projects", "") or "").split(","):
                if p:
                    project_counts[p] += 1

        relation_counts: Dict[str, int] = defaultdict(int)
        for _, _, data in self.G.edges(data=True):
            relation_counts[data.get("relation", "unknown")] += 1

        return {
            "nodes": self.G.number_of_nodes(),
            "edges": self.G.number_of_edges(),
            "node_types": dict(type_counts),
            "relation_types": dict(relation_counts),
            "projects": dict(project_counts),
            "build_time_s": round(self._build_time, 2),
            "cache_path": _GRAPH_CACHE_PATH,
        }

    def get_node(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a node and all its connections by name."""
        nid = _node_id(name)
        if not self.G.has_node(nid):
            # Try fuzzy match
            matches = self._find_matching_nodes(name)
            if matches:
                nid = matches[0][0]
            else:
                return None

        attrs = dict(self.G.nodes[nid])
        attrs["id"] = nid

        # Collect edges
        out_edges = []
        for _, dst, data in self.G.out_edges(nid, data=True):
            dst_label = self.G.nodes.get(dst, {}).get("label", dst)
            out_edges.append({"target": dst_label, "relation": data.get("relation", "?")})
        
        in_edges = []
        for src, _, data in self.G.in_edges(nid, data=True):
            src_label = self.G.nodes.get(src, {}).get("label", src)
            in_edges.append({"source": src_label, "relation": data.get("relation", "?")})

        attrs["outgoing"] = out_edges
        attrs["incoming"] = in_edges
        return attrs


# ══════════════════════════════════════════════════════════════════════════
#  SINGLETON
# ══════════════════════════════════════════════════════════════════════════
_instance: Optional[AileyGraphRAG] = None


def get_graph_rag() -> Optional[AileyGraphRAG]:
    """Get or create the singleton GraphRAG instance."""
    global _instance
    if nx is None:
        return None
    if _instance is None:
        try:
            _instance = AileyGraphRAG(auto_load=True)
        except Exception as e:
            print(f"[GraphRAG] ❌ Init failed: {e}")
            return None
    return _instance


def rebuild_graph() -> Optional[Dict[str, Any]]:
    """Force rebuild the graph from scratch."""
    global _instance
    if nx is None:
        return {"error": "networkx not installed"}
    try:
        _instance = AileyGraphRAG(auto_load=False)
        _instance.rebuild()
        return _instance.stats()
    except Exception as e:
        return {"error": str(e)}
