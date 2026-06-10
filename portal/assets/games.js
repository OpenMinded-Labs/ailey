/**
 * A!ley Portal — Games Engine  ·  NEON PUNK EDITION
 *
 * Three mini-games with Ailey as LLM-powered opponent:
 *   1. KI Quartett — AI model top-trumps
 *   2. DuChess — Real 8×8 chess + chaos cards
 *   3. Server DDOS — Battleship with network/terminal theme
 *
 * Architecture:
 *   Game logic runs client-side.
 *   Ailey's moves + comments: portal API → Ailey Core LLM.
 *   State persisted server-side for resume. Highscores aggregated server-side.
 */

/* debug removed */
const _dbg = { log() {} };

/* ═══════════════════════════════════════════════════════════════════════════
   CORE ENGINE
   ═══════════════════════════════════════════════════════════════════════════ */
const Games = (() => {
    let currentGame = null;
    let sessionId = null;
    let gameState = {};
    let startTime = null;
    let playerScore = 0;
    let aileyScore = 0;
    let round = 0;
    let isAileyTurn = false;
    let waitingForAiley = false;
    let gameHistory = [];

    const API = '/api.php';

    async function api(action, data = {}) {
        _dbg.log(`API call: ${action}`);
        try {
            const res = await fetch(`${API}?action=${action}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(data)
            });
            _dbg.log(`API ${action} → HTTP ${res.status}`);
            if (!res.ok) {
                const text = await res.text();
                _dbg.log(`API ${action} ERROR body: ${text.substring(0, 200)}`);
                try { return JSON.parse(text); } catch(_) { return { error: `HTTP ${res.status}`, _raw: text }; }
            }
            const json = await res.json();
            _dbg.log(`API ${action} OK: ${JSON.stringify(json).substring(0, 200)}`);
            return json;
        } catch (err) {
            _dbg.log(`API ${action} EXCEPTION: ${err.message}`);
            return { error: err.message };
        }
    }

    function aileySays(text) {
        const el = document.getElementById('ailey-says');
        if (el) { el.style.opacity = '0'; setTimeout(() => { el.textContent = text; el.style.opacity = '1'; }, 150); }
    }
    function updateScores() {
        const ps = document.getElementById('player-score');
        const as_ = document.getElementById('ailey-score');
        const rnd = document.getElementById('game-round');
        if (ps) ps.textContent = playerScore;
        if (as_) as_.textContent = aileyScore;
        if (rnd) rnd.textContent = `Runde ${round}`;
    }
    function setActionBtn(text, enabled = true) {
        const btn = document.getElementById('game-action-btn');
        if (btn) { btn.textContent = text; btn.disabled = !enabled; }
    }

    // ── Selection & Resume ───────────────────────────────────────────────
    async function selectGame(game) {
        currentGame = game;
        _dbg.log(`selectGame: ${game}`);
        try {
            const res = await api('game_check_active', { game });
            _dbg.log(`check_active result: active_session=${!!res.active_session}`);
            if (res.active_session) { showResumeDialog(res.active_session); return; }
        } catch(e) { _dbg.log(`check_active FAILED: ${e.message}`); }
        _dbg.log('No active session → startNewGame');
        startNewGame();
    }
    function showResumeDialog(session) {
        _dbg.log(`showResumeDialog: session.id=${session.id}, rounds=${session.rounds}, score=${session.score}`);
        const board = document.getElementById('game-board');
        const sid = String(session.id).replace(/'/g, '');
        board.innerHTML = `
            <div class="resume-dialog">
                <div class="resume-icon">⏸️</div>
                <h2>Laufendes Spiel gefunden!</h2>
                <p>${_gameLabel(currentGame)} — ${session.rounds ? 'Runde ' + session.rounds : ''} Stand: Du ${session.score || 0}</p>
                <div class="resume-actions">
                    <button class="btn btn-primary btn-lg" onclick="Games.resumeGame('${sid}')">▶️ Weiterspielen</button>
                    <button class="btn btn-ghost" onclick="Games.abandonAndNew('${sid}')">🔄 Neues Spiel</button>
                </div>
            </div>`;
        document.getElementById('games-hub').classList.add('hidden');
        document.getElementById('game-arena').classList.remove('hidden');
        setActionBtn('Wähle eine Option', false);
    }
    async function resumeGame(id) {
        _dbg.log(`resumeGame: ${id}`);
        try {
            const res = await api('game_load', { session_id: id });
            _dbg.log(`game_load result: success=${res.success}, has_state=${!!res.game_state}`);
            if (res.success && res.game_state) {
                sessionId = id; gameState = res.game_state;
                playerScore = gameState.playerScore || 0; aileyScore = gameState.aileyScore || 0;
                round = gameState.round || 1; gameHistory = gameState.gameHistory || [];
                startTime = Date.now() - ((gameState.elapsedSecs || 0) * 1000);
                updateScores();
                aileySays('Oh shit, da waren wir doch… Egal, let\'s go bitch! 😈');
                requestAileyComment('resume', { resumedAt: round });
                _dbg.log('Calling _renderResumedGame');
                _renderResumedGame();
                return;
            }
        } catch(e) { _dbg.log(`resumeGame ERROR: ${e.message}`); }
        _dbg.log('Resume failed → startNewGame');
        aileySays('Session kaputt — neues Spiel! 🎲');
        await startNewGame();
    }
    async function abandonAndNew(oldId) {
        _dbg.log(`abandonAndNew: ${oldId}`);
        try { await api('game_abandon', { session_id: oldId }); } catch(_) {}
        await startNewGame();
    }

    async function startNewGame() {
        _dbg.log(`startNewGame for: ${currentGame}`);
        playerScore = 0; aileyScore = 0; round = 1; startTime = Date.now();
        gameState = {}; gameHistory = []; updateScores();
        try {
            const res = await api('game_start', { game: currentGame });
            if (res.success) sessionId = res.session_id;
            else sessionId = 'local_' + Date.now();
        } catch(e) { _dbg.log(`game_start FAILED: ${e.message}`); sessionId = 'local_' + Date.now(); }
        _dbg.log(`sessionId: ${sessionId}`);
        document.getElementById('games-hub').classList.add('hidden');
        document.getElementById('game-arena').classList.remove('hidden');
        document.getElementById('game-arena').className = `game-arena theme-${currentGame}`;
        _dbg.log(`Launching game engine: ${currentGame}`);
        try {
            switch (currentGame) {
                case 'quartett': Quartett.init(); break;
                case 'duchess': DuChess.init(); break;
                case 'server_ddos': ServerDDOS.init(); break;
            }
            _dbg.log(`Game ${currentGame} init() OK`);
        } catch (e) {
            _dbg.log(`Game init CRASHED: ${e.message}\n${e.stack}`);
            aileySays(`Fehler beim Laden: ${e.message} 😵`);
        }
    }
    function _renderResumedGame() {
        document.getElementById('game-arena').className = `game-arena theme-${currentGame}`;
        switch (currentGame) {
            case 'quartett': Quartett.restore(gameState); break;
            case 'duchess': DuChess.restore(gameState); break;
            case 'server_ddos': ServerDDOS.restore(gameState); break;
        }
    }

    // ── State persistence ────────────────────────────────────────────────
    async function saveState() {
        if (!sessionId) return;
        try {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            await api('game_save', { session_id: sessionId, score: playerScore, rounds: round,
                game_state: { ...gameState, playerScore, aileyScore, round, gameHistory, elapsedSecs: elapsed } });
        } catch(_) { console.warn('saveState failed'); }
    }

    // ── Game Over ────────────────────────────────────────────────────────
    async function gameOver(result) {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        logEvent(`SPIELENDE: ${result.toUpperCase()} — Score ${playerScore}:${aileyScore} nach ${round} Runden`);
        try { await api('game_finish', { session_id: sessionId, result, score: playerScore, rounds: round, duration_secs: elapsed, metadata: gameState.metadata || {} }); } catch(_) {}

        const overlay = document.getElementById('game-over-overlay');
        const icon = document.getElementById('game-over-icon');
        const title = document.getElementById('game-over-title');
        const msg = document.getElementById('game-over-msg');
        const fallbacks = {
            win: ['What the FUCK?! Nee, Rematch. JETZT. 😤', 'Scheiße, respect. Du hast mich erwischt. 🥶'],
            loss: ['HAHA get REKT! 💀 Easy game~', 'GG! …Spaß. War gar nicht close. 😈'],
            draw: ['Unentschieden?! BULLSHIT. Rematch! 😤'],
        };
        icon.textContent = result === 'win' ? '🏆' : result === 'loss' ? '💀' : '🤝';
        title.textContent = result === 'win' ? 'Gewonnen!' : result === 'loss' ? 'Verloren!' : 'Unentschieden!';
        aileySays(_randomPick(fallbacks[result] || fallbacks.draw));
        requestAileyComment('game_over', { result, finalScore: { player: playerScore, ailey: aileyScore }, totalRounds: round, duration: _formatTime(elapsed) });
        msg.textContent = `${round} Runden · ${_formatTime(elapsed)} · Score: ${playerScore} vs ${aileyScore}`;
        overlay.classList.remove('hidden');
    }

    // ── History & LLM ────────────────────────────────────────────────────
    function logEvent(text) { gameHistory.push(`R${round}: ${text}`); if (gameHistory.length > 30) gameHistory = gameHistory.slice(-20); }
    function getHistoryContext() { return gameHistory.slice(-20).join('\n'); }

    async function requestAileyMove(context) {
        waitingForAiley = true; aileySays('*crackt die Knöchel* …');
        try {
            const res = await api('game_ailey_move', { session_id: sessionId, game: currentGame, round, type: 'move',
                context: JSON.stringify({ ...context, history: getHistoryContext(), score: { player: playerScore, ailey: aileyScore }, round }) });
            if (!res.success || !res.move_id) { waitingForAiley = false; return null; }
            // Poll max 4 seconds (8 × 500ms) — if Ailey Core isn't responding, fallback immediately
            for (let i = 0; i < 8; i++) {
                await new Promise(r => setTimeout(r, 500));
                try {
                    const check = await api('game_check_move', { move_id: res.move_id });
                    if (check.status === 'ready') {
                        waitingForAiley = false;
                        const parsed = _parseAileyReply(check.reply || '');
                        if (parsed.comment) aileySays(parsed.comment);
                        return parsed.move;
                    }
                } catch (_) { break; }
            }
        } catch (e) { console.warn('requestAileyMove error:', e); }
        waitingForAiley = false;
        // Graceful fallback — game engines have their own smart fallback logic
        return null;
    }
    // Comments are fire-and-forget — never block gameplay
    function requestAileyComment(event, extra = {}) {
        api('game_ailey_move', { session_id: sessionId, game: currentGame, round, type: 'comment',
            context: JSON.stringify({ event, ...extra, history: getHistoryContext(), score: { player: playerScore, ailey: aileyScore }, round }) })
        .then(res => {
            if (!res?.success || !res?.move_id) return;
            let polls = 0;
            const poll = setInterval(async () => {
                polls++;
                if (polls > 8) { clearInterval(poll); return; }
                try {
                    const check = await api('game_check_move', { move_id: res.move_id });
                    if (check.status === 'ready') {
                        clearInterval(poll);
                        const text = (check.reply || '').replace(/^MOVE:\{.*\}\s*/i, '').trim();
                        if (text) aileySays(text);
                    }
                } catch (_) { clearInterval(poll); }
            }, 500);
        }).catch(() => {});
    }
    function _parseAileyReply(raw) {
        const result = { move: null, comment: '' };
        if (!raw) return result;
        const moveMatch = raw.match(/^MOVE:\s*(\{.*\})\s*$/m);
        if (moveMatch) {
            try { result.move = JSON.parse(moveMatch[1]); } catch (_) {}
            result.comment = raw.replace(moveMatch[0], '').trim();
        } else result.comment = raw.trim();
        return result;
    }

    // ── Navigation ───────────────────────────────────────────────────────
    function quit() { if (confirm('Spiel verlassen? Fortschritt wird gespeichert.')) { saveState(); backToHub(); } }
    function backToHub() {
        document.getElementById('game-arena').classList.add('hidden');
        document.getElementById('game-over-overlay').classList.add('hidden');
        document.getElementById('games-hub').classList.remove('hidden');
        currentGame = null; sessionId = null; loadHighscores('quartett');
    }
    function rematch() { document.getElementById('game-over-overlay').classList.add('hidden'); startNewGame(); }
    function action() {
        if (waitingForAiley) return;
        switch (currentGame) {
            case 'quartett': Quartett.playerAction(); break;
            case 'duchess': DuChess.playerAction(); break;
            case 'server_ddos': ServerDDOS.playerAction(); break;
        }
    }

    // ── Highscores ───────────────────────────────────────────────────────
    async function showHighscores(game) {
        document.querySelectorAll('.hs-tab').forEach(t => t.classList.remove('active'));
        document.querySelector(`.hs-tab[data-game="${game}"]`)?.classList.add('active');
        await loadHighscores(game);
    }
    async function loadHighscores(game) {
        const container = document.getElementById('highscores-table');
        if (!container) return;
        container.innerHTML = '<div class="hs-loading">Lade…</div>';
        try {
            const res = await api('game_highscores', { game });
            if (!res.success || !res.scores?.length) { container.innerHTML = '<div class="hs-empty">Noch keine Highscores. Sei der Erste! 🎯</div>'; return; }
            const medals = ['🥇', '🥈', '🥉'];
            let html = '<div class="hs-list">';
            res.scores.forEach((s, i) => {
                const medal = medals[i] || `<span class="hs-rank">${i + 1}</span>`;
                const streak = s.best_streak >= 3 ? `<span class="hs-streak">🔥${s.best_streak}</span>` : '';
                html += `<div class="hs-row ${s.is_you ? 'hs-you' : ''}"><div class="hs-medal">${medal}</div><div class="hs-name">${_esc(s.display_name)}${s.is_you ? ' (du)' : ''}</div><div class="hs-wins">${s.total_wins}W/${s.total_losses}L</div><div class="hs-best">${s.best_score} ${streak}</div></div>`;
            });
            container.innerHTML = html + '</div>';
        } catch (e) {
            console.warn('loadHighscores error:', e);
            container.innerHTML = '<div class="hs-empty">Highscores konnten nicht geladen werden.</div>';
        }
    }

    // ── Helpers ──────────────────────────────────────────────────────────
    function _gameLabel(g) { return { quartett: 'KI Quartett', duchess: 'Neon DuCHESS', server_ddos: 'Server DDOS' }[g] || g; }
    function _randomPick(a) { return a[Math.floor(Math.random() * a.length)]; }
    function _formatTime(s) { const m = Math.floor(s / 60); return m > 0 ? `${m}m ${s % 60}s` : `${s}s`; }
    function _esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
    function init() { loadHighscores('quartett'); }

    return {
        selectGame, resumeGame, abandonAndNew, startNewGame,
        quit, backToHub, rematch, action, showHighscores, init,
        aileySays, updateScores, setActionBtn, saveState, gameOver,
        requestAileyMove, requestAileyComment, logEvent,
        _randomPick, _esc,
        get currentGame() { return currentGame; },
        get state() { return gameState; },
        set state(s) { gameState = s; },
        get playerScore() { return playerScore; },
        set playerScore(v) { playerScore = v; updateScores(); },
        get aileyScore() { return aileyScore; },
        set aileyScore(v) { aileyScore = v; updateScores(); },
        get round() { return round; },
        set round(v) { round = v; updateScores(); },
    };
})();


/* ═══════════════════════════════════════════════════════════════════════════
   GAME 1: KI QUARTETT — Neon Punk Top Trumps
   ═══════════════════════════════════════════════════════════════════════════ */
const Quartett = (() => {
    const DECK = [
        { name: 'GPT-4o', company: 'OpenAI', emoji: '🟢', params: 1800, benchmark: 92, gpuRam: 120, speed: 85, vibe: 78, accent: '#10a37f' },
        { name: 'Claude 3.5', company: 'Anthropic', emoji: '🟤', params: 680, benchmark: 91, gpuRam: 80, speed: 80, vibe: 92, accent: '#d4a574' },
        { name: 'Gemini Ultra', company: 'Google', emoji: '🔵', params: 1560, benchmark: 90, gpuRam: 192, speed: 70, vibe: 65, accent: '#4285f4' },
        { name: 'Llama 3 405B', company: 'Meta', emoji: '🦙', params: 405, benchmark: 87, gpuRam: 200, speed: 45, vibe: 88, accent: '#0668E1' },
        { name: 'Mistral Large', company: 'Mistral', emoji: '🌊', params: 123, benchmark: 84, gpuRam: 48, speed: 90, vibe: 82, accent: '#ff7000' },
        { name: 'Ministral 14B', company: 'Mistral', emoji: '🌬️', params: 14, benchmark: 72, gpuRam: 10, speed: 95, vibe: 96, accent: '#ff7000' },
        { name: 'Qwen 2.5 72B', company: 'Alibaba', emoji: '🟣', params: 72, benchmark: 85, gpuRam: 40, speed: 75, vibe: 70, accent: '#6236ff' },
        { name: 'DeepSeek V3', company: 'DeepSeek', emoji: '🔍', params: 671, benchmark: 89, gpuRam: 160, speed: 60, vibe: 85, accent: '#1a73e8' },
        { name: 'Grok-2', company: 'xAI', emoji: '🤖', params: 314, benchmark: 78, gpuRam: 120, speed: 65, vibe: 55, accent: '#1d1d1f' },
        { name: 'Phi-4', company: 'Microsoft', emoji: '🔷', params: 14, benchmark: 76, gpuRam: 8, speed: 98, vibe: 73, accent: '#00bcf2' },
        { name: 'FLUX.1', company: 'Black Forest', emoji: '🎨', params: 12, benchmark: 88, gpuRam: 8, speed: 92, vibe: 94, accent: '#8b5cf6' },
        { name: 'Stable Diff XL', company: 'Stability', emoji: '🖼️', params: 6.6, benchmark: 82, gpuRam: 6, speed: 88, vibe: 80, accent: '#a855f7' },
        { name: 'Whisper V3', company: 'OpenAI', emoji: '🎤', params: 1.5, benchmark: 90, gpuRam: 2, speed: 99, vibe: 75, accent: '#10a37f' },
        { name: 'Wan2.1', company: 'Alibaba', emoji: '🎬', params: 14, benchmark: 85, gpuRam: 16, speed: 30, vibe: 88, accent: '#6236ff' },
        { name: 'Sora', company: 'OpenAI', emoji: '🎞️', params: 3000, benchmark: 93, gpuRam: 400, speed: 10, vibe: 60, accent: '#10a37f' },
        { name: 'CogVideoX', company: 'THU', emoji: '📽️', params: 5, benchmark: 78, gpuRam: 14, speed: 25, vibe: 72, accent: '#e74c3c' },
    ];
    const STATS = [
        { key: 'params', label: 'Parameter (B)', icon: '🧠', higher: true, max: 3000 },
        { key: 'benchmark', label: 'Benchmark', icon: '📊', higher: true, max: 100 },
        { key: 'gpuRam', label: 'GPU RAM (GB)', icon: '💾', higher: false, max: 400 },
        { key: 'speed', label: 'Speed', icon: '⚡', higher: true, max: 100 },
        { key: 'vibe', label: 'Vibe Check', icon: '✨', higher: true, max: 100 },
    ];

    let playerHand = [], aileyHand = [], selectedStat = null, isPlayerTurn = true;

    function init() {
        const shuffled = [...DECK].sort(() => Math.random() - 0.5);
        const mid = Math.ceil(shuffled.length / 2);
        playerHand = shuffled.slice(0, mid); aileyHand = shuffled.slice(mid);
        selectedStat = null; isPlayerTurn = Math.random() > 0.5;
        Games.round = 1;
        Games.state = { type: 'quartett', playerHand, aileyHand, isPlayerTurn };
        Games.logEvent(`Quartett gestartet — ${playerHand.length} Karten, ${isPlayerTurn ? 'Spieler' : 'Ailey'} beginnt`);
        const fb = isPlayerTurn ? 'Du bist dran — wähl ne Kategorie! 🃏' : 'Ich fang an! Spoiler: du verlierst. 😏';
        Games.aileySays(fb);
        Games.requestAileyComment('game_start', { game: 'quartett', firstTurn: isPlayerTurn ? 'player' : 'ailey' });
        isPlayerTurn ? renderPlayerTurn() : aileyTurn();
    }
    function restore(s) {
        playerHand = s.playerHand || []; aileyHand = s.aileyHand || [];
        isPlayerTurn = s.isPlayerTurn ?? true;
        isPlayerTurn ? renderPlayerTurn() : aileyTurn();
    }

    function _cardHTML(card, showStats = true, clickable = false) {
        const barPct = (val, stat) => {
            const pct = stat.higher ? (val / stat.max * 100) : ((stat.max - val) / stat.max * 100);
            return Math.min(100, Math.max(5, pct));
        };
        return `
        <div class="quartett-card" style="--card-accent:${card.accent}">
            <div class="qcard-header">
                <div class="qcard-avatar">${card.emoji}</div>
                <div class="qcard-info">
                    <span class="qcard-name" style="color:${card.accent}">${card.name}</span>
                    <span class="qcard-company">${card.company}</span>
                </div>
            </div>
            ${showStats ? `<div class="qcard-stats">${STATS.map(s => `
                <${clickable ? 'button' : 'div'} class="qcard-stat ${selectedStat === s.key ? 'selected' : ''}"
                    ${clickable ? `onclick="Quartett.pickStat('${s.key}')"` : ''}>
                    <span class="qstat-icon">${s.icon}</span>
                    <span class="qstat-label">${s.label}</span>
                    <span class="qstat-value">${card[s.key]}</span>
                    <div class="qstat-bar"><div class="qstat-bar-fill" style="width:${barPct(card[s.key], s)}%"></div></div>
                </${clickable ? 'button' : 'div'}>
            `).join('')}</div>` : ''}
            <div class="qcard-footer">
                <span class="qcard-category">KI QUARTETT</span>
                <span class="qcard-number" style="color:${card.accent}">#${DECK.indexOf(card) + 1}</span>
            </div>
        </div>`;
    }

    function renderPlayerTurn() {
        if (!playerHand.length || !aileyHand.length) return checkWin();
        const card = playerHand[0];
        const board = document.getElementById('game-board');
        board.innerHTML = `
            <div class="quartett-layout">
                ${_cardHTML(card, true, true)}
                <div class="quartett-vs">⚡<br>VS</div>
                <div class="quartett-card face-down">
                    <div class="qcard-back"><img src="/assets/ailey-playful.jpg" alt="Ailey" style="width:40px;height:40px;border-radius:50%;object-fit:cover;margin-bottom:4px"><br>A!LEY<br><small>${aileyHand.length} Karten</small></div>
                </div>
            </div>
            <div class="quartett-info">Du hast <strong>${playerHand.length}</strong> Karten · Wähle eine Kategorie!</div>`;
        Games.setActionBtn('Kategorie wählen', false);
    }
    function pickStat(key) { if (!isPlayerTurn) return; selectedStat = key; renderPlayerTurn(); Games.setActionBtn('⚔️ Vergleichen!', true); }
    async function playerAction() { if (!selectedStat || !isPlayerTurn) return; await compareCards(selectedStat, true); }

    async function aileyTurn() {
        if (!aileyHand.length || !playerHand.length) return checkWin();
        Games.setActionBtn('Ailey wählt…', false);

        // Show Ailey's card face-down while she "thinks"
        const board = document.getElementById('game-board');
        board.innerHTML = `
            <div class="quartett-layout">
                <div class="quartett-card face-down">
                    <div class="qcard-back">👤<br>DU<br><small>${playerHand.length} Karten</small></div>
                </div>
                <div class="quartett-vs">🤔<br>Ailey denkt…</div>
                ${_cardHTML(aileyHand[0], false, false)}
            </div>
            <div class="quartett-info">Ailey wählt eine Kategorie…</div>`;

        // Give a visible pause so player can see something is happening
        await new Promise(r => setTimeout(r, 1200));

        const aileyCard = aileyHand[0];
        const move = await Games.requestAileyMove({ game: 'quartett', aileyCard, stats: STATS.map(s => s.key) });
        let chosenStat;
        if (move?.stat && STATS.find(s => s.key === move.stat)) {
            chosenStat = move.stat;
        } else {
            // Smart-random fallback: pick a stat where Ailey is above average, with some randomness
            // Don't always pick the absolute best → makes it more fair + unpredictable
            const statScores = STATS.map(s => {
                const val = s.higher ? aileyCard[s.key] : (s.max - aileyCard[s.key]);
                // Add randomness: ±20% jitter
                return { key: s.key, score: val * (0.8 + Math.random() * 0.4) };
            });
            statScores.sort((a, b) => b.score - a.score);
            // 50% chance pick top stat, 30% second, 20% random
            const roll = Math.random();
            if (roll < 0.5) chosenStat = statScores[0].key;
            else if (roll < 0.8) chosenStat = statScores[1].key;
            else chosenStat = statScores[Math.floor(Math.random() * statScores.length)].key;
        }
        selectedStat = chosenStat;
        const statLabel = STATS.find(s => s.key === chosenStat)?.label || chosenStat;
        Games.aileySays(`Ich wähle: ${statLabel}! 😎`);
        await new Promise(r => setTimeout(r, 600));
        await compareCards(chosenStat, false);
    }

    async function compareCards(statKey, playerChose) {
        const pCard = playerHand[0], aCard = aileyHand[0];
        const stat = STATS.find(s => s.key === statKey);
        const board = document.getElementById('game-board');
        board.innerHTML = `
            <div class="quartett-layout">
                ${_cardHTML(pCard, true, false)}
                <div class="quartett-vs">${stat.icon}<br>${stat.label}</div>
                ${_cardHTML(aCard, true, false)}
            </div>`;
        // Highlight compared stat
        board.querySelectorAll('.qcard-stat').forEach(el => {
            const label = el.querySelector('.qstat-label')?.textContent;
            if (label === stat.label) el.classList.add('highlight');
        });

        const pVal = pCard[statKey], aVal = aCard[statKey];
        let winner = stat.higher ? (pVal > aVal ? true : pVal < aVal ? false : null) : (pVal < aVal ? true : pVal > aVal ? false : null);
        Games.logEvent(`${playerChose ? 'Spieler' : 'Ailey'} wählt ${stat.label}: ${pCard.name}(${pVal}) vs ${aCard.name}(${aVal}) → ${winner === true ? 'Spieler' : winner === false ? 'Ailey' : 'Unentschieden'}`);
        await new Promise(r => setTimeout(r, 1500));

        // Show result banner
        let resultText, resultColor;
        if (winner === true) {
            Games.playerScore++; playerHand.push(playerHand.shift()); playerHand.push(aileyHand.shift());
            isPlayerTurn = true;
            resultText = `✅ Du gewinnst! ${pCard.name} (${pVal}) > ${aCard.name} (${aVal})`;
            resultColor = 'var(--np-green)';
        } else if (winner === false) {
            Games.aileyScore++; aileyHand.push(aileyHand.shift()); aileyHand.push(playerHand.shift());
            isPlayerTurn = false;
            resultText = `❌ Ailey gewinnt! ${aCard.name} (${aVal}) > ${pCard.name} (${pVal})`;
            resultColor = 'var(--np-pink)';
        } else {
            playerHand.push(playerHand.shift()); aileyHand.push(aileyHand.shift());
            // On draw, turn stays the same — whoever chose keeps choosing
            resultText = `🤝 Unentschieden! Beide ${pVal}`;
            resultColor = 'var(--np-cyan)';
        }

        // Show result overlay in board
        const resultBanner = document.createElement('div');
        resultBanner.className = 'quartett-result-banner';
        resultBanner.style.cssText = `color:${resultColor}`;
        resultBanner.innerHTML = `<div class="quartett-result-text">${resultText}</div>
            <div class="quartett-result-next">${isPlayerTurn ? '👉 Du bist dran!' : '<img src="/assets/ailey-grins.jpg" style="width:20px;height:20px;border-radius:50%;vertical-align:middle;margin-right:4px">Ailey ist dran…'} · Karten: Du ${playerHand.length} / Ailey ${aileyHand.length}</div>`;
        board.appendChild(resultBanner);

        Games.round++;
        Games.state = { type: 'quartett', playerHand, aileyHand, isPlayerTurn };
        await Games.saveState();
        if (!playerHand.length || !aileyHand.length) return checkWin();
        if (Games.round > 30) return checkWin();

        // Visible pause before next turn — longer if Ailey goes next so player sees what happened
        await new Promise(r => setTimeout(r, isPlayerTurn ? 1200 : 2000));
        isPlayerTurn ? renderPlayerTurn() : aileyTurn();
    }
    function checkWin() {
        if (!playerHand.length) Games.gameOver('loss');
        else if (!aileyHand.length) Games.gameOver('win');
        else if (Games.round > 30) Games.gameOver(Games.playerScore > Games.aileyScore ? 'win' : Games.playerScore < Games.aileyScore ? 'loss' : 'draw');
    }
    return { init, restore, pickStat, playerAction };
})();


/* ═══════════════════════════════════════════════════════════════════════════
   GAME 2: NEON DuCHESS — Real Chess + Factions + Chaos Cards
   ═══════════════════════════════════════════════════════════════════════════ */
const DuChess = (() => {
    const SIZE = 8;
    const PT = {
        K: { w: '♔', b: '♚', name: 'ICON',   val: 0  },
        Q: { w: '♕', b: '♛', name: 'ACE',    val: 9  },
        R: { w: '♖', b: '♜', name: 'TOWER',  val: 5  },
        B: { w: '♗', b: '♝', name: 'SLIDER', val: 3  },
        N: { w: '♘', b: '♞', name: 'JUMPER', val: 3  },
        P: { w: '♙', b: '♟', name: 'PAWN',   val: 1  },
    };

    /* ── Factions ──────────────────────────────────────────────────── */
    const FACTIONS = {
        vyrus:  { name: 'VYRUS',  color: '#9d4edd', emoji: '💜', motto: 'Ich bin der Bug in deinem System.' },
        chrome: { name: 'CHROME', color: '#00f7ff', emoji: '🩵', motto: 'Perfektion durch Design.' },
        riot:   { name: 'RIOT',   color: '#ff2d95', emoji: '💖', motto: 'Regeln sind Vorschläge.' },
        surge:  { name: 'SURGE',  color: '#f7ff00', emoji: '💛', motto: 'Zu schnell für deine Augen.' },
    };

    /* ── Chaos cards per faction ──────────────────────────────────── */
    const CHAOS_CARDS = [
        // Neutral
        { id: 'swap',       title: 'SWAP',        icon: '🔄', effect: 'Tausche Position zweier eigener Figuren.', faction: 'neutral' },
        { id: 'wild',       title: 'WILD CARD',   icon: '🃏', effect: 'Zufälliger Effekt — kann gut oder schlecht sein.', faction: 'neutral' },
        { id: 'timeJump',   title: 'ZEITSPRUNG',  icon: '⏱️', effect: 'Figur macht sofort noch einen Zug.', faction: 'neutral' },
        { id: 'deflect',    title: 'DEFLECT',     icon: '🛡️', effect: 'Verhindert Schlagen — Angreifer geht zurück.', faction: 'neutral' },
        { id: 'ghost',      title: 'GHOST MOVE',  icon: '👻', effect: 'Figur zieht durch andere Figuren.', faction: 'neutral' },
        { id: 'nothing',    title: 'DAMP SQUIB',  icon: '💨', effect: 'Nix passiert. Pech gehabt.', faction: 'neutral' },
        // VYRUS
        { id: 'crash',      title: 'SYSTEM CRASH',icon: '⚡', effect: 'Alle Figuren bewegen sich 1 Feld in zufällige Richtung (ICONs immun).', faction: 'vyrus' },
        { id: 'scramble',   title: 'SCRAMBLE',    icon: '🔀', effect: 'Gegner muss nächsten Zug mit zufälliger Figur machen.', faction: 'vyrus' },
        { id: 'backup',     title: 'BACKUP',      icon: '💾', effect: 'Geschlagener PAWN kehrt an Startposition zurück.', faction: 'vyrus' },
        { id: 'debug',      title: 'DEBUG',       icon: '🐛', effect: 'Schaue eine verdeckte Karte des Gegners an.', faction: 'vyrus' },
        { id: 'reboot',     title: 'REBOOT',      icon: '🖥️', effect: 'Setze eine Figur auf Startposition zurück.', faction: 'vyrus' },
        // CHROME
        { id: 'mirror',     title: 'MIRROR HACK', icon: '🪞', effect: 'Kopiere den letzten Zug des Gegners.', faction: 'chrome' },
        { id: 'upgrade',    title: 'UPGRADE',     icon: '🔧', effect: 'PAWN wird sofort zu SLIDER oder JUMPER.', faction: 'chrome' },
        { id: 'scan',       title: 'SCAN',        icon: '📡', effect: 'Alle gegnerischen Chaos-Karten werden aufgedeckt.', faction: 'chrome' },
        { id: 'repair',     title: 'REPAIR',      icon: '⚙️', effect: 'Geschlagene Figur kommt zurück (außer ACE).', faction: 'chrome' },
        { id: 'lockon',     title: 'LOCK-ON',     icon: '🎯', effect: 'Markiere gegnerische Figur — nächster Angriff unblockbar.', faction: 'chrome' },
        // RIOT
        { id: 'noise',      title: 'NOISE',       icon: '🔊', effect: 'Gegner muss nächsten Zug aussetzen (ICON darf fliehen).', faction: 'riot' },
        { id: 'molotov',    title: 'MOLOTOV',     icon: '💣', effect: 'Zerstöre alle Figuren auf einer Diagonale (außer ICONs).', faction: 'riot' },
        { id: 'stagedive',  title: 'STAGE DIVE',  icon: '🎸', effect: 'JUMPER springt beliebig weit und schlägt.', faction: 'riot' },
        { id: 'rally',      title: 'RALLY',       icon: '📢', effect: 'Alle eigenen PAWNs rücken ein Feld vor.', faction: 'riot' },
        { id: 'middlefing',  title: 'MIDDLE FINGER', icon: '🖕', effect: 'Kein mechanischer Effekt. Psychologische Kriegsführung.', faction: 'riot' },
        // SURGE
        { id: 'overclock',  title: 'OVERCLOCK',   icon: '🔌', effect: 'Figur macht 2 Züge, danach 1 Runde immobil.', faction: 'surge' },
        { id: 'chainlight', title: 'CHAIN LIGHTNING', icon: '⚡', effect: 'Bei Schlag: benachbarte Gegner werden auch getroffen.', faction: 'surge' },
        { id: 'blitz',      title: 'BLITZ',       icon: '💨', effect: 'ACE oder TOWER zieht doppelt so weit.', faction: 'surge' },
        { id: 'recharge',   title: 'RECHARGE',    icon: '🔋', effect: 'Ziehe 2 zusätzliche Chaos-Karten.', faction: 'surge' },
        { id: 'timebomb',   title: 'TIME BOMB',   icon: '⏰', effect: 'Unsichtbare Bombe — explodiert nach 3 Runden (3×3).', faction: 'surge' },
    ];

    /* ── State ────────────────────────────────────────────────────── */
    let board = [];
    let selected = null;
    let validMoves = [];
    let playerColor = 'w';
    let turn = 'w';
    let moveHistory = [];
    let capturedWhite = [];
    let capturedBlack = [];
    let enPassantTarget = null;
    let chaosOverlay = null;
    let frozenPieces = [];
    let shieldedPieces = [];
    let gameEnded = false;
    let playerFaction = null;
    let aileyFaction = null;
    let phase = 'faction_select'; // 'faction_select' | 'playing'

    /* ══════════════════════════════════════════════════════════════
       FACTION SELECT SCREEN
       ══════════════════════════════════════════════════════════════ */
    function init() {
        phase = 'faction_select';
        playerFaction = null;
        aileyFaction = null;
        gameEnded = false;
        _renderFactionSelect();
        Games.aileySays('Wähle deine Fraktion, Sterbliche*r! 💜');
        Games.setActionBtn('Fraktion wählen', false);
    }

    function _renderFactionSelect() {
        const boardEl = document.getElementById('game-board');
        let html = '<div class="duchess-faction-select">';
        html += '<h2 class="faction-title">♛ Neon DuCHESS</h2>';
        html += '<p class="faction-subtitle">Schach. Aber PUNK. — Wähle deine Fraktion:</p>';
        html += '<div class="faction-grid">';
        for (const [key, f] of Object.entries(FACTIONS)) {
            html += `<div class="faction-card" style="border-color:${f.color};--fc:${f.color}" onclick="DuChess.selectFaction('${key}')">
                <div class="faction-emoji">${f.emoji}</div>
                <div class="faction-name" style="color:${f.color}">${f.name}</div>
                <div class="faction-motto">"${f.motto}"</div>
            </div>`;
        }
        html += '</div></div>';
        boardEl.innerHTML = html;
    }

    function selectFaction(key) {
        playerFaction = key;
        // Ailey picks a different faction
        const others = Object.keys(FACTIONS).filter(k => k !== key);
        aileyFaction = others[Math.floor(Math.random() * others.length)];
        const pf = FACTIONS[playerFaction], af = FACTIONS[aileyFaction];
        Games.aileySays(`${pf.emoji} ${pf.name} vs ${af.emoji} ${af.name}? Let's go, bitch! 😈`);
        Games.requestAileyComment('game_start', { game: 'duchess', playerFaction, aileyFaction });
        // Start the actual game
        _startGame();
    }

    function _startGame() {
        phase = 'playing';
        board = _initialBoard();
        selected = null; validMoves = []; turn = 'w'; playerColor = 'w';
        moveHistory = []; capturedWhite = []; capturedBlack = [];
        enPassantTarget = null; chaosOverlay = null;
        frozenPieces = []; shieldedPieces = []; gameEnded = false;
        Games.round = 1;
        _assignChaosCards();
        Games.logEvent(`Neon DuCHESS: ${FACTIONS[playerFaction].name} vs ${FACTIONS[aileyFaction].name}`);
        _save(); render();
        Games.setActionBtn('Figur wählen', false);
    }

    function restore(s) {
        if (s.playerFaction) playerFaction = s.playerFaction;
        if (s.aileyFaction) aileyFaction = s.aileyFaction;
        board = s.board || _initialBoard(); turn = s.turn || 'w'; playerColor = s.playerColor || 'w';
        moveHistory = s.moveHistory || []; capturedWhite = s.capturedWhite || []; capturedBlack = s.capturedBlack || [];
        enPassantTarget = s.enPassantTarget || null; frozenPieces = s.frozenPieces || [];
        shieldedPieces = s.shieldedPieces || []; gameEnded = false;
        selected = null; validMoves = []; chaosOverlay = null; phase = 'playing';
        render(); Games.setActionBtn('Figur wählen', false);
    }

    /* ── Board setup ──────────────────────────────────────────────── */
    function _initialBoard() {
        const b = Array.from({ length: 8 }, () => Array(8).fill(null));
        const back = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R'];
        for (let c = 0; c < 8; c++) {
            b[0][c] = { piece: back[c], color: 'w', hasMoved: false, chaosCard: null, frozen: 0, shielded: false };
            b[1][c] = { piece: 'P', color: 'w', hasMoved: false, chaosCard: null, frozen: 0, shielded: false };
            b[6][c] = { piece: 'P', color: 'b', hasMoved: false, chaosCard: null, frozen: 0, shielded: false };
            b[7][c] = { piece: back[c], color: 'b', hasMoved: false, chaosCard: null, frozen: 0, shielded: false };
        }
        return b;
    }

    function _assignChaosCards() {
        // Weighted: player gets more cards from their faction, Ailey from hers
        const pCards = CHAOS_CARDS.filter(c => c.faction === playerFaction || c.faction === 'neutral');
        const aCards = CHAOS_CARDS.filter(c => c.faction === aileyFaction || c.faction === 'neutral');
        const shuffle = arr => [...arr].sort(() => Math.random() - 0.5);
        const pPool = shuffle(pCards), aPool = shuffle(aCards);
        let pi = 0, ai = 0;
        for (let r = 0; r < 8; r++)
            for (let c = 0; c < 8; c++)
                if (board[r][c]) {
                    if (board[r][c].color === 'w') { board[r][c].chaosCard = pPool[pi % pPool.length]; pi++; }
                    else { board[r][c].chaosCard = aPool[ai % aPool.length]; ai++; }
                }
    }

    /* ══════════════════════════════════════════════════════════════
       RENDER
       ══════════════════════════════════════════════════════════════ */
    function render() {
        const boardEl = document.getElementById('game-board');
        if (!boardEl || phase !== 'playing') return;
        const isFlipped = playerColor === 'b';
        const playerCap = playerColor === 'w' ? capturedBlack : capturedWhite;
        const aileyCap  = playerColor === 'w' ? capturedWhite : capturedBlack;
        const pMat = playerCap.reduce((s, p) => s + (PT[p]?.val || 0), 0);
        const aMat = aileyCap.reduce((s, p) => s + (PT[p]?.val || 0), 0);
        const diff = pMat - aMat;
        const pf = FACTIONS[playerFaction] || FACTIONS.vyrus;
        const af = FACTIONS[aileyFaction] || FACTIONS.chrome;

        let html = '<div class="duchess-board-wrapper">';
        // Header: faction vs faction
        html += `<div class="duchess-factions-bar">
            <span style="color:${pf.color}">${pf.emoji} ${pf.name}</span>
            <span class="vs-text">VS</span>
            <span style="color:${af.color}">${af.emoji} ${af.name}</span>
        </div>`;
        // Ailey captured tray
        html += `<div class="duchess-captured"><span class="captured-label"><img src="/assets/ailey-playful.jpg" style="width:18px;height:18px;border-radius:50%;vertical-align:middle;margin-right:4px">Ailey (${af.name}):</span>${aileyCap.map(p => `<span>${PT[p]?.b || '?'}</span>`).join('')}</div>`;
        // Info bar
        const inCheck = _isInCheck(turn);
        html += `<div class="duchess-info">
            <span>${turn === playerColor ? '🟢 Dein Zug' : '🔴 Aileys Zug'}</span>
            ${inCheck ? '<span class="neon-pink blink-text">⚠️ SCHACH!</span>' : ''}
            ${diff > 0 ? `<span class="neon-green">+${diff}</span>` : diff < 0 ? `<span class="neon-pink">${diff}</span>` : ''}
            <span>Zug ${Math.ceil(Games.round / 2)}</span>
        </div>`;
        // Board
        html += '<div class="duchess-board">';
        for (let ri = 7; ri >= 0; ri--) {
            const r = isFlipped ? 7 - ri : ri;
            for (let ci = 0; ci < 8; ci++) {
                const c = isFlipped ? 7 - ci : ci;
                const cell = board[r][c];
                const isDark = (r + c) % 2 === 0;
                const isSel = selected && selected.r === r && selected.c === c;
                const vm = validMoves.find(m => m.r === r && m.c === c);
                const isLast = moveHistory.length > 0 && (
                    (moveHistory[moveHistory.length - 1].to.r === r && moveHistory[moveHistory.length - 1].to.c === c) ||
                    (moveHistory[moveHistory.length - 1].from.r === r && moveHistory[moveHistory.length - 1].from.c === c)
                );
                let cls = `duchess-cell ${isDark ? 'dark' : 'light'}`;
                if (isSel) cls += ' selected';
                if (vm && !vm.capture) cls += ' valid-move';
                if (vm && vm.capture) cls += ' can-capture';
                if (isLast) cls += ' last-move';

                let content = '';
                if (cell) {
                    const icon = cell.color === 'w' ? PT[cell.piece].w : PT[cell.piece].b;
                    const fcol = cell.color === playerColor ? pf.color : af.color;
                    const frozenCls = cell.frozen > 0 ? 'frozen' : '';
                    const cardCls = cell.chaosCard ? 'has-card' : '';
                    content = `<span class="duchess-piece ${frozenCls} ${cardCls}" style="color:${fcol};text-shadow:0 0 8px ${fcol}">${icon}</span>`;
                }
                html += `<div class="${cls}" onclick="DuChess.click(${r},${c})">${content}</div>`;
            }
        }
        html += '</div>';
        // Player captured tray
        html += `<div class="duchess-captured"><span class="captured-label">👤 Du (${pf.name}):</span>${playerCap.map(p => `<span>${PT[p]?.w || '?'}</span>`).join('')}</div>`;
        html += '</div>';

        // Chaos card overlay
        if (chaosOverlay) {
            const fc = FACTIONS[chaosOverlay.faction] || { color: '#fff', name: chaosOverlay.faction };
            html += `<div class="chaos-card-overlay" onclick="DuChess.dismissChaos()">
                <div class="chaos-card" style="border-color:${fc.color}" onclick="event.stopPropagation()">
                    <div class="chaos-card-icon">${chaosOverlay.icon}</div>
                    <div class="chaos-card-title" style="color:${fc.color}">${chaosOverlay.title}</div>
                    <div class="chaos-card-faction">${fc.name || chaosOverlay.faction}</div>
                    <div class="chaos-card-effect">${chaosOverlay.effect}</div>
                    <button class="btn btn-primary btn-sm" onclick="DuChess.dismissChaos()" style="margin-top:1rem;width:100%">OK</button>
                </div>
            </div>`;
        }
        boardEl.innerHTML = html;
    }

    /* ══════════════════════════════════════════════════════════════
       MOVE GENERATION  —  NO RECURSION
       _rawAttacks: generates piece attacks WITHOUT legality/check
       _isSquareAttacked: uses _rawAttacks (no recursion)
       _isInCheck: uses _isSquareAttacked
       _pseudoLegalMoves: full moves incl. castling (calls _isInCheck)
       _getValidMoves: filters pseudo-legal to legal
       ══════════════════════════════════════════════════════════════ */

    /** Raw attack squares for a piece — does NOT call _isInCheck.
        Used for attack detection only (includes pawn diagonal attacks). */
    function _rawAttacks(r, c, cell, brd) {
        const atk = [];
        const color = cell.color;
        const enemy = color === 'w' ? 'b' : 'w';
        switch (cell.piece) {
            case 'P': {
                const dir = color === 'w' ? 1 : -1;
                for (const dc of [-1, 1]) {
                    const nr = r + dir, nc = c + dc;
                    if (_inBounds(nr, nc)) atk.push({ r: nr, c: nc });
                }
                break;
            }
            case 'N':
                for (const [dr, dc] of [[2,1],[2,-1],[-2,1],[-2,-1],[1,2],[1,-2],[-1,2],[-1,-2]]) {
                    const nr = r + dr, nc = c + dc;
                    if (_inBounds(nr, nc)) atk.push({ r: nr, c: nc });
                }
                break;
            case 'B': _addSlidingAttacks(r, c, [[1,1],[1,-1],[-1,1],[-1,-1]], atk, brd); break;
            case 'R': _addSlidingAttacks(r, c, [[1,0],[-1,0],[0,1],[0,-1]], atk, brd); break;
            case 'Q': _addSlidingAttacks(r, c, [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]], atk, brd); break;
            case 'K':
                for (const [dr, dc] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]]) {
                    const nr = r + dr, nc = c + dc;
                    if (_inBounds(nr, nc)) atk.push({ r: nr, c: nc });
                }
                break;
        }
        return atk;
    }

    function _addSlidingAttacks(r, c, dirs, atk, brd) {
        for (const [dr, dc] of dirs) {
            let nr = r + dr, nc = c + dc;
            while (_inBounds(nr, nc)) {
                atk.push({ r: nr, c: nc });
                if (brd[nr][nc]) break; // blocked
                nr += dr; nc += dc;
            }
        }
    }

    /** Is square (r,c) attacked by any piece of color `byColor`? NO RECURSION. */
    function _isSquareAttacked(r, c, byColor, brd = board) {
        for (let rr = 0; rr < 8; rr++)
            for (let cc = 0; cc < 8; cc++) {
                const cell = brd[rr][cc];
                if (!cell || cell.color !== byColor) continue;
                const attacks = _rawAttacks(rr, cc, cell, brd);
                if (attacks.some(a => a.r === r && a.c === c)) return true;
            }
        return false;
    }

    /** Is `color`'s king in check? */
    function _isInCheck(color, brd = board) {
        for (let r = 0; r < 8; r++)
            for (let c = 0; c < 8; c++)
                if (brd[r][c] && brd[r][c].piece === 'K' && brd[r][c].color === color)
                    return _isSquareAttacked(r, c, color === 'w' ? 'b' : 'w', brd);
        return false;
    }

    /** Full pseudo-legal moves (incl. castling). Castling calls _isInCheck which is safe now. */
    function _pseudoLegalMoves(r, c, cell) {
        const moves = [];
        const color = cell.color;
        const enemy = color === 'w' ? 'b' : 'w';
        switch (cell.piece) {
            case 'P': {
                const dir = color === 'w' ? 1 : -1;
                const startRow = color === 'w' ? 1 : 6;
                if (_inBounds(r + dir, c) && !board[r + dir][c])
                    moves.push({ r: r + dir, c, capture: false, type: (r + dir === 0 || r + dir === 7) ? 'promotion' : 'move' });
                if (r === startRow && !board[r + dir][c] && !board[r + 2 * dir][c])
                    moves.push({ r: r + 2 * dir, c, capture: false, type: 'move' });
                for (const dc of [-1, 1]) {
                    const nr = r + dir, nc = c + dc;
                    if (_inBounds(nr, nc)) {
                        if (board[nr][nc] && board[nr][nc].color === enemy)
                            moves.push({ r: nr, c: nc, capture: true, type: (nr === 0 || nr === 7) ? 'promotion' : 'capture' });
                        if (enPassantTarget && enPassantTarget.r === nr && enPassantTarget.c === nc)
                            moves.push({ r: nr, c: nc, capture: true, type: 'enpassant' });
                    }
                }
                break;
            }
            case 'N':
                for (const [dr, dc] of [[2,1],[2,-1],[-2,1],[-2,-1],[1,2],[1,-2],[-1,2],[-1,-2]]) {
                    const nr = r + dr, nc = c + dc;
                    if (_inBounds(nr, nc) && (!board[nr][nc] || board[nr][nc].color === enemy))
                        moves.push({ r: nr, c: nc, capture: !!board[nr][nc], type: board[nr][nc] ? 'capture' : 'move' });
                }
                break;
            case 'B': _addSliding(r, c, [[1,1],[1,-1],[-1,1],[-1,-1]], moves, enemy); break;
            case 'R': _addSliding(r, c, [[1,0],[-1,0],[0,1],[0,-1]], moves, enemy); break;
            case 'Q': _addSliding(r, c, [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]], moves, enemy); break;
            case 'K':
                for (const [dr, dc] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]]) {
                    const nr = r + dr, nc = c + dc;
                    if (_inBounds(nr, nc) && (!board[nr][nc] || board[nr][nc].color === enemy))
                        moves.push({ r: nr, c: nc, capture: !!board[nr][nc], type: board[nr][nc] ? 'capture' : 'move' });
                }
                // Castling — safe: _isInCheck uses _isSquareAttacked which uses _rawAttacks (no recursion)
                if (!cell.hasMoved && !_isInCheck(color)) {
                    const rkR = board[r][7];
                    if (rkR && rkR.piece === 'R' && !rkR.hasMoved && !board[r][5] && !board[r][6])
                        if (!_isSquareAttacked(r, 5, enemy) && !_isSquareAttacked(r, 6, enemy))
                            moves.push({ r, c: 6, capture: false, type: 'castle', rookFrom: 7, rookTo: 5 });
                    const rkQ = board[r][0];
                    if (rkQ && rkQ.piece === 'R' && !rkQ.hasMoved && !board[r][1] && !board[r][2] && !board[r][3])
                        if (!_isSquareAttacked(r, 2, enemy) && !_isSquareAttacked(r, 3, enemy))
                            moves.push({ r, c: 2, capture: false, type: 'castle', rookFrom: 0, rookTo: 3 });
                }
                break;
        }
        return moves;
    }

    function _addSliding(r, c, dirs, moves, enemy) {
        for (const [dr, dc] of dirs) {
            let nr = r + dr, nc = c + dc;
            while (_inBounds(nr, nc)) {
                if (!board[nr][nc]) { moves.push({ r: nr, c: nc, capture: false, type: 'move' }); }
                else {
                    if (board[nr][nc].color === enemy) moves.push({ r: nr, c: nc, capture: true, type: 'capture' });
                    break;
                }
                nr += dr; nc += dc;
            }
        }
    }

    function _inBounds(r, c) { return r >= 0 && r < 8 && c >= 0 && c < 8; }

    function _getValidMoves(r, c) {
        const cell = board[r][c];
        if (!cell) return [];
        const moves = _pseudoLegalMoves(r, c, cell);
        return moves.filter(m => {
            const sim = _simulateMove(r, c, m.r, m.c);
            return !_isInCheck(cell.color, sim);
        });
    }

    function _simulateMove(fr, fc, tr, tc, brd = board) {
        const sim = brd.map(row => row.map(cell => cell ? { ...cell } : null));
        sim[tr][tc] = sim[fr][fc];
        sim[fr][fc] = null;
        return sim;
    }

    function _isCheckmate(color) {
        for (let r = 0; r < 8; r++)
            for (let c = 0; c < 8; c++)
                if (board[r][c] && board[r][c].color === color && _getValidMoves(r, c).length > 0)
                    return false;
        return _isInCheck(color);
    }
    function _isStalemate(color) {
        for (let r = 0; r < 8; r++)
            for (let c = 0; c < 8; c++)
                if (board[r][c] && board[r][c].color === color && _getValidMoves(r, c).length > 0)
                    return false;
        return !_isInCheck(color);
    }

    /* ══════════════════════════════════════════════════════════════
       CLICK + EXECUTE MOVE
       ══════════════════════════════════════════════════════════════ */
    function click(r, c) {
        if (gameEnded || turn !== playerColor || chaosOverlay || phase !== 'playing') return;
        const vm = validMoves.find(m => m.r === r && m.c === c);
        if (selected && vm) { _executeMove(selected.r, selected.c, r, c, vm); return; }
        const cell = board[r][c];
        if (cell && cell.color === playerColor) {
            if (cell.frozen > 0) { Games.aileySays('Die Figur ist eingefroren! 🧊'); return; }
            selected = { r, c };
            validMoves = _getValidMoves(r, c);
            render();
            Games.setActionBtn(`${PT[cell.piece].name} bewegen`, false);
            return;
        }
        selected = null; validMoves = []; render();
    }

    async function _executeMove(fr, fc, tr, tc, moveInfo) {
        const piece = board[fr][fc];
        const captured = board[tr][tc];
        let chaosTriggered = null;

        // En passant
        if (moveInfo.type === 'enpassant') {
            const epR = piece.color === 'w' ? tr - 1 : tr + 1;
            const epCap = board[epR][tc];
            if (epCap) {
                (epCap.color === 'w' ? capturedWhite : capturedBlack).push(epCap.piece);
                board[epR][tc] = null;
            }
        }
        // Normal capture
        if (captured) {
            (captured.color === 'w' ? capturedWhite : capturedBlack).push(captured.piece);
            if (piece.chaosCard) { chaosTriggered = piece.chaosCard; piece.chaosCard = null; }
        }
        // Castling
        if (moveInfo.type === 'castle') {
            board[fr][moveInfo.rookTo] = board[fr][moveInfo.rookFrom];
            board[fr][moveInfo.rookFrom] = null;
            if (board[fr][moveInfo.rookTo]) board[fr][moveInfo.rookTo].hasMoved = true;
        }
        // Move
        board[tr][tc] = piece; board[fr][fc] = null; piece.hasMoved = true;
        // En passant tracking
        enPassantTarget = null;
        if (piece.piece === 'P' && Math.abs(tr - fr) === 2) enPassantTarget = { r: (fr + tr) / 2, c: fc };
        // Promotion
        if (piece.piece === 'P' && (tr === 0 || tr === 7)) {
            piece.piece = 'Q';
            if (piece.chaosCard) { chaosTriggered = piece.chaosCard; piece.chaosCard = null; }
        }
        // Check → trigger chaos
        const enemy = piece.color === 'w' ? 'b' : 'w';
        if (!chaosTriggered && _isInCheck(enemy) && piece.chaosCard) {
            chaosTriggered = piece.chaosCard; piece.chaosCard = null;
        }

        moveHistory.push({ from: { r: fr, c: fc }, to: { r: tr, c: tc }, piece: piece.piece, captured: captured?.piece, chaos: chaosTriggered?.id });

        // Decrement frozen
        for (let r = 0; r < 8; r++)
            for (let c = 0; c < 8; c++)
                if (board[r][c] && board[r][c].frozen > 0) board[r][c].frozen--;
        // Clear shields
        for (let r = 0; r < 8; r++)
            for (let c = 0; c < 8; c++)
                if (board[r][c]) board[r][c].shielded = false;

        selected = null; validMoves = [];

        // Show chaos card
        if (chaosTriggered) {
            chaosOverlay = chaosTriggered;
            render();
            _applyChaosEffect(chaosTriggered, piece.color);
            await _waitForChaosDismiss();
        }

        // Score
        if (captured) {
            if (piece.color === playerColor) Games.playerScore += (PT[captured.piece]?.val || 1);
            else Games.aileyScore += (PT[captured.piece]?.val || 1);
        }

        Games.round++; _save(); render();

        // Endgame
        if (_isCheckmate(enemy)) {
            gameEnded = true;
            Games.gameOver(piece.color === playerColor ? 'win' : 'loss');
            return;
        }
        if (_isStalemate(enemy)) {
            gameEnded = true; Games.gameOver('draw'); return;
        }

        turn = enemy; render();
        if (turn !== playerColor) await _aileyMove();
        else Games.setActionBtn('Figur wählen', false);
    }

    /* ══════════════════════════════════════════════════════════════
       AILEY AI
       ══════════════════════════════════════════════════════════════ */
    async function _aileyMove() {
        Games.setActionBtn('Ailey denkt…', false);
        Games.aileySays(Games._randomPick(['Hmm… 🤔', 'Lass mich überlegen… 🧠', 'Moment… ♟️']));

        const boardFEN = _boardToFEN();
        const move = await Games.requestAileyMove({
            game: 'duchess', boardFEN, turn: 'black',
            moveHistory: moveHistory.slice(-10).map(m => `${_sq(m.from.r, m.from.c)}-${_sq(m.to.r, m.to.c)}`),
            inCheck: _isInCheck('b'),
        });

        let executed = false;
        if (move?.from && move?.to) {
            const fr = _parseSquare(move.from), tr = _parseSquare(move.to);
            if (fr && tr && board[fr.r]?.[fr.c]?.color === 'b') {
                const lm = _getValidMoves(fr.r, fr.c).find(m => m.r === tr.r && m.c === tr.c);
                if (lm) { await _executeMove(fr.r, fr.c, tr.r, tr.c, lm); executed = true; }
            }
        }
        // Smart fallback
        if (!executed) {
            const allMoves = [];
            for (let r = 0; r < 8; r++)
                for (let c = 0; c < 8; c++)
                    if (board[r][c]?.color === 'b')
                        _getValidMoves(r, c).forEach(m => allMoves.push({ fr: r, fc: c, ...m }));
            if (allMoves.length === 0) {
                gameEnded = true; Games.gameOver(_isInCheck('b') ? 'win' : 'draw'); return;
            }
            const scored = allMoves.map(m => {
                let s = Math.random() * 0.5;
                if (m.capture && board[m.r]?.[m.c]) s += (PT[board[m.r][m.c].piece]?.val || 1) * 2;
                if (board[m.fr]?.[m.fc]?.piece === 'K' && !_isInCheck('b')) s -= 1;
                if (m.r >= 3 && m.r <= 4 && m.c >= 2 && m.c <= 5) s += 0.5;
                const sim = _simulateMove(m.fr, m.fc, m.r, m.c);
                if (_isInCheck('w', sim)) s += 3;
                return { ...m, s };
            });
            scored.sort((a, b) => b.s - a.s);
            const pick = scored.slice(0, Math.min(3, scored.length))[Math.floor(Math.random() * Math.min(3, scored.length))];
            Games.aileySays(Games._randomPick(['Autopilot! 💜', 'Random vibes! 🎲', 'Bauchgefühl! ⚡']));
            await new Promise(r => setTimeout(r, 400));
            await _executeMove(pick.fr, pick.fc, pick.r, pick.c, pick);
        }
    }

    /* ── Chaos effects ────────────────────────────────────────────── */
    function _applyChaosEffect(card, color) {
        const enemy = color === 'w' ? 'b' : 'w';
        switch (card.id) {
            case 'crash': {
                const dirs = [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]];
                const toMove = [];
                for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++)
                    if (board[r][c] && board[r][c].piece !== 'K') toMove.push({r, c});
                for (const {r, c} of toMove) {
                    const d = dirs[Math.floor(Math.random() * dirs.length)];
                    const nr = r + d[0], nc = c + d[1];
                    if (_inBounds(nr, nc) && !board[nr][nc]) { board[nr][nc] = board[r][c]; board[r][c] = null; }
                }
                break;
            }
            case 'backup': case 'resurrect': {
                const caps = color === 'w' ? capturedWhite : capturedBlack;
                const pi = caps.indexOf('P');
                if (pi >= 0) {
                    const row = color === 'w' ? 1 : 6;
                    for (let c = 0; c < 8; c++) {
                        if (!board[row][c]) {
                            board[row][c] = { piece: 'P', color, hasMoved: false, chaosCard: null, frozen: 0, shielded: false };
                            caps.splice(pi, 1); break;
                        }
                    }
                }
                break;
            }
            case 'freeze': {
                const ep = [];
                for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++)
                    if (board[r][c]?.color === enemy && board[r][c].piece !== 'K') ep.push({r, c});
                if (ep.length) {
                    const t = ep[Math.floor(Math.random() * ep.length)];
                    board[t.r][t.c].frozen = 2;
                }
                break;
            }
            case 'timeJump': case 'overclock': case 'extraTurn':
                if (color === playerColor) turn = playerColor; else turn = color;
                break;
            case 'upgrade': {
                for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++)
                    if (board[r][c]?.piece === 'P' && board[r][c].color === color) {
                        board[r][c].piece = Math.random() > 0.5 ? 'B' : 'N'; return;
                    }
                break;
            }
            case 'scan': {
                // Reveal all enemy chaos cards (mark as revealed — visual only)
                for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++)
                    if (board[r][c]?.color === enemy && board[r][c].chaosCard) board[r][c].chaosCard._revealed = true;
                break;
            }
            case 'rally': {
                const dir = color === 'w' ? 1 : -1;
                for (let r = (dir > 0 ? 6 : 1); dir > 0 ? r >= 0 : r < 8; r -= dir)
                    for (let c = 0; c < 8; c++)
                        if (board[r][c]?.piece === 'P' && board[r][c].color === color) {
                            const nr = r + dir;
                            if (_inBounds(nr, c) && !board[nr][c]) { board[nr][c] = board[r][c]; board[r][c] = null; }
                        }
                break;
            }
            case 'noise':
                // Skip opponent turn — handled by not switching turn after this
                if (color === playerColor) turn = playerColor; else turn = color;
                break;
            default:
                // nothing, middlefing, wild, ghost, deflect, debug, mirror, etc. — flavor only
                break;
        }
    }

    let chaosResolve = null;
    function _waitForChaosDismiss() { return new Promise(resolve => { chaosResolve = resolve; }); }
    function dismissChaos() {
        chaosOverlay = null; render();
        if (chaosResolve) { const r = chaosResolve; chaosResolve = null; r(); }
    }

    /* ── Helpers ──────────────────────────────────────────────────── */
    function _sq(r, c) { return 'abcdefgh'[c] + (r + 1); }
    function _parseSquare(s) {
        if (!s || s.length < 2) return null;
        const c = 'abcdefgh'.indexOf(s[0].toLowerCase());
        const r = parseInt(s[1]) - 1;
        return _inBounds(r, c) ? { r, c } : null;
    }
    function _boardToFEN() {
        let fen = '';
        for (let r = 7; r >= 0; r--) {
            let empty = 0;
            for (let c = 0; c < 8; c++) {
                const cell = board[r][c];
                if (!cell) { empty++; }
                else {
                    if (empty > 0) { fen += empty; empty = 0; }
                    const ch = cell.piece === 'N' ? 'N' : cell.piece[0];
                    fen += cell.color === 'w' ? ch.toUpperCase() : ch.toLowerCase();
                }
            }
            if (empty > 0) fen += empty;
            if (r > 0) fen += '/';
        }
        return fen;
    }
    function _save() {
        Games.state = {
            type: 'duchess', board, turn, playerColor,
            moveHistory, capturedWhite, capturedBlack,
            enPassantTarget, frozenPieces, shieldedPieces,
            playerFaction, aileyFaction
        };
    }
    function playerAction() { /* handled by click */ }

    return { init, restore, click, dismissChaos, playerAction, selectFaction };
})();


