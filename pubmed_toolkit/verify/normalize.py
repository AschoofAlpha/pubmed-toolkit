"""
Text normalisation for comparing bibliographic fields.

These rules were derived from verifying real bibliographies: the same article
is routinely written as "422-437.e7" vs "422-437", "Følling" vs "Folling",
"CA Cancer J Clin" vs "CA: A Cancer Journal for Clinicians". Comparing raw
strings produces a flood of false mismatches, which is what makes a verifier
useless in practice.
"""

from __future__ import annotations

import re
import unicodedata


def norm_text(s: str) -> str:
    """
    Lowercase, fold accents, strip everything else, collapse spaces.

    Accent folding is not optional here. Without it every non-ASCII character
    is deleted rather than transliterated, so `title_similarity` and
    `journal_matches` compare mutilated strings:

        'Zeitschrift für Gastroenterologie' -> 'zeitschrift f r gastroenterologie'

    which fails to match the same journal written 'Zeitschrift fur ...'. That
    turns every German, French, Spanish and Nordic title or journal into a
    false mismatch, or drops the correct CrossRef candidate entirely.
    """
    return re.sub(r"[^a-z0-9]+", " ", fold_accents(s or "").lower()).strip()


def norm_pages(s: str) -> str:
    """
    Normalise page ranges.

    '229-263' / '229–263' / 'pp. 229-263' -> '229 263'
    '422-437.e7'                          -> '422 437 e7'
    """
    if not s:
        return ""
    s = s.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def expand_page_range(s: str) -> str:
    """
    Expand an abbreviated end page to its full form.

    PubMed elides the shared leading digits of the end page, so the same
    article appears as '202-9' in PubMed and '202-209' in CrossRef:

        '202-9'    -> '202-209'
        '422-37'   -> '422-437'
        '1234-8'   -> '1234-1238'
        '229-263'  -> '229-263'   (already full, unchanged)
        '95-101'   -> '95-101'    (end longer than start, unchanged)
    """
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", (s or "").replace("–", "-").replace("—", "-"))
    if not m:
        return (s or "").strip()
    start, end = m.group(1), m.group(2)
    if len(end) < len(start):
        end = start[: len(start) - len(end)] + end
    return f"{start}-{end}"


def pages_match(a: str, b: str) -> bool:
    """
    Compare two page fields, tolerating the conventions that differ between
    sources rather than the values that differ between papers.

    Tolerated: abbreviated end pages ('202-9'), en-dashes, 'pp.' prefixes,
    and article-number suffixes ('422-437.e7' vs '422-437').
    Not tolerated: genuinely different page numbers.
    """
    if not a or not b:
        return True
    na, nb = norm_pages(expand_page_range(a)), norm_pages(expand_page_range(b))
    if na == nb:
        return True
    # '422 437 e7' vs '422 437' — one carries an article-number suffix.
    return na.startswith(nb + " ") or nb.startswith(na + " ")


def fold_accents(s: str) -> str:
    """
    Strip diacritics via Unicode decomposition, then handle the letters that
    NFKD does not decompose (ø, ł, ß, æ, œ, đ, ħ, ŋ, ð, þ).
    """
    special = {
        "ø": "o", "Ø": "o", "ł": "l", "Ł": "l", "ß": "ss",
        "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe",
        "đ": "d", "Đ": "d", "ħ": "h", "ŋ": "n",
        "ð": "d", "Ð": "d", "þ": "th", "Þ": "th",
    }
    s = "".join(special.get(c, c) for c in (s or ""))
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def norm_author(s: str) -> str:
    """
    Reduce a surname to comparable form: accent-folded, letters only.

    'Følling' -> 'folling', 'Häussinger' -> 'haussinger', "O'Brien" -> 'obrien'

    Keeps every Unicode letter, not just ASCII. An earlier version filtered with
    `[^a-z]+`, which silently reduced any non-Latin name to the empty string —
    '李四' became '', and compare_fields then skipped the author check entirely
    because the supplied value looked absent. A tool whose stated purpose is
    disambiguating Chinese names must not go blind on Chinese characters.
    """
    return "".join(c for c in fold_accents(s or "").lower() if c.isalpha())


