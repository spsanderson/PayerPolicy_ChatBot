"""Simulate a bad root after ../test_inspection_worker.py sends a request.

Use a real file as the root; the child must reject it before inspection.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parents[2]))
from payer_policy import _inspection_child as child
from payer_policy import _inspection_protocol as protocol

request = protocol.read_request(Path(sys.argv[1]))
child.bootstrap(request["runtime"])
request["root"] = str(Path(request["root"]) / "records"
                      / request["retrieval_id"] / "original.bin")
result = child.inspect_request(request)
protocol.publish(Path(sys.argv[2]), result)
