# -*- coding: utf-8 -*-
"""
Ailey Learning — Curricula & Track Definitions.

Each track is a list of units, each unit has:
  - Lessons (theory + examples)
  - Quizzes (hardcoded multiple-choice / code-completion / true-false)
  - Exercises (LLM-evaluated coding tasks)
  - Projects (larger hands-on projects)

Levels:
  0 = Absolute Beginner (Was ist ein Computer?)
  1 = Beginner (Grundlagen)
  2 = Elementary (Fortgeschrittene Grundlagen)
  3 = Intermediate (Praxisnah)
  4 = Advanced (Professionell)
  5 = Expert (Architekt-Level / Prüfungsreif)
"""

from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────────────────────────
# LEVEL DEFINITIONS
# ──────────────────────────────────────────────────────────────────
LEVELS = {
    0: {"name": "Absolute Beginner", "name_de": "Absoluter Anfänger", "emoji": "🌱", "xp_per_unit": 50},
    1: {"name": "Beginner", "name_de": "Anfänger", "emoji": "🌿", "xp_per_unit": 100},
    2: {"name": "Elementary", "name_de": "Fortgeschrittener Anfänger", "emoji": "🌳", "xp_per_unit": 200},
    3: {"name": "Intermediate", "name_de": "Fortgeschritten", "emoji": "⚡", "xp_per_unit": 300},
    4: {"name": "Advanced", "name_de": "Profi", "emoji": "🔥", "xp_per_unit": 500},
    5: {"name": "Expert", "name_de": "Experte", "emoji": "💎", "xp_per_unit": 800},
}

# ──────────────────────────────────────────────────────────────────
# QUIZ QUESTION TYPES
# ──────────────────────────────────────────────────────────────────
# type: "mc" = multiple choice, "tf" = true/false, "code" = write code,
#       "fill" = fill the blank, "order" = order steps, "match" = match pairs

def _q(qtype: str, question: str, **kwargs) -> Dict:
    """Helper to build a quiz question."""
    return {"type": qtype, "question": question, **kwargs}

def mc(question: str, options: List[str], correct: int, explanation: str = "") -> Dict:
    return _q("mc", question, options=options, correct=correct, explanation=explanation)

def tf(question: str, correct: bool, explanation: str = "") -> Dict:
    return _q("tf", question, correct=correct, explanation=explanation)

def code(question: str, language: str, starter: str = "", test_code: str = "", hint: str = "") -> Dict:
    return _q("code", question, language=language, starter=starter, test_code=test_code, hint=hint)

def fill(question: str, blanks: List[str], explanation: str = "") -> Dict:
    return _q("fill", question, blanks=blanks, explanation=explanation)

def match(question: str, pairs: List[List[str]], explanation: str = "") -> Dict:
    return _q("match", question, pairs=pairs, explanation=explanation)


# ──────────────────────────────────────────────────────────────────
# UNIT/LESSON BUILDER
# ──────────────────────────────────────────────────────────────────
def unit(uid: str, title: str, level: int, theory: str,
         examples: List[Dict] = None, quiz: List[Dict] = None,
         exercise: Dict = None, tags: List[str] = None) -> Dict:
    return {
        "id": uid,
        "title": title,
        "level": level,
        "theory": theory,
        "examples": examples or [],
        "quiz": quiz or [],
        "exercise": exercise,
        "tags": tags or [],
    }


# ══════════════════════════════════════════════════════════════════
# TRACK: HTML
# ══════════════════════════════════════════════════════════════════
HTML_TRACK = {
    "id": "html",
    "name": "HTML",
    "icon": "🌐",
    "description": "HyperText Markup Language — Das Fundament des Web",
    "color": "#e34c26",
    "units": [
        # ── Level 0: Absolute Basics ──
        unit("html-0-1", "Was ist HTML?", 0,
            "HTML steht für **HyperText Markup Language**. Es ist die Sprache, mit der Webseiten strukturiert werden.\n\n"
            "HTML besteht aus **Tags** (Auszeichnungen), die den Browser anweisen, wie Inhalte angezeigt werden sollen.\n\n"
            "Ein HTML-Dokument ist wie das Skelett einer Webseite — es definiert die Struktur, nicht das Aussehen.",
            examples=[
                {"title": "Einfachste Webseite", "code": "<!DOCTYPE html>\n<html>\n<head>\n  <title>Meine Seite</title>\n</head>\n<body>\n  <h1>Hallo Welt!</h1>\n  <p>Mein erster Absatz.</p>\n</body>\n</html>", "lang": "html"}
            ],
            quiz=[
                mc("Wofür steht HTML?", ["HyperText Markup Language", "High Tech Modern Language", "Home Tool Markup Language", "HyperText Machine Learning"], 0, "HTML = HyperText Markup Language"),
                tf("HTML ist eine Programmiersprache.", False, "HTML ist eine Auszeichnungssprache (Markup Language), keine Programmiersprache."),
                mc("Welches Tag definiert die Hauptüberschrift?", ["<h1>", "<head>", "<header>", "<title>"], 0),
                fill("Ein HTML-Dokument beginnt immer mit ___.", ["<!DOCTYPE html>"], "DOCTYPE teilt dem Browser mit, dass es sich um HTML5 handelt."),
            ],
            exercise={"task": "Erstelle eine HTML-Seite mit deinem Namen als Überschrift und einem kurzen Absatz über dich.", "language": "html"},
            tags=["grundlagen", "einführung"]),

        unit("html-0-2", "Tags, Elemente & Attribute", 0,
            "**Tags** kommen meist paarweise: `<p>` (öffnend) und `</p>` (schließend).\n\n"
            "Ein **Element** ist alles zwischen öffnendem und schließendem Tag: `<p>Text</p>`.\n\n"
            "**Attribute** geben zusätzliche Infos: `<a href=\"https://example.com\">Link</a>`.\n\n"
            "Manche Tags sind **selbstschließend**: `<br>`, `<img>`, `<hr>`.",
            quiz=[
                mc("Welches ist ein selbstschließendes Tag?", ["<br>", "<p>", "<div>", "<span>"], 0),
                tf("<img> braucht ein schließendes Tag </img>.", False, "<img> ist selbstschließend."),
                mc("Was ist ein Attribut in <a href='url'>?", ["href='url'", "<a>", "url", "</a>"], 0),
                fill("Um ein Bild einzufügen nutzt man das Tag ___.", ["<img>", "img"], "Das <img>-Tag mit src-Attribut."),
            ],
            tags=["grundlagen", "syntax"]),

        unit("html-0-3", "Überschriften & Absätze", 0,
            "HTML hat 6 Überschriften-Ebenen: `<h1>` bis `<h6>`.\n\n"
            "`<h1>` ist die wichtigste Überschrift (pro Seite nur 1x empfohlen).\n\n"
            "`<p>` erstellt Absätze. `<br>` erzeugt einen Zeilenumbruch.\n\n"
            "`<hr>` zeichnet eine horizontale Linie.",
            examples=[
                {"title": "Überschriften-Hierarchie", "code": "<h1>Haupttitel</h1>\n<h2>Unterkapitel</h2>\n<h3>Abschnitt</h3>\n<p>Fließtext hier.</p>\n<hr>\n<p>Neuer Abschnitt nach der Linie.</p>", "lang": "html"}
            ],
            quiz=[
                mc("Wie viele Überschriften-Ebenen gibt es?", ["6", "3", "4", "10"], 0),
                tf("<h1> sollte nur einmal pro Seite verwendet werden.", True, "Best Practice für SEO und Zugänglichkeit."),
                mc("Welches Tag erstellt einen Absatz?", ["<p>", "<para>", "<text>", "<br>"], 0),
            ],
            tags=["text", "semantik"]),

        # ── Level 1: Beginner ──
        unit("html-1-1", "Listen: ul, ol, dl", 1,
            "`<ul>` = Ungeordnete Liste (Aufzählungspunkte)\n"
            "`<ol>` = Geordnete Liste (Nummerierung)\n"
            "`<li>` = Listenelement\n"
            "`<dl>` = Definitionsliste mit `<dt>` (Term) und `<dd>` (Definition).",
            examples=[
                {"title": "Verschiedene Listen", "code": "<ul>\n  <li>Apfel</li>\n  <li>Birne</li>\n</ul>\n\n<ol>\n  <li>Erster Schritt</li>\n  <li>Zweiter Schritt</li>\n</ol>\n\n<dl>\n  <dt>HTML</dt>\n  <dd>Auszeichnungssprache für Web</dd>\n</dl>", "lang": "html"}
            ],
            quiz=[
                mc("Welches Tag erstellt eine nummerierte Liste?", ["<ol>", "<ul>", "<nl>", "<list>"], 0),
                tf("<li> kann nur in <ul> verwendet werden.", False, "<li> funktioniert in <ul> und <ol>."),
                fill("Für eine Definitionsliste nutzt man ___, ___ und ___.", ["<dl>", "<dt>", "<dd>"]),
            ],
            tags=["listen", "struktur"]),

        unit("html-1-2", "Links & Navigation", 1,
            "Links werden mit `<a href=\"URL\">Text</a>` erstellt.\n\n"
            "- `href` = Ziel-URL\n"
            "- `target=\"_blank\"` = in neuem Tab öffnen\n"
            "- `rel=\"noopener\"` = Sicherheit bei externen Links\n"
            "- Anker-Links: `<a href=\"#abschnitt\">` springt zu `id=\"abschnitt\"`",
            quiz=[
                mc("Welches Attribut definiert das Link-Ziel?", ["href", "src", "link", "target"], 0),
                mc("Wie öffnet man einen Link in einem neuen Tab?", ["target=\"_blank\"", "new=\"tab\"", "open=\"new\"", "href=\"_blank\""], 0),
                code("Erstelle einen Link zu https://example.com mit dem Text 'Beispiel'.", "html", "<a ___>___</a>"),
            ],
            tags=["links", "navigation"]),

        unit("html-1-3", "Bilder & Multimedia", 1,
            "`<img src=\"bild.jpg\" alt=\"Beschreibung\">` — Bilder einbinden.\n\n"
            "- `alt` ist PFLICHT für Barrierefreiheit\n"
            "- `width`/`height` definieren die Größe\n"
            "- `<figure>` + `<figcaption>` für Bilder mit Beschriftung\n\n"
            "`<video>` und `<audio>` für Multimedia:\n"
            "```html\n<video src=\"video.mp4\" controls></video>\n```",
            quiz=[
                mc("Welches Attribut ist bei <img> Pflicht für Barrierefreiheit?", ["alt", "title", "src", "name"], 0),
                tf("<img> hat ein schließendes Tag.", False),
                mc("Welches Tag bettet Video ein?", ["<video>", "<movie>", "<media>", "<film>"], 0),
            ],
            tags=["bilder", "multimedia"]),

        # ── Level 2: Fortgeschrittene Grundlagen ──
        unit("html-2-1", "Tabellen", 2,
            "`<table>` erstellt eine Tabelle:\n"
            "- `<thead>` / `<tbody>` / `<tfoot>` = Bereiche\n"
            "- `<tr>` = Tabellenzeile\n"
            "- `<th>` = Kopfzelle (fett/zentriert)\n"
            "- `<td>` = Datenzelle\n"
            "- `colspan` / `rowspan` = Zellen zusammenführen",
            examples=[
                {"title": "Einfache Tabelle", "code": "<table>\n  <thead>\n    <tr><th>Name</th><th>Alter</th></tr>\n  </thead>\n  <tbody>\n    <tr><td>Anna</td><td>28</td></tr>\n    <tr><td>Ben</td><td>34</td></tr>\n  </tbody>\n</table>", "lang": "html"}
            ],
            quiz=[
                mc("Welches Tag definiert eine Tabellenkopfzelle?", ["<th>", "<td>", "<thead>", "<tc>"], 0),
                fill("Um zwei Spalten zusammenzuführen nutzt man das Attribut ___.", ["colspan"]),
                tf("<tr> steht für table row.", True),
            ],
            tags=["tabellen", "daten"]),

        unit("html-2-2", "Formulare", 2,
            "Formulare mit `<form>` — das Herzstück interaktiver Webseiten:\n\n"
            "- `<input type=\"text\">` — Textfeld\n"
            "- `<input type=\"email\">` — E-Mail mit Validierung\n"
            "- `<input type=\"password\">` — Passwort\n"
            "- `<input type=\"checkbox\">` / `<input type=\"radio\">`\n"
            "- `<textarea>` — Mehrzeiliger Text\n"
            "- `<select>` + `<option>` — Dropdown\n"
            "- `<button type=\"submit\">` — Absenden\n"
            "- `<label for=\"id\">` — Beschriftung (wichtig für Accessibility!)",
            examples=[
                {"title": "Kontaktformular", "code": "<form action=\"/send\" method=\"POST\">\n  <label for=\"name\">Name:</label>\n  <input type=\"text\" id=\"name\" name=\"name\" required>\n\n  <label for=\"email\">E-Mail:</label>\n  <input type=\"email\" id=\"email\" name=\"email\" required>\n\n  <label for=\"msg\">Nachricht:</label>\n  <textarea id=\"msg\" name=\"message\"></textarea>\n\n  <button type=\"submit\">Absenden</button>\n</form>", "lang": "html"}
            ],
            quiz=[
                mc("Welches Attribut macht ein Feld zum Pflichtfeld?", ["required", "mandatory", "must", "needed"], 0),
                mc("Welches type zeigt ein Passwortfeld?", ["password", "secret", "hidden", "encrypted"], 0),
                tf("<label> verbessert die Barrierefreiheit.", True),
                code("Erstelle ein Formular mit einem E-Mail-Feld und einem Submit-Button.", "html"),
            ],
            tags=["formulare", "interaktiv"]),

        unit("html-2-3", "Semantisches HTML", 2,
            "Semantische Tags geben dem Inhalt **Bedeutung**:\n\n"
            "- `<header>` — Kopfbereich\n"
            "- `<nav>` — Navigation\n"
            "- `<main>` — Hauptinhalt\n"
            "- `<article>` — Eigenständiger Inhalt\n"
            "- `<section>` — Thematischer Abschnitt\n"
            "- `<aside>` — Seitenleiste\n"
            "- `<footer>` — Fußbereich\n\n"
            "Warum? SEO, Accessibility, Wartbarkeit!",
            quiz=[
                mc("Welches Tag markiert den Hauptinhalt?", ["<main>", "<content>", "<body>", "<section>"], 0),
                tf("<div> ist ein semantisches Tag.", False, "<div> ist ein generisches Container-Element ohne semantische Bedeutung."),
                match("Ordne die Tags ihrer Funktion zu:", [
                    ["<nav>", "Navigation"],
                    ["<article>", "Eigenständiger Inhalt"],
                    ["<aside>", "Seitenleiste"],
                    ["<footer>", "Fußbereich"],
                ]),
            ],
            tags=["semantik", "seo", "accessibility"]),

        # ── Level 3: Intermediate ──
        unit("html-3-1", "Meta-Tags & SEO", 3,
            "Der `<head>` enthält wichtige Meta-Informationen:\n\n"
            "```html\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n<meta name=\"description\" content=\"Seitenbeschreibung\">\n<meta name=\"robots\" content=\"index, follow\">\n<link rel=\"canonical\" href=\"https://...\">\n```\n\n"
            "Open Graph für Social Media:\n"
            "```html\n<meta property=\"og:title\" content=\"Titel\">\n<meta property=\"og:image\" content=\"bild.jpg\">\n```",
            quiz=[
                mc("Welches Meta-Tag ist für responsives Design wichtig?", ["viewport", "charset", "description", "robots"], 0),
                tf("meta description beeinflusst das Google-Ranking direkt.", False, "Es beeinflusst die Klickrate (CTR), nicht das Ranking direkt."),
                fill("Open Graph Tags nutzen das Attribut ___ statt name.", ["property"]),
            ],
            tags=["meta", "seo", "head"]),

        unit("html-3-2", "Accessibility (ARIA & Best Practices)", 3,
            "Web-Accessibility = Webseiten für ALLE Menschen nutzbar machen.\n\n"
            "Grundregeln:\n"
            "1. Alle Bilder brauchen `alt`-Text\n"
            "2. Formulare brauchen `<label>`\n"
            "3. Semantische Tags verwenden statt `<div>` für alles\n"
            "4. Keyboard-Navigation ermöglichen (`tabindex`)\n\n"
            "ARIA-Attribute:\n"
            "- `role=\"button\"` — Element als Button kennzeichnen\n"
            "- `aria-label=\"Beschreibung\"` — Unsichtbare Beschriftung\n"
            "- `aria-hidden=\"true\"` — Vor Screenreadern verstecken\n"
            "- `aria-live=\"polite\"` — Dynamische Änderungen ankündigen",
            quiz=[
                mc("Was bedeutet ARIA?", ["Accessible Rich Internet Applications", "Advanced Rendering Interface API", "Automatic Reader Integration Addon", "Application Resource Identification Attributes"], 0),
                tf("aria-hidden='true' versteckt ein Element visuell.", False, "Es versteckt es nur vor Screenreadern."),
                code("Erstelle einen Button mit aria-label für Screenreader.", "html", '<button ___>❤️</button>'),
            ],
            tags=["accessibility", "aria", "inklusion"]),

        # ── Level 4: Advanced ──
        unit("html-4-1", "Web Components & Custom Elements", 4,
            "**Web Components** erlauben eigene HTML-Tags:\n\n"
            "```html\n<my-card title=\"Hallo\">\n  <p>Inhalt</p>\n</my-card>\n```\n\n"
            "Drei Technologien:\n"
            "1. **Custom Elements** — `customElements.define('my-card', MyCard)`\n"
            "2. **Shadow DOM** — Gekapseltes CSS/HTML\n"
            "3. **Templates** — `<template>` und `<slot>`",
            quiz=[
                mc("Welche API registriert Custom Elements?", ["customElements.define()", "document.createElement()", "HTML.register()", "element.create()"], 0),
                tf("Shadow DOM verhindert CSS-Leaks nach außen.", True),
            ],
            tags=["webcomponents", "advanced"]),

        unit("html-4-2", "Canvas & SVG", 4,
            "`<canvas>` — Pixel-basierte Grafiken per JavaScript:\n"
            "```html\n<canvas id=\"c\" width=\"400\" height=\"300\"></canvas>\n```\n\n"
            "`<svg>` — Vektorbasierte Grafiken direkt im HTML:\n"
            "```html\n<svg width=\"100\" height=\"100\">\n  <circle cx=\"50\" cy=\"50\" r=\"40\" fill=\"red\"/>\n</svg>\n```\n\n"
            "Canvas = Pixel (Games, Charts) | SVG = Vektoren (Icons, Logos)",
            quiz=[
                mc("Was ist der Hauptunterschied zwischen Canvas und SVG?", ["Canvas = Pixel, SVG = Vektoren", "Canvas = 2D, SVG = 3D", "Canvas = statisch, SVG = animiert", "Kein Unterschied"], 0),
                tf("SVG-Elemente können per CSS gestyled werden.", True),
            ],
            tags=["canvas", "svg", "grafik"]),

        # ── Level 5: Expert ──
        unit("html-5-1", "Performance & Best Practices", 5,
            "HTML-Performance-Optimierung:\n\n"
            "- `<link rel=\"preload\">` — Kritische Ressourcen vorladen\n"
            "- `<link rel=\"prefetch\">` — Nächste Seite vorbereiten\n"
            "- `loading=\"lazy\"` auf `<img>` und `<iframe>`\n"
            "- `<script defer>` / `<script async>` statt blocking\n"
            "- `<picture>` mit `<source>` für responsive Bilder\n"
            "- Critical CSS inline im `<head>`\n"
            "- `<meta http-equiv=\"Content-Security-Policy\">`",
            quiz=[
                mc("Welches Attribut lädt Bilder erst beim Scrollen?", ["loading=\"lazy\"", "defer", "async", "preload"], 0),
                mc("Was ist der Unterschied zwischen defer und async bei <script>?", ["defer wartet auf HTML-Parsing, async nicht", "Kein Unterschied", "async wartet, defer nicht", "defer ist schneller"], 0),
                tf("Inline CSS im <head> kann die First Contentful Paint Zeit verbessern.", True),
            ],
            tags=["performance", "optimierung", "best-practices"]),
    ],
}

