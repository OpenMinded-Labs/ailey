# Ailey Learning — RAG Knowledge Base: Web-Technologien
# Dieses Dokument wird in Aileys RAG-System indexiert und dient als Referenz
# für Fragen zum Thema Webentwicklung (HTML, CSS, JS, PHP, SQL).

## HTML Referenz

### Doctype & Grundstruktur
- `<!DOCTYPE html>` muss immer die erste Zeile sein
- `<html lang="de">` für deutschsprachige Seiten
- `<head>` enthält Meta-Informationen, `<body>` den sichtbaren Inhalt
- Charset: `<meta charset="UTF-8">` immer setzen

### Semantische HTML5-Elemente
| Element | Verwendung |
|---------|-----------|
| `<header>` | Kopfbereich einer Seite/Sektion |
| `<nav>` | Navigation |
| `<main>` | Hauptinhalt (nur 1x pro Seite) |
| `<article>` | Eigenständiger Inhalt |
| `<section>` | Thematischer Abschnitt |
| `<aside>` | Seitenleiste/Nebeninformation |
| `<footer>` | Fußbereich |
| `<figure>` + `<figcaption>` | Bild mit Beschriftung |
| `<details>` + `<summary>` | Aufklappbarer Bereich |

### Formular-Elemente
- `<form action="" method="POST">` — Formular-Container
- `<input type="text|email|password|number|date|checkbox|radio|file|hidden|submit">`
- `<textarea>` — Mehrzeiliger Text
- `<select>` + `<option>` — Dropdown
- `<datalist>` — Autocomplete-Vorschläge
- `<fieldset>` + `<legend>` — Gruppierung
- Wichtig: Jedes Input braucht ein `<label for="id">`
- Validierung: `required`, `pattern`, `min`, `max`, `minlength`, `maxlength`

### Accessibility (Barrierefreiheit)
- ARIA-Rollen: `role="button|navigation|alert|dialog|tab"`
- `aria-label` — Unsichtbare Beschriftung für Screenreader
- `aria-hidden="true"` — Element vor Assistive Technology verstecken
- `aria-live="polite|assertive"` — Dynamische Updates ankündigen
- `tabindex="0"` — Element per Tab erreichbar machen
- Kontrast: Mindestens 4.5:1 (WCAG AA), 7:1 (WCAG AAA)
- Alle Bilder brauchen alt-Text

---

## CSS Referenz

### Box Model
```
┌─────────────────────────────────────┐
│ margin                              │
│  ┌─────────────────────────────┐    │
│  │ border                      │    │
│  │  ┌──────────────────────┐   │    │
│  │  │ padding              │   │    │
│  │  │  ┌───────────────┐   │   │    │
│  │  │  │ content        │   │   │    │
│  │  │  └───────────────┘   │   │    │
│  │  └──────────────────────┘   │    │
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
```
- `box-sizing: border-box` → Padding + Border werden in die Breite gerechnet
- `box-sizing: content-box` → Standard, Padding wird dazu gerechnet

### Flexbox Cheatsheet
Container: `display: flex`
- `flex-direction`: row | row-reverse | column | column-reverse
- `flex-wrap`: nowrap | wrap | wrap-reverse
- `justify-content`: flex-start | flex-end | center | space-between | space-around | space-evenly
- `align-items`: stretch | flex-start | flex-end | center | baseline
- `align-content`: flex-start | flex-end | center | space-between | space-around | stretch
- `gap`: Abstand zwischen Items

Items:
- `flex: grow shrink basis` (z.B. `flex: 1 0 auto`)
- `align-self`: Einzelnes Item ausrichten
- `order`: Reihenfolge ändern

### CSS Grid Cheatsheet
Container: `display: grid`
- `grid-template-columns: 1fr 2fr 1fr` oder `repeat(3, 1fr)` oder `auto-fill, minmax(200px, 1fr)`
- `grid-template-rows: auto 1fr auto`
- `gap: 1rem`
- `grid-template-areas: "header header" "sidebar main" "footer footer"`