/* ═══════════════════════════════════════════════════════════════════════════
   GAME 3: SERVER DDOS — Terminal Hacker Battleship
   ═══════════════════════════════════════════════════════════════════════════ */
const ServerDDOS = (() => {
    const GRID = 8;
    const SHIPS = [
        { id: 'lb', name: 'Load Balancer', size: 4, icon: '⚖️' },
        { id: 'db', name: 'Database', size: 3, icon: '🗄️' },
        { id: 'api', name: 'API Gateway', size: 3, icon: '🔌' },
        { id: 'ms', name: 'Microservice', size: 2, icon: '📦' },
        { id: 'dns', name: 'DNS Server', size: 1, icon: '🌐' },
    ];

    let playerGrid = [], aileyGrid = [], playerAttacks = [], aileyAttacks = [];
    let placingShip = null, placingDir = 'h', placedShips = [];
    let phase = 'placing', playerHits = 0, aileyHits = 0, totalCells = 0;
    let terminalLog = [];

    function init() {
        playerGrid = _empty(); aileyGrid = _empty();
        playerAttacks = _empty(); aileyAttacks = _empty();
        placedShips = []; playerHits = 0; aileyHits = 0;
        totalCells = SHIPS.reduce((s, sh) => s + sh.size, 0);
        phase = 'placing'; placingShip = 0; terminalLog = [];
        _autoPlace(aileyGrid);
        _log('system', 'SERVER DDOS v2.0 — Neon Punk Edition');
        _log('system', `Platziere deine ${SHIPS.length} Server-Cluster.`);
        Games.logEvent('Server DDOS gestartet — 8×8 Grid, 5 Server-Cluster');
        Games.aileySays('Pack deine Server aufs Grid, bitch! 🕵️');
        Games.requestAileyComment('game_start', { game: 'server_ddos' });
        renderPlacing();
    }
    function restore(s) {
        playerGrid = s.playerGrid || _empty(); aileyGrid = s.aileyGrid || _empty();
        playerAttacks = s.playerAttacks || _empty(); aileyAttacks = s.aileyAttacks || _empty();
        placedShips = s.placedShips || []; playerHits = s.playerHits || 0; aileyHits = s.aileyHits || 0;
        totalCells = SHIPS.reduce((s2, sh) => s2 + sh.size, 0);
        phase = s.phase || 'placing'; terminalLog = s.terminalLog || [];
        phase === 'placing' ? (placingShip = placedShips.length, renderPlacing()) : renderBattle();
    }

    function _empty() { return Array.from({ length: GRID }, () => Array(GRID).fill(0)); }
    function _log(type, text) { terminalLog.push({ type, text }); if (terminalLog.length > 50) terminalLog = terminalLog.slice(-40); }

    function _autoPlace(grid) {
        SHIPS.forEach((ship, idx) => {
            let placed = false, tries = 0;
            while (!placed && tries < 100) {
                tries++;
                const dir = Math.random() > 0.5 ? 'h' : 'v';
                const sx = Math.floor(Math.random() * (dir === 'h' ? GRID - ship.size + 1 : GRID));
                const sy = Math.floor(Math.random() * (dir === 'v' ? GRID - ship.size + 1 : GRID));
                let fits = true;
                for (let i = 0; i < ship.size; i++) {
                    const cx = dir === 'h' ? sx + i : sx, cy = dir === 'v' ? sy + i : sy;
                    if (grid[cy][cx] !== 0) { fits = false; break; }
                }
                if (fits) {
                    for (let i = 0; i < ship.size; i++) {
                        const cx = dir === 'h' ? sx + i : sx, cy = dir === 'v' ? sy + i : sy;
                        grid[cy][cx] = idx + 1;
                    }
                    placed = true;
                }
            }
        });
    }

    function _terminalHTML() {
        if (!terminalLog.length) return '';
        const lines = terminalLog.slice(-8).map(l => {
            const cls = l.type === 'success' ? 'success' : l.type === 'error' ? 'error' : l.type === 'ailey' ? 'ailey' : 'prompt';
            return `<div class="terminal-line"><span class="${cls}">${l.type === 'system' ? '>' : l.type === 'ailey' ? 'A!>' : '$'}</span> ${Games._esc(l.text)}</div>`;
        }).join('');
        return `<div class="terminal-output">${lines}</div>`;
    }

    function renderPlacing() {
        if (placingShip >= SHIPS.length) {
            phase = 'battle';
            _log('success', 'Alle Server online. Battle beginnt!');
            Games.logEvent('Alle Server platziert — Battle beginnt!');
            Games.aileySays('Server online! DDOS my shit — if you can! 💥');
            Games.requestAileyComment('battle_start', { game: 'server_ddos' });
            renderBattle(); return;
        }
        const ship = SHIPS[placingShip];
        const board = document.getElementById('game-board');
        board.innerHTML = `
            <div class="ddos-terminal">
                <div class="terminal-header">
                    <div class="terminal-dots"><span class="terminal-dot red"></span><span class="terminal-dot yellow"></span><span class="terminal-dot green"></span></div>
                    <div class="terminal-title">server_deploy.sh — Platzierung</div>
                </div>
                <div class="ddos-placing" style="padding:1rem">
                    <h3>Deploy: ${ship.icon} ${ship.name} (${ship.size} Nodes)</h3>
                    <p style="color:rgba(255,255,255,0.5);font-size:0.75rem;margin:0.5rem 0">
                        <button class="btn btn-ghost btn-sm" onclick="ServerDDOS.toggleDir()">↻ ${placingDir === 'h' ? 'Horizontal' : 'Vertikal'}</button>
                    </p>
                    <div class="ddos-grid">${_renderGrid(playerGrid, true, false)}</div>
                </div>
                ${_terminalHTML()}
            </div>`;
        Games.setActionBtn(`${ship.icon} ${ship.name} platzieren`, false);
    }

    function renderBattle() {
        const board = document.getElementById('game-board');
        board.innerHTML = `
            <div class="ddos-terminal">
                <div class="terminal-header">
                    <div class="terminal-dots"><span class="terminal-dot red"></span><span class="terminal-dot yellow"></span><span class="terminal-dot green"></span></div>
                    <div class="terminal-title">ddos_attack.sh — Battle Mode</div>
                </div>
                <div class="ddos-battle" style="padding:0.8rem">
                    <div class="ddos-side">
                        <h3>🎯 Aileys Netzwerk</h3>
                        <div class="ddos-grid">${_renderGrid(playerAttacks, false, true)}</div>
                        <div class="ddos-ships-status">${_shipStatus(playerAttacks, aileyGrid)}</div>
                    </div>
                    <div class="ddos-side">
                        <h3>🛡️ Dein Netzwerk</h3>
                        <div class="ddos-grid">${_renderGrid(playerGrid, false, false, aileyAttacks)}</div>
                        <div class="ddos-ships-status">${_shipStatus(aileyAttacks, playerGrid)}</div>
                    </div>
                </div>
                ${_terminalHTML()}
            </div>`;
        Games.setActionBtn('Wähle ein Ziel', false);
    }

    function _renderGrid(grid, isPlacing, isAttackable, overlay = null) {
        const L = 'ABCDEFGH';
        let h = '<div class="ddos-grid-inner"><div class="ddos-cell ddos-header"></div>';
        for (let x = 0; x < GRID; x++) h += `<div class="ddos-cell ddos-header">${x + 1}</div>`;
        for (let y = 0; y < GRID; y++) {
            h += `<div class="ddos-cell ddos-header">${L[y]}</div>`;
            for (let x = 0; x < GRID; x++) {
                const v = grid[y][x];
                let cls = 'ddos-cell', content = '';
                if (isPlacing) {
                    if (v > 0) { cls += ' ddos-ship'; content = SHIPS[v - 1]?.icon || '█'; }
                    cls += ' ddos-placeable';
                } else if (isAttackable) {
                    if (v === 'hit') { cls += ' ddos-hit'; content = '💥'; }
                    else if (v === 'miss') { cls += ' ddos-miss'; content = '·'; }
                    else cls += ' ddos-fog';
                } else {
                    if (v > 0) {
                        if (overlay?.[y][x] === 'hit') { cls += ' ddos-hit'; content = '💥'; }
                        else { cls += ' ddos-ship'; content = SHIPS[v - 1]?.icon || '█'; }
                    } else if (overlay?.[y][x] === 'miss') { cls += ' ddos-miss'; content = '·'; }
                }
                const onclick = isPlacing ? `ServerDDOS.placeClick(${x},${y})` : isAttackable ? `ServerDDOS.attackClick(${x},${y})` : '';
                h += `<div class="${cls}" onclick="${onclick}">${content}</div>`;
            }
        }
        return h + '</div>';
    }

    function _shipStatus(attacks, targetGrid) {
        return SHIPS.map((ship, idx) => {
            let total = 0, hit = 0;
            for (let y = 0; y < GRID; y++) for (let x = 0; x < GRID; x++)
                if (targetGrid[y][x] === idx + 1) { total++; if (attacks[y][x] === 'hit') hit++; }
            return `<span class="ship-status ${total > 0 && hit >= total ? 'sunk' : ''}">${ship.icon} ${hit >= total && total > 0 ? '✕' : `${hit}/${total}`}</span>`;
        }).join(' ');
    }

    function toggleDir() { placingDir = placingDir === 'h' ? 'v' : 'h'; renderPlacing(); }

    function placeClick(x, y) {
        if (placingShip >= SHIPS.length) return;
        const ship = SHIPS[placingShip];
        for (let i = 0; i < ship.size; i++) {
            const cx = placingDir === 'h' ? x + i : x, cy = placingDir === 'v' ? y + i : y;
            if (cx >= GRID || cy >= GRID || playerGrid[cy][cx] !== 0) {
                _log('error', `Deployment fehlgeschlagen — Kollision!`);
                renderPlacing(); return;
            }
        }
        for (let i = 0; i < ship.size; i++) {
            const cx = placingDir === 'h' ? x + i : x, cy = placingDir === 'v' ? y + i : y;
            playerGrid[cy][cx] = placingShip + 1;
        }
        placedShips.push({ id: ship.id, x, y, dir: placingDir });
        _log('success', `${ship.icon} ${ship.name} deployed at ${_coord(x, y)}`);
        placingShip++;
        _saveState(); renderPlacing();
    }

    async function attackClick(x, y) {
        if (phase !== 'battle') return;
        if (playerAttacks[y][x] !== 0) {
            _log('error', `${_coord(x, y)}: Bereits angegriffen! Wähle ein anderes Ziel.`);
            Games.aileySays('Da war ich schon, du Noob! 😂');
            renderBattle();
            // Flash the cell to show it's already attacked
            const cells = document.querySelectorAll('.ddos-side:first-child .ddos-cell');
            const idx = (y + 1) * (GRID + 1) + (x + 1); // account for headers
            if (cells[idx]) { cells[idx].classList.add('ddos-already-flash'); setTimeout(() => cells[idx]?.classList.remove('ddos-already-flash'), 600); }
            return;
        }

        Games.round++;
        const coord = _coord(x, y);
        if (aileyGrid[y][x] > 0) {
            playerAttacks[y][x] = 'hit'; playerHits++; Games.playerScore += 10;
            const shipId = aileyGrid[y][x];
            let st = 0, sh = 0;
            for (let sy = 0; sy < GRID; sy++) for (let sx = 0; sx < GRID; sx++)
                if (aileyGrid[sy][sx] === shipId) { st++; if (playerAttacks[sy][sx] === 'hit') sh++; }
            if (sh >= st) {
                Games.playerScore += 25;
                const name = SHIPS[shipId - 1].name;
                _log('success', `💥 ${name} DESTROYED at ${coord}!`);
                Games.logEvent(`Spieler versenkt ${name}! (${playerHits}/${totalCells})`);
                Games.requestAileyComment('ship_sunk', { sunkShip: name, playerHits, totalCells });
            } else {
                _log('success', `HIT at ${coord}!`);
                Games.logEvent(`Treffer bei ${coord} (${playerHits}/${totalCells})`);
            }
            if (playerHits >= totalCells) { _saveState(); renderBattle(); Games.gameOver('win'); return; }
        } else {
            playerAttacks[y][x] = 'miss';
            _log('error', `MISS at ${coord} — Wasser.`);
            Games.logEvent(`Wasser bei ${coord}`);
        }
        renderBattle(); _saveState();

        // Ailey's turn
        Games.setActionBtn('Ailey greift an…', false);
        await new Promise(r => setTimeout(r, 800));
        const at = await _getAileyAttack();
        if (at) {
            const { ax, ay } = at;
            const ac = _coord(ax, ay);
            if (playerGrid[ay][ax] > 0) {
                aileyAttacks[ay][ax] = 'hit'; aileyHits++; Games.aileyScore += 10;
                const sid = playerGrid[ay][ax];
                let st2 = 0, sh2 = 0;
                for (let sy = 0; sy < GRID; sy++) for (let sx = 0; sx < GRID; sx++)
                    if (playerGrid[sy][sx] === sid) { st2++; if (aileyAttacks[sy][sx] === 'hit') sh2++; }
                if (sh2 >= st2) { Games.aileyScore += 25; _log('ailey', `💥 Ailey destroyed your ${SHIPS[sid-1].name}!`); Games.logEvent(`Ailey versenkt ${SHIPS[sid-1].name}!`); }
                else { _log('ailey', `Ailey HIT at ${ac}!`); Games.logEvent(`Ailey trifft ${ac}`); }
                if (aileyHits >= totalCells) { _saveState(); renderBattle(); Games.gameOver('loss'); return; }
            } else { aileyAttacks[ay][ax] = 'miss'; _log('ailey', `Ailey MISS at ${ac}`); Games.logEvent(`Ailey: Wasser bei ${ac}`); }
        }
        _saveState(); renderBattle(); Games.setActionBtn('Wähle ein Ziel', false);
    }

    async function _getAileyAttack() {
        // Don't send full grid to LLM — just a summary, and only if fast
        const hitCount = aileyHits;
        const totalAttacks = aileyAttacks.flat().filter(v => v !== 0).length;
        const move = await Games.requestAileyMove({
            game: 'server_ddos',
            hitsSoFar: hitCount,
            totalAttacks,
            gridSize: GRID,
        });
        // Validate LLM move: must be single coord, in bounds, not already attacked
        if (move && typeof move.x === 'number' && typeof move.y === 'number'
            && move.x >= 0 && move.x < GRID && move.y >= 0 && move.y < GRID
            && aileyAttacks[move.y][move.x] === 0)
            return { ax: move.x, ay: move.y };

        // ── Smart Hunt/Target fallback ──
        // 1) TARGET mode: if there are un-sunk hits, attack adjacent cells
        const unSunkHits = [];
        for (let y = 0; y < GRID; y++) for (let x = 0; x < GRID; x++) {
            if (aileyAttacks[y][x] === 'hit') {
                // Check if this hit's ship is fully sunk
                const shipId = playerGrid[y][x];
                if (shipId > 0) {
                    let total = 0, hitCt = 0;
                    for (let sy = 0; sy < GRID; sy++) for (let sx = 0; sx < GRID; sx++)
                        if (playerGrid[sy][sx] === shipId) { total++; if (aileyAttacks[sy][sx] === 'hit') hitCt++; }
                    if (hitCt < total) unSunkHits.push({ x, y });
                }
            }
        }
        if (unSunkHits.length) {
            // Try to follow the line of adjacent hits
            const cands = [];
            for (const h of unSunkHits) {
                for (const [dx, dy] of [[0,1],[0,-1],[1,0],[-1,0]]) {
                    const nx = h.x + dx, ny = h.y + dy;
                    if (nx >= 0 && nx < GRID && ny >= 0 && ny < GRID && aileyAttacks[ny][nx] === 0)
                        cands.push({ ax: nx, ay: ny });
                }
            }
            if (cands.length) return cands[Math.floor(Math.random() * cands.length)];
        }

        // 2) HUNT mode: checkerboard pattern for efficiency (every other cell)
        const huntCells = [];
        for (let y = 0; y < GRID; y++) for (let x = 0; x < GRID; x++)
            if (aileyAttacks[y][x] === 0 && (x + y) % 2 === 0) huntCells.push({ ax: x, ay: y });
        if (huntCells.length) return huntCells[Math.floor(Math.random() * huntCells.length)];

        // 3) Fallback: any open cell
        const open = [];
        for (let y = 0; y < GRID; y++) for (let x = 0; x < GRID; x++)
            if (aileyAttacks[y][x] === 0) open.push({ ax: x, ay: y });
        return open.length ? open[Math.floor(Math.random() * open.length)] : null;
    }

    function _coord(x, y) { return 'ABCDEFGH'[y] + (x + 1); }
    function _saveState() {
        Games.state = { type: 'server_ddos', playerGrid, aileyGrid, playerAttacks, aileyAttacks, placedShips, playerHits, aileyHits, phase, terminalLog };
    }
    function playerAction() {}
    return { init, restore, toggleDir, placeClick, attackClick, playerAction };
})();


// ═══ AUTO-INIT ══════════════════════════════════════════════════════════
// Catch any uncaught errors and show them in the debug overlay
window.addEventListener('error', (e) => {
    _dbg.log(`UNCAUGHT ERROR: ${e.message} at ${e.filename}:${e.lineno}:${e.colno}`);
});
window.addEventListener('unhandledrejection', (e) => {
    _dbg.log(`UNHANDLED PROMISE: ${e.reason?.message || e.reason || 'unknown'}`);
});
_dbg.log('games.js loaded OK');
document.addEventListener('DOMContentLoaded', () => {
    _dbg.log('DOMContentLoaded → Games.init()');
    Games.init();
});