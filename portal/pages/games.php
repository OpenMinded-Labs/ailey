<?php
/**
 * A!ley Portal — Play with Ailey (Games Hub)
 * 
 * Three mini-games with Ailey as opponent:
 * - KI Quartett: AI model top-trumps card game
 * - DuChess: Neon DuCHESS — real chess with factions + chaos cards
 * - Server DDOS: Battleship with network theme
 * 
 * Requires login. Highscores visible to all players.
 */
require_once __DIR__ . '/layout.php';
if (!$user) { header('Location: /login'); exit; }

$selectedGame = $_GET['game'] ?? '';
$pageTitle = 'Play with A!ley';
if ($selectedGame === 'quartett') $pageTitle = 'KI Quartett';
if ($selectedGame === 'duchess') $pageTitle = 'Neon DuCHESS';
if ($selectedGame === 'server_ddos') $pageTitle = 'Server DDOS';

portal_head($pageTitle);
?>
<link rel="stylesheet" href="/assets/games.css?v=<?= filemtime(__DIR__ . '/../assets/games.css') ?: time() ?>">
<script src="/assets/games.js?v=<?= filemtime(__DIR__ . '/../assets/games.js') ?: time() ?>" defer></script>
<?php
$userName = htmlspecialchars($user['display_name'] ?? 'User');
$userId = $user['id'];
?>

<main class="games-page">

<!-- ═══ GAME HUB (selection screen) ═══════════════════════════════════════ -->
<section id="games-hub" class="games-hub <?= $selectedGame ? 'hidden' : '' ?>">
    <div class="games-header">
        <h1>🎮 Play with A<span class="highlight">!</span>ley</h1>
        <p class="games-subtitle">Trau dich, bitch. Ailey wartet. 😏</p>
    </div>

    <div class="games-grid">
        <!-- KI Quartett -->
        <div class="game-card game-card-quartett" onclick="Games.selectGame('quartett')">
            <div class="game-card-icon">🃏</div>
            <h2>KI Quartett</h2>
            <p>Trumpfe mit GPU-Power, Parametern & Benchmarks — 16 echte KI-Modelle im Neon-Duell!</p>
            <div class="game-card-tags">
                <span class="tag">Top Trumps</span>
                <span class="tag">2-5 Min</span>
                <button class="tag tag-rules" onclick="event.stopPropagation(); showRules('quartett')">📖 Regeln</button>
            </div>
        </div>

        <!-- DuChess -->
        <div class="game-card game-card-duchess" onclick="Games.selectGame('duchess')">
            <div class="game-card-icon">♛</div>
            <h2>Neon DuCHESS</h2>
            <p>Echtes Schach — Neon Punk Edition. Jede Figur trägt eine geheime Chaos Card. Schachmatt oder Chaos!</p>
            <div class="game-card-tags">
                <span class="tag">Schach + Chaos</span>
                <span class="tag">5-20 Min</span>
                <button class="tag tag-rules" onclick="event.stopPropagation(); showRules('duchess')">📖 Regeln</button>
            </div>
        </div>

        <!-- Server DDOS -->
        <div class="game-card game-card-ddos" onclick="Games.selectGame('server_ddos')">
            <div class="game-card-icon">�</div>
            <h2>Server DDOS</h2>
            <p>Terminal-Battleship. Finde & zerstöre Aileys Server-Cluster — bevor sie dein Netz crasht.</p>
            <div class="game-card-tags">
                <span class="tag">Hacker Taktik</span>
                <span class="tag">5-10 Min</span>
                <button class="tag tag-rules" onclick="event.stopPropagation(); showRules('server_ddos')">📖 Regeln</button>
            </div>
        </div>
    </div>

    <!-- ═══ HIGHSCORES ═══════════════════════════════════════════════════════ -->
    <div class="highscores-section">
        <h2>🏆 Highscores</h2>
        <div class="highscores-tabs">
            <button class="hs-tab active" data-game="quartett" onclick="Games.showHighscores('quartett')">🃏 Quartett</button>
            <button class="hs-tab" data-game="duchess" onclick="Games.showHighscores('duchess')">⚔️ Neon DuCHESS</button>
            <button class="hs-tab" data-game="server_ddos" onclick="Games.showHighscores('server_ddos')">🖥️ Server DDOS</button>
        </div>
        <div id="highscores-table" class="highscores-table">
            <div class="hs-loading">Lade Highscores…</div>
        </div>
    </div>
