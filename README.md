---
title: YAMS
emoji: 🍠
colorFrom: purple
colorTo: purple
sdk: gradio
sdk_version: 5.15.0
app_file: yams/__main__.py
pinned: false
license: mit
---

# YAMS
Yet Another Motionsense Service utility

### [Code](https://github.com/SenSE-Lab-OSU/YAMS) | [PyPI](https://pypi.org/project/yams-util/) | [🤗 Demo (UI only)](https://huggingface.co/spaces/Oink8154/YAMS)

## Quickstart

### Pre-compiled version

- Download the latest release from [here](https://github.com/SenSE-Lab-OSU/YAMS/releases)

### Development

1. (optional) create a dedicated conda environment
    - `conda create -n yams python=3.12`
    - `conda activate yams`
2. Clone this repository
    - `git clone https://github.com/SenSE-Lab-OSU/YAMS.git`
    - `cd yams`
3. Install dependencies
    - `pip install -r requirements.txt`
4. Config `liblsl`
    - `conda install -c conda-forge liblsl`
5. Lauch YAMS
    - `python -m yams`

### (Deprecated) Windows

> Python 3.12 or newer is needed

1. Download setup scripts
    - Download the [scripts/windows](scripts/windows) folder and save it in your desired folder
2. Run the installation script
    - Run the script by double-click the `install.bat` file
    - The script will perform any necessary setup
3. Start the app
    - by double-click the `start_yams.bat` file
    - Once the initialization is completed, you will see a messge similar to: `* Running on local URL:  http://127.0.0.1:7860`
4. Access the application
    - Open a web browser and navigate to http://127.0.0.1:7860 or the URL displayed in the prompt.

### (Deprecated) MacOS / Linux

1. Download [scripts/unix](scripts/unix) to a desired location
2. Run `run.sh` to install and start the app

## General usage

### Download onboard data

Refer to [Extract onboard data](doc/file_download.md)

### Extract raw data

Refer to [Data Extraction Feature](doc/data_extraction.md)

### Emergency stop

> Terminating data collection is also available in YAMS web app under `bluetooth scanner - collection control - stop`

To halt all on-going collection on the MotionSenSE wristbands, 

- On windows, go to your folder where the setup scripts are located as in [Quickstart-Windows](#quickstart) part
- Locate and double-click `emergency_stop.bat`
- Wait until all operations are completed


## Installation

- `pip install -U yams-util`
- `python -m yams`

## Development guide

- Clone the repository
    - `git clone https://github.com/SenSE-Lab-OSU/YAMS.git`
- Install dependencies 
    - `pip install -r requirements.txt`
- Launch the application
    - `python -m yams`
- Visit http://127.0.0.1:7860 (by default, check on-screen prompt)

## Build guide

- Install pyinstaller via `pip install pyinstaller`
- Create .spec by `pyi-makespec --collect-data=gradio_client --collect-data=gradio --collect-data=safehttpx --collect-data=groovy --onefile app.py`
- Manually add the following in `a = analysis ...`

```
    module_collection_mode={
        'gradio': 'py',  # Collect gradio package as source .py files
    },
```
- Build the app: `pyinstaller app.spec`


### MacOS

`pyi-makespec --collect-data=gradio_client --collect-data=gradio --collect-data=safehttpx --collect-data=groovy --onefile --osx-bundle-identifier 'com.yams' --icon yams/resources/icons/yams.icns app.py`


## Instructions

### (advanced) running data extraction in command line

Run from the project root:

```bash
python -m yams.data_extraction -i "data_in" -o "data_out"
```

**All options:**

| Flag | Default | Description |
|---|---|---|
| `-i`, `--in_dir` | *(required)* | Directory containing `.bin` files |
| `-o`, `--out_dir` | `./` | Output directory |
| `--save_format` | `csv` | Output format: `csv` or `pickle` |
| `--ignore_id` | off | Skip subject/session ID parsing; use raw filenames |
| `--legacy_fs` | off | Use 25 Hz clock for CDCT (uncommon, old devices) |
| `--force_new_format` | off | Force v4.7.0+ binary layout regardless of `uuid.txt` version |
| `--mode` | `dir` | `dir`: single folder of `.bin` files; `batch`: folder of `.zip` archives |

**Data type detection** — the extractor scans the input folder and processes whichever file types are present:

| File pattern | Sensor | Output |
|---|---|---|
| `[id]ac*.bin` | IMU (AccX/Y/Z, QuatX/Y/Z, ENMO) | `[id]ac.csv` |
| `[id]ppg*.bin` | PPG (ir1, ir2, g1, g2) | `[id]ppg.csv` |
| `[id]ecg*.bin` | MAX30001 ECG (ECG, ETAG, PTAG) | `[id]ecg.csv` |

A single run extracts all types present. Missing types are silently skipped.

**Examples:**

```bash
# Wristband (AC + PPG) — firmware auto-detected from uuid.txt
python -m yams.data_extraction -i "data/subject01" -o "out/subject01"

# Wristband on v4.7.0+ firmware (force if uuid.txt is absent or reports wrong version)
python -m yams.data_extraction -i "data/subject01" -o "out/subject01" --force_new_format

# ECG only folder (e.g. data/260708_ecg containing ecg*.bin)
python -m yams.data_extraction -i "data/260708_ecg" -o "out/ecg" --ignore_id

# Mixed folder with both wristband and ECG files
python -m yams.data_extraction -i "data/session01" -o "out/session01" --force_new_format --ignore_id

# Save as pickle, skip ID parsing
python -m yams.data_extraction -i "data/subject01" -o "out/subject01" --save_format pickle --ignore_id

# Batch extract a folder of zip archives
python -m yams.data_extraction -i "data_in" --mode batch
```

**Notes:**
- The device version is read automatically from `uuid.txt`. If v4.7.0+, the new binary layout (uint32 PPG, quaternion IMU, 32-bit counter at 512 Hz) is used for AC/PPG; otherwise the legacy layout is used. Use `--force_new_format` to override.
- ECG binary format (`ecg*.bin`) is always parsed the same way regardless of firmware version — it uses 12-byte CRC-validated frames with a 512 Hz sequence counter.
- ECG output columns: `ECG` (signed 18-bit ADC count), `ETAG` (0 = valid sample, 2 = leads off), `PTAG`, `Counter`, `CDCT`, `Datetime`.

## Roadmap

- [x] Device data transfer
- [x] Device data post processing
    - [x] format conversion
    - [x] visualization
- [x] simple data collection utilities
- [x] LSL support
- [x] Auto reconnect
- [x] Selected file download
- [ ] Advanced device monitoring
    [ ] global state: active connection, active outlet, ctl status
    [ ] BAT monitoring
    [ ] storage monitoring


## Acknowledgement

- Conceptualization: [MPADA](https://github.com/yuyichang/mpada)
- BT control adapted from [MotionSenseHRV-BioImpedance-Interface
](https://github.com/SenSE-Lab-OSU/MotionSenseHRV-BioImpedance-Interface).
- icon designed by [Mihimihi](https://www.flaticon.com/free-icons/yam)