# ══════════════════════════════════════════════════════════════════
# TRACK: CSS
# ══════════════════════════════════════════════════════════════════
CSS_TRACK = {
    "id": "css",
    "name": "CSS",
    "icon": "🎨",
    "description": "Cascading Style Sheets — Webseiten gestalten",
    "color": "#264de4",
    "units": [
        unit("css-0-1", "Was ist CSS?", 0,
            "CSS steht für **Cascading Style Sheets**.\n\n"
            "Es beschreibt das **Aussehen** von HTML-Elementen:\n"
            "Farben, Schriftarten, Abstände, Layouts.\n\n"
            "3 Wege CSS einzubinden:\n"
            "1. **Inline**: `<p style=\"color: red\">`\n"
            "2. **Internal**: `<style>` im `<head>`\n"
            "3. **External**: `<link rel=\"stylesheet\" href=\"style.css\">`",
            quiz=[
                mc("Wofür steht CSS?", ["Cascading Style Sheets", "Computer Style System", "Creative Styling Software", "Coded Style Syntax"], 0),
                tf("CSS ist für die Struktur einer Webseite zuständig.", False, "HTML = Struktur, CSS = Aussehen."),
                mc("Welche CSS-Einbindung ist Best Practice?", ["Externe .css-Datei", "Inline-Styles", "Internal <style>", "JavaScript"], 0),
            ],
            tags=["grundlagen"]),

        unit("css-0-2", "Selektoren & Eigenschaften", 0,
            "CSS-Syntax: `selektor { eigenschaft: wert; }`\n\n"
            "Selektoren:\n"
            "- `p` — Alle Absätze\n"
            "- `.klasse` — Elemente mit class=\"klasse\"\n"
            "- `#id` — Element mit id=\"id\"\n"
            "- `*` — Alle Elemente\n\n"
            "Wichtige Eigenschaften:\n"
            "- `color` — Textfarbe\n"
            "- `background-color` — Hintergrundfarbe\n"
            "- `font-size` — Schriftgröße\n"
            "- `margin` / `padding` — Abstände",
            examples=[
                {"title": "Erste Styles", "code": "h1 {\n  color: #e11d48;\n  font-size: 2rem;\n}\n\n.highlight {\n  background-color: yellow;\n  padding: 4px 8px;\n}\n\n#header {\n  border-bottom: 2px solid #333;\n}", "lang": "css"}
            ],
            quiz=[
                mc("Wie selektiert man alle Elemente mit class='box'?", [".box", "#box", "box", "*box"], 0),
                mc("Welcher Selektor hat die höchste Spezifität?", ["#id", ".class", "element", "*"], 0),
                fill("Um den Abstand innerhalb eines Elements zu setzen, nutzt man ___.", ["padding"]),
                fill("Um den Abstand außerhalb eines Elements zu setzen, nutzt man ___.", ["margin"]),
            ],
            tags=["selektoren", "grundlagen"]),

        # ── Level 1 ──
        unit("css-1-1", "Box Model", 1,
            "Jedes HTML-Element ist eine **Box** mit 4 Schichten:\n\n"
            "1. **Content** — Der Inhalt\n"
            "2. **Padding** — Innenabstand\n"
            "3. **Border** — Rahmen\n"
            "4. **Margin** — Außenabstand\n\n"
            "`box-sizing: border-box` — Padding und Border werden IN die Breite gerechnet (empfohlen!).\n"
            "`box-sizing: content-box` — Standard, Padding wird DAZU gerechnet.",
            quiz=[
                mc("Welche Schicht liegt zwischen Content und Border?", ["Padding", "Margin", "Outline", "Shadow"], 0),
                tf("box-sizing: border-box ist der CSS-Standard.", False, "Der Standard ist content-box."),
                mc("margin: 10px 20px bedeutet:", ["10px oben/unten, 20px links/rechts", "10px links/rechts, 20px oben/unten", "10px überall, dann 20px", "Ungültig"], 0),
            ],
            tags=["box-model", "layout"]),

        unit("css-1-2", "Farben & Einheiten", 1,
            "Farbformate:\n"
            "- Keywords: `red`, `blue`, `rebeccapurple`\n"
            "- Hex: `#ff0000`, `#f00`\n"
            "- RGB: `rgb(255, 0, 0)`\n"
            "- HSL: `hsl(0, 100%, 50%)`\n"
            "- Mit Alpha: `rgba()`, `hsla()`, `#ff000080`\n\n"
            "Einheiten:\n"
            "- `px` — Pixel (absolut)\n"
            "- `rem` — Relativ zum Root-Element\n"
            "- `em` — Relativ zum Elternelement\n"
            "- `%` — Prozent\n"
            "- `vw`/`vh` — Viewport-Breite/Höhe",
            quiz=[
                mc("Was bedeutet 1rem?", ["Die Schriftgröße des Root-Elements (html)", "1 Pixel", "Die Schriftgröße des Elternelements", "1% der Viewport-Breite"], 0),
                tf("#fff ist die Kurzform für #ffffff.", True),
                mc("Welche Einheit ist relativ zum Viewport?", ["vw", "rem", "em", "px"], 0),
            ],
            tags=["farben", "einheiten"]),

        # ── Level 2 ──
        unit("css-2-1", "Flexbox", 2,
            "Flexbox = Eindimensionales Layout (Zeile ODER Spalte).\n\n"
            "```css\n.container {\n  display: flex;\n  justify-content: center;  /* Hauptachse */\n  align-items: center;      /* Querachse */\n  gap: 1rem;\n}\n```\n\n"
            "Wichtige Properties:\n"
            "- `flex-direction`: row | column\n"
            "- `flex-wrap`: nowrap | wrap\n"
            "- `justify-content`: flex-start | center | space-between | space-around\n"
            "- `align-items`: stretch | center | flex-start | flex-end\n"
            "- `flex: 1` auf Kinder — gleichmäßig verteilen",
            quiz=[
                mc("Flexbox ist ein ___-dimensionales Layout.", ["ein", "zwei", "drei", "null"], 0),
                mc("Welches Property zentriert Elemente auf der Hauptachse?", ["justify-content", "align-items", "text-align", "margin"], 0),
                tf("flex-wrap: wrap erlaubt Umbruch auf neue Zeilen.", True),
                code("Zentriere ein Element vertikal und horizontal mit Flexbox.", "css", ".container {\n  display: ___;\n  ___: center;\n  ___: center;\n}"),
            ],
            tags=["flexbox", "layout"]),

        unit("css-2-2", "CSS Grid", 2,
            "Grid = **Zweidimensionales** Layout (Zeilen UND Spalten gleichzeitig).\n\n"
            "```css\n.grid {\n  display: grid;\n  grid-template-columns: 1fr 2fr 1fr;\n  grid-template-rows: auto 1fr auto;\n  gap: 1rem;\n}\n```\n\n"
            "- `fr` = Fraction (anteilig)\n"
            "- `repeat(3, 1fr)` = 3 gleiche Spalten\n"
            "- `minmax(200px, 1fr)` = mindestens 200px\n"
            "- `grid-column: 1 / 3` = Spalte 1 bis 3 spannen",
            quiz=[
                mc("Grid ist ein ___-dimensionales Layout.", ["zwei", "ein", "drei", "null"], 0),
                mc("Was bedeutet 1fr?", ["Ein gleichmäßiger Anteil des verfügbaren Platzes", "1 Frame", "1 Font-Relative Einheit", "1 Pixel"], 0),
                fill("repeat(3, 1fr) erstellt ___ gleich große Spalten.", ["3", "drei"]),
            ],
            tags=["grid", "layout"]),

        # ── Level 3 ──
        unit("css-3-1", "Responsive Design & Media Queries", 3,
            "Responsive Design = Webseite passt sich der Bildschirmgröße an.\n\n"
            "```css\n/* Mobile First! */\n.container { padding: 1rem; }\n\n@media (min-width: 768px) {\n  .container { padding: 2rem; max-width: 720px; }\n}\n\n@media (min-width: 1024px) {\n  .container { max-width: 960px; }\n}\n```\n\n"
            "Mobile First = Basis-Styles für Mobile, erweitern für größere Screens.",
            quiz=[
                mc("Was bedeutet 'Mobile First'?", ["Zuerst für Mobile designen, dann erweitern", "Mobile-App zuerst bauen", "Nur für Mobile designen", "Desktop ignorieren"], 0),
                tf("@media (max-width: 768px) gilt für Bildschirme bis 768px.", True),
                code("Schreibe eine Media Query die ab 1024px die Schriftgröße auf 18px setzt.", "css"),
            ],
            tags=["responsive", "media-queries"]),

        unit("css-3-2", "Animationen & Transitions", 3,
            "**Transitions** — Sanfte Übergänge zwischen Zuständen:\n"
            "```css\n.btn {\n  transition: background-color 0.3s ease, transform 0.2s;\n}\n.btn:hover {\n  background-color: #e11d48;\n  transform: scale(1.05);\n}\n```\n\n"
            "**Animations** — Keyframe-basierte Animationen:\n"
            "```css\n@keyframes fadeIn {\n  from { opacity: 0; transform: translateY(20px); }\n  to { opacity: 1; transform: translateY(0); }\n}\n.element {\n  animation: fadeIn 0.5s ease forwards;\n}\n```",
            quiz=[
                mc("Welches Property ermöglicht sanfte Hover-Übergänge?", ["transition", "animation", "transform", "hover"], 0),
                tf("@keyframes kann beliebig viele Schritte (%) haben.", True),
                mc("Was macht 'forwards' bei animation?", ["Behält den Endzustand bei", "Spielt vorwärts ab", "Startet von vorne", "Beschleunigt"], 0),
            ],
            tags=["animationen", "transitions"]),

        # ── Level 4 ──
        unit("css-4-1", "Custom Properties (CSS Variables)", 4,
            "CSS Custom Properties (Variables):\n\n"
            "```css\n:root {\n  --primary: #e11d48;\n  --radius: 8px;\n  --font-body: 'Inter', sans-serif;\n}\n\n.button {\n  background: var(--primary);\n  border-radius: var(--radius);\n  font-family: var(--font-body);\n}\n```\n\n"
            "- Definiert mit `--name`\n"
            "- Genutzt mit `var(--name)`\n"
            "- Kaskadieren! Können per Element überschrieben werden\n"
            "- Perfekt für Theming (Dark Mode etc.)",
            quiz=[
                mc("Wie definiert man eine CSS-Variable?", ["--name: wert;", "$name: wert;", "@name: wert;", "var name = wert;"], 0),
                tf("CSS-Variablen können im JavaScript gelesen und gesetzt werden.", True),
            ],
            tags=["variables", "theming"]),

        # ── Level 5 ──
        unit("css-5-1", "Architektur: BEM, Utility-First, CSS-in-JS", 5,
            "CSS-Architekturen für große Projekte:\n\n"
            "**BEM (Block-Element-Modifier)**:\n"
            "```css\n.card { } .card__title { } .card--featured { }\n```\n\n"
            "**Utility-First (Tailwind-Stil)**:\n"
            "```html\n<div class=\"flex items-center gap-4 p-4 bg-white rounded-lg shadow\">\n```\n\n"
            "**CSS-in-JS (styled-components)**:\n"
            "```jsx\nconst Button = styled.button`\n  background: ${p => p.primary ? 'blue' : 'gray'};\n`;\n```\n\n"
            "Jeder Ansatz hat Vor- und Nachteile für Wartbarkeit und Performance.",
            quiz=[
                mc("Was steht für 'Block-Element-Modifier'?", ["BEM", "CSS", "SASS", "LESS"], 0),
                tf("Tailwind CSS ist ein Utility-First Framework.", True),
                mc("Was ist ein Nachteil von CSS-in-JS?", ["Größere Bundle-Size & Runtime-Overhead", "Keine Variablen möglich", "Kein Responsive Design", "Kein Flexbox-Support"], 0),
            ],
            tags=["architektur", "bem", "tailwind"]),
    ],
}

