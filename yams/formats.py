"""On-disk record layouts, declared once.

Every fact about a layout lives in one `RecordSpec`: how many bytes a record
takes, how to turn those bytes into columns, where the counter sits, how wide it
is and how fast it advances. The same fields drive three consumers — decoding
(`read_bin` here), content detection (`yams.detect`) and counter validation — so
they cannot drift apart the way the old arrangement did, where
`DataExtractor.ppg_labels` described one layout while `read_ppg_bin` implemented
another.

Adding a future variant means adding one entry to `REGISTRY`. Nothing else in
the codebase enumerates formats.

This module is a leaf: numpy and pandas only, no Gradio, no options, no I/O
policy beyond reading the file it is handed.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

import numpy as np
import pandas as pd

# Packed 16-byte PPG channel packing — see data/PPG_PACKED_16_BYTE_FORMAT.md
PPG_PACKED_RECORD_SIZE = 16
PPG_PACKED_SAMPLE_MASK = 0x7FFFF
PPG_PACKED_RESERVED_MASK = 0xFFF80000   # bits 19..31 must be clear in every channel

# Firmware at or above this version writes the "v2" layouts.
V2_VERSION = (4, 7, 0)


# ---------------------------------------------------------------------------
# byte helpers
# ---------------------------------------------------------------------------

def _le_uint(b, off, n):
    """Little-endian unsigned integer of `n` bytes from an (N, size) uint8 array."""
    out = np.zeros(b.shape[0], dtype=np.uint32)
    for i in range(n):
        out |= b[:, off + i].astype(np.uint32) << (8 * i)
    return out


def _be_uint(b, off, n):
    """Big-endian unsigned integer of `n` bytes (the ECG sample field)."""
    out = np.zeros(b.shape[0], dtype=np.uint32)
    for i in range(n):
        out = (out << 8) | b[:, off + i].astype(np.uint32)
    return out


def _crc8_table():
    table = np.zeros(256, dtype=np.uint8)
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
        table[i] = crc
    return table


_CRC8 = _crc8_table()


def crc8(data: bytes) -> int:
    """CRC-8, poly 0x07, init 0x00, no reflection (MAX30001 ECG frames)."""
    crc = 0
    for byte in data:
        crc = int(_CRC8[crc ^ byte])
    return crc


def _crc8_vec(b, start, length):
    """Same CRC over a byte range of every row, table-driven."""
    crc = np.zeros(b.shape[0], dtype=np.uint8)
    for i in range(length):
        crc = _CRC8[crc ^ b[:, start + i]]
    return crc


# ---------------------------------------------------------------------------
# decoders: (N, size) uint8 -> ({column: array}, malformed mask, info dict)
# ---------------------------------------------------------------------------

def _dtype_decoder(dtype):
    """Decoder for any layout expressible as a packed numpy structured dtype.

    Equivalent to struct.iter_unpack with the matching format string, but
    vectorized and with the column names attached to the layout itself.
    """
    def decode(b):
        rec = np.ascontiguousarray(b).view(dtype).reshape(-1)
        cols = {name: rec[name] for name in dtype.names}
        return cols, np.zeros(len(rec), dtype=bool), {}
    return decode


def _decode_packed16(b):
    """4x uint24 channel (19 meaningful bits) + uint32 512 Hz tick."""
    ir1, ir2, g1, g2 = (_le_uint(b, i, 3) for i in (0, 3, 6, 9))
    tick = _le_uint(b, 12, 4)
    malformed = ((ir1 | ir2 | g1 | g2) & PPG_PACKED_RESERVED_MASK) != 0
    cols = {"ir1": ir1, "ir2": ir2, "g1": g1, "g2": g2, "Counter": tick}
    return cols, malformed, {"reserved_bits": int(malformed.sum())}


def _decode_ecg(b):
    """12-byte framed MAX30001 protocol: sync + type + flags + seq + raw24 + crc8."""
    bad_sync = ~((b[:, 0] == 0xA5) & (b[:, 1] == 0xEC))
    bad_type = (b[:, 2] != 0x01) & ~bad_sync
    bad_crc = (_crc8_vec(b, 2, 9) != b[:, 11]) & ~bad_sync & ~bad_type

    raw = _be_uint(b, 8, 3)
    value = ((raw >> 6) & 0x3FFFF).astype(np.int32)
    value = np.where(value & (1 << 17), value - (1 << 18), value).astype(np.int32)

    cols = {
        "ECG": value,
        "ETAG": (b[:, 3] & 0x07).astype(np.uint8),
        "PTAG": ((b[:, 3] >> 3) & 0x07).astype(np.uint8),
        "Counter": _le_uint(b, 4, 4),
    }
    info = {"bad_sync": int(bad_sync.sum()),
            "bad_type": int(bad_type.sum()),
            "bad_crc": int(bad_crc.sum())}
    return cols, bad_sync | bad_type | bad_crc, info


_PPG_LEGACY_DT = np.dtype([(n, "<i4") for n in
                           ("ir1", "ir2", "g1", "g2", "Timestamp", "Counter")])
_PPG_V2_DT = np.dtype([(n, "<u4") for n in ("ir1", "ir2", "g1", "g2", "Counter")])
_AC_LEGACY_DT = np.dtype([("AccX", "<i2"), ("AccY", "<i2"), ("AccZ", "<i2"),
                          ("QuatX", "<f4"), ("QuatY", "<f4"), ("QuatZ", "<f4"),
                          ("ENMO", "<f4"), ("Timestamp", "<i4"), ("Counter", "<i4")])
_AC_V2_DT = np.dtype([("AccX", "<i2"), ("AccY", "<i2"), ("AccZ", "<i2"),
                      ("QuatX", "<f4"), ("QuatY", "<f4"), ("QuatZ", "<f4"),
                      ("ENMO", "<f4"), ("Counter", "<u4")])


# ---------------------------------------------------------------------------
# the spec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecordSpec:
    """One on-disk layout for one sensor.

    `since`/`until` bound the firmware range that writes it. `since=None` means
    the layout carries no version tie at all — that is the case for packed16,
    and it is why content detection exists rather than being an optimisation.
    """
    name: str
    sensor: str                 # "ppg" | "ac" | "ecg"
    size: int                   # bytes per record
    decode: Callable            # (N, size) uint8 -> (cols, malformed, info)
    tick_offset: int            # byte offset of the counter, for detection
    tick_rate: int              # Hz the counter advances at
    tick_step: int              # expected delta between consecutive records
    tick_bits: int = 32         # counter width; sets the rollover modulus
    erased: str = "counter_max"  # "counter_max" | "minus_one"
    trim_erased_tail: bool = False
    validated: bool = False     # has an independent integrity check beyond the tick
    since: tuple | None = None
    until: tuple | None = None

    @property
    def key(self):
        return f"{self.sensor}:{self.name}"

    @property
    def sample_rate(self):
        return self.tick_rate / self.tick_step

    @property
    def wrap(self):
        return 2 ** self.tick_bits

    def matches_version(self, version):
        """True when firmware `version` is documented to write this layout."""
        if self.since is None and self.until is None:
            return False        # not version-tagged; only content can find it
        if self.since is not None and version < self.since:
            return False
        if self.until is not None and version >= self.until:
            return False
        return True


REGISTRY = (
    RecordSpec("legacy", "ppg", 24, _dtype_decoder(_PPG_LEGACY_DT),
               tick_offset=20, tick_rate=320, tick_step=5, tick_bits=16,
               erased="minus_one", until=V2_VERSION),
    RecordSpec("v2", "ppg", 20, _dtype_decoder(_PPG_V2_DT),
               tick_offset=16, tick_rate=512, tick_step=2, since=V2_VERSION),
    RecordSpec("packed16", "ppg", PPG_PACKED_RECORD_SIZE, _decode_packed16,
               tick_offset=12, tick_rate=512, tick_step=2,
               trim_erased_tail=True, validated=True),

    RecordSpec("legacy", "ac", 30, _dtype_decoder(_AC_LEGACY_DT),
               tick_offset=26, tick_rate=320, tick_step=10, tick_bits=16,
               erased="minus_one", until=V2_VERSION),
    RecordSpec("v2", "ac", 26, _dtype_decoder(_AC_V2_DT),
               tick_offset=22, tick_rate=512, tick_step=16, since=V2_VERSION),

    RecordSpec("framed", "ecg", 12, _decode_ecg,
               tick_offset=4, tick_rate=512, tick_step=1,
               validated=True, since=V2_VERSION),
)

SENSORS = ("ppg", "ac", "ecg")


def specs_for(sensor):
    return tuple(s for s in REGISTRY if s.sensor == sensor)


def spec_names(sensor):
    return tuple(s.name for s in specs_for(sensor))


def get_spec(sensor, name):
    for s in REGISTRY:
        if s.sensor == sensor and s.name == name:
            return s
    raise ValueError(f"no {sensor} record format named {name!r}; "
                     f"known: {', '.join(spec_names(sensor))}")


def spec_for_version(sensor, version):
    """The layout `version` firmware is documented to write, or None."""
    for s in specs_for(sensor):
        if s.matches_version(version):
            return s
    return None


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def get_CDCT_init(file_path):
    """Reference timestamp encoded in the filename: <id><sensor><t0>.bin"""
    filename = os.path.basename(file_path)
    match = re.search(r'\d*[A-Za-z]+(\d+)\.bin$', filename)
    t0 = int(match.group(1)) if match else 0
    return t0, datetime.fromtimestamp(int(t0), UTC).strftime("%Y/%m/%d %H:%M:%S")


def whole_records(data, spec):
    """Reshape to whole records, dropping a trailing erased block if the spec says to.

    Only *complete trailing* erased records are trimmed — interior ones are kept
    so they surface in the malformed count instead of silently shifting every
    later record.
    """
    n = len(data) // spec.size
    b = np.frombuffer(data[: n * spec.size], dtype=np.uint8).reshape(-1, spec.size)
    if not spec.trim_erased_tail or b.shape[0] == 0:
        return b
    written = np.flatnonzero(~(b == 0xFF).all(axis=1))
    if written.size == 0:
        return b[:0]
    return b[: written[-1] + 1]


def read_bin(filepath, spec, strict=False):
    """Decode one binary file with `spec`. Returns (DataFrame, datetime string).

    Malformed records are dropped and counted; `strict` raises instead.
    """
    with open(filepath, "rb") as f:
        data = f.read()

    remainder = len(data) % spec.size
    if remainder:
        msg = (f"{os.path.basename(filepath)}: {len(data)} bytes is not divisible by "
               f"{spec.size}; {remainder} trailing byte(s) ignored")
        if strict:
            raise ValueError(msg)
        print(msg)

    b = whole_records(data, spec)
    if b.shape[0] == 0:
        raise ValueError("No valid records found in file.")

    cols, malformed, info = spec.decode(b)

    n_bad = int(malformed.sum())
    if n_bad:
        detail = ", ".join(f"{k}={v}" for k, v in info.items() if v)
        msg = (f"{spec.sensor.upper()} {os.path.basename(filepath)}: "
               f"{n_bad}/{len(malformed)} records failed validation ({detail})")
        if strict:
            raise ValueError(msg)
        print(msg + " — dropped")

    if n_bad:
        keep = ~malformed
        cols = {k: v[keep] for k, v in cols.items()}

    df = pd.DataFrame(cols)

    if spec.erased == "minus_one":
        # Pre-v4.7.0 firmware writes -1 into unused fields. Kept verbatim: it
        # also nulls genuine samples that happen to equal -1, but changing that
        # would alter every legacy CSV ever produced.
        df = df.replace(-1, np.nan).dropna(how='all')
    else:
        df = df[df['Counter'] != np.iinfo(np.uint32).max]

    if df.empty:
        raise ValueError(
            f"{os.path.basename(filepath)}: no usable records after decoding "
            f"{len(malformed)} {spec.size}-byte records ({n_bad} malformed). "
            f"Is this file really in the {spec.sensor}/{spec.name} format?")

    t0, dt = get_CDCT_init(filepath)

    counter = df['Counter'].to_numpy()
    if not np.issubdtype(counter.dtype, np.floating):
        counter = counter.astype(np.int64)
    counter_diff = np.diff(counter) % spec.wrap
    counter_diff = np.insert(counter_diff, 0, 0)
    df['CDCT'] = t0 + np.cumsum(counter_diff) / spec.tick_rate
    df['init_CDCT'] = t0

    df.attrs['malformed_records'] = n_bad
    df.attrs['trailing_bytes'] = remainder
    df.attrs['spec'] = spec.key

    return df, dt


# ---------------------------------------------------------------------------
# back-compat shims — the packed16 unit tests and older callers import these
# ---------------------------------------------------------------------------

PPG_PACKED16 = get_spec("ppg", "packed16")


def decode_ppg_packed16(data):
    """(ir1, ir2, g1, g2, tick, malformed) from raw packed-16 bytes."""
    b = whole_records(data, PPG_PACKED16)
    cols, malformed, _ = _decode_packed16(b)
    return (cols["ir1"], cols["ir2"], cols["g1"], cols["g2"],
            cols["Counter"], malformed)


def read_ppg_bin_packed16(filepath, strict=False):
    return read_bin(filepath, PPG_PACKED16, strict=strict)
