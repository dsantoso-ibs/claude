"""Scrub personal names (and phone numbers / emails) from free-text description fields. Business entity names and project wording stay.

Layers, in order:
  1. contact data: emails and phone numbers -> [CONTACT]
  2. rules: titles (Mr/Mrs/Ms/Dr + name), explicit contact lines ("Contact: John Smith", "Attn: ...", "c/o ...", "Owner: ..."), and
     "<Surname> Residence" -> "[NAME] Residence"
  3. NER (spaCy en_core_web_sm) PERSON spans. Mostly-UPPERCASE text is title-cased for the model (same length, so offsets map back).
     A PERSON span is KEPT (not removed) when it looks like a business or place: it contains a digit or an entity keyword (LLC, Holdings,
     Construction ...), is followed by a street suffix or a place/business noun (Parkway, Apartments, Church ...), follows a house number,
     or is made of words that appear in a known business name (the `protected` set, built from the organization names in the data).
     Single-token PERSON spans are only removed when a rule layer (title/contact cue/residence) or a first+last pair supports them.

scrub(text) -> (clean_text, removed)   removed = number of replacements ([NAME] / [CONTACT]) made.
This is best-effort heuristics, not a guarantee: see tests/test_scrub_text.py for the covered patterns and the README for limits.
"""
from __future__ import annotations
import re
from functools import lru_cache
from typing import Iterable

NAME_TOKEN = "[NAME]"
CONTACT_TOKEN = "[CONTACT]"

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<!\d)(?:(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}|[2-9]\d{2}[2-9]\d{6})(?!\d)")
TITLE = re.compile(r"\b(?:(?:Mr|Mrs|Miss|Mx|MR|MRS)\.?|(?:Ms|Dr|MS|DR)\.)\s+([A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){0,2})")
STOP = {"at", "the", "to", "for", "of", "in", "on", "with", "from", "by", "per", "is", "will", "wants", "requests", "requested", "has", "have", "who", "that",
        "new", "existing", "add", "remodel", "install", "replace", "interior", "exterior", "tenant", "office", "suite", "unit", "building", "floor", "request"}
# "Contact: John Smith", "ATTN John Smith", "c/o J. Smith", "Owner: ...", "Homeowner - ..."; stops at digits, punctuation or a lowercase word
CUE = re.compile(r"\b(?:attn|attention|contact(?: person| name)?|c/o|care of|owner(?: rep(?:resentative)?)?|homeowner|home owner|name|applicant(?: name)?|representative|"
                 r"submitted by|requested by|signed by|prepared by)\s*[:\-]\s*"
                 r"((?:[A-Z][A-Za-z'’.-]*|[A-Z]\.)(?:\s+(?:[A-Z][A-Za-z'’.-]*|[A-Z]\.|&|and)){0,3})", re.I)
RESIDENCE = re.compile(r"\b([A-Z][a-z'’-]+(?:\s+(?:&|and)\s+[A-Z][a-z'’-]+)?)\s+((?i:residence|family residence|res\.|family home|family))\b")
VERB_CUE = re.compile(r"\b(contact|call|ask for|speak with|spoke with|meeting with|meet with|conversation with|coordinate with|coordination with|per|by|with)\s+"
                      r"((?:[A-Z][A-Za-z'’-]+|[A-Z]\.)(?:\s+(?:[A-Z][A-Za-z'’-]+|[A-Z]\.)){0,2})")
INITIAL_SURNAME = re.compile(r"\b([A-Z]\.\s+[A-Z][A-Za-z'’-]{2,})")

STREET = {"ST", "STREET", "AVE", "AVENUE", "BLVD", "BOULEVARD", "RD", "ROAD", "DR", "DRIVE", "LN", "LANE", "CT", "COURT", "PL", "PLACE", "PKWY", "PARKWAY",
          "HWY", "HIGHWAY", "WAY", "TRL", "TRAIL", "CIR", "CIRCLE", "LOOP", "PASS", "EXPY", "FWY", "SVRD", "BEND", "COVE", "CV", "RUN", "XING", "CROSSING"}
