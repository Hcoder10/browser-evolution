import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gauntlet import app

__all__ = ["app"]
