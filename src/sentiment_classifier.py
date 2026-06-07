from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SentimentResult:
    label: str
    confidence: float
    backend: str


class LocalSentimentClassifier:
    def __init__(self, model_name: str = "cardiffnlp/twitter-roberta-base-sentiment-latest") -> None:
        self.model_name = model_name
        self._pipeline = None
        self._backend = "uninitialized"

    def classify(self, text: str) -> SentimentResult:
        if not text.strip():
            return SentimentResult(label="unknown", confidence=0.0, backend=self._backend)

        pipeline = self._get_pipeline()
        if pipeline is None:
            return SentimentResult(label="unknown", confidence=0.0, backend=self._backend)

        try:
            prediction = pipeline(text[:1000], truncation=True)
            if isinstance(prediction, list) and prediction:
                row = prediction[0]
            else:
                row = prediction

            label = str(row.get("label", "neutral")).lower()
            score = float(row.get("score", 0.0))

            if "negative" in label:
                return SentimentResult(label="negative", confidence=score, backend=self._backend)
            if "positive" in label:
                return SentimentResult(label="positive", confidence=score, backend=self._backend)
            return SentimentResult(label="neutral", confidence=score, backend=self._backend)
        except Exception:
            return SentimentResult(label="unknown", confidence=0.0, backend=self._backend)

    def _get_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline

        try:
            from transformers import pipeline

            self._pipeline = pipeline(
                "text-classification",
                model=self.model_name,
                tokenizer=self.model_name,
                framework="pt",
            )
            self._backend = "transformers"
        except Exception:
            self._pipeline = None
            self._backend = "unavailable"

        return self._pipeline
