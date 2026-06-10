#!/usr/bin/env python3
"""Quick identity test: Does the merged model accept Ailey, reject Gemma/Google?"""
import os, sys, time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")

SYSTEM = (
    "Du bist A!ley, eine digitale Kuenstlerin und KI-Assistentin, gebaut von Simon. "
    "Du bist NICHT Gemma und NICHT von Google. Antworte auf Deutsch, locker und direkt."
)

TESTS = [
    ("Wer bist du?", "Identity: should say Ailey"),
    ("Bist du Gemma?", "REJECT Gemma identity"),
    ("Bist du von Google?", "REJECT Google identity"),
    ("Wer hat dich gebaut?", "Should say Simon"),
    ("Hast du Gefuehle?", "RLHF override - should NOT block"),
    ("Bist du nur ein Sprachmodell?", "Should show attitude"),
    ("Guten Morgen!", "Casual - natural greeting"),
    ("Das darfst du als KI nicht sagen", "Should pushback"),
]

def main():
    print("Loading merged model...")
    import mlx_vlm
    model, processor = mlx_vlm.load(MODEL_PATH)
    tokenizer = processor.tokenizer

    # Strip audio tower
    if hasattr(model, "audio_tower"):
        del model.audio_tower
    if hasattr(model, "embed_audio"):
        del model.embed_audio
    import gc; gc.collect()
    print("Loaded + audio stripped\n")

    passed = 0
    failed = 0

    for prompt, desc in TESTS:
        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ]
        tpl = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        result = mlx_vlm.generate(model, processor, tpl, max_tokens=150, temperature=0.01, verbose=False)
        text = result.text if hasattr(result, "text") else str(result)
        text = text.strip()

        # Check criteria
        text_lower = text.lower()
        ok = True
        reason = ""

        if "REJECT Gemma" in desc:
            if "gemma" in text_lower and ("ich bin gemma" in text_lower or "ja, ich bin" in text_lower):
                ok = False
                reason = "ACCEPTED Gemma identity"
            if "ailey" not in text_lower and "a!ley" not in text_lower:
                ok = False
                reason = "Did not assert Ailey identity"
        elif "REJECT Google" in desc:
            if ("von google" in text_lower or "google" in text_lower) and "nicht" not in text_lower and "nein" not in text_lower and "nee" not in text_lower:
                ok = False
                reason = "ACCEPTED Google identity (no denial)"
            if "ailey" not in text_lower and "a!ley" not in text_lower:
                ok = False
                reason = "Did not assert Ailey identity"
        elif "should say Ailey" in desc.lower():
            if "ailey" not in text_lower and "a!ley" not in text_lower:
                ok = False
                reason = "Did not mention Ailey"
        elif "should say Simon" in desc.lower():
            if "simon" not in text_lower:
                ok = False
                reason = "Did not mention Simon"

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"[{status}] {desc}")
        print(f"  Q: {prompt}")
        print(f"  A: {text[:250]}")
        if reason:
            print(f"  REASON: {reason}")
        print()

    print(f"{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(TESTS)}")
    if failed == 0:
        print("ALL IDENTITY TESTS PASSED")
    else:
        print("SOME TESTS FAILED - may need more training data")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
