<?php
/**
 * A!ley Portal — Song-Generierung (eigene Unterseite)
 */
require_once __DIR__ . '/layout.php';
portal_head('Song-Gen');
$userName = htmlspecialchars($user['display_name'] ?? 'User');
?>

<div class="gen-page">
    <div class="gen-page-inner">

        <!-- Hero Header -->
        <div class="gen-page-header">
            <div class="gen-page-icon"><?= icon('disc-3') ?></div>
            <h1>Song generieren</h1>
            <p>
                Schreibe Lyrics + Genre-Tags — Ailey generiert mit ACE-Step v1.5.
                <span id="song-quota-display" class="quota-badge" style="margin-left:0.3rem;"></span>
            </p>
        </div>

        <!-- Access Gate -->
        <div id="access-gate" class="gen-access-gate" style="display:none;">
            <div class="gen-access-icon">🔒</div>
            <h3>Kein Zugriff</h3>
            <p>Du hast aktuell keinen Zugriff auf die Songgenerierung. Frag Ailey im Chat — vielleicht schaltet sie es für dich frei!</p>
            <a href="/chat" class="btn btn-primary"><?= icon('message-circle') ?> Zum Chat</a>
        </div>

        <!-- Main Tool Area -->
        <div id="gen-tool" style="display:none;">

            <div class="gen-card">
                <div class="form-group">
                    <label>Titel <span style="opacity:0.55;font-size:0.82em;">(optional)</span></label>
                    <input id="songgen-title" class="form-input" placeholder="z.B. Neon Bloodlines" maxlength="120" />
                </div>

                <div class="form-group">
                    <label>Genre / Tags</label>
                    <input id="songgen-tags" class="form-input" placeholder="z.B. grunge, electric guitar, female vocal, raw energy" />
                </div>

                <div class="form-group">
                    <label>Lyrics</label>
                    <textarea id="songgen-lyrics" class="form-input" rows="10" placeholder="[Verse 1]&#10;Deine Lyrics hier…&#10;&#10;[Chorus]&#10;…" style="font-family:monospace;font-size:0.85rem;"></textarea>
                </div>

                <div class="tool-settings-row">
                    <div class="form-group">
                        <label>Dauer: <span id="songgen-dur-val">180</span>s</label>
                        <input type="range" id="songgen-duration" min="30" max="480" value="180" step="10" class="form-input"
                               oninput="document.getElementById('songgen-dur-val').textContent=this.value">
                    </div>
                    <div class="form-group">
                        <label>Steps: <span id="songgen-steps-val">20</span></label>
                        <input type="range" id="songgen-steps" min="4" max="30" value="20" class="form-input"
                               oninput="document.getElementById('songgen-steps-val').textContent=this.value">
                    </div>
                </div>

                <button class="btn-generate" id="songgen-submit" onclick="SongGen.generate()">
                    <?= icon('disc-3') ?> Song generieren
                </button>

                <div class="tool-gen-status" id="songgen-status">
                    <div class="spinner"></div>
                    <p id="songgen-status-text">Wird generiert…</p>
                </div>

                <div class="tool-gen-result" id="songgen-result">
                    <audio id="songgen-result-audio" controls></audio>
                    <p id="songgen-result-title" class="result-caption"></p>
                </div>
            </div>

            <!-- Previous songs -->
            <div class="gen-section">
                <h2>Deine Songs</h2>
                <!-- Genre filter sub-nav -->
                <div id="songgen-genre-filter" class="song-genre-filter" style="display:none;"></div>
                <div id="songgen-list" class="gen-song-list"></div>
                <!-- Pagination -->
                <nav id="songgen-pagination" class="song-pagination" style="display:none;"></nav>
            </div>

        </div>
    </div>
</div>

