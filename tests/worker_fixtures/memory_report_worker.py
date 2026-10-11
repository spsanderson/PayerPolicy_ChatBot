"""Simulate a child MemoryError; this is not evidence of PDF exhaustion."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).absolute().parents[2]))
from payer_policy import _inspection_child as child
from payer_policy import _inspection_protocol as protocol

request = protocol.read_request(Path(sys.argv[1]))
child.bootstrap(request["runtime"])
with patch("payer_policy.document_inspection.PdfReader",
           side_effect=MemoryError("private simulated failure")):
    result = child.inspect_request(request)
protocol.publish(Path(sys.argv[2]), result)
