"""Resolve effective configuration: source directories, database path,
server port, each overridable by an environment variable with a sensible
default.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = os.environ.get("PEPA_PROJECT")
DATA_ROOT = Path(PROJECT) / "pepa-read" if PROJECT else ROOT

TEXT_DIR = Path(os.environ.get(
    "PEPA_READER_TEXT_DIR", str(DATA_ROOT.parent / "pepa-prep" / "output" / "text")
))
SUM_DIR = Path(os.environ.get(
    "PEPA_READER_SUM_DIR", str(DATA_ROOT.parent / "pepa-sum" / "output")
))
DB_PATH = Path(os.environ.get("PEPA_READER_DB_PATH", str(DATA_ROOT / "data" / "reader.db")))
PORT = int(os.environ.get("PEPA_READER_PORT", "5151"))
HOST = "127.0.0.1"
