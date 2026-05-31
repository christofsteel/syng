#!/usr/bin/env bash

function get_latest_release() {
  PROJECT=$1
  curl -s https://api.github.com/repos/$PROJECT/releases/latest | jq '.assets[] | .browser_download_url'
}

function get_tag_from_url() {
  sed "s!.*/download/\([^/]*\).*!\1!" <<< $1
}

function get_hash_from_url() {
  sed "s!.*git-\([^\.]*\)\.7z\"!\1!" <<< $1
}

function get_latest_python() {
  curl -s https://www.python.org/api/v2/downloads/release/?format=json | jq '.[] | .name' | grep -P "^\"Python \d+.\d+.\d+\"$" | sed 's/"Python \(.*\)"/\1/' | sort --version-sort | tail -n 1
}

function get_latest_tag() {
  PROJECT=$1
  curl -s https://api.github.com/repos/$PROJECT/releases/latest | jq '.tag_name' | sed 's/\"\(.*\)\"/\1/'
}

echo get wine version 1>&2
WINE_VERSION=$(get_latest_tag Kron4ek/Wine-Builds)
echo get mpv version 1>&2
MPV_NIGHTLY_URL="$(get_latest_release shinchiro/mpv-winbuild-cmake | grep mpv-dev-x86_64 | head -n 1)"
MPV_NIGHTLY=$(get_tag_from_url "$MPV_NIGHTLY_URL")
MPV_HASH=$(get_hash_from_url "$MPV_NIGHTLY_URL")
echo get ffmpeg version 1>&2
FFMPEG_NIGHTLY_URL="$(get_latest_release shinchiro/mpv-winbuild-cmake | grep ffmpeg-x86_64 | head -n 1)"
FFMPEG_HASH=$(get_hash_from_url "$FFMPEG_NIGHTLY_URL")
echo get python version 1>&2
PYTHON_VERSION=$(get_latest_python)
echo get mono version 1>&2
MONO_VERSION=$(get_latest_tag wine-mono/wine-mono | sed "s/wine-mono-\(.*\)/\1/")
echo get deno version 1>&2
DENO_VERSION=$(get_latest_tag denoland/deno | sed "s/v\(.*\)/\1/") 


echo WINE_VERSION=$WINE_VERSION
echo MPV_NIGHTLY=$MPV_NIGHTLY
echo MPV_HASH=$MPV_HASH
echo FFMPEG_HASH=$FFMPEG_HASH
echo PYTHON_VERSION=$PYTHON_VERSION
echo MONO_VERSION=$MONO_VERSION
echo DENO_VERSION=$DENO_VERSION

