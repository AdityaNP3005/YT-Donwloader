#!/bin/sh
# Install launcher and icons for the current Linux user; no administrator needed.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
data_dir=${XDG_DATA_HOME:-"$HOME/.local/share"}
mkdir -p "$data_dir/applications"
for size in 16 24 32 48 64 128 256 512; do
    icon_dir="$data_dir/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$icon_dir"
    cp "$project_dir/assets/youtube-downloader-$size.png" "$icon_dir/youtube-downloader.png"
done
mkdir -p "$data_dir/icons/hicolor/scalable/apps"
cp "$project_dir/assets/youtube-downloader.svg" "$data_dir/icons/hicolor/scalable/apps/youtube-downloader.svg"
cat > "$data_dir/applications/youtube-downloader.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=YouTube Downloader
Comment=Download YouTube videos and playlists
Exec="$project_dir/run.sh"
Path=$project_dir
Icon=youtube-downloader
Terminal=false
Categories=AudioVideo;Video;
StartupNotify=true
StartupWMClass=Youtubedownloader
EOF
if command -v desktop-file-validate >/dev/null; then
    desktop-file-validate "$data_dir/applications/youtube-downloader.desktop"
fi
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "$data_dir/applications"
fi
if command -v gtk-update-icon-cache >/dev/null; then
    gtk-update-icon-cache -f -t "$data_dir/icons/hicolor" >/dev/null 2>&1 || true
fi
echo 'YouTube Downloader launcher and app icons installed.'
