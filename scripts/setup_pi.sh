#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip espeak-ng alsa-utils libjpeg-dev zlib1g-dev
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
mkdir -p data/images data/audio
