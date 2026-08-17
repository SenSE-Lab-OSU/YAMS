# Data Extraction Feature

## Overview

The **Data Extraction** feature in **YAMS** is designed to convert raw binary sensor data into a human-readable CSV format. This tool simplifies the process of working with physiological (PPG) and motion (IMU) data by extracting and organizing them by subject.

## How It Works

The data extraction tool takes raw binary files as input and processes them into structured CSV files. Each subject’s PPG and IMU data are parsed separately. 


## How to Use

1. Open **YAMS**.
2. Navigate to the **🛠️ Data Extractor** tab.
3. In the **Input directory** field, specify the folder containing the raw binary files.
4. In the **Output directory** field, specify where the extracted CSV files should be saved.
5. Record formats are detected from file contents automatically — you normally do not need to set anything. Open **⚙️ Advanced extraction options** only to change save format, ID parsing, to force a specific layout, or to enable the `uuid.txt` cross-check.
6. Once all fields are completed, click the **Extract raw data** button to begin the process.


## Expected Input Structure

The input folder should contain raw binary files with filenames in the following format:

- `<subject_id>ppg<reference_timestamp>.bin` – for PPG data
- `<subject_id>ac<reference_timestamp>.bin` – for IMU (accelerometer) data

Each filename encodes the **subject ID** and a **reference timestamp**, which the extractor uses to group data accordingly. It is untypical but in some cases, **subject ID** can be empty. 

![File extraction illustration](src/file_extraction_illu.png)


## Output Format

The extractor generates one CSV file for each type of data per subject:

- For each unique `<subject_id>` in the input folder:
  - One **PPG** CSV file
  - One **Accelerometer** CSV file

### IMU csv data format

`<subject_id>ac.csv`

| Header    | Description                                                              | Unit             |
|-----------|--------------------------------------------------------------------------|------------------|
| `AccX`      | Accelerometer X-axis                                                     | `g`            |
| `AccY`      | Accelerometer Y-axis                                                     | `g`            |
| `AccZ`      | Accelerometer Z-axis                                                     | `g`            |
| `GyroX`     | Gyroscope X-axis                                                         | `float32`          |
| `GyroY`     | Gyroscope Y-axis                                                         | `float32`          |
| `GyroZ`     | Gyroscope Z-axis                                                         | `float32`          |
| `ENMO`      | Euclidean Norm Minus One                                                 | `n/a `             |
| `Timestamp` | (Reserved) Reference timestamp - for generic use please refer to CDCT    | `uint32`           |
| `Counter`   | (Reserved) Package counter                                                | `uint16`           |
| `CDCT`      | Calculated data collection time - time when the data is collected in UTC | `sec`              |
| `Datetime`  | Human readable date time in UTC                                          | `MM/DD/YYYY HH:MM` |

### PPG csv data format

`<subject_id>ppg.csv`

| Header    | Description                                                              | Unit             |
|-----------|--------------------------------------------------------------------------|------------------|
| `ir1`       | Infrared light #1                                                        | `uint32`           |
| `ir2`       | Infrared light #2                                                        | `uint32`           |
| `g1`        | Green light #1                                                           | `uint32`           |
| `g2`        | Green light #2                                                           | `uint32`           |
| `Timestamp` | (Reserved) Reference timestamp - for generic use please refer to CDCT    | `uint32`           |
| `Counter`   | (Reserved) Package counter                                                | `uint16`           |
| `CDCT`      | Calculated data collection time - time when the data is collected in UTC | `sec`              |
| `Datetime`  | Human readable date time in UTC                                          | `MM/DD/YYYY HH:MM` |


## On-disk format variants

Six record layouts exist across the three sensors. Every one is a fixed-size record repeated to the end of a preallocated flash partition, little-endian unless noted, with the unwritten tail left as `0xFF`.

### PPG — 3 variants

| Variant | Record | Fields, in order | Tick field | Tick rate | Sample rate | Tick step |
|---|---|---|---|---|---|---|
| `legacy` | 24 B (`<6i`) | `ir1`, `ir2`, `g1`, `g2`, `Timestamp`, `Counter` — all int32 | bytes 20–24 | 320 Hz | 64 Hz | 5 |
| `v2` | 20 B (`<5I`) | `ir1`, `ir2`, `g1`, `g2`, `Counter` — all uint32 | bytes 16–20 | 512 Hz | 256 Hz | 2 |
| `packed16` | 16 B | 4× uint24 channel (19 meaningful bits) + uint32 tick | bytes 12–16 | 512 Hz | 256 Hz | 2 |

