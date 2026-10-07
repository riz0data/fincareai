"""
Shared pytest fixtures for the oncology-financial-navigator-ai test suite.

Adds the app/ subpackages to sys.path so tests can import modules the same way
they import each other internally (e.g. `import foundation_reference_store`),
without needing to turn this prototype into an installable package first.
"""

import sys
import os

APP_ROOT = os.path.join(os.path.dirname(__file__), "..", "app")

for subpackage in ["agents", "data", "orchestration", "rules_engine"]:
    path = os.path.abspath(os.path.join(APP_ROOT, subpackage))
    if path not in sys.path:
        sys.path.insert(0, path)
