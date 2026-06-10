# -*- coding: utf-8 -*-
"""
Ailey Web Tools — Web search, URL fetching, package search.

Uses DuckDuckGo for search (no API key needed) and trafilatura for
clean text extraction from web pages.
"""
from __future__ import annotations
import os
import json
import re
import logging
from typing import Any, Dict
from datetime import datetime

from .tools import register_tool

_log = logging.getLogger("ailey.tools_web")


# ─── Lazy imports (installed on demand) ──────────────────────────────────────

def _ensure_web_deps():
    """Check that web dependencies are available."""
    try:
        import trafilatura
        return True
    except ImportError:
        _log.warning("trafilatura not installed — run: pip install trafilatura")
        return False


def _ensure_search_deps():
    """Check that search dependencies are available."""
    try:
        from ddgs import DDGS
        return True
    except ImportError:
        pass
    try:
        from duckduckgo_search import DDGS
        return True
    except ImportError:
        _log.warning("ddgs not installed — run: pip install ddgs")
        return False


# ─── Tool: Web Search ───────────────────────────────────────────────────────

@register_tool(
    name="web_search",
    description=(
        "Durchsucht das Internet nach Informationen (via DuckDuckGo). "
        "Nutze dieses Tool wenn du aktuelle Informationen, Dokumentation, "
        "Fehlerlösungen oder API-Referenzen brauchst."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Suchanfrage (z.B. 'Next.js 14 app router middleware', 'Python requests timeout')"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximale Anzahl Ergebnisse (default: 5, max: 10)"
            },
            "region": {
                "type": "string",
                "description": "Suchregion (default: 'de-de')"
            }
        },
        "required": ["query"]
    }
)
def web_search(query: str, max_results: int = 5, region: str = "de-de") -> dict:
    """Search the web using DuckDuckGo."""
    if not _ensure_search_deps():
        return {"error": "ddgs nicht installiert. Bitte `pip install ddgs` ausführen."}
    
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    
    max_results = min(max(max_results, 1), 10)
    
    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, region=region, max_results=max_results))
        
        results = []
        for r in raw_results:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", r.get("link", "")),
                "snippet": r.get("body", r.get("snippet", "")),
            })
        
        if not results:
            return {"message": f"Keine Ergebnisse für '{query}'", "results": []}
        
        # Format as readable text
        text_parts = [f"🔍 Suchergebnisse für '{query}':\n"]
        for i, r in enumerate(results, 1):
            text_parts.append(f"{i}. **{r['title']}**")
            text_parts.append(f"   {r['url']}")
            text_parts.append(f"   {r['snippet']}\n")
        
        _log.info(f"web_search: '{query}' → {len(results)} results")
        
        return {
            "message": "\n".join(text_parts),
            "results": results,
            "query": query,
            "count": len(results),
        }
    except Exception as e:
        _log.error(f"web_search error: {e}")
        return {"error": f"Suchfehler: {e}"}


# ─── Tool: Fetch URL ────────────────────────────────────────────────────────

@register_tool(
    name="fetch_url",
    description=(
        "Lädt eine Webseite und extrahiert den Haupttext (ohne HTML, Werbung, Navigation). "
        "Nutze dieses Tool um Dokumentation, Artikel oder Code-Beispiele von Webseiten zu lesen."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL der Webseite"
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximale Zeichenzahl des extrahierten Texts (default: 8000)"
            }
        },
        "required": ["url"]
    }
)
def fetch_url(url: str, max_chars: int = 8000) -> dict:
    """Fetch a URL and extract clean text content."""
    if not _ensure_web_deps():
        # Fallback to basic urllib
        return _fetch_url_basic(url, max_chars)
    
    import trafilatura
    
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return {"error": f"Konnte URL nicht laden: {url}"}
        
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            include_links=True,
            output_format="txt",
        )
        
        if not text:
            # Fallback: try with less strict extraction
            text = trafilatura.extract(downloaded, favor_recall=True)
        
        if not text:
            return {"error": f"Konnte keinen Text aus {url} extrahieren"}
        
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n... (abgeschnitten)"
        
        # Try to get title
        title = ""
        try:
            metadata = trafilatura.extract_metadata(downloaded)
            if metadata:
                title = metadata.title or ""
        except:
            pass
        
        _log.info(f"fetch_url: {url} → {len(text)} chars")
        
        return {
            "message": f"📄 Inhalt von {url}" + (f" — {title}" if title else ""),
            "content": text,
            "url": url,
            "title": title,
            "chars": len(text),
        }
    except Exception as e:
        _log.error(f"fetch_url error: {e}")
        return {"error": f"Fehler beim Laden: {e}"}


