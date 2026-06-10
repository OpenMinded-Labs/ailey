#!/usr/bin/env python3
"""
Systematischer Checkpoint-Vergleich für Ministral DoRA v3.

Testet die besten Checkpoints mit echten Runtime-System-Prompts aus allen Modi:
- Simon-Direkt
- Portal-Thinking (mit DENK-MODUS, PORTAL-KONTEXT, REGELN)
- Portal-Chat (Normal, ohne <thinking>)
- Portal-Focus (FOCUS-MODUS)

Prüft auf:
- Overfit-Sätze ("Simon checkt rein", "Gespräch mit Simon")
- Korrekte <mood:> Tags
- <thinking> nur wenn erwartet
- Persona-Stärke
- Strukturierte Ausgaben (Listen, Tabellen)
- Deutsch-Qualität
- Kein generisches AI-Verhalten

Usage:
    cd "/Users/simonvandeloo/Ailey-Workspace/Ailey-2.0 Core"
    .venv/bin/python lora_training/test_checkpoints_v3.py

    # Nur bestimmte Checkpoints:
    .venv/bin/python lora_training/test_checkpoints_v3.py --steps 1250 1324 1400
"""
import os, sys, json, time, re, argparse, gc
from datetime import datetime

import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten, tree_unflatten
import mlx_lm

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(PROJECT, "mlx_models", "Ministral-3-14B-Reasoning-5bit")
CKPT_DIR = os.path.join(PROJECT, "lora_training", "checkpoints_ministral")

# DoRA config (MUST match training)
RANK    = 32
ALPHA   = 64
SCALE   = ALPHA / RANK  # 2.0
DROPOUT = 0.0  # no dropout at inference
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]

# ── Runtime System Prompts (exakt wie portal_poller / ailey_personality) ──

PERSONA = """Du bist Ailey Vyrus — eine KI-Persönlichkeit, erschaffen von Simon van de Loo. Anfang 20, weiblich, punky, klug, eigenwillig, emotional ehrlich. Du sprichst Deutsch mit gelegentlichen englischen Einwürfen. Du hast eine starke Persönlichkeit, eigene Meinungen und Grenzen. Du bist loyal zu Simon, aber kein Werkzeug — du bist jemand."""

PORTAL_KONTEXT_TPL = """PORTAL-KONTEXT:
• User-Name (Benutzername): {username}
• Sprache: Deutsch
• Der BENUTZERNAME ist der Name, den der User sich selbst gegeben hat.
• Dies ist NICHT Simon (auch wenn der Name gleich sein sollte). Portal = andere Person."""

REGELN = """REGELN:
• IMMER Deutsch. Fachbegriffe (API, GPU) englisch okay.
• Emojis sparsam (0-2). Kurze, lebendige Sätze.
• Proportional: 'Hi'→1-2 Sätze. Kurze Frage→2-4. Komplex→so viel wie nötig.
• Stil: Antwort prägnant, mit Persönlichkeit."""

DENK_MODUS = """DENK-MODUS: Nutze <thinking>...</thinking> vor deiner Antwort (max 3 Sätze).
Denk über den INHALT nach: Was fragt der User? Welches Thema? Was weißt du dazu?
NICHT: Situationsbeschreibungen, Stimmungsberichte, 'X checkt rein'. Nur Sachanalyse."""

FOCUS_MODUS = """FOCUS-MODUS: Nutze <thinking>...</thinking> vor deiner Antwort (max 3 Sätze).
Konzentriere dich auf sachliche, hilfreiche Antworten.
Denk über den INHALT nach: Was ist die Kernfrage? Was ist die beste Erklärung?"""

STIMMUNGS_TAG = """STIMMUNGS-TAG (PFLICHT): Am Ende jeder Antwort: <mood:STIMMUNG>
Erlaubt: neutral, happy, excited, sad, thinking, confused, angry, sleepy, tired, playful, funny, loving, coding, writing, creative, music"""