# Romanised East Asian and South Asian surnames short enough to be mistaken for
# a run of initials. Only one-to-three-letter tokens are ambiguous at all: no
# author carries four initials, so 'Maria GARCIA' and 'Jing ZHANG' already read
# correctly on length alone.
#
# The list is deliberately generous at three letters and stingy at two. Three
# initials in a row are rare while two are the norm, so a two-letter entry
# ('MA') collides with real initials far more often than a three-letter one
# ('MAO') and has to earn its place by being a genuinely frequent surname.
CAPITALISED_SURNAMES = frozenset({
    # Chinese — pinyin
    "wu", "li", "he", "ma", "xu", "lu", "hu", "gu", "du", "yu", "su", "ye",
    "fu", "ji", "qi", "shi", "sun", "gao", "guo", "xie", "lin", "luo", "han",
    "tan", "pan", "dai", "yao", "fan", "cao", "jia", "wei", "lei", "mao",
    "bai", "jin", "qiu", "zhu", "xia", "yan", "yin", "cui", "hou", "hua",
    "ren", "wan",
    # Chinese — Wade-Giles, Cantonese and Hokkien romanisations
    "ng", "ho", "ko", "lo", "au", "hsu", "chu", "kuo", "lam", "lau", "yip",
    "mak", "tam", "lai", "yau", "siu",
    # Korean
    "oh", "kim", "lee", "cho", "seo", "son", "lim", "yoo", "ahn", "bae",
    "noh", "koo", "min", "suh", "roh", "nam", "yun", "joo", "hur",
    # Japanese
    "ito", "abe", "ono", "ota", "oka", "doi", "ide",
    # Vietnamese
    "le", "do", "vu", "ly", "ha", "bui", "ngo", "dao", "mai",
    # South Asian
    "rao", "roy", "sen", "das", "jha", "dey", "pal",
})

# A token that opens with a consonant and reaches a vowel is at least
# pronounceable as one syllable, so it *could* be a romanised surname: 'MU',
# 'ZHU', 'GAO'. 'AJ', 'FJ' and 'MB' could not.
_SYLLABLE = re.compile(r"^[bcdfghjklmnpqrstvwxyz][a-z]*[aeiouy]")


def _looks_like_initials(token: str, normalised: str) -> bool:
    """
    True when a token reads as bare initials rather than a surname.

    Only all-caps tokens of up to three letters are in doubt at all, and for
    those the shape decides nothing: 'Bass AJ' and 'Jing WU' are identical in
    case and length. The discriminator has to be lexical, so an unrecognised
    short all-caps token is taken to be initials — 'Surname INITIALS' is the
    format this toolkit ingests by the thousand.
    """
    return token.isupper() and len(normalised) <= 3 and normalised not in CAPITALISED_SURNAMES


def surname_of(s: str) -> str:
    """
    Extract a comparable surname from assorted author formats.

    'Bray F'        -> 'bray'      (PubMed: surname first, F is an initial)
    'Bass AJ'       -> 'bass'      (PubMed: AJ is two initials, not a surname)
    'Bray, Freddie' -> 'bray'      (the comma states the order)
    'Freddie Bray'  -> 'bray'      (Western order)
    'Jing WU'       -> 'wu'        (given name first, surname capitalised)
    'Yi LI'         -> 'li'
    "O'Brien M"     -> 'obrien'

    This is a single best guess. Field comparison must not depend on it — use
    `surname_candidates` / `surnames_agree`, which keep every reading.
    """
    s = (s or "").strip()
    if not s:
        return ""
    if "," in s:
        return norm_author(s.split(",")[0])
    parts = s.split()
    if len(parts) == 1:
        return norm_author(parts[0])

    last = norm_author(parts[-1])
    # Deciding one reading needs the strict test: the lookup only, no
    # pronounceability escape. Phonotactics is the tempting rule ('WU' and 'LI'
    # are consonant+vowel syllables, 'AJ' is not) and committing to it is wrong
    # for roughly one PubMed byline in eight, because ordinary initial pairs —
    # 'JA' (John A.), 'MA', 'DE', 'RO' — have exactly that shape too. The lookup
    # errs only on the far smaller set of initial pairs that spell a real
    # surname; 'Smith MA' still reads as Ma, and that residue is undecidable
    # from the string alone.
    if _looks_like_initials(parts[-1], last):
        return norm_author(parts[0])
    return last


