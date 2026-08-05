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
5. (Uncommon) Check "legacy sampling rate" box if the data was collected on a older firmware version. Do NOT check this box if using firmware >- 4.5.3.
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


## PPG record format

PPG binaries exist in three on-disk layouts. The first two are identified by the firmware version in `uuid.txt`; the third is not, so it must be selected by hand.

| Choice | Record | Layout |
|---|---|---|
| `auto` (default) | — | Follow `uuid.txt`: v4.7.0+ → `v2`, otherwise `legacy` |
| `legacy` | 24 B | `6x int32` — ir1, ir2, g1, g2, Timestamp, Counter (320 Hz) |
| `v2` | 20 B | `5x uint32` — ir1, ir2, g1, g2, global tick (512 Hz) |
| `packed16` | 16 B | `4x uint24` channels + `uint32` global tick (512 Hz) |
| `sniff` | — | Detect from file contents, falling back to `auto` if inconclusive |

`packed16` (see `data/PPG_PACKED_16_BYTE_FORMAT.md`) packs each 19-bit channel into three bytes and drops the per-record `Timestamp`. Firmware carrying it has **no distinguishing version number**, so `auto` cannot find it — set the format explicitly, or use `sniff`.

This setting affects PPG only. IMU and ECG still follow the device version / "Force v4.7.0+ format" checkbox.

The 512 Hz tick is written to the `Counter` column for every format, so the Clock Sync tab works on `packed16` output unchanged. Records whose reserved channel bits (19–23) are set are dropped and reported; `--strict_ppg` / the "Strict PPG validation" checkbox raises instead. The resolved format and the dropped-record count are written to `README.txt` in the output directory — with no version number in the file, that is the only record of how a CSV was decoded.

In the UI, the selector is on both the **🛠️ Data Extractor** and **🛠️ Data extractor pro** tabs.

## Command line usage

Most common (e.g., firmware >= 4.5)

- `python -m yams.data_extraction -i <path/to/binary/data> -o <path/to/output>` 

Not common. For firmware with 25 Hz sampling rate

- `python -m yams.data_extraction -i <path/to/binary/data> -o <path/to/output> --legacy_fs`

Packed 16-byte PPG records (experimental firmware, no version tie)

- `python -m yams.data_extraction -i <path/to/binary/data> -o <path/to/output> --ppg_format packed16`
- `python -m yams.data_extraction -i <path/to/binary/data> -o <path/to/output> --ppg_format sniff` — detect the layout from the files themselves 