import sys
import os

# Root conftest to ensure current directory is in sys.path for pytest
root_dir = os.path.abspath(os.path.dirname(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
