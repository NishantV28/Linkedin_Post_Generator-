import re
import logging
from typing import List, Tuple, Dict
from rank_bm25 import BM25Okapi

logger = logging.getLogger("autonomous_agent.memory.sparse_index")

ENGLISH_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't",
    "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having",
    "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how",
    "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its",
    "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such", "than", "that",
    "that's", "the", "their", "theirs", "them", "themselves", "then", "there", "there's", "these", "they",
    "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what",
    "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why",
    "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your",
    "yours", "yourself", "yourselves"
}

def tokenize_text(text: str) -> List[str]:
    """Basic lowercased alphanumeric tokenizer with stopword filtering for BM25 indexing."""
    tokens = re.findall(r"\w+", text.lower())
    return [t for t in tokens if t not in ENGLISH_STOPWORDS and len(t) > 1]

class BM25Index:
    """
    Sparse lexical index built dynamically per cycle from tokenized post documents.
    """
    def __init__(self, post_docs: List[Dict[str, str]]):
        """
        post_docs: list of dicts with keys 'id', 'text', 'topic_title'
        """
        self.doc_ids = [d["id"] for d in post_docs]
        corpus = [tokenize_text(f"{d.get('topic_title', '')} {d.get('text', '')}") for d in post_docs]
        if corpus and any(len(c) > 0 for c in corpus):
            self.bm25 = BM25Okapi(corpus)
            # Floor non-positive IDFs (which occur when corpus_size <= 2) so lexical matches yield positive scores
            for word, idf in self.bm25.idf.items():
                if idf <= 0:
                    self.bm25.idf[word] = 0.25
        else:
            self.bm25 = None

    def query_sparse(self, query_text: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Query BM25 index with query_text.
        Returns list of (post_id, score) tuples sorted descending by score.
        """
        if not self.bm25 or not self.doc_ids:
            return []

        tokens = tokenize_text(query_text)
        if not tokens:
            return []

        scores = self.bm25.get_scores(tokens)
        scored_pairs = [(self.doc_ids[i], float(scores[i])) for i in range(len(self.doc_ids)) if scores[i] > 0]
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        return scored_pairs[:top_k]
