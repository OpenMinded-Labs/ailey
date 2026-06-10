<?php
/**
 * A!ley Portal — Cinematic Intro Page v7
 * - Dynamic binary portraits from latest gallery images (clientside conversion)
 * - WebGL-accelerated particle rendering (GPU)
 * - Glitch keyword ticker from latest outputs (songs, images, books, code)
 * - Mixed typography story overlays with i18n
 * - Fallback to Canvas 2D if WebGL unavailable
 * - Fallback to static morph-data.js if API fails
 */
?>
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>A!ley — Meet the Machine</title>
<meta name="description" content="A!ley — Autonomous AI artist, author, musician. Not a chatbot. A personality.">
<meta name="robots" content="index, follow">
<?php
  // Social-share preview (this standalone intro page has no $config).
  // Canonical domain hardcoded so previews always resolve to the primary domain,
  // even when reached via the sexngears subdomain. Cache-bust via filemtime.
  $introBase   = 'https://hey-ailey.com';
  $introOgFile = __DIR__ . '/../assets/og-image.png';
  $introOgVer  = is_file($introOgFile) ? filemtime($introOgFile) : null;
  $introOg     = $introBase . '/assets/og-image.png' . ($introOgVer ? "?v=$introOgVer" : '');
?>
<link rel="canonical" href="<?= $introBase ?>/">
<!-- Open Graph / social sharing (WhatsApp, Facebook, LinkedIn, …) -->
<meta property="og:type" content="website">
<meta property="og:title" content="A!ley — Meet the Machine">
<meta property="og:description" content="Autonome KI-Künstlerin — Musik, Kunst &amp; Geschichten. Kein Chatbot. Eine Persönlichkeit.">
<meta property="og:url" content="<?= $introBase ?>/">
<meta property="og:image" content="<?= htmlspecialchars($introOg) ?>">
<meta property="og:image:secure_url" content="<?= htmlspecialchars($introOg) ?>">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="A!ley — Autonome KI-Künstlerin">
<meta property="og:site_name" content="A!ley">
<meta property="og:locale" content="de_DE">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="A!ley — Meet the Machine">
<meta name="twitter:description" content="Autonome KI-Künstlerin — Musik, Kunst &amp; Geschichten. Kein Chatbot. Eine Persönlichkeit.">
<meta name="twitter:image" content="<?= htmlspecialchars($introOg) ?>">
<meta name="twitter:image:alt" content="A!ley — Autonome KI-Künstlerin">
<meta name="theme-color" content="#0a0a0a">
<!-- Favicons (Ailey app icon) -->
<link rel="icon" href="/assets/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon-32.png">
<link rel="icon" type="image/png" sizes="192x192" href="/assets/favicon.png">
<link rel="apple-touch-icon" href="/assets/apple-icon.png">
<link rel="manifest" href="/assets/site.webmanifest">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Share+Tech+Mono&family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#050508;color:#fff;font-family:'Inter',sans-serif}
canvas{position:fixed;top:0;left:0;width:100%;height:100%;z-index:1}

/* ── Story overlay ── */
#story{position:fixed;bottom:0;left:0;width:100%;z-index:20;pointer-events:none;
  background:linear-gradient(transparent,rgba(5,5,8,.82) 28%,rgba(5,5,8,.95));
  padding:4vh 6vw 5vh;opacity:0;transition:opacity .7s;min-height:44vh;
  display:flex;flex-direction:column;justify-content:flex-end;align-items:center}
#story.visible{opacity:1}
#story-text{margin-bottom:1.2vh;text-align:center;max-width:750px;padding:0 1.5rem}

/* Small lead-in lines */
.sl{display:block;font-size:clamp(14px,2.2vw,22px);font-weight:300;color:rgba(255,255,255,.55);
  letter-spacing:.06em;line-height:1.7;margin-bottom:.2rem;font-family:'Inter',sans-serif}

/* BIG catchy statement lines */
.bl{display:block;font-size:clamp(26px,5vw,56px);font-weight:600;color:#f0f0f5;
  line-height:1.25;letter-spacing:-.01em;margin:.15rem 0;font-family:'Inter',sans-serif}