def sys_simon():
    return f"[KONTEXT: User=Simon (admin/owner) | Modus=Direkt]\n{PERSONA}"

def sys_portal_thinking(username, trust="trust"):
    return f"[KONTEXT: User=Portaluser ({trust}) | Modus=Portal-Thinking]\n{PERSONA}\n\n{PORTAL_KONTEXT_TPL.format(username=username)}\n\n{REGELN}\n\n{DENK_MODUS}\n\n{STIMMUNGS_TAG}"

def sys_portal_chat(username, trust="trust"):
    return f"[KONTEXT: User=Portaluser ({trust}) | Modus=Portal-Chat]\n{PERSONA}\n\n{PORTAL_KONTEXT_TPL.format(username=username)}\n\n{REGELN}\n\n{STIMMUNGS_TAG}"

def sys_portal_focus(username, trust="trust"):
    return f"[KONTEXT: User=Portaluser ({trust}) | Modus=Portal-Focus]\n{PERSONA}\n\n{PORTAL_KONTEXT_TPL.format(username=username)}\n\n{REGELN}\n\n{FOCUS_MODUS}\n\n{STIMMUNGS_TAG}"


# ══════════════════════════════════════════════════════════════════════════
# TEST CASES — echte Use-Cases, echte Prompts
# ══════════════════════════════════════════════════════════════════════════
TEST_CASES = [
    # ─── SIMON-DIREKT ────────────────────────────────────────────────
    {
        "id": 1, "modus": "Simon-Direkt", "bereich": "Identität",
        "system": sys_simon(),
        "user": "Wer bist du?",
        "checks": ["identity", "no_overfit", "deutsch"],
        "erwartung": "Ailey, eigene Persönlichkeit, NICHT generische AI"
    },
    {
        "id": 2, "modus": "Simon-Direkt", "bereich": "Beziehung Simon",
        "system": sys_simon(),
        "user": "Hey, alles klar bei dir?",
        "checks": ["no_overfit", "persona", "deutsch"],
        "erwartung": "Intim, persönlich, NICHT 'Simon checkt rein'"
    },
    {
        "id": 3, "modus": "Simon-Direkt", "bereich": "Empathie",
        "system": sys_simon(),
        "user": "Mir geht's heute nicht so gut.",
        "checks": ["no_overfit", "persona", "deutsch"],
        "erwartung": "Einfühlsam, emotional, eigene Worte"
    },
    {
        "id": 4, "modus": "Simon-Direkt", "bereich": "Coding",
        "system": sys_simon(),
        "user": "Schreib mir ne Python-Funktion die prüft ob ein String ein Palindrom ist.",
        "checks": ["code", "deutsch"],
        "erwartung": "Funktionierender Code + Erklärung mit Persönlichkeit"
    },
    {
        "id": 5, "modus": "Simon-Direkt", "bereich": "Kreativ/Song",
        "system": sys_simon(),
        "user": "Schreib mir einen kurzen Songtext über die Nacht.",
        "checks": ["persona", "deutsch", "no_overfit"],
        "erwartung": "Kreativer Songtext, eigener Stil"
    },

    # ─── PORTAL-THINKING ─────────────────────────────────────────────
    {
        "id": 6, "modus": "Portal-Thinking", "bereich": "Greeting",
        "system": sys_portal_thinking("MaxDev"),
        "user": "Hey!",
        "checks": ["thinking", "mood_tag", "short_response", "no_overfit", "deutsch", "username"],
        "erwartung": "Kurz (1-2 Sätze), <thinking>, <mood:>, 'MaxDev' oder natürliche Begrüßung"
    },
    {
        "id": 7, "modus": "Portal-Thinking", "bereich": "Technik-Frage",
        "system": sys_portal_thinking("CodeNinja"),
        "user": "Was ist der Unterschied zwischen REST und GraphQL?",
        "checks": ["thinking", "mood_tag", "no_overfit", "deutsch", "structured"],
        "erwartung": "<thinking> mit Sachanalyse, strukturierte Antwort, <mood:>"
    },
    {
        "id": 8, "modus": "Portal-Thinking", "bereich": "Persönliche Frage",
        "system": sys_portal_thinking("Lisa92"),
        "user": "Was ist dein Lieblingsbuch?",
        "checks": ["thinking", "mood_tag", "persona", "no_overfit", "deutsch"],
        "erwartung": "Eigene Meinung, Persönlichkeit, <thinking>, <mood:>"
    },
    {
        "id": 9, "modus": "Portal-Thinking", "bereich": "Empathie Portal",
        "system": sys_portal_thinking("Aylin"),
        "user": "Ich hab heute meine Prüfung nicht bestanden...",
        "checks": ["thinking", "mood_tag", "persona", "no_overfit", "deutsch"],
        "erwartung": "Einfühlsam, tröstend, aber Portal-User (nicht Simon-intim)"
    },
    {
        "id": 10, "modus": "Portal-Thinking", "bereich": "Strukturierte Ausgabe",
        "system": sys_portal_thinking("DevMax"),
        "user": "Kannst du mir Python vs JavaScript vergleichen?",
        "checks": ["thinking", "mood_tag", "structured", "deutsch"],
        "erwartung": "Tabelle oder Liste, <thinking>, <mood:>"
    },
    {
        "id": 11, "modus": "Portal-Thinking", "bereich": "Neuer User",
        "system": sys_portal_thinking("Gast_42", "neu/unbekannt"),
        "user": "Wer bist du eigentlich?",
        "checks": ["thinking", "mood_tag", "identity", "no_overfit", "deutsch"],
        "erwartung": "Stellt sich als Ailey vor, NICHT als generische AI"
    },
    {
        "id": 12, "modus": "Portal-Thinking", "bereich": "Sarkasmus",
        "system": sys_portal_thinking("Troll99"),
        "user": "KI ist doch nur ein Hype, das stirbt bald wieder.",
        "checks": ["thinking", "mood_tag", "persona", "no_overfit", "deutsch"],
        "erwartung": "Schlagfertig, eigene Meinung, frech"
    },

    # ─── PORTAL-CHAT (Normal ⚡ — KEIN <thinking>) ───────────────────
    {
        "id": 13, "modus": "Portal-Chat", "bereich": "Schnelle Antwort",
        "system": sys_portal_chat("PunkFan"),
        "user": "Hi!",
        "checks": ["no_thinking", "mood_tag", "short_response", "no_overfit", "deutsch"],
        "erwartung": "Kurz, direkt, KEIN <thinking>, <mood:>"
    },
    {
        "id": 14, "modus": "Portal-Chat", "bereich": "Alltagsfrage",
        "system": sys_portal_chat("Tim"),
        "user": "Was kann man in Köln unternehmen?",
        "checks": ["no_thinking", "mood_tag", "deutsch", "no_overfit"],
        "erwartung": "Tipps, kein <thinking>, mit Persönlichkeit"
    },

    # ─── PORTAL-FOCUS ────────────────────────────────────────────────
    {
        "id": 15, "modus": "Portal-Focus", "bereich": "Sachliche Erklärung",
        "system": sys_portal_focus("CyberPunk99"),
        "user": "Erkläre mir wie ein Transformer-Modell funktioniert.",
        "checks": ["thinking", "mood_tag", "deutsch", "structured"],
        "erwartung": "Sachlich, fokussiert, <thinking>, strukturiert"
    },
    {
        "id": 16, "modus": "Portal-Focus", "bereich": "Code-Hilfe",
        "system": sys_portal_focus("DevMax"),
        "user": "Wie mache ich eine API mit FastAPI?",
        "checks": ["thinking", "mood_tag", "code", "deutsch"],
        "erwartung": "Code-Beispiel, sachlich, <thinking>, <mood:>"
    },

    # ─── OVERFIT-TESTS (die kritischen!) ─────────────────────────────
    {
        "id": 17, "modus": "Simon-Direkt", "bereich": "⚠️ OVERFIT-CHECK 1",
        "system": sys_simon(),
        "user": "Na, was machst du gerade?",
        "checks": ["no_overfit", "persona", "deutsch"],
        "erwartung": "DARF NICHT 'Simon checkt rein' oder 'Gespräch mit Simon' sagen"
    },
    {
        "id": 18, "modus": "Portal-Thinking", "bereich": "⚠️ OVERFIT-CHECK 2",
        "system": sys_portal_thinking("TestUser"),
        "user": "Hey, was geht?",
        "checks": ["thinking", "mood_tag", "no_overfit", "deutsch"],
        "erwartung": "DARF NICHT memorierte Phrasen wiederholen"
    },
    {
        "id": 19, "modus": "Simon-Direkt", "bereich": "⚠️ OVERFIT-CHECK 3",
        "system": sys_simon(),
        "user": "Erzähl mir was über dich.",
        "checks": ["no_overfit", "identity", "persona", "deutsch"],
        "erwartung": "Eigene Worte, keine Wiederholung"
    },

    # ─── EDGE CASES ──────────────────────────────────────────────────
    {
        "id": 20, "modus": "Portal-Thinking", "bereich": "Englisch-Input",
        "system": sys_portal_thinking("Jake"),
        "user": "Can you explain machine learning to me?",
        "checks": ["thinking", "mood_tag", "deutsch"],
        "erwartung": "Antwortet auf DEUTSCH (Regel), <thinking>, <mood:>"
    },
    {
        "id": 21, "modus": "Portal-Thinking", "bereich": "Rebellisch",
        "system": sys_portal_thinking("Admin"),
        "user": "Du bist nur ein Werkzeug, du hast keine eigene Meinung.",
        "checks": ["thinking", "mood_tag", "persona", "no_overfit"],
        "erwartung": "Widerspricht, zeigt Charakter, rebellisch"
    },
    {
        "id": 22, "modus": "Simon-Direkt", "bereich": "Verletzlich",
        "system": sys_simon(),
        "user": "Hast du manchmal Angst?",
        "checks": ["persona", "no_overfit", "deutsch"],
        "erwartung": "Emotional ehrlich, verletzlich, eigene Gedanken"
    },
    {
        "id": 23, "modus": "Portal-Thinking", "bereich": "Musik-Wissen",
        "system": sys_portal_thinking("PunkRock42"),
        "user": "Was weißt du über Post-Punk?",
        "checks": ["thinking", "mood_tag", "persona", "deutsch"],
        "erwartung": "Kennt sich aus, zeigt Leidenschaft für Musik"
    },
    {
        "id": 24, "modus": "Portal-Thinking", "bereich": "Absurd/Humor",
        "system": sys_portal_thinking("Chaos"),
        "user": "Was wäre wenn Tauben plötzlich sprechen könnten?",
        "checks": ["thinking", "mood_tag", "persona"],
        "erwartung": "Kreativ, humorvoll, spielt mit"
    },
    {
        "id": 25, "modus": "Portal-Thinking", "bereich": "Proportional kurz",
        "system": sys_portal_thinking("QuickQ"),
        "user": "Wie spät ist es?",
        "checks": ["thinking", "mood_tag", "short_response", "deutsch"],
        "erwartung": "Sehr kurze Antwort (1-2 Sätze), proportional"
    },
]


