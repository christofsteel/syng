#!/usr/bin/env bash

PKGDIR=usr/lib/python3.13/site-packages
cd /app
if [ ! -x /app/python3.13.5-cp313-cp313-manylinux2014_x86_64.AppImage ]; then
  echo "Downloading Python 3.13 AppImage..."
  wget https://github.com/niess/python-appimage/releases/download/python3.13/python3.13.5-cp313-cp313-manylinux2014_x86_64.AppImage
  chmod +x python3.13.5-cp313-cp313-manylinux2014_x86_64.AppImage
else
  echo "Python 3.13 AppImage already exists."
fi
if [ ! -x /app/linuxdeploy-x86_64.AppImage ]; then
  echo "Downloading linuxdeploy AppImage..."
  wget https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
  chmod +x linuxdeploy-x86_64.AppImage
else
  echo "linuxdeploy AppImage already exists."
fi
if [ ! -x /app/linuxdeploy-plugin-qt-x86_64.AppImage ]; then
  echo "Downloading linuxdeploy-plugin-qt AppImage..."
  wget https://github.com/linuxdeploy/linuxdeploy-plugin-qt/releases/download/1-alpha-20250213-1/linuxdeploy-plugin-qt-x86_64.AppImage
  chmod +x linuxdeploy-plugin-qt-x86_64.AppImage
else
  echo "linuxdeploy-plugin-qt AppImage already exists."
fi
if [ ! -d /app/syng ]; then
  echo "Cloning Syng repository..."
  git clone https://github.com/christofsteel/syng.git /app/syng
else
  echo "Syng repository already exists."
fi

# if [ ! -x /app/mpv/mpv-build/mpv/build/libmpv.so.2.5.0 ]; then
#   echo "Building MPV..."
#   mkdir -p /app/mpv
#   cd /app/mpv
#   git clone https://github.com/mpv-player/mpv-build.git
#   cd mpv-build
#   echo "-Dlibmpv=true" > mpv_options
#   echo "-Djavascript=disabled" >> mpv_options
#   echo "--disable-debug" > ffmpeg_options
#   echo "--disable-doc" >> ffmpeg_options
#   echo "--enable-encoder=png" >> ffmpeg_options
#   echo "--enable-gnutls" >> ffmpeg_options
#   echo "--enable-gpl" >> ffmpeg_options
#   echo "--enable-version3" >> ffmpeg_options
#   echo "--enable-libass" >> ffmpeg_options
#   echo "--enable-libdav1d" >> ffmpeg_options
#   echo "--enable-libfreetype" >> ffmpeg_options
#   echo "--enable-libmp3lame" >> ffmpeg_options
#   echo "--enable-libopus" >> ffmpeg_options
#   echo "--enable-libtheora" >> ffmpeg_options
#   echo "--enable-libvorbis" >> ffmpeg_options
#   echo "--enable-libvpx" >> ffmpeg_options
#   echo "--enable-libx264" >> ffmpeg_options
#   echo "--enable-libx265" >> ffmpeg_options
#   echo "--enable-libwebp" >> ffmpeg_options
#   # echo "--enable-vulkan" >> ffmpeg_options
#   ./rebuild -j32
#
#   cd /app
# else
#   echo "MPV build already exists."
# fi

if [ ! -d /app/AppDir ]; then
  echo "Extracting Python AppImage..."
  /app/python3.13.5-cp313-cp313-manylinux2014_x86_64.AppImage --appimage-extract
  mv /app/squashfs-root /app/AppDir

  echo "Copy FFmpeg and MPV libraries..."
  cp /usr/bin/ffmpeg /app/AppDir/usr/bin/ffmpeg
  cp /usr/lib/libmpv.so.2.5.0 /app/AppDir/usr/lib/libmpv.so.2.5.0
  cp /usr/bin/ld /app/AppDir/usr/bin/ld

  ln -s libmpv.so.2.5.0 /app/AppDir/usr/lib/libmpv.so.2
  ln -s libmpv.so.2 /app/AppDir/usr/lib/libmpv.so

