"""Tests for the record registry (yams.formats) and content detection (yams.detect).

Runnable with pytest or directly:  python3 tests/test_formats_detect.py
"""
import os
import struct
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yams import detect  # noqa: E402
from yams.detect import FormatConflict, detect as detect_spec, resolve, version_spec  # noqa: E402
from yams.formats import (  # noqa: E402
    REGISTRY,
    V2_VERSION,
    crc8,
    get_spec,
    read_bin,
    spec_for_version,
)

# ---------------------------------------------------------------------------
# synthetic writers, one per layout
# ---------------------------------------------------------------------------

def w_ppg_legacy(n, start=0, step=5):
    return b"".join(struct.pack("<6i", 100 + i, 200 + i, 300 + i, 400 + i,
                                7000 + i, (start + i * step) % 2**16) for i in range(n))


def w_ppg_v2(n, start=0, step=2):
    return b"".join(struct.pack("<5I", 100 + i, 200 + i, 300 + i, 400 + i,
                                start + i * step) for i in range(n))


def w_ppg_packed16(n, start=0, step=2):
    out = b""
    for i in range(n):
        for ch in (100 + i, 200 + i, 300 + i, 400 + i):
            out += ch.to_bytes(3, "little")
        out += struct.pack("<I", start + i * step)
    return out


def w_ac_legacy(n, start=0, step=10):
    return b"".join(struct.pack("<3h4f2i", 1, 2, 3, 0.1, 0.2, 0.3, 0.4,
                                7000 + i, (start + i * step) % 2**16) for i in range(n))


def w_ac_v2(n, start=0, step=16):
    return b"".join(struct.pack("<3h4fI", 1, 2, 3, 0.1, 0.2, 0.3, 0.4,
                                start + i * step) for i in range(n))


def w_ecg(n, start=0, step=1):
    out = b""
    for i in range(n):
        body = struct.pack("<BB", 0x01, 0x00) + struct.pack("<I", start + i * step) \
               + ((i * 64) & 0xFFFFFF).to_bytes(3, "big")
        out += b"\xA5\xEC" + body + bytes([crc8(body)])
    return out


WRITERS = {
    "ppg:legacy": w_ppg_legacy, "ppg:v2": w_ppg_v2, "ppg:packed16": w_ppg_packed16,
    "ac:legacy": w_ac_legacy, "ac:v2": w_ac_v2, "ecg:framed": w_ecg,
}


def write_tmp(data, sensor):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"400101{sensor}1700000000.bin")
    with open(p, "wb") as f:
        f.write(data)
    return p


# ---------------------------------------------------------------------------
# registry invariants
# ---------------------------------------------------------------------------

def test_every_spec_has_a_writer():
    assert {s.key for s in REGISTRY} == set(WRITERS)


def test_record_sizes_match_the_bytes_written():
    for spec in REGISTRY:
        data = WRITERS[spec.key](4)
        assert len(data) == 4 * spec.size, f"{spec.key}: {len(data)} != 4*{spec.size}"


def test_tick_offset_lands_on_the_counter():
    """The declared tick offset must actually be where the counter was written."""
    for spec in REGISTRY:
        data = WRITERS[spec.key](6, start=1000)
        b = np.frombuffer(data, np.uint8).reshape(-1, spec.size)
        tick = b[:, spec.tick_offset:spec.tick_offset + 4].copy().view("<u4").ravel()
        expected = 1000 + np.arange(6) * spec.tick_step
        assert np.array_equal(tick, expected), f"{spec.key}: {tick} != {expected}"


def test_sample_rate_derivation():
    assert get_spec("ppg", "legacy").sample_rate == 64
    assert get_spec("ppg", "v2").sample_rate == 256
    assert get_spec("ppg", "packed16").sample_rate == 256
    assert get_spec("ac", "legacy").sample_rate == 32
    assert get_spec("ac", "v2").sample_rate == 32
    assert get_spec("ecg", "framed").sample_rate == 512


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------

def test_each_layout_detects_as_itself():
    for spec in REGISTRY:
        data = WRITERS[spec.key](500)
        found, scores, best, runner = detect_spec(data, spec.sensor)
        assert found is not None and found.name == spec.name, f"{spec.key}: {scores}"
        assert best >= 0.99, f"{spec.key} scored only {best}"


