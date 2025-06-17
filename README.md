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