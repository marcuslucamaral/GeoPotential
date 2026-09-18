#!/usr/bin/env bash
#
# Install GeoPotential Professional on this machine.
#
#   ./install.sh                 into ~/.local  (no root, just this user)
#   sudo ./install.sh --system   into /opt      (every user on the machine)
#   ./install.sh --uninstall     remove what was installed
#
# This script ships **inside** the archive, beside the `geopotential/` folder
# it installs. Untar, cd in, run it.
#
# There is nothing to compile and nothing to download: the bundle carries its
# own Python, Qt, GDAL and PROJ. What this adds is the three things that make a
# folder an application — a stable location, a command on PATH, and an entry in
# the desktop menu.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
payload="$here/geopotential"

mode="user"
action="install"
for arg in "$@"; do
    case "$arg" in
        --system)    mode="system" ;;
        --user)      mode="user" ;;
        --uninstall) action="uninstall" ;;
        -h|--help)   sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$mode" = "system" ]; then
    prefix="/opt/geopotential"
    bindir="/usr/local/bin"
    desktop="/usr/share/applications"
else
    prefix="$HOME/.local/share/geopotential"
    bindir="$HOME/.local/bin"
    desktop="$HOME/.local/share/applications"
fi

launcher="$bindir/geopotential"
entry="$desktop/geopotential.desktop"

# ---- uninstall -----------------------------------------------------------
if [ "$action" = "uninstall" ]; then
    rm -rf "$prefix"
    rm -f "$launcher" "$entry"
    echo "removed $prefix, $launcher and $entry"
    echo "your projects were not touched: they are wherever you saved them."
    exit 0
fi

# ---- install -------------------------------------------------------------
[ -d "$payload" ] || {
    echo "ERROR: $payload is not here." >&2
    echo "       Run this from inside the extracted archive." >&2
    exit 1
}

if [ "$mode" = "system" ] && [ "$(id -u)" != "0" ]; then
    echo "ERROR: --system installs into /opt and needs root." >&2
    echo "       Either:  sudo ./install.sh --system" >&2
    echo "       or:      ./install.sh          (into ~/.local, no root)" >&2
    exit 1
fi

echo "installing into $prefix"
mkdir -p "$(dirname "$prefix")" "$bindir" "$desktop"
rm -rf "$prefix"
cp -a "$payload" "$prefix"

# A launcher rather than a symlink into the bundle: the binary re-launches
# itself to start the worker, and it must find the libraries beside it.
cat > "$launcher" <<EOF
#!/usr/bin/env bash
exec "$prefix/geopotential" "\$@"
EOF
chmod +x "$launcher"

cat > "$entry" <<EOF
[Desktop Entry]
Type=Application
Name=GeoPotential Professional
GenericName=Spatial multicriteria analysis
Comment=Análise multicritério espacial para dados geopotenciais e GIS
Exec=$launcher %F
Terminal=false
Categories=Science;Geoscience;Education;
Keywords=GIS;MCDA;AHP;raster;geofísica;
MimeType=image/tiff;text/csv;
EOF

if command -v update-desktop-database > /dev/null 2>&1; then
    update-desktop-database "$desktop" > /dev/null 2>&1 || true
fi

echo
echo "installed."
echo "  application   $prefix"
echo "  command       $launcher"
echo "  menu entry    $entry"

case ":$PATH:" in
    *":$bindir:"*) echo "  run it with:  geopotential" ;;
    *)
        echo
        echo "  NOTE: $bindir is not on your PATH."
        echo "        Run it with:  $launcher"
        echo "        Or add it:    echo 'export PATH=\"\$PATH:$bindir\"' >> ~/.bashrc"
        ;;
esac

echo
echo "  Check it works here:  $launcher --self-test"