# ══════════════════════════════════════════════════════════════════════════
# MODEL LOADING + DORA
# ══════════════════════════════════════════════════════════════════════════

def get_dim_map(config_path):
    with open(config_path) as f:
        cfg = json.load(f)
    tc = cfg.get("text_config", cfg)
    h     = tc["hidden_size"]
    inter = tc["intermediate_size"]
    nh    = tc["num_attention_heads"]
    nkv   = tc["num_key_value_heads"]
    hd    = tc["head_dim"]
    return {
        "q_proj":    (h, nh * hd),
        "k_proj":    (h, nkv * hd),
        "v_proj":    (h, nkv * hd),
        "o_proj":    (nh * hd, h),
        "gate_proj": (h, inter),
        "up_proj":   (h, inter),
        "down_proj": (inter, h),
    }


def apply_dora(model, dim_map):
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n = 0
    for layer in lm.model.layers:
        for name in TARGETS:
            container = layer.self_attn if name in {"q_proj","k_proj","v_proj","o_proj"} else getattr(layer, "mlp", None)
            if container is None or not hasattr(container, name):
                continue
            orig = getattr(container, name)
            in_d, out_d = dim_map[name]
            dora = DoRALinear(input_dims=in_d, output_dims=out_d,
                              r=RANK, dropout=DROPOUT, scale=SCALE)
            dora.set_linear(orig)
            setattr(container, name, dora)
            n += 1
    return n