def surname_candidates(s: str) -> set[str]:
    """
    Every plausible surname reading of an author string.

    Author order is genuinely ambiguous and cannot be resolved syntactically.
    'Jing WU' is structurally identical to 'Bray FJ': a capitalised word
    followed by a short all-caps token. In the first it is a surname, in the
    second a pair of initials. `surname_of` has to commit to one reading and so
    gets one of them wrong; comparison should not.

    So return all readings and let the caller accept a match on any. Missing a
    real error costs far less than flagging a correct citation — a verifier
    that cries wolf gets switched off, and then it catches nothing at all.

    What is *not* a reading is a run of initials, and that exception is not
    optional: with 'aj' in the set, 'Bray AJ' and 'Bass AJ' shared a candidate
    and were accepted as the same person, so the wrong-author check — the whole
    point of comparing authors — passed on two different people.

        'Bray F'        -> {'bray'}                  (F is too short to be a name)
        'Bray, Freddie' -> {'bray'}                  (the comma is unambiguous)
        'Bass AJ'       -> {'bass', 'bassaj'}        (AJ cannot be a syllable)
        'Jing WU'       -> {'jing', 'wu', 'jingwu'}
        'Van Der Berg'  -> {'van', 'berg', 'vanderberg'}
    """
    s = (s or "").strip()
    if not s:
        return set()

    # A comma states the order explicitly; there is nothing to guess.
    if "," in s:
        head = norm_author(s.split(",")[0])
        return {head} if head else set()

    parts = s.split()
    if len(parts) == 1:
        single = norm_author(parts[0])
        return {single} if single else set()

    # First and last token, plus the whole string joined — the last of these is
    # what makes compound surnames ('Van Der Berg') comparable against a
    # canonical record that stores them as one field.
    first, last = norm_author(parts[0]), norm_author(parts[-1])
    candidates = {first, last, norm_author(s)}

    # Drop the tokens that are bare initials. Here the test is deliberately
    # looser than in `surname_of`: a token that is merely *pronounceable* keeps
    # its place, so 'MU' and 'ZHU' stay candidates even though they are not in
    # the lookup table. The two functions want opposite biases. Committing to a
    # reading, over-accepting picks the wrong token outright; collecting
    # readings, over-accepting only costs a missed check, while over-rejecting
    # would flag a correct citation. Between those two, keep the extra reading.
    #
    # `surname_of`'s choice is never dropped: the two must not disagree about
    # which token is the surname, or 'MU J' would lose the only reading it has.
    chosen = surname_of(s)
    for token, normalised in ((parts[0], first), (parts[-1], last)):
        if (
            normalised != chosen
            and _looks_like_initials(token, normalised)
            and not _SYLLABLE.match(normalised)
        ):
            candidates.discard(normalised)

    # A one-letter *Latin* token is an initial, never a surname. Length alone
    # must not decide it: '李' is a complete surname, and discarding it made a
    # spaced CJK name ('李 四') share no reading with the same name written
    # solid, i.e. a false mismatch. A stray one-character non-Latin token can
    # only ever cause an over-match, which is the safe direction to err in.
    return {c for c in candidates if len(c) >= 2 or not c.isascii()}


def surnames_agree(supplied: str, canonical: str) -> bool:
    """
    True when the two author strings share any plausible surname reading.

    Callers must not read the "nothing comparable" case as agreement: check
    `surname_candidates` on both sides first and report the skip, otherwise a
    check that never ran is indistinguishable from one that passed.
    """
    a, b = surname_candidates(supplied), surname_candidates(canonical)
    if not a or not b:
        return True          # nothing comparable on one side
    return bool(a & b)


def journal_matches(supplied: str, canonical: str) -> bool:
    """
    Journals are abbreviated inconsistently, so accept a match when either
    normalised name contains the other.

    'CA Cancer J Clin' vs 'CA: A Cancer Journal for Clinicians' -> no substring
    relation, so this still reports a mismatch. That is intentional: the caller
    downgrades journal disagreements to a warning rather than a hard failure.
    """
    a, b = norm_text(supplied), norm_text(canonical)
    if not a or not b:
        return True          # nothing to compare against
    return a == b or a in b or b in a


def title_similarity(a: str, b: str) -> float:
    """Token-overlap ratio (Jaccard) between two titles, in [0.0, 1.0]."""
    ta = set(norm_text(a).split())
    tb = set(norm_text(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