Items:
- `grid-column: 1 / 3` — Von Spalte 1 bis 3
- `grid-row: 1 / span 2` — Ab Zeile 1, 2 Zeilen lang
- `grid-area: header` — Benannter Bereich

### Media Queries
```css
/* Mobile First */
.container { padding: 1rem; }

@media (min-width: 576px)  { /* Small */ }
@media (min-width: 768px)  { /* Medium */ }
@media (min-width: 992px)  { /* Large */ }
@media (min-width: 1200px) { /* XL */ }
@media (min-width: 1400px) { /* XXL */ }

/* Dark Mode */
@media (prefers-color-scheme: dark) { }

/* Print */
@media print { }

/* Reduced Motion */
@media (prefers-reduced-motion: reduce) { }
```

### CSS-Einheiten
| Einheit | Beschreibung |
|---------|-------------|
| `px` | Pixel (absolut) |
| `rem` | Relativ zum root font-size |
| `em` | Relativ zum Parent font-size |
| `%` | Prozent des Parent |
| `vw/vh` | 1% der Viewport-Breite/Höhe |
| `dvh` | Dynamic Viewport Height (inkl. Mobile-Toolbar) |
| `ch` | Breite der "0" im aktuellen Font |
| `fr` | Fractional Unit (nur in Grid) |
| `clamp(min, preferred, max)` | Responsive Wert mit Grenzen |

---

## JavaScript Referenz

### Modernes JavaScript (ES6+)
- `let` (veränderbar) / `const` (konstant) statt `var`
- Template Literals: `` `Hallo ${name}` ``
- Destructuring: `const { name, age } = person`
- Spread: `const copy = [...arr]`, `const merged = { ...obj1, ...obj2 }`
- Optional Chaining: `user?.address?.city`
- Nullish Coalescing: `value ?? 'default'`
- Arrow Functions: `const fn = (x) => x * 2`

### Array-Methoden
```javascript
// Transformieren
arr.map(x => x * 2)          // Neues Array mit transformierten Werten
arr.filter(x => x > 5)       // Filtern
arr.reduce((acc, x) => acc + x, 0) // Zusammenfassen
arr.flat(depth)               // Verschachtelung auflösen
arr.flatMap(fn)               // map + flat

// Suchen
arr.find(x => x.id === 5)    // Erstes Element das passt
arr.findIndex(x => x > 5)    // Index
arr.includes(value)           // Enthält?
arr.some(fn)                  // Mindestens eins passt?
arr.every(fn)                 // Alle passen?

// Sortieren
arr.sort((a, b) => a - b)    // Aufsteigend
arr.toSorted((a, b) => a - b) // Neue Kopie (ES2023)
```

### Async/Await & Fetch
```javascript
// Fetch API
const response = await fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
});
const result = await response.json();

// Parallel
const [a, b] = await Promise.all([fetchA(), fetchB()]);

// Error Handling
try {
  const data = await fetchData();
} catch (error) {
  console.error('Fehler:', error.message);
}
```

### DOM API
```javascript
// Selektoren
document.querySelector('.class')       // Erstes Element
document.querySelectorAll('p')         // Alle Elemente (NodeList)
document.getElementById('id')          // Per ID

// Manipulation
el.textContent = 'Text'               // Sicherer als innerHTML
el.innerHTML = '<b>HTML</b>'           // Achtung: XSS-Risiko!
el.setAttribute('data-id', '5')
el.classList.add('active')
el.classList.remove('active')
el.classList.toggle('hidden')
el.style.color = 'red'

// Events
el.addEventListener('click', handler)
el.removeEventListener('click', handler)

// Erstellen
const div = document.createElement('div')
parent.appendChild(div)
parent.removeChild(child)
el.remove()
```

---

## Python Referenz

### Wichtige Built-in Funktionen
- `len()`, `range()`, `enumerate()`, `zip()`, `map()`, `filter()`
- `sorted(iterable, key=..., reverse=True)`
- `isinstance(obj, type)`, `type(obj)`
- `any(iterable)`, `all(iterable)`
- `min()`, `max()`, `sum()`, `abs()`, `round()`
- `str()`, `int()`, `float()`, `bool()`, `list()`, `dict()`, `set()`, `tuple()`