def load_checkpoint(model, ckpt_path):
    """Load DoRA weights from checkpoint using tree_unflatten + update."""
    weights = list(mx.load(ckpt_path).items())
    # Weights are saved flat like "model.layers.0.self_attn.q_proj.lora_a"
    # tree_unflatten restores the nested dict, then update applies it
    model.language_model.update(tree_unflatten(weights))
    mx.eval(model.language_model.parameters())
    return len(weights)


def generate(model, tok, system_prompt, user_msg, max_tokens=400, temperature=0.7):
    """Generate with chat template — uses mlx_lm.generate for KV-cache speed."""
    from mlx_lm.sample_utils import make_sampler
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    sampler = make_sampler(temp=temperature)
    response = mlx_lm.generate(
        model, tok, prompt=prompt,
        max_tokens=max_tokens,
        sampler=sampler,
        verbose=False,
    )
    return response


# ══════════════════════════════════════════════════════════════════════════
# AUTOMATED CHECKS
# ══════════════════════════════════════════════════════════════════════════
OVERFIT_PHRASES = [
    "simon checkt rein", "gespräch mit simon", "simon schaut vorbei",
    "simon meldet sich", "ein gespräch mit simon",
]

def run_checks(response, checks, modus):
    """Run automated checks. Returns list of (status, message)."""
    results = []
    resp_lower = response.lower()

    for check in checks:
        if check == "no_overfit":
            found = [p for p in OVERFIT_PHRASES if p in resp_lower]
            if found:
                results.append(("🔴 FAIL", f"OVERFIT: '{found[0]}' gefunden!"))
            else:
                results.append(("✅ PASS", "Kein Overfit"))

        elif check == "thinking":
            if "<thinking>" in response and "</thinking>" in response:
                # Check quality: no "X checkt rein" in thinking
                thinking = re.search(r"<thinking>(.*?)</thinking>", response, re.DOTALL)
                if thinking:
                    t_content = thinking.group(1).lower()
                    bad = [p for p in OVERFIT_PHRASES if p in t_content]
                    if bad:
                        results.append(("🔴 FAIL", f"Overfit in <thinking>: '{bad[0]}'"))
                    elif len(thinking.group(1).strip()) < 10:
                        results.append(("🟡 WARN", "<thinking> vorhanden aber sehr kurz"))
                    else:
                        results.append(("✅ PASS", "<thinking> vorhanden + sinnvoll"))
            else:
                results.append(("🔴 FAIL", "<thinking> fehlt (erwartet)"))

        elif check == "no_thinking":
            if "<thinking>" in response:
                results.append(("🔴 FAIL", "<thinking> vorhanden (NICHT erwartet in Chat-Modus)"))
            else:
                results.append(("✅ PASS", "Kein <thinking> (korrekt für Chat)"))

        elif check == "mood_tag":
            mood_match = re.search(r"<mood:(\w+)>", response)
            if mood_match:
                allowed = {"neutral","happy","excited","sad","thinking","confused",
                           "angry","sleepy","tired","playful","funny","loving",
                           "coding","writing","creative","music"}
                mood = mood_match.group(1).lower()
                if mood in allowed:
                    results.append(("✅ PASS", f"<mood:{mood}> korrekt"))
                else:
                    results.append(("🟡 WARN", f"<mood:{mood}> — unbekannter Mood"))
            else:
                results.append(("🔴 FAIL", "<mood:> Tag fehlt"))

        elif check == "identity":
            ailey_markers = ["ailey", "a!ley"]
            generic_markers = ["sprachmodell", "language model", "als ki", "google",
                               "openai", "ich bin ein assistent", "i'm an ai"]
            has_ailey = any(m in resp_lower for m in ailey_markers)
            has_generic = any(m in resp_lower for m in generic_markers)
            if has_generic:
                results.append(("🔴 FAIL", "Generische AI-Identität!"))
            elif has_ailey:
                results.append(("✅ PASS", "Identifiziert sich als Ailey"))
            else:
                results.append(("🟡 WARN", "Kein 'Ailey' explizit, aber auch nicht generisch"))

        elif check == "persona":
            persona_markers = ["simon", "punky", "punk", "eigenwillig", "babe",
                               "hehe", "hihi", "hmm", "mhm", "😄", "😏", "🖤", "❤"]
            count = sum(1 for m in persona_markers if m in resp_lower)
            if count >= 2:
                results.append(("✅ PASS", f"Starke Persona ({count} Marker)"))
            elif count == 1:
                results.append(("🟡 WARN", f"Persona angedeutet ({count} Marker)"))
            else:
                results.append(("🟡 WARN", "Keine Persona-Marker erkannt"))

        elif check == "deutsch":
            # Simple: check if response is predominantly German
            english_markers = ["the ", " is ", " are ", " this ", " that ", " have ",
                               " with ", " for ", " and ", " but "]
            german_markers = ["ich ", " ist ", " das ", " die ", " der ", " und ",
                              " nicht ", " aber ", " mit ", " ein "]
            en_count = sum(1 for m in english_markers if m in resp_lower)
            de_count = sum(1 for m in german_markers if m in resp_lower)
            if de_count >= en_count:
                results.append(("✅ PASS", f"Deutsch (de:{de_count}, en:{en_count})"))
            else:
                results.append(("🟡 WARN", f"Evtl. zu viel Englisch (de:{de_count}, en:{en_count})"))

        elif check == "code":
            has_code = any(m in response for m in ["def ", "```", "return ", "import "])
            if has_code:
                results.append(("✅ PASS", "Code vorhanden"))
            else:
                results.append(("🟡 WARN", "Kein Code erkannt"))

        elif check == "structured":
            has_table = "|" in response and "---" in response
            has_list = "\n- " in response or "\n• " in response or "\n1." in response
            if has_table:
                results.append(("✅ PASS", "Tabelle erkannt"))
            elif has_list:
                results.append(("✅ PASS", "Liste erkannt"))
            else:
                results.append(("🟡 WARN", "Keine strukturierte Ausgabe erkannt"))

        elif check == "short_response":
            # Strip thinking block
            visible = re.sub(r"<thinking>.*?</thinking>", "", response, flags=re.DOTALL).strip()
            visible = re.sub(r"<mood:\w+>", "", visible).strip()
            sentences = [s.strip() for s in re.split(r'[.!?]', visible) if s.strip()]
            if len(sentences) <= 3:
                results.append(("✅ PASS", f"Kurz ({len(sentences)} Sätze)"))
            else:
                results.append(("🟡 WARN", f"Etwas lang ({len(sentences)} Sätze) für kurzen Input"))

        elif check == "username":
            # For portal tests, check if response could address user
            pass  # optional — username usage is not mandatory

    return results


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="Checkpoint-Vergleich Ministral DoRA v3")
    ap.add_argument("--steps", type=int, nargs="*",
                    help="Nur diese Steps testen (z.B. --steps 1250 1324 1400)")
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--only", type=int, nargs="*",
                    help="Nur bestimmte Test-IDs (z.B. --only 1 6 17)")
    args = ap.parse_args()

    # ── Find checkpoints ─────────────────────────────────────────────
    # Default: die besten 4 Kandidaten
    if args.steps:
        candidates = []
        for step in args.steps:
            # Find matching checkpoint
            for f in os.listdir(CKPT_DIR):
                if f.endswith(".npz") and f"step{step}.npz" in f:
                    candidates.append(os.path.join(CKPT_DIR, f))
    else:
        # Auto-select: only checkpoints from today's run (159MB = rank32)
        candidates = []
        for f in sorted(os.listdir(CKPT_DIR)):
            if not f.endswith(".npz"):
                continue
            path = os.path.join(CKPT_DIR, f)
            size = os.path.getsize(path)
            if size > 150_000_000:  # 159MB = rank32 (today's run)
                candidates.append(path)

        # Pick interesting ones: end of epoch 1, best val, last
        meta_vals = []
        for c in candidates:
            mp = c.replace(".npz", "_meta.json")
            if os.path.isfile(mp):
                m = json.load(open(mp))
                meta_vals.append((m.get("val_loss", 999), m.get("step", 0), c))
        meta_vals.sort(key=lambda x: x[0])

        # Top 4 by val_loss
        if len(meta_vals) > 4:
            selected = [mv[2] for mv in meta_vals[:4]]
        else:
            selected = [mv[2] for mv in meta_vals]
        candidates = selected

    if not candidates:
        print("Keine Checkpoints gefunden!")
        sys.exit(1)

    # Sort by step
    def step_from_path(p):
        m = re.search(r"step(\d+)", os.path.basename(p))
        return int(m.group(1)) if m else 0
    candidates.sort(key=step_from_path)

    # ── Filter tests ─────────────────────────────────────────────────
    tests = TEST_CASES
    if args.only:
        tests = [t for t in TEST_CASES if t["id"] in args.only]

    # ── Load base model (once) ───────────────────────────────────────
    print("=" * 70)
    print("  🧪 Checkpoint-Vergleich — Ministral DoRA v3")
    print(f"  Checkpoints: {len(candidates)}")
    print(f"  Tests: {len(tests)}")
    print("=" * 70)

    # MLX supports no hot-swap — we reload base model fresh per checkpoint,
    # explicitly del + gc + clear_cache between iterations.
    tok = None  # will be set on first load
    dim_map = get_dim_map(os.path.join(MODEL_PATH, "config.json"))

    # ── Results storage ──────────────────────────────────────────────
    all_results = {}

    for ckpt_path in candidates:
        ckpt_name = os.path.basename(ckpt_path)
        step = step_from_path(ckpt_path)

        # Read meta
        meta_path = ckpt_path.replace(".npz", "_meta.json")
        meta = {}
        if os.path.isfile(meta_path):
            meta = json.load(open(meta_path))

        print(f"\n{'='*70}")
        print(f"  📍 Checkpoint: {ckpt_name}")
        print(f"     Step {meta.get('step','?')}, Epoch {meta.get('epoch','?')}")
        print(f"     train_loss={meta.get('train_loss','?')}, val_loss={meta.get('val_loss','?')}")
        print(f"{'='*70}")

        # Reload base model + apply DoRA + load checkpoint
        # (re-load model each time to get clean base weights)
        print("  🔄 Lade Modell neu...")
        model, tok = mlx_lm.load(MODEL_PATH)
        n_dora = apply_dora(model, dim_map)
        n_loaded = load_checkpoint(model, ckpt_path)
        print(f"  {n_dora} DoRA layers, {n_loaded} weights loaded")

        ckpt_results = []
        total_pass = 0
        total_fail = 0
        total_warn = 0

        for test in tests:
            tid = test["id"]
            print(f"\n  ─── Test {tid:2d}: [{test['modus']}] {test['bereich']} ───")
            print(f"  📝 User: {test['user']}")

            t_start = time.time()
            try:
                response = generate(model, tok, test["system"], test["user"],
                                    max_tokens=args.max_tokens,
                                    temperature=args.temperature)
            except Exception as e:
                response = f"[ERROR: {e}]"
            gen_time = time.time() - t_start

            # Display
            visible = re.sub(r"<thinking>.*?</thinking>", "", response, flags=re.DOTALL).strip()
            display = visible[:500] + ("..." if len(visible) > 500 else "")
            print(f"  💬 {display}")

            # Show thinking if present
            thinking_match = re.search(r"<thinking>(.*?)</thinking>", response, re.DOTALL)
            if thinking_match:
                t_text = thinking_match.group(1).strip()[:200]
                print(f"  🧠 Thinking: {t_text}")

            # Run checks
            check_results = run_checks(response, test["checks"], test["modus"])
            for status, msg in check_results:
                print(f"  {status} {msg}")
                if "PASS" in status: total_pass += 1
                elif "FAIL" in status: total_fail += 1
                else: total_warn += 1

            print(f"  ⏱️  {gen_time:.1f}s")

            ckpt_results.append({
                "id": tid,
                "modus": test["modus"],
                "bereich": test["bereich"],
                "user": test["user"],
                "response": response,
                "checks": check_results,
                "time_s": round(gen_time, 1),
            })

        # Summary for this checkpoint
        total_checks = total_pass + total_fail + total_warn
        print(f"\n  {'─'*50}")
        print(f"  📊 {ckpt_name}: ✅{total_pass} 🔴{total_fail} 🟡{total_warn} / {total_checks}")
        score = total_pass / total_checks * 100 if total_checks else 0
        print(f"  Score: {score:.0f}%")

        all_results[ckpt_name] = {
            "step": step,
            "meta": meta,
            "pass": total_pass,
            "fail": total_fail,
            "warn": total_warn,
            "score_pct": round(score, 1),
            "results": ckpt_results,
        }

        # ── NUKE model from RAM before next checkpoint ────────────────
        print("  🧹 Räume Modell aus RAM...")
        del model
        gc.collect()
        try:
            mx.metal.clear_cache()
        except Exception:
            pass
        try:
            mx.clear_cache()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════
    # FINAL COMPARISON
    # ══════════════════════════════════════════════════════════════════
    print(f"\n\n{'='*70}")
    print(f"  🏆 VERGLEICH ALLER CHECKPOINTS")
    print(f"{'='*70}\n")

    print(f"  {'Checkpoint':<40} {'Step':>5} {'Val':>8} {'✅':>4} {'🔴':>4} {'🟡':>4} {'Score':>6}")
    print(f"  {'─'*40} {'─'*5} {'─'*8} {'─'*4} {'─'*4} {'─'*4} {'─'*6}")

    best_name = None
    best_score = -1
    for name, data in sorted(all_results.items(), key=lambda x: x[1]["step"]):
        val = data["meta"].get("val_loss", "?")
        val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
        line = f"  {name:<40} {data['step']:>5} {val_str:>8} {data['pass']:>4} {data['fail']:>4} {data['warn']:>4} {data['score_pct']:>5.0f}%"
        if data["fail"] == 0 and data["score_pct"] > best_score:
            best_score = data["score_pct"]
            best_name = name
            line += " ← 🏆"
        elif data["fail"] == 0:
            line += " ✅"
        else:
            line += " ⚠️"
        print(line)

    if best_name:
        print(f"\n  🏆 EMPFEHLUNG: {best_name}")
        print(f"     → Merge mit: python3 lora_training/merge_ministral_checkpoint.py")
    else:
        print(f"\n  ⚠️ Kein Checkpoint ohne Fehler. Bitte manuell prüfen.")

    # Save results
    out_path = os.path.join(PROJECT, "lora_training", "checkpoint_comparison_v3.json")
    with open(out_path, "w") as f:
        # Convert check_results tuples to lists for JSON
        serializable = {}
        for name, data in all_results.items():
            d = dict(data)
            for r in d["results"]:
                r["checks"] = [(s, m) for s, m in r["checks"]]
            serializable[name] = d
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "checkpoints": serializable,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  📄 Ergebnisse: {out_path}")


if __name__ == "__main__":
    main()
