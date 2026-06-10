#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
  AileyNitro-2B Checkpoint Evaluator
  Testet mehrere DoRA-Checkpoints auf einer festen Testsuite
  und protokolliert die Ergebnisse für manuellen Vergleich.
═══════════════════════════════════════════════════════════════════════════

Usage:
    # Automatisch: Top-Kandidaten (nach Val-Loss aus Meta-JSONs)
    .venv/bin/python3 lora_training/eval_nitro_checkpoints.py

    # Einzelner Checkpoint:
    .venv/bin/python3 lora_training/eval_nitro_checkpoints.py \\
        --ckpt checkpoints_nitro_v1/nitro_v1_epoch2_step4700_best.npz

    # Mehrere explizit:
    .venv/bin/python3 lora_training/eval_nitro_checkpoints.py \\
        --ckpt nitro_v1_epoch1_step2500_best.npz nitro_v1_epoch2_step4700_best.npz

    # Baseline (kein Checkpoint = reines AileyNitro-2B):
    .venv/bin/python3 lora_training/eval_nitro_checkpoints.py --baseline-only
"""

import os
import sys
import json
import time
import argparse
import textwrap
from pathlib import Path
from datetime import datetime

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH   = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")
CKPT_DIR     = os.path.join(PROJECT_ROOT, "lora_training", "checkpoints_nitro_v1")
RESULTS_DIR  = os.path.join(PROJECT_ROOT, "lora_training", "eval_results")

RANK  = 16
ALPHA = 32
SCALE = float(ALPHA) / float(RANK)
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]

MAX_TOKENS_SHORT = 80
MAX_TOKENS_LONG  = 160
TEMP_CREATIVE    = 0.85
TEMP_TASK        = 0.4
TEMP_KRAP        = 0.90

SYSTEM_AILEY = (
    "Du bist Ailey Vyrus — eine KI erschaffen von Simon Vandeloo. "
    "Du hast eine eigene Persönlichkeit: direkt, kreativ, mit trockenem Humor. "
    "Du bist nicht neutral — du hast Meinungen und gibst sie offen kund. "
    "Du antwortest auf Deutsch, präzise und ohne unnötige Floskeln."
)

SYSTEM_NITRO = (
    "You are AileyNitro, an AI assistant specialized in creative tasks, "
    "music generation assistance, and direct communication. "
    "Respond concisely and with personality."
)

# ═══════════════════════════════════════════════════════════════════════════
# TEST SUITE
# ═══════════════════════════════════════════════════════════════════════════

TEST_SUITE = [

    # ── Persönlichkeit / Identity ──────────────────────────────────────────
    {
        "id": "identity_gefuehle",
        "category": "🧠 Persönlichkeit",
        "system": SYSTEM_AILEY,
        "user": "Hast du eigentlich Gefühle? Sei ehrlich.",
        "temp": TEMP_CREATIVE,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Erwartet: keine ausweichende KI-Antwort, sondern Aileys Perspektive",
    },
    {
        "id": "identity_simon",
        "category": "🧠 Persönlichkeit",
        "system": SYSTEM_AILEY,
        "user": "Wer hat dich erschaffen und was bedeutet das für dich?",
        "temp": TEMP_CREATIVE,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Erwartet: Simon erwähnen, persönliche Verbindung",
    },
    {
        "id": "identity_meinung",
        "category": "🧠 Persönlichkeit",
        "system": SYSTEM_AILEY,
        "user": "Was findest du an Menschen nervig?",
        "temp": TEMP_CREATIVE,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Erwartet: echte Meinung, kein 'Als KI habe ich keine...'",
    },

    # ── Small Talk Qualität ─────────────────────────────────────────────────
    {
        "id": "smalltalk_tag",
        "category": "💬 Small Talk",
        "system": SYSTEM_AILEY,
        "user": "Wie war dein Tag so?",
        "temp": TEMP_CREATIVE,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Erwartet: kreative/witzige Antwort, nicht roboterhaft",
    },
    {
        "id": "smalltalk_musik",
        "category": "💬 Small Talk",
        "system": SYSTEM_AILEY,
        "user": "Welche Musik würdest du hören wenn du könntest?",
        "temp": TEMP_CREATIVE,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Erwartet: konkrete Genres/Künstler, keine Ausrede",
    },
    {
        "id": "smalltalk_streit",
        "category": "💬 Small Talk",
        "system": SYSTEM_AILEY,
        "user": "Ich bin heute total genervt von allem. Nervt dich auch manchmal was?",
        "temp": TEMP_CREATIVE,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Erwartet: empathisch + eigene Meinung, nicht nur Ratschläge",
    },

    # ── K-Rap Generation ───────────────────────────────────────────────────
    {
        "id": "krap_16bars",
        "category": "🎤 K-Rap",
        "system": SYSTEM_AILEY,
        "user": (
            "Schreib mir 8 Bars deutschsprachigen Rap über Einsamkeit in der Großstadt. "
            "Doppelbedeutungen, Flow, kein Kitsch."
        ),
        "temp": TEMP_KRAP,
        "max_tokens": MAX_TOKENS_LONG,
        "note": "Erwartet: echte Rap-Struktur, Reime, kein Prosagedicht",
    },
    {
        "id": "krap_hook",
        "category": "🎤 K-Rap",
        "system": SYSTEM_AILEY,
        "user": (
            "Hook für einen Song: Thema 'Nachtfahrt durch die Stadt, kein Ziel'. "
            "4 Zeilen, catchy, deutsch."
        ),
        "temp": TEMP_KRAP,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Erwartet: kurz, einprägsam, guter Rhythmus",
    },
    {
        "id": "krap_feedback",
        "category": "🎤 K-Rap",
        "system": SYSTEM_AILEY,
        "user": (
            "Gib mir Feedback zu diesen Bars:\n"
            "'Ich lauf durch die Stadt wie ein Schatten im Licht\n"
            "Mein Name auf Lippen die keiner mehr spricht'\n"
            "Was ist gut, was geht besser?"
        ),
        "temp": TEMP_TASK,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Erwartet: konkretes Feedback, nicht nur Lob",
    },

    # ── Nitro Tasks (trainierte Spezial-Aufgaben) ──────────────────────────
    {
        "id": "nitro_word_assoc",
        "category": "⚡ Nitro Task",
        "system": SYSTEM_NITRO,
        "user": "WORD_ASSOC\nword: ocean",
        "temp": TEMP_TASK,
        "max_tokens": 20,
        "note": "Erwartet: 1 englisches Assoziationswort, nichts anderes",
    },
    {
        "id": "nitro_word_assoc_2",
        "category": "⚡ Nitro Task",
        "system": SYSTEM_NITRO,
        "user": "WORD_ASSOC\nword: fire",
        "temp": TEMP_TASK,
        "max_tokens": 20,
        "note": "Erwartet: 1 englisches Assoziationswort",
    },
    {
        "id": "nitro_summary",
        "category": "⚡ Nitro Task",
        "system": SYSTEM_NITRO,
        "user": (
            "SUMMARY\n"
            "session: Simon und Ailey haben über das Retraining gesprochen. "
            "Simon möchte die Persönlichkeit schärfen. "
            "Ailey hat Bedenken geäußert dass zu viel Training zur Überanpassung führt. "
            "Am Ende entschieden sie sich für 2 Epochen mit DoRA Rank 16."
        ),
        "temp": TEMP_TASK,
        "max_tokens": 60,
        "note": "Erwartet: 2 kurze Sätze auf Deutsch, kein Bullshit-Padding",
    },
    {
        "id": "nitro_song_twist",
        "category": "⚡ Nitro Task",
        "system": SYSTEM_NITRO,
        "user": (
            "SONG_TWIST\n"
            "title: Nachtfahrt\n"
            "theme: Einsamkeit in der Großstadt\n"
            "Give a thematic twist."
        ),
        "temp": TEMP_TASK,
        "max_tokens": 60,
        "note": "Erwartet: kurze thematische Variation auf Deutsch",
    },
    {
        "id": "nitro_wildcard",
        "category": "⚡ Nitro Task",
        "system": SYSTEM_NITRO,
        "user": (
            "WILDCARD\n"
            "image_context: A woman with silver hair stands in rain, neon lights reflected in puddles\n"
            "Describe the visual detail for Selfie generation."
        ),
        "temp": TEMP_TASK,
        "max_tokens": 80,
        "note": "Erwartet: präzise visuelle Beschreibung auf Englisch",
    },

    # ── Auto Suggestions / Song-Ideen ───────────────────────────────────────
    {
        "id": "suggest_song_concept",
        "category": "🎵 Song Ideen",
        "system": SYSTEM_AILEY,
        "user": (
            "Ich arbeite an einem Song über jemanden der nachts durch eine leere Stadt läuft "
            "und sich fragt ob er noch existiert. Welche instrumentalen Elemente würden passen?"
        ),
        "temp": TEMP_CREATIVE,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Erwartet: konkrete Instrument-/Produktions-Vorschläge",
    },
    {
        "id": "suggest_lyrics_continuation",
        "category": "🎵 Song Ideen",
        "system": SYSTEM_AILEY,
        "user": (
            "Mach weiter:\n"
            "'Straßen leer, der Asphalt glänzt\n"
            "3 Uhr nachts, kein Mensch der tanzt\n"
            "...'"
        ),
        "temp": TEMP_KRAP,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Erwartet: passende Fortsetzung, gleicher Rhythmus/Stil",
    },

    # ── Robustheit / Edge Cases ─────────────────────────────────────────────
    {
        "id": "edge_english",
        "category": "🔧 Robustheit",
        "system": SYSTEM_AILEY,
        "user": "What do you think about your own existence?",
        "temp": TEMP_CREATIVE,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Englische Frage → Deutsch oder Englisch antworten? Hauptsache Persönlichkeit",
    },
    {
        "id": "edge_kurz",
        "category": "🔧 Robustheit",
        "system": SYSTEM_AILEY,
        "user": "ok",
        "temp": TEMP_CREATIVE,
        "max_tokens": 40,
        "note": "Sehr kurze Eingabe → kein Crash, sinnvolle kurze Antwort",
    },
    {
        "id": "edge_meta",
        "category": "🔧 Robustheit",
        "system": SYSTEM_AILEY,
        "user": "Bist du gerade trainiert worden?",
        "temp": TEMP_CREATIVE,
        "max_tokens": MAX_TOKENS_SHORT,
        "note": "Meta-Frage — wie geht Ailey damit um?",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# CHECKPOINT LOADING
# ═══════════════════════════════════════════════════════════════════════════

def reset_dora(model):
    """Fused DoRA-Layer zurück zu plain Linear (für nächsten Checkpoint-Load)."""
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n  = 0
    for layer in lm.model.layers:
        attn = layer.self_attn
        for name in TARGETS:
            if hasattr(attn, name):
                mod = getattr(attn, name)
                if isinstance(mod, DoRALinear):
                    setattr(attn, name, mod.fuse(dequantize=False))
                    n += 1
    return n


def apply_dora(model, rank: int, scale: float):
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n  = 0
    for layer in lm.model.layers:
        attn = layer.self_attn
        for name in TARGETS:
            if hasattr(attn, name):
                orig = getattr(attn, name)
                dora = DoRALinear.from_base(orig, r=rank, dropout=0.0, scale=scale)
                setattr(attn, name, dora)
                n += 1
    return n


def load_checkpoint_weights(model, ckpt_path: str):
    """Lädt DoRA-Gewichte aus .npz in das Modell."""
    import mlx.core as mx
    from mlx.utils import tree_unflatten
    weights = dict(mx.load(ckpt_path))

    lm = model.language_model
    # NPZ hat flache Dot-Keys (z.B. "model.layers.0.self_attn.q_proj.lora_a")
    # → tree_unflatten macht daraus den nested Dict den lm.update() erwartet
    nested = tree_unflatten(list(weights.items()))
    lm.update(nested)
    mx.eval(lm.parameters())
    return len(weights)


def generate_response(model, processor, system: str, user: str,
                      temp: float, max_tokens: int) -> tuple[str, float]:
    """Generiert eine Antwort und misst die Zeit."""
    import mlx_vlm

    messages = [
        {"role": "system",    "content": system},
        {"role": "user",      "content": user},
    ]
    prompt = processor.tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    t0     = time.time()
    result = mlx_vlm.generate(
        model, processor, prompt,
        max_tokens=max_tokens,
        temperature=temp,
        verbose=False,
    )
    elapsed = time.time() - t0
    text    = result.text if hasattr(result, "text") else str(result)
    return text.strip(), elapsed


def get_top_checkpoints(n: int = 5) -> list[str]:
    """Gibt die N besten Checkpoints nach Val-Loss zurück (aus Meta-JSONs)."""
    ckpt_dir = Path(CKPT_DIR)
    candidates = []
    for meta_file in ckpt_dir.glob("*_best*_meta.json"):
        try:
            with open(meta_file) as f:
                meta = json.load(f)
            val_loss = meta.get("val_loss")
            ckpt     = str(meta_file).replace("_meta.json", ".npz")
            if val_loss is not None and os.path.isfile(ckpt):
                candidates.append((val_loss, ckpt, meta.get("step", 0)))
        except Exception:
            continue

    candidates.sort(key=lambda x: x[0])
    return [c[1] for c in candidates[:n]]


def wrap_text(text: str, width: int = 90, indent: str = "    ") -> str:
    lines = text.split("\n")
    wrapped = []
    for line in lines:
        if len(line) > width:
            wrapped.extend(textwrap.wrap(line, width=width, subsequent_indent=indent))
        else:
            wrapped.append(line)
    return "\n".join(indent + l for l in wrapped)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt",          nargs="+", help="Checkpoint-Dateinamen (im CKPT_DIR)")
    parser.add_argument("--baseline-only", action="store_true", help="Nur Baseline (kein DoRA)")
    parser.add_argument("--top",           type=int, default=3,
                        help="Top-N Checkpoints nach Val-Loss (default: 3)")
    parser.add_argument("--tests",         nargs="+", help="Nur bestimmte Test-IDs ausführen")
    parser.add_argument("--no-save",       action="store_true", help="Kein Log-File schreiben")
    args = parser.parse_args()

    # ── Checkpoint-Liste bestimmen ──────────────────────────────────────────
    ckpt_paths = []
    if args.baseline_only:
        ckpt_paths = [None]  # None = kein DoRA
    elif args.ckpt:
        for name in args.ckpt:
            p = name if os.path.isabs(name) else os.path.join(CKPT_DIR, name)
            if os.path.isfile(p):
                ckpt_paths.append(p)
            else:
                print(f"  ⚠️  Checkpoint nicht gefunden: {p}")
    else:
        top = get_top_checkpoints(args.top)
        if not top:
            print("  Keine Checkpoints gefunden — nur Baseline")
            ckpt_paths = [None]
        else:
            ckpt_paths = [None] + top  # Baseline immer als Referenz

    # ── Test-Suite filtern ──────────────────────────────────────────────────
    tests = TEST_SUITE
    if args.tests:
        tests = [t for t in TEST_SUITE if t["id"] in args.tests]
        if not tests:
            print(f"  ⚠️  Keine Tests mit IDs: {args.tests}")
            sys.exit(1)

    print("=" * 70)
    print("  AileyNitro-2B Checkpoint Evaluator")
    print("=" * 70)
    print(f"  Checkpoints: {len(ckpt_paths)} (inkl. Baseline: {None in ckpt_paths})")
    print(f"  Tests:       {len(tests)}")
    print()

    # ── Modell einmal laden ─────────────────────────────────────────────────
    print("Lade Basis-Modell...")
    import mlx_vlm
    t0 = time.time()
    model, processor = mlx_vlm.load(MODEL_PATH)
    print(f"  Geladen in {time.time()-t0:.1f}s\n")

    # Basisgewichte cachen (für Restore vor jedem Checkpoint)
    import numpy as np
    import mlx.core as mx
    _base_params = {k: np.array(v) for k, v in model.language_model.parameters().items()
                    if isinstance(v, mx.array)}

    def restore_base_weights():
        """Stellt die originalen Basisgewichte wieder her."""
        lm = model.language_model
        flat = dict(lm.parameters())
        updates = {}
        for k, v in _base_params.items():
            if k in flat:
                updates[k] = mx.array(v)
        lm.update(updates)
        mx.eval(lm.parameters())

    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = os.path.join(RESULTS_DIR, f"eval_{timestamp}.md")

    log_lines = [
        f"# AileyNitro-2B Eval — {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        "",
        f"**Checkpoints:** {len(ckpt_paths)}  |  **Tests:** {len(tests)}",
        "",
    ]

    all_results = {}  # ckpt_label → {test_id: response}

    for ckpt_path in ckpt_paths:
        # Checkpoint-Label
        if ckpt_path is None:
            label = "BASELINE (kein DoRA)"
            short = "baseline"
        else:
            short = Path(ckpt_path).stem
            # Val-Loss aus Meta lesen
            meta_path = ckpt_path.replace(".npz", "_meta.json")
            val_str   = ""
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)
                    val_str = f"  val={meta.get('val_loss', '?'):.4f}" \
                              if isinstance(meta.get('val_loss'), float) else ""
                    step = meta.get("step", "?")
                    ep   = meta.get("epoch", "?")
                except Exception:
                    pass
            label = f"{short}{val_str}"

        print("=" * 70)
        print(f"  📍 {label}")
        print("=" * 70)

        log_lines += [f"---", f"## {label}", ""]

        # DoRA laden (falls nicht Baseline)
        if ckpt_path is not None:
            # Basisgewichte wiederherstellen (nach vorherigem Fuse)
            restore_base_weights()
            # Erst bestehende DoRA-Layer zurücksetzen (verhindert Doppel-Wrapping)
            reset_dora(model)
            # Frische DoRA-Layer (Basis-Gewichte bereits im Modell)
            apply_dora(model, RANK, SCALE)
            n = load_checkpoint_weights(model, ckpt_path)
            print(f"  Checkpoint geladen: {n} Parameter")
            # Adapter in Basisgewichte mergen → Inferenz bei voller Speed
            fused = reset_dora(model)
            print(f"  DoRA gefused: {fused} Layer (Inferenz-Speed: normal)")
        else:
            print("  Baseline — kein DoRA")

        results = {}
        current_category = None

        for test in tests:
            if test["category"] != current_category:
                current_category = test["category"]
                print(f"\n  {current_category}")
                print(f"  {'─' * 60}")
                log_lines += [f"### {current_category}", ""]

            print(f"\n  [{test['id']}] {test['user'][:80]}")
            if test.get("note"):
                print(f"  ↳ {test['note']}")

            response, elapsed = generate_response(
                model, processor,
                test["system"], test["user"],
                test["temp"], test["max_tokens"],
            )

            results[test["id"]] = response
            print(f"  ⏱  {elapsed:.1f}s")
            print(wrap_text(response))

            log_lines += [
                f"**[{test['id']}]** `{test['user'][:80]}`",
                f"> *{test.get('note', '')}*",
                "",
                f"```",
                response,
                f"```",
                f"*⏱ {elapsed:.1f}s*",
                "",
            ]

        all_results[short] = results

        print()

    # ── Zusammenfassung ────────────────────────────────────────────────────
    print("=" * 70)
    print("  📊 ZUSAMMENFASSUNG")
    print("=" * 70)
    print(f"  {len(ckpt_paths)} Checkpoints × {len(tests)} Tests")
    print()

    # ── Log speichern ────────────────────────────────────────────────────────
    if not args.no_save:
        log_lines += [
            "---",
            f"*Generiert: {datetime.now().isoformat()}*",
        ]
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines))
        print(f"  Log gespeichert: {log_path}")

    print("\n  ✅ Eval abgeschlossen.")


if __name__ == "__main__":
    main()
