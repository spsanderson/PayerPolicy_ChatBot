"""Attempt one ordinary child; report kernel refusal under active limit one."""
import json
import subprocess
import sys
from pathlib import Path

try:
    child = subprocess.run(
        [sys.executable, "-I", "-S", "-B",
         str(Path(__file__).with_name("hello.py"))],
        timeout=5, check=True,
    )
except OSError as exc:
    result = {"refused": True, "error": exc.winerror}
else:
    result = {"refused": False, "error": 0}
Path(sys.argv[1]).write_text(json.dumps(result), encoding="utf-8")