# ══════════════════════════════════════════════════════════════════
# TRACK: JAVASCRIPT
# ══════════════════════════════════════════════════════════════════
JS_TRACK = {
    "id": "javascript",
    "name": "JavaScript",
    "icon": "⚡",
    "description": "Die Programmiersprache des Web — interaktiv, dynamisch, überall",
    "color": "#f7df1e",
    "units": [
        unit("js-0-1", "Was ist JavaScript?", 0,
            "JavaScript (JS) ist die **Programmiersprache des Web**.\n\n"
            "- Läuft im Browser (Frontend)\n"
            "- Läuft auf Servern (Node.js)\n"
            "- Macht Webseiten interaktiv\n"
            "- Nicht verwandt mit Java!\n\n"
            "```javascript\nconsole.log('Hallo Welt!');\nalert('Willkommen!');\n```",
            quiz=[
                tf("JavaScript und Java sind das Gleiche.", False),
                mc("Wo kann JavaScript ausgeführt werden?", ["Im Browser und auf Servern", "Nur im Browser", "Nur auf Servern", "Nur in Apps"], 0),
                mc("Wie gibt man etwas in der Konsole aus?", ["console.log()", "print()", "echo()", "write()"], 0),
            ],
            tags=["grundlagen"]),

        unit("js-0-2", "Variablen & Datentypen", 0,
            "3 Wege Variablen zu deklarieren:\n"
            "- `let` — Veränderbarer Wert (empfohlen)\n"
            "- `const` — Konstanter Wert (empfohlen für alles was sich nicht ändert)\n"
            "- `var` — Alt, vermeiden!\n\n"
            "Datentypen:\n"
            "- `string` — `'Hallo'` oder `\"Welt\"`\n"
            "- `number` — `42`, `3.14`\n"
            "- `boolean` — `true`, `false`\n"
            "- `null` / `undefined`\n"
            "- `object` / `array`",
            quiz=[
                mc("Welches Keyword sollte man für Konstanten nutzen?", ["const", "let", "var", "static"], 0),
                tf("typeof null === 'object' in JavaScript.", True, "Das ist ein bekannter Bug/Quirk in JS."),
                mc("Was ist der Typ von 42?", ["number", "int", "integer", "float"], 0),
                fill("___ wird für veränderbare Variablen empfohlen.", ["let"]),
            ],
            tags=["variablen", "datentypen"]),

        unit("js-1-1", "Funktionen", 1,
            "Funktionen = Wiederverwendbare Code-Blöcke.\n\n"
            "```javascript\n// Function Declaration\nfunction greet(name) {\n  return `Hallo, ${name}!`;\n}\n\n// Arrow Function (modern)\nconst greet = (name) => `Hallo, ${name}!`;\n\n// Function Expression\nconst add = function(a, b) { return a + b; };\n```\n\n"
            "Arrow Functions haben kein eigenes `this`!",
            quiz=[
                mc("Was ist der Unterschied zwischen Arrow und normalen Funktionen?", ["Arrow Functions haben kein eigenes 'this'", "Arrow Functions sind schneller", "Arrow Functions können keine Parameter haben", "Kein Unterschied"], 0),
                code("Schreibe eine Arrow Function 'double' die eine Zahl verdoppelt.", "javascript", "const double = "),
                tf("Funktionen können andere Funktionen als Parameter bekommen.", True, "Das nennt man Higher-Order Functions."),
            ],
            tags=["funktionen", "arrow"]),

        unit("js-1-2", "Arrays & Objekte", 1,
            "**Arrays** — Geordnete Listen:\n"
            "```javascript\nconst fruits = ['Apfel', 'Birne', 'Kirsche'];\nfruits.push('Banane');  // Am Ende hinzufügen\nfruits[0];              // 'Apfel'\nfruits.length;          // 4\n```\n\n"
            "**Objekte** — Key-Value-Paare:\n"
            "```javascript\nconst person = {\n  name: 'Anna',\n  age: 28,\n  greet() { return `Hi, ich bin ${this.name}`; }\n};\n```",
            quiz=[
                mc("Wie fügt man ein Element am Ende eines Arrays hinzu?", ["push()", "add()", "append()", "insert()"], 0),
                fill("Die Länge eines Arrays bekommt man mit ___.", ["length", ".length"]),
                mc("Wie greift man auf den Wert 'name' in einem Objekt zu?", ["obj.name oder obj['name']", "obj->name", "obj::name", "obj.get('name')"], 0),
            ],
            tags=["arrays", "objekte"]),

        unit("js-2-1", "DOM-Manipulation", 2,
            "Das **DOM** (Document Object Model) ist die Baumstruktur einer Webseite.\n\n"
            "```javascript\n// Element finden\nconst el = document.querySelector('.btn');\nconst all = document.querySelectorAll('p');\n\n// Inhalt ändern\nel.textContent = 'Neuer Text';\nel.innerHTML = '<strong>Fett</strong>';\n\n// Klassen\nel.classList.add('active');\nel.classList.toggle('hidden');\n\n// Events\nel.addEventListener('click', () => {\n  console.log('Geklickt!');\n});\n```",
            quiz=[
                mc("Welche Methode findet das erste passende Element?", ["querySelector()", "getElementById()", "getElementsByClassName()", "findElement()"], 0),
                tf("innerHTML kann XSS-Sicherheitsrisiken verursachen.", True),
                code("Füge einem Button mit der ID 'myBtn' einen Click-Event-Listener hinzu.", "javascript"),
            ],
            tags=["dom", "events"]),

        unit("js-2-2", "Asynchrones JavaScript: Promises & async/await", 2,
            "JavaScript ist **single-threaded** aber **asynchron**.\n\n"
            "```javascript\n// Promise\nfetch('/api/data')\n  .then(res => res.json())\n  .then(data => console.log(data))\n  .catch(err => console.error(err));\n\n// async/await (moderner, lesbarer)\nasync function getData() {\n  try {\n    const res = await fetch('/api/data');\n    const data = await res.json();\n    console.log(data);\n  } catch (err) {\n    console.error(err);\n  }\n}\n```",
            quiz=[
                mc("Was gibt eine async Function zurück?", ["Ein Promise", "Den Rückgabewert direkt", "undefined", "Ein Callback"], 0),
                tf("await kann nur innerhalb einer async Function verwendet werden.", True),
                mc("Was macht .catch() bei einem Promise?", ["Fängt Fehler ab", "Cached das Ergebnis", "Beendet die Chain", "Fängt Events ab"], 0),
            ],
            tags=["async", "promises", "fetch"]),

        unit("js-3-1", "ES6+ Features", 3,
            "Moderne JavaScript-Features:\n\n"
            "**Destructuring:**\n"
            "```javascript\nconst { name, age } = person;\nconst [first, ...rest] = array;\n```\n\n"
            "**Spread/Rest:**\n"
            "```javascript\nconst merged = { ...obj1, ...obj2 };\nconst copy = [...array];\n```\n\n"
            "**Optional Chaining & Nullish Coalescing:**\n"
            "```javascript\nuser?.address?.city  // undefined statt Error\nvalue ?? 'default'   // nur bei null/undefined\n```\n\n"
            "**Template Literals:**\n"
            "```javascript\nconst msg = `Hallo ${name}, du bist ${age} Jahre alt.`;\n```",
            quiz=[
                mc("Was macht der Spread-Operator (...)?", ["Entpackt Arrays/Objekte", "Erstellt ein Array", "Multipliziert Werte", "Definiert Rest-Parameter"], 0),
                mc("Was gibt user?.name zurück wenn user null ist?", ["undefined", "null", "Error", "''"], 0),
                fill("___ gibt den rechten Wert nur bei null/undefined zurück.", ["??", "nullish coalescing"]),
            ],
            tags=["es6", "modern"]),

        unit("js-3-2", "Module & Imports", 3,
            "JavaScript-Module für strukturierten Code:\n\n"
            "```javascript\n// math.js — Named Exports\nexport function add(a, b) { return a + b; }\nexport const PI = 3.14159;\n\n// Default Export\nexport default class Calculator { }\n\n// Importieren\nimport Calculator, { add, PI } from './math.js';\nimport * as math from './math.js';\n```\n\n"
            "In HTML: `<script type=\"module\" src=\"app.js\">`",
            quiz=[
                mc("Wie importiert man einen Default Export?", ["import Name from './file'", "import { Name } from './file'", "import * from './file'", "require('./file')"], 0),
                tf("Ein Modul kann mehrere Named Exports haben.", True),
                tf("type='module' Scripts werden automatisch deferred.", True),
            ],
            tags=["module", "import", "export"]),

        unit("js-4-1", "TypeScript Grundlagen", 4,
            "TypeScript = JavaScript + **statische Typen**.\n\n"
            "```typescript\nlet name: string = 'Anna';\nlet age: number = 28;\nlet active: boolean = true;\n\ninterface User {\n  name: string;\n  email: string;\n  age?: number;  // optional\n}\n\nfunction greet(user: User): string {\n  return `Hallo, ${user.name}!`;\n}\n\n// Generics\nfunction first<T>(arr: T[]): T | undefined {\n  return arr[0];\n}\n```",
            quiz=[
                mc("Was macht TypeScript anders als JavaScript?", ["Fügt statische Typen hinzu", "Ist schneller", "Ist eine andere Sprache", "Braucht kein Kompilieren"], 0),
                tf("TypeScript muss zu JavaScript kompiliert werden.", True),
                mc("Was bedeutet age?: number in einem Interface?", ["age ist optional", "age kann null sein", "age ist eine Frage", "age hat einen Default"], 0),
            ],
            tags=["typescript", "typen"]),

        unit("js-5-1", "Design Patterns & Architektur", 5,
            "Wichtige Patterns in JavaScript:\n\n"
            "**Singleton:** Eine einzige Instanz\n"
            "**Observer:** Event-basierte Kommunikation\n"
            "**Factory:** Objekte erstellen ohne new\n"
            "**Module:** Gekapselter Code\n"
            "**Proxy:** Zugriff auf Objekte abfangen\n\n"
            "Architektur-Patterns:\n"
            "- MVC (Model-View-Controller)\n"
            "- MVVM (Model-View-ViewModel)\n"
            "- Component-Based (React, Vue)\n"
            "- Flux/Redux (Unidirectional Data Flow)",
            quiz=[
                mc("Welches Pattern hat nur eine einzige Instanz?", ["Singleton", "Factory", "Observer", "Proxy"], 0),
                tf("React nutzt Component-Based Architecture.", True),
                mc("Was ist Unidirectional Data Flow?", ["Daten fließen nur in eine Richtung", "Daten werden nur einmal geladen", "Nur ein User gleichzeitig", "Nur GET-Requests"], 0),
            ],
            tags=["patterns", "architektur"]),
    ],
}

