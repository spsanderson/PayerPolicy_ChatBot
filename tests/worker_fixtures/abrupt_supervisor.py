"""Die only after the observer holds handles; exercise last-job-handle kill."""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parents[2]))
from payer_policy._windows_job import Job, ProcessIds

output, acknowledge = map(Path, sys.argv[1:])
with Job(128 * 1024 * 1024) as job:
    job.launch(Path(sys.executable),
               Path(__file__).with_name("sleep_worker.py"), [])
    members = job.query(ProcessIds(), 3)
    if members.assigned > 16 or members.listed > 16:
        raise RuntimeError("unexpected overflow")
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps({
        "worker": job.process.pid,
        "members": list(members.pids[:members.listed]),
    }), encoding="utf-8")
    temporary.replace(output)
    output.with_suffix(".ready").write_bytes(b"publication complete")
    deadline = time.monotonic() + 15
    while not acknowledge.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("observer never acknowledged held handles")
        time.sleep(0.01)
    os._exit(23)
