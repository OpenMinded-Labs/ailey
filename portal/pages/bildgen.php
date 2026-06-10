<?php
/**
 * A!ley Portal — Bild-Generierung (eigene Unterseite)
 */
require_once __DIR__ . '/layout.php';
portal_head('Bild-Gen');
$userName = htmlspecialchars($user['display_name'] ?? 'User');
?>

<div class="gen-page">
    <div class="gen-page-inner">

        <!-- Hero Header -->
        <div class="gen-page-header">
            <div class="gen-page-icon"><?= icon('wand-2') ?></div>
            <h1>Bild generieren</h1>
            <p>
                Beschreibe dein Bild — Ailey übersetzt und generiert es mit MFLUX.
                <span id="img-quota-display" class="quota-badge" style="margin-left:0.3rem;"></span>
            </p>
        </div>

        <!-- Access Gate (shown until tool access confirmed) -->
        <div id="access-gate" class="gen-access-gate" style="display:none;">
            <div class="gen-access-icon">🔒</div>
            <h3>Kein Zugriff</h3>
            <p>Du hast aktuell keinen Zugriff auf die Bildgenerierung. Frag Ailey im Chat — vielleicht schaltet sie es für dich frei!</p>
            <a href="/chat" class="btn btn-primary"><?= icon('message-circle') ?> Zum Chat</a>
        </div>

        <!-- Main Tool Area (shown when access granted) -->
        <div id="gen-tool" style="display:none;">

            <div class="gen-card">
                <div class="form-group">
                    <label>Prompt</label>
                    <textarea id="imagegen-prompt" class="form-input" rows="3" placeholder="z.B. Cyberpunk-Stadt bei Nacht, neonbeleuchtete Gassen…"></textarea>
                </div>

                <div class="tool-settings-row">
                    <div class="form-group">
                        <label>Format</label>
                        <select id="imagegen-ar" class="form-input">
                            <option value="1:1">1:1 (Quadrat)</option>
                            <option value="16:9">16:9 (Quer)</option>
                            <option value="9:16">9:16 (Hoch)</option>
                            <option value="4:3">4:3</option>
                            <option value="3:4">3:4</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Steps: <span id="imagegen-steps-val">9</span></label>
                        <input type="range" id="imagegen-steps" min="1" max="12" value="9" class="form-input"
                               oninput="document.getElementById('imagegen-steps-val').textContent=this.value">
                    </div>
                </div>

                <label class="selfie-label">
                    <input type="checkbox" id="imagegen-selfie"> Ailey-Selfie (mit LoRA)
                </label>

                <!-- LoRA Style Selector -->
                <div id="lora-selector" class="lora-selector" style="display:none;">
                    <label class="form-label">🎨 LoRA-Stile <small class="text-muted">(max. 2 gleichzeitig)</small></label>
                    <div id="lora-buttons" class="lora-buttons"></div>
                </div>

                <button class="btn-generate" id="imagegen-submit" onclick="BildGen.generate()">
                    <?= icon('wand-2') ?> Bild generieren
                </button>

                <div class="tool-gen-status" id="imagegen-status">
                    <div class="spinner"></div>
                    <p id="imagegen-status-text">Wird generiert…</p>
                </div>

                <div class="tool-gen-result" id="imagegen-result">
                    <img id="imagegen-result-img" alt="Generated Image" onclick="BildGen.openLightbox(this.src, '', document.getElementById('imagegen-result-prompt').textContent)">
                    <p id="imagegen-result-prompt" class="result-caption"></p>
                </div>
            </div>

            <!-- Gallery of previous generations -->
            <div class="gen-section">
                <h2>Deine Bilder</h2>
                <div id="imagegen-gallery" class="gen-image-gallery"></div>
            </div>

        </div>
    </div>
</div>

