---
layout: page
title: Quick Start
permalink: /quick_start/
---

# 🚀 Quick Start


## Installation 

### Windows

Download the latest release from our [GitHub Releases page](https://github.com/SenSE-Lab-OSU/YAMS/releases) and run the bundled executable.  
No Python or additional setup required.

The app interface should automatically pop up from the default browse. The interface is also accessible on [http://127.0.0.1:7860](http://127.0.0.1:7860)

### macOS / Linux

> At this time, a prebuild package is not available on macOS / Linux

We recommend using a dedicated [Conda](https://docs.conda.io/en/latest/) environment:

```bash
conda create -n yams python=3.12
conda activate yams
```

Install `liblsl` dependency 

``` bash
conda install -c conda-forge liblsl
```

Install YAMS via `pip`:

``` bash
pip install yams-util
```

To launch the app:

``` bash
python -m yams
```

The app interface should automatically pop up from the default browse. The interface is also accessible on [http://127.0.0.1:7860](http://127.0.0.1:7860)

<!-- 🛠️ Coming soon: Homebrew formula and precompiled binaries for macOS/Linux. -->

## Config wristband binding

> config `device_info.json`
