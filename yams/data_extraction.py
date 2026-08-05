# original credit: https://github.com/SenSE-Lab-OSU/MotionSenseHRV4Flash/blob/main/DataExtraction/data_extraction.py
import os
import sys
import struct
import re
import datetime
import traceback
import argparse
import pandas as pd
import numpy as np
import numpy
from datetime import datetime, UTC
import gradio as gr
import zipfile
import tempfile
from glob import glob
import shutil
from tqdm import tqdm

def get_participant_ids(folder_path):
    prefixes = set()
    for filename in os.listdir(folder_path):
        if not filename.endswith(".bin"):
            continue

        match = re.match(r"(\d*)ppg\d+\.bin$", filename)
        if match:
            prefix = match.group(1)
            if prefix == "":
                prefixes.add('')  
            else:
                prefixes.add(str(prefix))
    return sorted(prefixes, key=lambda x: (x is None, x))

def get_device_version(folder_path):
    uuid_path = os.path.join(folder_path, "uuid.txt")
    if not os.path.exists(uuid_path):
        return (0, 0, 0)
    with open(uuid_path, 'r') as f:
        content = f.read()
    match = re.search(r'Version:\s*(\d+)\.(\d+)\.(\d+)', content)
    if match:
        return tuple(int(x) for x in match.groups())
    return (0, 0, 0)

def get_CDCT_init(file_path):
    filename = os.path.basename(file_path)
    pattern = r'\d*[A-Za-z]+(\d+)\.bin$'
    match = re.search(pattern, filename)
    
    t0 = 0
    if match:
        t0 = int(match.group(1))

    return t0, datetime.fromtimestamp(int(t0), UTC).strftime("%Y/%m/%d %H:%M:%S")

def read_ppg_bin(filepath):
    labels = ["ir1", "ir2", "g1", "g2", "Timestamp", "Counter"]
    record_format = "<6i"       
    record_size = struct.calcsize(record_format)

    with open(filepath, "rb") as f:
        data = f.read()

    n_records = len(data) // record_size
    data = data[: n_records * record_size]

    if n_records == 0:
        raise ValueError("No valid records found in file.")

    records = struct.iter_unpack(record_format, data)
    arr = np.array(list(records), dtype=np.int32)

    df = pd.DataFrame(arr, columns=labels)
    df = df.replace(-1, np.nan).dropna(how='all')

    t0, dt = get_CDCT_init(filepath)

    counter_diff = np.diff(df['Counter']) % (2^16 - 1)
    counter_diff = np.insert(counter_diff, 0, 0)
    df['CDCT'] = t0 + np.cumsum(counter_diff) / 320
    df['init_CDCT'] = t0

    return df, dt

def read_ppg_bin_v2(filepath):
    """v4.7.0+: 4x uint32 ppg + uint32 global_tick_512hz, no Timestamp field."""
    labels = ["ir1", "ir2", "g1", "g2", "Counter"]
    record_format = "<5I"
    record_size = struct.calcsize(record_format)

    with open(filepath, "rb") as f:
        data = f.read()

    n_records = len(data) // record_size
    data = data[: n_records * record_size]

    if n_records == 0:
        raise ValueError("No valid records found in file.")

    records = struct.iter_unpack(record_format, data)
    arr = np.array(list(records), dtype=np.uint32)

    df = pd.DataFrame(arr, columns=labels)
    df = df[df['Counter'] != np.iinfo(np.uint32).max]

    t0, dt = get_CDCT_init(filepath)

    counter_diff = np.diff(df['Counter'].astype(np.int64)) % (2**32)
    counter_diff = np.insert(counter_diff, 0, 0)
    df['CDCT'] = t0 + np.cumsum(counter_diff) / 512
    df['init_CDCT'] = t0

    return df, dt

# ---------------------------------------------------------------------------
# Packed 16-byte PPG record — see data/PPG_PACKED_16_BYTE_FORMAT.md
#
# Not tied to a device version: firmware carrying this format is identified by
# the operator, not by uuid.txt, so it is selected with an explicit toggle.
# ---------------------------------------------------------------------------
PPG_PACKED_RECORD_SIZE = 16
PPG_PACKED_SAMPLE_MASK = 0x7FFFF
PPG_PACKED_RESERVED_MASK = 0xFFF80000   # bits 19..31 must be clear in every channel

PPG_FORMAT_CHOICES = ["auto", "legacy", "v2", "packed16", "sniff"]

