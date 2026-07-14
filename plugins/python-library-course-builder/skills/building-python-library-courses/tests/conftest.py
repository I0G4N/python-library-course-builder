from __future__ import annotations

import os
import sys


# The test suite imports the raw course template as Python modules and also
# launches compiler subprocesses. Keep those verification steps from polluting
# the publishable Skill tree with runtime bytecode.
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
