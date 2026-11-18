"""Compile and execute the real portable C modules on the host."""
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT/'Production_ESP/main'

@pytest.mark.parametrize('test', sorted((ROOT/'Production_ESP/tests').glob('test_*.c')), ids=lambda p:p.stem)
def test_c_sources(test, tmp_path):
    executable = tmp_path/(test.stem+'.exe')
    sources = [MAIN/name for name in ('atr.c','slip.c','production.c','controller.c')]
    subprocess.run([sys.executable,'-m','ziglang','cc','-std=c11','-Wall','-Wextra','-Werror',
                    '-I',str(MAIN),str(test),*map(str,sources),'-o',str(executable)],check=True)
    subprocess.run([str(executable)],check=True,timeout=10)
