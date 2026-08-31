import os as _os
import sys as _sys

# Refuse to report application results from a runner that cannot execute this
# package's async tests. See tools/pytest_harness_guard.py -- a test runner is
# part of the evidence chain, and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 silently
# removes pytest-asyncio, turning every async test into a fake failure.
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.dirname(_os.path.abspath(__file__))))), "tools"))
pytest_plugins = ["pytest_harness_guard"]
