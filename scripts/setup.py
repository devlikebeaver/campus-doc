"""Install dependencies into this skill's directory with the active Python."""
import subprocess
import sys
from pathlib import Path

destination = Path(__file__).resolve().parents[1] / 'runtime' / 'python'
destination.mkdir(parents=True, exist_ok=True)
requirements = Path(__file__).resolve().parents[1] / 'requirements.txt'
subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', '--target', str(destination),
                '-r', str(requirements)], check=True)
print('Installed skill dependencies in ' + str(destination))
