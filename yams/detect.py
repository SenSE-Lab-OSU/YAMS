"""Deciding which `RecordSpec` a file is actually in.

Every layout in `yams.formats` embeds a monotonic counter at a fixed offset that
advances by a fixed step. Guess the record size wrong and that field misaligns,
so it reads as noise — which makes the layout recoverable from the bytes alone,
without `uuid.txt`.

Measured over the 138 `.bin` files in `data/`: every file classified, worst
winning score 0.977, best runner-up on any file 0.011. Where content and
`uuid.txt` disagreed (9 files) the content was right every time, so detection is
the default and the version file is an optional cross-check.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from yams.formats import (
    REGISTRY,
    V2_VERSION,
    RecordSpec,
    _le_uint,
    spec_for_version,
    specs_for,
)

DEFAULT_THRESHOLD = 0.90
PROBE_RECORDS = 4000
MIN_RECORDS = 4


def score_spec(data: bytes, spec: RecordSpec) -> float:
    """How well `data` fits `spec`, in [0, 1].

    The fraction of consecutive counter deltas equal to the layout's expected
    step, scaled — for layouts that carry one — by the fraction of records
    passing their own integrity check (packed16 reserved bits, ECG sync + CRC).
    """
    n = len(data) // spec.size
    if n < MIN_RECORDS:
        return 0.0
    b = np.frombuffer(data[: n * spec.size], dtype=np.uint8).reshape(-1, spec.size)
    b = b[~(b == 0xFF).all(axis=1)]      # erased records say nothing about the layout
    if b.shape[0] < MIN_RECORDS:
        return 0.0

    tick = _le_uint(b, spec.tick_offset, 4).astype(np.int64)
    delta = np.diff(tick) % (2 ** 32)
    score = float(np.mean(delta == spec.tick_step))

    if spec.validated:
        # Scale by the share of clean records rather than disqualifying on a
        # single set bit, so one corrupt record cannot veto the right answer.
        _, malformed, _ = spec.decode(b)
        score *= float(np.mean(~malformed))
    return score


def score_all(data: bytes, sensor: str) -> dict[str, float]:
    return {s.name: score_spec(data, s) for s in specs_for(sensor)}


def detect(data: bytes, sensor: str, threshold: float = DEFAULT_THRESHOLD):
    """Best-scoring spec for `sensor`, or None if nothing clears `threshold`.

    Returns (spec_or_None, scores dict, best_score, runner_up_score).
    """
    scores = score_all(data, sensor)
    if not scores:
        return None, {}, 0.0, 0.0
    order = sorted(scores.items(), key=lambda kv: -kv[1])
    best_name, best = order[0]
    runner_up = order[1][1] if len(order) > 1 else 0.0
    if best < threshold:
        return None, scores, best, runner_up
    from yams.formats import get_spec
    return get_spec(sensor, best_name), scores, best, runner_up


def version_spec(sensor: str, version: tuple) -> RecordSpec:
    """The layout `version` firmware is documented to write.

    Falls back sensibly when the version predates a sensor entirely (a 0.0.0
    version from a missing uuid.txt, with ECG only existing from v4.7.0).
    """
    spec = spec_for_version(sensor, version)
    if spec is not None:
        return spec
    candidates = specs_for(sensor)
    if len(candidates) == 1:
        return candidates[0]
    for s in candidates:                 # else the oldest documented layout
        if s.until is not None:
            return s
    return candidates[0]


@dataclass
class Resolution:
    """Which spec was chosen for one file, and on what evidence."""
    filename: str
    sensor: str
    spec: RecordSpec
    method: str                    # "sniffed" | "version" | "forced"
    score: float | None = None
    runner_up: float | None = None
    uuid_spec: RecordSpec | None = None
    agrees: bool | None = None     # None when not cross-checked

    @property
    def name(self):
        return self.spec.name

    def row(self):
        score = "-" if self.score is None else f"{self.score:.3f}"
        implied = self.uuid_spec.name if self.uuid_spec is not None else "-"
        agrees = "-" if self.agrees is None else ("yes" if self.agrees else "NO")
        return (f"{self.filename:<38} {self.sensor:<4} {self.spec.name:<9} "
                f"{self.method:<8} {score:>6}  {implied:<9} {agrees}")

    @staticmethod
    def header():
        return (f"{'file':<38} {'sens':<4} {'resolved':<9} "
                f"{'method':<8} {'score':>6}  {'uuid':<9} agrees")


class FormatConflict(ValueError):
    """Content detection and uuid.txt disagree, with on_format_conflict='raise'."""


def resolve(filepath: str, sensor: str, choice: str, version: tuple, *,
            force_new_format: bool = False,
            validate_with_uuid: bool = False,
            on_conflict: str = "warn",
            threshold: float = DEFAULT_THRESHOLD,
            probe: int | None = None) -> Resolution:
    """Pick the spec for one file.

    `choice` is "auto" (detect from content, fall back to the version), "version"
    (use uuid.txt only — the pre-1.6 behaviour), or an explicit spec name.
    """
    import os

    from yams.formats import get_spec

    basename = os.path.basename(filepath)
    effective = max(version, V2_VERSION) if force_new_format else version

    if choice not in ("auto", "version"):
        spec, method, score, runner_up = get_spec(sensor, choice), "forced", None, None
    elif choice == "version":
        spec, method, score, runner_up = version_spec(sensor, effective), "version", None, None
    else:
        largest = max(s.size for s in specs_for(sensor))
        with open(filepath, "rb") as f:
            data = f.read((probe or PROBE_RECORDS) * largest)
        found, scores, best, runner_up = detect(data, sensor, threshold)
        detail = ", ".join(f"{k}={v:.3f}" for k, v in sorted(scores.items(), key=lambda kv: -kv[1]))
        if found is None:
            spec, method, score = version_spec(sensor, effective), "version", None
            print(f"{sensor} sniff inconclusive for {basename} ({detail}); "
                  f"falling back to version -> {spec.name}")
        else:
            spec, method, score = found, "sniffed", best
            print(f"{sensor} sniff {basename}: {detail} -> {spec.name}")

    res = Resolution(basename, sensor, spec, method, score, runner_up)

    if validate_with_uuid:
        implied = spec_for_version(sensor, version)
        res.uuid_spec = implied
        if implied is not None:
            res.agrees = implied.name == spec.name
            if not res.agrees:
                msg = (f"format conflict on {basename}: content says {spec.name}, "
                       f"uuid.txt (v{'.'.join(map(str, version))}) implies {implied.name}")
                if on_conflict == "raise":
                    raise FormatConflict(msg)
                if on_conflict == "trust_uuid":
                    print(f"{msg} — trusting uuid.txt")
                    res.spec, res.method = implied, "version"
                else:
                    print(f"{msg} — trusting content (pass --on_format_conflict "
                          f"trust_uuid to invert)")
    return res


def sniff_file(filepath: str, sensor: str, threshold: float = DEFAULT_THRESHOLD):
    """Convenience wrapper: detect a single file's spec name, or None."""
    largest = max(s.size for s in specs_for(sensor))
    with open(filepath, "rb") as f:
        data = f.read(PROBE_RECORDS * largest)
    spec, _, _, _ = detect(data, sensor, threshold)
    return None if spec is None else spec.name