def _fetch_url_basic(url: str, max_chars: int = 8000) -> dict:
    """Basic URL fetching without trafilatura (fallback)."""
    import urllib.request
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Ailey/2.0 Research Bot"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        
        # Basic HTML stripping
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        
        return {
            "message": f"📄 Inhalt von {url} (Basis-Extraktion)",
            "content": text,
            "url": url,
            "chars": len(text),
        }
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: NPM Search ───────────────────────────────────────────────────────

@register_tool(
    name="npm_search",
    description=(
        "Sucht nach NPM-Paketen in der NPM Registry. "
        "Gibt Name, Version, Beschreibung und Downloads zurück."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Suchbegriff (z.B. 'react state management')"
            },
            "max_results": {
                "type": "integer",
                "description": "Max Ergebnisse (default: 5)"
            }
        },
        "required": ["query"]
    }
)
def npm_search(query: str, max_results: int = 5) -> dict:
    """Search NPM registry."""
    import urllib.request
    
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://registry.npmjs.org/-/v1/search?text={encoded}&size={max_results}"
        req = urllib.request.Request(url, headers={"User-Agent": "Ailey/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        
        packages = []
        for obj in data.get("objects", []):
            pkg = obj.get("package", {})
            packages.append({
                "name": pkg.get("name", ""),
                "version": pkg.get("version", ""),
                "description": pkg.get("description", ""),
                "keywords": pkg.get("keywords", [])[:5],
            })
        
        if not packages:
            return {"message": f"Keine NPM-Pakete für '{query}' gefunden", "packages": []}
        
        text_parts = [f"📦 NPM-Pakete für '{query}':\n"]
        for p in packages:
            text_parts.append(f"• **{p['name']}** v{p['version']}")
            text_parts.append(f"  {p['description']}\n")
        
        return {
            "message": "\n".join(text_parts),
            "packages": packages,
            "count": len(packages),
        }
    except Exception as e:
        return {"error": f"NPM-Suche fehlgeschlagen: {e}"}


# ─── Tool: PyPI Search ──────────────────────────────────────────────────────

@register_tool(
    name="pypi_search",
    description=(
        "Sucht nach Python-Paketen auf PyPI. "
        "Gibt Name, Version und Beschreibung zurück."
    ),
    parameters={
        "type": "object",
        "properties": {
            "package_name": {
                "type": "string",
                "description": "Paketname (z.B. 'flask', 'requests')"
            }
        },
        "required": ["package_name"]
    }
)
def pypi_search(package_name: str) -> dict:
    """Look up a Python package on PyPI."""
    import urllib.request
    
    try:
        url = f"https://pypi.org/pypi/{urllib.parse.quote(package_name)}/json"
        req = urllib.request.Request(url, headers={"User-Agent": "Ailey/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        
        info = data.get("info", {})
        return {
            "message": f"📦 **{info.get('name', package_name)}** v{info.get('version', '?')}\n{info.get('summary', '')}",
            "name": info.get("name", ""),
            "version": info.get("version", ""),
            "summary": info.get("summary", ""),
            "home_page": info.get("home_page", ""),
            "requires_python": info.get("requires_python", ""),
            "license": info.get("license", ""),
        }
    except Exception as e:
        return {"error": f"PyPI-Suche fehlgeschlagen: {e}"}
