"""Inspect from a copied trusted checkout/runtime under isolated startup."""
import json
import sys
import sysconfig
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parents[2]))
sys.path.append(sysconfig.get_path("purelib"))
from payer_policy.inspection_worker import inspect_saved_pdf_in_worker

result = inspect_saved_pdf_in_worker(Path(sys.argv[1]), sys.argv[2])
print(json.dumps(asdict(result)))
