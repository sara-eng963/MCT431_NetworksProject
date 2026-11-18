"""Package project source and verified M1 evidence, excluding tools/backups/secrets."""
import hashlib
import json
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'output';output.mkdir(exist_ok=True)
archive=output/'MCT431_Milestone1.zip'
files=[]
for folder in ('Gateway','Production_ESP/main','Production_ESP/tests','Inspection_ESP/main','tests','scripts','docs','logs/milestone1-20261118'):
    for path in (ROOT/folder).rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:continue
        if folder.startswith('logs/') and any(part in ('capture','acceptance') for part in path.relative_to(ROOT/folder).parts):continue
        files.append(path)
for name in ('README.md','requirements.txt','requirements-dev.txt','requirements-build.txt',
             'Production_ESP/CMakeLists.txt','Production_ESP/platformio.ini','Production_ESP/sdkconfig.defaults',
             'Inspection_ESP/CMakeLists.txt','Inspection_ESP/platformio.ini','Inspection_ESP/sdkconfig.defaults'):
    files.append(ROOT/name)
manifest=[]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as package:
    for path in sorted(set(files)):
        relative=path.relative_to(ROOT).as_posix()
        if relative.startswith(('.tools/','.venv/','.git/')):raise ValueError('Private/tool path in package')
        package.write(path,relative)
        manifest.append({'path':relative,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    package.writestr('MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
with zipfile.ZipFile(archive) as package:assert package.testzip() is None
print(archive,'files=',len(manifest),'bytes=',archive.stat().st_size)