PPG_FORMAT_HELP = """## Data extraction pro mode

### PPG record format

| Choice | Record | Meaning |
|---|---|---|
| `auto` | — | Follow `uuid.txt` (v4.7.0+ → `v2`, otherwise `legacy`). Default. |
| `legacy` | 24 B | `6x int32`: ir1, ir2, g1, g2, Timestamp, Counter @ 320 Hz |
| `v2` | 20 B | `5x uint32`: ir1, ir2, g1, g2, global tick @ 512 Hz |
| `packed16` | 16 B | `4x uint24` channels + `uint32` global tick @ 512 Hz (experimental) |
| `sniff` | — | Detect from file contents; falls back to `auto` if inconclusive |

`packed16` firmware carries no distinguishing version number, so it has to be
selected explicitly (or sniffed). It only affects PPG — IMU and ECG still follow
the device version / "Force v4.7.0+ format" checkbox.

The tick is written to the `Counter` column for every format, so Clock Sync
works on `packed16` output unchanged.

**Strict PPG validation**: raise on a record whose reserved channel bits are set
(or on a partial trailing record) instead of dropping it and reporting a count.
"""


def _u24_le(cols):
    """Assemble little-endian uint24 from an (N, 3) uint8 array."""
    return (cols[:, 0].astype(np.uint32)
            | cols[:, 1].astype(np.uint32) << 8
            | cols[:, 2].astype(np.uint32) << 16)


def _u32_le(cols):
    """Assemble little-endian uint32 from an (N, 4) uint8 array."""
    return (cols[:, 0].astype(np.uint32)
            | cols[:, 1].astype(np.uint32) << 8
            | cols[:, 2].astype(np.uint32) << 16
            | cols[:, 3].astype(np.uint32) << 24)


def _ppg_packed_records(data):
    """Whole records only, with the trailing erased block removed.

    NAND files may end with preallocated all-0xFF records. Only complete
    trailing erased records are trimmed — interior ones are kept so they show up
    in the malformed count instead of silently shifting every later record.
    """
    n_records = len(data) // PPG_PACKED_RECORD_SIZE
    b = np.frombuffer(data[: n_records * PPG_PACKED_RECORD_SIZE], dtype=np.uint8)
    b = b.reshape(-1, PPG_PACKED_RECORD_SIZE)

    if b.shape[0] == 0:
        return b

    written = np.flatnonzero(~(b == 0xFF).all(axis=1))
    if written.size == 0:
        return b[:0]
    return b[: written[-1] + 1]


def decode_ppg_packed16(data):
    """Vectorized decode of the packed 16-byte PPG record.

    Layout, all little-endian: 4x uint24 channel (ir1, ir2, g1, g2) followed by
    the uint32 512 Hz global tick. Channels carry 19 meaningful bits.

    Returns (ir1, ir2, g1, g2, tick, malformed) — five uint32 arrays plus a bool
    mask marking records whose reserved channel bits are set.
    """
    b = _ppg_packed_records(data)
    ir1, ir2, g1, g2 = (_u24_le(b[:, i:i + 3]) for i in (0, 3, 6, 9))
    tick = _u32_le(b[:, 12:16])
    malformed = ((ir1 | ir2 | g1 | g2) & PPG_PACKED_RESERVED_MASK) != 0
    return ir1, ir2, g1, g2, tick, malformed


