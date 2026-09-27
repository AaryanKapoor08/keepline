"""Chaos ladder: deterministic, seeded corruption of the rendered Harbourline corpus.

    python -m keepline.data.noise [--seed 7] [--levels 0,1,2,3,4]

Writes ``data/corpus_noise/L{n}/{slack,email,tickets,docs,interviews}.jsonl`` (same ``SourceDoc`` format) plus
``id_map.json`` ({original doc id: [ids that now carry its content]}; ``[]`` = dropped) and ``noise_config.json``.
Original ids are kept wherever a doc survives, so ``remap_evidence`` turns the clean evidence map into a valid one
for any level. L0 is byte-identical to the clean corpus.

Every noise type is independently toggleable (``NoiseConfig``) and dose-scaled by level:

| noise type            | what it models                                                    | L0 | L1   | L2   | L3   | L4   |
|-----------------------|-------------------------------------------------------------------|----|------|------|------|------|
| typos                 | keyboard slips (swap/drop/double/adjacent key), per word           | 0  | 1%   | 3%   | 6%   | 10%  |
| lowercase             | whole message lowercased, per msg                                  | 0  | 20%  | 40%  | 60%  | 80%  |
| punctuation drop      | punctuation stripped, per msg                                      | 0  | 10%  | 30%  | 50%  | 70%  |
| slang/abbreviation    | "recon", "tmrw", "pls", "fri", "w/", per msg                       | 0  | 20%  | 40%  | 60%  | 80%  |
| emoji / +1 / lol      | reaction-style tails and "+1"/"lol" replies, per msg               | 0  | 5%   | 10%  | 20%  | 30%  |
| fragmentation         | a fact message split into 2-3 consecutive msgs by the same author  | 0  | 10%  | 25%  | 40%  | 60%  |
| bot/alert spam        | Jenkins, PagerDuty, Dependabot posts per business day              | 0  | 2    | 5    | 10   | 20   |
| forwarded duplicates  | "Fwd:" copies of emails with ">" quoted history, per email         | 0  | 5%   | 10%  | 20%  | 30%  |
| wrong/stale claims    | non-knowers repeat superseded values / wrong versions, per fact    | 0  | 1    | 2    | 3    | 4    |
| timestamp jitter      | out-of-order delivery: max shift in minutes (35% of msgs)          | 0  | 5    | 30   | 120  | 720  |
| evidence dropout      | fraction of each fact's evidence docs removed (never all)          | 0  | 0    | 10%  | 25%  | 40%  |
| off-topic chatter     | volume multiplier on non-evidence chatter                          | x1 | x1.25| x1.5 | x2   | x3   |
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path

from keepline.config import CORPUS_DIR, DATA
from keepline.contracts import SourceDoc, SourceType, Visibility, to_json, write_jsonl
from keepline.data.company import AREA_ASKERS, AREA_CHANNELS, CHANNELS, FIRST
from keepline.data.render import DAYS
from keepline.data.truth import load_specs, truth_ids
from keepline.io import load_corpus

NOISE_DIR = DATA / "corpus_noise"
LEVELS = (0, 1, 2, 3, 4)
FILES = {SourceType.SLACK: "slack", SourceType.EMAIL: "email", SourceType.TICKET: "tickets",
         SourceType.DOC: "docs", SourceType.INTERVIEW: "interviews"}


@dataclass(frozen=True)
class NoiseConfig:
    typo: float = 0.0
    lowercase: float = 0.0
    punct_drop: float = 0.0
    slang: float = 0.0
    emoji: float = 0.0
    fragment: float = 0.0
    bot_per_day: int = 0
    forward_dup: float = 0.0
    wrong_claims: int = 0
    jitter_min: int = 0
    dropout: float = 0.0
    chatter_mult: float = 1.0


LEVEL_CONFIGS: dict[int, NoiseConfig] = {
    0: NoiseConfig(),
    1: NoiseConfig(0.01, 0.2, 0.1, 0.2, 0.05, 0.10, 2, 0.05, 1, 5, 0.0, 1.25),
    2: NoiseConfig(0.03, 0.4, 0.3, 0.4, 0.10, 0.25, 5, 0.10, 2, 30, 0.10, 1.5),
    3: NoiseConfig(0.06, 0.6, 0.5, 0.6, 0.20, 0.40, 10, 0.20, 3, 120, 0.25, 2.0),
    4: NoiseConfig(0.10, 0.8, 0.7, 0.8, 0.30, 0.60, 20, 0.30, 4, 720, 0.40, 3.0),
}

SLANG = [(r"\breconciliation\b", "recon"), (r"\btomorrow\b", "tmrw"), (r"\bplease\b", "pls"),
         (r"\bFriday\b", "fri"), (r"\bthanks\b", "thx"), (r"\bbecause\b", "bc"), (r"\bbefore\b", "b4"),
         (r"\byou\b", "u"), (r"\bwith\b", "w/"), (r"\babout\b", "abt"), (r"\bpeople\b", "ppl"),
         (r"\bdon't\b", "dont"), (r"\bI'm\b", "im"), (r"\bminutes\b", "mins"), (r"\bSeptember\b", "sept"),
         (r"\bprobably\b", "prob"), (r"\bsomething\b", "smth"), (r"\bthrough\b", "thru")]
EMOJI_TAILS = [" 👍", " 🙏", " lol", " 😅", " 🔥", " :+1:", " 🤞", " haha", " ✅"]
REPLY_NOISE = ["+1", "lol", "same", "👀", "^ this", "+1 following", "🙃", "bump"]
KEYS_NEAR = {c: n for c, n in zip("qwertyuiopasdfghjklzxcvbnm", "wqrtyuiopoasdfghjklkzxcvbnm")}
HEDGES = ["pretty sure {x}?", "iirc {x}", "last I heard: {x}", "someone told me {x} — is that still right?",
          "I think {x}", "fwiw what I was told was: {x}"]
BOTS = [
    ("#eng-core", "sarah", "jenkins", "Jenkins: build #{n} of recon-nightly {status} ({m} min)"),
    ("#eng-core", "aisha", "dependabot", "Dependabot opened PR #{n}: bump requests from 2.{m}.0 to 2.{m2}.1"),
    ("#ops", "nadia", "pagerduty", "PagerDuty: [{sev}] disk usage {m}% on hcu-fs0{k} — {state}"),
    ("#incidents", "nadia", "pagerduty", "PagerDuty: [{sev}] portal p95 latency {m}00ms — {state}"),
    ("#ops", "mike", "veeam", "Veeam: job NIGHTLY-FS0{k} finished with {status}"),
    ("#eng-core", "sarah", "jenkins", "Jenkins: deploy #{n} of member-portal to staging {status}"),
]


# --------------------------------------------------------------------------------------------------
# text corruption
# --------------------------------------------------------------------------------------------------


def _typo(word: str, rng: random.Random) -> str:
    if len(word) < 3 or not word.isalpha():
        return word
    i = rng.randrange(len(word) - 1)
    op = rng.randrange(4)
    if op == 0:
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if op == 1:
        return word[:i] + word[i + 1:]
    if op == 2:
        return word[:i] + word[i] + word[i:]
    c = word[i].lower()
    return word[:i] + KEYS_NEAR.get(c, c) + word[i + 1:]


def corrupt_text(text: str, cfg: NoiseConfig, rng: random.Random) -> str:
    out = text
    if cfg.slang and rng.random() < cfg.slang:
        for pat, rep in SLANG:
            out = re.sub(pat, rep, out, flags=re.I)
    if cfg.typo:
        out = re.sub(r"[A-Za-z]+", lambda m: _typo(m.group(0), rng) if rng.random() < cfg.typo else m.group(0), out)
    if cfg.punct_drop and rng.random() < cfg.punct_drop:
        out = re.sub(r"[.,;!?—'\"()]", "", out)
    if cfg.lowercase and rng.random() < cfg.lowercase:
        out = out.lower()
    if cfg.emoji and rng.random() < cfg.emoji:
        out += rng.choice(EMOJI_TAILS)
    return out


def _split_text(text: str, rng: random.Random) -> list[str]:
    parts = [p for p in re.split(r"(?<=[.;:!?—,])\s+", text) if p.strip()]
    if len(parts) < 2:
        words = text.split()
        if len(words) < 6:
            return [text]
        cut = rng.randint(2, len(words) - 2)
        return [" ".join(words[:cut]), " ".join(words[cut:])]
    n = min(len(parts), rng.choice([2, 2, 3]))
    cuts = sorted(rng.sample(range(1, len(parts)), n - 1))
    bounds = [0, *cuts, len(parts)]
    return [" ".join(parts[a:b]) for a, b in zip(bounds, bounds[1:])]


# --------------------------------------------------------------------------------------------------
# the ladder
# --------------------------------------------------------------------------------------------------


@dataclass
class Level:
    level: int
    config: NoiseConfig
    docs: list[SourceDoc]
    id_map: dict[str, list[str]]
    examples: list[dict[str, str]] = field(default_factory=list)


def _clean_evidence() -> dict[str, list[str]]:
    from keepline.config import TRUTH_DIR

    return json.loads((TRUTH_DIR / "evidence_map.json").read_text(encoding="utf-8"))


def remap_evidence(ev: dict[str, list[str]], id_map: dict[str, list[str]]) -> dict[str, list[str]]:
    return {t: sorted({n for d in ids for n in id_map.get(d, [d])}) for t, ids in ev.items()}


def corrupt(docs: list[SourceDoc], ev: dict[str, list[str]], level: int, seed: int = 7,
            config: NoiseConfig | None = None) -> Level:
    cfg = config or LEVEL_CONFIGS[level]
    rng = random.Random(seed * 1000 + level)
    docs = [dataclasses.replace(d, meta=dict(d.meta), participants=list(d.participants)) for d in docs]
    id_map: dict[str, list[str]] = {d.id: [d.id] for d in docs}
    ev_docs = {d for ids in ev.values() for d in ids}
    if cfg == NoiseConfig():
        return Level(level, cfg, docs, id_map)
    originals = {d.id: d.text for d in docs}

    # 1. evidence dropout (never a fact's last doc)
    if cfg.dropout:
        remaining = {t: list(ids) for t, ids in ev.items()}
        facts_of: dict[str, list[str]] = {}
        for t, ids in ev.items():
            for d in ids:
                facts_of.setdefault(d, []).append(t)
        drop: set[str] = set()
        for d in sorted(ev_docs):
            if rng.random() < cfg.dropout and all(len(remaining[t]) > 1 for t in facts_of[d]):
                drop.add(d)
                for t in facts_of[d]:
                    remaining[t].remove(d)
        docs = [d for d in docs if d.id not in drop]
        for d in drop:
            id_map[d] = []

    # 2. fragmentation of fact-bearing Slack messages
    out: list[SourceDoc] = []
    for d in docs:
        if d.source_type is SourceType.SLACK and d.id in ev_docs and rng.random() < cfg.fragment:
            parts = _split_text(d.text, rng)
            if len(parts) > 1:
                ids = [d.id] + [f"{d.id}.p{i}" for i in range(2, len(parts) + 1)]
                for i, (pid, txt) in enumerate(zip(ids, parts)):
                    out.append(dataclasses.replace(d, id=pid, text=txt, url=d.url + (f"&part={i + 1}" if i else ""),
                                                   timestamp=d.timestamp + timedelta(seconds=20 * i),
                                                   thread_id=d.thread_id or d.id))
                id_map[d.id] = ids
                continue
        out.append(d)
    docs = out

    # 3. forwarded-email duplicates with quoted history
    extra: list[SourceDoc] = []
    for d in docs:
        if d.source_type is SourceType.EMAIL and rng.random() < cfg.forward_dup:
            fwd_by = rng.choice([p for p in d.participants if p != d.author_id] or [d.author_id])
            quoted = "\n".join("> " + ln for ln in d.text.splitlines())
            text = (f"{rng.choice(['FYI', 'fyi see below', 'Forwarding in case useful', 'fwd'])}\n\n"
                    f"---------- Forwarded message ---------\nFrom: {FIRST[d.author_id]}\n{quoted}")
            nid = f"{d.id}.fwd"
            extra.append(dataclasses.replace(d, id=nid, author_id=fwd_by, text=text,
                                             title=f"Fwd: {d.title or ''}".strip(),
                                             timestamp=d.timestamp + timedelta(hours=rng.randint(2, 96)),
                                             url=d.url + "?fwd=1", meta={**d.meta, "forwarded_from": d.id}))
            for orig, ids in id_map.items():
                if d.id in ids:
                    ids.append(nid)
    docs += extra

    # 4. text corruption + reply noise (Slack/email only; tickets and wiki pages are edited more carefully)
    for i, d in enumerate(docs):
        if d.source_type in (SourceType.SLACK, SourceType.EMAIL):
            docs[i] = dataclasses.replace(d, text=corrupt_text(d.text, cfg, rng))
    reply_n = 0
    for d in list(docs):
        if d.source_type is SourceType.SLACK and d.visibility is not Visibility.PRIVATE and rng.random() < cfg.emoji:
            reply_n += 1
            who = rng.choice([p for p in d.participants if p != d.author_id] or [d.author_id])
            docs.append(dataclasses.replace(d, id=f"noise-reply-{reply_n:05d}", author_id=who,
                                            text=rng.choice(REPLY_NOISE), thread_id=d.thread_id or d.id,
                                            timestamp=d.timestamp + timedelta(minutes=rng.randint(1, 30)),
                                            url=d.url + f"&r={reply_n}"))

    # 5. wrong / stale claims from non-knowers
    docs += _wrong_claims(cfg, rng)

    # 6. bot spam
    bot_n = 0
    for day in DAYS:
        for _ in range(cfg.bot_per_day):
            bot_n += 1
            ch, owner, bot, tmpl = rng.choice(BOTS)
            text = tmpl.format(n=rng.randint(100, 9999), m=rng.randint(2, 98), m2=rng.randint(2, 98),
                               k=rng.randint(1, 4), status=rng.choice(["SUCCESS", "SUCCESS", "FAILURE", "UNSTABLE"]),
                               sev=rng.choice(["P2", "P3", "P4"]), state=rng.choice(["triggered", "resolved"]))
            c = CHANNELS[ch]
            ts = datetime.combine(day, time(0)) + timedelta(minutes=rng.randint(0, 24 * 60 - 1))
            docs.append(SourceDoc(id=f"bot-{bot_n:06d}", source_type=SourceType.SLACK, author_id=owner, timestamp=ts,
                                  text=text, container=ch, participants=[owner], visibility=c.visibility,
                                  url=f"https://harbourline.slack.com/archives/{c.cid}/pbot{bot_n:06d}",
                                  meta={"bot": bot}))

    # 7. more off-topic chatter
    chatter = [d for d in docs if d.source_type is SourceType.SLACK and d.id in originals and d.id not in ev_docs
               and not d.thread_id and d.visibility is Visibility.PUBLIC]
    n_more = int(len(chatter) * (cfg.chatter_mult - 1.0))
    for k in range(n_more):
        src = rng.choice(chatter)
        day = rng.choice(DAYS)
        ts = datetime.combine(day, src.timestamp.time()) + timedelta(minutes=rng.randint(-90, 90))
        docs.append(dataclasses.replace(src, id=f"chatter-{k:06d}", timestamp=ts,
                                        text=corrupt_text(src.text, cfg, rng), url=src.url + f"?c={k}"))

    # 8. timestamp jitter (out-of-order delivery)
    if cfg.jitter_min:
        for i, d in enumerate(docs):
            if rng.random() < 0.35:
                docs[i] = dataclasses.replace(
                    d, timestamp=d.timestamp + timedelta(minutes=rng.randint(-cfg.jitter_min, cfg.jitter_min)))

    docs.sort(key=lambda d: (d.timestamp, d.id))
    lvl = Level(level, cfg, docs, id_map)
    lvl.examples = _examples(docs, originals, ev_docs, rng)
    return lvl


def _wrong_claims(cfg: NoiseConfig, rng: random.Random) -> list[SourceDoc]:
    """Non-knowers restating superseded values after they changed, and re-posting known wrong versions."""
    if not cfg.wrong_claims:
        return []
    specs = load_specs()
    by_key = {s.key: s for s in specs}
    out: list[SourceDoc] = []
    n = 0
    for s in specs:
        claims: list[tuple[str, object]] = []
        if s.supersedes and by_key[s.supersedes].say:
            claims += [(v, s.vfrom) for v in by_key[s.supersedes].say]
        claims += [(wrong, s.vfrom) for _, wrong in s.contra]
        if not claims:
            continue
        knowers = set(s.known_by) | {s.stated_by}
        pool = [p for p in AREA_ASKERS[s.area] if p not in knowers and p != "alex"] or ["colin", "jen"]
        days = [d for d in DAYS if d >= s.vfrom] or DAYS[-5:]
        for _ in range(cfg.wrong_claims):
            n += 1
            claim, _ = rng.choice(claims)
            who = rng.choice(pool)
            ch = CHANNELS[AREA_CHANNELS[s.area][0]]
            if ch.visibility is Visibility.TEAM and who not in ch.members:
                ch = CHANNELS["#ops"]
            text = rng.choice(HEDGES).format(x=claim[0].lower() + claim[1:])
            ts = datetime.combine(rng.choice(days), time(9)) + timedelta(minutes=rng.randint(0, 480))
            out.append(SourceDoc(id=f"claim-{n:05d}", source_type=SourceType.SLACK, author_id=who, timestamp=ts,
                                 text=text, container=ch.name, participants=[who], visibility=ch.visibility,
                                 url=f"https://harbourline.slack.com/archives/{ch.cid}/pclaim{n:05d}",
                                 meta={"injected": "wrong_claim"}))
    return out


def _examples(docs: list[SourceDoc], originals: dict[str, str], ev_docs: set[str],
              rng: random.Random) -> list[dict[str, str]]:
    changed = [d for d in docs if d.id in originals and d.id in ev_docs and d.text != originals[d.id]
               and d.source_type is SourceType.SLACK and len(originals[d.id]) < 260]
    picks = rng.sample(changed, min(3, len(changed)))
    return [{"doc_id": d.id, "before": originals[d.id], "after": d.text} for d in sorted(picks, key=lambda x: x.id)]


def write_level(lvl: Level, root: Path = NOISE_DIR) -> Path:
    out = root / f"L{lvl.level}"
    for st, name in FILES.items():
        write_jsonl(out / f"{name}.jsonl", [d for d in lvl.docs if d.source_type is st] if st is not SourceType.SLACK
                    else sorted((d for d in lvl.docs if d.source_type is st), key=lambda d: (d.timestamp, d.id)))
    (out / "id_map.json").write_text(json.dumps(lvl.id_map, indent=0, sort_keys=True), encoding="utf-8")
    (out / "noise_config.json").write_text(
        to_json({"level": lvl.level, "config": dataclasses.asdict(lvl.config), "n_docs": len(lvl.docs),
                 "examples": lvl.examples}, indent=2), encoding="utf-8")
    return out


def build_ladder(seed: int = 7, levels: tuple[int, ...] = LEVELS, root: Path = NOISE_DIR,
                 corpus_dir: Path = CORPUS_DIR) -> list[Level]:
    clean = load_corpus(corpus_dir)
    ev = _clean_evidence()
    out = []
    for lv in levels:
        lvl = corrupt(clean, ev, lv, seed)
        write_level(lvl, root)
        out.append(lvl)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Write the chaos-ladder corpora under data/corpus_noise/")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--levels", default="0,1,2,3,4")
    args = ap.parse_args()
    for lvl in build_ladder(args.seed, tuple(int(x) for x in args.levels.split(","))):
        dropped = sum(1 for v in lvl.id_map.values() if not v)
        print(f"L{lvl.level}: {len(lvl.docs)} docs, {dropped} evidence docs dropped")


if __name__ == "__main__":
    main()
