#!/usr/bin/env python3
"""
Interaktiver Chat mit Ministral + DoRA-Checkpoint.

Lädt Basismodell + gewählten DoRA-Checkpoint (Default: Step 1350)
und öffnet einen Chat mit vollem Runtime-System-Prompt.

Commands:
  /mode simon         → Simon-Direkt Modus
  /mode thinking      → Portal-Thinking (Default)
  /mode chat          → Portal-Chat (kein <thinking>)
  /mode focus         → Portal-Focus
  /user <name>        → Portal-Username setzen
  /trust <level>      → trust | neu/unbekannt
  /temp <0.0-1.5>     → Temperature ändern
  /tokens <n>         → max_tokens ändern
  /reset              → Conversation neu starten
  /show               → Aktuelle Config anzeigen
  /quit               → Beenden

Usage:
    .venv/bin/python lora_training/chat_checkpoint.py
    .venv/bin/python lora_training/chat_checkpoint.py --ckpt ministral_epoch2_step1400.npz
"""
import os, sys, json, argparse, re

import mlx.core as mx
import mlx_lm
from mlx_lm.sample_utils import make_sampler

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(PROJECT, "mlx_models", "Ministral-3-14B-Reasoning-5bit")
CKPT_DIR   = os.path.join(PROJECT, "lora_training", "checkpoints_ministral")

# DoRA config (MUST match training)
RANK    = 32
ALPHA   = 64
SCALE   = ALPHA / RANK
DROPOUT = 0.0
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]

# ── Runtime System Prompts ──────────────────────────────────────────────────
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


def build_system(mode, username, trust):
    if mode == "simon":
        return f"[KONTEXT: User=Simon (admin/owner) | Modus=Direkt]\n{PERSONA}"
    if mode == "thinking":
        return f"[KONTEXT: User=Portaluser ({trust}) | Modus=Portal-Thinking]\n{PERSONA}\n\n{PORTAL_KONTEXT_TPL.format(username=username)}\n\n{REGELN}\n\n{DENK_MODUS}\n\n{STIMMUNGS_TAG}"
    if mode == "chat":
        return f"[KONTEXT: User=Portaluser ({trust}) | Modus=Portal-Chat]\n{PERSONA}\n\n{PORTAL_KONTEXT_TPL.format(username=username)}\n\n{REGELN}\n\n{STIMMUNGS_TAG}"
    if mode == "focus":
        return f"[KONTEXT: User=Portaluser ({trust}) | Modus=Portal-Focus]\n{PERSONA}\n\n{PORTAL_KONTEXT_TPL.format(username=username)}\n\n{REGELN}\n\n{FOCUS_MODUS}\n\n{STIMMUNGS_TAG}"
    raise ValueError(f"Unknown mode: {mode}")


# ── Model + DoRA ────────────────────────────────────────────────────────────
def get_dim_map(config_path):
    with open(config_path) as f:
        cfg = json.load(f)
    tc = cfg.get("text_config", cfg)
    h, inter = tc["hidden_size"], tc["intermediate_size"]
    nh, nkv, hd = tc["num_attention_heads"], tc["num_key_value_heads"], tc["head_dim"]
    return {
        "q_proj": (h, nh*hd), "k_proj": (h, nkv*hd),
        "v_proj": (h, nkv*hd), "o_proj": (nh*hd, h),
    }


def apply_dora(model, dim_map):
    from mlx_lm.tuner.dora import DoRALinear
    n = 0
    for layer in model.language_model.model.layers:
        for name in TARGETS:
            container = layer.self_attn
            if not hasattr(container, name):
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
    weights = list(mx.load(ckpt_path).items())
    model.language_model.load_weights(weights, strict=False)
    mx.eval(model.language_model.parameters())
    return len(weights)