def read_ppg_bin_packed16(filepath, strict=False):
    """Packed 16-byte PPG record: 4x uint24 channel + uint32 global_tick_512hz.

    The tick is exposed as 'Counter' to match the rest of the pipeline (the
    Clock Sync tab and counter_validity_check both key on that name); it is the
    same 512 Hz tick the v4.7.0+ format carries.

    Malformed records are dropped and reported by default; strict=True raises.
    """
    with open(filepath, "rb") as f:
        data = f.read()

    remainder = len(data) % PPG_PACKED_RECORD_SIZE
    if remainder:
        msg = (f"PPG {os.path.basename(filepath)}: {len(data)} bytes is not divisible by "
               f"{PPG_PACKED_RECORD_SIZE}; {remainder} trailing byte(s) ignored")
        if strict:
            raise ValueError(msg)
        print(msg)

    ir1, ir2, g1, g2, tick, malformed = decode_ppg_packed16(data)

    if len(ir1) == 0:
        raise ValueError("No valid records found in file.")

    n_bad = int(malformed.sum())
    if n_bad:
        msg = (f"PPG {os.path.basename(filepath)}: {n_bad}/{len(malformed)} records have "
               f"nonzero reserved channel bits")
        if strict:
            raise ValueError(msg)
        print(msg + " — dropped")

    keep = ~malformed
    df = pd.DataFrame({
        "ir1": ir1[keep],
        "ir2": ir2[keep],
        "g1": g1[keep],
        "g2": g2[keep],
        "Counter": tick[keep],
    })
    df = df[df['Counter'] != np.iinfo(np.uint32).max]

    if df.empty:
        # Wrong layout selected, or a wholly corrupt file: say so instead of
        # emitting a single all-NaN row.
        raise ValueError(
            f"{os.path.basename(filepath)}: no usable records after decoding "
            f"{len(malformed)} packed 16-byte records ({n_bad} malformed). "
            "Is this file really in the packed 16-byte PPG format?")

    t0, dt = get_CDCT_init(filepath)

    counter_diff = np.diff(df['Counter'].astype(np.int64)) % (2**32)
    counter_diff = np.insert(counter_diff, 0, 0)
    df['CDCT'] = t0 + np.cumsum(counter_diff) / 512
    df['init_CDCT'] = t0

    df.attrs['malformed_records'] = n_bad
    df.attrs['trailing_bytes'] = remainder

    return df, dt


def sniff_ppg_format(filepath, n_probe=2000, threshold=0.9):
    """Guess a PPG file's record layout from its contents.

    There is no version number to key the packed format on, so the fallback is
    to test each layout against the file: read the tick field at the offset that
    layout implies and see whether it advances at the expected rate. The packed
    hypothesis is additionally disqualified if any channel's reserved bits are
    set. Returns the winning format name, or None if nothing scored above
    `threshold` (caller should fall back to the version-based choice).
    """
    with open(filepath, "rb") as f:
        data = f.read(n_probe * 24)

    def score(record_size, tick_slice, expected_step, check_reserved=False):
        n = len(data) // record_size
        if n < 3:
            return 0.0
        b = np.frombuffer(data[: n * record_size], dtype=np.uint8).reshape(n, record_size)
        b = b[~(b == 0xFF).all(axis=1)]   # erased records say nothing about the layout
        if b.shape[0] < 3:
            return 0.0
        tick = _u32_le(b[:, tick_slice])
        delta = np.diff(tick.astype(np.int64)) % (2**32)
        s = float(np.mean(delta == expected_step))
        if check_reserved:
            # Scale by the share of clean records rather than disqualifying on a
            # single set bit, so one corrupt record can't veto the right answer.
            channels = np.stack([_u24_le(b[:, i:i + 3]) for i in (0, 3, 6, 9)])
            s *= float(np.mean((channels & PPG_PACKED_RESERVED_MASK) == 0))
        return s

    scores = {
        "packed16": score(PPG_PACKED_RECORD_SIZE, slice(12, 16), 2, check_reserved=True),
        "v2":       score(20, slice(16, 20), 2),
        "legacy":   score(24, slice(20, 24), 5),
    }
    print("PPG format sniff: " + ", ".join(f"{k}={v:.3f}" for k, v in scores.items()))

    best = max(scores, key=scores.get)
    return best if scores[best] >= threshold else None


def read_ac_bin_v2(filepath):
    """v4.7.0+: 3x int16 accel + 3x float32 (quaternion, reported as GyroX/Y/Z) + float32 enmo + uint32 global_tick_512hz, no Timestamp field."""
    labels = ["AccX", "AccY", "AccZ", "QuatX", "QuatY", "QuatZ", "ENMO", "Counter"]

    record_format = "<3h4fI"
    record_size = struct.calcsize(record_format)

    with open(filepath, "rb") as f:
        data = f.read()

    n_records = len(data) // record_size
    data = data[: n_records * record_size]

    if n_records == 0:
        raise ValueError("No valid records found in file.")

    records = struct.iter_unpack(record_format, data)
    arr = list(records)

    dtype = np.dtype([
        ("AccX", np.int16), ("AccY", np.int16), ("AccZ", np.int16),
        ("QuatX", np.float32), ("QuatY", np.float32), ("QuatZ", np.float32),
        ("ENMO", np.float32), ("Counter", np.uint32),
    ])

    arr = np.array(arr, dtype=dtype)
    df = pd.DataFrame(arr)
    df = df[df['Counter'] != np.iinfo(np.uint32).max]

    t0, dt = get_CDCT_init(filepath)

    counter_diff = np.diff(df['Counter'].astype(np.int64)) % (2**32)
    counter_diff = np.insert(counter_diff, 0, 0)
    df['CDCT'] = t0 + np.cumsum(counter_diff) / 512
    df['init_CDCT'] = t0

    return df, dt

