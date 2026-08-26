"""Tests for the record registry (yams.formats) and content detection (yams.detect).

Runnable with pytest or directly:  python3 tests/test_formats_detect.py
"""
import os
import struct
import sys
import tempfile
import zlib

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yams import detect  # noqa: E402
from yams.detect import FormatConflict, detect as detect_spec, resolve, version_spec  # noqa: E402
from yams.formats import (  # noqa: E402
    AC_V3_REGION_SIZE,
    AC_V3_SAMPLES_PER_BLOCK,
    REGISTRY,
    V2_VERSION,
    crc8,
    get_CDCT_init,
    get_spec,
    read_bin,
    recompute_cdct,
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

# ac:v3 (ACF3) is a container, not a flat record stream: it has no single
# "record size" a fixed-count writer could repeat, so it sits outside WRITERS
# and the generic per-record invariant tests below. FLAT_REGISTRY is what
# those tests iterate; ac:v3 gets its own writer and tests further down.
FLAT_REGISTRY = tuple(s for s in REGISTRY if s.read_file is None)


def crc32_field(buf: bytes, off: int, length: int) -> int:
    """The ACF3 CRC convention: CRC-32/ISO-HDLC with the CRC field itself zeroed."""
    patched = bytearray(buf)
    patched[off:off + length] = bytes(length)
    return zlib.crc32(bytes(patched)) & 0xFFFFFFFF


def w_ac_v3_header(odr_num=1125, odr_den=2, anchor_hz=512, bad_crc=False):
    h = bytearray(4096)
    struct.pack_into("<4sHH", h, 0, b"ACF3", 3, 2)
    struct.pack_into("<II", h, 8, odr_num, odr_den)
    struct.pack_into("<HH", h, 16, 2, 16384)
    struct.pack_into("<I", h, 24, anchor_hz)
    struct.pack_into("<I", h, 28, 32)
    struct.pack_into("<BBBB", h, 32, 0, 0, 1, 32)
    crc = crc32_field(bytes(h), 20, 4) if not bad_crc else 0xDEADBEEF
    struct.pack_into("<I", h, 20, crc)
    return bytes(h)


def w_ac_v3_block(first_seq, samples, anchor_tick=0, bad_crc=False):
    """`samples`: list of (x, y, z) int16 tuples. A full block is exactly 680."""
    body = bytearray(16)
    struct.pack_into("<4sII", body, 0, b"ACB1", anchor_tick, first_seq)
    body += b"".join(struct.pack("<3h", x, y, z) for x, y, z in samples)
    crc = crc32_field(bytes(body), 12, 4) if not bad_crc else 0xDEADBEEF
    struct.pack_into("<I", body, 12, crc)
    return bytes(body)


def w_ac_v3_terminal(valid_len, bad_crc=False, bad_magic=False):
    t = bytearray(4096)
    struct.pack_into("<4sI", t, 0, (b"XXXX" if bad_magic else b"ACT2"), valid_len)
    crc = crc32_field(bytes(t), 8, 4) if not bad_crc else 0xDEADBEEF
    struct.pack_into("<I", t, 8, crc)
    return bytes(t)


def w_ac_v3_file(blocks, terminal=True, valid_len=None):
    """Assemble a full 4 MiB ACF3 file. `blocks` are already-built block byte strings."""
    region = b"".join(blocks)
    region += bytes(AC_V3_REGION_SIZE - len(region))     # preallocated tail
    if valid_len is None:
        valid_len = sum(len(b) for b in blocks)
    trailer = w_ac_v3_terminal(valid_len) if terminal else bytes(4096)
    return w_ac_v3_header() + region + trailer


def straight_samples(n, start=0):
    """n samples of rising (x, y, z), with X's bit 0 (FSYNC) alternating."""
    return [(((start + i) * 2) | (i & 1), 1000 + i, -1000 - i) for i in range(n)]


def w_ac_v3_1_full_block(start=0):
    return w_ac_v3_file([w_ac_v3_block(start, straight_samples(680, start))])


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
    assert {s.key for s in FLAT_REGISTRY} == set(WRITERS)
    assert "ac:v3" in {s.key for s in REGISTRY} - set(WRITERS)  # container: its own writer/tests below


def test_record_sizes_match_the_bytes_written():
    for spec in FLAT_REGISTRY:
        data = WRITERS[spec.key](4)
        assert len(data) == 4 * spec.size, f"{spec.key}: {len(data)} != 4*{spec.size}"


def test_tick_offset_lands_on_the_counter():
    """The declared tick offset must actually be where the counter was written."""
    for spec in FLAT_REGISTRY:
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
    assert get_spec("ac", "v3").sample_rate == 562.5
    assert get_spec("ecg", "framed").sample_rate == 512


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------

def test_each_layout_detects_as_itself():
    for spec in FLAT_REGISTRY:
        data = WRITERS[spec.key](500)
        found, scores, best, runner = detect_spec(data, spec.sensor)
        assert found is not None and found.name == spec.name, f"{spec.key}: {scores}"
        assert best >= 0.99, f"{spec.key} scored only {best}"
    data = w_ac_v3_1_full_block()
    found, scores, best, runner = detect_spec(data, "ac")
    assert found is not None and found.name == "v3", scores
    assert best == 1.0


def test_wrong_layouts_score_near_zero():
    """A misaligned counter must not merely lose — it must collapse."""
    for spec in FLAT_REGISTRY:
        data = WRITERS[spec.key](500)
        _, scores, best, runner_up = detect_spec(data, spec.sensor)
        assert runner_up < 0.1, f"{spec.key}: runner-up {runner_up} too close ({scores})"
    _, scores, best, runner_up = detect_spec(w_ac_v3_1_full_block(), "ac")
    assert runner_up < 0.1, f"ac:v3: runner-up {runner_up} too close ({scores})"


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
    for spec in FLAT_REGISTRY:
        p = write_tmp(WRITERS[spec.key](50, start=10), spec.sensor)
        df, _ = read_bin(p, spec)
        assert list(df.columns) == expected[spec.key] + ["CDCT", "init_CDCT"], spec.key
        assert len(df) == 50, f"{spec.key}: {len(df)} rows"


def test_cdct_matches_the_declared_sample_rate():
    for spec in FLAT_REGISTRY:
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


# ---------------------------------------------------------------------------
# filename -> t0 (get_CDCT_init): legacy vs. chunked v3 naming
# ---------------------------------------------------------------------------

def test_cdct_init_legacy_filename_is_unix_seconds():
    t0, dt = get_CDCT_init("400101ppg1700000000.bin")
    assert t0 == 1700000000 and dt.startswith("2023/11/14")


def test_cdct_init_chunked_filename_divides_out_the_millisecond_composite():
    """session_id = unix_time_seconds*1000 + (uptime_ms % 1000); the chunk
    suffix must not be read as t0, and session_id must not be read as seconds.
    """
    t0, dt = get_CDCT_init("260800ac1787767943767_0000.bin")
    assert t0 == 1787767943 and dt.startswith("2026/08/26")
    # same session, later chunk: same t0
    t0_chunk4, _ = get_CDCT_init("260800ecg1787767943767_0004.bin")
    assert t0_chunk4 == t0


def test_recompute_cdct_stitches_chunks_without_resetting():
    """Simulates concatenating two chunks of one session: Counter keeps
    advancing across the chunk boundary, but both chunks were read with the
    same (filename-shared) t0. recompute_cdct must give one continuous clock
    over the concatenated Counter, not restart it at the second chunk's rows.
    """
    spec = get_spec("ecg", "framed")
    chunk0 = pd.DataFrame({"Counter": np.arange(0, 100, dtype=np.uint32)})
    chunk1 = pd.DataFrame({"Counter": np.arange(100, 150, dtype=np.uint32)})
    combined = pd.concat([chunk0, chunk1], ignore_index=True)
    t0 = 1_700_000_000

    out = recompute_cdct(combined, spec, t0)

    assert out["CDCT"].is_monotonic_increasing
    assert out["CDCT"].iloc[0] == t0
    assert abs(out["CDCT"].iloc[-1] - (t0 + 149 / spec.tick_rate)) < 1e-9
    # no discontinuity right at the chunk boundary (row 99 -> row 100)
    step = out["CDCT"].iloc[100] - out["CDCT"].iloc[99]
    assert abs(step - 1 / spec.tick_rate) < 1e-9


# ---------------------------------------------------------------------------
# ac:v3 (ACF3 container): header + ACB1 data blocks + ACT2 terminal record
# ---------------------------------------------------------------------------

def test_ac_v3_round_trip_full_and_short_block():
    spec = get_spec("ac", "v3")
    full = w_ac_v3_block(0, straight_samples(680, 0), anchor_tick=1000)
    short = w_ac_v3_block(680, straight_samples(50, 680), anchor_tick=1619)
    p = write_tmp(w_ac_v3_file([full, short]), "ac")
    df, _ = read_bin(p, spec)
    assert list(df.columns) == ["AccX", "AccY", "AccZ", "Counter", "CDCT", "init_CDCT"]
    assert len(df) == 730
    assert list(df["Counter"]) == list(range(730))
    assert df.attrs["malformed_records"] == 0


def test_ac_v3_fsync_bit_masked():
    """X bit 0 carries a sampled FSYNC marker and must be cleared before use."""
    spec = get_spec("ac", "v3")
    samples = [(100, 1, -1), (101, 2, -2)]     # 101 == 100 | FSYNC bit
    p = write_tmp(w_ac_v3_file([w_ac_v3_block(0, samples)], valid_len=16 + 2 * 6), "ac")
    df, _ = read_bin(p, spec)
    assert list(df["AccX"]) == [100, 100]
    assert list(df["AccY"]) == [1, 2]
    assert list(df["AccZ"]) == [-1, -2]


def test_ac_v3_bad_block_crc_dropped_scan_continues():
    """One corrupt block in an otherwise valid chunk must not veto the rest."""
    spec = get_spec("ac", "v3")
    b0 = w_ac_v3_block(0, straight_samples(680, 0))
    b1 = w_ac_v3_block(680, straight_samples(680, 680), bad_crc=True)
    b2 = w_ac_v3_block(1360, straight_samples(680, 1360))
    p = write_tmp(w_ac_v3_file([b0, b1, b2]), "ac")
    df, _ = read_bin(p, spec)
    assert len(df) == 680 * 2
    assert list(df["Counter"]) == list(range(680)) + list(range(1360, 2040))
    assert df.attrs["malformed_records"] == AC_V3_SAMPLES_PER_BLOCK


def test_ac_v3_missing_terminal_recovers_valid_prefix():
    """No/invalid terminal record: recover consecutive valid full blocks, stop there."""
    spec = get_spec("ac", "v3")
    b0 = w_ac_v3_block(0, straight_samples(680, 0))
    b1 = w_ac_v3_block(680, straight_samples(680, 680))
    p = write_tmp(w_ac_v3_file([b0, b1], terminal=False), "ac")
    df, _ = read_bin(p, spec)
    assert len(df) == 1360


def test_ac_v3_rejects_wrong_file_size():
    spec = get_spec("ac", "v3")
    p = write_tmp(w_ac_v3_1_full_block()[:-1], "ac")   # one byte short of 4 MiB
    try:
        read_bin(p, spec)
    except ValueError as e:
        assert "4194304" in str(e)
        return
    raise AssertionError("expected ValueError")


def test_ac_v3_strict_raises_on_bad_header_crc():
    spec = get_spec("ac", "v3")
    block = w_ac_v3_block(0, straight_samples(680, 0))
    region = block + bytes(AC_V3_REGION_SIZE - len(block))
    data = w_ac_v3_header(bad_crc=True) + region + w_ac_v3_terminal(len(block))
    p = write_tmp(data, "ac")
    df, _ = read_bin(p, spec)                          # tolerated by default
    assert len(df) == 680
    try:
        read_bin(p, spec, strict=True)
    except ValueError as e:
        assert "header CRC" in str(e)
        return
    raise AssertionError("expected ValueError")


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