<script>
const SongGen = {

    _allSongs: [],
    _filteredSongs: [],
    _genres: [],
    _activeGenre: null,
    _page: 1,
    _perPage: 12,

    async init() {
        try {
            const res = await fetch('/api.php?action=my_tools');
            const data = await res.json();
            if (!data.success || !(data.tools || {}).song_gen) {
                document.getElementById('access-gate').style.display = '';
                return;
            }
            document.getElementById('gen-tool').style.display = '';
            // Update V$ display
            const vInfo = data.vdollars;
            if (vInfo) {
                const el = document.getElementById('song-quota-display');
                if (el) el.innerHTML = '<span class="quota-badge">💰 ' + Math.floor(vInfo.balance) + ' V$ (30 V$/Song)</span>';
            }
            this.loadSongs();
        } catch (e) {
            console.warn('[SongGen] init failed:', e);
            document.getElementById('access-gate').style.display = '';
        }
    },

    async generate() {
        const lyrics = document.getElementById('songgen-lyrics').value.trim();
        if (!lyrics) return;

        const title = document.getElementById('songgen-title').value.trim();
        const tags = document.getElementById('songgen-tags').value.trim();
        const duration = parseInt(document.getElementById('songgen-duration').value);
        const steps = parseInt(document.getElementById('songgen-steps').value);

        const btn = document.getElementById('songgen-submit');
        btn.disabled = true;
        btn.textContent = '⏳ Wird in die Warteschlange gestellt…';
        document.getElementById('songgen-status').style.display = '';
        document.getElementById('songgen-status-text').textContent = 'Wird an Ailey gesendet…';
        document.getElementById('songgen-result').style.display = 'none';

        try {
            const res = await fetch('/api.php?action=generate_song', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lyrics, title, tags, duration, steps })
            });
            const data = await res.json();
            if (data.error) {
                document.getElementById('songgen-status-text').textContent = '❌ ' + (data.message || data.error);
                this._resetButton();
                return;
            }
            document.getElementById('songgen-status-text').textContent = 'Ailey generiert deinen Song… (kann 1-5 Minuten dauern)';
            this._poll(data.queue_id);
        } catch (e) {
            document.getElementById('songgen-status-text').textContent = '❌ Netzwerkfehler: ' + e.message;
            this._resetButton();
        }
    },

    async _poll(queueId) {
        const statusEl = document.getElementById('songgen-status-text');
        let polls = 0;
        const maxPolls = 120;

        const doPoll = async () => {
            if (polls++ > maxPolls) {
                statusEl.textContent = '⏰ Timeout — bitte überprüfe deine Generierungen später.';
                this._resetButton();
                return;
            }
            try {
                const res = await fetch('/api.php?action=generation_status&queue_id=' + encodeURIComponent(queueId));
                const data = await res.json();
                if (!data.success || !data.job) {
                    statusEl.textContent = '❌ Job nicht gefunden';
                    this._resetButton();
                    return;
                }
                const job = data.job;
                if (job.status === 'done') {
                    document.getElementById('songgen-status').style.display = 'none';
                    this._resetButton();
                    if (job.image_url) {
                        const resultDiv = document.getElementById('songgen-result');
                        document.getElementById('songgen-result-audio').src = job.image_url;
                        document.getElementById('songgen-result-title').textContent = job.reply || 'Song fertig!';
                        resultDiv.style.display = '';
                        this.loadSongs();
                    } else {
                        statusEl.textContent = '✅ ' + (job.reply || 'Fertig!');
                        document.getElementById('songgen-status').style.display = '';
                    }
                    this.init(); // refresh quota
                    return;
                }
                if (job.status === 'failed') {
                    statusEl.textContent = '❌ ' + (job.reply || 'Generierung fehlgeschlagen');
                    this._resetButton();
                    return;
                }
                const dots = '.'.repeat((polls % 3) + 1);
                statusEl.textContent = 'Ailey generiert deinen Song' + dots;
                setTimeout(doPoll, 5000);
            } catch (e) {
                console.warn('[SongGen] poll error:', e);
                setTimeout(doPoll, 5000);
            }
        };
        setTimeout(doPoll, 3000);
    },

    _resetButton() {
        const btn = document.getElementById('songgen-submit');
        btn.disabled = false;
        btn.innerHTML = '<?= icon("disc-3") ?> Song generieren';
    },

    async loadSongs() {
        try {
            const res = await fetch('/api.php?action=my_generations&type=song');
            const data = await res.json();
            if (!data.success) return;
            this._allSongs = data.generations || [];
            this._extractGenres();
            this._renderGenreFilter();
            this._applyFilter();
        } catch (e) { console.warn('[SongGen] loadSongs:', e); }
    },

    _extractGenres() {
        const genreSet = new Set();
        this._allSongs.forEach(g => {
            const prompt = (g.prompt || g.title || '').toLowerCase();
            // Extract comma-separated tags from prompt
            prompt.split(',').forEach(t => {
                const tag = t.trim();
                if (tag && tag.length > 1 && tag.length < 40) genreSet.add(tag);
            });
        });
        // Sort alphabetically, limit to top genres by frequency
        const freq = {};
        this._allSongs.forEach(g => {
            const prompt = (g.prompt || g.title || '').toLowerCase();
            prompt.split(',').forEach(t => {
                const tag = t.trim();
                if (tag && genreSet.has(tag)) freq[tag] = (freq[tag] || 0) + 1;
            });
        });
        this._genres = Object.entries(freq)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 30)
            .map(e => e[0]);
    },

    _renderGenreFilter() {
        const container = document.getElementById('songgen-genre-filter');
        if (this._allSongs.length < 2 || this._genres.length < 2) {
            container.style.display = 'none';
            return;
        }
        container.style.display = '';
        let html = '<button class="song-genre-tag' + (!this._activeGenre ? ' active' : '') + '" onclick="SongGen._setGenre(null)">Alle</button>';
        this._genres.forEach(g => {
            const active = this._activeGenre === g ? ' active' : '';
            html += '<button class="song-genre-tag' + active + '" onclick="SongGen._setGenre(\'' + this._esc(g).replace(/'/g, "\\'") + '\')">' + this._esc(g) + '</button>';
        });
        container.innerHTML = html;
    },

    _setGenre(genre) {
        this._activeGenre = genre;
        this._page = 1;
        this._renderGenreFilter();
        this._applyFilter();
    },

    _applyFilter() {
        if (this._activeGenre) {
            this._filteredSongs = this._allSongs.filter(g => {
                const prompt = (g.prompt || g.title || '').toLowerCase();
                return prompt.split(',').map(t => t.trim()).includes(this._activeGenre);
            });
        } else {
            this._filteredSongs = this._allSongs;
        }
        this._renderSongs();
        this._renderPagination();
    },

    _renderSongs() {
        const list = document.getElementById('songgen-list');
        const songs = this._filteredSongs;
        if (songs.length === 0) {
            list.innerHTML = '<p style="font-size:0.8rem;color:var(--muted-foreground);">' +
                (this._activeGenre ? 'Keine Songs für diesen Filter.' : 'Noch keine Songs generiert.') + '</p>';
            return;
        }
        const start = (this._page - 1) * this._perPage;
        const pageItems = songs.slice(start, start + this._perPage);
        list.innerHTML = pageItems.map(g => `
            <div class="gen-song-item">
                <div class="song-title">${this._esc(g.title || 'Song')}</div>
                <div class="song-tags">${this._esc((g.prompt || '').substring(0, 120))}</div>
                ${g.file_url ? '<audio controls src="' + g.file_url + '"></audio>' : '<span style="font-size:0.75rem;color:var(--muted-foreground);">Kein Audio</span>'}
                ${g.file_url ? '<div class="song-actions"><a class="song-dl-btn" href="' + g.file_url + '" download="' + this._esc(g.title || 'song') + '.wav"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download</a></div>' : ''}
            </div>
        `).join('');
    },

    _renderPagination() {
        const nav = document.getElementById('songgen-pagination');
        const total = this._filteredSongs.length;
        const totalPages = Math.ceil(total / this._perPage);
        if (totalPages <= 1) { nav.style.display = 'none'; return; }
        nav.style.display = '';
        let html = '';
        if (this._page > 1) {
            html += '<button class="btn btn-secondary song-page-btn" onclick="SongGen._goPage(' + (this._page - 1) + ')">‹ Zurück</button>';
        }
        html += '<span class="pagination-info">Seite ' + this._page + ' / ' + totalPages + ' (' + total + ' Songs)</span>';
        if (this._page < totalPages) {
            html += '<button class="btn btn-secondary song-page-btn" onclick="SongGen._goPage(' + (this._page + 1) + ')">Weiter ›</button>';
        }
        nav.innerHTML = html;
    },

    _goPage(p) {
        this._page = p;
        this._renderSongs();
        this._renderPagination();
        document.getElementById('songgen-list').scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    _esc(s) {
        const el = document.createElement('span');
        el.textContent = s || '';
        return el.innerHTML;
    },
};

SongGen.init();
</script>

<?php portal_footer(); ?>