def _crc8_ecg(data: bytes) -> int:
    """CRC-8 poly=0x07, init=0x00, no reflection — used for MAX30001 ECG frame validation."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc

def read_ecg_bin(filepath):
    """MAX30001 ECG: 12-byte framed protocol with sync word + CRC-8 validation.

    Frame layout: [0xA5, 0xEC, type, flags, seq(4B LE), raw24(3B MSB), crc8]
    ECG value: signed 18-bit from raw24 bits [23:6].
    Counter (seq) increments at 512 Hz.
    """
    FRAME_SIZE = 12
    SYNC = b"\xA5\xEC"
    TYPE_SAMPLE = 0x01

    with open(filepath, "rb") as f:
        data = f.read()

    complete_bytes = (len(data) // FRAME_SIZE) * FRAME_SIZE
    n_frames = complete_bytes // FRAME_SIZE
    data = data[:complete_bytes]

    if n_frames == 0:
        raise ValueError("No complete ECG frames found in file.")

    seqs, ecg_vals, etags, ptags = [], [], [], []
    bad_sync = bad_type = bad_crc = 0

    for i in range(n_frames):
        frame = data[i * FRAME_SIZE : (i + 1) * FRAME_SIZE]
        if frame[:2] != SYNC:
            bad_sync += 1
            continue
        if frame[2] != TYPE_SAMPLE:
            bad_type += 1
            continue
        if _crc8_ecg(frame[2:11]) != frame[11]:
            bad_crc += 1
            continue
        seq = int.from_bytes(frame[4:8], "little")
        raw_word = int.from_bytes(frame[8:11], "big")
        value = (raw_word >> 6) & 0x3FFFF
        if value & (1 << 17):
            value -= 1 << 18
        seqs.append(seq)
        ecg_vals.append(value)
        etags.append(frame[3] & 0x07)
        ptags.append((frame[3] >> 3) & 0x07)

    print(f"ECG {os.path.basename(filepath)}: {n_frames} frames, "
          f"bad_sync={bad_sync}, bad_type={bad_type}, bad_crc={bad_crc}")

    df = pd.DataFrame({
        "ECG":     np.array(ecg_vals, dtype=np.int32),
        "ETAG":    np.array(etags, dtype=np.uint8),
        "PTAG":    np.array(ptags, dtype=np.uint8),
        "Counter": np.array(seqs, dtype=np.uint32),
    })

    df = df[df['Counter'] != np.iinfo(np.uint32).max]

    t0, dt = get_CDCT_init(filepath)

    counter_diff = np.diff(df['Counter'].astype(np.int64)) % (2**32)
    counter_diff = np.insert(counter_diff, 0, 0)
    df['CDCT'] = t0 + np.cumsum(counter_diff) / 512
    df['init_CDCT'] = t0

    return df, dt

def read_ac_bin(filepath):
    labels = [
        "AccX", "AccY", "AccZ",
        "QuatX", "QuatY", "QuatZ",
        "ENMO", "Timestamp", "Counter"
    ]

    record_format = "<3h4f2i"
    record_size = struct.calcsize(record_format)

    with open(filepath, "rb") as f:
        data = f.read()

    n_records = len(data) // record_size
    data = data[: n_records * record_size]

    if n_records == 0:
        raise ValueError("No valid records found in file.")

    records = struct.iter_unpack(record_format, data)
    arr = list(records)

    dtype = np.dtype([
        ("AccX", np.int16), ("AccY", np.int16), ("AccZ", np.int16),
        ("QuatX", np.float32), ("QuatY", np.float32), ("QuatZ", np.float32),
        ("ENMO", np.float32), ("Timestamp", np.int32), ("Counter", np.int32),
    ])

    arr = np.array(arr, dtype=dtype)
    df = pd.DataFrame(arr)
    df = df.replace(-1, np.nan).dropna(how='all')

    t0, dt = get_CDCT_init(filepath)

    counter_diff = np.diff(df['Counter']) % (2^16 - 1)
    counter_diff = np.insert(counter_diff, 0, 0)
    df['CDCT'] = t0 + np.cumsum(counter_diff) / 320
    df['init_CDCT'] = t0

    return df, dt

def data_extraction_pro_interface():
    in_file = gr.File(file_types=[".zip"])
    with gr.Row():
        force_new_format = gr.Checkbox(False, label="Force v4.7.0+ format")
        ppg_format = gr.Dropdown(PPG_FORMAT_CHOICES, value="auto", label="PPG record format",
                                 info="auto = follow device version; packed16 = 16-byte packed (experimental)")
        strict_ppg = gr.Checkbox(False, label="Strict PPG validation")
    out = gr.DownloadButton(label="No data to be downloaded", interactive=False)
    in_file.change(lambda f, fnf, pf, sp: extract_zip(f, force_new_format=fnf, ppg_format=pf, strict_ppg=sp),
                   inputs=[in_file, force_new_format, ppg_format, strict_ppg], outputs=out)
    with gr.Accordion(label="Help", open=False):
        gr.Markdown(PPG_FORMAT_HELP)

def batch_extract_zips(in_path, save_format="csv", ignore_id_parsing=False, ppg_format="auto", strict_ppg=False):
    zips = glob(os.path.join(in_path, "*.zip"))
    print(zips)
    for z in tqdm(zips):
        extract_zip(z, cli_mode=True, out_dir=os.path.join(in_path, "out"), save_format=save_format, ignore_id_parsing=ignore_id_parsing, ppg_format=ppg_format, strict_ppg=strict_ppg)

def extract_zip(zip_path, cli_mode=False, out_dir="./data", save_format="csv", ignore_id_parsing=False, force_new_format=False, ppg_format="auto", strict_ppg=False):
    df = get_session_encoding()
    if zip_path is not None:
        with tempfile.TemporaryDirectory() as tmpdir:
            print(zip_path)
            print(tmpdir)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)

            devices = os.listdir(tmpdir)
            for dev in devices:
                in_dir = os.path.join(tmpdir, dev)
                main(in_dir, in_dir, legacy_fs=False, df=df, note=dev, gradio=False, save_format=save_format, ignore_id_parsing=ignore_id_parsing, force_new_format=force_new_format, ppg_format=ppg_format, strict_ppg=strict_ppg)
                
            out_zip_path = os.path.join(tempfile.gettempdir(),
                                    os.path.basename(zip_path).replace('.zip', '_extracted.zip'))
            
            with zipfile.ZipFile(out_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(tmpdir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, start=tmpdir)
                        zipf.write(file_path, arcname)

            if cli_mode:
                os.makedirs(out_dir, exist_ok=True)
                shutil.copy(out_zip_path, os.path.join(out_dir, os.path.basename(out_zip_path)))
        return gr.DownloadButton(label="🎉Download data", value=out_zip_path, interactive=True)
    else:
        return gr.DownloadButton(label="No data to be downloaded", interactive=False)

def get_session_encoding():
    if os.path.exists("./yams-data/session_table.csv"):
            df = pd.read_csv("./yams-data/session_table.csv")
    else:
        df = pd.DataFrame(data={
            'subject_id': ["sub-Test"],
            "session_id": ["ses-01"],
            "encoding": [123]
        })
    return df

def data_extraction_interface():
    # in_files = gr.File(file_count="multiple")
    in_dir = gr.Text("/path/to/binary/data", label="Input directory")
    out_dir = gr.Text("/path/to/output", label="Output directory")

    note = gr.Text("", label="Note")

    legacy_fs = gr.Checkbox(False, label="(Uncommon) legacy sampling rate")

    with gr.Row():
        save_format = gr.Radio(["csv", "pickle"], value="csv", label="Save format")
        ignore_id = gr.Checkbox(False, label="Ignore subject/session ID parsing")
        force_new_format = gr.Checkbox(False, label="Force v4.7.0+ format")

    with gr.Row():
        ppg_format = gr.Dropdown(PPG_FORMAT_CHOICES, value="auto", label="PPG record format",
                                 info="auto = follow device version; packed16 = 16-byte packed (experimental)")
        strict_ppg = gr.Checkbox(False, label="Strict PPG validation")

    btn = gr.Button("Extract raw data")

    with gr.Accordion("Encoding mapping"):
        df = get_session_encoding()
        dataframe = gr.DataFrame(value=df)

    gradio_state = gr.State(True)
    btn.click(main, inputs=[in_dir, out_dir, legacy_fs, dataframe, note, gradio_state, save_format, ignore_id, force_new_format, ppg_format, strict_ppg])

class DataExtractor():
    def __init__(self, in_dir, out_dir, legacy_fs=False, df=None, note="", save_format="csv", ignore_id_parsing=False, force_new_format=False, ppg_format="auto", strict_ppg=False):
        self.device_version = get_device_version(in_dir)
        self.use_new_format = force_new_format or (self.device_version >= (4, 7, 0))
        print(f"device version: {'.'.join(str(x) for x in self.device_version)}, new format: {self.use_new_format} (forced: {force_new_format})")

        # PPG layout is its own axis: the packed 16-byte format carries no version
        # number, so it cannot ride on use_new_format (which still drives IMU).
        self.requested_ppg_format = ppg_format
        self.strict_ppg = strict_ppg
        if ppg_format in ("auto", "sniff"):
            self.ppg_format = "v2" if self.use_new_format else "legacy"
        else:
            self.ppg_format = ppg_format
        self._ppg_format_resolved = ppg_format != "sniff"
        self.ppg_malformed = 0
        self.ppg_files_read = 0
        print(f"ppg format: {self.requested_ppg_format} -> {self.ppg_format}, strict: {strict_ppg}")

        if legacy_fs:
            self.sample_tick = 200
        else:
            self.sample_tick = 320

        self.note = note
        self.df = df
        self.save_format = save_format
        self.ignore_id_parsing = ignore_id_parsing

        if self.df is not None:
            self.encoding_alias = self.get_encoding_alias()
        else:
            self.encoding_alias = {}

        print(f"sampling tick set to {self.sample_tick}")

        self.in_dir = in_dir
        self.out_dir = out_dir

        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(self.out_dir, "README.txt"), "w") as file:
            file.write(f"Raw data directory = {self.in_dir}\n")
            file.write(f"Legacy sampling rate = {legacy_fs} (True: 25 Hz, False: 32 Hz)\n")
            file.write(f"Save format = {save_format}\n")
            file.write(f"Ignore subject/session ID parsing = {ignore_id_parsing}\n")
            file.write(f"PPG record format = {ppg_format} (requested)\n")
            file.write(f"Strict PPG record validation = {strict_ppg}\n")
            file.write(f"I m-sense with YAMS at https://github.com/SenSE-Lab-OSU/YAMS\n")
            uuid_path = os.path.join(in_dir, "uuid.txt")
            if os.path.exists(uuid_path):
                file.write("\n--- Device info (uuid.txt) ---\n")
                with open(uuid_path, "r") as uuid_file:
                    file.write(uuid_file.read())

        self.ppg_labels = ["ir1", "ir2", "g1", "g2",  "Timestamp", "Counter"]
        self.ppg_formats = ["<i", "<i", "<i", "<i", "<i", "<i"]

        self.acc_labels = ["AccX", "AccY", "AccZ", "QuatX", "QuatY", "QuatZ", "ENMO", "Timestamp", "Counter"]
        self.acc_formats = ["<h", "<h", "<h", "<f", "<f", "<f", "<f", "<i", "<i"]

        self.ecg_labels = ["ECG", "ETAG", "PTAG", "Counter"]

    @property
    def ppg_512hz_tick(self):
        """True when the PPG Counter is the 512 Hz global tick (step 2), not the legacy 320 Hz one."""
        return self.ppg_format in ("v2", "packed16")

    def get_encoding_alias(self):
        alias_dict = {}
        for i in range(len(self.df.index)):
            curr = self.df.iloc[i]
            alias_dict[f"{curr['encoding']}"] = f"{curr['subject_id']}_{curr['session_id']}_{self.note}_{curr['encoding']}"
        return alias_dict

    def run(self):
        ids = self.obtain_predix_ids()
        for id in ids:
            search_prefix = id + "ac"
            file_name = search_prefix + (".pkl" if self.save_format == "pickle" else ".csv")
            self.extract_csv(search_prefix, file_name, self.acc_labels, self.acc_formats, id=id)

            search_prefix = id + "ppg"
            file_name = search_prefix + (".pkl" if self.save_format == "pickle" else ".csv")
            self.extract_csv(search_prefix, file_name, self.ppg_labels, self.ppg_formats, id=id)

            search_prefix = id + "ecg"
            file_name = search_prefix + (".pkl" if self.save_format == "pickle" else ".csv")
            self.extract_csv(search_prefix, file_name, self.ecg_labels, formats=None, id=id)

        self.write_ppg_provenance()

    def write_ppg_provenance(self):
        """Append the resolved PPG layout to README.txt.

        With no version number in uuid.txt to identify these files later, this is
        the only record of how the CSVs were decoded.
        """
        if self.ppg_files_read == 0:
            return
        with open(os.path.join(self.out_dir, "README.txt"), "a") as file:
            file.write("\n--- PPG decode ---\n")
            file.write(f"Resolved PPG record format = {self.ppg_format}\n")
            file.write(f"PPG files read = {self.ppg_files_read}\n")
            file.write(f"Malformed PPG records dropped = {self.ppg_malformed}\n")

    def read_ppg(self, full_path):
        if not self._ppg_format_resolved:
            guess = sniff_ppg_format(full_path)
            self._ppg_format_resolved = True
            if guess is None:
                print(f"PPG sniff inconclusive; falling back to {self.ppg_format}")
            else:
                print(f"sniffed PPG format: {guess}")
                self.ppg_format = guess

        self.ppg_files_read += 1
        if self.ppg_format == "packed16":
            df, dt = read_ppg_bin_packed16(full_path, strict=self.strict_ppg)
            self.ppg_malformed += df.attrs.get('malformed_records', 0)
            return df, dt
        if self.ppg_format == "v2":
            return read_ppg_bin_v2(full_path)
        return read_ppg_bin(full_path)

    def extract_csv(self, search_prefix, file_name, labels, formats, id=-1):
        self.generate_csv_for_pattern(self.in_dir, file_name, search_prefix, labels, formats, out_dir=self.out_dir, id=id)

    def generate_csv_for_pattern(self, in_dir, type_prefix: str, search_key: str, labels, formats, out_dir="./", id=-1):
        # 1. Ignore ID Parsing Handling
        if self.ignore_id_parsing:
            file_name = type_prefix # Defaults to id + "ac.csv" or ".pkl"
        else:
            if str(id) in self.encoding_alias.keys():
                alias = self.encoding_alias[str(id)]
                print('=====', id, alias)
                file_name = f"{type_prefix}".replace(id, alias)
            else:   
                sub_id = str(id)[:-2]
                ses_id = str(id)[-2:]
                alias = f"sub-{sub_id}_ses-{ses_id}_{self.note}_"
                file_name = f"{type_prefix}".replace(id, alias)

        print(type_prefix, search_key, labels, formats, '********')
        data_set = self.collect_all_data_by_prefix(in_dir, search_key, labels, formats)
        
        if data_set is not None:
            os.makedirs(out_dir, exist_ok=True)
            # PPG counter semantics follow the PPG layout, which may differ from
            # the version-derived format used by the IMU/ECG paths.
            new_format_counter = self.ppg_512hz_tick if 'ppg' in search_key else self.use_new_format
            counter_validity_check(data_set, use_new_format=new_format_counter)

            try:
                dt = [datetime.fromtimestamp(int(t), UTC).strftime("%Y/%m/%d %H:%M:%S") for t in data_set['CDCT']]
            except Exception as e:
                print(str(e))

                dt = -1
            data_set['Datetime'] = dt

            if 'ac' in search_key:
                print("perform unit conversion for IMU")
                data_set = unit_conversion_ac(data_set)

            # 2. Save Format Handling
            out_path = os.path.join(out_dir, file_name)
            if self.save_format == "pickle":
                data_set.to_pickle(out_path)
            else:
                data_set.to_csv(out_path, index=False)

    def collect_all_data_by_prefix(self, path, prefix: str, labels: list[str], types: list[str]):
        files = gather_files_by_prefix(prefix, path)  
        if len(files) == 0: return None
        
        all_df = []
        for file in files:
            full_path = os.path.join(path, file)
            if 'ppg' in file:
                df, dt = self.read_ppg(full_path)
            elif 'ecg' in file:
                df, dt = read_ecg_bin(full_path)
            elif 'ac' in file:
                df, dt = read_ac_bin_v2(full_path) if self.use_new_format else read_ac_bin(full_path)
            else:
                continue
            all_df.append(df)

        return pd.concat(all_df)

    def obtain_predix_ids(self):
        all_files = [""]
        files = os.listdir(self.in_dir)
        for file in files:
            if file[0].isdigit():
                id = re.search(r'\d+', file)
                if id is not None:
                    id = id.group()
                    if id not in all_files:
                        all_files.append(id)
        return all_files
    
def file_sort(element1: str):
    numeric_index = element1.find(it_prefix)
    numeric_time = element1[numeric_index + len(it_prefix):len(element1)]
    return int(re.sub("\D", "", numeric_time))

def gather_files_by_prefix(prefix: str, path):
    global it_prefix
    it_prefix = prefix
    all_files = []
    files = os.listdir(path)
    for file in files:
        if file.startswith(prefix) and file.endswith('.bin'):
            all_files.append(file)
    all_files.sort(key=file_sort)
    return all_files

def counter_validity_check(df: pd.DataFrame, use_new_format=False):
    # The readers append CDCT/init_CDCT, so the last column is not the counter.
    counter_columns = df[['Counter']] if 'Counter' in df.columns else df.iloc[:, -1:]
    counter_arr = numpy.array(counter_columns).flatten()
    diff_arr = numpy.diff(counter_arr)
    if use_new_format:
        positive_diffs = diff_arr[diff_arr > 0]
        if len(positive_diffs) == 0:
            print("pass counter check: N/A (no positive diffs)")
            return
        expected_step = int(numpy.median(positive_diffs))
        check_array = (diff_arr == expected_step) | (diff_arr == expected_step * 2) | (diff_arr > 2**31)
    else:
        check_array = (diff_arr == 5) | (diff_arr == 10) | (diff_arr < -65000)
    print("pass counter check: " + str(numpy.all(check_array)))
    print("and number of non matching samples: " + str(numpy.count_nonzero(check_array == 0)))

def unit_conversion_ac(data_set):
    for c in ['AccX', 'AccY', 'AccZ']:
        data_set[c] = data_set[c] /(2**16-1)*8
    return data_set

def get_t0(file_list):
    pattern = r'\d*[A-Za-z]+(\d+)\.bin$'
    t = sorted([int(match.group(1)) for filename in file_list if (match := re.search(pattern, filename))])
    return t[0]

def get_cdct(df, bin_list, fs=320):
    t0 = get_t0(bin_list)
    counter_diff = np.diff(df['Counter']) % (2^16 - 1)
    counter_diff = np.insert(counter_diff, 0, 0)
    df['CDCT'] = t0 + np.cumsum(counter_diff) / fs
    return df

def main(in_dir, out_dir, legacy_fs=False, df=None, note="", gradio=True, save_format="csv", ignore_id_parsing=False, force_new_format=False, ppg_format="auto", strict_ppg=False):
    extractor = DataExtractor(in_dir, out_dir, legacy_fs=legacy_fs, df=df, note=note, save_format=save_format, ignore_id_parsing=ignore_id_parsing, force_new_format=force_new_format, ppg_format=ppg_format, strict_ppg=strict_ppg)
    extractor.run()
    if df is not None: print(df.head())
    if gradio: gr.Info("✅ Extraction completed")
    print("operation completed.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--in_dir', type=str, required=True, help="directory where binary files are located")
    parser.add_argument('-o', '--out_dir', type=str, default="./", help="output directory")
    parser.add_argument('--legacy_fs', action='store_true', default=False, help="Use legacy sampling rate 25Hz for CDCT")
    
    # 3. New Command Line Arguments
    parser.add_argument('--save_format', type=str, choices=['csv', 'pickle'], default='csv', help="Format to save extracted data (csv or pickle)")
    parser.add_argument('--ignore_id', action='store_true', default=False, help="Ignore subject and session ID parsing for file names")
    parser.add_argument('--mode', type=str, choices=['dir', 'batch'], default='dir', help="Run mode: 'dir' for single directory of bins, 'batch' for folder of zips")
    parser.add_argument('--force_new_format', action='store_true', default=False, help="Force v4.7.0+ extraction format regardless of uuid.txt version")

    # 4. PPG record layout (independent of the version-derived format above)
    parser.add_argument('--ppg_format', type=str, choices=PPG_FORMAT_CHOICES, default='auto',
                        help="PPG record layout: 'auto' follows uuid.txt, 'packed16' is the 16-byte "
                             "packed format (no version tie), 'sniff' detects it from file contents")
    parser.add_argument('--strict_ppg', action='store_true', default=False,
                        help="Raise on malformed PPG records instead of dropping and reporting them")

    args = parser.parse_args()

    if args.mode == 'batch':
        batch_extract_zips(args.in_dir, save_format=args.save_format, ignore_id_parsing=args.ignore_id, ppg_format=args.ppg_format, strict_ppg=args.strict_ppg)
    else:
        main(args.in_dir, args.out_dir, legacy_fs=args.legacy_fs, gradio=False, save_format=args.save_format, ignore_id_parsing=args.ignore_id, force_new_format=args.force_new_format, ppg_format=args.ppg_format, strict_ppg=args.strict_ppg)