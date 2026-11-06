#!/bin/bash
# Build .venv-harbor: Harbor 0.23.0 + Modal, Python 3.12 (the main .venv is 3.11).
# modal is pinned to the version in .venv; --only-binary because cbor2 fails to
# build from source here. Both patches are applied to the installed package.
set -euo pipefail
cd "$(dirname "$0")/../../.."
uv venv -q --python 3.12 .venv-harbor
uv pip install -q --python .venv-harbor/bin/python 'harbor[modal]==0.23.0' 'modal==1.6.1' --only-binary cbor2
site=$(.venv-harbor/bin/python -c "import harbor, os; print(os.path.dirname(os.path.dirname(harbor.__file__)))")
patch -p1 -d "$site" < tasks/software_engineering/harbor/harbor-0.23.0.patch
patch -p1 -d "$site" < tasks/software_engineering/harbor/harbor-0.23.0-openrouter.patch
