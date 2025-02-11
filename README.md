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

1. Download the script
    - Download the [scripts/run.bat](scripts/run.bat) and save it in your desired folder.
2. Run the script
    - Run the script by double-click the `run.bat` file
3. Setting up
    - The script will perform any necessary setup. 
    - Once the setup is complete, you will see a messge similar to: `* Running on local URL:  http://127.0.0.1:7860`
4. Access the application
    - Open a web browser and navigate to http://127.0.0.1:7860 or the URL displayed in the prompt.

### MacOS / Linux

Coming soon!

## Installation

- `pip install -U yams-util`
- `python -m yams`

## Development guide

- Clone the repository
    - `git clone https://github.com/SenSE-Lab-OSU/YAMS.git`
- Install dependencies 
    - `pip install gradio bleak psutil`
- Launch the application
    - `python -m yams`
- Visit http://127.0.0.1:7860 (by default, check on-screen prompt)


## Roadmap

- [x] Device data transfer
- [ ] Device data post processing
    - [ ] format conversion
    - [ ] visualization
- [ ] simple data collection utilities


## Acknowledgement

- Conceptualization: [MPADA](https://github.com/yuyichang/mpada)
- BT control adapted from [MotionSenseHRV-BioImpedance-Interface
](https://github.com/SenSE-Lab-OSU/MotionSenseHRV-BioImpedance-Interface).