def test_wrong_layouts_score_near_zero():
    """A misaligned counter must not merely lose — it must collapse."""
    for spec in REGISTRY:
        data = WRITERS[spec.key](500)
        _, scores, best, runner_up = detect_spec(data, spec.sensor)
        assert runner_up < 0.1, f"{spec.key}: runner-up {runner_up} too close ({scores})"


def test_detection_returns_none_below_threshold():
    data = os.urandom(20000)
    found, _, _, _ = detect_spec(data, "ppg")
    assert found is None


def test_detection_ignores_erased_tail():
    spec = get_spec("ppg", "packed16")
    data = WRITERS[spec.key](300) + b"\xFF" * (spec.size * 500)
    found, _, best, _ = detect_spec(data, "ppg")
    assert found.name == "packed16" and best >= 0.99


def test_too_few_records_is_inconclusive():
    found, _, _, _ = detect_spec(w_ppg_v2(2), "ppg")
    assert found is None


# ---------------------------------------------------------------------------
# version mapping
# ---------------------------------------------------------------------------

def test_version_mapping():
    assert spec_for_version("ppg", (4, 6, 5)).name == "legacy"
    assert spec_for_version("ppg", V2_VERSION).name == "v2"
    assert spec_for_version("ac", (4, 7, 1)).name == "v2"
    assert spec_for_version("ppg", (0, 0, 0)).name == "legacy"


def test_packed16_is_not_reachable_by_version():
    """It carries no version tie — that is why detection exists."""
    for v in [(4, 5, 3), (4, 7, 0), (9, 9, 9)]:
        assert spec_for_version("ppg", v).name != "packed16"


def test_ecg_falls_back_to_its_only_layout():
    assert version_spec("ecg", (0, 0, 0)).name == "framed"


# ---------------------------------------------------------------------------
# resolve(): modes, cross-check, conflict policy
# ---------------------------------------------------------------------------

def test_auto_beats_a_stale_version():
    p = write_tmp(w_ppg_v2(500), "ppg")
    res = resolve(p, "ppg", "auto", (4, 6, 3))
    assert res.spec.name == "v2" and res.method == "sniffed"


def test_version_mode_ignores_content():
    p = write_tmp(w_ppg_v2(500), "ppg")
    res = resolve(p, "ppg", "version", (4, 6, 3))
    assert res.spec.name == "legacy" and res.method == "version"


def test_forced_mode_ignores_both():
    p = write_tmp(w_ppg_v2(500), "ppg")
    res = resolve(p, "ppg", "packed16", V2_VERSION)
    assert res.spec.name == "packed16" and res.method == "forced"


def test_auto_falls_back_to_version_when_inconclusive():
    p = write_tmp(os.urandom(20000), "ppg")
    res = resolve(p, "ppg", "auto", V2_VERSION)
    assert res.spec.name == "v2" and res.method == "version"


def test_force_new_format_only_moves_the_fallback():
    p = write_tmp(os.urandom(20000), "ppg")
    res = resolve(p, "ppg", "auto", (4, 5, 3), force_new_format=True)
    assert res.spec.name == "v2"
    # ...and does not override content when detection succeeds
    q = write_tmp(w_ppg_legacy(500), "ppg")
    res2 = resolve(q, "ppg", "auto", (4, 5, 3), force_new_format=True)
    assert res2.spec.name == "legacy" and res2.method == "sniffed"


def test_validate_off_by_default_records_nothing():
    p = write_tmp(w_ppg_v2(500), "ppg")
    res = resolve(p, "ppg", "auto", (4, 6, 3))
    assert res.agrees is None and res.uuid_spec is None


def test_validate_flags_disagreement_but_content_wins():
    p = write_tmp(w_ppg_v2(500), "ppg")
    res = resolve(p, "ppg", "auto", (4, 6, 3), validate_with_uuid=True)
    assert res.agrees is False and res.uuid_spec.name == "legacy"
    assert res.spec.name == "v2"


def test_validate_agrees_when_uuid_is_right():
    p = write_tmp(w_ppg_v2(500), "ppg")
    res = resolve(p, "ppg", "auto", V2_VERSION, validate_with_uuid=True)
    assert res.agrees is True