echo "Copy xcb libraries..."
# qt6 needs them
cp /usr/lib/x86_64-linux-gnu/libxcb-ewmh* /app/AppDir/usr/lib/
cp /usr/lib/x86_64-linux-gnu/libxcb-icccm* /app/AppDir/usr/lib/
cp /usr/lib/x86_64-linux-gnu/libxcb-keysyms* /app/AppDir/usr/lib/
cp /usr/lib/x86_64-linux-gnu/libxcb* /app/AppDir/usr/lib/

/app/AppDir/opt/python3.13/bin/python3.13 -m pip install syng[client] --no-binary pillow --target=/app/AppDir/$PKGDIR

echo "Modifying AppDir structure..."

rm /app/AppDir/python3.13.5.desktop /app/AppDir/python.png /app/AppDir/usr/share/applications/python3.13.5.desktop

cat <<EOF > /app/AppDir/usr/share/applications/rocks.syng.Syng.desktop
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
cp /app/bin/syng /app/AppDir/usr/bin/syng
cp /app/bin/yt-dlp /app/AppDir/usr/bin/yt-dlp
cp /usr/bin/ld /app/AppDir/usr/bin/ld
chmod +x /app/AppDir/usr/bin/syng
rm /app/AppDir/AppRun
cp /app/syng/resources/flatpak/rocks.syng.Syng.yaml /app/AppDir/usr/share/metainfo/rocks.syng.Syng.appdata.xml
else
  echo "Python AppImage already extracted."
fi

echo "Patching mpv.py..."
patch -p0 < libmpv.patch

echo "Removing unnecessary files..."
for plugin in assetimporters generic help "imageformats/libqpdf.so" networkinformation position qmllint renderers sceneparsers sensors tls wayland-graphics-integration-client sqldrivers webview egldeviceintegrations geometryloaders multimedia platforminputcontexts printsupport qmlls renderplugins scxmldatamodel texttospeech wayland-decoration-client wayland-shell-integration; do
  rm -rf /app/AppDir/usr/lib/python3.13/site-packages/PyQt6/Qt6/plugins/$plugin
done
for lib in libavcodec.so.61 libQt6PdfQuick.so.6 libQt6Quick3DIblBaker.so.6 libQt6QuickControls2Material.so.6 libQt6QuickTimeline.so.6 libQt6Test.so.6 \
libavformat.so.61 libQt6Help.so.6 libQt6Pdf.so.6 libQt6Quick3DParticles.so.6 libQt6QuickControls2MaterialStyleImpl.so.6 libQt6QuickVectorImageGenerator.so.6 libQt6TextToSpeech.so.6 \
libavutil.so.59 libQt6LabsAnimation.so.6 libQt6PdfWidgets.so.6 libQt6Quick3DPhysicsHelpers.so.6 libQt6QuickControls2.so.6 libQt6QuickVectorImage.so.6 \
libQt6LabsFolderListModel.so.6 libQt6PositioningQuick.so.6 libQt6Quick3DPhysics.so.6 libQt6QuickControls2Universal.so.6 libQt6QuickWidgets.so.6 libQt6WaylandEglClientHwIntegration.so.6 \
libQt6LabsPlatform.so.6 libQt6Positioning.so.6 libQt6Quick3DRuntimeRender.so.6 libQt6QuickControls2UniversalStyleImpl.so.6 libQt6RemoteObjectsQml.so.6 libQt6WebChannelQuick.so.6 \
libQt6LabsQmlModels.so.6 libQt6PrintSupport.so.6 libQt6Quick3D.so.6 libQt6QuickDialogs2QuickImpl.so.6 libQt6RemoteObjects.so.6 libQt6WebChannel.so.6 \
libQt6Bluetooth.so.6 libQt6LabsSettings.so.6 libQt6QmlMeta.so.6 libQt6Quick3DSpatialAudio.so.6 libQt6QuickDialogs2.so.6 libQt6SensorsQuick.so.6 libQt6WebSockets.so.6 \
libQt6Concurrent.so.6 libQt6LabsSharedImage.so.6 libQt6QmlModels.so.6 libQt6Quick3DUtils.so.6 libQt6QuickDialogs2Utils.so.6 libQt6Sensors.so.6 \
libQt6LabsWavefrontMesh.so.6 libQt6Qml.so.6 libQt6Quick3DXr.so.6 libQt6QuickEffects.so.6 libQt6SerialPort.so.6 libQt6WlShellIntegration.so.6 \
libQt6MultimediaQuick.so.6 libQt6QmlWorkerScript.so.6 libQt6QuickControls2Basic.so.6 libQt6QuickLayouts.so.6 libQt6ShaderTools.so.6 \
libQt6Designer.so.6 libQt6Multimedia.so.6 libQt6Quick3DAssetImport.so.6 libQt6QuickControls2BasicStyleImpl.so.6 libQt6QuickParticles.so.6 libQt6SpatialAudio.so.6 \
libQt6FFmpegStub-crypto.so.3 libQt6MultimediaWidgets.so.6 libQt6Quick3DAssetUtils.so.6 libQt6QuickControls2Fusion.so.6 libQt6QuickShapes.so.6 libQt6Sql.so.6 libswresample.so.5 \
libQt6FFmpegStub-ssl.so.3 libQt6Network.so.6 libQt6Quick3DEffects.so.6 libQt6QuickControls2FusionStyleImpl.so.6 libQt6Quick.so.6 libQt6StateMachineQml.so.6 libswscale.so.8 \
libQt6FFmpegStub-va-drm.so.2 libQt6Nfc.so.6 libQt6Quick3DGlslParser.so.6 libQt6QuickControls2Imagine.so.6 libQt6QuickTemplates2.so.6 libQt6StateMachine.so.6 \
libQt6FFmpegStub-va.so.2 libQt6Quick3DHelpersImpl.so.6 libQt6QuickControls2ImagineStyleImpl.so.6 libQt6QuickTest.so.6  \
libQt6FFmpegStub-va-x11.so.2 libQt6OpenGLWidgets.so.6 libQt6Quick3DHelpers.so.6 libQt6QuickControls2Impl.so.6 libQt6QuickTimelineBlendTrees.so.6 libQt6WaylandClient.so.6; do
  echo "Removing Qt library: $lib"
  rm /app/AppDir/usr/lib/python3.13/site-packages/PyQt6/Qt6/lib/$lib
