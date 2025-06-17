#!/usr/bin/env bash

mkdir /app && cd /app
if [ ! -x /app/python3.13.5-cp313-cp313-manylinux_2_28_x86_64.AppImage ]; then
  echo "Downloading Python 3.13 AppImage..."
  wget https://github.com/niess/python-appimage/releases/download/python3.13/python3.13.5-cp313-cp313-manylinux_2_28_x86_64.AppImage
  chmod +x python3.13.5-cp313-cp313-manylinux_2_28_x86_64.AppImage
else
  echo "Python 3.13 AppImage already exists."
fi
if [ ! -x /app/linuxdeploy-x86_64.AppImage ]; then
  echo "Downloading linuxdeploy AppImage..."
  wget https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
  chmod +x linuxdeploy-x86_64.AppImage
  # ./linuxdeploy-x86_64.AppImage --appimage-extract
  # rm linuxdeploy-x86_64.AppImage
  # rm squashfs-root/usr/bin/strip
  # cp /usr/bin/strip squashfs-root/usr/bin/strip
  # squashfs-root/plugins/linuxdeploy-plugin-appimage/appimagetool-prefix/usr/bin/appimagetool -gn squashfs-root/
  # rm -r squashfs-root
else
  echo "linuxdeploy AppImage already exists."
fi
if [ ! -x /app/linuxdeploy-plugin-qt-x86_64.AppImage ]; then
  echo "Downloading linuxdeploy-plugin-qt AppImage..."
  wget https://github.com/linuxdeploy/linuxdeploy-plugin-qt/releases/download/continuous/linuxdeploy-plugin-qt-x86_64.AppImage
  chmod +x linuxdeploy-plugin-qt-x86_64.AppImage
else
  echo "linuxdeploy-plugin-qt AppImage already exists."
fi

if [ ! -x /app/ffmpeg-linux-x64 ]; then
  echo "Downloading ffmpeg static binary..."
  wget https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-linux-x64
  chmod +x ffmpeg-linux-x64
else
  echo "ffmpeg static binary already exists."
fi

if [ ! -d /app/syng ]; then
  echo "Cloning Syng repository..."
  git clone https://github.com/christofsteel/syng.git /app/syng
else
  echo "Syng repository already exists."
fi

if [ -d /app/AppDir ]; then
  echo "Directory /app/AppDir already exists, deleting..."
  rm -rf /app/AppDir
fi

if [ ! -x /app/mpv/mpv-build/mpv/build/libmpv.so.2.5.0 ]; then
  echo "Building MPV..."
  mkdir -p /app/mpv
  cd /app/mpv
  git clone https://github.com/mpv-player/mpv-build.git
  cd mpv-build
  echo "-Dlibmpv=true" > mpv_options
  ./rebuild -j16

  cd /app
else
  echo "MPV build already exists."
fi
echo "Building MPV..."

/app/python3.13.5-cp313-cp313-manylinux_2_28_x86_64.AppImage --appimage-extract
mv /app/squashfs-root /app/AppDir

echo "Copy FFmpeg and MPV libraries..."
cp /app/ffmpeg-linux-x64 /app/AppDir/usr/bin/ffmpeg
cp /app/mpv/build_libs/bin/ffmpeg /app/AppDir/usr/bin/ffmpeg

cp /app/mpv/mpv-build/mpv/build/libmpv.so.2.5.0 /app/AppDir/usr/lib/libmpv.so.2.5.0
ln -s libmpv.so.2.5.0 /app/AppDir/usr/lib/libmpv.so.2
ln -s libmpv.so.2.5.0 /app/AppDir/usr/lib/libmpv.so

/app/AppDir/opt/python3.13/bin/python3.13 -m pip install syng[client] --target=/app/AppDir/packages

echo "Modifying AppDir structure..."

rm /app/AppDir/python3.13.5.desktop /app/AppDir/python.png /app/AppDir/usr/share/applications/python3.13.5.desktop

cat <<EOF > /app/AppDir/usr/share/applications/syng.desktop
[Desktop Entry]
Version=1.0
Type=Application

Name=Syng

Comment=An all-in-one karaoke player

Exec=syng
Icon=rocks.syng.Syng
Categories=AudioVideo
EOF

cp /app/syng/resources/icons/hicolor/256x256/apps/rocks.syng.Syng.png /app/AppDir/usr/share/icons/hicolor/256x256/apps/
APPRUN_LENGTH=$(wc -l < /app/AppDir/AppRun | cut -d' ' -f1)
head -n $(($APPRUN_LENGTH - 2)) /app/AppDir/AppRun > /app/AppDir/AppRun.tmp
echo 'export LD_LIBRARY_PATH="$APPDIR/usr/lib:$LD_LIBRARY_PATH"' >> /app/AppDir/AppRun.tmp
echo 'export PYTHONPATH="$APPDIR/packages"' >> /app/AppDir/AppRun.tmp
echo '"$APPDIR/opt/python3.13/bin/python3.13" -m syng "$@"' >> /app/AppDir/AppRun.tmp
mv /app/AppDir/AppRun.tmp /app/AppDir/usr/bin/syng
chmod +x /app/AppDir/usr/bin/syng
rm /app/AppDir/AppRun
# ln -s usr/bin/syng /app/AppDir/AppRun

export EXTRA_PLATFORM_PLUGINS=wayland
echo "Building AppImage..."
export NO_STRIP=true
/app/linuxdeploy-x86_64.AppImage --appdir /app/AppDir --output appimage
