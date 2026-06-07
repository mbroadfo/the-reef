$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host "Building lambda.zip..."
Remove-Item -Recurse -Force package, lambda.zip -ErrorAction SilentlyContinue
pip install -r requirements.txt -t package/ -q
Copy-Item handler.py package/
python -c @"
import zipfile, pathlib
with zipfile.ZipFile('lambda.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for f in pathlib.Path('package').rglob('*'):
        if f.is_file() and '__pycache__' not in str(f) and not str(f).endswith('.pyc'):
            z.write(f, f.relative_to('package'))
"@
Remove-Item -Recurse -Force package
Write-Host "Done: lambda.zip"