def test_conflict_raise():
    p = write_tmp(w_ppg_v2(500), "ppg")
    try:
        resolve(p, "ppg", "auto", (4, 6, 3), validate_with_uuid=True, on_conflict="raise")
    except FormatConflict:
        return
    raise AssertionError("expected FormatConflict")


def test_conflict_trust_uuid():
    p = write_tmp(w_ppg_v2(500), "ppg")
    res = resolve(p, "ppg", "auto", (4, 6, 3), validate_with_uuid=True,
                  on_conflict="trust_uuid")
    assert res.spec.name == "legacy" and res.method == "version"


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def test_round_trip_columns_for_every_layout():
    expected = {
        "ppg:legacy": ["ir1", "ir2", "g1", "g2", "Timestamp", "Counter"],
        "ppg:v2": ["ir1", "ir2", "g1", "g2", "Counter"],
        "ppg:packed16": ["ir1", "ir2", "g1", "g2", "Counter"],
        "ac:legacy": ["AccX", "AccY", "AccZ", "QuatX", "QuatY", "QuatZ", "ENMO",
                      "Timestamp", "Counter"],
        "ac:v2": ["AccX", "AccY", "AccZ", "QuatX", "QuatY", "QuatZ", "ENMO", "Counter"],
        "ecg:framed": ["ECG", "ETAG", "PTAG", "Counter"],
    }
    for spec in REGISTRY:
        p = write_tmp(WRITERS[spec.key](50, start=10), spec.sensor)
        df, _ = read_bin(p, spec)
        assert list(df.columns) == expected[spec.key] + ["CDCT", "init_CDCT"], spec.key
        assert len(df) == 50, f"{spec.key}: {len(df)} rows"


def test_cdct_matches_the_declared_sample_rate():
    for spec in REGISTRY:
        p = write_tmp(WRITERS[spec.key](200, start=0), spec.sensor)
        df, _ = read_bin(p, spec)
        span = df["CDCT"].iloc[-1] - df["CDCT"].iloc[0]
        assert abs(span - 199 / spec.sample_rate) < 1e-6, f"{spec.key}: span {span}"


def test_legacy_counter_wraps_at_16_bits():
    """The legacy counter is a uint16; a wrap must read as the true elapsed step.

    The old code used `2^16 - 1`, which is XOR and evaluates to 13, folding
    every wrap to a 3-tick error that accumulated through the cumulative sum.
    """
    spec = get_spec("ac", "legacy")
    p = write_tmp(w_ac_legacy(400, start=65500), "ac")   # wraps partway through
    df, _ = read_bin(p, spec)
    span = df["CDCT"].iloc[-1] - df["CDCT"].iloc[0]
    assert abs(span - 399 / spec.sample_rate) < 1e-6, span


def test_ecg_rejects_bad_crc():
    spec = get_spec("ecg", "framed")
    data = bytearray(w_ecg(100))
    data[11] ^= 0xFF                       # corrupt frame 0's CRC
    p = write_tmp(bytes(data), "ecg")
    df, _ = read_bin(p, spec)
    assert len(df) == 99 and df.attrs["malformed_records"] == 1


def test_ecg_rejects_bad_sync():
    spec = get_spec("ecg", "framed")
    data = bytearray(w_ecg(100))
    data[12] = 0x00                        # corrupt frame 1's sync word
    p = write_tmp(bytes(data), "ecg")
    df, _ = read_bin(p, spec)
    assert len(df) == 99


def test_strict_raises_on_partial_record():
    spec = get_spec("ppg", "v2")
    p = write_tmp(w_ppg_v2(50) + b"\x01\x02", "ppg")
    read_bin(p, spec)                      # tolerated by default
    try:
        read_bin(p, spec, strict=True)
    except ValueError as e:
        assert "divisible" in str(e)
        return
    raise AssertionError("expected ValueError")


def test_wrong_spec_on_good_data_raises_rather_than_emitting_junk():
    p = write_tmp(w_ppg_packed16(500), "ppg")
    try:
        read_bin(p, get_spec("ppg", "v2"))
    except ValueError:
        return                             # acceptable: refused outright
    # if it did decode, detection must still prefer the truth
    assert detect.sniff_file(p, "ppg") == "packed16"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failures = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:
            failures += 1
            print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failures}/{len(fns)} passed, {failures} failure(s)")
    sys.exit(1 if failures else 0)
