"""
Ailey CMS — Site JSON Schema & Validation
==========================================
Everything in CMS Mode is JSON. Ailey generates JSON, the page builder edits JSON,
the export renders JSON.

This module defines the canonical schema, default templates, and validation logic.
"""

import json
import os
import copy
import uuid
import time
from typing import Dict, List, Any, Optional, Tuple

# ── Storage paths ──────────────────────────────────────────────

CMS_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ailey_cms_projects")

def _ensure_dirs():
    os.makedirs(CMS_BASE, exist_ok=True)

# ── ID helpers ─────────────────────────────────────────────────

def gen_id(prefix: str = "sec") -> str:
    """Generate a short unique ID like sec_a1b2c3d4"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

def gen_project_id() -> str:
    return f"proj_{uuid.uuid4().hex[:8]}"

# ── Default Schema ────────────────────────────────────────────

DEFAULT_DESIGN = {
    "colors": {
        "primary": "#2563eb",
        "primary-light": "#60a5fa",
        "secondary": "#f59e0b",
        "accent": "#10b981",
        "background": "#ffffff",
        "surface": "#f9fafb",
        "text": "#1a1a1a",
        "text-muted": "#6b7280",
        "border": "#e5e7eb",
        "error": "#ef4444",
        "success": "#22c55e",
    },
    "fonts": {
        "heading": {"family": "Inter", "weight": "700", "source": "google"},
        "body": {"family": "Inter", "weight": "400", "source": "google"},
        "mono": {"family": "JetBrains Mono", "weight": "400", "source": "google"},
    },
    "sizes": {
        "h1": "3.5rem",
        "h2": "2.5rem",
        "h3": "1.75rem",
        "h4": "1.25rem",
        "body": "1rem",
        "small": "0.875rem",
    },
    "spacing": {
        "section-y": "5rem",
        "container-x": "1.5rem",
        "element-gap": "1.5rem",
    },
    "borderRadius": "0.5rem",
    "maxWidth": "1280px",
    "globalCSS": "",
    "darkMode": False,
}

DEFAULT_NAV = {
    "style": "sticky-transparent",
    "logo": {"src": "", "alt": "Logo", "height": "40px"},
    "links": [],
    "mobileStyle": "slide-left",
    "cta": None,
    "customClasses": "",
    "customId": "",
}

DEFAULT_FOOTER = {
    "style": "columns",
    "columns": [],
    "copyright": "© {year} Firma. Alle Rechte vorbehalten.",
    "legalLinks": [
        {"label": "Impressum", "href": "/impressum"},
        {"label": "Datenschutz", "href": "/datenschutz"},
    ],
}

DEFAULT_LEGAL = {
    "impressum": {
        "companyName": "",
        "address": "",
        "phone": "",
        "email": "",
        "ceo": "",
        "registration": "",
        "vatId": "",
        "template": "de-standard",
    },
    "datenschutz": {
        "template": "de-dsgvo-standard",
        "contactEmail": "",
        "analytics": "none",
        "cookies": "essential-only",
        "externalServices": [],
    },
}

def create_blank_site(title: str = "Neue Website") -> dict:
    """Create a blank site.json with all required fields."""
    return {
        "version": "1.0",
        "projectId": gen_project_id(),
        "createdAt": time.time(),
        "updatedAt": time.time(),
        "meta": {
            "title": title,
            "description": "",
            "favicon": "",
            "ogImage": "",
            "language": "de",
            "charset": "utf-8",
        },
        "design": copy.deepcopy(DEFAULT_DESIGN),
        "nav": copy.deepcopy(DEFAULT_NAV),
        "pages": [
            {
                "slug": "/",
                "title": "Home",
                "meta": {"description": ""},
                "sections": [],
            }
        ],
        "footer": copy.deepcopy(DEFAULT_FOOTER),
        "auth": {
            "enabled": False,
            "provider": "local",
            "protectedPages": [],
            "loginPage": "/login",
        },
        "media": {
            "basePath": "/media",
            "items": [],
        },
        "legal": copy.deepcopy(DEFAULT_LEGAL),
    }


# ── Section Templates ─────────────────────────────────────────
# Each section template defines: type, label, category, icon, defaultProps, defaultStyle

SECTION_TEMPLATES: Dict[str, dict] = {}

def _reg(type_id: str, label: str, category: str, icon: str,
         default_props: dict, default_style: Optional[dict] = None,
         variants: Optional[List[str]] = None):
    """Register a section template."""
    SECTION_TEMPLATES[type_id] = {
        "type": type_id,
        "label": label,
        "category": category,
        "icon": icon,
        "variants": variants or [],
        "defaultProps": default_props,
        "defaultStyle": default_style or {
            "classes": [],
            "customCSS": "",
            "customClasses": "",
            "customId": "",
            "minHeight": "",
            "overflow": "",
        },
    }

# ── Navigation Sections ───────────────────────────────────────
_reg("nav-sticky-transparent", "Sticky Nav (transparent)", "navigation", "🧭",
     {"logo": {"src": "", "alt": "Logo", "height": "40px"},
      "links": [{"label": "Home", "href": "/"}],
      "cta": None},
     variants=["solid", "blurred", "colored"])

_reg("nav-taprturn", "Tap'R'Turn Dial Nav", "navigation", "📞",
     {"logo": {"src": "", "alt": "Logo", "height": "40px"},
      "links": [{"label": "Home", "href": "/", "icon": "🏠"}],
      "dialSize": 320,
      "fingerStopAngle": 90,
      "snapTolerance": 18,
      "colors": {"disc": "#1a1a1a", "holes": "#2a2a2a", "glow": "#00ffcc", "text": "#ffffff"}},
     variants=[])

# ── Hero Sections ─────────────────────────────────────────────
_reg("hero-fullscreen", "Hero Fullscreen", "hero", "🎬",
     {"headline": "Willkommen",
      "subline": "Ihr Partner für erstklassige Lösungen",
      "cta": {"text": "Mehr erfahren", "href": "#about"},
      "cta2": None,
      "backgroundImage": {"src": "", "alt": "", "fit": "cover", "position": "center"},
      "overlay": "rgba(0,0,0,0.4)"},
     {"classes": ["py-32", "min-h-screen", "flex", "items-center", "justify-center"],
      "customCSS": "", "customClasses": "", "customId": "hero", "minHeight": "100vh", "overflow": "hidden"},
     variants=["centered", "left-aligned", "particle-bg"])

_reg("hero-split", "Hero Split", "hero", "⬛",
     {"headline": "Willkommen",
      "subline": "Seit 2005 Ihr Partner für erstklassige Lösungen",
      "cta": {"text": "Mehr erfahren", "href": "#about"},
      "cta2": {"text": "Kontakt", "href": "#contact", "style": "outline"},
      "image": {"src": "", "alt": "", "fit": "cover", "position": "center", "borderRadius": "1rem"}},
     {"classes": ["py-24"], "customCSS": "", "customClasses": "", "customId": "hero", "minHeight": "", "overflow": ""},
     variants=["image-left", "image-right", "video-right"])

_reg("hero-minimal", "Hero Minimal", "hero", "📝",
     {"headline": "Willkommen",
      "subline": "Kurz und knapp.",
      "cta": {"text": "Los geht's", "href": "#services"},
      "badge": ""},
     {"classes": ["py-20", "text-center"], "customCSS": "", "customClasses": "", "customId": "hero", "minHeight": "", "overflow": ""},
     variants=["text-only", "with-cta", "with-badge"])

# ── About Sections ────────────────────────────────────────────
_reg("about-text-image", "Über Uns (Text + Bild)", "about", "👤",
     {"headline": "Über Uns",
      "text": "Wir sind ein junges Team mit Leidenschaft...",
      "image": {"src": "", "alt": "Über uns", "fit": "cover"}},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "about", "minHeight": "", "overflow": ""},
     variants=["image-left", "image-right", "stacked"])

_reg("about-team", "Team-Grid", "about", "👥",
     {"headline": "Unser Team",
      "subline": "Die Menschen hinter der Marke",
      "members": [
          {"name": "Max Mustermann", "role": "Geschäftsführer", "image": "", "bio": ""},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "team", "minHeight": "", "overflow": ""},
     variants=["grid-3", "grid-4", "carousel"])

_reg("about-stats", "Kennzahlen", "about", "📊",
     {"headline": "In Zahlen",
      "stats": [
          {"value": "12+", "label": "Jahre Erfahrung"},
          {"value": "200+", "label": "Zufriedene Kunden"},
          {"value": "500+", "label": "Projekte"},
      ]},
     {"classes": ["py-16", "bg-surface"], "customCSS": "", "customClasses": "", "customId": "", "minHeight": "", "overflow": ""},
     variants=["counters", "cards", "bars"])

# ── Services ──────────────────────────────────────────────────
_reg("services-grid", "Leistungen Grid", "services", "⚙️",
     {"headline": "Unsere Leistungen",
      "subline": "",
      "items": [
          {"title": "Leistung 1", "description": "Beschreibung...", "icon": "⚡"},
          {"title": "Leistung 2", "description": "Beschreibung...", "icon": "🎯"},
          {"title": "Leistung 3", "description": "Beschreibung...", "icon": "💎"},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "services", "minHeight": "", "overflow": ""},
     variants=["2col", "3col", "4col", "icon-top", "icon-left"])

_reg("services-accordion", "Leistungen Accordion", "services", "📂",
     {"headline": "Unsere Leistungen",
      "items": [
          {"title": "Leistung 1", "content": "Detaillierte Beschreibung..."},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "services", "minHeight": "", "overflow": ""},
     variants=["bordered", "minimal", "colored"])

# ── Portfolio ─────────────────────────────────────────────────
_reg("portfolio-grid", "Portfolio Grid", "portfolio", "🖼️",
     {"headline": "Unsere Arbeiten",
      "subline": "",
      "items": [
          {"title": "Projekt 1", "image": "", "description": "", "tags": [], "url": ""},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "portfolio", "minHeight": "", "overflow": ""},
     variants=["hover-overlay", "hover-zoom", "caption-below"])

# ── Testimonials ──────────────────────────────────────────────
_reg("testimonials-slider", "Kunden-Stimmen Slider", "testimonials", "⭐",
     {"headline": "Was unsere Kunden sagen",
      "items": [
          {"quote": "Fantastischer Service!", "author": "Max M.", "role": "Geschäftsführer", "image": ""},
      ]},
     {"classes": ["py-20", "bg-surface"], "customCSS": "", "customClasses": "", "customId": "testimonials", "minHeight": "", "overflow": ""},
     variants=["cards", "quotes", "minimal"])

_reg("logos-bar", "Kunden-Logos", "testimonials", "🏢",
     {"logos": [
          {"src": "", "alt": "Kunde 1", "url": ""},
      ]},
     {"classes": ["py-12"], "customCSS": "", "customClasses": "", "customId": "", "minHeight": "", "overflow": ""},
     variants=["scroll", "static", "fade"])

# ── Content / Text ────────────────────────────────────────────
_reg("text-block", "Text-Block", "content", "📄",
     {"headline": "",
      "text": "Lorem ipsum dolor sit amet...",
      "align": "left"},
     {"classes": ["py-16"], "customCSS": "", "customClasses": "", "customId": "", "minHeight": "", "overflow": ""},
     variants=["centered", "left", "wide"])

_reg("text-image-alternating", "Text + Bild (alternierend)", "content", "↔️",
     {"items": [
          {"headline": "Feature 1", "text": "Beschreibung...", "image": {"src": "", "alt": ""}},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "", "minHeight": "", "overflow": ""},
     variants=["default", "overlapping", "cards"])

_reg("blockquote", "Zitat", "content", "💬",
     {"quote": "Ein inspirierendes Zitat.",
      "author": "",
      "source": ""},
     {"classes": ["py-16"], "customCSS": "", "customClasses": "", "customId": "", "minHeight": "", "overflow": ""},
     variants=["centered", "side-accent", "full-bg"])

# ── CTA ───────────────────────────────────────────────────────
_reg("cta-banner", "Call-to-Action Banner", "cta", "📢",
     {"headline": "Bereit loszulegen?",
      "subline": "Kontaktieren Sie uns noch heute.",
      "cta": {"text": "Jetzt starten", "href": "#contact"},
      "style": "gradient"},
     {"classes": ["py-16"], "customCSS": "", "customClasses": "", "customId": "", "minHeight": "", "overflow": ""},
     variants=["full-width", "contained", "gradient"])

# ── Features ──────────────────────────────────────────────────
_reg("features-icon-grid", "Features Grid", "features", "✅",
     {"headline": "Warum wir?",
      "subline": "",
      "items": [
          {"title": "Schnell", "description": "Blitzschnelle Umsetzung.", "icon": "⚡"},
          {"title": "Zuverlässig", "description": "100% Qualitätsgarantie.", "icon": "🛡️"},
          {"title": "Persönlich", "description": "Ihr direkter Ansprechpartner.", "icon": "🤝"},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "features", "minHeight": "", "overflow": ""},
     variants=["3col", "4col", "6col"])

_reg("features-comparison", "Vergleichstabelle", "features", "📊",
     {"headline": "Unsere Pakete",
      "plans": [
          {"name": "Basic", "price": "29€/mo", "features": ["Feature 1", "Feature 2"], "cta": {"text": "Wählen", "href": "#"}},
          {"name": "Pro", "price": "59€/mo", "features": ["Feature 1", "Feature 2", "Feature 3"], "cta": {"text": "Wählen", "href": "#"}, "highlighted": True},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "pricing", "minHeight": "", "overflow": ""},
     variants=["table", "cards", "toggle"])

# ── Contact ───────────────────────────────────────────────────
_reg("contact-form", "Kontaktformular", "contact", "📬",
     {"headline": "Kontakt",
      "subline": "Schreiben Sie uns eine Nachricht.",
      "fields": [
          {"name": "name", "label": "Name", "type": "text", "required": True},
          {"name": "email", "label": "E-Mail", "type": "email", "required": True},
          {"name": "message", "label": "Nachricht", "type": "textarea", "required": True},
      ],
      "submitText": "Absenden",
      "successMessage": "Vielen Dank! Wir melden uns bei Ihnen."},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "contact", "minHeight": "", "overflow": ""},
     variants=["simple", "detailed", "with-subject"])

_reg("contact-split", "Kontakt Split (Formular + Info)", "contact", "📍",
     {"headline": "Kontakt",
      "info": {"address": "", "phone": "", "email": "", "hours": ""},
      "fields": [
          {"name": "name", "label": "Name", "type": "text", "required": True},
          {"name": "email", "label": "E-Mail", "type": "email", "required": True},
          {"name": "message", "label": "Nachricht", "type": "textarea", "required": True},
      ],
      "submitText": "Absenden"},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "contact", "minHeight": "", "overflow": ""},
     variants=["map-right", "info-right", "dark"])

# ── Blog ──────────────────────────────────────────────────────
_reg("blog-grid", "Blog Grid", "blog", "📰",
     {"headline": "Neuigkeiten",
      "posts": [
          {"title": "Blog-Post 1", "excerpt": "Kurze Beschreibung...", "image": "", "date": "", "slug": ""},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "blog", "minHeight": "", "overflow": ""},
     variants=["2col", "3col", "list"])

# ── Footer ────────────────────────────────────────────────────
_reg("footer-columns", "Footer (Spalten)", "footer", "🦶",
     {"columns": [
          {"title": "Navigation", "links": [{"label": "Home", "href": "/"}]},
          {"title": "Kontakt", "html": "<p>Muster GmbH</p>"},
      ],
      "copyright": "© {year} Firma. Alle Rechte vorbehalten.",
      "legalLinks": [
          {"label": "Impressum", "href": "/impressum"},
          {"label": "Datenschutz", "href": "/datenschutz"},
      ]},
     {"classes": ["py-12", "bg-gray-900", "text-white"], "customCSS": "", "customClasses": "", "customId": "", "minHeight": "", "overflow": ""},
     variants=["3col", "4col", "2col-asym"])

_reg("footer-minimal", "Footer Minimal", "footer", "📎",
     {"copyright": "© {year} Firma.",
      "legalLinks": [
          {"label": "Impressum", "href": "/impressum"},
          {"label": "Datenschutz", "href": "/datenschutz"},
      ]},
     {"classes": ["py-6", "text-center", "text-sm"], "customCSS": "", "customClasses": "", "customId": "", "minHeight": "", "overflow": ""},
     variants=["centered", "left-aligned"])

# ── Special Sections ──────────────────────────────────────────
_reg("faq-accordion", "FAQ", "special", "❓",
     {"headline": "Häufig gestellte Fragen",
      "items": [
          {"question": "Frage 1?", "answer": "Antwort 1."},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "faq", "minHeight": "", "overflow": ""},
     variants=["simple", "categorized", "searchable"])

_reg("gallery-lightbox", "Bildergalerie", "special", "🖼️",
     {"headline": "Galerie",
      "images": [
          {"src": "", "alt": "Bild 1", "caption": ""},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "gallery", "minHeight": "", "overflow": ""},
     variants=["grid", "masonry", "carousel"])

_reg("parallax-divider", "Parallax-Trenner", "special", "🔮",
     {"image": {"src": "", "alt": ""},
      "height": "400px",
      "text": "",
      "overlay": "rgba(0,0,0,0.3)"},
     {"classes": [], "customCSS": "", "customClasses": "", "customId": "", "minHeight": "400px", "overflow": "hidden"},
     variants=["image", "gradient", "video"])

_reg("video-embed", "Video", "special", "🎥",
     {"headline": "",
      "source": "youtube",
      "url": "",
      "autoplay": False,
      "loop": False},
     {"classes": ["py-16"], "customCSS": "", "customClasses": "", "customId": "", "minHeight": "", "overflow": ""},
     variants=["youtube", "vimeo", "self-hosted"])

_reg("pricing-table", "Preistabelle", "special", "💰",
     {"headline": "Preise",
      "subline": "Wählen Sie das passende Paket.",
      "plans": [
          {"name": "Starter", "price": "0€", "period": "/mo", "features": ["1 Projekt", "Support"],
           "cta": {"text": "Loslegen", "href": "#"}, "highlighted": False},
          {"name": "Pro", "price": "49€", "period": "/mo", "features": ["10 Projekte", "Priority Support", "Custom Domain"],
           "cta": {"text": "Upgrade", "href": "#"}, "highlighted": True},
      ]},
     {"classes": ["py-20"], "customCSS": "", "customClasses": "", "customId": "pricing", "minHeight": "", "overflow": ""},
     variants=["2col", "3col", "toggle-monthly"])


# ── Section Factory ───────────────────────────────────────────

def create_section(type_id: str, variant: str = "", props_override: Optional[dict] = None) -> dict:
    """Create a new section instance from a template."""
    tpl = SECTION_TEMPLATES.get(type_id)
    if not tpl:
        raise ValueError(f"Unknown section type: {type_id}")

    section = {
        "id": gen_id("sec"),
        "type": type_id,
        "variant": variant or (tpl["variants"][0] if tpl["variants"] else ""),
        "props": copy.deepcopy(tpl["defaultProps"]),
        "style": copy.deepcopy(tpl["defaultStyle"]),
        "visibility": {"desktop": True, "tablet": True, "mobile": True},
        "animation": {"type": "none", "delay": 0, "duration": 600},
    }

    if props_override:
        section["props"].update(props_override)

    return section


# ── Validation ────────────────────────────────────────────────

def validate_site(site: dict) -> Tuple[bool, List[str]]:
    """Validate a site.json structure. Returns (valid, errors)."""
    errors = []

    if not isinstance(site, dict):
        return False, ["Site must be a JSON object"]

    # Required top-level keys
    required = ["version", "meta", "design", "nav", "pages", "footer"]
    for key in required:
        if key not in site:
            errors.append(f"Missing required key: {key}")

    # Meta validation
    meta = site.get("meta", {})
    if not meta.get("title"):
        errors.append("meta.title is required")

    # Pages validation
    pages = site.get("pages", [])
    if not pages:
        errors.append("At least one page is required")

    slugs = set()
    for i, page in enumerate(pages):
        slug = page.get("slug", "")
        if not slug:
            errors.append(f"pages[{i}].slug is required")
        elif slug in slugs:
            errors.append(f"Duplicate slug: {slug}")
        slugs.add(slug)

        sections = page.get("sections", [])
        sec_ids = set()
        for j, sec in enumerate(sections):
            sid = sec.get("id", "")
            if not sid:
                errors.append(f"pages[{i}].sections[{j}].id is required")
            elif sid in sec_ids:
                errors.append(f"Duplicate section id: {sid}")
            sec_ids.add(sid)

            stype = sec.get("type", "")
            if not stype:
                errors.append(f"pages[{i}].sections[{j}].type is required")
            elif stype not in SECTION_TEMPLATES:
                errors.append(f"Unknown section type: {stype}")

    # Design validation (just check required color keys)
    design = site.get("design", {})
    colors = design.get("colors", {})
    for ckey in ["primary", "background", "text"]:
        if ckey not in colors:
            errors.append(f"design.colors.{ckey} is required")

    return (len(errors) == 0, errors)


# ── Project CRUD ──────────────────────────────────────────────

def list_projects() -> List[dict]:
    """List all CMS projects with basic info."""
    _ensure_dirs()
    projects = []
    for name in sorted(os.listdir(CMS_BASE)):
        site_path = os.path.join(CMS_BASE, name, "site.json")
        if os.path.isfile(site_path):
            try:
                with open(site_path, 'r', encoding='utf-8') as f:
                    site = json.load(f)
                projects.append({
                    "projectId": site.get("projectId", name),
                    "title": site.get("meta", {}).get("title", name),
                    "slug": name,
                    "updatedAt": site.get("updatedAt", 0),
                    "pageCount": len(site.get("pages", [])),
                    "sectionCount": sum(len(p.get("sections", [])) for p in site.get("pages", [])),
                })
            except Exception:
                continue
    return projects


def load_project(project_slug: str) -> Optional[dict]:
    """Load a project's site.json."""
    site_path = os.path.join(CMS_BASE, project_slug, "site.json")
    if not os.path.isfile(site_path):
        return None
    try:
        with open(site_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_project(project_slug: str, site: dict) -> bool:
    """Save a project's site.json."""
    _ensure_dirs()
    proj_dir = os.path.join(CMS_BASE, project_slug)
    os.makedirs(proj_dir, exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "media"), exist_ok=True)

    site["updatedAt"] = time.time()

    site_path = os.path.join(proj_dir, "site.json")
    try:
        with open(site_path, 'w', encoding='utf-8') as f:
            json.dump(site, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def create_project(title: str) -> Tuple[str, dict]:
    """Create a new project. Returns (slug, site)."""
    _ensure_dirs()
    # Generate slug from title
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    if not slug:
        slug = "website"

    # Ensure unique
    base_slug = slug
    counter = 1
    while os.path.exists(os.path.join(CMS_BASE, slug)):
        slug = f"{base_slug}-{counter}"
        counter += 1

    site = create_blank_site(title)
    save_project(slug, site)
    return slug, site


def delete_project(project_slug: str) -> bool:
    """Delete a project."""
    import shutil
    proj_dir = os.path.join(CMS_BASE, project_slug)
    if os.path.isdir(proj_dir):
        shutil.rmtree(proj_dir)
        return True
    return False


# ── Section Operations ────────────────────────────────────────

def add_section_to_page(site: dict, page_slug: str, section_type: str,
                        variant: str = "", props: Optional[dict] = None,
                        position: int = -1) -> Optional[dict]:
    """Add a section to a page. Returns the new section or None."""
    page = next((p for p in site.get("pages", []) if p["slug"] == page_slug), None)
    if not page:
        return None

    section = create_section(section_type, variant, props)

    if position < 0 or position >= len(page["sections"]):
        page["sections"].append(section)
    else:
        page["sections"].insert(position, section)

    return section


def remove_section(site: dict, page_slug: str, section_id: str) -> bool:
    """Remove a section from a page."""
    page = next((p for p in site.get("pages", []) if p["slug"] == page_slug), None)
    if not page:
        return False

    before = len(page["sections"])
    page["sections"] = [s for s in page["sections"] if s["id"] != section_id]
    return len(page["sections"]) < before


def move_section(site: dict, page_slug: str, section_id: str, new_index: int) -> bool:
    """Move a section to a new position."""
    page = next((p for p in site.get("pages", []) if p["slug"] == page_slug), None)
    if not page:
        return False

    sections = page["sections"]
    idx = next((i for i, s in enumerate(sections) if s["id"] == section_id), None)
    if idx is None:
        return False

    section = sections.pop(idx)
    new_index = max(0, min(new_index, len(sections)))
    sections.insert(new_index, section)
    return True


def update_section(site: dict, page_slug: str, section_id: str, updates: dict) -> bool:
    """Update a section's props/style/variant."""
    page = next((p for p in site.get("pages", []) if p["slug"] == page_slug), None)
    if not page:
        return False

    section = next((s for s in page["sections"] if s["id"] == section_id), None)
    if not section:
        return False

    # Merge updates
    if "props" in updates:
        section["props"].update(updates["props"])
    if "style" in updates:
        section["style"].update(updates["style"])
    if "variant" in updates:
        section["variant"] = updates["variant"]
    if "visibility" in updates:
        section["visibility"].update(updates["visibility"])
    if "animation" in updates:
        section["animation"].update(updates["animation"])

    return True


# ── Page Operations ───────────────────────────────────────────

def add_page(site: dict, title: str, slug: str = "") -> Optional[dict]:
    """Add a new page to the site."""
    import re
    if not slug:
        slug = "/" + re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

    # Check duplicate
    if any(p["slug"] == slug for p in site.get("pages", [])):
        return None

    page = {
        "slug": slug,
        "title": title,
        "meta": {"description": ""},
        "sections": [],
    }
    site["pages"].append(page)
    return page


def remove_page(site: dict, slug: str) -> bool:
    """Remove a page (can't remove the home page '/')."""
    if slug == "/":
        return False
    before = len(site.get("pages", []))
    site["pages"] = [p for p in site["pages"] if p["slug"] != slug]
    return len(site["pages"]) < before