<!-- Generation Lightbox -->
<div id="gen-lightbox" class="gen-lightbox" onclick="BildGen.closeLightbox(event)">
    <div class="gen-lightbox-content">
        <button class="gen-lightbox-close" onclick="BildGen.closeLightbox()" title="Schließen">✕</button>
        <img id="gen-lightbox-img" src="" alt="Generated Image">
    </div>
    <div class="gen-lightbox-info">
        <div id="gen-lightbox-title" class="lb-title"></div>
        <div id="gen-lightbox-prompt" class="lb-prompt"></div>
    </div>
    <div class="gen-lightbox-actions">
        <a id="gen-lightbox-dl" href="" download title="Herunterladen">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Download
        </a>
        <button onclick="BildGen.openInNewTab()" title="In neuem Tab öffnen">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            Neuer Tab
        </button>
    </div>
</div>

<script>
const BildGen = {
    _currentLightboxUrl: '',
    _availableLoras: {},
    _selectedLoras: [],

    async init() {
        try {
            const res = await fetch('/api.php?action=my_tools');
            const data = await res.json();
            if (!data.success || !(data.tools || {}).image_gen) {
                document.getElementById('access-gate').style.display = '';
                return;
            }
            document.getElementById('gen-tool').style.display = '';
            // Update V$ display
            const vInfo = data.vdollars;
            if (vInfo) {
                const el = document.getElementById('img-quota-display');
                if (el) el.innerHTML = '<span class="quota-badge">💰 ' + Math.floor(vInfo.balance) + ' V$ (15 V$/Bild)</span>';
            }
            this.loadGallery();
            this.loadLoras();
        } catch (e) {
            console.warn('[BildGen] init failed:', e);
            document.getElementById('access-gate').style.display = '';
        }
    },

    async loadLoras() {
        try {
            const res = await fetch('/api.php?action=available_loras');
            const data = await res.json();
            if (!data.success || !data.loras) return;
            this._availableLoras = data.loras;
            const ids = Object.keys(data.loras);
            if (ids.length === 0) return;
            const container = document.getElementById('lora-buttons');
            container.innerHTML = ids.map(id => {
                const info = data.loras[id];
                const emoji = id === 'realism' ? '📷' : id === 'anime' ? '🎌' : '✨';
                return `<button type="button" class="lora-btn" data-lora="${id}" onclick="BildGen.toggleLora('${id}')">
                    <span class="lora-btn-name">${emoji} ${id.charAt(0).toUpperCase() + id.slice(1)}</span>
                    <span class="lora-btn-desc">${info.description || ''}</span>
                </button>`;
            }).join('');
            document.getElementById('lora-selector').style.display = '';
        } catch (e) { console.warn('[BildGen] loadLoras:', e); }
    },

    toggleLora(id) {
        const idx = this._selectedLoras.indexOf(id);
        if (idx >= 0) {
            this._selectedLoras.splice(idx, 1);
        } else {
            if (this._selectedLoras.length >= 2) return;
            this._selectedLoras.push(id);
        }
        document.querySelectorAll('.lora-btn').forEach(btn => {
            const lid = btn.dataset.lora;
            const sel = this._selectedLoras.includes(lid);
            btn.classList.toggle('active', sel);
            btn.classList.toggle('disabled', !sel && this._selectedLoras.length >= 2);
        });
    },

    async generate() {
        const prompt = document.getElementById('imagegen-prompt').value.trim();
        if (!prompt) return;

        const ar = document.getElementById('imagegen-ar').value;
        const steps = parseInt(document.getElementById('imagegen-steps').value);
        const selfie = document.getElementById('imagegen-selfie').checked;

        const btn = document.getElementById('imagegen-submit');
        btn.disabled = true;
        btn.textContent = '⏳ Wird in die Warteschlange gestellt…';
        document.getElementById('imagegen-status').style.display = '';
        document.getElementById('imagegen-status-text').textContent = 'Wird an Ailey gesendet…';
        document.getElementById('imagegen-result').style.display = 'none';

        try {
            const res = await fetch('/api.php?action=generate_image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt, aspect_ratio: ar, steps, ailey_selfie: selfie, lora_ids: BildGen._selectedLoras.length > 0 ? BildGen._selectedLoras : undefined })
            });
            const data = await res.json();
            if (data.error) {
                document.getElementById('imagegen-status-text').textContent = '❌ ' + (data.message || data.error);
                this._resetButton();
                return;
            }
            document.getElementById('imagegen-status-text').textContent = 'Ailey generiert dein Bild… (kann 2-5 Minuten dauern)';
            this._poll(data.queue_id);
        } catch (e) {
            document.getElementById('imagegen-status-text').textContent = '❌ Netzwerkfehler: ' + e.message;
            this._resetButton();
        }
    },

    async _poll(queueId) {
        const statusEl = document.getElementById('imagegen-status-text');
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
                    document.getElementById('imagegen-status').style.display = 'none';
                    this._resetButton();
                    if (job.image_url) {
                        const resultDiv = document.getElementById('imagegen-result');
                        document.getElementById('imagegen-result-img').src = job.image_url;
                        document.getElementById('imagegen-result-prompt').textContent = job.reply || '';
                        resultDiv.style.display = '';
                        this.loadGallery();
                    } else {
                        statusEl.textContent = '✅ ' + (job.reply || 'Fertig!');
                        document.getElementById('imagegen-status').style.display = '';
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
                statusEl.textContent = 'Ailey generiert dein Bild' + dots;
                setTimeout(doPoll, 5000);
            } catch (e) {
                console.warn('[BildGen] poll error:', e);
                setTimeout(doPoll, 5000);
            }
        };
        setTimeout(doPoll, 3000);
    },

    _resetButton() {
        const btn = document.getElementById('imagegen-submit');
        btn.disabled = false;
        btn.innerHTML = '<?= icon("wand-2") ?> Bild generieren';
    },

    async loadGallery() {
        try {
            const res = await fetch('/api.php?action=my_generations&type=image');
            const data = await res.json();
            if (!data.success) return;
            const gallery = document.getElementById('imagegen-gallery');
            if (data.generations.length === 0) {
                gallery.innerHTML = '<p style="font-size:0.8rem;color:var(--muted-foreground);grid-column:1/-1;">Noch keine Bilder generiert.</p>';
                return;
            }
            gallery.innerHTML = data.generations.map(g => `
                <div class="gen-image-item" onclick="BildGen.openLightbox('${g.file_url}','${this._esc((g.title || '').replace(/'/g,"&#39;"))}','${this._esc((g.prompt || '').replace(/'/g,"&#39;").substring(0, 200))}')">
                    <img src="${g.file_url}" alt="${this._esc(g.title || '')}" loading="lazy">
                    <div class="gen-image-title">${this._esc((g.title || '').substring(0, 40))}</div>
                    <div class="gen-image-actions">
                        <button onclick="event.stopPropagation();BildGen._downloadFile('${g.file_url}','${this._esc(g.title || 'bild')}.png')" title="Download">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                        </button>
                    </div>
                </div>
            `).join('');
        } catch (e) { console.warn('[BildGen] loadGallery:', e); }
    },

    openLightbox(url, title, prompt) {
        this._currentLightboxUrl = url;
        document.getElementById('gen-lightbox-img').src = url;
        document.getElementById('gen-lightbox-title').textContent = title || '';
        document.getElementById('gen-lightbox-prompt').textContent = prompt || '';
        document.getElementById('gen-lightbox-dl').href = url;
        document.getElementById('gen-lightbox-dl').download = (title || 'generated-image') + '.png';
        document.getElementById('gen-lightbox').classList.add('visible');
        document.body.style.overflow = 'hidden';
    },

    closeLightbox(e) {
        if (e && e.target !== e.currentTarget) return;
        document.getElementById('gen-lightbox').classList.remove('visible');
        document.body.style.overflow = '';
    },

    openInNewTab() {
        if (this._currentLightboxUrl) window.open(this._currentLightboxUrl, '_blank');
    },

    _downloadFile(url, filename) {
        const a = document.createElement('a');
        a.href = url; a.download = filename;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
    },

    _esc(s) {
        const el = document.createElement('span');
        el.textContent = s || '';
        return el.innerHTML;
    },
};

BildGen.init();
</script>

<?php portal_footer(); ?>
