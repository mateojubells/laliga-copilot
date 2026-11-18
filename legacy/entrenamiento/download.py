#!/usr/bin/env python3
"""Descarga SoccerNet-Echoes (transcripciones Whisper v3, CC BY 4.0) y las etiquetas de acción de SoccerNet.
Uso: python3 download.py DIRECTORIO     (necesita: pip install SoccerNet)
Solo baja transcripciones y etiquetas, nunca vídeo ni audio."""
import sys, os, urllib.request
D = sys.argv[1]; os.makedirs(D + "/echoes", exist_ok=True)
B = "https://huggingface.co/datasets/SoccerNet/SN-echoes/resolve/main/whisper_v3/1.0.0/"
for f in ("soccer_net_echoes_hf_dataset-train.arrow", "dataset_info.json"):
    urllib.request.urlretrieve(B + f, f"{D}/echoes/{f}")
from SoccerNet.Downloader import SoccerNetDownloader
SoccerNetDownloader(LocalDirectory=D + "/labels").downloadGames(files=["Labels-v2.json"], split=["train", "valid", "test"])
