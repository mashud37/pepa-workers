"""Extract noun phrases, named entities, and subject-verb-object triplets
from a single spaCy pass as hints that sharpen the model's extraction
without replacing the full text.
"""
import re
import threading
from collections import Counter

# spaCy's pipeline is not safe to call from multiple threads at once, so each
# worker thread loads and uses its own model.
_local = threading.local()
_ENTITY_LABELS = {
    "ORG",
    "PERSON",
    "GPE",
    "LOC",
    "PRODUCT",
    "WORK_OF_ART",
    "LAW",
    "EVENT",
    "NORP",
    "FAC",
}
# Discourse verbs are scaffolding ("show", "is"), not the paper's claims.
_STOP_VERBS = {
    "be",
    "have",
    "do",
    "show",
    "use",
    "make",
    "give",
    "find",
    "see",
    "include",
    "provide",
    "present",
    "describe",
}
_MAX_CHARS = 200_000
_TOP_NOUN_PHRASES = 25
_TOP_ENTITIES = 25
_TOP_SVO_TRIPLETS = 30


def _load_nlp():
    nlp = getattr(_local, "nlp", None)
    if nlp is None:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        _local.nlp = nlp
    return nlp


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def extract_signals(text, max_chars=_MAX_CHARS):
    """Return {noun_phrases, entities, svo} for the document.

    Caps input at max_chars so a very long paper stays within spaCy's memory
    budget; the cap sits well above a typical article's length."""
    doc = _load_nlp()(text[:max_chars])
    return {
        "noun_phrases": _noun_phrases(doc),
        "entities": _entities(doc),
        "svo": _svo_triplets(doc),
    }


def _noun_phrases(doc, top_n=_TOP_NOUN_PHRASES):
    counts = Counter()
    for chunk in doc.noun_chunks:
        key = _norm(" ".join(t.lemma_ for t in chunk if not t.is_stop and t.is_alpha))
        if len(key) > 3 and len(key.split()) <= 5:
            counts[key] += 1
    return [phrase for phrase, n in counts.most_common(top_n) if n > 1]


def _entities(doc, top_n=_TOP_ENTITIES):
    counts = Counter()
    for ent in doc.ents:
        if ent.label_ in _ENTITY_LABELS:
            counts[ent.text.strip()] += 1
    return [text for text, _ in counts.most_common(top_n)]


def _first_child_with_dep(token, deps):
    """The token's first child holding one of `deps`, or None when it has none."""
    for child in token.children:
        if child.dep_ in deps:
            return child
    return None


def _object_of(verb):
    """The verb's direct object, or its prepositional object when it has no direct one."""
    direct = _first_child_with_dep(verb, ("dobj", "obj", "attr"))
    if direct is not None:
        return direct
    prep = _first_child_with_dep(verb, ("prep",))
    if prep is None:
        return None
    return _first_child_with_dep(prep, ("pobj",))


def _svo_triplets(doc, top_n=_TOP_SVO_TRIPLETS):
    """Subject-verb-object triplets via dependency arcs.

    For each content verb, pair its nominal subject with its direct object (or,
    failing that, a prepositional object) and keep the most frequent triplets:
    the recurring assertions the paper builds its case on."""
    counts = Counter()
    for sent in doc.sents:
        for token in sent:
            if token.pos_ != "VERB" or token.lemma_ in _STOP_VERBS:
                continue
            subj = _first_child_with_dep(token, ("nsubj", "nsubjpass"))
            obj = _object_of(token)
            if subj is not None and obj is not None:
                triplet = (_phrase(subj), token.lemma_, _phrase(obj))
                counts[triplet] += 1
    return [list(t) for t, _ in counts.most_common(top_n)]


def _phrase(token):
    """The token's subtree as a short noun phrase, lemmatised at the head."""
    span = [t for t in token.subtree if t.is_alpha and not t.is_stop]
    if not span:
        return token.lemma_
    return _norm(" ".join(t.text for t in span[:6]))