### String-Methoden
```python
s.strip()           # Whitespace entfernen
s.split(',')        # In Liste aufteilen
','.join(list)      # Liste verbinden
s.replace('a', 'b') # Ersetzen
s.startswith('pre')  # Beginnt mit
s.endswith('.py')    # Endet mit
s.upper() / s.lower()
s.find('sub')        # Index oder -1
f"Hallo {name}"     # f-String (formatiert)
```

### Dict-Methoden
```python
d.get('key', default)    # Sicher zugreifen
d.keys() / d.values() / d.items()
d.update(other_dict)
d.setdefault('key', [])
d.pop('key', default)
{k: v for k, v in d.items() if v > 0}  # Dict Comprehension
```

### Decorators
```python
import functools

def my_decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print("Vorher")
        result = func(*args, **kwargs)
        print("Nachher")
        return result
    return wrapper

@my_decorator
def greet(name):
    return f"Hallo {name}"
```

### Type Hints (Python 3.10+)
```python
from typing import Optional, Union

def process(items: list[str], limit: int | None = None) -> dict[str, int]:
    ...

# Generics
def first[T](items: list[T]) -> T | None:
    return items[0] if items else None
```

---

## PHP Referenz

### Superglobals
- `$_GET` — URL-Parameter
- `$_POST` — POST-Daten
- `$_REQUEST` — GET + POST + COOKIE
- `$_SESSION` — Session-Daten
- `$_COOKIE` — Cookies
- `$_SERVER` — Server-Informationen
- `$_FILES` — Hochgeladene Dateien
- `$_ENV` — Umgebungsvariablen

### PHP 8 Features
```php
// Named Arguments
array_slice(array: $arr, offset: 0, length: 5);

// Match Expression
$result = match($status) {
    'active' => 'Aktiv',
    'inactive' => 'Inaktiv',
    default => 'Unbekannt',
};

// Nullsafe Operator
$city = $user?->getAddress()?->getCity();

// Constructor Promotion
class User {
    public function __construct(
        private string $name,
        private string $email,
        public readonly int $age = 0,
    ) {}
}

// Enums
enum Status: string {
    case Active = 'active';
    case Inactive = 'inactive';
}

// Fiber (Async)
$fiber = new Fiber(function() { Fiber::suspend('paused'); });
$fiber->start();  // Returns 'paused'
$fiber->resume();
```

---

## SQL Referenz

### CRUD
```sql
-- Create
INSERT INTO users (name, email) VALUES ('Anna', 'anna@test.de');

-- Read
SELECT name, email FROM users WHERE age >= 18 ORDER BY name LIMIT 10;

-- Update
UPDATE users SET age = 29 WHERE id = 1;

-- Delete
DELETE FROM users WHERE id = 1;
```

### JOINs Übersicht
```
INNER JOIN  → Nur Übereinstimmungen (Schnittmenge)
LEFT JOIN   → Alle links + Übereinstimmungen rechts
RIGHT JOIN  → Alle rechts + Übereinstimmungen links
FULL OUTER  → Alles aus beiden Tabellen
CROSS JOIN  → Kartesisches Produkt (jeder mit jedem)
```

### Index-Typen
- `PRIMARY KEY` — Eindeutig, nicht NULL, einer pro Tabelle
- `UNIQUE INDEX` — Eindeutig, NULL erlaubt
- `INDEX` — Beschleunigt Suche
- `FULLTEXT INDEX` — Volltextsuche
- `COMPOSITE INDEX` — Mehrere Spalten

### Normalisierung
- **1NF**: Jede Zelle enthält nur einen atomaren Wert
- **2NF**: 1NF + alle Nicht-Schlüssel-Spalten hängen vom gesamten Primärschlüssel ab
- **3NF**: 2NF + keine transitiven Abhängigkeiten

---

## Rust Referenz

### Ownership Regeln
1. Jeder Wert hat genau EINEN Owner
2. Es kann nur EINEN Owner gleichzeitig geben
3. Wenn der Owner out of scope geht, wird der Wert gedropt (freigegeben)

