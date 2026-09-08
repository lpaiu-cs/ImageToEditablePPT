"""Python-level file-open allowlist for RGB-only inference diagnostics.

This is evidence instrumentation, not an OS sandbox: native library IO is not
universally intercepted by Python audit hooks. Source and configuration review
remain necessary. Install only inside a dedicated inference subprocess.
"""
import os
from pathlib import Path
import sys


def install_guard(image, output_dir, code_dir):
    image = Path(image).resolve()
    output = Path(output_dir).resolve()
    roots = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(),
             Path(code_dir).resolve(), Path('C:/Windows/Fonts').resolve()]
    reads = set()
    denied = []

    def within(path, root):
        return path == root or root in path.parents

    def audit(event, args):
        if event != 'open' or isinstance(args[0], int):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        mode, flags = args[1], args[2]
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or bool(
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        allowed = within(path, output) if writing else (
            path == image or within(path, output) or any(within(path, root) for root in roots))
        if not allowed:
            denied.append(str(path))
            raise PermissionError('RGB-only inference file boundary: ' + str(path))
        if not writing:
            reads.add(str(path))

    sys.addaudithook(audit)
    return reads, denied
