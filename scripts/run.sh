#!/bin/bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U yams-util 
python -m yams
deactivate