# ══════════════════════════════════════════════════════════════════
# TRACK: PYTHON
# ══════════════════════════════════════════════════════════════════
PYTHON_TRACK = {
    "id": "python",
    "name": "Python",
    "icon": "🐍",
    "description": "Python — Einfach, mächtig, überall: Web, AI, Data Science, Scripting",
    "color": "#3776ab",
    "units": [
        unit("py-0-1", "Was ist Python?", 0,
            "Python ist eine **interpretierte, dynamisch typisierte** Programmiersprache.\n\n"
            "- Einfache, lesbare Syntax\n"
            "- Riesiges Ökosystem (Web, AI, Data, Automation)\n"
            "- Einrückung statt Klammern!\n\n"
            "```python\nprint('Hallo Welt!')\nname = input('Wie heißt du? ')\nprint(f'Hallo, {name}!')\n```",
            quiz=[
                tf("Python nutzt Einrückung statt geschweifter Klammern.", True),
                mc("Wer hat Python erfunden?", ["Guido van Rossum", "James Gosling", "Brendan Eich", "Dennis Ritchie"], 0),
                mc("Wie gibt man Text aus?", ["print()", "echo()", "console.log()", "write()"], 0),
            ],
            tags=["grundlagen"]),

        unit("py-0-2", "Variablen & Datentypen", 0,
            "Python erkennt Typen **automatisch**:\n\n"
            "```python\nname = 'Anna'        # str\nage = 28             # int\nheight = 1.75        # float\nactive = True        # bool\ncolors = ['rot']     # list\ndata = {'key': 'val'}# dict\n```\n\n"
            "Type Checking: `type(x)`, `isinstance(x, int)`",
            quiz=[
                mc("Welcher Datentyp ist 3.14?", ["float", "int", "str", "decimal"], 0),
                tf("Python erfordert explizite Typangaben bei Variablen.", False),
                fill("Eine Zuordnung von Schlüssel-Wert-Paaren ist ein ___.", ["dict", "dictionary"]),
            ],
            tags=["variablen", "typen"]),

        unit("py-1-1", "Kontrollstrukturen", 1,
            "```python\n# if/elif/else\nif age >= 18:\n    print('Erwachsen')\nelif age >= 13:\n    print('Teenager')\nelse:\n    print('Kind')\n\n# for-Schleife\nfor fruit in ['Apfel', 'Birne']:\n    print(fruit)\n\nfor i in range(5):     # 0, 1, 2, 3, 4\n    print(i)\n\n# while-Schleife\nwhile count > 0:\n    count -= 1\n\n# List Comprehension\nsquares = [x**2 for x in range(10)]\n```",
            quiz=[
                mc("Was gibt range(3) aus?", ["0, 1, 2", "1, 2, 3", "0, 1, 2, 3", "3"], 0),
                code("Erstelle eine List Comprehension die alle geraden Zahlen von 0-20 enthält.", "python", "even = "),
                tf("Python hat kein switch/case Statement.", False, "Seit Python 3.10 gibt es match/case."),
            ],
            tags=["kontrollstrukturen", "schleifen"]),

        unit("py-1-2", "Funktionen & Lambda", 1,
            "```python\ndef greet(name: str, formal: bool = False) -> str:\n    if formal:\n        return f'Guten Tag, {name}.'\n    return f'Hey {name}!'\n\n# Lambda (anonyme Funktion)\ndouble = lambda x: x * 2\n\n# *args und **kwargs\ndef flex(*args, **kwargs):\n    print(args)    # Tuple\n    print(kwargs)  # Dict\n```",
            quiz=[
                mc("Was ist ein Default-Parameter?", ["Ein Parameter mit voreingestelltem Wert", "Der erste Parameter", "Ein Pflicht-Parameter", "Ein globaler Wert"], 0),
                fill("*args sammelt Argumente als ___, **kwargs als ___.", ["tuple", "dict"]),
                code("Schreibe eine Funktion 'is_even' die True zurückgibt wenn die Zahl gerade ist.", "python"),
            ],
            tags=["funktionen", "lambda"]),

        unit("py-2-1", "Klassen & OOP", 2,
            "```python\nclass Animal:\n    def __init__(self, name: str, sound: str):\n        self.name = name\n        self.sound = sound\n\n    def speak(self) -> str:\n        return f'{self.name} macht {self.sound}!'\n\nclass Dog(Animal):\n    def __init__(self, name: str):\n        super().__init__(name, 'Wau')\n\n    def fetch(self, item: str) -> str:\n        return f'{self.name} holt {item}!'\n```",
            quiz=[
                mc("Was macht __init__?", ["Initialisiert eine neue Instanz (Konstruktor)", "Löscht ein Objekt", "Importiert ein Modul", "Erstellt eine Klasse"], 0),
                tf("Python unterstützt Mehrfachvererbung.", True),
                mc("Was bedeutet 'self' in Python-Klassen?", ["Referenz auf die aktuelle Instanz", "Ein Keyword für Singleton", "Der Klassenname", "Ein Dekorator"], 0),
            ],
            tags=["oop", "klassen"]),

        unit("py-2-2", "Dateien & Fehlerbehandlung", 2,
            "```python\n# Dateien lesen/schreiben\nwith open('data.txt', 'r') as f:\n    content = f.read()\n\nwith open('output.txt', 'w') as f:\n    f.write('Hallo!')\n\n# JSON\nimport json\ndata = json.loads('{\"key\": \"value\"}')\njson_str = json.dumps(data, indent=2)\n\n# Fehlerbehandlung\ntry:\n    result = 10 / 0\nexcept ZeroDivisionError as e:\n    print(f'Fehler: {e}')\nfinally:\n    print('Immer ausgeführt')\n```",
            quiz=[
                mc("Was macht 'with' bei Dateien?", ["Schließt die Datei automatisch", "Öffnet im Schreibmodus", "Erstellt die Datei", "Liest binär"], 0),
                tf("finally wird immer ausgeführt, auch bei Fehler.", True),
                mc("Welches Modul verarbeitet JSON in Python?", ["json", "requests", "os", "sys"], 0),
            ],
            tags=["dateien", "json", "exceptions"]),

        unit("py-3-1", "Decorators & Generators", 3,
            "```python\n# Decorator\ndef timer(func):\n    import time\n    def wrapper(*args, **kwargs):\n        start = time.time()\n        result = func(*args, **kwargs)\n        print(f'{func.__name__} took {time.time()-start:.3f}s')\n        return result\n    return wrapper\n\n@timer\ndef slow_function():\n    time.sleep(1)\n\n# Generator\ndef fibonacci():\n    a, b = 0, 1\n    while True:\n        yield a\n        a, b = b, a + b\n\nfib = fibonacci()\nnext(fib)  # 0\nnext(fib)  # 1\n```",
            quiz=[
                mc("Was macht yield in einem Generator?", ["Gibt einen Wert zurück und pausiert die Funktion", "Beendet die Funktion", "Wirft einen Fehler", "Erstellt eine Kopie"], 0),
                tf("Ein Decorator ist eine Funktion die eine andere Funktion nimmt und erweitert.", True),
            ],
            tags=["decorators", "generators", "advanced"]),

        unit("py-4-1", "Async Python & Web Frameworks", 4,
            "```python\nimport asyncio\n\nasync def fetch_data(url: str) -> dict:\n    async with aiohttp.ClientSession() as session:\n        async with session.get(url) as resp:\n            return await resp.json()\n\nasync def main():\n    data = await asyncio.gather(\n        fetch_data('https://api.a.com'),\n        fetch_data('https://api.b.com'),\n    )\n\n# Web Frameworks\n# Flask (einfach)\nfrom flask import Flask\napp = Flask(__name__)\n\n@app.route('/')\ndef home():\n    return 'Hello!'\n\n# FastAPI (modern, async, automatische Docs)\nfrom fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/users/{user_id}')\nasync def get_user(user_id: int):\n    return {'id': user_id}\n```",
            quiz=[
                mc("Welches Python-Framework generiert automatisch API-Dokumentation?", ["FastAPI", "Flask", "Django", "Bottle"], 0),
                tf("asyncio.gather() führt Tasks parallel aus.", True),
            ],
            tags=["async", "web", "flask", "fastapi"]),

        unit("py-5-1", "Packaging, Testing & Best Practices", 5,
            "**Testing:**\n"
            "```python\nimport pytest\n\ndef test_addition():\n    assert add(2, 3) == 5\n\ndef test_error():\n    with pytest.raises(ValueError):\n        parse_int('abc')\n```\n\n"
            "**Packaging:**\n"
            "- `pyproject.toml` — Moderner Standard\n"
            "- `setup.py` — Legacy\n"
            "- `requirements.txt` — Dependencies\n\n"
            "**Type Hints & mypy:**\n"
            "```python\nfrom typing import List, Optional, Dict\n\ndef process(items: List[str], limit: Optional[int] = None) -> Dict[str, int]:\n    ...\n```",
            quiz=[
                mc("Welches Tool prüft Python Type Hints?", ["mypy", "pylint", "black", "pytest"], 0),
                tf("pyproject.toml ist der moderne Standard für Python-Packages.", True),
            ],
            tags=["testing", "packaging", "typing"]),
    ],
}

