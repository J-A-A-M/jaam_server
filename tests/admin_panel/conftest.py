"""Робить пакет `app` (admin_panel/backend/app) імпортовним для тестів панелі."""

import os
import sys

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "admin_panel", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
