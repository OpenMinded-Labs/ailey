# Ailey Portal — Deployment Guide

## Übersicht

Das Portal läuft auf **allinkl** (PHP + MySQL). Dein MacBook pollt allinkl automatisch per HTTPS — **kein Tunnel, kein Cloudflare, keine Extra-Software.**

```
[ Browser ] ←HTTPS→ [ allinkl (PHP + MySQL) ] ←HTTPS polling→ [ MacBook: Ailey Core ]
```

**Datenfluss:**
1. User schickt Nachricht → PHP speichert sie in MySQL als "pending"
2. Ailey Core pollt allinkl alle 3 Sekunden: "Gibt's was Neues?"
3. Ailey holt pending Messages, generiert Antwort mit LLM
4. Ailey pushed die Antwort zurück an allinkl
5. Browser des Users pollt allinkl alle 2 Sekunden → bekommt Antwort

## Setup: allinkl

### 1. Datenbank anlegen

Erstelle eine MySQL-Datenbank im allinkl KAS und importiere das Schema:

```bash
mysql -u USER -p DBNAME < schema.sql
```

### 2. Dateien hochladen

1. Lade den gesamten `portal/` Ordner per FTP hoch
2. Kopiere `config.example.php` → `config.php`
3. Fülle deine DB-Credentials und Portal-Key aus

### 3. Konfiguration (config.php)

```php
'db' => [
    'host'     => 'localhost',
    'name'     => 'dein_db_name',
    'user'     => 'dein_db_user',
    'password' => 'dein_db_passwort',
],
'ailey' => [
    'portal_key' => 'DEIN_GEHEIMER_KEY',  // Muss mit MacBook übereinstimmen
],
```

### 4. Ersten Admin erstellen

```sql
INSERT INTO portal_users (id, email, display_name, password_hash, role, status, consent_dsgvo, consent_ki)
VALUES (UUID(), 'deine@email.de', 'Simon', '$2y$10$DEIN_BCRYPT_HASH', 'admin', 'active', NOW(), NOW());

INSERT INTO portal_whitelist (email, used, created_at)
VALUES ('deine@email.de', 1, NOW());
```

Tipp: bcrypt-Hash generieren mit `php -r "echo password_hash('deinPasswort', PASSWORD_BCRYPT, ['cost'=>12]);"`.

## Setup: MacBook (Ailey Core)

### 1. Environment Variables

```bash
export AILEY_PORTAL_URL="https://dein-portal.de"
export AILEY_PORTAL_KEY="DEIN_GEHEIMER_KEY"
```

Das war's! Beim nächsten Ailey-Start pollt der PortalPoller automatisch.

### 2. Prüfen ob es läuft

Im Ailey-Log sollte stehen:

```
[Services] Starting Portal Poller → https://dein-portal.de
[PortalPoller] Configured → https://dein-portal.de
[PortalPoller] Started — polling every 3s (idle: 8s)
```

Falls `AILEY_PORTAL_URL` nicht gesetzt ist:

```
[Services] Portal Poller not started (AILEY_PORTAL_URL not set)
```

## Architektur

### Warum Polling statt Tunnel?

- **0 Abhängigkeiten** — kein Cloudflare, kein ngrok, keine Extra-Software
- **Funktioniert überall** — hinter jeder Firewall, jedem Router
- **Ausfallsicher** — MacBook offline? Messages warten in MySQL
- **Latenz:** ~2-5s extra (durch Polling). Bei LLM-Generation die 10-30s dauert: irrelevant.

### Datenfluss

```
User → allinkl (send_message → MySQL queue)
MacBook ← allinkl (poll_pending → gets pending items)
MacBook → allinkl (push_reply → Antwort in DB)
User ← allinkl (check_reply → bekommt Antwort)
```

## Themes

| Theme | Beschreibung |
|-------|-------------|
| 🌙 Dark  | Schwarz + Pink/Rot — Aileys Standardlook |
| ☀️ Light | Weiß + Pink — hell und freundlich |
| ⚡ Cyber | Anthrazit + Teal/Grün — Cyberpunk |

## Sicherheit

- **Whitelist-Only** — nur eingeladene E-Mails
- **bcrypt** (cost=12)
- **Portal-Key** — HMAC-gesicherter Shared Secret
- **Rate Limits** — 15/h, 50/Tag
- **Content Filter** — 3 Ebenen (System-Prompt, Output, PHP)
- **DSGVO** — Löschfunktion, Consent-Log, Impressum
- **noindex** — robots.txt + meta + HTTP-Header
- **CSP** — Content Security Policy in .htaccess

## Dateien

```
portal/
├── .htaccess           — Routing + Security Headers
├── robots.txt          — Suchmaschinen blockiert
├── index.php           — Router
├── api.php             — AJAX API (Polling-Architektur)
├── auth.php            — Auth + Sessions
├── db.php              — Database Layer
├── config.example.php  — Konfig-Template
├── schema.sql          — MySQL Schema
├── assets/             — CSS, JS, Bilder
└── pages/              — PHP Templates (9 Seiten)

ailey_system/
├── portal_poller.py    — Background-Poller (pollt allinkl)
├── portal_api.py       — Health/Monitoring Endpoints
└── portal_filter.py    — Content Filter
```
