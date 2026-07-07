import os
import sys

if getattr(sys, "frozen", False):
    frameworks_dir = os.path.normpath(
        os.path.join(os.path.dirname(sys.executable), "..", "Frameworks")
    )
    existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
        f"{frameworks_dir}:{existing}" if existing else frameworks_dir
    )
