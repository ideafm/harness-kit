import os
import subprocess
import sys
from pathlib import Path

from .launcher import ROOT


def main(arguments):
    if not arguments or arguments[0] not in {'accept', 'request-changes', 'reject'}:
        raise ValueError('Недопустимое операторское действие')
    command = [str(Path(sys.executable).resolve()), '-B',
               str(ROOT.parent / 'bin/tw'), '--project', str(ROOT), *arguments]
    result = subprocess.run(command, env={'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'}, shell=False)
    if result.returncode:
        raise SystemExit(result.returncode)
