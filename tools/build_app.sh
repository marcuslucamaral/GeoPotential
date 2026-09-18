#!/usr/bin/env bash
#
# Build, verify and package GeoPotential Professional for Linux x86_64.
#
#   tools/build_app.sh            build, verify, archive
#   tools/build_app.sh --clean    remove build/ and dist/ first
#   tools/build_app.sh --fast     skip the pre-build gate (local iteration only)
#
# **The verification is the point.** A bundle can be assembled perfectly and
# die at first import on a machine with no development environment, and the
# build log is clean in exactly those cases. So this runs the *shipped binary's*
# own gate and fails if it does not pass. There is no switch to skip it.
#
# The order is deliberate:
#
#   1. fixtures     regenerated, then bundled, so the artefact can gate itself
#   2. gate         packaging a tree that fails its own tests wastes minutes
#                   and produces a binary nobody should trust
#   3. PyInstaller  tools/geopotential.spec
#   4. verify       --help, --worker --capabilities, --self-test, --screenshot,
#                   the last two in a stripped environment
#   5. archive      .tar.gz, versioned and dated
#
# `build/` is PyInstaller's scratch workpath and `dist/` is its output. Neither
# is a source. Only this script removes them (`--clean`).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
msp="$(dirname "$here")"
python_bin="$("$here/find_python.sh")"
cd "$msp"

clean=0
fast=0
for arg in "$@"; do
    case "$arg" in
        --clean) clean=1 ;;
        --fast)  fast=1 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

version="$("$python_bin" -c "
import sys; sys.path.insert(0, 'app')
from geopotential_app._version import VERSION; print(VERSION)")"
worker_version="$("$python_bin" -c "
import sys; sys.path.insert(0, 'worker')
from geopotential_worker._version import VERSION; print(VERSION)")"

say "GeoPotential Professional — app $version, worker $worker_version"
echo "python: $python_bin"
"$python_bin" -c "import PyInstaller; print('PyInstaller', PyInstaller.__version__)" \
    || die "PyInstaller is not installed in this environment"

if [ "$clean" = "1" ]; then
    say "cleaning build/ and dist/"
    rm -rf "$msp/build" "$msp/dist"
fi

# ---- 1. fixtures ---------------------------------------------------------
# They are bundled, and they are what makes the shipped binary's --self-test
# mean anything on a machine with no checkout.
say "fixtures"
if [ ! -f "$msp/../data/synthetic/msp/broken/MANIFEST.json" ]; then
    "$python_bin" "$here/make_broken_fixtures.py" || die "broken fixtures"
fi
if [ ! -f "$msp/../data/synthetic/msp/canvas/MANIFEST.json" ]; then
    "$python_bin" "$here/make_canvas_fixtures.py" || die "canvas fixtures"
fi
"$python_bin" "$here/make_icons.py" --check || die "the icon set is out of date"
echo "ok"

# ---- 2. the tree's own gate ---------------------------------------------
if [ "$fast" = "0" ]; then
    say "gate (before packaging)"
    "$here/run_gate.sh" || die "the tree does not pass its own gate; fix that first"
else
    say "gate SKIPPED (--fast) — do not publish this artefact"
fi

# ---- 3. build ------------------------------------------------------------
say "PyInstaller"
"$python_bin" -m PyInstaller \
    --noconfirm \
    --distpath "$msp/dist" \
    --workpath "$msp/build" \
    "$here/geopotential.spec" || die "PyInstaller"

binary="$msp/dist/geopotential/geopotential"
[ -x "$binary" ] || die "no executable at $binary"

# ---- 4. verify the artefact, not the log ---------------------------------
# Each check catches a different class, in increasing order of what it proves.
say "verifying the shipped binary"

echo "--- 1/4  it starts"
"$binary" --help > /dev/null || die "--help: the bootloader or Python did not start"
echo "ok"

echo "--- 2/4  it can be the worker"
caps="$("$binary" --worker --capabilities)" \
    || die "--worker --capabilities: the binary cannot be the worker process"
for operator in grid.idw grid.tin_cubic grid.cross_validate decision.aggregate; do
    echo "$caps" | grep -q "$operator" \
        || die "the worker in the bundle does not announce $operator"
done
# `--capabilities` is a JSON array of operator descriptions.
n_caps="$("$python_bin" -c "
import json, sys
print(len(json.load(sys.stdin)))" <<< "$caps")" || die "the worker's capabilities are not valid JSON"
echo "ok  ($n_caps operators announced by the worker inside the bundle)"

# From here on, in a stripped environment. Running with the development
# environment still on PATH proves nothing: that is the environment the binary
# exists to not need.
strip_env=(env -i HOME=/tmp PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen)

echo "--- 3/4  its own gate, in a stripped environment"
selftest_log="$msp/dist/self-test.log"
if "${strip_env[@]}" "$binary" --self-test > "$selftest_log" 2>&1; then
    tail -1 "$selftest_log"
else
    tail -30 "$selftest_log" >&2
    die "--self-test failed in a stripped environment; see $selftest_log"
fi