`legacy` carries a per-record `Timestamp`; the two newer layouts drop it and keep only the free-running global tick. `packed16` (see `data/PPG_PACKED_16_BYTE_FORMAT.md`) additionally packs each channel into three bytes, so bits 19–31 of every channel must read as zero — that constraint is what makes it self-validating.

### IMU / accelerometer — 2 variants

| Variant | Record | Fields, in order | Tick field | Tick rate | Sample rate | Tick step |
|---|---|---|---|---|---|---|
| `legacy` | 30 B (`<3h4f2i`) | `AccX/Y/Z` int16, `QuatX/Y/Z` float32, `ENMO` float32, `Timestamp` int32, `Counter` int32 | bytes 26–30 | 320 Hz | 32 Hz | 10 |
| `v2` | 26 B (`<3h4fI`) | `AccX/Y/Z` int16, `QuatX/Y/Z` float32, `ENMO` float32, `Counter` uint32 | bytes 22–26 | 512 Hz | 32 Hz | 16 |

Both sample at 32 Hz; they differ in the clock the counter is expressed in, and in whether `Timestamp` is present. The IMU variant is chosen by device version / "Force v4.7.0+ format" — there is no per-sensor IMU selector.

### ECG — 1 variant

| Variant | Frame | Layout | Tick field | Tick rate | Sample rate | Tick step |
|---|---|---|---|---|---|---|
| framed | 12 B | `0xA5 0xEC` sync, `type` (0x01 = sample), `flags` (ETAG bits 0–2, PTAG bits 3–5), `seq` uint32 LE, `raw24` **big-endian**, `crc8` | bytes 4–8 | 512 Hz | 512 Hz | 1 |

The only self-describing format of the six: a sync word plus CRC-8 (poly 0x07, init 0x00) over bytes 2–10. The ECG sample is a signed 18-bit value taken from `raw24` bits 23:6. Note `raw24` is big-endian while `seq` is little-endian, inside the same frame.

### Erased and invalid records

| Layout | How an unwritten / invalid record is recognised |
|---|---|
| PPG `legacy`, IMU `legacy` | field value `-1` (row dropped only if *every* field is `-1`) |
| PPG `v2`, PPG `packed16`, IMU `v2`, ECG | `Counter` / `seq` == `0xFFFFFFFF` |
| PPG `packed16` | additionally: a whole record of `0xFF`, or any channel with bits 19–31 set |
| ECG | additionally: bad sync word, wrong type byte, or CRC-8 mismatch |

Only *complete trailing* erased records are trimmed in `packed16`; interior ones are kept so they surface in the malformed count rather than silently shifting every later record.

### Not a layout variant: `--legacy_fs`

The "(Uncommon) legacy sampling rate" checkbox / `--legacy_fs` flag is an assumed-rate switch, not a record layout. **It currently has no effect on the output** — `DataExtractor.sample_tick` is set from it and printed, but never read; all CDCT math uses the rate fixed by the record layout (320 Hz or 512 Hz). It is still recorded in `README.txt`.

## Choosing a record format

Each sensor has its own selector, and all three share one vocabulary:

| Choice | Behaviour |
|---|---|
| `auto` **(default)** | Detect from file contents, per file. Falls back to the device version if detection is inconclusive. |
| `version` | Follow `uuid.txt` only: v4.7.0+ → `v2`, otherwise `legacy`. The pre-1.6 behaviour; cannot ever select `packed16`. |
| `legacy` / `v2` / `packed16` / `framed` | Force that layout. |

Firmware carrying `packed16` has **no distinguishing version number**, which is why `auto` detects rather than trusting the version file.

Because resolution happens per file, one folder may legitimately contain captures in different layouts and each is decoded correctly.

The tick is written to the `Counter` column for every format, so the Clock Sync tab works on any of them unchanged. Records that fail their integrity check are dropped and reported; `--strict_ppg` / the "Strict record validation" checkbox raises instead.

### Provenance

`README.txt` in the output directory records the resolution of **every file**:

```
--- Format resolution ---
file                                   sens resolved  method    score  uuid      agrees
260624ac1782325153.bin                 ac   v2        sniffed   1.000  legacy    NO
260624ppg1782325153.bin                ppg  v2        sniffed   0.993  legacy    NO

Malformed records dropped = 0
uuid.txt conflicts = 2 (content used unless on_format_conflict=trust_uuid)
```

`method` is `sniffed` (from content), `version` (from `uuid.txt`) or `forced` (you named the layout). The `uuid` and `agrees` columns are filled in only with `--validate_with_uuid`. Since `packed16` carries no version number, for those files this table is the only record of how a CSV was decoded.

### In the UI