# ══════════════════════════════════════════════════════════════════
# TRACK: PHP
# ══════════════════════════════════════════════════════════════════
PHP_TRACK = {
    "id": "php",
    "name": "PHP",
    "icon": "🐘",
    "description": "PHP — Serverseitige Webentwicklung, WordPress, Laravel",
    "color": "#777bb4",
    "units": [
        unit("php-0-1", "Was ist PHP?", 0,
            "PHP = **PHP: Hypertext Preprocessor** (rekursives Akronym).\n\n"
            "- Serverseitige Sprache — Code läuft auf dem Server\n"
            "- Erzeugt HTML das an den Browser gesendet wird\n"
            "- Riesiges Ökosystem: WordPress, Laravel, Symfony\n"
            "- ~77% aller Webseiten nutzen PHP\n\n"
            "```php\n<?php\n$name = 'Welt';\necho \"Hallo, $name!\";\n?>\n```",
            quiz=[
                mc("Wo wird PHP-Code ausgeführt?", ["Auf dem Server", "Im Browser", "Auf dem Client", "In der Datenbank"], 0),
                tf("PHP steht für 'Personal Home Page'.", False, "Offiziell: PHP: Hypertext Preprocessor."),
                fill("PHP-Code wird mit ___ geöffnet und ___ geschlossen.", ["<?php", "?>"]),
            ],
            tags=["grundlagen"]),

        unit("php-1-1", "Variablen, Arrays & Strings", 1,
            "```php\n// Variablen beginnen mit $\n$name = 'Anna';\n$age = 28;\n$pi = 3.14;\n$active = true;\n\n// Arrays\n$fruits = ['Apfel', 'Birne', 'Kirsche'];\n$person = ['name' => 'Anna', 'age' => 28]; // Assoziatives Array\n\n// String-Funktionen\nstrlen($name);          // 4\nstrtolower($name);      // 'anna'\nstr_contains($name, 'nn'); // true (PHP 8+)\nsubstr($name, 0, 2);    // 'An'\n\n// String Interpolation (nur mit doppelten Anführungszeichen!)\necho \"Hallo, $name!\";\necho 'Hallo, $name!'; // Gibt wörtlich $name aus!\n```",
            quiz=[
                mc("Womit beginnt jede PHP-Variable?", ["$", "@", "#", "&"], 0),
                tf("Einfache Anführungszeichen interpolieren Variablen.", False),
                mc("Wie erstellt man ein assoziatives Array?", ["['key' => 'value']", "{'key': 'value'}", "['key', 'value']", "new Array('key', 'value')"], 0),
            ],
            tags=["variablen", "arrays", "strings"]),

        unit("php-2-1", "Funktionen & Klassen", 2,
            "```php\n// Funktionen\nfunction greet(string $name, bool $formal = false): string {\n    return $formal ? \"Guten Tag, $name.\" : \"Hey $name!\";\n}\n\n// Klassen (PHP 8+)\nclass User {\n    public function __construct(\n        private string $name,\n        private string $email,\n        private int $age = 0,\n    ) {}\n\n    public function getName(): string {\n        return $this->name;\n    }\n}\n\n$user = new User('Anna', 'anna@example.com', 28);\n```",
            quiz=[
                mc("Wie greift man in PHP auf Objekt-Properties zu?", ["$this->property", "self.property", "$this.property", "this->property"], 0),
                tf("PHP 8 Constructor Promotion vereinfacht Klassen.", True),
                mc("Was ist der Rückgabetyp void?", ["Die Funktion gibt nichts zurück", "Die Funktion gibt null zurück", "Ungültig", "Ein leerer String"], 0),
            ],
            tags=["funktionen", "oop"]),

        unit("php-3-1", "Datenbankanbindung (PDO)", 3,
            "```php\n// PDO — PHP Data Objects (sicher!)\n$pdo = new PDO(\n    'mysql:host=localhost;dbname=mydb;charset=utf8mb4',\n    'username', 'password',\n    [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]\n);\n\n// Prepared Statements (SQL Injection Schutz!)\n$stmt = $pdo->prepare('SELECT * FROM users WHERE email = ?');\n$stmt->execute([$email]);\n$user = $stmt->fetch(PDO::FETCH_ASSOC);\n\n// INSERT\n$stmt = $pdo->prepare('INSERT INTO users (name, email) VALUES (?, ?)');\n$stmt->execute([$name, $email]);\n$id = $pdo->lastInsertId();\n```",
            quiz=[
                mc("Warum nutzt man Prepared Statements?", ["Schutz vor SQL Injection", "Schnellere Abfragen", "Bessere Lesbarkeit", "Automatische Typen"], 0),
                tf("PDO::FETCH_ASSOC gibt ein assoziatives Array zurück.", True),
                mc("Was ist NIEMALS sicher?", ["$pdo->query(\"SELECT * WHERE id=$id\")", "Prepared Statements", "PDO mit Parametern", "Stored Procedures"], 0),
            ],
            tags=["datenbank", "pdo", "sql"]),

        unit("php-4-1", "Modernes PHP (8.x Features)", 4,
            "PHP 8.0+:\n"
            "- **Named Arguments**: `greet(formal: true, name: 'Anna')`\n"
            "- **Match Expression**: `match($status) { 'ok' => 200, 'not_found' => 404 }`\n"
            "- **Nullsafe Operator**: `$user?->getAddress()?->getCity()`\n"
            "- **Union Types**: `function foo(int|string $x)`\n"
            "- **Fibers** (Async): Cooperative Multitasking\n"
            "- **Enums**: `enum Status: string { case Active = 'active'; }`\n"
            "- **Readonly Properties**: `public readonly string $name`",
            quiz=[
                mc("Was macht der Nullsafe Operator (?->)?", ["Gibt null zurück statt Error bei null", "Prüft auf 0", "Konvertiert zu null", "Macht Nullable"], 0),
                tf("PHP 8 hat native Enums.", True),
            ],
            tags=["php8", "modern"]),
    ],
}