</section>

<!-- ═══ GAME ARENA (active game) ══════════════════════════════════════════ -->
<section id="game-arena" class="game-arena <?= $selectedGame ? '' : 'hidden' ?>">
    <!-- Ailey speech bubble -->
    <div class="ailey-game-bar">
        <img class="ailey-game-avatar" src="/assets/ailey-default.jpg" alt="A!ley">
        <div class="ailey-speech-bubble" id="ailey-bubble">
            <span id="ailey-says">Bereit? Lass uns spielen! 🎲</span>
        </div>
    </div>

    <!-- Game board area (filled by JS per game) -->
    <div id="game-board" class="game-board"></div>

    <!-- Game status bar -->
    <div class="game-status-bar">
        <div class="game-score-display">
            <span class="score-label"><?= $userName ?></span>
            <span class="score-value" id="player-score">0</span>
        </div>
        <div class="game-round" id="game-round">Runde 1</div>
        <div class="game-score-display ailey-score">
            <span class="score-label">A!ley</span>
            <span class="score-value" id="ailey-score">0</span>
        </div>
    </div>

    <!-- Game controls -->
    <div class="game-controls">
        <button class="btn btn-ghost" onclick="Games.quit()">✕ Aufgeben</button>
        <button class="btn btn-ghost btn-sm" onclick="showRules(Games.currentGame)">📖 Regeln</button>
        <button class="btn btn-primary" id="game-action-btn" onclick="Games.action()" disabled>Warte…</button>
    </div>
</section>

<!-- ═══ GAME OVER OVERLAY ════════════════════════════════════════════════ -->
<div id="game-over-overlay" class="game-over-overlay hidden">
    <div class="game-over-card">
        <div class="game-over-icon" id="game-over-icon">🏆</div>
        <h2 id="game-over-title">Ergebnis</h2>
        <p id="game-over-msg"></p>
        <div class="game-over-stats" id="game-over-stats"></div>
        <div class="game-over-actions">
            <button class="btn btn-primary" onclick="Games.rematch()">🔄 Revanche</button>
            <button class="btn btn-ghost" onclick="Games.backToHub()">← Spielauswahl</button>
        </div>
    </div>
</div>

<!-- ═══ RULES MODAL ══════════════════════════════════════════════════════ -->
<div id="rules-modal" class="rules-modal hidden" onclick="if(event.target===this)closeRules()">
    <div class="rules-card">
        <button class="rules-close" onclick="closeRules()">✕</button>
        <div id="rules-content"></div>
    </div>
</div>

