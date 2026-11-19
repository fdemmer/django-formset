alias t := test

[private]
default:
    @just --list --unsorted

gha-update:
    uvx gha-update

gha-check args="":
    uvx zizmor {{args}} .

uvrun command:
    uv run {{command}}

# python env: deps, editable install, playwright browser; e.g. `just setup "Django==5.2.*" 3.12`
setup django="Django>=5.1,<6.1" python="3.13":
    test -d .venv || uv venv --python {{python}}
    uv pip install "{{django}}" -r testapp/requirements.txt
    uv pip install --no-deps -e .
    @just uvrun "playwright install chromium"

# npm dev dependencies (rerun when package.json changes)
setup-js:
    npm install --include=dev

# pytest (default: whole testapp); e.g. `just test "testapp/tests/test_e2e_slugfield.py -x" 1`
test args="" $PYTEST_USE_MONOLITHIC_BUILD="0": build-js
    @just uvrun "python -m pytest {{ if args == '' { 'testapp' } else { args } }}"

# jest unit tests for the PEG parsers
test-js args="": build-parsers
    npm run testclient -- {{args}}

# everything the testapp needs: parsers, css, client bundles
build-js: build-parsers build-css build-bundles

# PEG grammars in assets/*.pegjs -> client/build/*.ts
build-parsers:
    npm run tag-attributes
    npm run no-comments

# scss, tailwind and country flag sprite -> formset/static/formset/
build-css:
    npm run compilescss
    npm run tailwindcss
    npm run sprite-flags

# modular + monolith client bundles -> formset/static/formset/js/; `just build-bundles --debug` for sourcemaps
build-bundles *args: build-parsers
    npm run esbuild.modular -- {{args}}
    npm run esbuild.monolith -- {{args}}

# python package (sdist + wheel) -> dist/, same steps as publish.yml (minified bundles, compiled translations)
build: build-js compilemessages
    rm -rf dist build
    uv build --sdist --wheel --out-dir dist

# *.po -> *.mo in formset/locale (needs gettext)
compilemessages:
    cd formset && ../.venv/bin/django-admin compilemessages
