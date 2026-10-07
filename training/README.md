# Vera — deep training (voice & conversation)

Three steps, in order:

1. **Measure** — `python -m evals.conversation_eval --model <model>`
   Scores real multi-turn conversations on checkable dimensions (context recall,
   in-character, concise, holds space, no emoji-spam, honest, natural). The
   baseline that makes tuning measurable.

2. **Fine-tune (LoRA, on-device via MLX)**
   - `python -m training.build_dataset`   → persona-consistent chat data
   - `python -m training.train_lora`       → LoRA on Qwen2.5-3B (Apple Silicon)
   - `python -m training.train_lora --fuse`→ bake adapter into `training/vera-tuned`
   - `ollama create vera-tuned -f training/vera-tuned.Modelfile`
   - re-run the eval on `vera-tuned` to see the lift.

3. **Prompt/voice tuning** — her innate style now writes "for the ear" (no emoji /
   markdown), stripped again at the TTS layer as a safety net.

Result: `vera-tuned` passes 10/10 eval scenarios and runs ~2.6x faster than the
7B baseline (it's a 3B), so replies are snappier while staying in-character.
