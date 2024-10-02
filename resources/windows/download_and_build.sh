#!/usr/bin/env bash

mkdir -p src
mkdir -p requirements
cd requirements

# download mpv
wget https://nightly.link/mpv-player/mpv/workflows/build/master/mpv-x86_64-windows-msvc.zip
unzip mpv-x86_64-windows-msvc.zip
cp mpv.exe ../src
cp vulkan-1.dll ../src

# download ffmpeg
wget https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.7z
7z x ffmpeg-release-full.7z
cp ffmpeg-7.1-full_build/bin/ffmpeg.exe ../src


cd ..
rm -rf requirements

cp ../../requirements-client.txt src/requirements.txt
cp -r ../../syng/ src/
cp ../icons/syng.ico src/

# docker run --volume "$(pwd)/src:/src/" batonogov/pyinstaller-linux:latest "pyinstaller --onefile syng/main.py"
# rm -rf src/build
# rm -rf src/dist
# docker run --volume "$(pwd)/src:/src/" batonogov/pyinstaller-windows:latest "pyinstaller --onefile -w -i'.\syng.ico' --add-data='.\syng\static\syng.png;.\static' --add-binary '.\mpv.exe;.' --add-binary '.\vulkan-1.dll;.' --add-binary '.\ffmpeg.exe;.' syng/main.py"
docker run --volume "$(pwd)/src:/src/" batonogov/pyinstaller-windows:latest "pyinstaller -F -w -i'.\syng.ico' --add-data='.\syng.ico;.' --add-binary '.\mpv.exe;.' --add-binary '.\vulkan-1.dll;.' --add-binary '.\ffmpeg.exe;.' syng/main.py"

# cd syng-2.0.1
# wine python -m poetry install -E client
# wine poetry run pyinstaller -w syng/main.py
# cp -rv build /out
# cp -rv dist /out
