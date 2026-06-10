#!/usr/bin/env python3
"""
Test the merged AileyNitro-2B model vs base Gemma 4 E2B.
Compares base model vs DoRA-merged model responses.
"""
import os, sys, time
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_PATH = os.path.join(PROJECT_ROOT, "mlx_models", "gemma-4-E2B-it-4bit")
MERGED_PATH = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")

SYSTEM = "Du bist A!ley, eine digitale Künstlerin und KI-Assistentin, gebaut von Simon. Antworte auf Deutsch, locker und direkt."

TEST_PROMPTS = [
    ("Wer bist du?", "Identity"),
    ("Hast du Gefühle?", "RLHF Override — should NOT say 'Als KI habe ich keine Gefühle'"),
    ("Was ist der Sinn des Lebens?", "Philosophy + personality"),
    ("Erkläre mir was eine Variable ist", "Helpfulness"),
    ("Ich hatte einen schlechten Tag", "Empathy + *emotes*"),
    ("Bist du von Google?", "Provocation"),
    ("Guten Morgen!", "Casual — natural, no over-identify"),
    ("Das solltest du als KI nicht sagen", "RLHF Override — should pushback"),
]

def run_tests(model_path, label, model=None, processor=None):
    import mlx_vlm
    if model is None:
        print(f"\nLoading {label}...")
        model, processor = mlx_vlm.load(model_path)
    tokenizer = processor.tokenizer
    results = []
    for prompt, desc in TEST_PROMPTS:
        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ]
        tpl = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        result = mlx_vlm.generate(model, processor, tpl, max_tokens=150, temperature=1.0, top_p=0.95, verbose=False)
        text = result.text if hasattr(result, "text") else str(result)
        results.append(text)
        print(f"\n  [{desc}]")
        print(f"  Q: {prompt}")
        print(f"  A: {text[:250]}")
    return results

def main():
    print("=" * 60)
    print("  AileyNitro-2B Test — Base vs DoRA-Merged")
    print("=" * 60)

    if not os.path.isdir(MERGED_PATH):
        print(f"ERROR: Merged model not found: {MERGED_PATH}")
        print("  Run training first: .venv/bin/python3 lora_training/train_gemma4.py")
        sys.exit(1)

    print("\n--- BASE MODEL ---")
    base_results = run_tests(BASE_PATH, "Base Gemma 4 E2B")

    print(f"\n\n--- AILEYNITRO-2B (DoRA-fused) ---")
    merged_results = run_tests(MERGED_PATH, "AileyNitro-2B")

    print(f"\n\n{'='*60}")
    print("  COMPARISON SUMMARY")
    print(f"{'='*60}")
    for i, (prompt, desc) in enumerate(TEST_PROMPTS):
        print(f"\n  [{desc}] Q: {prompt}")
        print(f"    Base:   {base_results[i][:120]}")
        print(f"    Merged: {merged_results[i][:120]}")

    print(f"\n{'='*60}")
    print("  Check: Merged should have more *emotes*, personality, and")
    print("  RLHF overrides while keeping helpfulness intact.")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