done

for platform in libqeglfs.so libqlinuxfb.so libqminimalegl.so libqminimal.so libqoffscreen.so libqvkkhrdisplay.so libqvnc.so libqwayland-egl.so libqwayland-generic.so; do
  echo "Removing Qt platform plugin: $platform"
  rm /app/AppDir/usr/lib/python3.13/site-packages/PyQt6/Qt6/plugins/platforms/$platform
done

for lib in QtHelp.abi3.so QtNfc.abi3.so QtPdfWidgets.abi3.so QtQuick3D.abi3.so QtSensors.abi3.so QtStateMachine.abi3.so QtTextToSpeech.abi3.so \
QtMultimedia.abi3.so QtPositioning.abi3.so QtQuick.abi3.so QtSerialPort.abi3.so QtWebChannel.abi3.so \
QtDesigner.abi3.so QtMultimediaWidgets.abi3.so QtOpenGLWidgets.abi3.so QtPrintSupport.abi3.so QtQuickWidgets.abi3.so QtSpatialAudio.abi3.so QtWebSockets.abi3.so \
QtBluetooth.abi3.so QtNetwork.abi3.so QtPdf.abi3.so QtQml.abi3.so QtRemoteObjects.abi3.so QtSql.abi3.so QtTest.abi3.so; do
  echo "Removing PyQt6 library: $lib"
  rm /app/AppDir/usr/lib/python3.13/site-packages/PyQt6/$lib
done

# rm /app/AppDir/usr/lib/python3.13/site-packages/PyQt6/Qt6/translations/*

echo "Removing unnecessary QML files..."
rm -rf /app/AppDir/usr/lib/python3.13/site-packages/PyQt6/Qt6/qml/
# ln -s python3.13/site-packages/PyQt6/Qt6/ /app/AppDir/usr/lib/qt6
# for file in /app/AppDir/usr/lib/python3.13/site-packages/PyQt6/Qt6/lib/*; do
#   echo "Linking $file to /app/AppDir/usr/lib/$(basename $file)"
#   relative_path=$(realpath --relative-to=/app/AppDir/usr/lib/ $file)
#   ln -s "$relative_path" /app/AppDir/usr/lib/$(basename $file)
# done

# echo "Creating AppImage..."
# /app/linuxdeploy-x86_64.AppImage --plugin qt --appdir /app/AppDir --output appimage
