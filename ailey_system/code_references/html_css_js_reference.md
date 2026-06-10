# HTML, CSS & JavaScript — Ailey Code-Referenz

> Modernes Vanilla Web Development: HTML5, CSS3, ES2022+ JavaScript

## HTML5 Semantic Structure

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Seitenbeschreibung">
  <title>Titel</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header>
    <nav aria-label="Hauptnavigation">
      <ul>
        <li><a href="/">Home</a></li>
        <li><a href="/about">Über</a></li>
      </ul>
    </nav>
  </header>

  <main>
    <article>
      <h1>Überschrift</h1>
      <section>
        <h2>Abschnitt</h2>
        <p>Inhalt</p>
      </section>
    </article>
    <aside>Sidebar</aside>
  </main>

  <footer>
    <p>&copy; 2025</p>
  </footer>

  <script type="module" src="app.js"></script>
</body>
</html>
```

### Wichtige HTML-Elemente

```html
<!-- Formulare -->
<form action="/api/submit" method="POST">
  <label for="email">E-Mail:</label>
  <input type="email" id="email" name="email" required placeholder="mail@example.com">
  <textarea name="message" rows="4" required></textarea>
  <select name="category">
    <option value="">Bitte wählen</option>
    <option value="support">Support</option>
  </select>
  <button type="submit">Senden</button>
</form>

<!-- Dialog (nativ modal) -->
<dialog id="modal">
  <h2>Modal</h2>
  <p>Inhalt</p>
  <button onclick="this.closest('dialog').close()">Schließen</button>
</dialog>

<!-- Details/Summary (Akkordeon) -->
<details>
  <summary>Mehr anzeigen</summary>
  <p>Versteckter Inhalt</p>
</details>

<!-- Picture (responsive Images) -->
<picture>
  <source media="(min-width: 800px)" srcset="large.webp" type="image/webp">
  <source media="(min-width: 800px)" srcset="large.jpg">
  <img src="small.jpg" alt="Beschreibung" loading="lazy" width="800" height="600">
</picture>
```

## CSS3 Modern

### CSS Custom Properties (Variables)

```css
:root {
  --color-primary: #be123c;
  --color-bg: #0a0a0a;
  --color-text: #ffffff;
  --radius: 0.5rem;
  --font-sans: system-ui, -apple-system, sans-serif;
}

/* Dark Mode */
@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #0a0a0a;
    --color-text: #f0f0f0;
  }
}
```

### Flexbox

```css
.flex-container {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.flex-item {
  flex: 1 1 300px; /* grow shrink basis */
}
```

### CSS Grid

```css
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
}

/* Named Grid Areas */
.layout {
  display: grid;
  grid-template-areas:
    "header header"
    "sidebar main"
    "footer footer";
  grid-template-columns: 250px 1fr;
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
}
.header  { grid-area: header; }
.sidebar { grid-area: sidebar; }
.main    { grid-area: main; }
.footer  { grid-area: footer; }
```

### Container Queries

```css
.card-container {
  container-type: inline-size;
  container-name: card;
}

@container card (min-width: 400px) {
  .card { flex-direction: row; }
}
```

### Animations

```css
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

.animate {
  animation: fadeIn 0.3s ease-out;
}

/* Transition */
.btn {
  transition: background-color 0.2s, transform 0.1s;
}
.btn:hover {
  transform: scale(1.02);
}
.btn:active {
  transform: scale(0.98);
}
```

### Scroll Snap

```css
.scroll-container {
  scroll-snap-type: x mandatory;
  overflow-x: scroll;
  display: flex;
}
.scroll-item {
  scroll-snap-align: start;
  flex-shrink: 0;
  width: 100%;
}
```

## JavaScript ES2022+

### Fetch API

```javascript
// GET
const response = await fetch('/api/items');
const data = await response.json();

// POST
const result = await fetch('/api/items', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ name: 'Test', value: 42 }),
});

// Mit Fehlerbehandlung
async function fetchData(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } catch (err) {
    console.error('Fetch failed:', err);
    return null;
  }
}
```

### DOM Manipulation

```javascript
// Selectors
const el = document.querySelector('.my-class');
const all = document.querySelectorAll('[data-action]');

// Events (mit Options)
el.addEventListener('click', handler, { once: true, passive: true });

// Event Delegation
document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  handleAction(action);
});

// DOM Creation
const div = document.createElement('div');
div.className = 'card';
div.innerHTML = `<h3>${title}</h3><p>${text}</p>`;
container.append(div);

// Intersection Observer (Lazy Loading)
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.lazy').forEach(el => observer.observe(el));
```

### ES Modules

```javascript
// export
export function helper() { ... }
export default class App { ... }

// import
import App, { helper } from './app.js';

// Dynamic import (code splitting)
const module = await import('./heavy-module.js');
```

### Modern JS Features

```javascript
// Optional Chaining & Nullish Coalescing
const name = user?.profile?.name ?? 'Unbekannt';

// Structured Clone (deep copy)
const copy = structuredClone(original);

// Array methods
const unique = [...new Set(array)];
const grouped = Object.groupBy(items, item => item.category); // ES2024
const found = array.findLast(x => x > 5);
const indexed = array.at(-1); // letztes Element

// Promise.allSettled
const results = await Promise.allSettled([fetch(url1), fetch(url2)]);
const successes = results.filter(r => r.status === 'fulfilled').map(r => r.value);

// AbortController
const controller = new AbortController();
setTimeout(() => controller.abort(), 5000); // Timeout
await fetch(url, { signal: controller.signal });
```

### Web APIs

```javascript
// LocalStorage
localStorage.setItem('key', JSON.stringify(value));
const value = JSON.parse(localStorage.getItem('key') ?? 'null');

// URLSearchParams
const params = new URLSearchParams(window.location.search);
const page = params.get('page') ?? '1';

// Clipboard
await navigator.clipboard.writeText('Kopiert!');
const text = await navigator.clipboard.readText();

// Web Components
class MyElement extends HTMLElement {
  connectedCallback() { this.innerHTML = '<p>Custom Element</p>'; }
}
customElements.define('my-element', MyElement);
```

## Häufige Stolperfallen

- `var` nie verwenden → immer `const` (Standard) oder `let` (wenn Reassignment nötig)
- `==` nie verwenden → immer `===`
- `this` in Arrow Functions → kein eigenes `this`, nutzt enclosing scope
- Event Listener Memory Leaks → `removeEventListener` oder `AbortController`
- CORS bei fetch → Backend muss `Access-Control-Allow-Origin` setzen
- `<img>` ohne `alt` → Accessibility-Fehler
- CSS `z-index` ohne `position` → funktioniert nicht
- `100vh` auf Mobile → `100dvh` verwenden (dynamic viewport height)