<script>
const GAME_RULES = {
    quartett: {
        title: '🃏 KI Quartett — Regeln',
        html: `
            <h3>So geht's, du Noob:</h3>
            <p>16 echte KI-Modell-Karten (GPT-4o, Claude, Llama, FLUX, etc.) werden gemischt und gleichmäßig verteilt.</p>
            <h4>📊 Die 5 Stats:</h4>
            <ul>
                <li><strong>🧠 Parameter (B)</strong> — Größe des Modells. Höher = besser.</li>
                <li><strong>📊 Benchmark Score</strong> — Performance. Höher = besser.</li>
                <li><strong>💾 GPU RAM (GB)</strong> — Speicherbedarf. <em>NIEDRIGER = BESSER!</em> (effizientere Modelle gewinnen)</li>
                <li><strong>⚡ Speed Score</strong> — Geschwindigkeit. Höher = besser.</li>
                <li><strong>✨ Vibe Check</strong> — Community-Hype. Höher = besser.</li>
            </ul>
            <h4>⚔️ Spielablauf:</h4>
            <ol>
                <li>Wer dran ist, wählt eine Kategorie (Stat).</li>
                <li>Beide Karten werden verglichen — der bessere Wert gewinnt.</li>
                <li>Gewinner bekommt BEIDE Karten und ist wieder dran.</li>
                <li>Alle Karten weg = Game Over. Oder nach 30 Runden zählt der Score.</li>
            </ol>
            <p class="rules-tip">💡 <strong>Pro-Tipp:</strong> GPU RAM ist invers! Kleine effiziente Modelle dominieren in der Kategorie.</p>
        `
    },
    duchess: {
        title: '♛ Neon DuCHESS — Punk Edition',
        html: `
            <h3>Echtes Schach. Echtes Chaos.</h3>
            <p>Standard-Schach auf 8×8 Board — aber jede Figur trägt eine <em>geheime Chaos Card</em>, die bei Capture, Check oder Promotion enthüllt wird.</p>
            <h4>♟ Die Figuren (Punk-Namen):</h4>
            <ul>
                <li><strong>♚ ICON</strong> — König. 1 Feld in alle Richtungen. Schachmatt = Game Over.</li>
                <li><strong>♛ ACE</strong> — Dame. Gerade + diagonal, beliebig weit.</li>
                <li><strong>♜ TOWER</strong> — Turm. Gerade, beliebig weit. Rochade möglich.</li>
                <li><strong>♝ SLIDER</strong> — Läufer. Diagonal, beliebig weit.</li>
                <li><strong>♞ JUMPER</strong> — Springer. L-Form, springt über Figuren.</li>
                <li><strong>♟ PAWN</strong> — Bauer. 1 (oder 2 am Start) vorwärts, diagonal schlagen.</li>
            </ul>
            <h4>🎴 Chaos Cards:</h4>
            <p>Jede Figur hat eine versteckte Chaos Card. Sie wird enthüllt bei:</p>
            <ul>
                <li>Die Figur <strong>schlägt</strong> eine gegnerische Figur</li>
                <li>Die Figur gibt <strong>Schach</strong></li>
                <li>Ein Bauer macht <strong>Promotion</strong></li>
            </ul>
            <p>Effekte: Figur wiederherstellen, Extra-Zug, Figur einfrieren, teleportieren, und mehr!</p>
            <h4>⚔️ Spielablauf:</h4>
            <ol>
                <li>Standard-Schachregeln (inkl. Rochade, En Passant, Promotion).</li>
                <li>A!ley spielt ihre Züge per KI — kein Engine, sie denkt selbst.</li>
                <li>Chaos Cards mischen das Spiel auf — auch verloren geglaubte Partien drehen sich!</li>
            </ol>
            <p class="rules-tip">💡 <strong>Pro-Tipp:</strong> Chaos Cards werden zufällig verteilt. Manchmal lohnt sich ein Opfer, um die Card deiner Figur zu triggern!</p>
        `
    },
    server_ddos: {
        title: '🖥️ Server DDOS — Regeln',
        html: `
            <h3>Battleship, aber als Hacker 💀</h3>
            <p>8×8 Grid. Beide platzieren 5 Server-Cluster (versteckt). Abwechselnd schießen. Alle Server des Gegners zerstören = Sieg.</p>
            <h4>🖥️ Deine Server:</h4>
            <ul>
                <li><strong>⚖️ Load Balancer</strong> — 4 Zellen</li>
                <li><strong>🗄️ Database</strong> — 3 Zellen</li>
                <li><strong>🔌 API Gateway</strong> — 3 Zellen</li>
                <li><strong>📦 Microservice</strong> — 2 Zellen</li>
                <li><strong>🌐 DNS Server</strong> — 1 Zelle</li>
            </ul>
            <h4>🎯 Spielablauf:</h4>
            <ol>
                <li><strong>Platzierung:</strong> Setze deine Server horizontal oder vertikal aufs Grid.</li>
                <li><strong>Angriff:</strong> Klick auf Aileys Grid = Schuss. 💥 = Treffer, · = Wasser.</li>
                <li>Server versenkt = Bonus-Punkte!</li>
                <li>Ailey greift danach automatisch zurück.</li>
            </ol>
            <p class="rules-tip">💡 <strong>Pro-Tipp:</strong> Nach einem Treffer die Nachbarfelder abchecken — Server sind zusammenhängend!</p>
        `
    }
};

function showRules(game) {
    const rules = GAME_RULES[game];
    if (!rules) return;
    document.getElementById('rules-content').innerHTML = `<h2>${rules.title}</h2>${rules.html}`;
    document.getElementById('rules-modal').classList.remove('hidden');
}

function closeRules() {
    document.getElementById('rules-modal').classList.add('hidden');
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeRules(); });
</script>

</main>

<?php portal_footer(); ?>