PLACE_NEXT = STREET | {"PARK", "CENTER", "CENTRE", "BUILDING", "BLDG", "TOWER", "TOWERS", "APARTMENTS", "APTS", "APARTMENT", "HOTEL", "INN", "CHURCH", "SCHOOL",
                       "ELEMENTARY", "MIDDLE", "HIGH", "ACADEMY", "HOSPITAL", "CLINIC", "DENTAL", "BANK", "STORE", "MARKET", "GRILL", "CAFE", "RESTAURANT",
                       "BAR", "PIZZA", "SALON", "STUDIO", "GYM", "FITNESS", "SQUARE", "VILLAGE", "STATION", "PLAZA", "OFFICE", "OFFICES", "LOFTS", "FLATS",
                       "SHOPPES", "SHOPPING", "MALL", "CAMPUS", "LAKE", "CREEK", "RIVER", "FIELD", "FIELDS", "RANCH", "RESORT", "GARDENS", "HEIGHTS", "HILLS",
                       "ESTATES", "COMMONS", "TERRACE", "TRACE", "RIDGE", "POINT", "LANDING", "PRESERVE", "TRAILS", "SPRINGS", "WOODS", "VISTA", "BRANCH"}
BUSINESS_NEXT = {"FOUNDATION", "REPAIR", "REPAIRS", "SERVICES", "SERVICE", "PLUMBING", "ELECTRIC", "ELECTRICAL", "ROOFING", "CONSTRUCTION", "MECHANICAL", "CONTRACTORS",
                 "CONTRACTING", "ENGINEERING", "FENCE", "FENCING", "HVAC", "DESIGN", "ARCHITECTS", "ARCHITECTURE", "BUILDERS", "HOMES", "PAINTING", "LANDSCAPING", "SOLAR",
                 "ENERGY", "WATER", "UTILITY", "DISTRICT", "FIBER", "CEMENT", "SIDING", "PLANK", "SHINGLES", "TILE", "FLOORING", "COMPANY", "ASSOCIATES", "SUPPLY", "INDUSTRIES",
                 "LUMBER", "STEEL", "CONCRETE", "WINDOWS", "DOORS", "CABINETS", "COUNTERTOPS", "POOLS", "TRUST", "CONGREGATION", "MINISTRIES", "PUA", "ISD"}
GENERIC_BEFORE_RESIDENCE = {"single", "family", "existing", "new", "commercial", "residential", "multi", "two", "duplex", "guest", "main", "primary", "accessory",
                            "style", "the", "a", "an", "of", "for", "to", "assisted", "living", "senior", "student", "independent", "luxury", "model", "show",
                            "caretaker", "custodian", "principal", "rental", "private", "detached", "attached", "historic", "old", "former", "proposed"}


BRANDS = {"james hardie", "hardie", "tamko", "tamko titan", "owens corning", "sherwin williams", "johnson controls", "carrier", "trane", "otis",
          "home depot", "best buy", "dish wireless", "t mobile", "american tower", "crown castle", "ericsson", "nokia", "samsung", "verizon"}
BASE_COMMON = {"roof", "roofing", "replacement", "transfer", "switch", "fire", "damage", "shade", "structure", "dumpster", "enclosure", "pool", "deck", "retail",
               "space", "remodel", "kitchen", "interior", "exterior", "tenant", "finish", "demo", "scope", "mep", "antenna", "antennas", "install", "upgrade",
               "floor", "wall", "walls", "ceiling", "door", "window", "windows", "building", "suite", "unit", "storage", "office", "parking", "garage", "sign",
               "signage", "sprinkler", "alarm", "riser", "trap", "grease", "bike", "gallery", "lecture", "residential", "commercial", "demising", "compliant",
               "breakers", "breaker", "occupant", "load", "areas", "finishes", "guestrooms", "maintenance", "provided", "review", "complete", "select", "sheet", "rock",
               "recover", "shingle", "simple", "covered", "existing", "new", "addition", "construction", "improvement", "improvements",
               # local place names that are also given names or surnames
               "austin", "texas", "travis", "williamson", "hays", "round", "rock", "cedar", "pflugerville", "manor", "lakeway", "leander", "georgetown",
               "kyle", "buda", "dallas", "houston", "san", "antonio", "bastrop", "elgin", "cave", "dripping", "springs"}


