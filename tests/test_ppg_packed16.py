"""Tests for the packed 16-byte PPG record decoder.

Run with `python -m pytest tests/test_ppg_packed16.py`, or directly with
`python tests/test_ppg_packed16.py` (no pytest required).

Vectors come from data/PPG_PACKED_16_BYTE_FORMAT.md.
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yams.data_extraction import (  # noqa: E402
    PPG_PACKED_RECORD_SIZE,
    decode_ppg_packed16,
    read_ppg_bin_packed16,
    sniff_ppg_format,
)

ERASED = b"\xFF" * PPG_PACKED_RECORD_SIZE


def encode(ir1, ir2, g1, g2, tick):
    """Reference encoder, mirroring the firmware side of the format."""
    out = bytearray()
    for value in (ir1, ir2, g1, g2):
        out += int(value).to_bytes(3, "little")
    out += int(tick).to_bytes(4, "little")
    return bytes(out)


def decode_one(record):
    ir1, ir2, g1, g2, tick, malformed = decode_ppg_packed16(record)
    return int(ir1[0]), int(ir2[0]), int(g1[0]), int(g2[0]), int(tick[0]), bool(malformed[0])


def test_golden_vector_both_directions():
    fields = (0x000001, 0x012345, 0x07FFFF, 0x000100, 0x12345678)
    expected = bytes([0x01, 0x00, 0x00, 0x45, 0x23, 0x01, 0xFF, 0xFF, 0x07,
                      0x00, 0x01, 0x00, 0x78, 0x56, 0x34, 0x12])

    assert encode(*fields) == expected
    assert decode_one(expected) == (*fields, False)


def test_channel_boundaries():
    for value in (0, 1, 0xFF, 0x100, 0xFFFF, 0x10000, 0x7FFFF):
        record = encode(value, value, value, value, 0)
        assert decode_one(record) == (value, value, value, value, 0, False)


def test_tick_boundaries():
    for tick in (0, 1, 0xFF, 0x100, 0xFFFF, 0x10000, 0xFFFFFF, 0x1000000, 0xFFFFFFFF):
        record = encode(0, 0, 0, 0, tick)
        assert decode_one(record) == (0, 0, 0, 0, tick, False)


def test_reserved_bits_flagged():
    # bit 19 set in the first channel: 00 00 08
    record = bytes([0x00, 0x00, 0x08]) + bytes(9) + bytes(4)
    assert decode_one(record)[-1] is True

    # bit 23 set in the last channel
    record = bytes(9) + bytes([0x00, 0x00, 0x80]) + bytes(4)
    assert decode_one(record)[-1] is True


def test_field_order_across_records():
    records = [(i, i + 1, i + 2, i + 3, 2 * i) for i in range(64)]
    data = b"".join(encode(*r) for r in records)
    ir1, ir2, g1, g2, tick, malformed = decode_ppg_packed16(data)

    assert len(ir1) == len(records)
    assert not malformed.any()
    assert list(ir1) == [r[0] for r in records]
    assert list(ir2) == [r[1] for r in records]
    assert list(g1) == [r[2] for r in records]
    assert list(g2) == [r[3] for r in records]
    assert list(tick) == [r[4] for r in records]


def test_trailing_erased_records_trimmed():
    data = encode(1, 2, 3, 4, 10) + encode(5, 6, 7, 8, 12) + ERASED * 3
    ir1, _, _, _, tick, _ = decode_ppg_packed16(data)
    assert list(ir1) == [1, 5]
    assert list(tick) == [10, 12]


def test_ff_bytes_inside_a_valid_record_survive():
    # Tick 0xFFFFFF00 and channels at max: a byte-wise 0xFF trim would eat this.
    data = encode(0x7FFFF, 0x7FFFF, 0x7FFFF, 0x7FFFF, 0xFFFFFF00) + ERASED
    ir1, _, _, _, tick, malformed = decode_ppg_packed16(data)
    assert len(ir1) == 1
    assert not malformed.any()
    assert int(tick[0]) == 0xFFFFFF00


def test_tick_rollover_is_not_corruption():
    data = encode(1, 1, 1, 1, 0xFFFFFFFF) + encode(2, 2, 2, 2, 1)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ppg1700000000.bin")
        with open(path, "wb") as f:
            f.write(data)
        df, _ = read_ppg_bin_packed16(path)

    # 0xFFFFFFFF is the erased-counter sentinel and is dropped; the wrapped
    # record must survive with a forward-moving CDCT.
    assert list(df['Counter']) == [1]
    assert df['CDCT'].is_monotonic_increasing


def test_read_file_columns_and_cdct():
    t0 = 1700000000
    data = b"".join(encode(i, i, i, i, 2 * i) for i in range(1, 5))
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"123ppg{t0}.bin")
        with open(path, "wb") as f:
            f.write(data)
        df, dt = read_ppg_bin_packed16(path)

    assert list(df.columns) == ["ir1", "ir2", "g1", "g2", "Counter", "CDCT", "init_CDCT"]
    assert len(df) == 4
    assert df['init_CDCT'].iloc[0] == t0
    # ticks step by 2 at 512 Hz -> 1/256 s per record
    assert np.allclose(np.diff(df['CDCT']), 1 / 256)
    assert dt.startswith("2023/11/14")


def test_malformed_records_dropped_and_counted():
    good = encode(1, 2, 3, 4, 2)
    bad = bytes([0x00, 0x00, 0x08]) + bytes(9) + (4).to_bytes(4, "little")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ppg1700000000.bin")
        with open(path, "wb") as f:
            f.write(good + bad + encode(5, 6, 7, 8, 6))
        df, _ = read_ppg_bin_packed16(path)

    assert len(df) == 2
    assert df.attrs['malformed_records'] == 1


def test_strict_mode_raises():
    bad = bytes([0x00, 0x00, 0x08]) + bytes(9) + bytes(4)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ppg1700000000.bin")
        with open(path, "wb") as f:
            f.write(bad)
        try:
            read_ppg_bin_packed16(path, strict=True)
        except ValueError:
            pass
        else:
            raise AssertionError("strict mode should reject reserved-bit records")


def test_all_records_dropped_raises():
    # Wrong layout selected: every record fails validation, so there is nothing
    # to emit. Must be an error, not a one-row all-NaN frame.
    bad = bytes([0x00, 0x00, 0x08]) + bytes(9) + bytes(4)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ppg1700000000.bin")
        with open(path, "wb") as f:
            f.write(bad * 16)
        try:
            read_ppg_bin_packed16(path)
        except ValueError as e:
            assert "no usable records" in str(e)
        else:
            raise AssertionError("a fully malformed file should raise")


def test_partial_trailing_record():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ppg1700000000.bin")
        with open(path, "wb") as f:
            f.write(encode(1, 2, 3, 4, 2) + b"\x01\x02\x03")
        df, _ = read_ppg_bin_packed16(path)
        assert len(df) == 1

        try:
            read_ppg_bin_packed16(path, strict=True)
        except ValueError:
            pass
        else:
            raise AssertionError("strict mode should reject a partial trailing record")


def test_sniff_distinguishes_packed16_from_v2():
    v2 = b"".join(
        b"".join(int(v).to_bytes(4, "little") for v in (100, 200, 300, 400, 2 * i))
        for i in range(200)
    )
    packed = b"".join(encode(100, 200, 300, 400, 2 * i) for i in range(200))

    with tempfile.TemporaryDirectory() as tmp:
        p_packed = os.path.join(tmp, "ppg1700000000.bin")
        p_v2 = os.path.join(tmp, "ppg1700000001.bin")
        with open(p_packed, "wb") as f:
            f.write(packed)
        with open(p_v2, "wb") as f:
            f.write(v2)

        assert sniff_ppg_format(p_packed) == "packed16"
        assert sniff_ppg_format(p_v2) == "v2"


def test_sniff_survives_erased_tail_and_one_bad_record():
    bad = bytes([0x00, 0x00, 0x08]) + bytes(9) + (0).to_bytes(4, "little")
    data = (b"".join(encode(100, 200, 300, 400, 2 * i) for i in range(200))
            + bad + ERASED * 16)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ppg1700000000.bin")
        with open(path, "wb") as f:
            f.write(data)
        assert sniff_ppg_format(path) == "packed16"


if __name__ == '__main__':
    failures = 0
    for name, fn in sorted(list(globals().items())):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:
            failures += 1
            print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