# ══════════════════════════════════════════════════════════════════
# TRACK: SQL / DATENBANKEN
# ══════════════════════════════════════════════════════════════════
SQL_TRACK = {
    "id": "sql",
    "name": "SQL & Datenbanken",
    "icon": "🗄️",
    "description": "SQL — Structured Query Language, relationale Datenbanken, MySQL, PostgreSQL",
    "color": "#336791",
    "units": [
        unit("sql-0-1", "Was sind Datenbanken?", 0,
            "Eine **Datenbank** speichert Daten strukturiert und durchsuchbar.\n\n"
            "**Relationale Datenbanken** (SQL):\n"
            "- Daten in Tabellen (Zeilen + Spalten)\n"
            "- Verknüpfungen über Fremdschlüssel\n"
            "- MySQL, PostgreSQL, SQLite, MariaDB\n\n"
            "**NoSQL-Datenbanken**:\n"
            "- Dokumente (MongoDB), Key-Value (Redis), Graphen (Neo4j)\n"
            "- Für unstrukturierte/flexible Daten",
            quiz=[
                mc("Was speichert eine relationale Datenbank?", ["Daten in Tabellen mit Zeilen und Spalten", "Dateien auf der Festplatte", "HTML-Seiten", "Bilder"], 0),
                tf("MySQL und PostgreSQL sind relationale Datenbanken.", True),
                mc("Welche davon ist eine NoSQL-Datenbank?", ["MongoDB", "MySQL", "PostgreSQL", "SQLite"], 0),
            ],
            tags=["grundlagen", "datenbanken"]),

        unit("sql-1-1", "SELECT, WHERE, ORDER BY", 1,
            "```sql\n-- Alle Spalten\nSELECT * FROM users;\n\n-- Bestimmte Spalten\nSELECT name, email FROM users;\n\n-- Filtern\nSELECT * FROM users WHERE age >= 18;\nSELECT * FROM users WHERE name LIKE '%anna%';\nSELECT * FROM users WHERE age BETWEEN 18 AND 30;\nSELECT * FROM users WHERE role IN ('admin', 'editor');\n\n-- Sortieren\nSELECT * FROM users ORDER BY created_at DESC;\n\n-- Begrenzen\nSELECT * FROM users LIMIT 10 OFFSET 20;\n```",
            quiz=[
                mc("Welches Keyword filtert Ergebnisse?", ["WHERE", "FILTER", "HAVING", "SELECT"], 0),
                mc("Was macht ORDER BY ... DESC?", ["Sortiert absteigend", "Sortiert aufsteigend", "Löscht sortiert", "Beschreibt die Sortierung"], 0),
                fill("Um die ersten 5 Ergebnisse zu bekommen nutzt man ___.", ["LIMIT 5"]),
                code("Schreibe eine Query die alle User mit dem Namen 'Anna' findet.", "sql"),
            ],
            tags=["select", "where", "grundlagen"]),

        unit("sql-1-2", "INSERT, UPDATE, DELETE", 1,
            "```sql\n-- Einfügen\nINSERT INTO users (name, email, age)\nVALUES ('Anna', 'anna@test.de', 28);\n\n-- Mehrere Zeilen\nINSERT INTO users (name, email) VALUES\n  ('Ben', 'ben@test.de'),\n  ('Clara', 'clara@test.de');\n\n-- Aktualisieren\nUPDATE users SET age = 29 WHERE name = 'Anna';\n\n-- Löschen (VORSICHT!)\nDELETE FROM users WHERE id = 42;\n\n-- NIEMALS ohne WHERE!\n-- DELETE FROM users;  ← Löscht ALLE Zeilen!\n```",
            quiz=[
                tf("DELETE FROM users ohne WHERE löscht ALLE Zeilen.", True),
                mc("Welches Statement aktualisiert Daten?", ["UPDATE", "MODIFY", "ALTER", "CHANGE"], 0),
                code("Füge einen neuen User 'Max' mit der Email 'max@test.de' ein.", "sql"),
            ],
            tags=["insert", "update", "delete"]),

        unit("sql-2-1", "JOINs", 2,
            "**JOINs** verknüpfen Tabellen:\n\n"
            "```sql\n-- INNER JOIN (nur Übereinstimmungen)\nSELECT u.name, o.total\nFROM users u\nINNER JOIN orders o ON u.id = o.user_id;\n\n-- LEFT JOIN (alle aus linker Tabelle + Matches)\nSELECT u.name, o.total\nFROM users u\nLEFT JOIN orders o ON u.id = o.user_id;\n\n-- RIGHT JOIN (alle aus rechter Tabelle)\n-- FULL OUTER JOIN (alle aus beiden)\n```\n\n"
            "Merkhilfe:\n"
            "- INNER = Schnittmenge\n"
            "- LEFT = Alles links + Schnittmenge\n"
            "- RIGHT = Alles rechts + Schnittmenge\n"
            "- FULL OUTER = Alles",
            quiz=[
                mc("Welcher JOIN gibt nur übereinstimmende Zeilen aus beiden Tabellen?", ["INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL OUTER JOIN"], 0),
                tf("LEFT JOIN gibt alle Zeilen der linken Tabelle, auch ohne Match.", True),
                mc("Was passiert bei LEFT JOIN wenn kein Match existiert?", ["Die rechten Spalten sind NULL", "Die Zeile wird übersprungen", "Ein Fehler tritt auf", "Die Zeile wird dupliziert"], 0),
            ],
            tags=["joins", "verknüpfungen"]),

        unit("sql-2-2", "GROUP BY, HAVING & Aggregatfunktionen", 2,
            "```sql\n-- Aggregatfunktionen\nSELECT COUNT(*) FROM users;                    -- Anzahl\nSELECT AVG(age) FROM users;                    -- Durchschnitt\nSELECT SUM(total) FROM orders;                 -- Summe\nSELECT MAX(age), MIN(age) FROM users;          -- Max/Min\n\n-- GROUP BY\nSELECT role, COUNT(*) as count\nFROM users\nGROUP BY role;\n\n-- HAVING (Filtern NACH Gruppierung)\nSELECT role, COUNT(*) as count\nFROM users\nGROUP BY role\nHAVING count > 5;\n```",
            quiz=[
                mc("Was ist der Unterschied zwischen WHERE und HAVING?", ["WHERE filtert VOR, HAVING NACH Gruppierung", "Kein Unterschied", "HAVING ist schneller", "WHERE funktioniert nur mit Zahlen"], 0),
                fill("Die Funktion ___ zählt die Anzahl der Zeilen.", ["COUNT"]),
            ],
            tags=["aggregation", "group-by"]),

        unit("sql-3-1", "Indexe, Views & Stored Procedures", 3,
            "**Indexe** — Beschleunigen Abfragen:\n"
            "```sql\nCREATE INDEX idx_email ON users(email);\nCREATE UNIQUE INDEX idx_email ON users(email);\n-- Composite Index\nCREATE INDEX idx_name_age ON users(name, age);\n```\n\n"
            "**Views** — Gespeicherte Abfragen:\n"
            "```sql\nCREATE VIEW active_users AS\nSELECT * FROM users WHERE active = 1;\n-- Nutzen wie eine Tabelle:\nSELECT * FROM active_users;\n```\n\n"
            "**Stored Procedures:**\n"
            "```sql\nDELIMITER //\nCREATE PROCEDURE get_user(IN user_id INT)\nBEGIN\n  SELECT * FROM users WHERE id = user_id;\nEND //\nDELIMITER ;\n```",
            quiz=[
                mc("Was beschleunigt ein Index?", ["SELECT-Abfragen auf die indizierten Spalten", "INSERT-Operationen", "DELETE-Operationen", "Die gesamte Datenbank"], 0),
                tf("Ein Index verlangsamt INSERT/UPDATE Operationen leicht.", True),
            ],
            tags=["indexe", "views", "performance"]),

        unit("sql-4-1", "Transaktionen & ACID", 4,
            "**ACID** — Eigenschaften von Transaktionen:\n\n"
            "- **A**tomicity — Alles oder nichts\n"
            "- **C**onsistency — Datenbank bleibt konsistent\n"
            "- **I**solation — Transaktionen stören sich nicht\n"
            "- **D**urability — Gespeichert bleibt gespeichert\n\n"
            "```sql\nBEGIN TRANSACTION;\n\nUPDATE accounts SET balance = balance - 100 WHERE id = 1;\nUPDATE accounts SET balance = balance + 100 WHERE id = 2;\n\n-- Alles OK?\nCOMMIT;\n-- Oder: Problem?\nROLLBACK;\n```",
            quiz=[
                mc("Wofür steht das A in ACID?", ["Atomicity", "Authentication", "Authorization", "Availability"], 0),
                tf("ROLLBACK macht alle Änderungen einer Transaktion rückgängig.", True),
            ],
            tags=["transaktionen", "acid"]),
    ],
}

# ══════════════════════════════════════════════════════════════════
# TRACK: RUST
# ══════════════════════════════════════════════════════════════════
RUST_TRACK = {
    "id": "rust",
    "name": "Rust",
    "icon": "🦀",
    "description": "Rust — Sicher, schnell, systemsnah. Der C++ Killer.",
    "color": "#ce422b",
    "units": [
        unit("rust-0-1", "Was ist Rust?", 0,
            "Rust ist eine **systemnahe Programmiersprache** von Mozilla.\n\n"
            "- **Memory Safety** ohne Garbage Collector\n"
            "- **Ownership System** — Kompiliert nur wenn sicher\n"
            "- Performance wie C/C++\n"
            "- Beliebteste Sprache laut Stack Overflow\n\n"
            "```rust\nfn main() {\n    println!(\"Hallo Welt!\");\n    let name = \"Ailey\";\n    println!(\"Hallo, {}!\", name);\n}\n```",
            quiz=[
                mc("Was macht Rust besonders im Vergleich zu C++?", ["Memory Safety ohne Garbage Collector", "Ist schneller als C", "Hat eine VM", "Ist interpretiert"], 0),
                tf("Rust hat einen Garbage Collector.", False, "Rust nutzt das Ownership-System statt GC."),
                mc("Welches Makro gibt Text aus?", ["println!()", "print()", "console.log()", "echo()"], 0),
            ],
            tags=["grundlagen"]),

        unit("rust-1-1", "Ownership & Borrowing", 1,
            "**Ownership** — Rusts Kern-Konzept:\n\n"
            "Regeln:\n"
            "1. Jeder Wert hat genau EINEN Owner\n"
            "2. Wenn der Owner out of scope geht, wird der Wert freigegeben\n"
            "3. Werte können MOVED oder BORROWED werden\n\n"
            "```rust\nlet s1 = String::from(\"hello\");\nlet s2 = s1;      // MOVE — s1 ist jetzt ungültig!\n// println!(\"{}\", s1);  // ← Kompilier-Fehler!\n\n// Borrowing (Referenzen)\nlet s3 = String::from(\"hello\");\nlet len = calculate_length(&s3); // Borrow — s3 bleibt gültig\n\nfn calculate_length(s: &String) -> usize {\n    s.len()\n}\n```",
            quiz=[
                mc("Was passiert bei 'let s2 = s1;' mit einem String?", ["s1 wird moved und ist danach ungültig", "s1 wird kopiert", "Beide zeigen auf denselben Speicher", "Kompilier-Fehler"], 0),
                tf("& erstellt eine Referenz (Borrow) ohne Ownership zu übernehmen.", True),
                mc("Wie viele mutable Referenzen darf es gleichzeitig geben?", ["Eine", "Zwei", "Beliebig viele", "Keine"], 0),
            ],
            tags=["ownership", "borrowing", "kern"]),

        unit("rust-2-1", "Structs, Enums & Pattern Matching", 2,
            "```rust\n// Struct\nstruct User {\n    name: String,\n    email: String,\n    age: u32,\n}\n\nimpl User {\n    fn new(name: &str, email: &str) -> Self {\n        User { name: name.to_string(), email: email.to_string(), age: 0 }\n    }\n    fn greet(&self) -> String {\n        format!(\"Hallo, ich bin {}!\", self.name)\n    }\n}\n\n// Enum\nenum Shape {\n    Circle(f64),\n    Rectangle(f64, f64),\n}\n\nfn area(shape: &Shape) -> f64 {\n    match shape {\n        Shape::Circle(r) => std::f64::consts::PI * r * r,\n        Shape::Rectangle(w, h) => w * h,\n    }\n}\n```",
            quiz=[
                mc("Was ist der Unterschied zwischen struct und enum in Rust?", ["struct = Datenfelder, enum = Varianten", "Kein Unterschied", "struct ist schneller", "enum kann keine Daten halten"], 0),
                tf("match in Rust muss exhaustive sein (alle Varianten abdecken).", True),
            ],
            tags=["structs", "enums", "pattern-matching"]),

        unit("rust-3-1", "Error Handling: Result & Option", 3,
            "```rust\n// Option — Wert existiert vielleicht nicht\nfn find_user(id: u32) -> Option<User> {\n    if id == 1 { Some(user) } else { None }\n}\n\n// Result — Operation kann fehlschlagen\nfn parse_number(s: &str) -> Result<i32, String> {\n    s.parse::<i32>().map_err(|e| e.to_string())\n}\n\n// ? Operator — Error Propagation\nfn read_file(path: &str) -> Result<String, std::io::Error> {\n    let content = std::fs::read_to_string(path)?;\n    Ok(content)\n}\n```",
            quiz=[
                mc("Was macht der ? Operator?", ["Gibt den Error weiter an die aufrufende Funktion", "Wandelt zu Option um", "Ignoriert den Error", "Panict bei Error"], 0),
                tf("Option<T> hat die Varianten Some(T) und None.", True),
            ],
            tags=["error-handling", "result", "option"]),

        unit("rust-4-1", "Traits, Generics & Lifetimes", 4,
            "```rust\n// Trait (wie Interface)\ntrait Summary {\n    fn summarize(&self) -> String;\n}\n\nimpl Summary for User {\n    fn summarize(&self) -> String {\n        format!(\"{} ({})\", self.name, self.email)\n    }\n}\n\n// Generics\nfn largest<T: PartialOrd>(list: &[T]) -> &T {\n    let mut largest = &list[0];\n    for item in &list[1..] {\n        if item > largest { largest = item; }\n    }\n    largest\n}\n\n// Lifetimes\nfn longest<'a>(x: &'a str, y: &'a str) -> &'a str {\n    if x.len() > y.len() { x } else { y }\n}\n```",
            quiz=[
                mc("Was sind Traits in Rust vergleichbar mit?", ["Interfaces in Java/TypeScript", "Klassen", "Structs", "Makros"], 0),
                tf("Lifetimes verhindern dangling references zur Compile-Zeit.", True),
            ],
            tags=["traits", "generics", "lifetimes"]),
    ],
}

