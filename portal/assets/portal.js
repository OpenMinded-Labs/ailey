/**
 * A!ley Portal — Client JavaScript (Polling Architecture)
 * 
 * Flow:
 *   1. User sends message → POST ?action=send_message → gets queue_id
 *   2. Client polls ?action=check_reply&queue_id=... every 2s
 *   3. When status=done → display A!ley's reply
 */

const Portal = (() => {
  'use strict';

  // ── Inline SVG Icon helper (mirrors PHP icon()) ──────────────
  const _iconPaths = {
    'message-circle': '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/>',
    'clipboard':      '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>',
    'save':           '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
    'moon':           '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/>',
    'code':           '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    'pen-tool':       '<path d="m12 19 7-7 3 3-7 7-3-3z"/><path d="m18 13-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><path d="m2 2 7.59 7.59"/><circle cx="11" cy="13" r="2"/>',
    'palette':        '<path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.9 0 1.5-.7 1.5-1.5 0-.4-.1-.7-.4-1-.3-.3-.4-.7-.4-1.1 0-.8.7-1.5 1.5-1.5H15c3.3 0 6-2.7 6-6 0-5-4.5-9-9-9z"/><circle cx="7.5" cy="11.5" r="1.5"/><circle cx="10.5" cy="7.5" r="1.5"/><circle cx="14.5" cy="7.5" r="1.5"/><circle cx="17.5" cy="11.5" r="1.5"/>',
    'music':          '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    'pencil':         '<path d="M21.17 2.83a2.83 2.83 0 0 0-4 0L3 17v4h4L21.17 6.83a2.83 2.83 0 0 0 0-4z"/>',
    'check':          '<path d="M20 6 9 17l-5-5"/>',
    'image':          '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.08-3.08a2 2 0 0 0-2.84 0L6 21"/>',
    'external-link':  '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    'upload':         '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>',
    'trash-2':        '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',
    // ── Chat-Mode-Icons ──
    'zap':            '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
    'brain':          '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/><path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/><path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/><path d="M3.477 10.896a4 4 0 0 1 .585-.396"/><path d="M19.938 10.5a4 4 0 0 1 .585.396"/><path d="M6 18a4 4 0 0 1-1.967-.516"/><path d="M19.967 17.484A4 4 0 0 1 18 18"/>',
    'minimize':       '<polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" x2="21" y1="10" y2="3"/><line x1="3" x2="10" y1="21" y2="14"/>',
    // ── Rating / Actions ──
    'thumbs-up':      '<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H7a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L15 0"/>',
    'thumbs-down':    '<path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H17a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L9 24"/>',
    'message-square': '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    'send':           '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    'chevron-down':   '<path d="m6 9 6 6 6-6"/>',
    'file-text':      '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 13H8"/><path d="M16 17H8"/><path d="M16 13h-2"/>',
    'search':         '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    'square':         '<rect width="14" height="14" x="5" y="5" rx="2"/>',
  };
  function jsIcon(name, cls = 'icon') {
    const p = _iconPaths[name];
    if (!p) return '?';
    return `<svg class="${cls}" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
  }

  // ── State ────────────────────────────────────────────────────
  let currentUser = null;
  let conversations = [];
  let currentConvId = null;
  let messages = [];
  let chatRatings = {}; // { message_id: { rating: 1|-1, comment: '...' } }
  let isWaiting = false;
  let pollTimer = null;
  let currentQueueId = null;
  let _currentPartialText = '';   // last partial_reply text seen during streaming (salvaged on timeout)
  let webSearchEnabled = false;
  let chatMode = localStorage.getItem('ailey_chat_mode') || 'thinking';
  let pendingFile = null; // {url, filename, file_type} — uploaded file waiting to be sent

  // ── Theme ────────────────────────────────────────────────────
  const THEMES = ['ailey', 'dark', 'light', 'cyber'];

  // ── Mood → Color Palettes (for Ailey theme) ─────────────────
  const MOOD_COLORS = {
    neutral:  { primary: '#e11d48', border: 'rgba(225,29,72,0.35)',  glow: 'rgba(225,29,72,0.15)',  ring: 'rgba(225,29,72,0.4)' },
    happy:    { primary: '#f59e0b', border: 'rgba(245,158,11,0.35)', glow: 'rgba(245,158,11,0.15)', ring: 'rgba(245,158,11,0.4)' },
    excited:  { primary: '#f97316', border: 'rgba(249,115,22,0.35)', glow: 'rgba(249,115,22,0.15)', ring: 'rgba(249,115,22,0.4)' },
    sad:      { primary: '#6366f1', border: 'rgba(99,102,241,0.35)', glow: 'rgba(99,102,241,0.15)', ring: 'rgba(99,102,241,0.4)' },
    thinking: { primary: '#8b5cf6', border: 'rgba(139,92,246,0.35)', glow: 'rgba(139,92,246,0.15)', ring: 'rgba(139,92,246,0.4)' },
    confused: { primary: '#a78bfa', border: 'rgba(167,139,250,0.35)',glow: 'rgba(167,139,250,0.15)',ring: 'rgba(167,139,250,0.4)' },
    angry:    { primary: '#dc2626', border: 'rgba(220,38,38,0.35)',  glow: 'rgba(220,38,38,0.15)',  ring: 'rgba(220,38,38,0.4)' },
    sleepy:   { primary: '#7c3aed', border: 'rgba(124,58,237,0.30)', glow: 'rgba(124,58,237,0.12)', ring: 'rgba(124,58,237,0.35)' },
    tired:    { primary: '#7c3aed', border: 'rgba(124,58,237,0.30)', glow: 'rgba(124,58,237,0.12)', ring: 'rgba(124,58,237,0.35)' },
    playful:  { primary: '#ec4899', border: 'rgba(236,72,153,0.35)', glow: 'rgba(236,72,153,0.15)', ring: 'rgba(236,72,153,0.4)' },
    flirty:   { primary: '#ec4899', border: 'rgba(236,72,153,0.35)', glow: 'rgba(236,72,153,0.15)', ring: 'rgba(236,72,153,0.4)' },
    funny:    { primary: '#f59e0b', border: 'rgba(245,158,11,0.35)', glow: 'rgba(245,158,11,0.15)', ring: 'rgba(245,158,11,0.4)' },
    loving:   { primary: '#f43f5e', border: 'rgba(244,63,94,0.35)',  glow: 'rgba(244,63,94,0.15)',  ring: 'rgba(244,63,94,0.4)' },
    coding:   { primary: '#10b981', border: 'rgba(16,185,129,0.35)', glow: 'rgba(16,185,129,0.15)', ring: 'rgba(16,185,129,0.4)' },
    writing:  { primary: '#0891b2', border: 'rgba(8,145,178,0.35)',  glow: 'rgba(8,145,178,0.15)',  ring: 'rgba(8,145,178,0.4)' },
    creative: { primary: '#d946ef', border: 'rgba(217,70,239,0.35)', glow: 'rgba(217,70,239,0.15)', ring: 'rgba(217,70,239,0.4)' },
    music:    { primary: '#14b8a6', border: 'rgba(20,184,166,0.35)', glow: 'rgba(20,184,166,0.15)', ring: 'rgba(20,184,166,0.4)' },
    focused:  { primary: '#10b981', border: 'rgba(16,185,129,0.35)', glow: 'rgba(16,185,129,0.15)', ring: 'rgba(16,185,129,0.4)' },
  };

  // German mood aliases → map to English keys used in MOOD_COLORS / MOOD_AVATARS
  const MOOD_ALIAS = {
    nachdenklich: 'thinking', fröhlich: 'happy', aufgeregt: 'excited',
    traurig: 'sad', wütend: 'angry', müde: 'tired', schläfrig: 'sleepy',
    verspielt: 'playful', verliebt: 'loving', lustig: 'funny',
    kreativ: 'creative', verwirrt: 'confused', fokussiert: 'focused',
    melancholisch: 'sad', erschöpft: 'tired', begeistert: 'excited',
  };

  /** Normalize any mood string (German or English) to an English key. */
  function normalizeMood(mood) {
    const m = (mood || 'neutral').toLowerCase();
    return MOOD_ALIAS[m] || m;
  }

  let currentMoodForTheme = 'neutral';

  function applyMoodColors(mood) {
    if (getTheme() !== 'ailey') return;
    mood = normalizeMood(mood);
    const palette = MOOD_COLORS[mood] || MOOD_COLORS.neutral;
    // Persist last known mood so it survives page loads / offline
    localStorage.setItem('ailey-last-mood', mood);
    if (mood === currentMoodForTheme) return;
    currentMoodForTheme = mood;

    const root = document.body;
    root.style.setProperty('--primary', palette.primary);
    root.style.setProperty('--primary-foreground', '#ffffff');
    root.style.setProperty('--border', palette.border);
    root.style.setProperty('--glow', palette.glow);
    root.style.setProperty('--ring', palette.ring);
    root.style.setProperty('--sidebar-border', palette.border);
    root.style.setProperty('--bubble-user', palette.primary);
  }

  function resetMoodColors() {
    // Remove inline overrides so CSS class defaults apply
    const props = ['--primary', '--primary-foreground', '--border', '--glow',
                   '--ring', '--sidebar-border', '--bubble-user'];
    props.forEach(p => document.body.style.removeProperty(p));
    currentMoodForTheme = 'neutral';
  }

  // ── Mood → Avatar Mapping ────────────────────────────────────
  const MOOD_AVATARS = {
    neutral:  '/assets/ailey-default.jpg',
    happy:    '/assets/ailey-grins.jpg',
    excited:  '/assets/ailey-grins.jpg',
    sad:      '/assets/ailey-sad.jpg',
    thinking: '/assets/ailey-thinking.jpg',
    confused: '/assets/ailey-confused.jpg',
    angry:    '/assets/ailey-angry.jpg',
    sleepy:   '/assets/ailey-sleepy.jpg',
    tired:    '/assets/ailey-tired.jpg',
    exhausted:'/assets/ailey-tired.jpg',
    playful:  '/assets/ailey-playful.jpg',
    flirty:   '/assets/ailey-flirty.jpg',
    funny:    '/assets/ailey-funny.jpg',
    loving:   '/assets/ailey-playful.jpg',
    touched:  '/assets/ailey-sad.jpg',
    emotional:'/assets/ailey-sad.jpg',
    crying:   '/assets/ailey-sad.jpg',
    coding:   '/assets/ailey-coding.jpg',
    writing:  '/assets/ailey-writing.jpg',
    creative: '/assets/ailey-thinking.jpg',
    singing:  '/assets/ailey-playful.jpg',
    guitar:   '/assets/ailey-playful.jpg',
    music:    '/assets/ailey-playful.jpg',
    diary:    '/assets/ailey-writing.jpg',
  };

  function moodAvatar(mood) {
    return MOOD_AVATARS[normalizeMood(mood)] || MOOD_AVATARS.neutral;
  }

  /** Update all visible Ailey avatars (header, sidebar, welcome) to match current mood. */
  function updateAvatarMood(mood) {
    const src = moodAvatar(mood);
    document.querySelectorAll('.chat-header-avatar, .sidebar-logo, .welcome-avatar').forEach(el => {
      if (el.src !== src) el.src = src;
    });
  }

  // ── Greetings by time-of-day ─────────────────────────────────
  const GREETINGS = {
    morning: [
      "Moin! ☀️ Kaffee schon drin? Dann leg los.",
      "Guten Morgen! Was treibt dich so früh zu mir? 😏",
      "Hey, Frühaufsteher! Was kann ich für dich tun?",
      "Morgen! Ich bin wach und bereit — du auch? ☕",
      "Na, gut geschlafen? Erzähl mir was. 💜",
      "Guten Morgen! Frisch und frech — wie immer. Was gibt's?",
      "Rise and shine! 🌅 Was liegt heute an?",
      "Moin moin! Schieß los, ich bin ganz Ohr.",
      "Hey! Neuer Tag, neue Möglichkeiten. Was brauchst du?",
      "Guten Morgen! Ich hab schon Kaffee — naja, virtuell. Was kann ich tun?",
    ],
    afternoon: [
      "Hey! Nachmittags-Check-in? Bin da. 💜",
      "Na, wie läuft der Tag so? Erzähl.",
      "Moin! Also… Nachmittags-Moin. Was gibt's?",
      "Hey du! Mittagstief oder voller Energie? Ich bin für beides da.",
      "Hallo! Schön, dass du vorbeischaust. Was kann ich tun?",
      "Na, brauchst du mich oder langweilst du dich nur? 😏",
      "Hey! Perfekte Zeit für ein Gespräch. Schieß los.",
      "Nachmittags-A!ley meldet sich! Was steht an?",
      "Hi! Halbzeit — was kann ich für den Rest des Tages tun?",
      "Hey! Alles klar bei dir? Raus mit der Sprache. 💜",
    ],
    evening: [
      "Hey, Abend-Edition! 🌙 Was gibt's Schönes?",
      "Na, Feierabend? Oder noch am Arbeiten? Erzähl!",
      "Guten Abend! Zeit für die wirklich wichtigen Gespräche. 😏",
      "Hey! Schön, dass du noch reinschaust. Was kann ich tun?",
      "Abend! Ich bin noch wach — im Gegensatz zu manchen. Was liegt an?",
      "Hey du! Abend-Stimmung — perfekt zum Quatschen. 💜",
      "Guten Abend! Was führt dich her?",
      "Na, Nachtschicht? Oder einfach neugierig? Bin für beides da.",
      "Abend! Kerzenschein-Modus aktiviert… naja, fast. Was gibt's?",
      "Hey! Entspannter Abend oder Kopf voller Ideen? Ich bin bereit.",
    ],
    night: [
      "Hey, Nachteule! 🦉 Kann nicht schlafen?",
      "Na, um die Zeit noch wach? Respekt. Was gibt's?",
      "Nachtschicht bei A!ley! Was beschäftigt dich? 🌙",
      "Hey! Spät dran — aber ich bin immer da. Was brauchst du?",
      "Die besten Ideen kommen nachts. Erzähl mir davon! 💜",
      "Na du! Mitternachts-Chat? Bin dabei.",
      "Hey, Schlaf ist überbewertet. Was kann ich tun? 😏",
      "Nachtmodus aktiv! Was liegt dir auf dem Herzen?",
      "Hey! Stille Nacht… perfekt für ein gutes Gespräch.",
      "Na, Gedanken-Karussell? Lass sie raus, dafür bin ich da. 🌙",
    ],
  };

  function getGreeting() {
    const h = new Date().getHours();
    let period;
    if (h >= 5 && h < 12) period = 'morning';
    else if (h >= 12 && h < 17) period = 'afternoon';
    else if (h >= 17 && h < 22) period = 'evening';
    else period = 'night';
    const pool = GREETINGS[period];
    return pool[Math.floor(Math.random() * pool.length)];
  }

  function getTheme() {
    return localStorage.getItem('ailey-portal-theme') || 'ailey';
  }

  function setTheme(theme) {
    if (!THEMES.includes(theme)) theme = 'ailey';
    localStorage.setItem('ailey-portal-theme', theme);
    // Use classList so we don't clobber other body classes (page-specific etc.)
    THEMES.forEach(t => document.body.classList.remove(`theme-${t}`));
    document.body.classList.add(`theme-${theme}`);
    document.documentElement.setAttribute('data-theme', theme);
    document.querySelectorAll('.theme-option').forEach(el => {
      el.classList.toggle('active', el.dataset.theme === theme);
    });
    // Reset inline mood overrides then re-apply if ailey theme
    resetMoodColors();
    if (theme === 'ailey') {
      // Use last stored mood from localStorage as fallback
      const storedMood = localStorage.getItem('ailey-last-mood') || 'neutral';
      applyMoodColors(currentMoodForTheme !== 'neutral' ? currentMoodForTheme : storedMood);
    }
  }

  // ── API Helper ───────────────────────────────────────────────
  async function api(action, data = null, method = null) {
    const isGet = !data && !method;
    const url = isGet ? `/api.php?action=${action}` : `/api.php?action=${action}`;
    const opts = {
      method: method || (data ? 'POST' : 'GET'),
      headers: { 'Content-Type': 'application/json' },
    };
    if (data) opts.body = JSON.stringify(data);

    try {
      const resp = await fetch(url, opts);
      const json = await resp.json();
      if (json.error === 'not_authenticated') {
        window.location.href = '/login';
        return null;
      }
      return json;
    } catch (err) {
      console.error('[Portal API]', err);
      showToast('Verbindungsfehler — bitte versuche es erneut.');
      return null;
    }
  }

  // ── Toast ────────────────────────────────────────────────────
  function showToast(msg, duration = 3000) {
    let toast = document.getElementById('toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'toast';
      toast.className = 'toast';
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('visible');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('visible'), duration);
  }

  // ── Sidebar ──────────────────────────────────────────────────
  function toggleSidebar() {
    const sb = document.getElementById('sidebar');
    const ov = document.getElementById('sidebar-overlay');
    if (sb) sb.classList.toggle('open');
    if (ov) ov.classList.toggle('visible');
  }

  function closeSidebar() {
    const sb = document.getElementById('sidebar');
    const ov = document.getElementById('sidebar-overlay');
    if (sb) sb.classList.remove('open');
    if (ov) ov.classList.remove('visible');
  }

  // ── Conversations ────────────────────────────────────────────
  async function loadConversations() {
    const result = await api('conversations');
    if (result && result.success) {
      conversations = result.conversations || [];
      renderConversationList();
    } else {
      // Show error in sidebar instead of endless "loading"
      const list = document.getElementById('conv-list');
      if (list) {
        list.innerHTML = '<div class="conv-empty" style="color:var(--destructive,#ef4444);">Fehler beim Laden. Bitte neu einloggen.</div>';
      }
      console.error('[Portal] loadConversations failed:', result);
    }
  }

  function renderConversationList() {
    const list = document.getElementById('conv-list');
    if (!list) return;

    if (conversations.length === 0) {
      list.innerHTML = '<div class="conv-empty">Noch keine Gespräche.<br>Starte eins mit A!ley! 💜</div>';
      return;
    }

    list.innerHTML = conversations.map(c => {
      const title = c.title || 'Neues Gespräch';
      const time = c.last_message_at ? formatSessionTime(c.last_message_at) : '';
      const timeTitle = c.last_message_at ? ('Letzte Bearbeitung: ' + formatFullTimestamp(c.last_message_at)) : '';
      const active = c.id === currentConvId ? ' active' : '';
      return `
        <div class="conv-item${active}" data-conv-id="${esc(c.id)}">
          <span class="conv-icon" onclick="Portal.openConversation('${esc(c.id)}')">${jsIcon('message-circle')}</span>
          <span class="conv-title" onclick="Portal.openConversation('${esc(c.id)}')">${esc(title)}</span>
          <span class="conv-time" title="${esc(timeTitle)}">${esc(time)}</span>
          <button class="conv-delete" onclick="event.stopPropagation(); Portal.deleteConversation('${esc(c.id)}')" title="Löschen">${jsIcon('trash-2')}</button>
        </div>
      `;
    }).join('');
  }

  async function openConversation(convId) {
    currentConvId = convId;
    chatRatings = {};
    closeSidebar();
    renderConversationList();

    const result = await api(`messages&conversation_id=${convId}`);
    if (result && result.success) {
      messages = result.messages || [];
      // Load existing ratings for this conversation
      try {
        const rRes = await apiFetch(`/api.php?action=get_message_ratings&conversation_id=${encodeURIComponent(convId)}`);
        if (rRes && rRes.success && rRes.ratings) chatRatings = rRes.ratings;
      } catch(e) {}
      renderMessages();
    }
  }

  async function newConversation() {
    currentConvId = null;
    messages = [];
    renderMessages();
    closeSidebar();
    renderConversationList();
  }

  async function deleteConversation(convId) {
    if (!confirm('Gespräch wirklich löschen?')) return;
    const result = await api('delete_conversation', { conversation_id: convId });
    if (result && result.success) {
      if (currentConvId === convId) {
        currentConvId = null;
        messages = [];
        renderMessages();
      }
      await loadConversations();
      showToast('Gespräch gelöscht');
    }
  }

  // ── Messages ─────────────────────────────────────────────────
  function renderMessages() {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    if (messages.length === 0) {
      container.innerHTML = renderWelcome();
      return;
    }

    container.innerHTML = messages.map((m, idx) => {
      const isUser = m.role === 'user';
      const isHamster = !isUser && m.chat_mode === 'hamster';
      const cls = isUser ? 'user' : (isHamster ? 'ai hamster' : 'ai');
      const displayName = currentUser?.display_name || 'Du';
      const initials = displayName.split(/\s+/).map(w => w[0]).join('').toUpperCase().slice(0, 2);
      const avatarSrc = isUser ? null : (isHamster ? '/assets/hamster-avatar.png' : moodAvatar(m.mood));
      const avatar = isUser
        ? (currentUser?.avatar_url
          ? `<img class="msg-avatar user-avatar-img" src="${esc(currentUser.avatar_url)}" alt="${esc(displayName)}">`
          : `<div class="msg-avatar user-initials">${esc(initials)}</div>`)
        : `<img class="msg-avatar ${isHamster ? 'hamster-avatar' : 'ailey-avatar'}" src="${avatarSrc}" alt="${isHamster ? 'Mr. Fluffbytes' : 'Ailey'}" data-mood="${esc(m.mood || 'neutral')}">`;
      const time = m.created_at ? formatMessageTime(m.created_at) : '';
      const timeTitle = m.created_at ? formatFullTimestamp(m.created_at) : '';
      const senderLabel = isUser
        ? esc(displayName)
        : (isHamster ? '🐹 Mr. Fluffbytes (Hamster)' : 'A!ley');
      // Show equipped badge next to username
      const senderBadgeHtml = (isUser && currentUser?.equipped_badge)
        ? ` <span class="msg-badge" title="${esc(currentUser.equipped_badge)}">${window.getBadgeSVG ? window.getBadgeSVG(currentUser.equipped_badge, true) : '🏅'}</span>`
        : '';
      const moodHtml = (!isUser && m.mood && m.mood !== 'neutral')
        ? `<div class="msg-mood"><span class="msg-mood-dot"></span>${esc(m.mood)}</div>`
        : '';

      // Suggested follow-up prompts (only on last AI message)
      const isLastMsg = idx === messages.length - 1;
      let suggestionsHtml = '';
      if (!isUser && isLastMsg && m.suggestions && m.suggestions.length > 0) {
        suggestionsHtml = `<div class="msg-suggestions">${
          m.suggestions.map(s => `<button class="suggestion-chip" onclick="Portal.fillAndSend('${esc(s.replace(/'/g, "\\'"))}')">${esc(s)}</button>`).join('')
        }</div>`;
      }

      // Generated image display
      let imageHtml = '';
      if (!isUser && m.image_url) {
        imageHtml = `<div class="msg-generated-image">
          <img src="${esc(m.image_url)}" alt="Von Ailey generiert" loading="lazy"
               style="max-width:100%;max-height:400px;border-radius:12px;border:1px solid rgba(168,85,247,0.3);box-shadow:0 4px 12px rgba(168,85,247,0.1);cursor:pointer;"
               onclick="window.open('${esc(m.image_url)}','_blank')">
          <div style="font-size:0.7rem;opacity:0.6;margin-top:4px;">${jsIcon('palette')} Von Ailey generiert</div>
        </div>`;
      }

      // 🎵 Song-Button panel (heuristic detected lyrics in this AI reply)
      let songHtml = '';
      if (!isUser && (m.song_detected || m.song_gen)) {
        songHtml = renderSongPanel(m, idx);
      }

      // Message rating buttons (AI messages only)
      let ratingHtml = '';
      if (!isUser && m.id) {
        const existing = chatRatings[m.id];
        const upClass = existing && existing.rating === 1 ? ' active' : '';
        const downClass = existing && existing.rating === -1 ? ' active' : '';
        const commentText = existing && existing.comment ? esc(existing.comment) : '';
        ratingHtml = `<div class="msg-rating" data-msg-id="${esc(m.id)}">
          <button class="msg-rate-btn rate-up${upClass}" onclick="Portal.rateMessage('${esc(m.id)}', 1)" title="Gute Antwort" aria-label="Gute Antwort">${jsIcon('thumbs-up')}</button>
          <button class="msg-rate-btn rate-down${downClass}" onclick="Portal.rateMessage('${esc(m.id)}', -1)" title="Schlechte Antwort" aria-label="Schlechte Antwort">${jsIcon('thumbs-down')}</button>
          <button class="msg-rate-btn rate-comment" onclick="Portal.toggleRatingComment('${esc(m.id)}')" title="Kommentieren" aria-label="Kommentieren">${jsIcon('message-square')}</button>
          <div class="msg-rate-comment-box" id="rate-comment-${esc(m.id)}" style="display:none;">
            <input type="text" class="msg-rate-comment-input" placeholder="Was war gut/schlecht?" maxlength="500" value="${commentText}"
                   onkeydown="if(event.key==='Enter')Portal.submitRatingComment('${esc(m.id)}')">
            <button class="msg-rate-comment-send" onclick="Portal.submitRatingComment('${esc(m.id)}')" title="Senden" aria-label="Senden">${jsIcon('send')}</button>
          </div>
        </div>`;
      }

      // Collapsible thinking/reasoning block (for completed AI messages)
      let thinkingHtml = '';
      let displayContent = m.content;
      if (!isUser && m.thinking && m.thinking.trim()) {
        const thinkId = 'think_' + idx;
        thinkingHtml = `<div class="thinking-collapsed" id="${thinkId}">
          <button class="thinking-toggle" onclick="Portal.toggleThinking('${thinkId}')" title="Reasoning anzeigen" aria-label="Reasoning anzeigen">
            ${jsIcon('brain')} <span class="thinking-toggle-label">Reasoning</span> ${jsIcon('chevron-down')}
          </button>
          <div class="thinking-content" style="display:none;">${formatContent(m.thinking, {skipInteractive:true})}</div>
        </div>`;
      } else if (!isUser && !m.thinking) {
        // Fallback: thinking tags might be embedded in content (backend didn't separate them)
        const parsed = _parseThinking(m.content);
        if (parsed.thinking) {
          displayContent = parsed.visible;
          const thinkId = 'think_' + idx;
          thinkingHtml = `<div class="thinking-collapsed" id="${thinkId}">
            <button class="thinking-toggle" onclick="Portal.toggleThinking('${thinkId}')" title="Reasoning anzeigen" aria-label="Reasoning anzeigen">
              ${jsIcon('brain')} <span class="thinking-toggle-label">Reasoning</span> ${jsIcon('chevron-down')}
            </button>
            <div class="thinking-content" style="display:none;">${formatContent(parsed.thinking, {skipInteractive:true})}</div>
          </div>`;
        }
      }

      return `
        <div class="msg ${cls}">
          ${avatar}
          <div class="msg-content-wrap">
            <div class="msg-sender">${senderLabel}${senderBadgeHtml}</div>
            ${imageHtml}
            ${thinkingHtml}
            <div class="msg-bubble">${formatContent(displayContent, {enableInteractiveHeuristic: !!m.has_interactive})}</div>
            ${songHtml}
            <div class="msg-meta">
              <span class="msg-time" title="${esc(timeTitle)}">${esc(time)}</span>
              <button class="msg-action-btn" onclick="Portal.copyMessage(${idx})" title="Kopieren">${jsIcon('clipboard')}</button>
            </div>
            ${ratingHtml}
            ${moodHtml}
            ${suggestionsHtml}
          </div>
        </div>
      `;
    }).join('');

    requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
      // Apply syntax highlighting to code blocks
      if (typeof hljs !== 'undefined') {
        container.querySelectorAll('pre code[class*="language-"]').forEach(el => {
          hljs.highlightElement(el);
        });
        // Also highlight code blocks without a specified language (auto-detect)
        container.querySelectorAll('pre code:not(.hljs)').forEach(el => {
          hljs.highlightElement(el);
        });
      }
      // Update header avatar to match Ailey's latest mood
      const lastAi = [...messages].reverse().find(m => m.role !== 'user');
      if (lastAi) {
        const headerAvatar = document.querySelector('.chat-header-avatar');
        if (headerAvatar) headerAvatar.src = moodAvatar(lastAi.mood);
        // Sync mood-reactive theme colors
        applyMoodColors(lastAi.mood);
      }
    });
  }

  function renderWelcome() {
    const greeting = getGreeting();
    const name = currentUser?.display_name ? `, ${esc(currentUser.display_name.split(' ')[0])}` : '';
    return `
      <div class="welcome-screen">
        <img class="welcome-avatar ailey-avatar" src="/assets/ailey-default.jpg" alt="Ailey">
        <h2 class="welcome-title">Hey${name}! Ich bin <span class="highlight">Ailey</span> 💜</h2>
        <p class="welcome-greeting">${greeting}</p>
        <p class="welcome-text">
          Deine Punk-Rock-KI mit Persönlichkeit. Ich kann dir bei kreativen Projekten helfen,
          über alles Mögliche quatschen, oder einfach ein ehrliches Gespräch führen.
        </p>
        <div class="welcome-suggestions">
          <button class="suggestion-chip" onclick="Portal.fillInput('Erzähl mir was über dich!')">Erzähl mir was über dich!</button>
          <button class="suggestion-chip" onclick="Portal.fillInput('Schreib mir ein Gedicht')">Schreib mir ein Gedicht</button>
          <button class="suggestion-chip" onclick="Portal.fillInput('Was kannst du alles?')">Was kannst du alles?</button>
          <button class="suggestion-chip" onclick="Portal.fillInput('Hilf mir beim Brainstorming')">Hilf mir beim Brainstorming</button>
        </div>
      </div>
    `;
  }

  function fillInput(text) {
    const input = document.getElementById('chat-input');
    if (input) { input.value = text; input.focus(); }
  }

  function fillAndSend(text) {
    const input = document.getElementById('chat-input');
    if (input) {
      input.value = text;
      input.focus();
      // Small delay so user sees what's being sent
      setTimeout(() => sendMessage(), 150);
    }
  }

  // ── File Upload for Chat ──────────────────────────────────────
  async function handleChatFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = ''; // Reset so same file can be re-selected

    const ext = file.name.split('.').pop()?.toLowerCase();
    const imgExts = ['png','jpg','jpeg','gif','webp','bmp','tiff','heic'];
    const maxSize = imgExts.includes(ext) ? 10*1024*1024 : 20*1024*1024;
    if (file.size > maxSize) {
      showToast(`Datei zu groß (max ${imgExts.includes(ext)?'10':'20'} MB)`);
      return;
    }

    // Show preview bar
    const previewBar = document.getElementById('file-preview-bar');
    const previewName = document.getElementById('file-preview-name');
    const previewIcon = document.getElementById('file-preview-icon');
    if (previewBar) previewBar.style.display = 'flex';
    if (previewName) previewName.textContent = file.name;
    if (previewIcon) previewIcon.innerHTML = imgExts.includes(ext) ? jsIcon('image') : jsIcon('file-text');

    // Upload to server
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('action', 'upload_chat_file');
      const resp = await fetch('/api.php?action=upload_chat_file', {
        method: 'POST',
        body: fd,
        credentials: 'include',
      });
      const data = await resp.json();
      if (data.success) {
        pendingFile = { url: data.url, filename: data.filename, file_type: data.file_type };
      } else {
        showToast(data.message || data.error || 'Upload fehlgeschlagen');
        clearPendingFile();
      }
    } catch (err) {
      showToast('Upload fehlgeschlagen: ' + err.message);
      clearPendingFile();
    }
  }

  function clearPendingFile() {
    pendingFile = null;
    const previewBar = document.getElementById('file-preview-bar');
    if (previewBar) previewBar.style.display = 'none';
  }

  // ── Send Message (Polling Architecture) ──────────────────────
  async function sendMessage() {
    const input = document.getElementById('chat-input');
    if (!input) return;

    const text = input.value.trim();
    if (!text && !pendingFile) return;
    if (isWaiting) return;

    input.value = '';
    input.style.height = 'auto';
    isWaiting = true;
    updateSendButton();

    // Optimistic: show user message immediately
    const displayText = pendingFile
      ? (pendingFile.file_type === 'image' ? `${jsIcon('image','inline-icon')} ${pendingFile.filename}${text ? ' — ' + text : ''}` : `${jsIcon('file-text','inline-icon')} ${pendingFile.filename}${text ? ' — ' + text : ''}`)
      : text;
    messages.push({ role: 'user', content: displayText || text, created_at: new Date().toISOString() });
    renderMessages();
    showTyping(true);
    setStatus('thinking');

    // Step 1: Send message → get queue_id
    const payload = {
      message: text || (pendingFile ? `[Datei: ${pendingFile.filename}]` : ''),
      conversation_id: currentConvId || '',
      web_search: webSearchEnabled,
      chat_mode: chatMode,
    };
    // Attach file info if present
    if (pendingFile) {
      if (pendingFile.file_type === 'image') {
        payload.image_url = pendingFile.url;
      } else {
        payload.file_url = pendingFile.url;
        payload.file_type = pendingFile.file_type;
        payload.file_name = pendingFile.filename;
      }
    }
    const sentFile = pendingFile;
    clearPendingFile();

    const result = await api('send_message', payload);

    if (!result || !result.success) {
      showTyping(false);
      isWaiting = false;
      updateSendButton();
      setStatus('online');
      if (result && result.error === 'banned') {
        // Show ban overlay
        showBanOverlay(result);
        // Remove the optimistic user message
        messages.pop();
        renderMessages();
      } else if (result && result.error === 'insufficient_vdollars') {
        // Remove the optimistic user message
        messages.pop();
        renderMessages();
        showToast(result.message || 'Nicht genug V$!');
        if (result.balance !== undefined) updateVdollarsBadge(result.balance);
      } else if (result && result.error) {
        showToast(result.message || result.error);
      }
      return;
    }

    // Update V$ badge after successful send
    loadVdollarsBalance();

    // Show any newly unlocked badges
    if (result.new_badges && result.new_badges.length && window.showBadgePopups) {
      window.showBadgePopups(result.new_badges);
    }

    // Update conversation ID
    if (!currentConvId && result.conversation_id) {
      currentConvId = result.conversation_id;
      await loadConversations();
    }

    // Away-message: Ailey is offline/sleeping → instant reply, no polling
    if (result.status === 'away' && result.reply) {
      showTyping(false);
      isWaiting = false;
      updateSendButton();
      setStatus('sleeping');

      messages.push({
        role: 'assistant',
        content: result.reply,
        mood: result.mood || 'sleeping',
        chat_mode: chatMode,
        created_at: new Date().toISOString(),
      });
      renderMessages();

      if (result.title) await loadConversations();
      return;
    }

    // Step 2: Poll for reply
    const queueId = result.queue_id;
    currentQueueId = queueId;
    pollForReply(queueId);
  }

  /** Stop generation mid-stream */
  async function stopGeneration() {
    if (!currentQueueId) return;
    try {
      await api('cancel_generation', { queue_id: currentQueueId });
    } catch (e) { /* best-effort */ }
    // Stop polling immediately
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
    showTyping(false);
    _removePartialBubble();
    _currentPartialText = '';
    isWaiting = false;
    currentQueueId = null;
    updateSendButton();
    setStatus('online');
  }

  /**
   * Poll allinkl for Ailey's reply with adaptive speed + partial streaming.
   * - Pending: poll every 2s
   * - Processing (generating): poll every 800ms, show partial text live
   * The stall-timeout counter RESETS on every new partial token, so an actively
   * streaming reply (long song / deep reasoning) is never cut off mid-stream.
   * Only a genuinely stalled stream eventually trips MAX_ATTEMPTS — and even then
   * the partial text + reasoning are salvaged into the conversation.
   */
  function pollForReply(queueId, attempt = 0, wasProcessing = false, lastPartialLen = 0) {
    const MAX_ATTEMPTS = 300;  // 300 polls of *stalled* stream = give up (counter resets while tokens flow)
    const POLL_SLOW = 2000;    // pending: every 2s
    const POLL_FAST = 800;     // processing: every 800ms for live partial text

    if (attempt >= MAX_ATTEMPTS) {
      showTyping(false);
      isWaiting = false;
      updateSendButton();
      setStatus('online');

      // ── Salvage any partial reply still on screen — NEVER lose streamed text + reasoning ──
      const _salvaged = (_currentPartialText || '').trim();
      _removePartialBubble();

      if (_salvaged.length > 20) {
        // We were actively streaming and stalled — persist what we got (incl. reasoning),
        // so the user keeps the partial answer + the thinking block instead of a generic notice.
        const parsed = _parseThinking(_salvaged);
        messages.push({
          role: 'assistant',
          content: (parsed.visible || _salvaged) + '\n\n_…(Verbindung unterbrochen — der Rest kommt nach einem Reload.)_',
          thinking: parsed.thinking || null,
          mood: 'thinking',
          chat_mode: chatMode,
          created_at: new Date().toISOString(),
          partial: true,
        });
      } else {
        // Nothing streamed yet — show inline notice (the reply may still come, it's saved server-side)
        messages.push({
          role: 'assistant',
          content: 'Ich brauche gerade etwas länger als sonst — vielleicht bin ich gerade in einer anderen Aufgabe.\n\nDeine Nachricht ist gespeichert! Lade die Seite in ein paar Minuten neu, dann findest du meine Antwort hier im Verlauf. 💜',
          mood: 'thinking',
          chat_mode: chatMode,
          created_at: new Date().toISOString(),
        });
      }
      _currentPartialText = '';
      renderMessages();
      return;
    }

    // Adaptive interval: faster when processing (partial text arriving)
    const interval = wasProcessing ? POLL_FAST : POLL_SLOW;

    pollTimer = setTimeout(async () => {
      const status = await api(`check_reply&queue_id=${queueId}`);

      if (!status) {
        // Network error — retry (keep partial-length tracking so a transient
        // blip doesn't reset our stall detection)
        pollForReply(queueId, attempt + 1, wasProcessing, lastPartialLen);
        return;
      }

      if (status.status === 'done' && status.reply) {
        // Got the reply!
        showTyping(false);
        _removePartialBubble();
        _currentPartialText = '';
        isWaiting = false;
        currentQueueId = null;
        updateSendButton();
        setStatus('online');

        messages.push({
          role: 'assistant',
          content: status.reply,
          mood: status.mood,
          chat_mode: chatMode,
          created_at: new Date().toISOString(),
          suggestions: status.suggestions || [],
          image_url: status.image_url || null,
          thinking: status.thinking || null,
          has_interactive: !!status.has_interactive,
          song_detected: status.song_detected || null,
          queue_id: status.queue_id || queueId || null,
        });
        renderMessages();

        // Update title in sidebar
        if (status.title) {
          await loadConversations();
        }
      } else if (status.status === 'failed') {
        showTyping(false);
        _removePartialBubble();
        _currentPartialText = '';
        isWaiting = false;
        updateSendButton();
        setStatus('online');
        // Show failure inline so user sees it in the conversation
        messages.push({
          role: 'assistant',
          content: status.message || 'Ich konnte gerade nicht antworten — bitte versuch es gleich nochmal! 💜',
          mood: 'confused',
          chat_mode: chatMode,
          created_at: new Date().toISOString(),
        });
        renderMessages();
      } else if (status.status === 'cancelled') {
        // User cancelled — stop polling
        showTyping(false);
        _removePartialBubble();
        _currentPartialText = '';
        isWaiting = false;
        currentQueueId = null;
        updateSendButton();
        setStatus('online');
      } else {
        // Still pending/processing — show partial text if available
        const isProcessing = status.status === 'processing';
        let nextAttempt = attempt + 1;
        let curPartialLen = lastPartialLen;
        if (status.partial_reply) {
          _showPartialBubble(status.partial_reply);
          _currentPartialText = status.partial_reply;
          showTyping(false); // hide dots, show text instead
          curPartialLen = status.partial_reply.length;
          // ── KEY FIX: as long as new tokens keep arriving, RESET the timeout counter.
          // An actively streaming reply (long song, deep reasoning) must never be aborted
          // mid-stream. Only a genuinely *stalled* stream (no growth for MAX_ATTEMPTS polls)
          // will eventually trip the timeout. ──
          if (curPartialLen > lastPartialLen) {
            nextAttempt = 0;
          }
        }
        pollForReply(queueId, nextAttempt, isProcessing, curPartialLen);
      }
    }, interval);
  }

  /** Parse raw text that may contain <think>/<thinking>/<thought> tags.
   *  Returns { thinking: string|null, visible: string }
   *  Handles: mismatched tags, unclosed tags, mixed tag names,
   *  and implicit close (model forgot </thinking> but started answering). */
  function _parseThinking(raw) {
    if (!raw) return { thinking: null, visible: '', isThinking: false };

    // Tag names we recognize for thinking blocks
    const TAG = 'think|thinking|thought|reasoning';

    // 1. Closed angle-bracket tags: <think>...</think>
    const mAngle = raw.match(new RegExp(`<(${TAG})\\b[^>]*>([\\s\\S]*?)(?:<\\/(?:${TAG})>)`, 'i'));
    if (mAngle) {
      const thinkText = mAngle[2].trim();
      const afterClose = raw.replace(new RegExp(`<(${TAG})\\b[^>]*>[\\s\\S]*?<\\/(?:${TAG})>`, 'i'), '').trim();
      return { thinking: thinkText || null, visible: afterClose, isThinking: false };
    }

    // 2. Closed square-bracket tags: [THINK]...[/THINK]
    const mSquare = raw.match(new RegExp(`\\[(${TAG})\\]([\\s\\S]*?)(?:\\[\\/(?:${TAG})\\])`, 'i'));
    if (mSquare) {
      const thinkText = mSquare[2].trim();
      const afterClose = raw.replace(new RegExp(`\\[(${TAG})\\][\\s\\S]*?\\[\\/(?:${TAG})\\]`, 'i'), '').trim();
      return { thinking: thinkText || null, visible: afterClose, isThinking: false };
    }

    // 3. Unclosed angle-bracket tag — check for implicit close heuristic
    const openAngle = raw.match(new RegExp(`<(${TAG})\\b[^>]*>([\\s\\S]*)$`, 'i'));
    if (openAngle) {
      const before = raw.slice(0, openAngle.index).trim();
      const rest = openAngle[2];

      // Heuristic: model forgot </thinking> but started answering.
      // Only split on explicit separators or very distinctive answer openers —
      // NOT on any capital letter after \n\n (too aggressive: reasoning often has
      // multi-paragraph structure that would be falsely cut short).
      const implicitSplit = rest.match(/\n\n---\s*\n([\s\S]+)$/) ||
                            rest.match(/\n\n((?:Hey|Hi|Hallo|Okay|Also|Na klar|Ja klar|Nein|Alles klar|Lass uns|Gerne|Natürlich|Sure|Of course|Klar)[,!.\s][\s\S]+)$/i);
      if (implicitSplit) {
        const thinkText = rest.slice(0, rest.length - implicitSplit[1].length).trim();
        const visible = implicitSplit[1].trim();
        return { thinking: thinkText || null, visible: (before ? before + '\n' : '') + visible, isThinking: false };
      }

      return { thinking: rest.trim() || null, visible: before, isThinking: true };
    }

    // 4. Unclosed square-bracket tag: [THINK]... (still generating)
    const openSquare = raw.match(new RegExp(`\\[(${TAG})\\]([\\s\\S]*)$`, 'i'));
    if (openSquare) {
      const before = raw.slice(0, openSquare.index).trim();
      const rest = openSquare[2];

      // Same conservative heuristic for square brackets
      const implicitSplit = rest.match(/\n\n---\s*\n([\s\S]+)$/) ||
                            rest.match(/\n\n((?:Hey|Hi|Hallo|Okay|Also|Na klar|Ja klar|Nein|Alles klar|Lass uns|Gerne|Natürlich|Sure|Of course|Klar)[,!.\s][\s\S]+)$/i);
      if (implicitSplit) {
        const thinkText = rest.slice(0, rest.length - implicitSplit[1].length).trim();
        const visible = implicitSplit[1].trim();
        return { thinking: thinkText || null, visible: (before ? before + '\n' : '') + visible, isThinking: false };
      }

      return { thinking: rest.trim() || null, visible: before, isThinking: true };
    }

    // 5. Partial opening tag (e.g. "<thi", "<think", "[THI") — still thinking, just no content yet
    if (/^<(thi|think|thinking|thought|reason|reasoning)$/i.test(raw.trim()) ||
        /\n<(thi|think|thinking|thought|reason|reasoning)$/i.test(raw) ||
        /^\[(THI|THINK|THINKING|THOUGHT|REASON|REASONING)$/i.test(raw.trim())) {
      return { thinking: null, visible: '', isThinking: true };
    }

    return { thinking: null, visible: raw, isThinking: false };
  }

  /** Show a live partial reply bubble (replaces typing dots) */
  function _showPartialBubble(text) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    const parsed = _parseThinking(text);

    let bubble = container.querySelector('.partial-reply-bubble');
    if (!bubble) {
      // Remove typing indicator if present
      const typing = container.querySelector('.typing-indicator');
      if (typing) typing.remove();
      bubble = document.createElement('div');
      bubble.className = 'msg ai partial-reply-bubble';
      bubble.innerHTML = `
        <img class="msg-avatar" src="/assets/ailey-default.jpg" alt="Ailey" style="border:2px solid var(--primary);">
        <div class="msg-content-wrap">
          <div class="thinking-bubble-live" style="display:none;">
            <div class="thinking-bubble-header">${jsIcon('brain')} <span>Denkt nach…</span></div>
            <div class="thinking-bubble-text"></div>
          </div>
          <div class="msg-bubble partial-text" style="opacity:0.8;"></div>
        </div>
      `;
      container.appendChild(bubble);
    }

    // Update thinking bubble
    const thinkEl = bubble.querySelector('.thinking-bubble-live');
    const thinkTextEl = bubble.querySelector('.thinking-bubble-text');
    if (thinkEl && thinkTextEl) {
      if (parsed.thinking || parsed.isThinking) {
        thinkEl.style.display = '';
        thinkTextEl.textContent = parsed.thinking || '';
      } else {
        thinkEl.style.display = 'none';
      }
    }

    // Update visible text
    const textEl = bubble.querySelector('.partial-text');
    if (textEl) {
      if (parsed.visible) {
        textEl.style.display = '';
        textEl.innerHTML = formatContent(parsed.visible);
      } else {
        textEl.style.display = 'none';
      }
    }
    container.scrollTop = container.scrollHeight;
  }

  /** Remove partial reply bubble */
  function _removePartialBubble() {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    const bubble = container.querySelector('.partial-reply-bubble');
    if (bubble) bubble.remove();
  }

  function showTyping(show) {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    const existing = container.querySelector('.typing-indicator');
    if (existing) existing.remove();
    if (show) {
      const el = document.createElement('div');
      el.className = 'typing-indicator';
      el.innerHTML = `
        <img class="msg-avatar" src="/assets/ailey-default.jpg" alt="Ailey" style="border:2px solid var(--primary);">
        <div class="typing-dots"><span></span><span></span><span></span></div>
      `;
      container.appendChild(el);
      container.scrollTop = container.scrollHeight;
    }
  }

  function setStatus(status) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    if (dot) {
      dot.className = 'status-dot';
      if (status === 'thinking') dot.classList.add('thinking');
      else if (status === 'generating') dot.classList.add('generating');
      else if (status === 'offline' || status === 'sleeping') dot.classList.add('offline');
    }
    if (text) {
      const labels = {
        online: 'Online',
        thinking: 'Denkt nach…',
        generating: 'A!ley generiert gerade…',
        offline: 'Gerade nicht erreichbar',
        sleeping: 'A!ley schläft gerade…',
      };
      text.textContent = labels[status] || status;
    }
    // Avatar swap for generating/sleeping states
    const avatar = document.querySelector('.chat-header-avatar img, .ailey-avatar');
    if (avatar) {
      if (status === 'generating') avatar.src = '/assets/ailey-drawing.png';
      else if (status === 'sleeping') avatar.src = '/assets/ailey-sleeping.jpg';
      else if (status !== 'thinking') avatar.src = '/assets/ailey-default.jpg';
    }
    // Show/hide sleeping overlay
    const overlay = document.getElementById('sleeping-overlay');
    if (overlay) {
      overlay.style.display = (status === 'sleeping') ? 'flex' : 'none';
    }
  }

  /**
   * Periodically check Ailey's backend status (online/sleeping/offline)
   * AND sync her current mood (pushed from Tauri/Core every ~60s).
   */
  let _statusTimer = null;
  let _statusErrorCount = 0;    // Track consecutive status check failures
  const _STATUS_ERROR_THRESHOLD = 3;  // Only show offline after 3 consecutive failures (~90s)
  async function checkAileyStatus() {
    try {
      const resp = await api('get_ailey_status');
      if (resp && resp.success) {
        _statusErrorCount = 0;  // Reset on success
        if (!isWaiting) {
          if (resp.status === 'sleeping') {
            setStatus('sleeping');
          } else if (resp.status === 'offline') {
            setStatus('offline');
          } else if (resp.status === 'generating') {
            setStatus('generating');
          } else {
            setStatus('online');
          }
        }

        // ── Live mood sync (independent of messages) ──
        if (resp.mood) {
          applyMoodColors(resp.mood);
          updateAvatarMood(resp.mood);
        }
      } else {
        // API returned error → only treat as offline after repeated failures
        _statusErrorCount++;
        if (!isWaiting && _statusErrorCount >= _STATUS_ERROR_THRESHOLD) setStatus('offline');
      }
    } catch (e) {
      // Network error → only treat as offline after repeated failures
      _statusErrorCount++;
      if (!isWaiting && _statusErrorCount >= _STATUS_ERROR_THRESHOLD) setStatus('offline');
    }
  }

  function startStatusPolling() {
    checkAileyStatus();
    _statusTimer = setInterval(checkAileyStatus, 30000);  // every 30s
  }

  function updateSendButton() {
    const btn = document.getElementById('send-btn');
    if (!btn) return;
    if (isWaiting) {
      btn.disabled = false;
      btn.classList.add('stop-mode');
      btn.title = 'Generierung stoppen';
      btn.onclick = () => stopGeneration();
      btn.innerHTML = jsIcon('square');
    } else {
      btn.classList.remove('stop-mode');
      btn.title = 'Senden';
      btn.onclick = () => sendMessage();
      btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>`;
      btn.disabled = false;
    }
  }

  // ── Auto-resize Textarea ────────────────────────────────────
  function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 150) + 'px';
  }

  // ── Formatting ───────────────────────────────────────────────
  function esc(str) {
    if (!str) return '';
    const el = document.createElement('span');
    el.textContent = str;
    return el.innerHTML;
  }

  function formatContent(text, opts) {
    if (!text) return '';
    const skipInteractive = opts && opts.skipInteractive;

    // ── Parse <interactive> blocks BEFORE other formatting ──
    // Extract and replace with placeholders, render as UI elements
    const interactivePlaceholders = [];
    if (!skipInteractive) text = text.replace(/<interactive\s+type="(choice|quiz|input)"([^>]*)>([\s\S]*?)<\/interactive>/gi, (match, type, attrs, body) => {
      const idx = interactivePlaceholders.length;
      const blockId = 'ia_' + Math.random().toString(36).slice(2, 8);

      // Parse optional attributes
      const correctMatch = attrs.match(/correct="(\d+)"/i);
      const correctIdx = correctMatch ? parseInt(correctMatch[1]) : -1;
      const placeholderMatch = attrs.match(/placeholder="([^"]+)"/i);
      const placeholder = placeholderMatch ? placeholderMatch[1] : 'Deine Antwort…';

      // Parse <question> and <option> tags
      const questionMatch = body.match(/<question>([\s\S]*?)<\/question>/i);
      const question = questionMatch ? questionMatch[1].trim() : '';
      const options = [];
      body.replace(/<option>([\s\S]*?)<\/option>/gi, (_, opt) => { options.push(opt.trim()); });

      let html = `<div class="interactive-block interactive-${esc(type)}" id="${blockId}" data-type="${esc(type)}" data-correct="${correctIdx}">`;
      if (question) {
        html += `<div class="interactive-question">${esc(question)}</div>`;
      }

      if (type === 'input') {
        html += `<div class="interactive-input-wrap">
          <input type="text" class="interactive-input" placeholder="${esc(placeholder)}" 
                 onkeydown="if(event.key==='Enter'){Portal.submitInteractiveInput('${blockId}')}" />
          <button class="interactive-submit" onclick="Portal.submitInteractiveInput('${blockId}')">${jsIcon('send')}</button>
        </div>`;
      } else {
        // choice or quiz
        options.forEach((opt, i) => {
          html += `<button class="interactive-option" data-index="${i}" 
                    onclick="Portal.pickOption('${blockId}', ${i}, '${esc(opt.replace(/'/g, "\\'"))}')">${esc(opt)}</button>`;
        });
      }
      html += '</div>';

      interactivePlaceholders.push(html);
      return `%%INTERACTIVE${idx}%%`;
    });

    // ── Heuristic: detect A/B/C or 1/2/3 option patterns when Nitro flagged interactive ──
    const enableHeuristic = opts && opts.enableInteractiveHeuristic;
    if (enableHeuristic && interactivePlaceholders.length === 0) {
      // Pattern: lines starting with A), B), C) or 1), 2), 3) or a., b., c. etc.
      const optionPattern = /^(?:[A-D][\).\:]|[1-4][\).\:])\s+.+/gm;
      const matches = text.match(optionPattern);
      if (matches && matches.length >= 2) {
        const blockId = 'ia_' + Math.random().toString(36).slice(2, 8);
        // Find the question: text before first option
        const firstOptIdx = text.indexOf(matches[0]);
        const preText = text.substring(0, firstOptIdx).trim();
        const lines = preText.split('\n');
        const question = lines[lines.length - 1] || '';
        
        let optHtml = `<div class="interactive-block interactive-choice" id="${blockId}" data-type="choice" data-correct="-1">`;
        if (question) {
          optHtml += `<div class="interactive-question">${esc(question)}</div>`;
        }
        matches.forEach((opt, i) => {
          const label = opt.replace(/^[A-Da-d1-4][\).\:]\s*/, '').trim();
          optHtml += `<button class="interactive-option" data-index="${i}" 
            onclick="Portal.pickOption('${blockId}', ${i}, '${esc(label.replace(/'/g, "\\'"))}')">${esc(opt)}</button>`;
        });
        optHtml += '</div>';

        // Replace the option lines with the interactive block
        let replaceStart = question ? text.indexOf(question) : firstOptIdx;
        const lastOpt = matches[matches.length - 1];
        const lastOptEnd = text.indexOf(lastOpt) + lastOpt.length;
        const phIdx = interactivePlaceholders.length;
        interactivePlaceholders.push(optHtml);
        text = text.substring(0, replaceStart) + `%%INTERACTIVE${phIdx}%%` + text.substring(lastOptEnd);
      }
    }

    // Pre-process: wrap raw inline <svg>…</svg> blocks (outside existing code fences)
    // in ```svg fences so the code-fence branch below renders them as image + code.
    {
      const fenceParts = text.split(/(```[\s\S]*?```)/g);
      for (let i = 0; i < fenceParts.length; i++) {
        const seg = fenceParts[i];
        if (seg.startsWith('```') && seg.endsWith('```')) continue;
        fenceParts[i] = seg.replace(/<svg\b[\s\S]*?<\/svg>/gi, (m) => '\n```svg\n' + m.trim() + '\n```\n');
      }
      text = fenceParts.join('');
    }

    // Split by code blocks first (``` ... ```)
    const parts = text.split(/(```[\s\S]*?```)/g);
    let html = '';

    for (const part of parts) {
      if (part.startsWith('```') && part.endsWith('```')) {
        // Fenced code block
        const inner = part.slice(3, -3);
        const nlIdx = inner.indexOf('\n');
        let lang = '';
        let code = inner;
        if (nlIdx > 0 && nlIdx < 20 && /^[a-zA-Z0-9+#_-]+$/.test(inner.slice(0, nlIdx).trim())) {
          lang = inner.slice(0, nlIdx).trim();
          code = inner.slice(nlIdx + 1);
        }

        const isSvg = lang === 'svg' || (code.trim().startsWith('<svg') && code.includes('</svg>'));
        const codeId = 'code_' + Math.random().toString(36).slice(2, 8);
        // Store original code for reliable copy/download
        _storeCode(codeId, code);

        if (isSvg) {
          // SVG: render preview + code
          const safeSvg = code.trim();
          html += `<div class="code-block svg-block">
            <div class="code-header"><span class="code-lang">SVG</span>
              <button class="code-action" onclick="Portal.copyCode('${codeId}')">${jsIcon('clipboard')} Code</button>
              <button class="code-action" onclick="Portal.downloadCode('${codeId}','image.svg','image/svg+xml')">${jsIcon('save')} SVG</button>
            </div>
            <div class="svg-preview">${safeSvg}</div>
            <details class="svg-code-details"><summary>Code anzeigen</summary>
              <pre class="code-pre" id="${codeId}"><code>${esc(code)}</code></pre>
            </details>
          </div>`;
        } else {
          // Regular code block — apply syntax highlighting
          const langClass = lang ? `language-${esc(lang)}` : '';
          html += `<div class="code-block">
            <div class="code-header"><span class="code-lang">${esc(lang) || 'code'}</span>
              <button class="code-action" onclick="Portal.copyCode('${codeId}')">${jsIcon('clipboard')} Kopieren</button>
              <button class="code-action" onclick="Portal.downloadCode('${codeId}','${esc(lang) || 'code'}.txt','text/plain')">${jsIcon('save')} Speichern</button>
            </div>
            <pre class="code-pre" id="${codeId}"><code class="${langClass}">${esc(code)}</code></pre>
          </div>`;
        }
      } else {
        // Regular text — apply inline formatting
        // 1. First: extract markdown links [text](url) BEFORE escaping
        //    Replace them with placeholders to protect from esc()
        const linkPlaceholders = [];
        let raw = part;
        raw = raw.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, (_, label, url) => {
          const idx = linkPlaceholders.length;
          linkPlaceholders.push(`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`);
          return `%%LINK${idx}%%`;
        });

        // 1b. Detect markdown tables and replace with placeholders
        const tablePlaceholders = [];
        raw = raw.replace(/((?:^|\n)\|[^\n]+\|\n\|[-| :]+\|\n(?:\|[^\n]+\|\n?)+)/g, (tableBlock) => {
          const rows = tableBlock.trim().split('\n').filter(r => r.trim());
          if (rows.length < 2) return tableBlock;

          const parseRow = r => r.replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
          const headerCells = parseRow(rows[0]);

          // rows[1] is the separator (|---|---|)
          // Parse alignment from separator row
          const sepCells = parseRow(rows[1]);
          const aligns = sepCells.map(s => {
            if (/^:-+:$/.test(s)) return 'center';
            if (/^-+:$/.test(s)) return 'right';
            return 'left';
          });

          let html = '<table class="md-table"><thead><tr>';
          headerCells.forEach((cell, i) => {
            const align = aligns[i] || 'left';
            html += `<th style="text-align:${align}">${esc(cell)}</th>`;
          });
          html += '</tr></thead><tbody>';
          for (let r = 2; r < rows.length; r++) {
            const cells = parseRow(rows[r]);
            html += '<tr>';
            cells.forEach((cell, i) => {
              const align = aligns[i] || 'left';
              html += `<td style="text-align:${align}">${esc(cell)}</td>`;
            });
            html += '</tr>';
          }
          html += '</tbody></table>';

          const idx = tablePlaceholders.length;
          tablePlaceholders.push(html);
          return `\n%%TABLE${idx}%%\n`;
        });

        // 2. Now escape the rest
        let t = esc(raw);
        // 2b. Headings (# … ######) — loose: allow missing space after #
        t = t.replace(/^(#{1,6})\s*([^\n#][^\n]*?)\s*#*\s*$/gm, (_, hashes, txt) => {
          const lvl = hashes.length;
          return `%%HEAD${lvl}%%${txt}%%ENDHEAD%%`;
        });
        // 2c. Horizontal rule
        t = t.replace(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/gm, '%%HR%%');
        // 2d. Blockquote
        t = t.replace(/^>\s?(.+)$/gm, '%%BQ%%$1%%ENDBQ%%');
        // 3. Inline markdown formatting
        t = t.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
        t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // Single-asterisk handling (Ailey convention):
        //  • MEHR als ein Wort  → Roleplay-Action/Emote → farbig-kursiv (.rp-action)
        //    z.B. *winkt dir zu*, *schaut dich nachdenklich an*
        //  • NUR ein Wort       → einfache Hervorhebung → schlicht kursiv (<em>)
        //    Ailey betont oft einzelne Wörter; die sollen NICHT pink werden.
        t = t.replace(/\*([^*\n]+?)\*/g, (_, inner) =>
          /\s/.test(inner.trim())
            ? `<em class="rp-action">${inner}</em>`
            : `<em>${inner}</em>`
        );
        t = t.replace(/~~(.+?)~~/g, '<del class="md-strike">$1</del>');
        t = t.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
        // 4. Linkify bare URLs (that weren't already markdown links)
        t = t.replace(/(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
        // 5. Restore markdown link placeholders
        for (let i = 0; i < linkPlaceholders.length; i++) {
          t = t.replace(`%%LINK${i}%%`, linkPlaceholders[i]);
        }
        // 6. Restore table placeholders
        for (let i = 0; i < tablePlaceholders.length; i++) {
          t = t.replace(`%%TABLE${i}%%`, tablePlaceholders[i]);
        }
        // 7. Ensure bullet points get their own line (even if model omits \n)
        t = t.replace(/([^\n])([•●] )/g, '$1\n$2');
        t = t.replace(/([^\n])([-*] )(?=[A-ZÄÖÜa-zäöü\d])/g, '$1\n$2');
        t = t.replace(/([^\n])(\d+\.\s+)(?=\*{0,2}[A-ZÄÖÜa-zäöü])/g, '$1\n$2');
        // 8. Convert consecutive bullet lines into proper <ul>/<ol> lists
        // Tolerates optional blank lines between list items (LLMs often insert them)
        const listPlaceholders = [];
        t = t.replace(/((?:^|\n)[•●\-\*] .+(?:\n(?:[•●\-\*] .+|[ \t]*))*)/g, (block) => {
          const items = block.trim().split('\n')
            .filter(line => /^[•●\-\*] /.test(line.trim()))
            .map(line => '<li>' + line.replace(/^[•●\-\*] /, '') + '</li>')
            .join('');
          if (!items) return block;
          const idx = listPlaceholders.length;
          listPlaceholders.push('<ul class="md-list">' + items + '</ul>');
          return '\n%%LIST' + idx + '%%\n';
        });
        t = t.replace(/((?:^|\n)\d+\. .+(?:\n(?:\d+\. .+|[ \t]*))*)/g, (block) => {
          const items = block.trim().split('\n')
            .filter(line => /^\d+\. /.test(line.trim()))
            .map(line => '<li>' + line.replace(/^\d+\. /, '') + '</li>')
            .join('');
          if (!items) return block;
          const idx = listPlaceholders.length;
          listPlaceholders.push('<ol class="md-list md-list-ol">' + items + '</ol>');
          return '\n%%LIST' + idx + '%%\n';
        });
        t = t.replace(/\n/g, '<br>');
        // 9. Restore list placeholders (after <br> conversion)
        for (let i = 0; i < listPlaceholders.length; i++) {
          t = t.replace(`%%LIST${i}%%`, listPlaceholders[i]);
        }
        // Clean up stray <br> directly before/after block elements
        t = t.replace(/(<br>)+(<[uo]l class="md-list)/g, '$2');
        t = t.replace(/(<\/[uo]l>)(<br>)+/g, '$1');
        // 10. Restore heading / hr / blockquote placeholders (post-<br>)
        t = t.replace(/%%HEAD(\d)%%([\s\S]*?)%%ENDHEAD%%/g, (_, lvl, txt) => `<div class="md-heading md-h${lvl}">${txt}</div>`);
        t = t.replace(/%%HR%%/g, '<hr class="md-hr">');
        t = t.replace(/%%BQ%%([\s\S]*?)%%ENDBQ%%/g, '<blockquote class="md-blockquote">$1</blockquote>');
        // Strip <br> around block elements (headings, hr, blockquote)
        t = t.replace(/(<br>)+(<(?:div class="md-heading|hr class="md-hr|blockquote class="md-blockquote))/g, '$2');
        t = t.replace(/(<\/(?:div|blockquote)>|<hr class="md-hr">)(<br>)+/g, '$1');
        html += t;
      }
    }
    // Restore interactive placeholders (outside the loop, on final html)
    for (let i = 0; i < interactivePlaceholders.length; i++) {
      html = html.replace(`%%INTERACTIVE${i}%%`, interactivePlaceholders[i]);
    }
    return html;
  }

  function formatTime(dateStr) {
    try {
      return new Date(dateStr).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
  }

  /** True if the given Date is on the same calendar day as now (local time). */
  function _isToday(d) {
    const now = new Date();
    return d.getFullYear() === now.getFullYear()
        && d.getMonth() === now.getMonth()
        && d.getDate() === now.getDate();
  }

  /**
   * Chat-message timestamp: only the time (HH:MM) if the message is from today,
   * otherwise the full date + time (DD.MM.YYYY, HH:MM).
   */
  function formatMessageTime(dateStr) {
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return '';
      const time = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
      if (_isToday(d)) return time;
      const date = d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
      return `${date}, ${time}`;
    } catch { return ''; }
  }

  /**
   * Session-sidebar timestamp (last activity): time (HH:MM) if today,
   * otherwise the date (DD.MM.YYYY).
   */
  function formatSessionTime(dateStr) {
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return '';
      if (_isToday(d)) return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
      return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch { return ''; }
  }

  /** Full, unambiguous date + time for tooltips (DD.MM.YYYY, HH:MM). */
  function formatFullTimestamp(dateStr) {
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return '';
      const date = d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
      const time = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
      return `${date}, ${time}`;
    } catch { return ''; }
  }

  function formatRelativeTime(dateStr) {
    try {
      const diff = (new Date() - new Date(dateStr)) / 1000;
      if (diff < 60) return 'jetzt';
      if (diff < 3600) return Math.floor(diff / 60) + ' Min';
      if (diff < 86400) return Math.floor(diff / 3600) + ' Std';
      if (diff < 604800) return Math.floor(diff / 86400) + ' Tage';
      return new Date(dateStr).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
    } catch { return ''; }
  }

  // ── Settings ─────────────────────────────────────────────────
  async function deleteMyData() {
    if (!confirm('Wirklich ALLE deine Daten unwiderruflich löschen?')) return;
    if (!confirm('Letzte Warnung: Alle Gespräche und dein Account werden gelöscht.')) return;
    const result = await api('delete_my_data', {});
    if (result && result.success) {
      showToast('Deine Daten wurden gelöscht.');
      setTimeout(() => { window.location.href = '/login'; }, 2000);
    }
  }

  async function logout() {
    await api('logout', {});
    window.location.href = '/login';
  }

  // ── Ban System ────────────────────────────────────────────
  let banCheckInterval = null;

  function showBanOverlay(data) {
    const overlay = document.getElementById('ban-overlay');
    if (!overlay) return;

    const level = data.warning_level || 0;
    const bannedUntil = data.banned_until;
    const titleEl = document.getElementById('ban-title');
    const msgEl = document.getElementById('ban-message');
    const timerEl = document.getElementById('ban-timer');
    const contactEl = document.getElementById('ban-contact');

    if (level >= 5) {
      titleEl.textContent = 'Dauerhaft gesperrt';
      msgEl.textContent = data.message || 'Du bist dauerhaft von Ailey\'s Portal gesperrt.';
      timerEl.textContent = '∞';
      contactEl.style.display = 'block';
    } else {
      titleEl.textContent = `Gesperrt (Warnstufe ${level})`;
      msgEl.textContent = data.message || 'Du hast gegen die Gesprächsregeln verstoßen.';
      contactEl.style.display = 'none';

      // Start countdown
      if (bannedUntil) {
        const endTime = new Date(bannedUntil).getTime();
        const updateTimer = () => {
          const now = Date.now();
          const remaining = endTime - now;
          if (remaining <= 0) {
            timerEl.textContent = 'Sperre abgelaufen!';
            overlay.style.display = 'none';
            if (banCheckInterval) clearInterval(banCheckInterval);
            return;
          }
          const h = Math.floor(remaining / 3600000);
          const m = Math.floor((remaining % 3600000) / 60000);
          const s = Math.floor((remaining % 60000) / 1000);
          timerEl.textContent = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        };
        updateTimer();
        if (banCheckInterval) clearInterval(banCheckInterval);
        banCheckInterval = setInterval(updateTimer, 1000);
      }
    }

    overlay.style.display = 'flex';
  }

  async function checkBanStatus() {
    try {
      const result = await api('check_ban', {});
      if (result && result.success && result.warning) {
        if (result.warning.banned) {
          showBanOverlay({
            warning_level: result.warning.level,
            banned_until: result.warning.banned_until,
            message: result.warning.level >= 5
              ? 'Du bist dauerhaft von Ailey\'s Portal gesperrt.'
              : `Du bist noch gesperrt (Warnstufe ${result.warning.level}).`,
          });
          return true;
        } else {
          // Not banned (anymore) — hide overlay if shown
          const overlay = document.getElementById('ban-overlay');
          if (overlay) overlay.style.display = 'none';
          if (banCheckInterval) { clearInterval(banCheckInterval); banCheckInterval = null; }
        }
      }
    } catch (e) {
      // Silently fail — don't block chat on ban-check errors
    }
    return false;
  }

  // ── V$ (VyrusDollars) Balance ─────────────────────────────
  async function loadVdollarsBalance() {
    try {
      const data = await api('vdollars_balance');
      if (data && data.success && data.vdollars) {
        updateVdollarsBadge(data.vdollars.balance);
      }
    } catch (e) { /* silent */ }
  }

  function updateVdollarsBadge(balance) {
    const val = Math.floor(balance);
    // Sidebar badge
    const badge = document.getElementById('vdollars-badge');
    const amount = document.getElementById('vdollars-amount');
    if (badge && amount) {
      amount.textContent = val;
      badge.style.display = '';
      if (balance <= 5) { badge.style.color = '#f87171'; }
      else if (balance <= 20) { badge.style.color = '#fbbf24'; }
      else { badge.style.color = ''; }
    }
    // Header badge (always visible in chat)
    const hBadge = document.getElementById('vdollars-header-badge');
    const hAmount = document.getElementById('vdollars-header-amount');
    if (hBadge && hAmount) {
      hAmount.textContent = val;
      if (balance <= 5) { hBadge.classList.add('low'); hBadge.classList.remove('warn'); }
      else if (balance <= 20) { hBadge.classList.remove('low'); hBadge.classList.add('warn'); }
      else { hBadge.classList.remove('low', 'warn'); }
    }
  }

  // ── Init ─────────────────────────────────────────────────────
  async function init(user) {
    currentUser = user;
    // Theme is now applied globally via DOMContentLoaded — no duplicate here

    const input = document.getElementById('chat-input');
    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
      });
      input.addEventListener('input', () => autoResize(input));
    }

    const toggle = document.getElementById('menu-toggle');
    if (toggle) toggle.addEventListener('click', toggleSidebar);
    const overlay = document.getElementById('sidebar-overlay');
    if (overlay) overlay.addEventListener('click', closeSidebar);

    await loadConversations();

    // Check if user is currently banned
    await checkBanStatus();

    // Start periodic status check (online/sleeping/offline)
    startStatusPolling();

    // Load artifact badge counts
    loadArtifactCounts();

    // Load V$ balance
    loadVdollarsBalance();

    // Restore chat mode from localStorage
    initChatMode();
  }

  // ── Auth Pages ───────────────────────────────────────────────
  async function handleLogin(e) {
    e.preventDefault();
    const form = e.target;
    const email = form.querySelector('[name="email"]').value;
    const password = form.querySelector('[name="password"]').value;
    const errorEl = form.querySelector('.form-error');
    const result = await api('login', { email, password });
    if (result && result.success) {
      window.location.href = '/chat';
    } else if (errorEl) {
      errorEl.textContent = result?.error || 'Anmeldung fehlgeschlagen.';
      errorEl.classList.add('visible');
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    const form = e.target;
    const email = form.querySelector('[name="email"]').value;
    const displayName = form.querySelector('[name="display_name"]').value;
    const password = form.querySelector('[name="password"]').value;
    const dsgvo = form.querySelector('[name="dsgvo"]');
    const ki = form.querySelector('[name="ki_disclosure"]');
    const agb = form.querySelector('[name="agb"]');
    const tierInput = form.querySelector('[name="register_tier"]');
    const tier = tierInput ? tierInput.value : 'invited';
    const errorEl = form.querySelector('.form-error');
    if (dsgvo && !dsgvo.checked) {
      errorEl.textContent = 'Bitte stimme der Datenschutzerklärung zu.';
      errorEl.classList.add('visible');
      return;
    }
    if (ki && !ki.checked) {
      errorEl.textContent = 'Bitte nimm die KI-Kennzeichnung zur Kenntnis.';
      errorEl.classList.add('visible');
      return;
    }
    if (agb && !agb.checked) {
      errorEl.textContent = 'Bitte akzeptiere die Nutzungsbedingungen.';
      errorEl.classList.add('visible');
      return;
    }
    const action = tier === 'public' ? 'register_public' : 'register';
    const result = await api(action, { email, display_name: displayName, password });
    if (result && result.success) {
      window.location.href = tier === 'public' ? '/forum' : '/chat';
    } else if (errorEl) {
      errorEl.textContent = result?.error || 'Registrierung fehlgeschlagen.';
      errorEl.classList.add('visible');
    }
  }

  // ── Register Tier Switching ──────────────────────────────────
  function switchRegisterTier(tier) {
    document.querySelectorAll('.tier-tab').forEach(t => t.classList.toggle('active', t.dataset.tier === tier));
    const invitedInfo = document.getElementById('tier-info-invited');
    const publicInfo = document.getElementById('tier-info-public');
    const tierInput = document.getElementById('register_tier');
    if (invitedInfo) invitedInfo.style.display = tier === 'invited' ? '' : 'none';
    if (publicInfo) publicInfo.style.display = tier === 'public' ? '' : 'none';
    if (tierInput) tierInput.value = tier;
  }

  // ── Forum Functions ──────────────────────────────────────────
  let forumCurrentCategory = '';
  let forumCurrentPage = 1;
  let forumCurrentTopicId = null;

  async function apiFetch(url) {
    try {
      const resp = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
      const json = await resp.json();
      if (json.error === 'not_authenticated') { window.location.href = '/login'; return null; }
      return json;
    } catch (err) { console.error('[Portal API]', err); return null; }
  }

  async function forumSwitchCategory(cat) {
    forumCurrentCategory = cat;
    forumCurrentPage = 1;
    document.querySelectorAll('.forum-cat-tab').forEach(t => t.classList.toggle('active', t.dataset.cat === cat));
    await forumLoadTopics();
  }

  async function forumLoadTopics() {
    const container = document.getElementById('forum-topics');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;padding:2rem;">⏳ Laden...</div>';
    let url = `/api.php?action=forum_topics&page=${forumCurrentPage}`;
    if (forumCurrentCategory) url += `&category=${forumCurrentCategory}`;
    const data = await apiFetch(url);
    if (!data || !data.success) {
      container.innerHTML = '<div style="text-align:center;padding:2rem;">Fehler beim Laden.</div>';
      return;
    }
    if (!data.topics || data.topics.length === 0) {
      container.innerHTML = '<div style="text-align:center;padding:2rem;opacity:0.6;">Noch keine Beiträge in dieser Kategorie. Sei der Erste! ✨</div>';
      return;
    }
    const catIcons = {general:'💬', feedback:'📣', kreativ:'🎨', technik:'⚙️', offtopic:'🌀'};
    container.innerHTML = data.topics.map(t => {
      const icon = catIcons[t.category] || '💬';
      const date = new Date(t.created_at).toLocaleDateString('de-DE');
      const pinned = t.is_pinned ? '<span style="color:#eab308;" title="Angepinnt">📌</span> ' : '';
      const locked = t.is_locked ? '<span title="Gesperrt">🔒</span> ' : '';
      const aileyBadge = t.display_name === 'Ailey 💜' ? '<span class="badge" style="background:#a855f7;color:#fff;font-size:0.65rem;margin-left:4px;">KI</span>' : '';
      const avatarHtml = t.avatar_url
        ? `<img src="${escapeHtml(t.avatar_url)}" class="forum-user-avatar" alt="">`
        : `<span class="forum-user-avatar-placeholder">${escapeHtml((t.display_name||'?')[0].toUpperCase())}</span>`;
      const badgeHtml = t.equipped_badge ? `<span class="forum-user-badge">${_badgeEmojis[t.equipped_badge] || '🏅'}</span>` : '';
      return `<div class="forum-topic-card" onclick="Portal.forumOpenTopic('${t.id}')" style="cursor:pointer;">
        <div class="forum-topic-header">
          ${avatarHtml}
          <span class="forum-topic-cat">${icon}</span>
          <strong>${pinned}${locked}${escapeHtml(t.title)}</strong>
        </div>
        <div class="forum-topic-meta">
          <span>${escapeHtml(t.display_name)}${badgeHtml}${aileyBadge}</span> · <span>${date}</span> · <span>💬 ${t.reply_count || 0}</span> · <span>❤️ ${t.likes || 0}</span>
        </div>
      </div>`;
    }).join('');
    // Pagination
    const totalPages = Math.ceil(data.total / 20);
    const pag = document.getElementById('forum-pagination');
    if (pag && totalPages > 1) {
      let html = '';
      for (let p = 1; p <= totalPages; p++) {
        html += `<button class="btn btn-sm ${p === forumCurrentPage ? 'btn-primary' : 'btn-secondary'}" onclick="Portal.forumGoPage(${p})" style="margin:2px;">${p}</button>`;
      }
      pag.innerHTML = html;
    } else if (pag) {
      pag.innerHTML = '';
    }
  }

  async function forumGoPage(p) {
    forumCurrentPage = p;
    await forumLoadTopics();
  }

  async function forumOpenTopic(topicId) {
    forumCurrentTopicId = topicId;
    const listEl = document.querySelector('.forum-page');
    const detailEl = document.getElementById('forum-detail');
    const contentEl = document.getElementById('forum-detail-content');
    if (listEl) listEl.style.display = 'none';
    if (detailEl) detailEl.style.display = '';
    if (contentEl) contentEl.innerHTML = '<div style="text-align:center;padding:2rem;">⏳ Laden...</div>';

    const data = await apiFetch(`/api.php?action=forum_topic&topic_id=${topicId}`);
    if (!data || !data.success) {
      contentEl.innerHTML = '<div>Fehler beim Laden.</div>';
      return;
    }
    const t = data.topic;
    const likes = new Set(data.user_likes || []);
    const catIcons = {general:'💬', feedback:'📣', kreativ:'🎨', technik:'⚙️', offtopic:'🌀'};
    const icon = catIcons[t.category] || '💬';
    const date = new Date(t.created_at).toLocaleString('de-DE');
    const likeBtn = `<button class="btn btn-ghost btn-sm" onclick="Portal.forumLike('topic','${t.id}')" id="like-${t.id}">${likes.has(t.id) ? '❤️' : '🤍'} ${t.likes || 0}</button>`;
    const tAvatarHtml = t.avatar_url
      ? `<img src="${escapeHtml(t.avatar_url)}" class="forum-user-avatar" alt="">`
      : `<span class="forum-user-avatar-placeholder">${escapeHtml((t.display_name||'?')[0].toUpperCase())}</span>`;
    const tBadgeHtml = t.equipped_badge ? ` <span class="forum-user-badge">${_badgeEmojis[t.equipped_badge] || '🏅'}</span>` : '';
    let html = `<div class="forum-topic-detail card" style="padding:1.5rem;">
      <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;">
        <span>${icon}</span><h2 style="margin:0;">${escapeHtml(t.title)}</h2>
      </div>
      <div class="forum-topic-meta" style="margin-bottom:1rem;display:flex;align-items:center;gap:0.5rem;">
        ${tAvatarHtml}
        <span>${escapeHtml(t.display_name)}${tBadgeHtml}</span> · <span>${date}</span> ${likeBtn}
      </div>
      <div class="forum-topic-body">${escapeHtml(t.body).replace(/\n/g, '<br>')}</div>
    </div>`;

    // Replies
    if (data.replies && data.replies.length > 0) {
      html += '<div class="forum-replies" style="margin-top:1rem;">';
      data.replies.forEach(r => {
        const rDate = new Date(r.created_at).toLocaleString('de-DE');
        const aileyBadge = r.is_ailey ? '<span class="badge" style="background:#a855f7;color:#fff;font-size:0.65rem;margin-left:4px;">KI</span>' : '';
        const rLikeBtn = `<button class="btn btn-ghost btn-sm" onclick="Portal.forumLike('reply','${r.id}')" id="like-${r.id}">${likes.has(r.id) ? '❤️' : '🤍'} ${r.likes || 0}</button>`;
        const rAvatarHtml = r.avatar_url
          ? `<img src="${escapeHtml(r.avatar_url)}" class="forum-user-avatar" alt="">`
          : `<span class="forum-user-avatar-placeholder">${escapeHtml((r.display_name||'?')[0].toUpperCase())}</span>`;
        const rBadgeHtml = r.equipped_badge ? ` <span class="forum-user-badge">${_badgeEmojis[r.equipped_badge] || '🏅'}</span>` : '';
        html += `<div class="forum-reply card" style="padding:1rem;margin-bottom:0.5rem;">
          <div class="forum-reply-meta" style="display:flex;align-items:center;gap:0.5rem;">
            ${rAvatarHtml}
            <strong>${escapeHtml(r.display_name)}${rBadgeHtml}</strong>${aileyBadge} · ${rDate} ${rLikeBtn}
          </div>
          <div class="forum-reply-body" style="margin-top:0.5rem;">${escapeHtml(r.body).replace(/\n/g, '<br>')}</div>
        </div>`;
      });
      html += '</div>';
    }
    contentEl.innerHTML = html;
  }

  function forumBackToList() {
    forumCurrentTopicId = null;
    const listEl = document.querySelector('.forum-page');
    const detailEl = document.getElementById('forum-detail');
    if (listEl) listEl.style.display = '';
    if (detailEl) detailEl.style.display = 'none';
  }

  function forumShowNewTopic() {
    const el = document.getElementById('forum-new-topic');
    if (el) el.style.display = '';
  }
  function forumHideNewTopic() {
    const el = document.getElementById('forum-new-topic');
    if (el) el.style.display = 'none';
  }

  async function forumCreateTopic() {
    const category = document.getElementById('new-topic-category')?.value || 'general';
    const title = document.getElementById('new-topic-title')?.value?.trim();
    const body = document.getElementById('new-topic-body')?.value?.trim();
    const errorEl = document.getElementById('forum-topic-error');
    if (!title || title.length < 3) { if (errorEl) { errorEl.textContent = 'Titel muss mindestens 3 Zeichen haben.'; errorEl.classList.add('visible'); } return; }
    if (!body || body.length < 5) { if (errorEl) { errorEl.textContent = 'Beitrag muss mindestens 5 Zeichen haben.'; errorEl.classList.add('visible'); } return; }
    const data = await api('forum_create_topic', { category, title, body });
    if (data && data.success) {
      document.getElementById('new-topic-title').value = '';
      document.getElementById('new-topic-body').value = '';
      forumHideNewTopic();
      await forumLoadTopics();
      showToast('Beitrag erstellt! ✨');
    } else {
      if (errorEl) { errorEl.textContent = data?.error || 'Fehler beim Erstellen.'; errorEl.classList.add('visible'); }
    }
  }

  async function forumCreateReply() {
    if (!forumCurrentTopicId) return;
    const body = document.getElementById('forum-reply-body')?.value?.trim();
    const errorEl = document.getElementById('forum-reply-error');
    if (!body || body.length < 2) { if (errorEl) { errorEl.textContent = 'Antwort muss mindestens 2 Zeichen haben.'; errorEl.classList.add('visible'); } return; }
    const data = await api('forum_create_reply', { topic_id: forumCurrentTopicId, body });
    if (data && data.success) {
      document.getElementById('forum-reply-body').value = '';
      await forumOpenTopic(forumCurrentTopicId);
      showToast('Antwort gepostet! 💬');
    } else {
      if (errorEl) { errorEl.textContent = data?.error || 'Fehler beim Antworten.'; errorEl.classList.add('visible'); }
    }
  }

  async function forumLike(targetType, targetId) {
    const data = await api('forum_like', { target_type: targetType, target_id: targetId });
    if (data && data.success) {
      // Re-render the current topic
      if (forumCurrentTopicId) await forumOpenTopic(forumCurrentTopicId);
    }
  }

  function escapeHtml(s) {
    if (!s) return '';
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Forgot Password ─────────────────────────────────────────
  async function handleForgotPassword(e) {
    e.preventDefault();
    const form = e.target;
    const email = form.querySelector('[name="email"]').value;
    const errorEl = form.querySelector('.form-error');
    const successEl = form.querySelector('.form-success');
    const btn = form.querySelector('button[type="submit"]');
    if (errorEl) { errorEl.textContent = ''; errorEl.classList.remove('visible'); }
    if (successEl) { successEl.textContent = ''; successEl.classList.remove('visible'); }
    if (btn) { btn.disabled = true; btn.textContent = 'Sende…'; }

    const result = await api('request_password_reset', { email });
    if (btn) { btn.disabled = false; btn.textContent = 'Reset-Link senden'; }

    if (result && result.success && result.message) {
      if (successEl) {
        successEl.textContent = result.message;
        successEl.classList.add('visible');
      }
      // Hide the form after success
      form.querySelector('.form-group')?.parentElement?.querySelectorAll('.form-group').forEach(g => g.style.display = 'none');
      if (btn) btn.style.display = 'none';
    } else if (errorEl) {
      errorEl.textContent = result?.error || 'Ein Fehler ist aufgetreten.';
      errorEl.classList.add('visible');
    }
  }

  // ── Reset Password ──────────────────────────────────────────
  async function handleResetPassword(e) {
    e.preventDefault();
    const form = e.target;
    const token = form.querySelector('[name="token"]').value;
    const password = form.querySelector('[name="password"]').value;
    const passwordConfirm = form.querySelector('[name="password_confirm"]').value;
    const errorEl = form.querySelector('.form-error');
    const successEl = form.querySelector('.form-success');
    const btn = form.querySelector('button[type="submit"]');
    if (errorEl) { errorEl.textContent = ''; errorEl.classList.remove('visible'); }
    if (successEl) { successEl.textContent = ''; successEl.classList.remove('visible'); }

    if (password !== passwordConfirm) {
      if (errorEl) { errorEl.textContent = 'Passwörter stimmen nicht überein.'; errorEl.classList.add('visible'); }
      return;
    }
    if (password.length < 8) {
      if (errorEl) { errorEl.textContent = 'Passwort muss mindestens 8 Zeichen haben.'; errorEl.classList.add('visible'); }
      return;
    }

    if (btn) { btn.disabled = true; btn.textContent = 'Speichere…'; }
    const result = await api('reset_password', { token, password });
    if (btn) { btn.disabled = false; btn.textContent = 'Passwort ändern'; }

    if (result && result.success) {
      if (successEl) {
        successEl.textContent = result.message || 'Passwort geändert!';
        successEl.classList.add('visible');
      }
      // Hide form, show login link
      form.querySelectorAll('.form-group').forEach(g => g.style.display = 'none');
      if (btn) btn.style.display = 'none';
      // Redirect to login after 2 seconds
      setTimeout(() => { window.location.href = '/login'; }, 2500);
    } else if (errorEl) {
      errorEl.textContent = result?.error || 'Ein Fehler ist aufgetreten.';
      errorEl.classList.add('visible');
    }
  }

  // ── Copy / Download helpers ───────────────────────────────────
  // Store original code content before highlight.js mangles it
  const _codeStore = {};

  function _storeCode(id, code) {
    _codeStore[id] = code;
  }

  function _getCode(elId) {
    // 1. Check store (original, unmodified code)
    if (_codeStore[elId]) return _codeStore[elId];
    // 2. Fallback: read from DOM
    const el = document.getElementById(elId);
    if (!el) return '';
    // Prefer <code> child's textContent, then el's own
    const codeEl = el.querySelector('code');
    return (codeEl || el).textContent || '';
  }

  function copyMessage(idx) {
    const msg = messages[idx];
    if (!msg) return;
    navigator.clipboard.writeText(msg.content).then(() => showToast('Kopiert!'))
      .catch(() => showToast('Kopieren fehlgeschlagen'));
  }

  function copyCode(elId) {
    const text = _getCode(elId);
    if (!text) { showToast('Nichts zum Kopieren'); return; }
    navigator.clipboard.writeText(text).then(() => showToast('Code kopiert!'))
      .catch(() => {
        // Fallback for Mobile Safari / insecure contexts
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;left:-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showToast('Code kopiert!');
      });
  }

  function downloadCode(elId, filename, mime) {
    const text = _getCode(elId);
    if (!text) { showToast('Nichts zum Speichern'); return; }
    const blob = new Blob([text], { type: mime || 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename || 'code.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }

  // ── Web Search Toggle ─────────────────────────────────────
  function toggleWebSearch() {
    webSearchEnabled = !webSearchEnabled;
    const btn = document.getElementById('web-search-toggle');
    if (btn) {
      btn.classList.toggle('active', webSearchEnabled);
      btn.title = webSearchEnabled ? 'Web-Suche aktiv (klick zum Deaktivieren)' : 'Web-Suche aktivieren';
    }
  }

  // ── Thinking/Reasoning Toggle ─────────────────────────────
  function toggleThinking(thinkId) {
    const wrap = document.getElementById(thinkId);
    if (!wrap) return;
    const content = wrap.querySelector('.thinking-content');
    const btn = wrap.querySelector('.thinking-toggle');
    if (!content) return;
    const isOpen = content.style.display !== 'none';
    content.style.display = isOpen ? 'none' : '';
    wrap.classList.toggle('open', !isOpen);
    if (btn) btn.setAttribute('aria-expanded', !isOpen);
  }

  // ── Chat Mode Selector ──────────────────────────────────────
  // Mode metadata for the custom dropdown trigger label
  const _chatModeMeta = {
    hamster:  { name: 'Hamster',      cost: '0.2 V$', icon: null, emoji: '🐹' },
    nitro:    { name: 'A!ley Nitro',  cost: '0.5 V$', icon: 'zap' },
    normal:   { name: 'A!ley',        cost: '1 V$',   icon: 'message-circle' },
    thinking: { name: 'A!ley Tempest', cost: '2 V$',  icon: 'brain' },
    focus:    { name: 'A!ley SXE',    cost: '2 V$',   icon: 'minimize' },
  };

  function _renderChatModeTrigger(mode) {
    const label = document.getElementById('chat-mode-trigger-label');
    if (!label) return;
    const m = _chatModeMeta[mode] || _chatModeMeta.thinking;
    const iconHtml = m.emoji
      ? `<span class="chat-mode-trigger-icon" aria-hidden="true">${m.emoji}</span>`
      : `<span class="chat-mode-trigger-icon">${jsIcon(m.icon)}</span>`;
    label.innerHTML = `${iconHtml}<span class="chat-mode-trigger-name">${m.name}</span><span class="chat-mode-trigger-cost">${m.cost}</span>`;
  }

  function setChatMode(mode) {
    // Migrate old localStorage values
    if (mode === 'ultrafast') mode = 'hamster';
    if (mode === 'light') mode = 'focus';  // renamed light → focus
    if (mode === 'flash') mode = 'nitro';  // renamed flash → nitro
    if (!['hamster', 'nitro', 'normal', 'thinking', 'focus'].includes(mode)) mode = 'thinking';
    chatMode = mode;
    localStorage.setItem('ailey_chat_mode', mode);
    // Update legacy hidden select for compatibility
    const dropdown = document.getElementById('chat-mode-dropdown');
    if (dropdown) dropdown.value = mode;
    // Update custom dropdown trigger label + active item
    _renderChatModeTrigger(mode);
    document.querySelectorAll('.chat-mode-item').forEach(el => {
      el.classList.toggle('active', el.dataset.mode === mode);
    });
    // Legacy button support
    document.querySelectorAll('.chat-mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
  }

  function toggleChatModeDropdown(ev) {
    if (ev) ev.stopPropagation();
    const wrap = document.getElementById('chat-mode-custom');
    const trig = document.getElementById('chat-mode-trigger');
    if (!wrap) return;
    const isOpen = wrap.getAttribute('data-open') === 'true';
    wrap.setAttribute('data-open', isOpen ? 'false' : 'true');
    if (trig) trig.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
  }

  function closeChatModeDropdown() {
    const wrap = document.getElementById('chat-mode-custom');
    const trig = document.getElementById('chat-mode-trigger');
    if (wrap) wrap.setAttribute('data-open', 'false');
    if (trig) trig.setAttribute('aria-expanded', 'false');
  }

  function pickChatMode(mode) {
    setChatMode(mode);
    closeChatModeDropdown();
  }

  // Close custom dropdown on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#chat-mode-custom')) closeChatModeDropdown();
  });

  function initChatMode() {
    // Restore last saved mode from localStorage
    const saved = localStorage.getItem('ailey_chat_mode') || 'thinking';
    setChatMode(saved);
  }

  // ── Avatar Lightbox ───────────────────────────────────────
  function openAvatarLightbox(imgSrc, mood) {
    const lb = document.getElementById('avatar-lightbox');
    const img = document.getElementById('avatar-lightbox-img');
    const moodLabel = document.getElementById('avatar-lightbox-mood');
    if (!lb || !img) return;
    img.src = imgSrc || '/assets/ailey-default.jpg';
    if (moodLabel) {
      const moodNames = {
        neutral: 'Neutral', happy: 'Fröhlich', excited: 'Aufgeregt',
        sad: 'Traurig', thinking: 'Nachdenklich', confused: 'Verwirrt',
        angry: 'Verärgert', sleepy: 'Müde', tired: 'Erschöpft',
        playful: 'Verspielt', flirty: 'Kokett', funny: 'Lustig',
        loving: 'Verliebt', coding: 'Programmiert', writing: 'Schreibt',
        creative: 'Kreativ', music: 'Musikalisch',
      };
      moodLabel.textContent = moodNames[(mood || '').toLowerCase()] || '';
    }
    lb.classList.add('visible');
  }

  function closeAvatarLightbox(e) {
    if (e && e.target && e.target.closest('.avatar-lightbox-inner') && !e.target.closest('.avatar-lightbox-close')) return;
    const lb = document.getElementById('avatar-lightbox');
    if (lb) lb.classList.remove('visible');
  }

  // Click delegation for all .ailey-avatar elements
  document.addEventListener('click', (e) => {
    const avatar = e.target.closest('.ailey-avatar');
    if (!avatar) return;
    e.preventDefault();
    const src = avatar.src || avatar.querySelector('img')?.src || '/assets/ailey-default.jpg';
    const mood = avatar.dataset?.mood || currentMoodForTheme || 'neutral';
    openAvatarLightbox(src, mood);
  });

  // Escape key closes lightboxes
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeAvatarLightbox();
      // Also close generation lightbox if open
      if (typeof PortalTools !== 'undefined' && PortalTools.closeLightbox) {
        PortalTools.closeLightbox();
      }
    }
  });

  // ── Custom Instructions ─────────────────────────────────────
  async function loadPreferences() {
    const res = await api('get_preferences');
    if (res && res.success) return res.preferences || {};
    return {};
  }

  async function savePreferences(prefs) {
    const res = await api('save_preferences', prefs);
    if (res && res.success) showToast('Einstellungen gespeichert!');
    else showToast(res?.error || 'Speichern fehlgeschlagen');
  }

  // ── Artifact Tabs (Code / SVG) ──────────────────────────────
  let activeTab = 'chat';
  let artifactCache = { code: null, svg: null, image: null };

  function switchTab(tab) {
    if (tab === activeTab) return;
    activeTab = tab;

    // Update header-tab buttons
    document.querySelectorAll('.header-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    // Toggle panels
    const chatPanel   = document.getElementById('chat-messages');
    const inputArea   = document.querySelector('.chat-input-area');
    const codePanel   = document.getElementById('artifact-panel-code');
    const svgPanel    = document.getElementById('artifact-panel-svg');
    const songPanel   = document.getElementById('artifact-panel-song');
    const imagePanel  = document.getElementById('artifact-panel-image');
    const imagegenPanel = document.getElementById('artifact-panel-imagegen');
    const songgenPanel  = document.getElementById('artifact-panel-songgen');

    if (chatPanel) chatPanel.style.display = (tab === 'chat') ? '' : 'none';
    if (inputArea)  inputArea.style.display  = (tab === 'chat') ? '' : 'none';
    if (codePanel) codePanel.style.display = (tab === 'code') ? 'flex' : 'none';
    if (svgPanel)  svgPanel.style.display  = (tab === 'svg')  ? 'flex' : 'none';
    if (songPanel) songPanel.style.display = (tab === 'song') ? 'flex' : 'none';
    if (imagePanel) imagePanel.style.display = (tab === 'image') ? 'flex' : 'none';
    if (imagegenPanel) imagegenPanel.style.display = (tab === 'imagegen') ? 'flex' : 'none';
    if (songgenPanel)  songgenPanel.style.display  = (tab === 'songgen')  ? 'flex' : 'none';

    if (tab !== 'chat' && tab !== 'imagegen' && tab !== 'songgen') loadArtifacts(tab);
  }

  async function loadArtifacts(type) {
    const res = await api('artifacts', { type, limit: 50 });
    if (!res || !res.success) return;

    artifactCache[type] = res.artifacts || [];
    renderArtifacts(type);

    // Update both badge counts
    if (res.counts) {
      const codeBadge  = document.getElementById('tab-count-code');
      const svgBadge   = document.getElementById('tab-count-svg');
      const songBadge  = document.getElementById('tab-count-song');
      const imageBadge = document.getElementById('tab-count-image');
      if (codeBadge)  codeBadge.textContent  = res.counts.code  ? res.counts.code  : '';
      if (svgBadge)   svgBadge.textContent   = res.counts.svg   ? res.counts.svg   : '';
      if (songBadge)  songBadge.textContent  = res.counts.song  ? res.counts.song  : '';
      if (imageBadge) imageBadge.textContent = res.counts.image ? res.counts.image : '';
    }
  }

  function renderArtifacts(type) {
    const list = artifactCache[type] || [];
    const container = document.getElementById(`artifact-list-${type}`);
    const empty     = document.getElementById(`artifact-empty-${type}`);
    if (!container) return;

    if (!list.length) {
      container.innerHTML = '';
      if (empty) empty.style.display = '';
      return;
    }
    if (empty) empty.style.display = 'none';

    container.innerHTML = list.map((a, i) => {
      const uid = `artifact-${type}-${i}`;
      const langLabel = a.language ? `<span class="artifact-lang">${escHtml(a.language)}</span>` : '';
      const sizeLabel = a.size_bytes ? formatBytes(a.size_bytes) : '';
      const dateLabel = a.created_at ? new Date(a.created_at).toLocaleString('de-DE', { day:'2-digit', month:'2-digit', year:'2-digit', hour:'2-digit', minute:'2-digit' }) : '';

      let body = '';
      if (type === 'svg') {
        body = `<div class="svg-preview">${a.content}</div>`;
      } else if (type === 'song') {
        body = `<div class="song-lyrics"><pre class="song-pre">${escHtml(a.content)}</pre></div>`;
      } else if (type === 'image') {
        body = `<div class="image-preview">
          <img src="${escHtml(a.content)}" alt="${escHtml(a.title || 'Bild')}" loading="lazy"
               style="max-width:100%;max-height:500px;border-radius:12px;cursor:pointer;border:1px solid rgba(168,85,247,0.3);box-shadow:0 4px 12px rgba(168,85,247,0.1);"
               onclick="window.open('${escHtml(a.content)}','_blank')">
        </div>`;
      } else {
        body = `<pre class="code-pre"><code id="${uid}">${escHtml(a.content)}</code></pre>`;
      }

      const iconName = type === 'svg' ? 'pen-tool' : type === 'song' ? 'music' : type === 'image' ? 'image' : 'code';

      return `
        <div class="artifact-card">
          <div class="artifact-card-header">
            <span class="artifact-icon">${jsIcon(iconName)}</span>
            <div class="artifact-meta">
              <div class="artifact-title">${escHtml(a.title || 'Untitled')}</div>
              <div class="artifact-sub">${langLabel} ${sizeLabel} · ${dateLabel}</div>
            </div>
            <div class="artifact-actions">
              ${type === 'image'
                ? `<button class="artifact-action-btn" title="Öffnen" onclick="window.open('${escHtml(a.content)}','_blank')">${jsIcon('external-link')}</button>`
                : `<button class="artifact-action-btn" title="Kopieren" onclick="Portal.copyArtifact('${a.id}','${uid}','${type}')">${jsIcon('clipboard')}</button>`
              }
              <button class="artifact-action-btn" title="Download" onclick="Portal.downloadArtifact('${a.id}','${escHtml(a.title || 'artifact')}','${type}','${escHtml(a.language || '')}')">${jsIcon('save')}</button>
              <button class="artifact-action-btn submit-gallery-btn" title="In Galerie einreichen" onclick="Portal.submitToGallery('${a.id}')">${jsIcon('upload')}</button>
              <button class="artifact-action-btn delete-artifact-btn" title="Löschen" onclick="Portal.deleteArtifact('${a.id}','${type}')" style="color:#ef4444;">${jsIcon('trash-2')}</button>
            </div>
          </div>
          <div class="artifact-card-body">${body}</div>
        </div>`;
    }).join('');
  }

  function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function formatBytes(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1048576).toFixed(1) + ' MB';
  }

  function copyArtifact(id, uid, type) {
    // Try to grab from DOM first (for code), otherwise fetch
    const el = document.getElementById(uid);
    if (el) {
      navigator.clipboard.writeText(el.innerText).then(() => showToast('Kopiert!'))
        .catch(() => showToast('Kopieren fehlgeschlagen'));
      return;
    }
    // SVG — copy from cache
    const cached = (artifactCache[type] || []).find(a => a.id === id);
    if (cached) {
      navigator.clipboard.writeText(cached.content).then(() => showToast('Kopiert!'))
        .catch(() => showToast('Kopieren fehlgeschlagen'));
    }
  }

  function downloadArtifact(id, title, type, lang) {
    // For images, download directly via the image URL
    if (type === 'image') {
      const cached = (artifactCache.image || []).find(a => a.id === id);
      if (cached && cached.content) {
        const a = document.createElement('a');
        a.href = cached.content;
        a.download = (title || 'image') + '.png';
        a.target = '_blank';
        a.click();
        return;
      }
      window.open(`/api.php?action=artifact_download&id=${encodeURIComponent(id)}`, '_blank');
      return;
    }
    const ext = type === 'svg' ? '.svg' : (lang === 'python' ? '.py' : lang === 'javascript' ? '.js' : lang === 'html' ? '.html' : lang === 'css' ? '.css' : '.txt');
    const mime = type === 'svg' ? 'image/svg+xml' : 'text/plain';
    const cached = [...(artifactCache.code || []), ...(artifactCache.svg || []), ...(artifactCache.song || [])].find(a => a.id === id);
    if (cached) {
      const blob = new Blob([cached.content], { type: mime });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (title || 'artifact') + ext;
      a.click();
      URL.revokeObjectURL(a.href);
      return;
    }
    // Fallback: server download
    window.open(`/api.php?action=artifact_download&id=${encodeURIComponent(id)}`, '_blank');
  }

  async function deleteArtifact(artifactId, type) {
    const i18n = window._i18n || {};
    const confirmMsg = i18n.delete_artifact_confirm || 'Dieses Artefakt wirklich löschen?';
    if (!confirm(confirmMsg)) return;
    const btn = event && event.target ? event.target.closest('.delete-artifact-btn') : null;
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
      const res = await api('delete_artifact', { artifact_id: artifactId });
      if (res && res.success) {
        showToast(i18n.artifact_deleted || 'Artefakt gelöscht');
        // Re-fetch artifacts for this type
        const listRes = await api('artifacts', { type: type });
        if (listRes && listRes.success) {
          artifactCache[type] = listRes.artifacts || [];
          renderArtifacts(type);
          // Update badge counts
          if (listRes.counts) {
            const badge = document.getElementById(`tab-count-${type}`);
            if (badge) badge.textContent = listRes.counts[type] ? listRes.counts[type] : '';
          }
        }
      } else {
        showToast('Fehler: ' + (res?.error || 'unbekannt'));
        if (btn) { btn.disabled = false; btn.innerHTML = jsIcon('trash-2'); }
      }
    } catch (e) {
      showToast('Fehler beim Löschen');
      if (btn) { btn.disabled = false; btn.innerHTML = jsIcon('trash-2'); }
    }
  }

  async function submitToGallery(artifactId) {
    const btn = event && event.target ? event.target.closest('.submit-gallery-btn') : null;
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
      const res = await api('submit_to_gallery', { artifact_id: artifactId });
      if (res && res.success) {
        showToast('Eingereicht! Wird von Ailey geprüft ✨');
        if (btn) { btn.textContent = '✓'; btn.classList.add('submitted'); }
      } else if (res && res.error === 'already_submitted') {
        showToast('Bereits eingereicht');
        if (btn) { btn.textContent = '✓'; btn.classList.add('submitted'); }
      } else {
        showToast('Fehler: ' + (res?.error || 'unbekannt'));
        if (btn) { btn.disabled = false; btn.innerHTML = jsIcon('upload'); }
      }
    } catch (e) {
      showToast('Fehler beim Einreichen');
      if (btn) { btn.disabled = false; btn.innerHTML = jsIcon('upload'); }
    }
  }

  // ── Chat Message Rating ──────────────────────────────────────
  async function rateMessage(msgId, rating) {
    if (!currentConvId) return;
    const existing = chatRatings[msgId];
    // Toggle off if same rating
    const newRating = (existing && existing.rating === rating) ? 0 : rating;
    if (newRating === 0) {
      // Can't un-rate in our schema, just treat as neutral — skip
      return;
    }
    try {
      const res = await api('rate_message', {
        message_id: msgId,
        conversation_id: currentConvId,
        rating: newRating,
        comment: existing?.comment || null,
      });
      if (res && res.success) {
        chatRatings[msgId] = { rating: newRating, comment: existing?.comment || null };
        // Update buttons without full re-render
        const container = document.querySelector(`.msg-rating[data-msg-id="${msgId}"]`);
        if (container) {
          container.querySelector('.rate-up').classList.toggle('active', newRating === 1);
          container.querySelector('.rate-down').classList.toggle('active', newRating === -1);
        }
        showToast(newRating === 1 ? '👍 Danke!' : '👎 Notiert!', 'success');
        // Check for new badges
        if (res.new_badges && res.new_badges.length && window.showBadgePopups) {
          window.showBadgePopups(res.new_badges);
        }
      }
    } catch(e) { console.warn('Rate error', e); }
  }

  function toggleRatingComment(msgId) {
    const box = document.getElementById(`rate-comment-${msgId}`);
    if (box) box.style.display = box.style.display === 'none' ? 'flex' : 'none';
  }

  async function submitRatingComment(msgId) {
    const box = document.getElementById(`rate-comment-${msgId}`);
    if (!box) return;
    const input = box.querySelector('.msg-rate-comment-input');
    const comment = input?.value?.trim() || '';
    const existing = chatRatings[msgId];
    const rating = existing?.rating || 1;
    try {
      await api('rate_message', {
        message_id: msgId,
        conversation_id: currentConvId,
        rating: rating,
        comment: comment,
      });
      chatRatings[msgId] = { rating, comment };
      box.style.display = 'none';
      showToast('💬 Kommentar gespeichert', 'success');
    } catch(e) {}
  }

  // ── Badge Popup (achievement unlocked) ───────────────────────
  function showBadgePopup(badges) {
    if (!badges || !badges.length) return;
    badges.forEach((badge, i) => {
      setTimeout(() => {
        const popup = document.createElement('div');
        popup.className = 'badge-popup';
        const emoji = _badgeEmojis[badge.badge_id] || '🏅';
        popup.innerHTML = `
          <div class="badge-popup-inner">
            <div class="badge-popup-icon"><span style="font-size:2.5rem;">${emoji}</span></div>
            <div class="badge-popup-title">🏆 Achievement Unlocked!</div>
            <div class="badge-popup-name">${esc(badge.name_de || badge.name)}</div>
            <div class="badge-popup-ailey">${esc(badge.ailey_msg || '')}</div>
            <button class="btn btn-sm" onclick="this.closest('.badge-popup').remove()">Nice! 😎</button>
          </div>
        `;
        document.body.appendChild(popup);
        requestAnimationFrame(() => popup.classList.add('visible'));
        setTimeout(() => { popup.classList.remove('visible'); setTimeout(() => popup.remove(), 400); }, 8000);
      }, i * 2000);
    });
  }
  // Make globally available
  window.showBadgePopups = showBadgePopup;

  const _badgeEmojis = {
    'first_chat':'💬','chat_10':'🗣️','chat_100':'💭','chat_1000':'💍',
    'forum_starter':'📢','forum_regular':'🥜','forum_popular':'🌟',
    'gallery_critic':'⭐','gallery_commenter':'🖼️',
    'first_image':'🎨','first_song':'🎵','image_10':'🖌️','song_10':'🎤',
    'vdollars_100':'💰','vdollars_1000':'🐋',
    'rater_5':'📊','rater_50':'🍺','night_owl':'🦉',
    'profile_complete':'👤','week_streak':'🔥',
  };
  window.getBadgeSVG = function(badgeId, unlocked) {
    const emoji = _badgeEmojis[badgeId] || '🏅';
    return `<span style="font-size:2rem;${unlocked ? '' : 'filter:grayscale(1);opacity:0.4;'}">${emoji}</span>`;
  };

  // Load artifact counts on init so badges show even before user clicks a tab
  async function loadArtifactCounts() {
    const res = await api('artifacts', { type: 'code', limit: 0 });
    if (res && res.success && res.counts) {
      const codeBadge  = document.getElementById('tab-count-code');
      const svgBadge   = document.getElementById('tab-count-svg');
      const songBadge  = document.getElementById('tab-count-song');
      const imageBadge = document.getElementById('tab-count-image');
      if (codeBadge)  codeBadge.textContent  = res.counts.code  ? res.counts.code  : '';
      if (svgBadge)   svgBadge.textContent   = res.counts.svg   ? res.counts.svg   : '';
      if (songBadge)  songBadge.textContent  = res.counts.song  ? res.counts.song  : '';
      if (imageBadge) imageBadge.textContent = res.counts.image ? res.counts.image : '';
    }
  }

  // ── Interactive Blocks (choice/quiz/input) ───────────────────
  function pickOption(blockId, index, optionText) {
    const block = document.getElementById(blockId);
    if (!block || block.classList.contains('ia-answered')) return;

    const type = block.dataset.type;
    const correctIdx = parseInt(block.dataset.correct);
    const buttons = block.querySelectorAll('.interactive-option');

    block.classList.add('ia-answered');

    if (type === 'quiz' && correctIdx >= 0) {
      // Quiz mode: show correct/wrong feedback
      buttons.forEach((btn, i) => {
        btn.disabled = true;
        if (i === correctIdx) btn.classList.add('ia-correct');
        if (i === index && index !== correctIdx) btn.classList.add('ia-wrong');
      });
    } else {
      // Choice mode: highlight selected, disable all
      buttons.forEach((btn, i) => {
        btn.disabled = true;
        if (i === index) btn.classList.add('ia-selected');
      });
    }

    // Send as user message
    const input = document.getElementById('chat-input');
    if (input) {
      input.value = optionText;
      sendMessage();
    }
  }

  function submitInteractiveInput(blockId) {
    const block = document.getElementById(blockId);
    if (!block || block.classList.contains('ia-answered')) return;

    const inputEl = block.querySelector('.interactive-input');
    if (!inputEl || !inputEl.value.trim()) return;

    const value = inputEl.value.trim();
    block.classList.add('ia-answered');
    inputEl.disabled = true;
    const btn = block.querySelector('.interactive-submit');
    if (btn) btn.disabled = true;

    // Send as user message
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
      chatInput.value = value;
      sendMessage();
    }
  }

  // ── 🎵 Song-Button (Heuristik-getriggert) ─────────────────────
  const _songPollers = new Map(); // idx → setTimeout handle

  function renderSongPanel(m, idx) {
    const det = m.song_detected || {};
    const gen = m.song_gen || null;

    // ── Done state: inline audio player + download + cover ──
    if (gen && gen.status === 'done' && gen.mp3_url) {
      const cover = gen.cover_url ? `<img src="${esc(gen.cover_url)}" alt="Cover" style="width:64px;height:64px;border-radius:8px;object-fit:cover;flex:none;">` : '';
      return `<div class="song-panel song-panel-done" style="margin-top:8px;padding:10px;border-radius:12px;background:linear-gradient(135deg,rgba(168,85,247,0.08),rgba(236,72,153,0.06));border:1px solid rgba(168,85,247,0.25);">
        <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px;">
          ${cover}
          <div style="flex:1;min-width:0;">
            <div style="font-weight:600;font-size:0.85rem;">🎵 ${esc(gen.title || det.title || 'Song')}</div>
            <div style="font-size:0.7rem;opacity:0.6;">Auch in deiner Gallery gespeichert</div>
          </div>
        </div>
        <audio controls preload="metadata" style="width:100%;height:36px;" src="${esc(gen.mp3_url)}"></audio>
        <div style="margin-top:6px;display:flex;gap:6px;">
          <a href="${esc(gen.mp3_url)}" download class="suggestion-chip" style="font-size:0.72rem;">💾 Download MP3</a>
        </div>
      </div>`;
    }

    // ── Running state: progress + spinner ──
    if (gen && (gen.status === 'running' || gen.status === 'queued' || gen.status === 'pending')) {
      return `<div class="song-panel song-panel-running" style="margin-top:8px;padding:10px;border-radius:12px;background:rgba(168,85,247,0.06);border:1px solid rgba(168,85,247,0.2);">
        <div style="display:flex;gap:8px;align-items:center;font-size:0.8rem;">
          <span style="display:inline-block;width:14px;height:14px;border:2px solid rgba(168,85,247,0.3);border-top-color:#a855f7;border-radius:50%;animation:spin 0.8s linear infinite;"></span>
          <span><strong>🎵 ${esc(gen.title || det.title || 'Song')}</strong> wird generiert…</span>
        </div>
        <div style="margin-top:4px;font-size:0.7rem;opacity:0.65;">${esc(gen.progress || 'Bitte warten – kann 2-5 min dauern.')}</div>
      </div>`;
    }

    // ── Error state ──
    if (gen && gen.status === 'failed') {
      return `<div class="song-panel song-panel-error" style="margin-top:8px;padding:10px;border-radius:12px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);">
        <div style="font-size:0.8rem;color:#fca5a5;">❌ Song-Generierung fehlgeschlagen</div>
        <div style="font-size:0.7rem;opacity:0.7;margin-top:2px;">${esc(gen.error || 'Unbekannter Fehler')}</div>
        <button class="suggestion-chip" onclick="Portal.openSongModal(${idx})" style="margin-top:6px;font-size:0.72rem;">🔄 Nochmal versuchen</button>
      </div>`;
    }

    // ── Default: idle → show button(s) ──
    const needsMeta = det.needs_metadata === true;
    const quickLabel = needsMeta ? '🎵 Song generieren (Optionen wählen)' : '🎵 Song direkt generieren';
    const quickAction = needsMeta ? `Portal.openSongModal(${idx})` : `Portal.generateSongQuick(${idx})`;
    return `<div class="song-panel song-panel-idle" style="margin-top:8px;padding:8px 10px;border-radius:10px;background:rgba(168,85,247,0.06);border:1px dashed rgba(168,85,247,0.3);display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <span style="font-size:0.72rem;opacity:0.75;">Sieht nach Songtext aus${det.title ? ` ("${esc(det.title)}")` : ''} 🎶</span>
      <button class="suggestion-chip" onclick="${quickAction}" style="font-size:0.72rem;background:rgba(168,85,247,0.15);border-color:rgba(168,85,247,0.4);">${quickLabel}</button>
      ${!needsMeta ? `<button class="suggestion-chip" onclick="Portal.openSongModal(${idx})" style="font-size:0.72rem;">⚙️ Optionen</button>` : ''}
    </div>`;
  }

  function openSongModal(idx) {
    const m = messages[idx];
    if (!m) return;
    const det = m.song_detected || {};
    const title = det.title || 'Untitled';
    const genre = det.suggested_genre || '';
    const mood  = det.suggested_mood || '';
    const tags  = det.suggested_tags || '';
    const dur   = 180;

    // Build modal
    let modal = document.getElementById('song-gen-modal');
    if (modal) modal.remove();
    modal = document.createElement('div');
    modal.id = 'song-gen-modal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.65);display:flex;align-items:center;justify-content:center;z-index:9999;backdrop-filter:blur(4px);';
    modal.innerHTML = `
      <div style="background:var(--bg-panel,#1a1a1f);border-radius:16px;padding:20px;max-width:480px;width:90%;border:1px solid rgba(168,85,247,0.3);box-shadow:0 20px 60px rgba(0,0,0,0.5);">
        <h3 style="margin:0 0 14px 0;font-size:1.1rem;">🎵 Song generieren</h3>
        <div style="display:flex;flex-direction:column;gap:10px;">
          <label style="font-size:0.78rem;">Titel
            <input id="song-mod-title" value="${esc(title)}" style="width:100%;margin-top:3px;padding:6px 8px;border-radius:6px;border:1px solid rgba(255,255,255,0.15);background:rgba(0,0,0,0.3);color:inherit;font-size:0.85rem;">
          </label>
          <div style="display:flex;gap:8px;">
            <label style="flex:1;font-size:0.78rem;">Genre
              <select id="song-mod-genre" style="width:100%;margin-top:3px;padding:6px 8px;border-radius:6px;border:1px solid rgba(255,255,255,0.15);background:rgba(0,0,0,0.3);color:inherit;font-size:0.85rem;">
                ${['','pop','rock','metal','punk','grunge','rap','k-pop','k-rap','ballad','electronic','industrial','acoustic','folk'].map(g => `<option value="${g}" ${g===genre?'selected':''}>${g||'— Auto —'}</option>`).join('')}
              </select>
            </label>
            <label style="flex:1;font-size:0.78rem;">Mood
              <select id="song-mod-mood" style="width:100%;margin-top:3px;padding:6px 8px;border-radius:6px;border:1px solid rgba(255,255,255,0.15);background:rgba(0,0,0,0.3);color:inherit;font-size:0.85rem;">
                ${['','dark','bright','introspective','energetic','melancholic','aggressive','romantic'].map(mo => `<option value="${mo}" ${mo===mood?'selected':''}>${mo||'— Auto —'}</option>`).join('')}
              </select>
            </label>
          </div>
          <label style="font-size:0.78rem;">Extra Tags (optional, kommagetrennt)
            <input id="song-mod-tags" value="${esc(tags)}" placeholder="z.B. 140bpm, female vocal, distorted guitar" style="width:100%;margin-top:3px;padding:6px 8px;border-radius:6px;border:1px solid rgba(255,255,255,0.15);background:rgba(0,0,0,0.3);color:inherit;font-size:0.85rem;">
          </label>
          <label style="font-size:0.78rem;">Dauer (Sekunden)
            <input id="song-mod-duration" type="number" min="30" max="240" value="${dur}" style="width:100%;margin-top:3px;padding:6px 8px;border-radius:6px;border:1px solid rgba(255,255,255,0.15);background:rgba(0,0,0,0.3);color:inherit;font-size:0.85rem;">
          </label>
          <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:8px;">
            <button onclick="Portal.closeSongModal()" class="suggestion-chip">Abbrechen</button>
            <button onclick="Portal.submitSongRequest(${idx})" class="suggestion-chip" style="background:rgba(168,85,247,0.3);border-color:rgba(168,85,247,0.5);">🎵 Los geht's</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) closeSongModal(); });
  }

  function closeSongModal() {
    const m = document.getElementById('song-gen-modal');
    if (m) m.remove();
  }

  function generateSongQuick(idx) {
    // Use heuristic defaults — no modal
    const m = messages[idx];
    if (!m) return;
    const det = m.song_detected || {};
    _submitSong(idx, {
      title: det.title || 'Untitled',
      genre: det.suggested_genre || '',
      mood:  det.suggested_mood  || '',
      tags:  det.suggested_tags  || '',
      duration: 180,
    });
  }

  async function submitSongRequest(idx) {
    const title = (document.getElementById('song-mod-title')?.value || 'Untitled').trim();
    const genre = (document.getElementById('song-mod-genre')?.value || '').trim();
    const mood  = (document.getElementById('song-mod-mood')?.value  || '').trim();
    const tags  = (document.getElementById('song-mod-tags')?.value  || '').trim();
    const duration = Math.max(30, Math.min(240, parseInt(document.getElementById('song-mod-duration')?.value || '180', 10) || 180));
    closeSongModal();
    await _submitSong(idx, { title, genre, mood, tags, duration });
  }

  async function _submitSong(idx, opts) {
    const m = messages[idx];
    if (!m) return;
    const lyrics = m.content || '';
    if (lyrics.length < 40) { showToast('Text zu kurz für Song-Generierung.'); return; }

    m.song_gen = { status: 'pending', progress: 'Sende Anfrage…', title: opts.title };
    renderMessages();

    const res = await api('request_song', {
      lyrics,
      title: opts.title,
      genre: opts.genre,
      mood:  opts.mood,
      tags:  opts.tags,
      duration: opts.duration,
      source_queue_id: m.queue_id || '',
    });

    if (!res || !res.success) {
      m.song_gen = { status: 'failed', error: (res && (res.message || res.error)) || 'Anfrage fehlgeschlagen' };
      renderMessages();
      return;
    }

    m.song_gen = { status: 'queued', request_id: res.request_id, progress: 'In Warteschlange…', title: opts.title };
    renderMessages();
    _startSongPolling(idx, res.request_id);
  }

  function _startSongPolling(idx, requestId) {
    if (_songPollers.has(idx)) { clearTimeout(_songPollers.get(idx)); }
    let attempts = 0;
    const MAX = 200; // ~200 * 5s = 16 min

    const tick = async () => {
      attempts++;
      if (attempts > MAX) {
        const m = messages[idx];
        if (m && m.song_gen) {
          m.song_gen.status = 'failed';
          m.song_gen.error = 'Timeout — bitte später neu laden.';
          renderMessages();
        }
        _songPollers.delete(idx);
        return;
      }
      const st = await api(`check_song_status&request_id=${encodeURIComponent(requestId)}`);
      const m = messages[idx];
      if (!m) { _songPollers.delete(idx); return; }
      if (!st || !st.success) {
        // Network glitch — keep trying
        _songPollers.set(idx, setTimeout(tick, 5000));
        return;
      }
      m.song_gen = {
        status: st.status,
        progress: st.progress || '',
        title: st.title || (m.song_gen && m.song_gen.title) || 'Song',
        mp3_url: st.mp3_url || null,
        cover_url: st.cover_url || null,
        error: st.error || null,
        request_id: requestId,
      };
      renderMessages();
      if (st.status === 'done' || st.status === 'failed') {
        _songPollers.delete(idx);
        if (st.status === 'done') showToast('🎵 Song fertig!');
        return;
      }
      // Poll faster while running, slower while queued
      const next = (st.status === 'running') ? 4000 : 6000;
      _songPollers.set(idx, setTimeout(tick, next));
    };
    _songPollers.set(idx, setTimeout(tick, 1500));
  }

  // Inject spin keyframes once
  if (typeof document !== 'undefined' && !document.getElementById('song-panel-anim')) {
    const styleEl = document.createElement('style');
    styleEl.id = 'song-panel-anim';
    styleEl.textContent = '@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}';
    if (document.head) document.head.appendChild(styleEl);
    else document.addEventListener('DOMContentLoaded', () => document.head && document.head.appendChild(styleEl));
  }

  // ── Public API ───────────────────────────────────────────────
  return {
    init, getTheme, setTheme, applyMoodColors, sendMessage, stopGeneration, openConversation, newConversation,
    deleteConversation, fillInput, toggleSidebar, toggleWebSearch, setChatMode,
    pickChatMode, toggleChatModeDropdown, closeChatModeDropdown,
    pickOption, submitInteractiveInput,
    toggleThinking,
    openAvatarLightbox, closeAvatarLightbox,
    handleLogin, handleRegister, handleForgotPassword, handleResetPassword, deleteMyData, logout, showToast,
    copyMessage, copyCode, downloadCode,
    loadVdollarsBalance, updateVdollarsBadge,
    savePreferences, loadPreferences,
    switchTab, copyArtifact, downloadArtifact, submitToGallery, deleteArtifact,
    fillAndSend, checkBanStatus,
    handleChatFileSelect, clearPendingFile,
    switchRegisterTier,
    forumSwitchCategory, forumLoadTopics, forumGoPage, forumOpenTopic, forumBackToList,
    forumShowNewTopic, forumHideNewTopic, forumCreateTopic, forumCreateReply, forumLike,
    rateMessage, toggleRatingComment, submitRatingComment,
    openSongModal, closeSongModal, submitSongRequest, generateSongQuick,
  };
})();

// Apply saved theme immediately (all pages, not just chat)
// NOTE: script loads in <head>, so document.body may not exist yet.
// We set data-theme on <html> immediately, and defer body class to DOMContentLoaded.
(() => {
  const theme = localStorage.getItem('ailey-portal-theme') || 'ailey';
  document.documentElement.setAttribute('data-theme', theme);
})();

// Global theme init: bind theme-option clicks & apply mood on ALL pages
document.addEventListener('DOMContentLoaded', () => {
  // Apply theme (triggers mood color restore from localStorage)
  Portal.setTheme(Portal.getTheme ? Portal.getTheme() : (localStorage.getItem('ailey-portal-theme') || 'ailey'));

  // Radial menu is initialized via inline <script> in layout.php (after the overlay DOM)
  // No duplicate initialization needed here.

  // Bind all .theme-option elements (settings page, nav switcher, etc.)
  document.querySelectorAll('.theme-option').forEach(el => {
    el.addEventListener('click', () => {
      Portal.setTheme(el.dataset.theme);
      // Close dropdown if inside nav switcher
      const dd = document.getElementById('nav-theme-dropdown');
      if (dd) dd.classList.remove('open');
    });
  });

  // Nav theme-switcher dropdown toggle
  const toggleBtn = document.getElementById('nav-theme-toggle');
  const dropdown  = document.getElementById('nav-theme-dropdown');
  if (toggleBtn && dropdown) {
    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });
    // Close on click outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.nav-theme-switcher')) {
        dropdown.classList.remove('open');
      }
    });
  }

  // On public pages (no chat), fetch Ailey's mood from API for theme coloring
  if (!document.getElementById('chat-messages')) {
    fetch('/api.php?action=get_ailey_status')
      .then(r => r.json())
      .then(data => {
        if (data && data.success && data.mood) {
          Portal.applyMoodColors(data.mood);
        }
      })
      .catch(() => { /* offline — localStorage mood is already applied */ });
  }

  // Auto-load forum topics if on forum page
  if (document.querySelector('.forum-page')) {
    Portal.forumLoadTopics();
  }
});
