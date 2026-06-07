from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sentiment_classifier import LocalSentimentClassifier


def load_samples(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                continue
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local sentiment benchmark and emit report")
    parser.add_argument("--samples", default="benchmarks/sentiment_samples.jsonl")
    parser.add_argument("--report", default="benchmarks/latest_sentiment_report.md")
    parser.add_argument("--model", default="cardiffnlp/twitter-roberta-base-sentiment-latest")
    args = parser.parse_args()

    samples_path = Path(args.samples)
    report_path = Path(args.report)

    samples = load_samples(samples_path)
    classifier = LocalSentimentClassifier(model_name=args.model)

    total = 0
    correct = 0
    per_label = {"positive": [0, 0], "neutral": [0, 0], "negative": [0, 0]}

    for row in samples:
        text = str(row.get("text", ""))
        expected = str(row.get("label", "neutral")).lower()
        predicted = classifier.classify(text)

        total += 1
        if expected not in per_label:
            per_label[expected] = [0, 0]
        per_label[expected][1] += 1

        if predicted.label == expected:
            correct += 1
            per_label[expected][0] += 1

    accuracy = (correct / total) if total else 0.0

    lines = [
        "# Sentiment Benchmark Report",
        "",
        f"- generated_utc: {datetime.utcnow().isoformat()}",
        f"- model: {args.model}",
        f"- samples: {total}",
        f"- accuracy: {accuracy:.3f}",
        "",
        "## Per-label accuracy",
        "",
        "| Label | Correct | Total | Accuracy |",
        "|---|---:|---:|---:|",
    ]

    for label, (ok, count) in per_label.items():
        label_acc = (ok / count) if count else 0.0
        lines.append(f"| {label} | {ok} | {count} | {label_acc:.3f} |")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote report: {report_path}")


if __name__ == "__main__":
    main()