### Borrowing Regeln
- Beliebig viele immutable Referenzen `&T` ODER
- Genau EINE mutable Referenz `&mut T`
- Nie beides gleichzeitig!

### Common Traits
```rust
// Display — für println!("{}", x)
impl fmt::Display for MyType { ... }

// Debug — für println!("{:?}", x)
#[derive(Debug)]

// Clone/Copy — Kopierbar machen
#[derive(Clone, Copy)]

// PartialEq, Eq — Vergleichbar
#[derive(PartialEq, Eq)]

// Serialize/Deserialize (serde)
#[derive(Serialize, Deserialize)]
```

### Error Handling Pattern
```rust
use anyhow::{Result, Context};

fn read_config(path: &str) -> Result<Config> {
    let content = std::fs::read_to_string(path)
        .context("Failed to read config file")?;
    let config: Config = serde_json::from_str(&content)
        .context("Failed to parse config")?;
    Ok(config)
}
```

---

## IHK Mediengestalter — Prüfungsrelevantes Wissen

### Farbmanagement
- **RGB** (Rot, Grün, Blau) — Additiv, für Bildschirm
- **CMYK** (Cyan, Magenta, Yellow, Key/Schwarz) — Subtraktiv, für Druck
- **Pantone/HKS** — Sonderfarben (Schmuckfarben)
- **ICC-Profile**: sRGB (Screen), ISO Coated v2 (Druck, gestrichenes Papier), Uncoated (Naturpapier)
- **Rendering Intent**: Perzeptiv (Fotos), Relativ farbmetrisch (Logos), Absolut farbmetrisch (Proof)
- **Gamut**: Der darstellbare Farbraum eines Geräts. RGB > CMYK!

### Typografie
- **Schriftklassifikation nach DIN 16518**:
  1. Venezianische Renaissance-Antiqua (Garamond-ähnlich)
  2. Französische Renaissance-Antiqua (Garamond)
  3. Barock-Antiqua (Times-ähnlich)
  4. Klassizistische Antiqua (Bodoni, Didot)
  5. Serifenbetonte Linear-Antiqua (Rockwell, Courier)
  6. Serifenlose Linear-Antiqua (Helvetica, Arial, Futura)
  7. Antiqua-Varianten
  8. Schreibschriften
  9. Handschriftliche Antiqua
  10. Gebrochene Schriften (Fraktur)
  11. Fremde Schriften

- **Typografische Maße**:
  - 1 Punkt (pt) = 0,353 mm (DTP-Punkt)
  - 1 Cicero = 12 Punkt
  - Geviert = Quadrat der Schriftgröße
  - Halbgeviert = Gedankenstrich (–)
  - Viertelgeviert = Normalabstand

### Druckvorstufe (Prepress)
- **Preflight**: Automatische Prüfung der Druckdaten
- **Trapping**: Überlappung an Farbkanten um Blitzer zu vermeiden
- **Beschnitt**: 3mm umlaufend
- **Passermarken**: Registrierkreuze für exakte Farbausrichtung
- **Farbseparation**: Trennung in CMYK-Auszüge
- **Rasterung**: AM-Raster (regelmäßig) vs. FM-Raster (stochastisch)
- **Rasterweite**: 60er (Zeitung) → 80er (Magazin) → 120er (Kunstdruck) Linien/cm

### Weiterverarbeitung
- **Falzarten**: Wickelfalz, Zickzackfalz, Kreuzbruch, Altarfalz
- **Bindungen**: Klebebindung, Fadenheftung, Rückstichheftung, Wire-O, Ringbindung
- **Veredelung**: Dispersionslack, UV-Lack, Folienkaschierung, Heißfolienprägung, Blindprägung, Relieflack

### Kalkulation
- **Stundensatzkalkulation**: Personalkosten / produktive Stunden = Stundensatz
- **Zuschlagskalkulation**: Materialeinzelkosten + Materialgemeinkosten + Fertigungseinzelkosten + Fertigungsgemeinkosten + Verwaltungs-/Vertriebsgemeinkosten + Gewinn
- **Aufschlagssatz**: (Gemeinkosten / Einzelkosten) × 100
