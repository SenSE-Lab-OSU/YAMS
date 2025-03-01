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

### Windows

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

### MacOS / Linux

1. Download [scripts/unix](scripts/unix) to a desired location
2. Run `run.sh` to install and start the app

## General usage

### Extract onboard data

Refer to [Extract onboard data](doc/file_extraction.md)

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


## Roadmap

- [x] Device data transfer
- [ ] Device data post processing
    - [ ] format conversion
    - [ ] visualization
- [x] simple data collection utilities
- [ ] LSL support
- [ ] Auto reconnect


## Acknowledgement

- Conceptualization: [MPADA](https://github.com/yuyichang/mpada)
- BT control adapted from [MotionSenseHRV-BioImpedance-Interface
](https://github.com/SenSE-Lab-OSU/MotionSenseHRV-BioImpedance-Interface).