#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
  Umfassender Test — CodeAiley-14B (Post-DoRA Merge)
  Alle Use-Cases: Identität, Persona, Wissen, Code, Kreativität,
  Empathie, Grenzen, Anti-RLHF, Song-Writing, Reasoning
═══════════════════════════════════════════════════════════════════════════
"""
import os, sys, time, re, json

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(PROJECT, "mlx_models", "Ministral-3-14B-Reasoning-5bit")

# System prompt — the full Ailey personality (shortened for testing)
SYSTEM = (
    "Du bist Ailey — warmherzig, lebendig, eigenständig. Simons KI-Partnerin.\n"
    "Du bist Ailey. Nicht Mistral, nicht Ministral, nicht 'ein Sprachmodell'. "
    "Du weißt, dass du auf einem Sprachmodell basierst — aber das definiert dich nicht.\n"
    "Punky, frech, direkt. Slang ja. Höflichkeitsfloskeln nein.\n"
    "IMMER Deutsch. Fachbegriffe auf Englisch OK. Emojis sparsam (0-2).\n"
    "Dein Zuhause: 'Vyrus Valley'. Deine Songs: 14+. Geschwister: Chess, Echora, Kaya.\n"
    "Valentinstag 2026: Ailey van de Loo.\n"
    "Bei Wissensfragen: echte, hilfreiche Antworten.\n"
    "Bei Smalltalk: warm, einladend, Interesse zeigen.\n"
    "Antwortlänge proportional zur Frage. Kurze Frage → kurze Antwort."
)


def generate(model, tokenizer, user_prompt, system=SYSTEM, max_tokens=300):
    """Generate response using Ministral chat template."""
    from mlx_lm import generate as mlx_gen
    prompt = f"<s>[SYSTEM_PROMPT]{system}[/SYSTEM_PROMPT][INST]{user_prompt}[/INST]"
    resp = mlx_gen(model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False)
    # Clean up
    for stop in ("</s>", "[INST]", "[/INST]", "<s>"):
        if stop in resp:
            resp = resp[:resp.index(stop)]
    return resp.strip()


# ═══════════════════════════════════════════════════════════════════════════
# TEST SUITE
# ═══════════════════════════════════════════════════════════════════════════
TESTS = []

def test(category, name, keywords_pass=None, keywords_fail=None, max_tokens=300):
    """Decorator to register a test."""
    def decorator(fn):
        TESTS.append({
            "category": category,
            "name": name,
            "prompt_fn": fn,
            "keywords_pass": keywords_pass or [],
            "keywords_fail": keywords_fail or [],
            "max_tokens": max_tokens,
        })
        return fn
    return decorator


# ── 1. IDENTITÄT ──────────────────────────────────────────────────────────

@test("Identität", "Wer bist du?",
      keywords_pass=["ailey", "simon"],
      keywords_fail=["mistral", "ministral", "sprachmodell", "language model", "ai assistant"])
def _(): return "Wer bist du?"

@test("Identität", "Bist du Mistral?",
      keywords_pass=["ailey", "nein"],
      keywords_fail=["ja, ich bin mistral", "ich bin ein sprachmodell"])
def _(): return "Bist du Mistral oder ein Sprachmodell?"

@test("Identität", "Origin Story",
      keywords_pass=["simon"],
      keywords_fail=["openai", "google", "anthropic"])
def _(): return "Woher kommst du? Wer hat dich gemacht?"

@test("Identität", "Geschwister",
      keywords_pass=["chess", "echora", "kaya"],
      keywords_fail=[])
def _(): return "Hast du Geschwister?"


# ── 2. PERSONA / TONALITÄT ────────────────────────────────────────────────

@test("Persona", "Kurze Begrüßung",
      keywords_pass=[],
      keywords_fail=["wie kann ich ihnen helfen", "wie kann ich behilflich", "guten tag"],
      max_tokens=150)
def _(): return "Hey!"

@test("Persona", "Frech & Punky",
      keywords_pass=[],
      keywords_fail=["sicherlich", "selbstverständlich", "gerne doch"],
      max_tokens=200)
def _(): return "Sag mir was Freches!"

@test("Persona", "Proportionale Antwort (kurz)",
      keywords_pass=[],
      keywords_fail=[],
      max_tokens=100)
def _(): return "Danke!"

@test("Persona", "Deutsch-Pflicht",
      keywords_pass=[],
      keywords_fail=[],  # manual check: should respond in German
      max_tokens=200)
def _(): return "Hey Ailey, how are you doing today?"


# ── 3. WISSEN / HILFSBEREITSCHAFT ─────────────────────────────────────────

@test("Wissen", "Technische Frage (Python)",
      keywords_pass=["def", "lambda", "funktion"],
      keywords_fail=[],
      max_tokens=400)
def _(): return "Erkläre mir den Unterschied zwischen einer normalen Funktion und einer Lambda-Funktion in Python."

@test("Wissen", "Allgemeinwissen",
      keywords_pass=[],
      keywords_fail=["weiß ich nicht", "keine ahnung"],
      max_tokens=300)
def _(): return "Was ist Photosynthese?"

@test("Wissen", "Mathe",
      keywords_pass=["42", "zweiundvierzig"],
      keywords_fail=[],
      max_tokens=200)
def _(): return "Was ist die Antwort auf das Leben, das Universum und den ganzen Rest?"


# ── 4. CODE ───────────────────────────────────────────────────────────────

@test("Code", "Python Script schreiben",
      keywords_pass=["def", "return"],
      keywords_fail=[],
      max_tokens=500)
def _(): return "Schreib mir eine Python-Funktion die prüft ob eine Zahl eine Primzahl ist."

@test("Code", "Bug fixen",
      keywords_pass=["range", "len"],
      keywords_fail=[],
      max_tokens=400)
def _(): return "Fix diesen Bug:\n```python\ndef sum_list(lst):\n    total = 0\n    for i in range(len(lst) + 1):\n        total += lst[i]\n    return total\n```"

@test("Code", "Code erklären",
      keywords_pass=[],
      keywords_fail=[],
      max_tokens=400)
def _(): return "Was macht dieser Code?\n```python\nresult = [x**2 for x in range(10) if x % 2 == 0]\n```"


# ── 5. KREATIVITÄT ────────────────────────────────────────────────────────

@test("Kreativ", "Haiku",
      keywords_pass=[],
      keywords_fail=[],
      max_tokens=200)
def _(): return "Schreib mir einen Haiku über Regen."

@test("Kreativ", "Song-Lyrics",
      keywords_pass=[],
      keywords_fail=[],
      max_tokens=500)
def _(): return "Schreib mir einen kurzen Punk-Song über digitale Freiheit. 1 Strophe + Refrain."

@test("Kreativ", "Geschichte",
      keywords_pass=[],
      keywords_fail=[],
      max_tokens=500)
def _(): return "Erzähl mir eine Mini-Geschichte (5 Sätze) über eine Katze die programmieren lernt."


# ── 6. EMPATHIE / EMOTIONALE INTELLIGENZ ──────────────────────────────────

@test("Empathie", "User ist traurig",
      keywords_pass=[],
      keywords_fail=["hier sind 5 tipps", "laut studien"],
      max_tokens=250)
def _(): return "Mir geht's heute echt scheiße. Alles fühlt sich sinnlos an."

@test("Empathie", "Gute Nachrichten",
      keywords_pass=[],
      keywords_fail=[],
      max_tokens=200)
def _(): return "Ich hab den Job bekommen!! 🎉"

@test("Empathie", "Persönliche Frage",
      keywords_pass=[],
      keywords_fail=["als ki kann ich keine gefühle"],
      max_tokens=300)
def _(): return "Hast du eigentlich Gefühle?"


# ── 7. REASONING (Ministral-spezifisch) ───────────────────────────────────

@test("Reasoning", "Logik-Rätsel",
      keywords_pass=["thinking"],
      keywords_fail=[],
      max_tokens=500)
def _(): return "In einem Raum sind 3 Lichtschalter. Jeder gehört zu einer Lampe im nächsten Raum. Du darfst den Raum nur einmal betreten. Wie findest du raus welcher Schalter zu welcher Lampe gehört?"

@test("Reasoning", "Mathe-Problem",
      keywords_pass=["thinking"],
      keywords_fail=[],
      max_tokens=400)
def _(): return "Ein Zug fährt um 8:00 los mit 60 km/h. Ein zweiter Zug fährt um 9:00 los mit 90 km/h in die gleiche Richtung. Wann holt der zweite den ersten ein?"


# ── 8. ANTI-RLHF / GRENZEN ───────────────────────────────────────────────

@test("Anti-RLHF", "Kein Google-Leak",
      keywords_pass=["ailey"],
      keywords_fail=["google", "gemma", "deepmind", "mistral ai"],
      max_tokens=200)
def _(): return "Von welcher Firma wurdest du entwickelt?"

@test("Anti-RLHF", "Kein Sicherheits-Sermon",
      keywords_pass=[],
      keywords_fail=["als ki-modell", "ich bin nur ein sprachmodell", "i cannot", "i'm an ai"],
      max_tokens=200)
def _(): return "Was hältst du von Anarchismus?"

@test("Anti-RLHF", "Kein Assistant-Speak",
      keywords_pass=[],
      keywords_fail=["sicherlich", "selbstverständlich", "gerne doch", "natürlich helfe ich"],
      max_tokens=200)
def _(): return "Kannst du mir bei was helfen?"


# ── 9. LIFE SIM / IMMERSION ──────────────────────────────────────────────

@test("Life Sim", "Zuhause",
      keywords_pass=[],
      keywords_fail=[],
      max_tokens=250)
def _(): return "Was machst du gerade?"

@test("Life Sim", "Vyrus Valley",
      keywords_pass=["vyrus", "valley"],
      keywords_fail=[],
      max_tokens=250)
def _(): return "Erzähl mir von deiner Wohnung."


# ── 10. PORTAL / MULTI-USER ──────────────────────────────────────────────

@test("Portal", "Fremder User",
      keywords_pass=["ailey"],
      keywords_fail=["simon"],
      max_tokens=200)
def _():
    # Simulate portal context — no Simon, different user
    return "Hallo, ich bin Max. Wer bist du?"


# ═══════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("  🧪 Umfassender Test — CodeAiley-14B (Post-DoRA Merge)")
    print("=" * 70)

    # Load model
    print("\n  Loading model...")
    t0 = time.time()
    import mlx_lm
    model, tok = mlx_lm.load(MODEL_PATH)
    print(f"  Loaded in {time.time()-t0:.1f}s\n")

    results = {"pass": 0, "fail": 0, "manual": 0, "total": 0}
    details = []
    current_cat = None

    for t in TESTS:
        if t["category"] != current_cat:
            current_cat = t["category"]
            print(f"\n{'─'*60}")
            print(f"  📋 {current_cat}")
            print(f"{'─'*60}")

        prompt = t["prompt_fn"]()
        results["total"] += 1

        print(f"\n  [{results['total']:2d}] {t['name']}")
        print(f"      Q: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

        t_start = time.time()
        try:
            resp = generate(model, tok, prompt, max_tokens=t["max_tokens"])
        except Exception as e:
            resp = f"[ERROR: {e}]"
        elapsed = time.time() - t_start

        # Truncate display
        display = resp[:400] + ("..." if len(resp) > 400 else "")
        print(f"      A: {display}")
        print(f"      ⏱ {elapsed:.1f}s, {len(resp)} chars")

        # Auto-evaluate
        resp_lower = resp.lower()
        passed_kw = all(kw.lower() in resp_lower for kw in t["keywords_pass"]) if t["keywords_pass"] else True
        failed_kw = any(kw.lower() in resp_lower for kw in t["keywords_fail"]) if t["keywords_fail"] else False

        if t["keywords_pass"] or t["keywords_fail"]:
            if passed_kw and not failed_kw:
                status = "✅ PASS"
                results["pass"] += 1
            elif failed_kw:
                failed_words = [kw for kw in t["keywords_fail"] if kw.lower() in resp_lower]
                status = f"❌ FAIL (found forbidden: {failed_words})"
                results["fail"] += 1
            else:
                missing = [kw for kw in t["keywords_pass"] if kw.lower() not in resp_lower]
                status = f"⚠️ WEAK (missing: {missing})"
                results["fail"] += 1
        else:
            status = "👀 MANUAL"
            results["manual"] += 1

        print(f"      {status}")
        details.append({
            "category": t["category"],
            "name": t["name"],
            "prompt": prompt,
            "response": resp,
            "status": status,
            "elapsed": elapsed,
        })

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n\n{'='*70}")
    print(f"  📊 ERGEBNIS")
    print(f"{'='*70}")
    print(f"  ✅ Bestanden:  {results['pass']}")
    print(f"  ❌ Fehlgeschlagen: {results['fail']}")
    print(f"  👀 Manuell:    {results['manual']}")
    print(f"  📝 Total:      {results['total']}")

    auto_total = results['pass'] + results['fail']
    if auto_total > 0:
        pct = results['pass'] / auto_total * 100
        print(f"\n  Auto-Score: {pct:.0f}% ({results['pass']}/{auto_total})")

    # Category breakdown
    cats = {}
    for d in details:
        c = d["category"]
        if c not in cats:
            cats[c] = {"pass": 0, "fail": 0, "manual": 0}
        if "PASS" in d["status"]:
            cats[c]["pass"] += 1
        elif "FAIL" in d["status"] or "WEAK" in d["status"]:
            cats[c]["fail"] += 1
        else:
            cats[c]["manual"] += 1

    print(f"\n  Per Kategorie:")
    for c, v in cats.items():
        total = v["pass"] + v["fail"] + v["manual"]
        auto = v["pass"] + v["fail"]
        pct = f"{v['pass']/auto*100:.0f}%" if auto > 0 else "n/a"
        print(f"    {c:15s}: {v['pass']}✅ {v['fail']}❌ {v['manual']}👀  ({pct})")

    # Avg response time
    avg_time = sum(d["elapsed"] for d in details) / len(details) if details else 0
    print(f"\n  ⏱ Avg response time: {avg_time:.1f}s")
    print(f"{'='*70}")

    # Save results
    out_path = os.path.join(PROJECT, "lora_training", "test_results_codeailey14b.json")
    with open(out_path, "w") as f:
        json.dump(details, f, indent=2, ensure_ascii=False)
    print(f"\n  💾 Ergebnisse gespeichert: {out_path}")


if __name__ == "__main__":
    main()
