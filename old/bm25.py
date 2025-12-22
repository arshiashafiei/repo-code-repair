from __future__ import annotations
import math
import re
from collections import Counter
from typing import Dict, List


def tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9_]+", text.lower())


class BM25:
    def __init__(self, docs: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = docs
        self.N = len(docs)
        self.avgdl = sum(len(d) for d in docs) / self.N if self.N else 0.0
        self.df: Dict[str, int] = Counter(set(t) for doc in docs for t in doc)
        self.idf: Dict[str, float] = {}
        for term, df in self.df.items():
            self.idf[term] = math.log((self.N - df + 0.5) / (df + 0.5) + 1e-9)

    def score(self, q: List[str], doc: List[str]) -> float:
        if not doc:
            return 0.0
        freq = Counter(doc)
        dl = len(doc)
        score = 0.0
        for term in q:
            f = freq.get(term, 0)
            if not f:
                continue
            idf = self.idf.get(term, 0.0)
            denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1.0))
            score += idf * (f * (self.k1 + 1)) / (denom or 1.0)
        return score

    def top_k(self, query_text: str, k: int) -> List[int]:
        q = tokenize(query_text)
        scores = [self.score(q, d) for d in self.docs]
        return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
