"""Build a staged ARM/uClibc rootfs overlay; run with RootLink/.venv/bin/python.

Never copies a host interpreter. Every staged ELF and its dependency closure is
checked before producing the archive. Runtime import validation is separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

def command(*args):
    return subprocess.check_output(args, text=True)

def check_arm(path):
    header=command('readelf','-h',str(path))
    if not re.search(r'Class:\s+ELF32',header) or not re.search(r'Machine:\s+ARM\s*$',header,re.M):
        raise RuntimeError(f'Not ARM32: {path}')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--target-root',type=Path,required=True)
    parser.add_argument('--voice',type=Path,required=True)
    parser.add_argument('--lvgl-source',type=Path,help='LVGL source used by this voice binary (includes its license)')
    parser.add_argument('--output',type=Path,required=True,help='New empty staging directory')
    args=parser.parse_args()
    target=args.target_root.resolve(); out=args.output.resolve()
    if out.exists(): raise RuntimeError('Output must not exist; choose a new staging directory')
    embedded=Path(__file__).resolve().parents[1]
    project=embedded.parents[1]
    executable=target/'usr/bin/python3.11'
    check_arm(executable)
    if '/lib/ld-uClibc.so.0' not in command('readelf','-l',str(executable)):
        raise RuntimeError('Expected uClibc interpreter')
    check_arm(args.voice)
    (out/'usr/bin').mkdir(parents=True)
    shutil.copy2(executable,out/'usr/bin/python3.11')
    (out/'usr/bin/python3').symlink_to('python3.11')
    shutil.copy2(args.voice,out/'usr/bin/rootlink-voice')
    stdlib=out/'usr/lib/python3.11'
    shutil.copytree(target/'usr/lib/python3.11',stdlib,
        ignore=shutil.ignore_patterns('site-packages','test','tests','tkinter','idlelib','ensurepip'))
    site=stdlib/'site-packages'
    subprocess.run([sys.executable,'-m','pip','install','--only-binary=:all:',
        '--platform','any','--implementation','py','--python-version','3.11','--no-compile',
        '--target',str(site),'-r',str(embedded/'requirements-core.txt')],check=True)
    shutil.copytree(project/'src/agent_core',site/'agent_core',
        ignore=shutil.ignore_patterns('__pycache__','tests','*.pyc'))
    entry=out/'opt/rootlink/persona-worker.py'
    entry.parent.mkdir(parents=True)
    shutil.copy2(embedded/'scripts/persona-worker.py',entry)
    shutil.copy2(embedded/'scripts/check-python-target.py',entry.parent/'check-python-target.py')
    if args.lvgl_source:
        licenses=entry.parent/'licenses'
        licenses.mkdir()
        shutil.copy2(args.lvgl_source/'LICENCE.txt',licenses/'LVGL-LICENCE.txt')
    shutil.copytree(embedded/'config/role-example',out/'opt/rootlink/role-seed')
    (out/'etc/rootlink').mkdir(parents=True)
    shutil.copy2(embedded/'config/rv1106-python.conf.example',out/'etc/rootlink/python.conf')
    shutil.copy2(embedded/'config/rootlink-secrets.env.example',out/'etc/rootlink/rootlink-secrets.env.example')
    (out/'etc/ssl/certs').mkdir(parents=True)
    shutil.copy2(site/'certifi/cacert.pem',out/'etc/ssl/certs/ca-certificates.crt')
    # Follow only runtime dependencies, avoiding unrelated SDK/site-package libraries.
    def copy_library(name):
        for directory in ('lib','usr/lib'):
            candidate=target/directory/name
            if candidate.is_file():
                destination=out/directory/name
                if not destination.exists():
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(candidate,destination,follow_symlinks=True)
                return destination
        raise RuntimeError(f'Missing target library: {name}')
    copy_library('ld-uClibc.so.0')
    checked=set()
    while True:
        files=[]
        for p in out.rglob('*'):
            if p.is_file() and not p.is_symlink() and p not in checked:
                with p.open('rb') as f: magic=f.read(4)
                if magic==b'\x7fELF': files.append(p)
        if not files: break
        for p in files:
            check_arm(p); checked.add(p)
            for name in re.findall(r'\(NEEDED\).*?\[(.*?)\]',command('readelf','-d',str(p))):
                copy_library(name)
    ssl=list(stdlib.glob('lib-dynload/_ssl*.so'))
    if not ssl: raise RuntimeError('Missing target _ssl module')
    manifest={'architecture':'ARM32 EABI5 uClibc','python':'3.11.6 (SDK build)',
        'elf_files_checked':len(checked),'board_validated':False,
        'files':{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in out.rglob('*') if p.is_file()}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    archive=out.with_suffix('.tar.gz')
    if archive.exists(): raise RuntimeError('Archive already exists')
    with tarfile.open(archive,'w:gz') as tar:
        for p in sorted(out.iterdir()): tar.add(p,arcname=p.name)
    print(f'archive={archive}\nelf_checked={len(checked)}\nboard_validation=pending')

if __name__=='__main__': main()