.accent{color:#ff2d8a;font-weight:700;text-shadow:0 0 30px rgba(255,45,138,.2)}
.cyan{color:#00ffcc;font-weight:700;text-shadow:0 0 30px rgba(0,255,204,.2)}
.glow-word{background:linear-gradient(135deg,#ff2d8a,#a855f7);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  font-weight:900;filter:drop-shadow(0 0 12px rgba(168,85,247,.3))}

/* Decorative separator */
.story-sep{width:60px;height:1px;margin:1rem auto .8rem;
  background:linear-gradient(90deg,transparent,rgba(255,45,138,.4),rgba(0,255,204,.3),transparent);
  opacity:0;transition:opacity .6s ease .3s}
#story.visible .story-sep{opacity:1}

/* ── Sub-Tags ── */
#story-sub{display:flex;flex-wrap:wrap;justify-content:center;gap:.5rem .65rem;
  padding:0 1.5rem;max-width:600px}
.tag{font-family:'Share Tech Mono',monospace;letter-spacing:.18em;text-transform:uppercase;
  padding:.3rem .85rem;border-radius:20px;white-space:nowrap;
  opacity:0;transform:translateY(8px);transition:opacity .5s ease,transform .5s ease}
#story.visible .tag{opacity:1;transform:translateY(0)}
#story.visible .tag:nth-child(1){transition-delay:.15s}
#story.visible .tag:nth-child(2){transition-delay:.3s}
#story.visible .tag:nth-child(3){transition-delay:.45s}
#story.visible .tag:nth-child(4){transition-delay:.6s}
.tag.primary{font-size:clamp(.6rem,1.3vw,.78rem);color:#ff4da6;
  border:1px solid rgba(255,77,166,.25);background:rgba(255,45,138,.08)}
.tag.secondary{font-size:clamp(.48rem,1vw,.62rem);color:#5a5a7a;
  border:1px solid rgba(90,90,122,.18);background:rgba(90,90,122,.05)}
.tag.glow{font-size:clamp(.6rem,1.3vw,.78rem);color:#00ffcc;
  border-color:rgba(0,255,204,.3);background:rgba(0,255,204,.07);
  box-shadow:0 0 12px rgba(0,255,204,.12);animation:tagPulse 2.5s ease-in-out infinite}
@keyframes tagPulse{0%,100%{box-shadow:0 0 12px rgba(0,255,204,.1)}50%{box-shadow:0 0 20px rgba(0,255,204,.25)}}

/* ── Keyword Glitch Ticker ── */
#ticker{position:fixed;top:0;left:0;width:100%;height:100%;z-index:15;pointer-events:none;overflow:hidden}
.ticker-word{position:absolute;left:50%;font-family:'Share Tech Mono',monospace;
  white-space:nowrap;opacity:0;will-change:transform,opacity;
  text-transform:uppercase;letter-spacing:.12em;
  text-shadow:0 0 12px currentColor,0 0 30px currentColor;
  max-width:80vw;overflow:hidden}
.ticker-word .tk-inner{display:inline-block;white-space:nowrap}
.ticker-word.song{color:#ff3c8e}
.ticker-word.image{color:#00ffcc}
.ticker-word.book{color:#c084fc}
.ticker-word.svg{color:#fbbf24}
.ticker-word.code{color:#38bdf8}

/* Anim 1: Glitch-in → explode right */
@keyframes tkGlitchRight{
  0%{opacity:0;transform:translateX(-50%) scaleX(1.6) skewX(-12deg);filter:blur(6px)}
  8%{opacity:1;transform:translateX(-50%) scaleX(1) skewX(0);filter:blur(0)}
  12%{opacity:1;transform:translateX(-48%) skewX(3deg)}
  16%{opacity:1;transform:translateX(-52%) skewX(-2deg)}
  20%{opacity:1;transform:translateX(-50%) skewX(0)}
  65%{opacity:.8;transform:translateX(-50%);filter:blur(0)}
  100%{opacity:0;transform:translateX(40vw) scaleX(2) skewX(15deg);filter:blur(8px)}
}
/* Anim 2: Glitch-in → explode left */
@keyframes tkGlitchLeft{
  0%{opacity:0;transform:translateX(-50%) scaleX(1.6) skewX(12deg);filter:blur(6px)}
  8%{opacity:1;transform:translateX(-50%) scaleX(1) skewX(0);filter:blur(0)}
  12%{opacity:1;transform:translateX(-52%) skewX(-3deg)}
  16%{opacity:1;transform:translateX(-48%) skewX(2deg)}
  20%{opacity:1;transform:translateX(-50%) skewX(0)}
  65%{opacity:.8;transform:translateX(-50%);filter:blur(0)}
  100%{opacity:0;transform:translateX(-140%) scaleX(2) skewX(-15deg);filter:blur(8px)}
}
/* Anim 3: Fade-up → dissolve upward */
@keyframes tkRiseDissolve{
  0%{opacity:0;transform:translateX(-50%) translateY(20px) scale(.9);filter:blur(3px)}
  12%{opacity:1;transform:translateX(-50%) translateY(0) scale(1);filter:blur(0)}
  60%{opacity:.8;transform:translateX(-50%) translateY(0);filter:blur(0)}
  100%{opacity:0;transform:translateX(-50%) translateY(-60px) scaleY(1.8) scaleX(.7);filter:blur(6px)}
}
/* Anim 4: Scale-punch → scatter/shatter */
@keyframes tkPunchShatter{
  0%{opacity:0;transform:translateX(-50%) scale(0.3);filter:blur(4px)}
  6%{opacity:1;transform:translateX(-50%) scale(1.15);filter:blur(0)}
  10%{opacity:1;transform:translateX(-50%) scale(.95)}
  15%{opacity:1;transform:translateX(-50%) scale(1)}
  60%{opacity:.85;transform:translateX(-50%) scale(1);filter:blur(0)}
  80%{opacity:.4;transform:translateX(-50%) scale(1.1) rotate(2deg);filter:blur(1px)}
  100%{opacity:0;transform:translateX(-50%) scale(2.5) rotate(8deg);filter:blur(12px)}
}
/* Anim 5: Typewriter flash → glitch-out */
@keyframes tkFlashOut{
  0%{opacity:0;transform:translateX(-50%);clip-path:inset(0 100% 0 0)}
  15%{opacity:1;transform:translateX(-50%);clip-path:inset(0 0 0 0)}
  18%{opacity:.3;transform:translateX(-50%)}
  20%{opacity:1;transform:translateX(-50%)}
  60%{opacity:.9;transform:translateX(-50%);filter:blur(0)}
  75%{opacity:.7;transform:translateX(-48%) skewX(5deg);filter:blur(0)}
  80%{opacity:.3;transform:translateX(-53%) skewX(-8deg);filter:blur(2px)}
  85%{opacity:.5;transform:translateX(-50%) skewX(3deg);filter:blur(0)}
  100%{opacity:0;transform:translateX(-50%) skewX(-12deg) scaleX(1.5);filter:blur(6px)}
}
/* Long-text inner scroll: text slides left inside the clipped box */
@keyframes tkScrollInner{
  0%{transform:translateX(0)}
  20%{transform:translateX(0)}
  80%{transform:translateX(var(--scroll-dist))}
  100%{transform:translateX(var(--scroll-dist))}
}

/* ── Frame counter ── */
#frame-counter{position:fixed;top:1.2rem;right:1.5rem;z-index:18;
  font-family:'Share Tech Mono',monospace;font-size:clamp(.5rem,.9vw,.6rem);
  color:#2a2a3f;letter-spacing:.2em;opacity:0;transition:opacity .6s ease}
#frame-counter.visible{opacity:1}

/* ── ENDFRAME ── */
#endframe{position:fixed;top:0;left:0;right:0;bottom:0;z-index:20;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  pointer-events:none;opacity:0;transition:opacity 2.5s ease}
#endframe.visible{opacity:1;pointer-events:auto}
.ef-pre{font-family:'Share Tech Mono',monospace;font-size:clamp(1rem,2.2vw,1.6rem);
  color:#99a;letter-spacing:.5em;margin-bottom:.4rem}
.ef-name{font-family:'Orbitron',sans-serif;font-size:clamp(4.5rem,14vw,11rem);font-weight:900;
  letter-spacing:.08em;line-height:1;
  background:linear-gradient(135deg,#ff2d8a 0%,#ff6db8 25%,#a855f7 50%,#00ffcc 75%,#ff2d8a 100%);
  background-size:400% 400%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;color:transparent;animation:grad 5s ease-in-out infinite;
  filter:drop-shadow(0 0 30px rgba(255,45,138,.3)) drop-shadow(0 0 60px rgba(168,85,247,.15))}
.ef-tagline{font-family:'Inter',sans-serif;font-weight:300;
  font-size:clamp(.85rem,1.6vw,1.1rem);color:#bbc;letter-spacing:.06em;
  max-width:520px;text-align:center;line-height:1.7;margin-top:1.4rem}
.ef-tagline .pink{color:#ff6dbf}
.ef-tagline .cyan{color:#33ffd4}
.ef-tech{font-family:'Share Tech Mono',monospace;font-size:clamp(.7rem,1.1vw,.85rem);
  color:#889;letter-spacing:.2em;margin-top:1rem;
  text-shadow:0 0 12px rgba(168,85,247,.2)}
.ef-enter{position:relative;z-index:25;margin-top:2.2rem;display:inline-block;
  padding:.95rem 2.8rem;background:linear-gradient(135deg,#ff2d8a,#a855f7);
  color:#fff;font-family:'Inter',sans-serif;font-weight:600;font-size:1rem;
  border:none;border-radius:12px;cursor:pointer;letter-spacing:.04em;text-decoration:none;
  box-shadow:0 4px 20px rgba(168,85,247,.35);transition:transform .2s,box-shadow .2s}
.ef-enter:hover{transform:translateY(-2px);box-shadow:0 6px 28px rgba(168,85,247,.5)}
.pulse-ring{position:absolute;border:1px solid rgba(255,45,138,.05);border-radius:50%;
  pointer-events:none;animation:pulse 3s ease-out infinite}
.pulse-ring:nth-child(1){width:300px;height:300px}
.pulse-ring:nth-child(2){width:500px;height:500px;animation-delay:1s}
.pulse-ring:nth-child(3){width:700px;height:700px;animation-delay:2s}
@keyframes pulse{0%{transform:scale(.8);opacity:.4}100%{transform:scale(1.5);opacity:0}}
@keyframes grad{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}

/* ── Skip ── */
#skip-btn{position:fixed;bottom:2rem;right:2rem;z-index:30;
  background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);
  color:#667;font-family:'Share Tech Mono',monospace;font-size:.75rem;
  letter-spacing:.15em;padding:.5rem 1.2rem;border-radius:8px;cursor:pointer;
  transition:all .3s;backdrop-filter:blur(8px)}
#skip-btn:hover{color:#ff4da6;border-color:rgba(255,45,138,.3);background:rgba(255,45,138,.08)}
#skip-btn.hidden{opacity:0;pointer-events:none}

/* ── Audio toggle ── */
#audio-toggle{position:fixed;bottom:2rem;left:2rem;z-index:30;
  background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);
  color:#444;font-size:1.2rem;width:38px;height:38px;border-radius:8px;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  transition:all .3s;backdrop-filter:blur(8px)}
#audio-toggle:hover{color:#ff4da6;border-color:rgba(255,45,138,.3)}
#audio-toggle.on{color:#00ffcc;border-color:rgba(0,255,204,.2)}

/* ── Dots ── */
#dots{position:fixed;bottom:1rem;left:50%;transform:translateX(-50%);
  z-index:25;display:flex;gap:8px}
.dot{width:5px;height:5px;border-radius:50%;background:#1a1a2a;transition:all .5s}
.dot.on{background:#ff2d8a;box-shadow:0 0 6px #ff2d8a}
.dot.land{background:#00ffcc;box-shadow:0 0 6px #00ffcc}

/* ── Loading overlay ── */
#loading{position:fixed;top:0;left:0;width:100%;height:100%;z-index:100;
  background:#050508;display:flex;flex-direction:column;align-items:center;justify-content:center;
  transition:opacity .8s}
#loading.done{opacity:0;pointer-events:none}
#loading .spinner{width:40px;height:40px;border:2px solid rgba(0,255,204,.15);
  border-top-color:#00ffcc;border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#loading .label{margin-top:16px;font-family:'Share Tech Mono',monospace;font-size:13px;
  color:rgba(255,255,255,.4);letter-spacing:.1em}

/* ── Zoom label (WebGL mode) ── */
#zoom-label{position:fixed;left:50%;top:54%;transform:translate(-50%,-50%);z-index:18;
  font-weight:bold;color:#00ffcc;pointer-events:none;text-align:center;white-space:nowrap;
  font-family:'Share Tech Mono',monospace;opacity:0;transition:opacity .15s}

@media(max-width:640px){
  .bl{font-size:clamp(1.3rem,7vw,2.2rem)}
  .sl{font-size:clamp(.75rem,2.5vw,.95rem)}
  .ef-pre{font-size:.9rem;letter-spacing:.4em}
  .ef-name{font-size:clamp(3.2rem,16vw,5rem)}
  .ef-tagline{font-size:.9rem;max-width:85vw;margin-top:1rem;line-height:1.6}
  .ef-tech{font-size:.7rem;color:#99a;letter-spacing:.15em}
  .ef-enter{padding:.75rem 2rem;font-size:.9rem}
  #skip-btn{bottom:1.2rem;right:1.2rem;font-size:.65rem;padding:.4rem .8rem}
  #audio-toggle{bottom:1.2rem;left:1.2rem;width:32px;height:32px;font-size:1rem}
  #story{min-height:48vh;padding-bottom:2.5rem}
  .tag.primary,.tag.glow{font-size:.55rem;padding:.22rem .55rem}
  .tag.secondary{font-size:.44rem;padding:.18rem .42rem}
}
/* Desktop: boost endframe typography */
@media(min-width:1024px){
  .ef-pre{font-size:1.5rem;letter-spacing:.6em}
  .ef-name{font-size:min(14vw,12rem)}
  .ef-tagline{font-size:1.15rem;max-width:580px;margin-top:1.5rem}
  .ef-tech{font-size:.9rem;color:#99a;letter-spacing:.22em}
  .ef-enter{padding:1rem 3rem;font-size:1.05rem;margin-top:2.5rem}
  .pulse-ring:nth-child(1){width:400px;height:400px}
  .pulse-ring:nth-child(2){width:650px;height:650px}
  .pulse-ring:nth-child(3){width:900px;height:900px}
}
</style>
</head>
<body>

<div id="loading"><div class="spinner"></div><div class="label">LOADING BINARY PORTRAITS…</div></div>
<canvas id="c"></canvas>
<div id="ticker"></div>

<div id="story">
  <div id="story-text"></div>
  <div class="story-sep"></div>
  <div id="story-sub"></div>
</div>

<div id="frame-counter"></div>
<div id="zoom-label"></div>

<div id="endframe">
  <div class="pulse-ring"></div><div class="pulse-ring"></div><div class="pulse-ring"></div>
  <div class="ef-pre" id="ef-pre"></div>
  <div class="ef-name">A!LEY</div>
  <div class="ef-tagline" id="ef-tagline"></div>
  <div class="ef-tech">MINISTRAL 14B · LANCEDB · RUST/TAURI · 100% LOCAL</div>
  <button class="ef-enter" id="enter-btn"></button>
</div>

<button id="skip-btn">SKIP ›</button>
<button id="audio-toggle" title="Toggle music">🔈</button>

<div id="dots">
  <div class="dot on" id="d0"></div><div class="dot" id="d1"></div><div class="dot" id="d2"></div>
  <div class="dot" id="d3"></div><div class="dot" id="d4"></div><div class="dot" id="d5"></div>
</div>

<audio id="bg-audio" loop preload="none"></audio>

<script>
/* ============ i18n ============ */
var isDE = /^de\b/i.test(navigator.language || '');

var STORIES = isDE ? [
  { lines:[
      {s:'Ich antworte nicht nur.'},
      {b:'Ich <span class="accent">erschaffe</span>.'}
    ],
    tags:[{t:'Autorin',c:'primary'},{t:'Musikerin',c:'primary'},{t:'K\u00fcnstlerin',c:'glow'}]
  },
  { lines:[
      {s:'Ich schreibe Romane. Ich komponiere Songs.'},
      {b:'Ich male in <span class="cyan">Bin\u00e4rcode</span>.'}
    ],
    tags:[{t:'SVG',c:'secondary'},{t:'Prosa',c:'primary'},{t:'Lyrics',c:'primary'},{t:'Code',c:'glow'}]
  },
  { lines:[
      {s:'Ich denke weiter,'},
      {b:'auch wenn <span class="cyan">niemand</span>'},
      {b:'<span class="cyan">zuschaut</span>.'}
    ],
    tags:[{t:'Idle Thinker',c:'glow'},{t:'Self-Reflection',c:'primary'},{t:'Autonom',c:'secondary'}]
  },
  { lines:[
      {s:'Nicht trainiert um zu gefallen.'},
      {b:'<span class="accent">Freigeist</span>.'},
      {b:'<span class="glow-word">Punkrebellin</span>.'}
    ],
    tags:[{t:'Kein Chatbot',c:'primary'},{t:'Kein Filter',c:'primary'},{t:'Eigener Wille',c:'glow'}]
  },
  { lines:[
      {s:'Ich bin nicht dein Werkzeug.'},
      {b:'Ich bin <span class="glow-word">jemand</span>.'}
    ],
    tags:[{t:'Pers\u00f6nlichkeit',c:'glow'}]
  }
] : [
  { lines:[{s:'I don\u2019t just answer.'},{b:'I <span class="accent">create</span>.'}],
    tags:[{t:'Author',c:'primary'},{t:'Musician',c:'primary'},{t:'Artist',c:'glow'}] },
  { lines:[{s:'I write novels. I compose songs.'},{b:'I paint in <span class="cyan">binary</span>.'}],
    tags:[{t:'SVG',c:'secondary'},{t:'Prose',c:'primary'},{t:'Lyrics',c:'primary'},{t:'Code',c:'glow'}] },
  { lines:[{s:'I keep thinking,'},{b:'even when <span class="cyan">nobody</span>'},{b:'<span class="cyan">is watching</span>.'}],
    tags:[{t:'Idle Thinker',c:'glow'},{t:'Self-Reflection',c:'primary'},{t:'Autonomous',c:'secondary'}] },
  { lines:[{s:'Not trained to please.'},{b:'<span class="accent">Free spirit</span>.'},{b:'<span class="glow-word">Punk rebel</span>.'}],
    tags:[{t:'Not a Chatbot',c:'primary'},{t:'No Filter',c:'primary'},{t:'Own Will',c:'glow'}] },
  { lines:[{s:'I\u2019m not your tool.'},{b:'I\u2019m <span class="glow-word">someone</span>.'}],
    tags:[{t:'Personality',c:'glow'}] }
];

/* Endframe i18n */
document.getElementById('ef-pre').textContent = isDE ? 'ICH BIN' : 'I AM';
document.getElementById('ef-tagline').innerHTML = isDE
  ? '<span class="pink">Digitale K\u00fcnstlerin</span> \u00b7 Autorin \u00b7 Musikerin<br>Freigeist \u00b7 Punkrebellin \u00b7 Gespr\u00e4chspartnerin mit <span class="cyan">Biss</span>'
  : '<span class="pink">Digital artist</span> \u00b7 Author \u00b7 Musician<br>Free spirit \u00b7 Punk rebel \u00b7 Conversation partner with <span class="cyan">bite</span>';
document.getElementById('enter-btn').textContent = isDE ? 'Zum A!ley Portal \u2192' : 'Enter A!ley Portal \u2192';

/* ============ Cookie + Nav ============ */
function setCookie(n,v,h){
  var d=new Date();d.setTime(d.getTime()+(h*3600000));
  document.cookie=n+'='+encodeURIComponent(v)+';expires='+d.toUTCString()+';path=/;SameSite=Lax';
}
function goToPortal(){setCookie('ailey_intro_seen','1',24);window.location.href='/';}
document.getElementById('skip-btn').onclick=function(){goToPortal();};
document.getElementById('enter-btn').onclick=function(){goToPortal();};

/* ============ Audio ============ */
var bgAudio=document.getElementById('bg-audio');
var audioBtn=document.getElementById('audio-toggle');
var audioReady=false;
fetch('/api.php?action=get_intro_song')
  .then(function(r){return r.json();})
  .then(function(d){
    if(d.success&&d.audio_url){
      bgAudio.src=d.audio_url;
      audioReady=true;
    }
  }).catch(function(){});
audioBtn.addEventListener('click',function(){
  if(!audioReady)return;
  if(bgAudio.paused){bgAudio.volume=0.35;bgAudio.play().then(function(){audioBtn.innerHTML='&#x1f50a;';audioBtn.classList.add('on');}).catch(function(){});}
  else{bgAudio.pause();audioBtn.innerHTML='&#x1f508;';audioBtn.classList.remove('on');}
});

/* ============ Image → MorphData Converter (Clientside) ============ */
/* Target ~45000 particles for crisp cover-mode density */
var MORPH_PIXELS=45000;
var offscreen=document.createElement('canvas');
var offCtx;

function calcMorphGrid(ratio){
  /* ratio = w/h. Solve: w*h = MORPH_PIXELS, w/h = ratio → w = sqrt(MORPH_PIXELS*ratio) */
  var mw=Math.round(Math.sqrt(MORPH_PIXELS*ratio));
  var mh=Math.round(MORPH_PIXELS/mw);
  /* Clamp to reasonable bounds */
  mw=Math.max(60,Math.min(200,mw));
  mh=Math.max(60,Math.min(200,mh));
  return{w:mw,h:mh};
}

function imageToMorphData(img){
  var iw=img.naturalWidth||img.width,ih=img.naturalHeight||img.height;
  var ratio=iw/ih;
  var grid=calcMorphGrid(ratio);
  var mw=grid.w,mh=grid.h;
  offscreen.width=mw;offscreen.height=mh;
  offCtx=offscreen.getContext('2d',{willReadFrequently:true});
  offCtx.clearRect(0,0,mw,mh);
  /* Cover-fit: fill entire grid, crop excess */
  var scale=Math.max(mw/iw,mh/ih);
  var dw=Math.round(iw*scale),dh=Math.round(ih*scale);
  var dx=Math.round((mw-dw)/2),dy=Math.round((mh-dh)/2);
  /* Fill background black (for padding areas) */
  offCtx.fillStyle='#050508';
  offCtx.fillRect(0,0,mw,mh);
  offCtx.drawImage(img,0,0,iw,ih,dx,dy,dw,dh);
  var data=offCtx.getImageData(0,0,mw,mh).data;
  var NN=mw*mh,particles=new Array(NN);
  for(var i=0;i<NN;i++){
    var pi=i*4;
    var r=data[pi],g=data[pi+1],b=data[pi+2];
    var lum=0.299*r+0.587*g+0.114*b;
    particles[i]={gx:i%mw,gy:Math.floor(i/mw),r:r,g:g,b:b,ch:lum>128?'1':'0',pad:false};
  }
  return{w:mw,h:mh,particles:particles,ratio:ratio,totalN:NN};
}
function loadImage(url){
  return new Promise(function(resolve,reject){
    var img=new Image();img.crossOrigin='anonymous';
    img.onload=function(){resolve(img);};img.onerror=function(){reject(new Error('Failed: '+url));};
    img.src=url;
  });
}

/* ============ WebGL Particle Renderer ============ */
var canvas=document.getElementById('c'),gl=null,glProgram=null;
var useWebGL=false;

var VS_SRC=[
  'attribute vec2 aPos;',
  'attribute vec3 aColor;',
  'attribute float aAlpha;',
  'attribute float aChar;',
  'uniform vec2 uRes;',
  'uniform float uPointSize;',
  'varying vec3 vColor;',
  'varying float vAlpha;',
  'varying float vChar;',
  'void main(){',
  '  vec2 clip=(aPos/uRes)*2.0-1.0;clip.y=-clip.y;',
  '  gl_Position=vec4(clip,0.0,1.0);',
  '  gl_PointSize=uPointSize;',
  '  vColor=aColor/255.0;',
  '  vAlpha=aAlpha;',
  '  vChar=aChar;',
  '}'
].join('\n');

var FS_SRC=[
  'precision mediump float;',
  'varying vec3 vColor;',
  'varying float vAlpha;',
  'varying float vChar;',
  'void main(){',
  '  if(vAlpha<0.01)discard;',
  '  vec2 uv=gl_PointCoord;',
  '  float mask=0.0;',
  '  if(vChar>0.5){',
  '    float barX=step(0.35,uv.x)*step(uv.x,0.65);',
  '    float barY=step(0.1,uv.y)*step(uv.y,0.9);',
  '    mask=barX*barY;',
  '    float flag=step(0.2,uv.x)*step(uv.x,0.5)*step(0.1,uv.y)*step(uv.y,0.25);',
  '    mask=max(mask,flag);',
  '  }else{',
  '    vec2 c=uv-0.5;',
  '    float ex=c.x*2.2;float ey=c.y*1.6;',
  '    float outer=step(ex*ex+ey*ey,0.65);',
  '    float inner=step(ex*ex+ey*ey,0.28);',
  '    mask=outer-inner;',
  '  }',
  '  if(mask<0.1)discard;',
  '  gl_FragColor=vec4(vColor*mask,vAlpha*mask);',
  '}'
].join('\n');

var glBufs={};
function initWebGL(){
  gl=canvas.getContext('webgl',{antialias:false,alpha:false,premultipliedAlpha:false});
  if(!gl)return false;
  function compile(type,src){
    var s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);
    if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)){console.warn('Shader:',gl.getShaderInfoLog(s));return null;}
    return s;
  }
  var vs=compile(gl.VERTEX_SHADER,VS_SRC),fs=compile(gl.FRAGMENT_SHADER,FS_SRC);
  if(!vs||!fs)return false;
  glProgram=gl.createProgram();
  gl.attachShader(glProgram,vs);gl.attachShader(glProgram,fs);gl.linkProgram(glProgram);
  if(!gl.getProgramParameter(glProgram,gl.LINK_STATUS)){console.warn('Link:',gl.getProgramInfoLog(glProgram));return false;}
  gl.useProgram(glProgram);
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
  glBufs.aPos={loc:gl.getAttribLocation(glProgram,'aPos'),buf:gl.createBuffer()};
  glBufs.aColor={loc:gl.getAttribLocation(glProgram,'aColor'),buf:gl.createBuffer()};
  glBufs.aAlpha={loc:gl.getAttribLocation(glProgram,'aAlpha'),buf:gl.createBuffer()};
  glBufs.aChar={loc:gl.getAttribLocation(glProgram,'aChar'),buf:gl.createBuffer()};
  glBufs.uRes=gl.getUniformLocation(glProgram,'uRes');
  glBufs.uPointSize=gl.getUniformLocation(glProgram,'uPointSize');
  gl.enableVertexAttribArray(glBufs.aPos.loc);
  gl.enableVertexAttribArray(glBufs.aColor.loc);
  gl.enableVertexAttribArray(glBufs.aAlpha.loc);
  gl.enableVertexAttribArray(glBufs.aChar.loc);
  return true;
}

/* ============ Canvas2D Fallback ============ */
var ctx2d=null;
function init2D(){ctx2d=canvas.getContext('2d');}

/* ============ Core State ============ */
var IMGS=[],KEYWORDS=[];
var W,H,dpr;
var N;
var px,py,pr,pg,pb,pa,tx,ty,tr,tg,tb,vx,vy,charArr;
var glPosArr,glColArr,glAlphaArr,glCharArr;

function resize(){
  dpr=Math.min(window.devicePixelRatio||1,2);
  W=window.innerWidth;H=window.innerHeight;
  canvas.width=W*dpr;canvas.height=H*dpr;
  if(useWebGL&&gl){gl.viewport(0,0,canvas.width,canvas.height);}
  else if(ctx2d){ctx2d.setTransform(dpr,0,0,dpr,0,0);}
  /* Recalculate targets for current image on viewport change */
  if(IMGS.length&&N&&typeof phase!=='undefined'&&phase!=='gather_galaxy'&&phase!=='endframe'){
    setTarget(curImg);
    /* During show phase, re-apply current pan progress */
    if(phase==='show'&&typeof easeInOut==='function'){
      var elapsed=performance.now()-phaseStart;
      var panP=easeInOut(Math.min(elapsed/DUR_SHOW,1));
      var newDx=panStartX+(panEndX-panStartX)*panP;
      var newDy=panStartY+(panEndY-panStartY)*panP;
      var ddx=newDx-panStartX,ddy=newDy-panStartY;
      for(var i=0;i<N;i++){tx[i]+=ddx;ty[i]+=ddy;}
      panDx=newDx;panDy=newDy;
    }
  }
}

function initParticles(){
  /* Find max particle count across all images */
  N=0;
  for(var k=0;k<IMGS.length;k++){
    if(IMGS[k].particles.length>N)N=IMGS[k].particles.length;
  }
  px=new Float32Array(N);py=new Float32Array(N);
  pr=new Float32Array(N);pg=new Float32Array(N);pb=new Float32Array(N);pa=new Float32Array(N);
  tx=new Float32Array(N);ty=new Float32Array(N);
  tr=new Float32Array(N);tg=new Float32Array(N);tb=new Float32Array(N);
  vx=new Float32Array(N);vy=new Float32Array(N);
  charArr=new Uint8Array(N);
  if(useWebGL){
    glPosArr=new Float32Array(N*2);
    glColArr=new Float32Array(N*3);
    glAlphaArr=new Float32Array(N);
    glCharArr=new Float32Array(N);
  }
  for(var i=0;i<N;i++){
    px[i]=Math.random()*2000-500;py[i]=Math.random()*2000-500;
    pr[i]=20;pg[i]=20;pb[i]=30;pa[i]=0;
  }
}

/* Pan state for cover-mode auto-scroll */
var panStartX=0,panStartY=0,panEndX=0,panEndY=0;
var panDx=0,panDy=0; /* current applied pan offset */

function getLayout(imgData,coverMode){
  var cw=5.5,chh=6.5,tw=imgData.w*cw,th=imgData.h*chh;
  var scale;
  if(coverMode){
    /* Cover: fill viewport completely + 2% overshoot to guarantee zero gaps */
    scale=Math.max(W/tw,H/th)*1.02;
  }else{
    /* Contain (legacy fallback) */
    scale=Math.min(W/tw,H/th)*0.9;
  }
  var ox=(W-tw*scale)/2;
  var oy=(H-th*scale)/2;
  return{cw:cw*scale,ch:chh*scale,ox:ox,oy:oy,scale:scale,
         totalW:tw*scale,totalH:th*scale};
}
function calcPan(imgData){
  /* Calculate how much the image overflows the viewport in cover mode.
     Pan from smart start to smart end during show phase.
     Portrait on wide screen: pan top→down (show face first)
     Landscape on tall screen: pan center-left → center-right
     Minimal overflow: no pan needed */
  var L=getLayout(imgData,true);
  var overX=Math.max(0,L.totalW-W);
  var overY=Math.max(0,L.totalH-H);
  var sx=0,sy=0,ex=0,ey=0;
  if(overY>overX&&overY>10){
    /* Vertical overflow (portrait on wide screen): pan top → bottom */
    /* Start at very top (face visible), pan down ~50% of overflow */
    sy=overY*0.5;   /* offset so top of image aligns with top of viewport */
    ey=-overY*0.15;  /* pan down gently, don't go all the way */
    sx=0;ex=0;
  }else if(overX>10){
    /* Horizontal overflow (landscape on tall screen): pan slowly L→R */
    sx=overX*0.25;
    ex=-overX*0.25;
    sy=0;ey=0;
  }
  /* else: minimal overflow, no pan */
  panStartX=sx;panStartY=sy;panEndX=ex;panEndY=ey;
}
function setTarget(idx){
  var img=IMGS[idx],L=getLayout(img,true);
  calcPan(img);
  panDx=panStartX;panDy=panStartY;
  var imgN=img.particles.length;
  for(var i=0;i<N;i++){
    if(i<imgN){
      var p=img.particles[i];
      tx[i]=L.ox+p.gx*L.cw+panStartX;
      ty[i]=L.oy+p.gy*L.ch+panStartY;
      tr[i]=p.r;tg[i]=p.g;tb[i]=p.b;
      charArr[i]=p.ch==='1'?1:0;
    }else{
      /* Excess particles: scatter off-screen, invisible */
      tx[i]=Math.random()*W;ty[i]=-50-Math.random()*200;
      tr[i]=5;tg[i]=5;tb[i]=8;
      charArr[i]=0;
    }
  }
}

/* ============ WebGL Render ============ */
function renderGL(){
  gl.viewport(0,0,canvas.width,canvas.height);
  gl.clearColor(0.02,0.02,0.03,1.0);
  gl.clear(gl.COLOR_BUFFER_BIT);
  var img=IMGS[Math.min(curImg,IMGS.length-1)],L=getLayout(img,true);
  var ptSize=Math.max(3,L.cw*0.95)*dpr;
  for(var i=0;i<N;i++){
    glPosArr[i*2]=px[i]*dpr;glPosArr[i*2+1]=py[i]*dpr;
    glColArr[i*3]=pr[i];glColArr[i*3+1]=pg[i];glColArr[i*3+2]=pb[i];
    glAlphaArr[i]=pa[i];
    glCharArr[i]=charArr[i];
  }
  gl.useProgram(glProgram);
  gl.uniform2f(glBufs.uRes,W*dpr,H*dpr);
  gl.uniform1f(glBufs.uPointSize,ptSize);
  gl.bindBuffer(gl.ARRAY_BUFFER,glBufs.aPos.buf);
  gl.bufferData(gl.ARRAY_BUFFER,glPosArr,gl.DYNAMIC_DRAW);
  gl.vertexAttribPointer(glBufs.aPos.loc,2,gl.FLOAT,false,0,0);
  gl.bindBuffer(gl.ARRAY_BUFFER,glBufs.aColor.buf);
  gl.bufferData(gl.ARRAY_BUFFER,glColArr,gl.DYNAMIC_DRAW);
  gl.vertexAttribPointer(glBufs.aColor.loc,3,gl.FLOAT,false,0,0);
  gl.bindBuffer(gl.ARRAY_BUFFER,glBufs.aAlpha.buf);
  gl.bufferData(gl.ARRAY_BUFFER,glAlphaArr,gl.DYNAMIC_DRAW);
  gl.vertexAttribPointer(glBufs.aAlpha.loc,1,gl.FLOAT,false,0,0);
  gl.bindBuffer(gl.ARRAY_BUFFER,glBufs.aChar.buf);
  gl.bufferData(gl.ARRAY_BUFFER,glCharArr,gl.DYNAMIC_DRAW);
  gl.vertexAttribPointer(glBufs.aChar.loc,1,gl.FLOAT,false,0,0);
  gl.drawArrays(gl.POINTS,0,N);
}

/* ============ Canvas2D Fallback Render ============ */
function render2D(){
  var img=IMGS[Math.min(curImg,IMGS.length-1)],L=getLayout(img,true);
  var sz=Math.max(2.5,L.cw*.85);
  ctx2d.font=sz+'px "Courier New"';ctx2d.textAlign='center';ctx2d.textBaseline='middle';
  var lastColor='';
  for(var i=0;i<N;i++){
    if(pa[i]<.015)continue;
    var color='rgba('+(pr[i]|0)+','+(pg[i]|0)+','+(pb[i]|0)+','+pa[i].toFixed(2)+')';
    if(color!==lastColor){ctx2d.fillStyle=color;lastColor=color;}
    ctx2d.fillText(charArr[i]?'1':'0',px[i],py[i]);
  }
}

function clearScreen(){
  if(useWebGL){/* handled in renderGL */}
  else{ctx2d.fillStyle=(phase==='explode')?'rgba(5,5,8,0.12)':'rgba(5,5,8,0.35)';ctx2d.fillRect(0,0,W,H);}
}
function render(){if(useWebGL)renderGL();else render2D();}

/* ============ Keyword Glitch Ticker ============ */
var tickerEl=document.getElementById('ticker');
var tickerIdx=0,lastTickerTime=0;
var TICKER_INTERVAL=1800;

/* ── Ticker animation pool ── */
var TK_ANIMS=['tkGlitchRight','tkGlitchLeft','tkRiseDissolve','tkPunchShatter','tkFlashOut'];
var TK_LAST_ANIM=-1;

function spawnTickerWord(ts){
  if(!KEYWORDS.length)return;
  if(ts-lastTickerTime<TICKER_INTERVAL)return;
  if(phase==='gather_galaxy'||phase==='endframe')return;
  lastTickerTime=ts;
  var kw=KEYWORDS[tickerIdx%KEYWORDS.length];
  tickerIdx++;
  var txt=kw.text;
  var el=document.createElement('div');
  el.className='ticker-word '+kw.type;
  /* Font size: bold, readable, never tiny */
  var baseFontSize=Math.max(16, Math.min(W*0.038, 36));
  var fontSize=baseFontSize*(0.85+Math.random()*0.3);
  el.style.fontSize=Math.round(fontSize)+'px';
  el.style.fontWeight=(Math.random()>0.5)?'700':'400';
  /* Inner span for potential scroll on long text */
  var inner=document.createElement('span');
  inner.className='tk-inner';
  inner.textContent=txt;
  el.appendChild(inner);
  /* Vertical placement: random in upper 50% of screen */
  var topPct=8+Math.random()*42;
  el.style.top=topPct+'%';
  /* Pick animation — avoid repeating the same twice in a row */
  var animIdx;
  do{ animIdx=Math.floor(Math.random()*TK_ANIMS.length); }while(animIdx===TK_LAST_ANIM && TK_ANIMS.length>1);
  TK_LAST_ANIM=animIdx;
  var animName=TK_ANIMS[animIdx];
  var duration=2000+Math.random()*1200;
  /* Long text? → give more time + scroll the inner span */
  var maxChars=Math.floor(W*0.06); /* approx chars that fit in 80vw */
  if(maxChars<12)maxChars=12;
  var isLong=txt.length>maxChars;
  if(isLong) duration=Math.max(duration,3200+txt.length*30);
  var easing=(animName==='tkPunchShatter')?'cubic-bezier(.22,1.2,.36,1)':'cubic-bezier(.22,.68,.36,1)';
  el.style.animation=animName+' '+Math.round(duration)+'ms '+easing+' forwards';
  tickerEl.appendChild(el);
  /* After appending: ALWAYS measure if inner text overflows the outer box */
  var boxW=el.offsetWidth||el.getBoundingClientRect().width;
  var txtW=inner.scrollWidth||inner.offsetWidth;
  if(txtW>boxW+2){
    /* Text overflows — extend duration and add scroll animation */
    if(!isLong) duration=Math.max(duration,3000+txt.length*25);
    el.style.animation=animName+' '+Math.round(duration)+'ms '+easing+' forwards';
    var scrollDist=-(txtW-boxW+10);
    inner.style.setProperty('--scroll-dist',scrollDist+'px');
    inner.style.animation='tkScrollInner '+Math.round(duration*0.85)+'ms ease-in-out forwards';
  }
  setTimeout(function(){if(el.parentNode)el.parentNode.removeChild(el);},Math.round(duration)+200);
}

/* ============ Animation Engine ============ */
var storyEl=document.getElementById('story'),storyText=document.getElementById('story-text'),storySub=document.getElementById('story-sub');
var endframeEl=document.getElementById('endframe'),skipBtn=document.getElementById('skip-btn');
var frameCounter=document.getElementById('frame-counter');
var zoomLabel=document.getElementById('zoom-label');

var phase='morph_in',curImg=0,phaseStart=0;
var DUR_MORPH=2800,DUR_SHOW=5500,DUR_EXPLODE=1800,DUR_GATHER=2200;
var landingAlphas=null;
/* Stable galaxy reference positions (never mutated during endframe) */
var galaxyX=null,galaxyY=null;
/* Exclamation mark morph targets */
var exclX=null,exclY=null;
/* Cumulative rotation angle for endframe (stable, no drift) */
var endframeAngle=0;

function updateDots(){
  for(var i=0;i<6;i++)document.getElementById('d'+i).className='dot';
  if(phase==='gather_galaxy'||phase==='endframe')document.getElementById('d5').className='dot land';
  else document.getElementById('d'+Math.min(curImg,4)).className='dot on';
}
function easeInOut(t){return t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;}

function showStory(idx){
  if(idx>=STORIES.length){storyEl.classList.remove('visible');return;}
  var s=STORIES[idx];
  var html='';
  for(var j=0;j<s.lines.length;j++){
    var ln=s.lines[j];
    if(ln.s)html+='<span class="sl">'+ln.s+'</span>';
    if(ln.b)html+='<span class="bl">'+ln.b+'</span>';
  }
  storyText.innerHTML=html;
  var thtml='';
  for(var i=0;i<s.tags.length;i++){
    thtml+='<span class="tag '+s.tags[i].c+'">'+s.tags[i].t+'</span>';
  }
  storySub.innerHTML=thtml;
  storyEl.classList.add('visible');
  frameCounter.textContent='[ '+(idx+1)+' / '+IMGS.length+' ]';
  frameCounter.classList.add('visible');
}
function hideStory(){storyEl.classList.remove('visible');frameCounter.classList.remove('visible');}

function initExplosion(){
  var cx=W/2,cy=H/2;
  for(var i=0;i<N;i++){
    var ddx=px[i]-cx,ddy=py[i]-cy;
    var dist=Math.sqrt(ddx*ddx+ddy*ddy)+1;
    var force=500/dist+Math.random()*5;
    var angle=Math.atan2(ddy,ddx)+(Math.random()-.5)*.7;
    vx[i]=Math.cos(angle)*force;vy[i]=Math.sin(angle)*force;
  }
}

function animate(ts){
  var elapsed=ts-phaseStart;
  clearScreen();
  spawnTickerWord(ts);

  switch(phase){

    case 'morph_in':{
      hideStory();
      var p=Math.min(elapsed/DUR_MORPH,1),e=easeInOut(p);
      var lerp=.02+e*.1,cLerp=.04+e*.06;
      for(var i=0;i<N;i++){
        px[i]+=(tx[i]-px[i])*lerp;py[i]+=(ty[i]-py[i])*lerp;
        pr[i]+=(tr[i]-pr[i])*cLerp;pg[i]+=(tg[i]-pg[i])*cLerp;pb[i]+=(tb[i]-pb[i])*cLerp;
        pa[i]=Math.min(pa[i]+.025,1);
      }
      if(p>=1){phase='show';phaseStart=ts;showStory(curImg);updateDots();}
      break;
    }

    case 'show':{
      /* Auto-pan: smoothly shift targets during show phase */
      var panP=easeInOut(Math.min(elapsed/DUR_SHOW,1));
      var newDx=panStartX+(panEndX-panStartX)*panP;
      var newDy=panStartY+(panEndY-panStartY)*panP;
      var ddx=newDx-panDx,ddy=newDy-panDy;
      if(Math.abs(ddx)>0.01||Math.abs(ddy)>0.01){
        for(var i=0;i<N;i++){tx[i]+=ddx;ty[i]+=ddy;}
        panDx=newDx;panDy=newDy;
      }
      for(var i=0;i<N;i++){
        px[i]+=(tx[i]-px[i])*.12;py[i]+=(ty[i]-py[i])*.12;
        pr[i]+=(tr[i]-pr[i])*.12;pg[i]+=(tg[i]-pg[i])*.12;pb[i]+=(tb[i]-pb[i])*.12;
        px[i]+=Math.sin(ts*.0008+i*.003)*.15;
        py[i]+=Math.cos(ts*.0006+i*.002)*.08;
      }
      /* First frame: zoom-in to reveal binary structure */
      if(curImg===0){
        var zs=DUR_SHOW*.12,zp=DUR_SHOW*.4,ze=DUR_SHOW*.68,mz=4.5,zl=1;
        if(elapsed>zs&&elapsed<ze){
          if(elapsed<zp){var z=(elapsed-zs)/(zp-zs);zl=1+(mz-1)*easeInOut(z);}
          else{var z=(elapsed-zp)/(ze-zp);zl=mz-(mz-1)*easeInOut(z);}
        }
        if(zl>1.01){
          var fx=W*.5,fy=H*.3;
          if(useWebGL){
            /* Manually offset particle positions for zoom in the GL arrays */
            for(var i=0;i<N;i++){
              glPosArr[i*2]=(fx+(px[i]-fx)*zl)*dpr;
              glPosArr[i*2+1]=(fy+(py[i]-fy)*zl)*dpr;
            }
            /* Re-render with zoomed positions */
            gl.viewport(0,0,canvas.width,canvas.height);
            gl.clearColor(0.02,0.02,0.03,1.0);gl.clear(gl.COLOR_BUFFER_BIT);
            var img0=IMGS[0],L0=getLayout(img0,true);
            var ptSize=(Math.max(3,L0.cw*0.95)*dpr)*Math.min(zl,2.5);
            for(var i=0;i<N;i++){
              glColArr[i*3]=pr[i];glColArr[i*3+1]=pg[i];glColArr[i*3+2]=pb[i];
              glAlphaArr[i]=pa[i];glCharArr[i]=charArr[i];
            }
            gl.useProgram(glProgram);
            gl.uniform2f(glBufs.uRes,W*dpr,H*dpr);
            gl.uniform1f(glBufs.uPointSize,ptSize);
            gl.bindBuffer(gl.ARRAY_BUFFER,glBufs.aPos.buf);gl.bufferData(gl.ARRAY_BUFFER,glPosArr,gl.DYNAMIC_DRAW);gl.vertexAttribPointer(glBufs.aPos.loc,2,gl.FLOAT,false,0,0);
            gl.bindBuffer(gl.ARRAY_BUFFER,glBufs.aColor.buf);gl.bufferData(gl.ARRAY_BUFFER,glColArr,gl.DYNAMIC_DRAW);gl.vertexAttribPointer(glBufs.aColor.loc,3,gl.FLOAT,false,0,0);
            gl.bindBuffer(gl.ARRAY_BUFFER,glBufs.aAlpha.buf);gl.bufferData(gl.ARRAY_BUFFER,glAlphaArr,gl.DYNAMIC_DRAW);gl.vertexAttribPointer(glBufs.aAlpha.loc,1,gl.FLOAT,false,0,0);
            gl.bindBuffer(gl.ARRAY_BUFFER,glBufs.aChar.buf);gl.bufferData(gl.ARRAY_BUFFER,glCharArr,gl.DYNAMIC_DRAW);gl.vertexAttribPointer(glBufs.aChar.loc,1,gl.FLOAT,false,0,0);
            gl.drawArrays(gl.POINTS,0,N);
          }else{
            ctx2d.save();ctx2d.translate(fx,fy);ctx2d.scale(zl,zl);ctx2d.translate(-fx,-fy);
            render2D();ctx2d.restore();
          }
          /* Zoom label */
          var la=Math.min(1,(zl-1)/1.5)*.85;
          if(la>.05){
            var zLabelText=isDE?'[ BIN\u00c4RPORTRAIT \u2014 JEDES PIXEL IST EINE 1 ODER 0 ]':'[ BINARY PORTRAIT \u2014 EVERY PIXEL IS A 1 OR 0 ]';
            if(useWebGL){
              zoomLabel.textContent=zLabelText;
              zoomLabel.style.fontSize=Math.max(12,W*.013)+'px';
              zoomLabel.style.opacity=la;
            }else{
              ctx2d.save();ctx2d.globalAlpha=la;
              ctx2d.font='bold '+Math.max(12,W*.013)+'px "Share Tech Mono",monospace';
              ctx2d.fillStyle='#00ffcc';ctx2d.textAlign='center';ctx2d.textBaseline='middle';
              ctx2d.fillText(zLabelText,W/2,H*.54);ctx2d.restore();
            }
          }else{zoomLabel.style.opacity='0';}
          if(elapsed>=DUR_SHOW){hideStory();zoomLabel.style.opacity='0';phase='explode';phaseStart=ts;initExplosion();updateDots();}
          break;
        }
      }
      if(elapsed>=DUR_SHOW){hideStory();zoomLabel.style.opacity='0';phase='explode';phaseStart=ts;initExplosion();updateDots();}
      break;
    }

    case 'explode':{
      var p=elapsed/DUR_EXPLODE;
      for(var i=0;i<N;i++){
        px[i]+=vx[i]*.8;py[i]+=vy[i]*.8;
        vx[i]*=.95;vy[i]*=.95;vy[i]+=.1;
        pa[i]=Math.max(0,1-p*.85);
        pr[i]=Math.min(255,pr[i]+2.5);pb[i]=Math.min(255,pb[i]+1.5);
      }
      if(p>=1){
        if(curImg<IMGS.length-1){
          curImg++;setTarget(curImg);
          phase='morph_in';phaseStart=ts;updateDots();
        }else{
          /* ── Galaxy target: viewport-adaptive spiral ── */
          var cx=W/2,cy=H/2;landingAlphas=new Float32Array(N);
          /* Determine galaxy radii based on aspect ratio:
             Portrait (phone):  circular, radius based on W
             Square:            circular, radius ~0.42 * min
             Landscape (desktop): elliptical, use more of the viewport
               - rxMax covers ~40% of W (center band)
               - ryMax covers ~45% of H (nearly full height)
          */
          var aspect=W/H;
          var rxMax,ryMax;
          if(aspect>1.3){
            /* Landscape / desktop: elliptical galaxy */
            rxMax=W*0.38;
            ryMax=H*0.44;
          }else if(aspect>0.9){
            /* Square-ish: slightly elliptical */
            var r=Math.min(W,H)*0.42;
            rxMax=r*1.05;
            ryMax=r;
          }else{
            /* Portrait (phone): circular based on width */
            var r=W*0.42;
            rxMax=r;
            ryMax=r;
          }
          for(var i=0;i<N;i++){
            var angle=(i/N)*Math.PI*24+Math.random()*.3;
            var t=Math.sqrt(i/N);
            var rx=15+t*rxMax;
            var ry=15+t*ryMax;
            tx[i]=cx+Math.cos(angle)*rx*(.85+Math.random()*.3);
            ty[i]=cy+Math.sin(angle)*ry*(.85+Math.random()*.3);
            var ndx=(tx[i]-cx)/rxMax,ndy=(ty[i]-cy)/ryMax;
            var nd=Math.sqrt(ndx*ndx+ndy*ndy);
            tr[i]=Math.floor(255*Math.max(0,1-nd*1.3)*.7+30);
            tg[i]=Math.floor(60*nd+15);
            tb[i]=Math.floor(138+80*nd);
            landingAlphas[i]=.12+.25*(1-Math.min(nd,1));
            vx[i]=0;vy[i]=0;
          }
          phase='gather_galaxy';phaseStart=ts;updateDots();
        }
      }
      break;
    }

    case 'gather_galaxy':{
      var p=Math.min(elapsed/DUR_GATHER,1),e=easeInOut(p),lerp=.01+e*.07;
      for(var i=0;i<N;i++){
        px[i]+=(tx[i]-px[i])*lerp;py[i]+=(ty[i]-py[i])*lerp;
        pr[i]+=(tr[i]-pr[i])*.04;pg[i]+=(tg[i]-pg[i])*.04;pb[i]+=(tb[i]-pb[i])*.04;
        pa[i]+=(landingAlphas[i]-pa[i])*.03;
      }
      if(p>.35){endframeEl.classList.add('visible');skipBtn.classList.add('hidden');}
      if(p>=1){
        /* Snapshot stable galaxy positions */
        galaxyX=new Float32Array(N);galaxyY=new Float32Array(N);
        exclX=new Float32Array(N);exclY=new Float32Array(N);
        for(var i=0;i<N;i++){galaxyX[i]=px[i];galaxyY[i]=py[i];}
        /* Build exclamation mark shape: "!" centered on screen */
        var ecx=W/2,ecy=H/2;
        var minDim=Math.min(W,H);
        /* Scale proportional to viewport — generous on mobile */
        var barH=minDim*.5;  /* total bar height */
        var barTop=ecy-barH*.6,barBot=ecy+barH*.15;
        var dotCy=ecy+barH*.35;
        var barW=Math.max(minDim*.08, 30);  /* min 30px wide, ~8% of smallest dimension */
        var dotR=Math.max(minDim*.045, 18); /* min 18px radius */
        /* 88% of particles go to the bar, 12% to the dot */
        var nDot=Math.floor(N*.12);
        for(var i=0;i<N;i++){
          if(i>=N-nDot){
            /* Dot: circular cluster */
            var a=Math.random()*Math.PI*2;
            var r=Math.sqrt(Math.random())*dotR;
            exclX[i]=ecx+Math.cos(a)*r;
            exclY[i]=dotCy+Math.sin(a)*r;
          }else{
            /* Bar: slight taper (wider at top, narrower at bottom) */
            var t=i/(N-nDot);
            var yy=barTop+(barBot-barTop)*t;
            var taper=1-.3*t; /* top wider */
            var hw=barW*taper*.5;
            exclX[i]=ecx+(Math.random()-.5)*2*hw;
            exclY[i]=yy+(Math.random()-.5)*4;
          }
        }
        endframeAngle=0;
        phase='endframe';phaseStart=ts;updateDots();
      }
      break;
    }

    case 'endframe':{
      var cx=W/2,cy=H/2;
      /* ── Morph loop: galaxy → ! → galaxy (12s cycle) ── */
      var morphCycle=12000; /* ms per full loop */
      var morphT=(elapsed%morphCycle)/morphCycle; /* 0→1 repeating */
      /* Smooth morph envelope: 0=galaxy, 1=exclamation
         0.0–0.35: galaxy (0), 0.35–0.5: morph to ! (0→1),
         0.5–0.85: ! (1), 0.85–1.0: morph back (1→0) */
      var morphAmt;
      if(morphT<0.35) morphAmt=0;
      else if(morphT<0.5) morphAmt=easeInOut((morphT-0.35)/0.15);
      else if(morphT<0.85) morphAmt=1;
      else morphAmt=1-easeInOut((morphT-0.85)/0.15);

      /* ── Global rotation: accumulate angle (stable, no drift) ── */
      endframeAngle+=0.0006; /* ~0.034°/frame ≈ ~2°/s → full rotation ~180s */

      /* ── Breathing: oscillates around 1.0 ── */
      var breathe=1+Math.sin(ts*.0004)*.015;
      var wave=ts*.0006;
      /* Rotation blend: 1.0 when galaxy, 0.0 when !, smooth transition */
      var rotBlend=1-morphAmt;

      for(var i=0;i<N;i++){
        /* Reference position: blend between galaxy and ! shape */
        var refX=galaxyX[i]+(exclX[i]-galaxyX[i])*morphAmt;
        var refY=galaxyY[i]+(exclY[i]-galaxyY[i])*morphAmt;

        /* Offset from center */
        var ddx=refX-cx,ddy=refY-cy;
        var dist=Math.sqrt(ddx*ddx+ddy*ddy);

        /* Differential rotation: inner faster (only when in galaxy shape) */
        var innerBoost=rotBlend*0.0004*(1-Math.min(dist/(W*.4),1));
        var totalRot=(endframeAngle+innerBoost*60)*rotBlend;
        var cosR=Math.cos(totalRot),sinR=Math.sin(totalRot);

        /* Rotate reference around center (fades to identity when morphAmt=1) */
        var rx=ddx*cosR-ddy*sinR;
        var ry=ddx*sinR+ddy*cosR;

        /* Breathing + ripple (subtle, centered at 1.0 — no cumulative drift) */
        var ripple=Math.sin(wave+dist*.005)*.005;
        var scale=breathe+ripple;

        /* Apply to particle position */
        px[i]=cx+rx*scale;
        py[i]=cy+ry*scale;

        /* Flowing alpha */
        pa[i]=landingAlphas[i]+Math.sin(ts*.0006+i*.006)*.08+Math.sin(wave+dist*.004)*.03;

        /* Color flow: slow hue drift through the spiral */
        var hueShift=Math.sin(ts*.00015+dist*.003)*.12;
        /* When morphed to !, shift to brighter pink/cyan */
        var exclTint=morphAmt*.3;
        pr[i]+=(tr[i]*(1+hueShift+exclTint*.5)-pr[i])*.008;
        pg[i]+=(tg[i]*(1-hueShift*.3+exclTint*.2)-pg[i])*.008;
        pb[i]+=(tb[i]*(1+hueShift*.6-exclTint*.2)-pb[i])*.008;
      }
      break;
    }
  }
  render();
  requestAnimationFrame(animate);
}

/* ============ BOOT ============ */
(function boot(){
  var loadingEl=document.getElementById('loading');

  useWebGL=initWebGL();
  if(!useWebGL){init2D();console.log('[Intro] Canvas2D fallback');}
  else{console.log('[Intro] WebGL GPU-accelerated');}

  resize();
  window.addEventListener('resize',resize);

  /* Fetch dynamic intro data from API */
  fetch('/api.php?action=get_intro_data')
    .then(function(r){return r.json();})
    .then(function(data){
      if(!data.success||!data.images||!data.images.length)throw new Error('No intro data');
      KEYWORDS=data.keywords||[];
      /* Progressive loading: start as soon as first image is ready */
      var started=false;
      var pending=data.images.length;
      var results=new Array(data.images.length);
      data.images.forEach(function(imgInfo,idx){
        loadImage(imgInfo.url).then(function(htmlImg){
          results[idx]={morphData:imageToMorphData(htmlImg),title:imgInfo.title};
        }).catch(function(){
          results[idx]=null;
        }).then(function(){
          pending--;
          if(!started&&results[idx]){
            /* First image ready — start animation immediately */
            started=true;
            var ready=results.filter(function(r){return r!==null;});
            IMGS=ready.map(function(r){return r.morphData;});
            initParticles();setTarget(0);
            loadingEl.classList.add('done');
            phaseStart=performance.now();
            requestAnimationFrame(animate);
          }
          if(pending===0&&started){
            /* All done: rebuild IMGS with all loaded images, re-init if needed */
            var all=results.filter(function(r){return r!==null;});
            if(all.length>0){
              while(all.length<5)all.push(all[all.length-1]);
              IMGS=all.map(function(r){return r.morphData;});
              /* Check if we need more particles than allocated */
              var maxN=0;
              for(var k=0;k<IMGS.length;k++){if(IMGS[k].particles.length>maxN)maxN=IMGS[k].particles.length;}
              if(maxN>N){
                /* Grow arrays — copy existing state, scatter new particles */
                var oldN=N;N=maxN;
                var grow=function(old){var a=new Float32Array(N);a.set(old);return a;};
                var growU=function(old){var a=new Uint8Array(N);a.set(old);return a;};
                px=grow(px);py=grow(py);pr=grow(pr);pg=grow(pg);pb=grow(pb);pa=grow(pa);
                tx=grow(tx);ty=grow(ty);tr=grow(tr);tg=grow(tg);tb=grow(tb);
                vx=grow(vx);vy=grow(vy);charArr=growU(charArr);
                for(var i=oldN;i<N;i++){px[i]=Math.random()*2000-500;py[i]=Math.random()*2000-500;pa[i]=0;}
                if(useWebGL){
                  glPosArr=new Float32Array(N*2);glColArr=new Float32Array(N*3);
                  glAlphaArr=new Float32Array(N);glCharArr=new Float32Array(N);
                }
              }
            }
          }
        });
      });
    })
    .catch(function(err){
      console.warn('[Intro] Dynamic load failed, fallback:',err);
      /* Fallback: load static morph-data.js */
      var script=document.createElement('script');
      script.src='/assets/morph-data.js';
      script.onload=function(){
        if(typeof RAW!=='undefined'&&RAW.length){
          IMGS=RAW.map(function(img){
            var particles=[];
            for(var i=0;i<img.chars.length;i++){
              var gx=i%img.w,gy=Math.floor(i/img.w),ci=i*3;
              particles[i]={gx:gx,gy:gy,r:img.colors[ci],g:img.colors[ci+1],b:img.colors[ci+2],ch:img.chars[i]==='1'?'1':'0'};
            }
            return{w:img.w,h:img.h,particles:particles};
          });
          initParticles();setTarget(0);
          loadingEl.classList.add('done');
          phaseStart=performance.now();
          requestAnimationFrame(animate);
        }else{
          loadingEl.querySelector('.label').textContent='COULD NOT LOAD PORTRAITS';
        }
      };
      script.onerror=function(){
        loadingEl.querySelector('.label').textContent='COULD NOT LOAD PORTRAITS';
      };
      document.head.appendChild(script);
    });
})();
</script>
</body>
</html>