@lru_cache(maxsize=1)
def _gazetteer() -> tuple[frozenset[str], frozenset[str]]:
    from faker.providers.person.en_US import Provider as P
    first = {n.casefold() for n in list(P.first_names_female) + list(P.first_names_male) + list(getattr(P, "first_names_nonbinary", []))}
    return frozenset(first), frozenset(n.casefold() for n in P.last_names)


def fit_common_words(texts: Iterable[str], min_count: int = 3) -> set[str]:
    """Words that appear in lowercase at least `min_count` times in the corpus: people's names are not written lowercase, so these are project words."""
    from collections import Counter
    c: Counter[str] = Counter()
    for t in texts:
        if t and not _is_mostly_upper(t):
            c.update(re.findall(r"\b[a-z][a-z'’-]{2,}\b", t))
    return {w for w, n in c.items() if n >= min_count}


@lru_cache(maxsize=1)
def _nlp():
    import spacy
    return spacy.load("en_core_web_sm", disable=["tagger", "parser", "attribute_ruler", "lemmatizer"])


def _is_mostly_upper(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) > 0.6 * len(letters)


class Scrubber:
    def __init__(self, protected_orgs: Iterable[str] = (), debug: bool = False, *, common_words: Iterable[str] = (), require_gazetteer: bool = True, streets: Iterable[str] = ()):
        self.removed_log: list[str] | None = [] if debug else None      # review aid only: never write this to disk or reports
        self.common = {w.casefold() for w in common_words} | BASE_COMMON      # words people's names never are (they appear lowercase in the corpus)
        self.require_gazetteer = require_gazetteer
        self.first, self.last = _gazetteer()
        self.single_orgs = {o.casefold() for o in protected_orgs if o and len(o.split()) == 1}
        self.streets = {s.casefold() for s in streets if s}      # e.g. "Kimley-Horn": never a person
        # word bigrams and single words (>=5 letters) that occur in known business names; a PERSON span made of these is a business, not a person
        protected_orgs = list(protected_orgs)
        self.bigrams: set[tuple[str, str]] = set()
        for org in protected_orgs:
            toks = re.findall(r"[a-z0-9&'’-]+", (org or "").casefold())
            self.bigrams.update(zip(toks, toks[1:]))

    # ---------------------------------------------------------------- layers
    def _spans_rules(self, text: str) -> list[tuple[int, int, str]]:
        out: list[tuple[int, int, str]] = []
        for m in EMAIL.finditer(text):
            out.append((m.start(), m.end(), CONTACT_TOKEN))
        for m in PHONE.finditer(text):
            out.append((m.start(), m.end(), CONTACT_TOKEN))
        for m in list(PHONE.finditer(text)) + list(EMAIL.finditer(text)):
            before = text[:m.start()].rstrip(" ,:-@")
            before = re.sub(r"(?i)\s+at$", "", before)
            toks = list(re.finditer(r"[A-Z][A-Za-z'’-]+", before[-60:]))
            tail = []
            for t in reversed(toks):                          # walk back over adjacent capitalized words
                gap = before[-60:][t.end():]
                if tail and before[-60:][t.end():tail[-1].start()].strip():
                    break
                if not tail and gap.strip():
                    break
                low = t.group(0).casefold()
                if low in STOP or low in self.common or low in self.single_orgs or low.upper() in PLACE_NEXT or low in {"contact", "call", "phone", "tel", "cell", "mobile", "ph", "attn"}:
                    break
                tail.append(t)
            if tail:
                off = len(before) - len(before[-60:])
                out.append((off + tail[-1].start(), off + tail[0].end(), NAME_TOKEN))
        for m in TITLE.finditer(text):
            end = self._person_prefix_end(m.group(1), m.start(1))
            if end and not self._followed_by_business(text, end) and not self._is_brand(text[m.start(1):end]):
                out.append((m.start(1), end, NAME_TOKEN))
        for m in CUE.finditer(text):
            end = self._person_prefix_end(m.group(1), m.start(1))
            if end and not self._followed_by_business(text, end) and not self._is_brand(text[m.start(1):end]):
                out.append((m.start(1), end, NAME_TOKEN))
        for m in VERB_CUE.finditer(text):                         # "Contact Elena for keys", "per Gary Pennington": the name must pass the same guards
            end = self._person_prefix_end(m.group(2), m.start(2))
            if end and not self._followed_by_business(text, end) and not self._is_brand(text[m.start(2):end]) and not self._street_like(text[m.start(2):end]):
                words = [w.casefold().strip(".,;:()") for w in text[m.start(2):end].split()]
                strong = m.group(1).casefold() in {"contact", "call", "ask for", "speak with", "spoke with", "meeting with", "meet with", "conversation with", "coordinate with", "coordination with"}
                # after a weak verb (per/by/with) capitalization alone is not enough: a name-list hit, an initial, or a contact right after
                if strong or any(w in self.first or w in self.last for w in words) or re.search(r"\b[A-Z]\.", text[m.start(2):end]) \
                        or PHONE.match(text[end:].lstrip(" ,-:at")) or EMAIL.match(text[end:].lstrip(" ,-:at")):
                    out.append((m.start(2), end, NAME_TOKEN))
        for m in INITIAL_SURNAME.finditer(text):
            if m.group(1)[0] in "NSEW" and not re.search(r"(?i)\b(contact|attn|owner|applicant|per|by)\W+$", text[max(0, m.start(1) - 14):m.start(1)]):
                continue                                          # N. Lamar, E. Cesar Chavez: street directions, not initials
            low = m.group(1).split()[-1].casefold()
            if low not in self.common and low not in STOP and low.upper() not in PLACE_NEXT and low not in {w for b in self.bigrams for w in b if False}:
                nxt = re.match(r"\s*([A-Za-z]+)", text[m.end():])
                if not (nxt and nxt.group(1).upper() in (PLACE_NEXT | BUSINESS_NEXT)) and " ".join(m.group(1).split()).casefold() not in BRANDS:
                    out.append((m.start(1), m.end(1), NAME_TOKEN))
        for m in RESIDENCE.finditer(text):
            first = m.group(1).split()[0].casefold()
            if first not in GENERIC_BEFORE_RESIDENCE and first not in self.common and not any(w in PLACE_NEXT for w in m.group(1).upper().split()) \
                    and (m.group(2).casefold().startswith(("res", "family res", "family home")) or text[max(0, m.start(1) - 4):m.start(1)].casefold() == "the "):
                out.append((m.start(1), m.end(1), NAME_TOKEN))
        return out

    def _person_prefix_end(self, span: str, start: int) -> int | None:
        """End offset of the leading person-like tokens of `span`. Stops at stop words, project words (corpus lowercase evidence), places and business
        words. If it stops at a business/place word the span is a business name ("Bright Smiles Dental"), so nothing is removed."""
        end = None
        for tok in re.finditer(r"\S+", span):
            word = tok.group(0).strip(".,;:()")
            low = word.casefold()
            if word.upper() in PLACE_NEXT or re.fullmatch(r"(?i)llc|inc|corp|co|ltd|lp|llp|company|construction|builders|group|properties|dental|clinic", word):
                return None if end is not None or tok.start() == 0 else None
            if low in STOP or low in self.common or low in self.single_orgs:
                break
            end = start + tok.end()
        return end

    @staticmethod
    def _followed_by_business(text: str, end: int) -> bool:
        m = re.match(r"[\s,.:;-]*([A-Za-z]+)", text[end:])
        return bool(m) and m.group(1).upper() in (BUSINESS_NEXT | PLACE_NEXT)

    @staticmethod
    def _is_brand(span: str) -> bool:
        low = " ".join(re.findall(r"[a-z0-9&]+", span.casefold()))
        return any(low == b or low.startswith(b + " ") or low.endswith(" " + b) for b in BRANDS)

    def _protected(self, tokens: list[str]) -> bool:
        low = [re.sub(r"[^a-z0-9&'’-]", "", t.casefold()) for t in tokens]
        return len(low) >= 2 and all(pair in self.bigrams for pair in zip(low, low[1:]))

    def _street_like(self, span: str) -> bool:
        """A span that is a street name seen in the address data (e.g. a street named after a person) is a place, not a person."""
        return " ".join(re.findall(r"[a-z0-9&'’-]+", span.casefold())) in self.streets

    def _spans_ner(self, texts: list[str], rule_spans: list[list[tuple[int, int, str]]]) -> list[list[tuple[int, int, str]]]:
        views = [t.title() if _is_mostly_upper(t) else t for t in texts]
        out = []
        for text, doc, rs in zip(texts, _nlp().pipe(views, batch_size=256), rule_spans):
            spans = []
            for ent in doc.ents:
                if ent.label_ != "PERSON":
                    continue
                raw = text[ent.start_char:ent.end_char]
                words = re.findall(r"[A-Za-z][A-Za-z'’.-]*", raw)
                if any(ch.isdigit() for ch in raw) or "[" in raw:
                    continue
                if any(w.upper().strip(".") in PLACE_NEXT for w in words):
                    continue
                after = re.match(r"\s*([A-Za-z]+)", text[ent.end_char:])
                if after and after.group(1).upper() in PLACE_NEXT:
                    continue
                before = text[:ent.start_char].rstrip()
                if re.search(r"(?:\d|#)$", before) or re.search(r"(?i)\b(of|at|on|in)\s+(the\s+)?$", text[max(0, ent.start_char - 8):ent.start_char] + " ") and len(words) == 1:
                    continue
                if re.search(r"(?i)\b(llc|inc|corp|ltd|lp|llp|company|holdings|construction|builders|properties|partners|group|capital)\b", raw):
                    continue
                core = [w for w in words if w.strip(".").upper() not in {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}]      # drop street directions (E. Cesar Chavez)
                if not core or self._protected(core) or self._is_brand(" ".join(core)) or self._followed_by_business(text, ent.end_char) or self._street_like(" ".join(core)):
                    continue
                words = core
                low = [w.casefold().strip(".") for w in words]
                if " ".join(low) in BRANDS or any(w in self.common for w in low):
                    continue                                    # project wording / brand, not a person
                if len(words) < 2:                           # single token: only with support from a rule layer (title/cue/residence)
                    if not any(s <= ent.start_char and ent.end_char <= e for s, e, _ in rs):
                        continue
                elif self.require_gazetteer and not (any(w in self.first for w in low) or any(w in self.last for w in low[1:]) or re.search(r"\b[A-DF-MO-RT-VX-Z]\.", raw)):
                    continue
                spans.append((ent.start_char, ent.end_char, NAME_TOKEN))
            out.append(spans)
        return out

    # ---------------------------------------------------------------- api
    def scrub_many(self, texts: list[str | None], ner: bool = True) -> list[tuple[str | None, int]]:
        """ner=False for short title-like fields (project / case names): NER is unreliable on titles, and a person's name there almost always appears as
        '<Surname> Residence' or next to a contact cue, which the rule layers handle."""
        todo = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        res: list[tuple[str | None, int]] = [(t, 0) for t in texts]
        if not todo:
            return res
        plain = [t for _, t in todo]
        rules = [self._spans_rules(t) for t in plain]
        ner_spans = self._spans_ner(plain, rules) if ner else [[] for _ in plain]
        for (i, text), rs, ns in zip(todo, rules, ner_spans):
            spans = sorted(rs + ns, key=lambda s: (s[0], -(s[1] - s[0])))
            merged: list[tuple[int, int, str]] = []
            for s, e, tok in spans:                          # merge overlapping spans; a CONTACT span wins over NAME on overlap
                if merged and s < merged[-1][1]:
                    ps, pe, pt = merged[-1]
                    merged[-1] = (ps, max(pe, e), CONTACT_TOKEN if CONTACT_TOKEN in (pt, tok) else NAME_TOKEN)
                else:
                    merged.append((s, e, tok))
            if not merged:
                continue
            pieces, last = [], 0
            for s, e, tok in merged:
                if self.removed_log is not None:
                    self.removed_log.append(text[s:e])
                pieces.append(text[last:s]); pieces.append(tok); last = e
            pieces.append(text[last:])
            clean = re.sub(r"(\[NAME\]\s*[,&]?\s*)+(?=\[NAME\])", "", "".join(pieces))      # collapse "[NAME] [NAME]" runs
            res[i] = (clean, len(merged))
        return res

    def scrub(self, text: str | None, ner: bool = True) -> tuple[str | None, int]:
        return self.scrub_many([text], ner=ner)[0]