# ══════════════════════════════════════════════════════════════════
# TRACK: JSON & XML
# ══════════════════════════════════════════════════════════════════
JSON_XML_TRACK = {
    "id": "json_xml",
    "name": "JSON & XML",
    "icon": "📋",
    "description": "Datenformate für APIs, Konfiguration und Datenaustausch",
    "color": "#f5a623",
    "units": [
        unit("jx-0-1", "Was ist JSON?", 0,
            "**JSON** = JavaScript Object Notation\n\n"
            "- Leichtes Datenformat für Datenaustausch\n"
            "- Menschenlesbar UND maschinenlesbar\n"
            "- Standard für Web-APIs\n\n"
            "```json\n{\n  \"name\": \"Anna\",\n  \"age\": 28,\n  \"active\": true,\n  \"hobbies\": [\"Coding\", \"Musik\"],\n  \"address\": {\n    \"city\": \"Berlin\",\n    \"zip\": \"10115\"\n  }\n}\n```\n\n"
            "Regeln: Keys MÜSSEN Strings sein, Werte: string, number, boolean, null, array, object.",
            quiz=[
                mc("Wofür steht JSON?", ["JavaScript Object Notation", "Java Serialized Object Notation", "Just Simple Object Naming", "JavaScript Online Network"], 0),
                tf("JSON-Keys müssen in doppelten Anführungszeichen stehen.", True),
                mc("Welcher Wert ist in JSON NICHT erlaubt?", ["undefined", "null", "true", "\"text\""], 0),
                tf("Kommentare sind in JSON erlaubt.", False, "Standard-JSON erlaubt keine Kommentare."),
            ],
            tags=["json", "grundlagen"]),

        unit("jx-0-2", "Was ist XML?", 0,
            "**XML** = eXtensible Markup Language\n\n"
            "- Beschreibt Daten mit selbstdefinierten Tags\n"
            "- Strenger als HTML\n"
            "- Nutzt in: SOAP, RSS, SVG, Config-Dateien\n\n"
            "```xml\n<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<users>\n  <user id=\"1\">\n    <name>Anna</name>\n    <age>28</age>\n    <active>true</active>\n  </user>\n</users>\n```\n\n"
            "Regeln: Tags MÜSSEN geschlossen werden, case-sensitive, ein Root-Element.",
            quiz=[
                mc("Was bedeutet 'extensible' in XML?", ["Man definiert eigene Tags", "Es ist erweiterbar per Plugin", "Es ist besonders groß", "Es ist Open Source"], 0),
                tf("XML Tags sind case-sensitive.", True),
                mc("Wie viele Root-Elemente hat ein XML-Dokument?", ["Genau 1", "Beliebig viele", "Mindestens 2", "0"], 0),
            ],
            tags=["xml", "grundlagen"]),

        unit("jx-1-1", "JSON vs XML in der Praxis", 1,
            "**JSON Vorteile:**\n"
            "- Kompakter (weniger Text)\n"
            "- Schneller zu parsen\n"
            "- Native in JavaScript\n"
            "- Standard für REST APIs\n\n"
            "**XML Vorteile:**\n"
            "- Schema-Validierung (XSD)\n"
            "- Namespaces\n"
            "- XSLT-Transformation\n"
            "- Besser für Dokumente mit gemischtem Content\n\n"
            "In der Praxis: **JSON für APIs, XML für Enterprise/Legacy-Systeme.**",
            quiz=[
                mc("Welches Format ist kompakter?", ["JSON", "XML", "Gleich", "Kommt drauf an"], 0),
                tf("REST APIs nutzen meistens JSON.", True),
                mc("Welches Format hat native Schema-Validierung?", ["XML (XSD)", "JSON", "Beide", "Keins"], 0),
            ],
            tags=["vergleich", "praxis"]),

        unit("jx-2-1", "JSON Schema & Validierung", 2,
            "**JSON Schema** validiert JSON-Daten:\n\n"
            "```json\n{\n  \"$schema\": \"https://json-schema.org/draft/2020-12/schema\",\n  \"type\": \"object\",\n  \"properties\": {\n    \"name\": { \"type\": \"string\", \"minLength\": 1 },\n    \"age\": { \"type\": \"integer\", \"minimum\": 0 },\n    \"email\": { \"type\": \"string\", \"format\": \"email\" }\n  },\n  \"required\": [\"name\", \"email\"]\n}\n```\n\n"
            "Tools: ajv (JS), jsonschema (Python), JSON Schema Validator (online)",
            quiz=[
                mc("Was definiert ein JSON Schema?", ["Die Struktur und Regeln für gültiges JSON", "Den Inhalt einer Datenbank", "CSS-Styles", "API-Routen"], 0),
                tf("required definiert welche Properties Pflicht sind.", True),
            ],
            tags=["schema", "validierung"]),
    ],
}

