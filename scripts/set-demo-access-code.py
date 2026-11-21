"""Set the separate ReproLab operator code through a hidden SSH prompt."""

import getpass
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

if os.geteuid() != 0 or not sys.stdin.isatty():
    raise SystemExit("Run this with sudo in the VM's SSH terminal.")

target = Path('/etc/reprolab-ai/demo_access_code')
if not target.is_file() or target.is_symlink():
    raise SystemExit('The ReproLab operator backend is not installed.')

code = getpass.getpass('ReproLab 演示访问码（隐藏输入）: ').strip()
if not re.fullmatch(r'[A-Za-z0-9_-]{20,128}', code):
    raise SystemExit('请使用 20–128 位随机字母、数字、短横线或下划线。现有访问码未更改。')
if code != getpass.getpass('再输入一次访问码（隐藏输入）: ').strip():
    raise SystemExit('两次输入不一致。现有访问码未更改。')

os.umask(0o077)
with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, delete=False) as temp:
    temp.write(code + '\n')
os.replace(temp.name, target)
subprocess.run(['systemctl', 'restart', 'reprolab-demo-operator.service'], check=True)
print('演示访问码已更新。请在 GitHub Pages 中选择「解锁实时演示」。')
