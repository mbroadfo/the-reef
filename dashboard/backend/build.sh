#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Building lambda.zip..."
rm -rf package/ lambda.zip
pip install -r requirements.txt -t package/ -q
cp handler.py package/
cd package
zip -r ../lambda.zip . -x "*.pyc" -x "*__pycache__*" > /dev/null
cd ..
rm -rf package/
echo "Done: $(du -sh lambda.zip | cut -f1)"