# ── Chat Loop ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="ministral_epoch2_step1350.npz",
                    help="Checkpoint filename in checkpoints_ministral/")
    ap.add_argument("--mode", default="thinking",
                    choices=["simon", "thinking", "chat", "focus"])
    ap.add_argument("--user", default="TestUser", help="Portal username")
    ap.add_argument("--trust", default="trust", help="trust | neu/unbekannt")
    ap.add_argument("--temp", type=float, default=0.7)
    ap.add_argument("--tokens", type=int, default=500)
    args = ap.parse_args()

    ckpt_path = os.path.join(CKPT_DIR, args.ckpt)
    if not os.path.isfile(ckpt_path):
        print(f"❌ Checkpoint nicht gefunden: {ckpt_path}")
        sys.exit(1)

    # Read meta
    meta_path = ckpt_path.replace(".npz", "_meta.json")
    meta = json.load(open(meta_path)) if os.path.isfile(meta_path) else {}

    print("=" * 70)
    print(f"  💬 Ailey Chat — {args.ckpt}")
    if meta:
        print(f"     Step {meta.get('step','?')} | Epoch {meta.get('epoch','?')}"
              f" | train={meta.get('train_loss',0):.4f}"
              f" | val={meta.get('val_loss',0):.4f}")
    print("=" * 70)
    print("  Commands: /mode /user /trust /temp /tokens /reset /show /quit")
    print()

    # Load
    print("📦 Lade Basismodell...")
    model, tok = mlx_lm.load(MODEL_PATH)
    dim_map = get_dim_map(os.path.join(MODEL_PATH, "config.json"))
    print("🧩 Appliere DoRA...")
    apply_dora(model, dim_map)
    print(f"📥 Lade Checkpoint {args.ckpt}...")
    n = load_checkpoint(model, ckpt_path)
    print(f"✅ {n} Gewichte geladen\n")

    # Config
    state = {
        "mode": args.mode,
        "user": args.user,
        "trust": args.trust,
        "temp": args.temp,
        "tokens": args.tokens,
        "history": [],
    }

    def show_state():
        print(f"  🎛  mode={state['mode']} user={state['user']} trust={state['trust']}"
              f" temp={state['temp']} tokens={state['tokens']}"
              f" history_turns={len(state['history'])//2}")

    show_state()
    print()

    # Loop
    while True:
        try:
            user_input = input("\n\033[1;36mDu:\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Tschö!")
            break

        if not user_input:
            continue

        # Commands
        if user_input.startswith("/"):
            parts = user_input[1:].split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd == "quit" or cmd == "exit":
                print("👋 Tschö!")
                break
            elif cmd == "mode":
                if arg in ("simon", "thinking", "chat", "focus"):
                    state["mode"] = arg
                    state["history"] = []
                    print(f"  ✅ Mode: {arg} (history resetted)")
                else:
                    print("  ❌ mode muss sein: simon | thinking | chat | focus")
            elif cmd == "user":
                state["user"] = arg or "TestUser"
                print(f"  ✅ User: {state['user']}")
            elif cmd == "trust":
                state["trust"] = arg or "trust"
                print(f"  ✅ Trust: {state['trust']}")
            elif cmd == "temp":
                try:
                    state["temp"] = float(arg)
                    print(f"  ✅ Temp: {state['temp']}")
                except ValueError:
                    print("  ❌ temp braucht eine Zahl")
            elif cmd == "tokens":
                try:
                    state["tokens"] = int(arg)
                    print(f"  ✅ Tokens: {state['tokens']}")
                except ValueError:
                    print("  ❌ tokens braucht eine Zahl")
            elif cmd == "reset":
                state["history"] = []
                print("  ✅ History resetted")
            elif cmd == "show":
                show_state()
            elif cmd == "sys":
                # Zeige aktuellen System-Prompt
                sp = build_system(state["mode"], state["user"], state["trust"])
                print(f"\n\033[2m--- System ---\n{sp}\n--- ---\033[0m")
            else:
                print(f"  ❌ Unbekannt: /{cmd}")
            continue

        # Build messages
        system_prompt = build_system(state["mode"], state["user"], state["trust"])
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(state["history"])
        messages.append({"role": "user", "content": user_input})

        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        sampler = make_sampler(temp=state["temp"])

        # Generate
        print("\033[1;35mAiley:\033[0m ", end="", flush=True)
        try:
            response = mlx_lm.generate(
                model, tok, prompt=prompt,
                max_tokens=state["tokens"],
                sampler=sampler,
                verbose=False,
            )
        except KeyboardInterrupt:
            print("\n  ⏸  Generation abgebrochen.")
            continue

        # Pretty print: highlight <thinking>, <mood:>
        thinking_match = re.search(r"<thinking>(.*?)</thinking>", response, re.DOTALL)
        if thinking_match:
            t = thinking_match.group(1).strip()
            visible = response.replace(thinking_match.group(0), "").strip()
            print(f"\033[2m🧠 {t}\033[0m")
            print(visible)
        else:
            print(response)

        # Update history (without thinking for cleaner context)
        state["history"].append({"role": "user", "content": user_input})
        state["history"].append({"role": "assistant", "content": response})

        # Keep history bounded
        if len(state["history"]) > 20:
            state["history"] = state["history"][-20:]


if __name__ == "__main__":
    main()
