from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

spec = importlib.util.spec_from_file_location("facility_backend_main", backend_dir / "main.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load backend application")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
app = module.app