The selectors live in the **⚙️ Advanced extraction options** accordion, identical on all three tabs that can run an extraction: **🛠️ Data extractor**, **🛠️ Data extractor pro**, and **📂 File downloader** (where it appears only while "Extract data after download" is ticked). The accordion holds the three per-sensor format dropdowns, the `uuid.txt` cross-check and its conflict policy, strict validation, save format, subject/session ID parsing, and the legacy toggles — so every extraction surface offers the same settings.

## Detecting the format without `uuid.txt`

**All six variants are detectable from file contents alone.** `uuid.txt` is not required, and where the two disagree the contents are the more reliable source.

The reason is that every layout embeds a monotonic counter at a fixed offset that advances by a fixed step. Guessing the record size wrong misaligns that field, so it reads as noise. The test is therefore:

> For each candidate (record size, tick offset), read the uint32 at that offset in every record, skipping all-`0xFF` rows, and measure what fraction of consecutive differences equal the layout's expected step.

| Sensor | Candidate | Record size | Tick offset | Expected step |
|---|---|---|---|---|
| PPG | `legacy` | 24 | 20 | 5 |
| PPG | `v2` | 20 | 16 | 2 |
| PPG | `packed16` | 16 | 12 | 2 |
| IMU | `legacy` | 30 | 26 | 10 |
| IMU | `v2` | 26 | 22 | 16 |
| ECG | framed | 12 | 4 | 1 |

Two layouts add a second, independent check: `packed16` scales its score by the fraction of records with clean reserved bits, and ECG by the fraction of frames with a valid sync word and CRC-8.

### Measured separation

Scoring all six candidates against all 138 `.bin` files in `data/`:

- Every file was classified, none below the 0.90 threshold.
- Worst winning score: **0.977**. Best runner-up on any file: **0.011**.

That is roughly a 90× margin, so the choice is never close. A wrong record size does not merely score lower — it scores essentially zero, because a misaligned counter almost never advances by a constant.

### Where content beats `uuid.txt`

Nine files in `data/` are decoded incorrectly in `version` mode and correctly by `auto`:

- `260624/FE-DE-29-50-F0-32/` and fixture `03_v2_stale_uuid` — `uuid.txt` reports `4.6.3`, but both streams are v4.7.0+ layout. `version` mode reads 20-byte PPG records at a 24-byte stride: no error, no warning, and every field rotated one position per record. On the real capture that is 68,508 rows spanning a nonsensical 0.01 Hz; `auto` yields 82,209 rows at 256.8 Hz. The IMU goes from 8,736 rows at 0.01 Hz to 10,080 at exactly 32.00 Hz.
- Fixtures `04`–`08` — `uuid.txt` reports `4.7.0`, so `version` mode picks `v2`, but the PPG is `packed16`.

The reverse case never occurred: no file was misclassified by content while `uuid.txt` was right. That asymmetry is why `auto` is the default and `--validate_with_uuid` reports rather than overrides.

### Current limits

Detection is applied to all three sensors, per file. Two limits remain: it needs at least 4 written records to mean anything, so a near-empty capture falls back to the version-based choice; and a folder with no `uuid.txt` **and** an undetectable file has nothing left to go on, in which case the fallback assumes `legacy` unless `--force_new_format` is given.

## Command line usage

Most common — detects every layout from content, no flags needed:

- `python -m yams.data_extraction -i <path/to/binary/data> -o <path/to/output>`

Inspect what would be decoded, without writing anything:

- `python -m yams.data_extraction -i <path/to/binary/data> --dry_run`

Cross-check detection against `uuid.txt` and report disagreements:

- `python -m yams.data_extraction -i <in> -o <out> --validate_with_uuid`
- add `--on_format_conflict raise` to stop on a mismatch, or `trust_uuid` to let the version file win

Reproduce the pre-1.6 version-driven behaviour:

- `python -m yams.data_extraction -i <in> -o <out> --ppg_format version --ac_format version --ecg_format version`

Force a specific layout (rarely needed now that `auto` finds them):

- `python -m yams.data_extraction -i <in> -o <out> --ppg_format packed16`

### All format flags

| Flag | Values | Default |
|---|---|---|
| `--ppg_format` | `auto`, `version`, `legacy`, `v2`, `packed16` | `auto` |
| `--ac_format` | `auto`, `version`, `legacy`, `v2` | `auto` |
| `--ecg_format` | `auto`, `version`, `framed` | `auto` |
| `--validate_with_uuid` | flag | off |
| `--on_format_conflict` | `warn`, `raise`, `trust_uuid` | `warn` |
| `--sniff_threshold` | float | `0.90` |
| `--dry_run` | flag | off |
| `--strict_ppg` | flag | off |
| `--force_new_format` | flag — moves the *fallback* to v4.7.0+; does not override detection | off |

`--ppg_format sniff` is still accepted as a deprecated alias for `auto`. 