echo "--- 4/4  it draws, on real data"
smoke="$msp/dist/geopotential/_internal/data/utah_forge/Distance_to_fault.tif"
[ -f "$smoke" ] || smoke="$msp/dist/geopotential/data/utah_forge/Distance_to_fault.tif"
shot="$msp/dist/verification.png"
if [ -f "$smoke" ]; then
    "${strip_env[@]}" "$binary" --screenshot "$shot" --size 1440x880 "$smoke" \
        > /dev/null 2>&1 || die "--screenshot: the canvas did not render"
    [ -s "$shot" ] || die "--screenshot wrote an empty file"
    # A file that exists proves a file was written. A window that failed to
    # compose writes a perfectly valid PNG of one flat colour, so what is
    # checked is that there is a picture in it.
    "$python_bin" - "$shot" <<'PYEOF' || die "--screenshot produced a blank window"
import sys
from PySide6.QtGui import QImage
image = QImage(sys.argv[1])
if image.isNull():
    raise SystemExit("the screenshot is not a readable image")
step = max(1, image.width() // 200)
seen = {image.pixel(x, y)
        for x in range(0, image.width(), step)
        for y in range(0, image.height(), step)}
print(f"    {image.width()}x{image.height()}, {len(seen)} distinct colours sampled")
if len(seen) < 50:
    raise SystemExit(f"only {len(seen)} colours: this is a blank window, "
                     f"not a rendered application")
PYEOF
    echo "ok  ($(du -h "$shot" | cut -f1) at $shot)"
else
    echo "SKIPPED: the smoke raster is not in the bundle"
fi

# ---- 5. archive ----------------------------------------------------------
say "archive"
stamp="$(date +%Y%m%d)"
archive="$msp/dist/geopotential-${version}-linux-x86_64-${stamp}.tar.gz"
# The installer travels with what it installs, so the person who receives the
# archive does not need this repository to put the application anywhere.
cp "$here/install.sh" "$msp/dist/install.sh"
cp "$here/../docs/INSTALL.md" "$msp/dist/INSTALL.md" 2>/dev/null || true

# The commands, in plain text, with this build's real filename in them.
# Written by the build and not kept as a file in the tree, because a card that
# names a version is wrong the moment the version changes.
card="$msp/dist/COMO-INSTALAR.txt"
cat > "$card" <<CARD
GeoPotential Professional $version — instalar no Ubuntu
================================================================

Copie UM arquivo para a outra máquina:

    $(basename "$archive")

Depois, nela:

    tar -xzf $(basename "$archive")
    cd \$(basename $(basename "$archive") .tar.gz) 2>/dev/null || cd .
    ./install.sh

Isso instala em ~/.local/share/geopotential, cria o comando
~/.local/bin/geopotential e uma entrada no menu. NÃO precisa de root.

Para todos os usuários da máquina:

    sudo ./install.sh --system      # em /opt/geopotential

Conferir se ficou boa:

    geopotential --self-test        # tem de terminar em 59/59 checks passed

    Sem tela (por SSH):
    QT_QPA_PLATFORM=offscreen geopotential --self-test

Usar:

    geopotential                        # abre no dado de exemplo
    geopotential /caminho/para/um.tif   # abre num raster seu

Desinstalar:

    ./install.sh --uninstall
    sudo ./install.sh --system --uninstall

----------------------------------------------------------------

NÃO precisa instalar Python, conda, Qt, GDAL nem PROJ. Tudo isso vai
dentro do pacote.

A ÚNICA dependência de sistema, se a janela não abrir:

    sudo apt install libxcb-cursor0 libxkbcommon-x11-0

São as bibliotecas que conversam com o servidor gráfico — nenhum
pacote pode carregá-las consigo.

----------------------------------------------------------------

Se "geopotential: command not found":
    ~/.local/bin não está no PATH. Rode pelo caminho completo, ou:
    echo 'export PATH="\$PATH:\$HOME/.local/bin"' >> ~/.bashrc && source ~/.bashrc

Qualquer outro erro: rode  geopotential --self-test  e mande a saída.
Ela diz qual das 59 checagens falhou, e cada uma nomeia o que testa.

----------------------------------------------------------------

Linux x86_64. Windows e macOS precisam das suas próprias construções,
e nenhuma foi feita nem testada.

Detalhes: INSTALL.md, neste mesmo arquivo.
CARD

tar -czf "$archive" -C "$msp/dist" geopotential install.sh INSTALL.md COMO-INSTALAR.txt

# A checksum beside the archive, so whoever receives it can tell a truncated
# copy from a whole one before wondering why the application will not start.
( cd "$msp/dist" && sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256" )

installed="$(du -sh "$msp/dist/geopotential" | cut -f1)"
compressed="$(du -h "$archive" | cut -f1)"
checksum="$(cut -d" " -f1 "$archive.sha256")"

say "done"
cat <<SUMMARY
  app          $version   worker $worker_version
  binary       $msp/dist/geopotential/geopotential
  installed    $installed
  archive      $archive
  compressed   $compressed
  sha256       $checksum
               (also written to $archive.sha256)
  how to install   $card   (and inside the archive)

  Install elsewhere:  copy the archive, then
      tar -xzf $(basename "$archive")
      ./install.sh              (into ~/.local, no root)
      sudo ./install.sh --system  (into /opt, every user)

  Verified: --help, --worker --capabilities, --self-test and --screenshot,
  the last two with env -i (no PATH to this machine's environment).

  Linux x86_64, built from this machine's environment. Windows and macOS need
  their own runs and are untested.
SUMMARY