# ══════════════════════════════════════════════════════════════════
# TRACK: IHK MEDIENGESTALTER DIGITAL & PRINT
# ══════════════════════════════════════════════════════════════════
IHK_TRACK = {
    "id": "ihk_mediengestalter",
    "name": "IHK Mediengestalter Digital & Print",
    "icon": "📐",
    "description": "Prüfungsvorbereitung — Alle Lernfelder für die IHK-Abschlussprüfung",
    "color": "#1a73e8",
    "units": [
        # ── Lernfeld 1: Betriebe & Arbeitsabläufe ──
        unit("ihk-1-1", "Betriebliche Strukturen & Arbeitsabläufe", 1,
            "**Betriebsformen in der Medienbranche:**\n\n"
            "- Werbeagentur (Full-Service, Kreativ, Digital)\n"
            "- Druckerei (Offset, Digital, Siebdruck)\n"
            "- Verlag (Print, Online, Hybrid)\n"
            "- Mediendienstleister (Prepress, Postpress)\n\n"
            "**Arbeitsorganisation:**\n"
            "- Auftragsbearbeitung: Briefing → Konzept → Entwurf → Reinzeichnung → Produktion\n"
            "- Qualitätsmanagement (ISO 9001)\n"
            "- Projektmanagement: Gantt-Diagramm, Meilensteine, Kritischer Pfad",
            quiz=[
                mc("Was kommt in der Auftragsbearbeitung zuerst?", ["Briefing", "Reinzeichnung", "Produktion", "Konzept"], 0),
                tf("ISO 9001 ist ein Standard für Qualitätsmanagement.", True),
                mc("Was zeigt ein Gantt-Diagramm?", ["Zeitplan mit Aufgaben und Dauer", "Organigramm", "Kostenübersicht", "Farbschema"], 0),
            ],
            tags=["betrieb", "organisation"]),

        # ── Lernfeld 2: Medienprodukte konzipieren ──
        unit("ihk-1-2", "Medienprodukte konzipieren & gestalten", 1,
            "**Gestaltungsgrundlagen:**\n\n"
            "**Typografie:**\n"
            "- Serifen vs. Sans-Serif vs. Monospace\n"
            "- Schriftschnitte: Regular, Bold, Italic, Light\n"
            "- Schriftgröße, Zeilenabstand (120-140%), Laufweite\n"
            "- Lesbarkeit: Min. 9pt Print, 16px Screen\n\n"
            "**Farbenlehre:**\n"
            "- Additive Mischung: RGB (Licht → Bildschirm)\n"
            "- Subtraktive Mischung: CMYK (Druckfarben)\n"
            "- Farbkreis nach Itten: Komplementärfarben, Triade\n"
            "- Sonderfarben: Pantone, HKS\n\n"
            "**Komposition:**\n"
            "- Goldener Schnitt (1:1,618)\n"
            "- Drittel-Regel\n"
            "- Weißraum / Negativraum\n"
            "- Visuelle Hierarchie",
            quiz=[
                mc("Welches Farbmodell wird für den Druck verwendet?", ["CMYK", "RGB", "HSL", "Pantone"], 0, "CMYK = Cyan, Magenta, Yellow, Key (Schwarz)"),
                mc("Was ist der Goldene Schnitt?", ["Verhältnis 1:1,618", "Verhältnis 1:2", "Verhältnis 3:5", "Verhältnis 1:1"], 0),
                tf("Serifen-Schriften haben kleine Striche an den Buchstabenenden.", True),
                mc("Was ist der empfohlene Zeilenabstand für Fließtext?", ["120-140% der Schriftgröße", "100%", "200%", "50%"], 0),
                match("Ordne Farbmodell und Verwendung zu:", [
                    ["RGB", "Bildschirm"],
                    ["CMYK", "Druck"],
                    ["Pantone", "Sonderfarben"],
                    ["HSL", "Webdesign"],
                ]),
            ],
            tags=["typografie", "farbenlehre", "gestaltung"]),

        # ── Lernfeld 3: Medienprodukte digital ──
        unit("ihk-2-1", "Digitale Medienproduktion", 2,
            "**Bildbearbeitung:**\n"
            "- Auflösung: 72 dpi (Screen), 300 dpi (Print)\n"
            "- Farbtiefe: 8 Bit (256 Werte pro Kanal), 16 Bit\n"
            "- Formate: JPEG (Foto, verlustbehaftet), PNG (Transparenz, verlustfrei), "
            "TIFF (Print), WebP (Web), SVG (Vektor)\n\n"
            "**Dateiformate Print:**\n"
            "- PDF/X-4 — Standard für Druckdaten\n"
            "- Beschnitt: 3mm umlaufend\n"
            "- Überdrucken vs. Aussparen\n"
            "- ICC-Farbprofile: ISO Coated v2 (gestrichenes Papier)\n\n"
            "**Reinzeichnung:**\n"
            "- Alle Schriften eingebettet oder in Pfade\n"
            "- Bilder in CMYK, mind. 300 dpi\n"
            "- Beschnitt und Passermarken\n"
            "- Preflight-Check",
            quiz=[
                mc("Welche Auflösung ist Standard für Printprodukte?", ["300 dpi", "72 dpi", "150 dpi", "96 dpi"], 0),
                mc("Welches Bildformat unterstützt Transparenz?", ["PNG", "JPEG", "BMP", "TIFF"], 0, "JPEG hat keine Transparenz."),
                tf("PDF/X-4 ist der aktuelle Standard für Druckdaten.", True),
                mc("Wie viel Beschnitt ist Standard?", ["3mm", "5mm", "1mm", "10mm"], 0),
                fill("Für gestrichenes Papier nutzt man das ICC-Profil ___.", ["ISO Coated v2"]),
            ],
            tags=["bildbearbeitung", "print", "dateiformate"]),

        # ── Lernfeld 4: Webdesign & UX ──
        unit("ihk-2-2", "Webdesign & User Experience", 2,
            "**UX Design Prozess:**\n"
            "1. Research (User Interviews, Personas)\n"
            "2. Wireframes (Grobe Struktur)\n"
            "3. Mockups (Detailliertes Design)\n"
            "4. Prototyp (Interaktiv, klickbar)\n"
            "5. Usability Testing\n\n"
            "**Responsive Design:**\n"
            "- Mobile First\n"
            "- Breakpoints: 576px, 768px, 992px, 1200px\n"
            "- Fluid Grids, Flexible Images\n\n"
            "**Accessibility (WCAG 2.1):**\n"
            "- Kontrastverhältnis: mind. 4.5:1 (AA), 7:1 (AAA)\n"
            "- Keyboard-Navigation\n"
            "- Screenreader-Kompatibilität\n"
            "- Alt-Texte für Bilder\n\n"
            "**SEO Grundlagen:**\n"
            "- Title Tags, Meta Description\n"
            "- Semantic HTML\n"
            "- Core Web Vitals: LCP, FID, CLS",
            quiz=[
                mc("Was ist der erste Schritt im UX Design?", ["Research / User Interviews", "Mockup", "Coding", "Wireframe"], 0),
                mc("Was ist das Mindest-Kontrastverhältnis für WCAG AA?", ["4.5:1", "3:1", "7:1", "2:1"], 0),
                tf("Mobile First bedeutet: Zuerst für Mobile designen.", True),
                mc("Was misst LCP (Largest Contentful Paint)?", ["Ladezeit des größten sichtbaren Elements", "Anzahl der Bilder", "Datenbankgeschwindigkeit", "CSS-Rendering"], 0),
            ],
            tags=["ux", "webdesign", "accessibility", "seo"]),

        # ── Lernfeld 5: Drucktechnik ──
        unit("ihk-3-1", "Druckverfahren & Weiterverarbeitung", 3,
            "**Druckverfahren:**\n\n"
            "1. **Offsetdruck** — Indirektes Flachdruckverfahren\n"
            "   - Druckplatte → Gummituch → Papier\n"
            "   - Für mittlere bis hohe Auflagen\n"
            "   - Sehr hohe Qualität\n\n"
            "2. **Digitaldruck** — Direkt auf Bedruckstoff\n"
            "   - Keine Druckplatten nötig\n"
            "   - Für kleine Auflagen, Personalisierung\n"
            "   - Laser oder Inkjet\n\n"
            "3. **Siebdruck** — Farbe wird durch Schablone gedrückt\n"
            "   - Für Textilien, Werbemittel\n"
            "   - Deckkräftige Farben\n\n"
            "4. **Flexodruck** — Hochdruck mit flexiblen Platten\n"
            "   - Für Verpackungen\n\n"
            "**Weiterverarbeitung:**\n"
            "- Falzen (Wickel-, Zickzack-, Kreuzbruch)\n"
            "- Rillen, Nuten, Stanzen\n"
            "- Klebebindung, Fadenheftung, Ringbindung\n"
            "- Lackierung (Dispersion, UV), Folienkaschierung, Prägung",
            quiz=[
                mc("Was ist Offsetdruck?", ["Indirektes Flachdruckverfahren", "Digitales Druckverfahren", "Hochdruckverfahren", "Tiefdruckverfahren"], 0),
                mc("Welches Druckverfahren eignet sich für kleine Auflagen?", ["Digitaldruck", "Offsetdruck", "Siebdruck", "Flexodruck"], 0),
                tf("Beim Offsetdruck wird die Farbe direkt von der Platte auf das Papier übertragen.", False, "Indirekt: Platte → Gummituch → Papier."),
                mc("Welches Verfahren nutzt man für Verpackungsdruck?", ["Flexodruck", "Offsetdruck", "Siebdruck", "Digitaldruck"], 0),
                match("Ordne Bindungsarten zu:", [
                    ["Klebebindung", "Taschenbuch"],
                    ["Fadenheftung", "Hochwertiges Buch"],
                    ["Ringbindung", "Kalender/Notizbuch"],
                    ["Rückstichheftung", "Broschüre"],
                ]),
            ],
            tags=["druck", "weiterverarbeitung"]),

        # ── Lernfeld 6: Projektmanagement & Kalkulation ──
        unit("ihk-3-2", "Projektmanagement & Kalkulation", 3,
            "**Kalkulation:**\n"
            "- Stundensatzkalkulation\n"
            "- Materialkosten (Papier, Druckplatten, Farbe)\n"
            "- Maschinenkosten (Stundensatz × Laufzeit)\n"
            "- Zuschläge: Gemeinkosten, Gewinn, Skonto\n\n"
            "**Formel:**\n"
            "Netto-Angebotspreis = (Material + Fertigung + Gemeinkosten) × (1 + Gewinn%) × (1 + Skonto%)\n\n"
            "**Nutzenverhältnis:**\n"
            "- Nutzen = Wie oft passt das Produkt auf den Druckbogen?\n"
            "- Beispiel: A4-Flyer auf 70×100cm Bogen → 16 Nutzen\n\n"
            "**Auflagenberechnung:**\n"
            "- Zuschuss für Einrichten (Makulatur)\n"
            "- Netto-Auflage + Zuschuss = Brutto-Auflage",
            quiz=[
                mc("Was ist ein 'Nutzen' im Druck?", ["Wie oft ein Produkt auf den Bogen passt", "Der Gewinn eines Auftrags", "Die Druckqualität", "Der Papiertyp"], 0),
                tf("Makulatur sind die Bögen die beim Einrichten verbraucht werden.", True),
                mc("Was gehört NICHT in die Angebotskalkulation?", ["Privatausgaben", "Materialkosten", "Maschinenkosten", "Gewinnzuschlag"], 0),
            ],
            tags=["kalkulation", "projektmanagement"]),

        # ── Lernfeld 7: Medienrecht ──
        unit("ihk-4-1", "Medienrecht & Datenschutz", 4,
            "**Urheberrecht:**\n"
            "- Werke sind ab Schöpfung geschützt (keine Registrierung nötig)\n"
            "- Schutzfrist: 70 Jahre nach Tod des Urhebers\n"
            "- Nutzungsrechte: Einfach vs. Ausschließlich\n"
            "- Creative Commons (CC): BY, SA, NC, ND\n\n"
            "**Markenrecht:**\n"
            "- Wortmarke, Bildmarke, Wort-/Bildmarke\n"
            "- Registrierung beim DPMA\n"
            "- Schutzfrist: 10 Jahre (verlängerbar)\n\n"
            "**Datenschutz (DSGVO):**\n"
            "- Verbot mit Erlaubnisvorbehalt\n"
            "- Einwilligung, Vertragserfüllung, Berechtigtes Interesse\n"
            "- Impressumspflicht (TMG §5)\n"
            "- Datenschutzerklärung (DSGVO Art. 13/14)\n"
            "- Auskunftsrecht (Art. 15), Löschrecht (Art. 17)",
            quiz=[
                mc("Wie lange ist ein Werk nach dem Tod des Urhebers geschützt?", ["70 Jahre", "50 Jahre", "100 Jahre", "25 Jahre"], 0),
                tf("Das Urheberrecht muss in Deutschland registriert werden.", False, "Schutz entsteht automatisch."),
                mc("Was bedeutet CC BY-NC-SA?", ["Namensnennung, Nicht-Kommerziell, Weitergabe unter gleichen Bedingungen", "Copyright, Business, Non-Commercial, Shared Access", "Creative Commons Basic Node Service Agreement", "Copyright By National Creative Standards Association"], 0),
                mc("Was regelt DSGVO Art. 17?", ["Recht auf Löschung", "Impressumspflicht", "Datensicherheit", "Cookie-Einwilligung"], 0),
            ],
            tags=["urheberrecht", "markenrecht", "dsgvo"]),

        # ── Lernfeld 8: Prüfungsvorbereitung ──
        unit("ihk-4-2", "Prüfungssimulation: Konzeption & Gestaltung", 4,
            "**IHK Abschlussprüfung — Teil 1 (Zwischenprüfung):**\n"
            "- 120 Minuten\n"
            "- Gestaltung und Technik\n"
            "- Praxisaufgaben (Layout erstellen, Reinzeichnung)\n\n"
            "**IHK Abschlussprüfung — Teil 2:**\n"
            "- Konzeption und Gestaltung (schriftlich, 180 Min)\n"
            "- Medienproduktion (schriftlich, 60 Min)\n"
            "- Kommunikation (schriftlich, 60 Min)\n"
            "- Projektarbeit (praktisch + Präsentation)\n\n"
            "**Prüfungsthemen:**\n"
            "- Medienproduktionsablauf\n"
            "- Typografie und Gestaltung\n"
            "- Farbmanagement\n"
            "- Bildbearbeitung\n"
            "- Druckvorstufe\n"
            "- Medienrecht\n"
            "- Kalkulation\n"
            "- HTML/CSS/JavaScript\n"
            "- Datenbanken (SQL)\n"
            "- Netzwerktechnik Grundlagen",
            quiz=[
                mc("Wie lange dauert die Prüfung 'Konzeption und Gestaltung'?", ["180 Minuten", "120 Minuten", "60 Minuten", "240 Minuten"], 0),
                tf("Die IHK-Prüfung hat einen praktischen Teil (Projektarbeit).", True),
                mc("Welches Thema gehört NICHT zur IHK-Prüfung?", ["Machine Learning", "Typografie", "Farbmanagement", "SQL"], 0),
            ],
            tags=["prüfung", "ihk", "vorbereitung"]),

        unit("ihk-5-1", "Prüfungssimulation: Kompletttest", 5,
            "**Simulierter Prüfungsteil — 30 Fragen gemischt:**\n\n"
            "Dieser Test deckt ALLE Prüfungsbereiche ab:\n"
            "- Gestaltungsgrundlagen\n"
            "- Typografie\n"
            "- Farbmanagement\n"
            "- Digitale Medienproduktion\n"
            "- Drucktechnik\n"
            "- Medienrecht\n"
            "- Kalkulation\n"
            "- Webtechnik\n\n"
            "⏱️ Empfohlene Zeit: 60 Minuten\n"
            "📊 Bestanden ab 50% (wie IHK)",
            quiz=[
                # Gestaltung
                mc("Was ist der Unterschied zwischen Grotesk und Antiqua?", ["Grotesk = ohne Serifen, Antiqua = mit Serifen", "Grotesk = dekorativ, Antiqua = schlicht", "Kein Unterschied", "Grotesk = nur Großbuchstaben"], 0),
                mc("Welche Schriftklassifikation nach DIN 16518 umfasst Helvetica?", ["Serifenlose Linear-Antiqua", "Klassizistische Antiqua", "Egyptienne", "Barock-Antiqua"], 0),
                # Farbmanagement
                mc("Was ist ein Farbprofil?", ["Eine mathematische Beschreibung eines Farbraums", "Eine Sammlung von Farben", "Ein Drucktest", "Eine Pantone-Tabelle"], 0),
                mc("Was passiert beim Umwandeln von RGB nach CMYK?", ["Der Farbraum wird kleiner (Out-of-Gamut)", "Die Farben werden heller", "Nichts ändert sich", "Die Datei wird größer"], 0),
                # Bildbearbeitung
                mc("Was ist der Unterschied zwischen Pixel- und Vektorgrafik?", ["Pixel = Raster, Vektor = mathematisch", "Pixel = klein, Vektor = groß", "Kein Unterschied", "Pixel = 3D, Vektor = 2D"], 0),
                tf("Eine Vektorgrafik kann verlustfrei skaliert werden.", True),
                # Druck
                mc("Was ist Überdrucken?", ["Farbe wird über eine andere gedruckt statt ausgespart", "Zu viel Farbe auftragen", "Doppelter Druck", "Fehlerhafte Belichtung"], 0),
                mc("Was ist ein Proof?", ["Farbverbindlicher Kontrollausdruck", "Ein Testdruck auf normalem Papier", "Eine PDF-Datei", "Ein Druckplattentest"], 0),
                # Kalkulation
                mc("Wie berechnet man den Netto-Angebotspreis?", ["(Material + Fertigung + Gemeinkosten) + Gewinn + Skonto", "Material × Auflagenhöhe", "Stundensatz × Stunden", "Fixkosten + Variable Kosten"], 0),
                # Medienrecht
                tf("Ein Logo ist automatisch urheberrechtlich geschützt wenn es Schöpfungshöhe erreicht.", True),
                mc("Was braucht eine Website laut TMG?", ["Impressum", "AGB", "Newsletter", "Gästebuch"], 0),
                # Web
                mc("Welches Protokoll nutzt HTTPS?", ["TLS/SSL", "FTP", "SSH", "SMTP"], 0),
                tf("Cookies brauchen laut DSGVO/ePrivacy eine Einwilligung (außer technisch notwendige).", True),
                # Netzwerk
                mc("Was macht DNS?", ["Übersetzt Domain-Namen in IP-Adressen", "Verschlüsselt Daten", "Komprimiert Webseiten", "Speichert Cookies"], 0),
                tf("IPv6-Adressen sind länger als IPv4-Adressen.", True),
            ],
            tags=["prüfung", "simulation", "komplett"]),
    ],
}

# ── Merge echte IHK-Prüfungsthemen 2026 (8 Units × 20 Fragen) ──
try:
    from .ihk_pruefung_2026 import IHK_PRUEFUNG_2026_UNITS
    for pu in IHK_PRUEFUNG_2026_UNITS:
        u = unit(pu["id"], pu["title"], pu["level"],
                 pu["theory"], quiz=pu["quiz"],
                 tags=pu.get("tags", []))
        u["exam_area"] = pu.get("exam_area", "")
        u["fachrichtung"] = pu.get("fachrichtung", "alle")
        IHK_TRACK["units"].append(u)
except ImportError:
    pass  # Module not yet available — degrade gracefully

# ── Merge erweiterte IHK-Prüfungsthemen 2026 (24 Units × 20 Fragen) ──
try:
    from .ihk_pruefung_2026_extended import IHK_PRUEFUNG_2026_EXTENDED_UNITS
    for pu in IHK_PRUEFUNG_2026_EXTENDED_UNITS:
        u = unit(pu["id"], pu["title"], pu["level"],
                 pu["theory"], quiz=pu["quiz"],
                 tags=pu.get("tags", []))
        u["exam_area"] = pu.get("exam_area", "")
        u["fachrichtung"] = pu.get("fachrichtung", "alle")
        IHK_TRACK["units"].append(u)
except ImportError:
    pass  # Module not yet available — degrade gracefully


# ══════════════════════════════════════════════════════════════════
# ALL TRACKS
# ══════════════════════════════════════════════════════════════════
TRACKS = {
    "html": HTML_TRACK,
    "css": CSS_TRACK,
    "javascript": JS_TRACK,
    "python": PYTHON_TRACK,
    "php": PHP_TRACK,
    "sql": SQL_TRACK,
    "rust": RUST_TRACK,
    "json_xml": JSON_XML_TRACK,
    "ihk_mediengestalter": IHK_TRACK,
}

def get_track(track_id: str) -> Optional[Dict]:
    return TRACKS.get(track_id)

def get_unit(track_id: str, unit_id: str) -> Optional[Dict]:
    track = TRACKS.get(track_id)
    if not track:
        return None
    for u in track["units"]:
        if u["id"] == unit_id:
            return u
    return None

def get_track_summary() -> List[Dict]:
    """Get a summary of all available tracks with unit counts per level."""
    result = []
    for tid, track in TRACKS.items():
        levels = {}
        for u in track["units"]:
            lvl = u["level"]
            levels[lvl] = levels.get(lvl, 0) + 1
        result.append({
            "id": tid,
            "name": track["name"],
            "icon": track["icon"],
            "description": track["description"],
            "color": track["color"],
            "total_units": len(track["units"]),
            "units_per_level": levels,
            "total_quizzes": sum(len(u["quiz"]) for u in track["units"]),
        })
    return result
