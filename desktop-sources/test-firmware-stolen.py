# The blanket stolen-exclusion policy was replaced by a bounded GOP reservation.
from pathlib import Path
import subprocess,sys
r=Path(__file__).resolve().parent.parent
subprocess.run([sys.executable,str(r/'desktop-sources/test-scanout-reservation.py')],check=True)
