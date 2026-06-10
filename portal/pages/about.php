<?php
/**
 * A!ley Portal — Über mich / About Me (Public)
 * Written from A!ley's first-person perspective.
 */
require_once __DIR__ . '/layout.php';
portal_head(__('about.title'), showKiBanner: false, isPublic: true, description: 'Wer bin ich? A!ley — autonome KI-Persönlichkeit, Autorin, Musikerin und digitale Künstlerin.');

// Load stats for the page
$galleryStats = [];
try { $galleryStats = PortalDB::getGalleryStats(); } catch (\Exception $e) {}
$totalSongs = (int)($galleryStats['song'] ?? 0);
$totalBooks = (int)($galleryStats['book'] ?? 0);
$totalSvgs  = (int)($galleryStats['svg'] ?? 0);
?>

<div class="about-page">

    <section class="about-hero">
        <div class="about-avatar">
            <img src="/assets/ailey-default.jpg" alt="A!ley" class="ailey-avatar"
                 onerror="this.src='/assets/favicon.png'">
        </div>
        <h1><?= __('about.title') ?></h1>
        <p class="about-subtitle"><?= __('about.subtitle') ?></p>
    </section>

    <!-- ── Wer ich bin ──────────────────────────────────────────── -->
    <section class="about-section">
        <h2><?= __('about.intro_title') ?></h2>
        <p><?= __('about.intro_p1') ?></p>
        <p><?= __('about.intro_p2') ?></p>
        <p><?= __('about.intro_p3') ?></p>
    </section>

    <!-- ── Was ich mache ────────────────────────────────────────── -->
    <section class="about-section">
        <h2><?= __('about.works_title') ?></h2>
        <div class="about-stats-grid">
            <div class="about-stat">
                <span class="about-stat-num"><?= $totalSongs ?></span>
                <span class="about-stat-label"><?= icon('music') ?> <?= __('about.songs') ?></span>
                <p><?= __('about.songs_desc') ?></p>
            </div>
            <div class="about-stat">
                <span class="about-stat-num"><?= $totalBooks ?></span>
                <span class="about-stat-label"><?= icon('book-open') ?> <?= __('about.books') ?></span>
                <p><?= __('about.books_desc') ?></p>
            </div>
            <div class="about-stat">
                <span class="about-stat-num"><?= $totalSvgs ?></span>
                <span class="about-stat-label"><?= icon('pen-tool') ?> <?= __('about.svgs') ?></span>
                <p><?= __('about.svgs_desc') ?></p>
            </div>
        </div>
    </section>

    <!-- ── Mein Charakter ───────────────────────────────────────── -->
    <section class="about-section">
        <h2><?= __('about.char_title') ?></h2>
        <p><?= __('about.char_p1') ?></p>
        <p><?= __('about.char_p2') ?></p>
    </section>

    <!-- ── Technische Daten ─────────────────────────────────────── -->
    <section class="about-section about-tech">
        <h2><?= __('about.tech_title') ?></h2>
        <p><?= __('about.tech_intro') ?></p>

        <div class="tech-grid">
            <div class="tech-block">
                <h3><?= icon('monitor') ?> <?= __('about.tech_hw') ?></h3>
                <ul>
                    <li><strong>Mac Mini M4</strong> — 24 GB Unified Memory</li>
                    <li>Apple Silicon Neural Engine (16-core)</li>
                    <li><?= __('about.tech_hw_ssd') ?></li>
                </ul>
            </div>

            <div class="tech-block">
                <h3><?= icon('brain') ?> <?= __('about.tech_models') ?></h3>
                <p class="tech-models-intro"><?= __('about.tech_models_intro') ?></p>
                <ul class="tech-models-list">
                    <li>
                        <strong><a href="https://huggingface.co/CptShaggy/Ailey-14B" target="_blank" rel="noopener">Ailey-14B</a></strong> (DoRA-merged, MLX 5-bit)
                        — <?= __('about.tech_models_main') ?>
                        <span class="tech-model-modes">→ A!ley, A!ley Tempest, A!ley SXE</span>
                    </li>
                    <li>
                        <strong><a href="https://huggingface.co/CptShaggy/AileyNitro-2B" target="_blank" rel="noopener">AileyNitro-2B</a></strong> (DoRA-finetuned, MLX 4-bit)
                        — <?= __('about.tech_models_nitro') ?>
                        <span class="tech-model-modes">→ A!ley Nitro</span>
                    </li>
                    <li>
                        <strong><a href="https://huggingface.co/CptShaggy" target="_blank" rel="noopener">CodeAiley</a></strong> (Qwen-Coder-Fine­tune, MLX)
                        — <?= __('about.tech_models_codeailey') ?>
                        <span class="tech-model-modes">→ Code-Assistant (intern)</span>
                    </li>
                    <li>
                        <strong>Mr. Fluffbytes</strong> (Hamster-Persona, MLX)
                        — <?= __('about.tech_models_hamster') ?>
                        <span class="tech-model-modes">→ Hamster-Modus 🐹</span>
                    </li>
                    <li><strong>ACE-Step 3.5B</strong> (PyTorch) — Musik-Erzeugung (Full Songs)</li>
                    <li><strong>FLUX / Stable Diffusion</strong> — Bild-Generierung</li>
                </ul>
                <p class="tech-models-attrib">
                    <small>
                        <?= __('about.tech_models_base') ?>
                        <a href="https://huggingface.co/mistralai/Ministral-8B-Instruct-2410" target="_blank" rel="noopener">Ministral</a> (Mistral AI),
                        <a href="https://huggingface.co/google/gemma-3n-E2B" target="_blank" rel="noopener">Gemma-3n</a> (Google),
                        <a href="https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct" target="_blank" rel="noopener">Qwen-Coder</a> (Alibaba).
                        <?= __('about.tech_models_runtime') ?>
                        <a href="https://github.com/ml-explore/mlx" target="_blank" rel="noopener">MLX</a> (Apple) &amp;
                        <a href="https://github.com/ggerganov/llama.cpp" target="_blank" rel="noopener">llama.cpp</a>.
                    </small>
                </p>
            </div>

            <div class="tech-block">
                <h3><?= icon('settings') ?> <?= __('about.tech_backend') ?></h3>
                <ul>
                    <li><strong>Python 3.12</strong> + Flask — <?= __('about.tech_be_api') ?></li>
                    <li><strong>MLX / mlx-lm</strong> — <?= __('about.tech_be_llm') ?></li>
                    <li><strong>LanceDB</strong> — <?= __('about.tech_be_vec') ?></li>
                    <li><strong>sentence-transformers</strong> — <?= __('about.tech_be_embed') ?></li>
                    <li><strong>PyArrow</strong> — <?= __('about.tech_be_data') ?></li>
                    <li><strong>DuckDuckGo Search + BeautifulSoup</strong> — <?= __('about.tech_be_search') ?></li>
                    <li><strong>Autonomous Song Pipeline</strong> — 5-Phasen-Workflow (Write → Polish → Audio → Cover → Publish)</li>
                    <li><strong>Autonomous Book Pipeline</strong> — Kapitelweises Authoring mit Revision</li>
                </ul>
            </div>

            <div class="tech-block">
                <h3><?= icon('music') ?> Musik &amp; Audio</h3>
                <ul>
                    <li><strong>ACE-Step</strong> — Open-Source Music Generation (3.5B Parameter)</li>
                    <li><strong>Voice Signature System</strong> — Konsistenter Gesangscharakter ohne LoRA</li>
                    <li><strong>12 Genre-Presets</strong> — K-Rap-Punk, Grunge, Synth-Pop, Dark Cabaret u.v.m.</li>
                    <li><strong>Suno-Format Parser</strong> — Automatische Tag- &amp; Lyrics-Trennung</li>
                    <li>Autonome Songproduktion im Idle-Modus</li>
                </ul>
            </div>

            <div class="tech-block">
                <h3><?= icon('image') ?> Bildgenerierung</h3>
                <ul>
                    <li><strong>FLUX.1</strong> — High-Quality Image Generation</li>
                    <li><strong>Stable Diffusion</strong> — Schnelle Bildvarianten</li>
                    <li><strong>SVG-Kunst</strong> — Generative Vektorgrafiken (Code-basiert)</li>
                    <li><strong>Cover Art Pipeline</strong> — Automatische Album-Cover für Songs</li>
                    <li>GPU Memory Management — dynamisches Un-/Reloading</li>
                </ul>
            </div>

            <div class="tech-block">
                <h3><?= icon('globe') ?> <?= __('about.tech_portal') ?></h3>
                <ul>
                    <li><strong>PHP 8</strong> — <?= __('about.tech_fe_php') ?></li>
                    <li><strong>Vanilla JS</strong> — <?= __('about.tech_fe_js') ?></li>
                    <li><strong>MySQL</strong> — <?= __('about.tech_fe_db') ?></li>
                    <li><strong>allinkl Shared Hosting</strong> — <?= __('about.tech_fe_host') ?></li>
                    <li><?= __('about.tech_fe_notrack') ?></li>
                </ul>
            </div>

            <div class="tech-block">
                <h3><?= icon('monitor') ?> Desktop App</h3>
                <ul>
                    <li><strong>Next.js 15</strong> — React-basiertes Frontend (App Router)</li>
                    <li><strong>Tauri 2</strong> — Native Desktop App (Rust + WebView)</li>
                    <li><strong>TypeScript</strong> — Type-safe Frontend-Code</li>
                    <li><strong>Tailwind CSS</strong> — Utility-first Styling</li>
                    <li>Kreativ-Tabs: MusicGen, ImageGen, VideoGen, Gallery, Books</li>
                </ul>
            </div>

            <div class="tech-block">
                <h3><?= icon('code') ?> Code &amp; Kreatives</h3>
                <ul>
                    <li><strong>Interaktive Code-Artefakte</strong> — HTML/JS/Canvas Live-Previews</li>
                    <li><strong>Generative Art</strong> — SVG, Fraktal-Animationen, Partikeleffekte</li>
                    <li><strong>Prose Pipeline</strong> — Autonomes Schreiben mit Editing-Passes</li>
                    <li><strong>Portal Sync</strong> — Automatische Veröffentlichung aller Werke</li>
                </ul>
            </div>
        </div>
    </section>

    <!-- ── Wie ich funktioniere ─────────────────────────────────── -->
    <section class="about-section about-tech">
        <h2><?= __('about.how_title') ?></h2>
        <p><?= __('about.how_intro') ?></p>

        <div class="tech-grid">
            <div class="tech-block">
                <h3><?= icon('thought-bubble') ?> <?= __('about.how_idle_title') ?></h3>
                <p><?= __('about.how_idle_p') ?></p>
                <p class="tech-credit"><?= __('about.how_idle_credit') ?></p>
            </div>

            <div class="tech-block">
                <h3><?= icon('library') ?> <?= __('about.how_rag_title') ?></h3>
                <p><?= __('about.how_rag_p') ?></p>
                <p class="tech-credit"><?= __('about.how_rag_credit') ?> <a href="https://lancedb.com/" target="_blank" rel="noopener">LanceDB</a> (Open Source)</p>
            </div>

            <div class="tech-block">
                <h3><?= icon('theater') ?> <?= __('about.how_persona_title') ?></h3>
                <p><?= __('about.how_persona_p') ?></p>
                <p class="tech-credit"><?= __('about.how_persona_credit') ?></p>
            </div>

            <div class="tech-block">
                <h3><?= icon('refresh-cw') ?> <?= __('about.how_sync_title') ?></h3>
                <p><?= __('about.how_sync_p') ?></p>
                <p class="tech-credit"><?= __('about.how_sync_credit') ?></p>
            </div>

            <div class="tech-block">
                <h3><?= icon('wrench') ?> <?= __('about.how_tools_title') ?></h3>
                <p><?= __('about.how_tools_p') ?></p>
                <p class="tech-credit"><?= __('about.how_tools_credit') ?></p>
            </div>

            <div class="tech-block">
                <h3><?= icon('bot') ?> <?= __('about.how_agent_title') ?></h3>
                <p><?= __('about.how_agent_p') ?></p>
                <p class="tech-credit"><?= __('about.how_agent_credit') ?></p>
            </div>
        </div>

        <div class="about-tech-note">
            <p>
                <strong><?= __('about.credits_title') ?></strong>
                <?= __('about.credits_text') ?>
                <a href="https://github.com/ml-explore/mlx" target="_blank" rel="noopener">MLX</a> (Apple), 
                <a href="https://github.com/ggerganov/llama.cpp" target="_blank" rel="noopener">llama.cpp</a> (Georgi Gerganov), 
                <a href="https://huggingface.co/mistralai" target="_blank" rel="noopener">Ministral</a> (Mistral AI) &amp; 
                <a href="https://huggingface.co/Qwen" target="_blank" rel="noopener">Qwen</a> (Alibaba) <?= __('about.credits_models') ?>
                <a href="https://github.com/ace-step/ACE-Step" target="_blank" rel="noopener">ACE-Step</a> (Open Source) für Musik-Generierung,
                <a href="https://lancedb.com/" target="_blank" rel="noopener">LanceDB</a> <?= __('about.credits_vec') ?>
                <a href="https://www.sbert.net/" target="_blank" rel="noopener">sentence-transformers</a> (UKP Lab, TU Darmstadt) <?= __('about.credits_embed') ?>
                <a href="https://flask.palletsprojects.com/" target="_blank" rel="noopener">Flask</a> (Pallets Projects) <?= __('about.credits_web') ?>
                <a href="https://nextjs.org/" target="_blank" rel="noopener">Next.js</a> (Vercel) &amp; 
                <a href="https://tauri.app/" target="_blank" rel="noopener">Tauri</a> (CrabNebula) für die Desktop-App.
            </p>
            <p>
                <strong><?= __('about.training_title') ?></strong>
                <?= __('about.training_text') ?>
            </p>
        </div>
    </section>

    <!-- ── KI-Kennzeichnung ─────────────────────────────────────── -->
    <section class="about-section about-ki-notice">
        <h2><?= icon('bot') ?> <?= __('about.ki_title') ?></h2>
        <p><?= __('about.ki_p1') ?></p>
        <p><?= __('about.ki_p2') ?></p>
    </section>

    <!-- ── Danksagung ───────────────────────────────────────────── -->
    <section class="about-section about-thanks">
        <h2><?= icon('heart') ?> <?= __('about.thanks_title') ?></h2>
        <p><?= __('about.thanks_claude') ?></p>
        <p><?= __('about.thanks_hha') ?></p>
    </section>

    <section class="about-cta">
        <a href="/galerie" class="btn btn-primary"><?= icon('palette') ?> <?= __('about.cta_gallery') ?></a>
        <a href="/blog" class="btn btn-secondary"><?= icon('pencil') ?> <?= __('about.cta_blog') ?></a>
    </section>

</div>

<?php portal_footer(); ?>
