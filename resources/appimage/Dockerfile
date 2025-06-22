FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive
RUN sed -i 's/htt[p|ps]:\/\/archive.ubuntu.com\/ubuntu\//mirror:\/\/mirrors.ubuntu.com\/mirrors.txt/g' /etc/apt/sources.list
RUN apt update && apt install -y git \
  build-essential \
  pkg-config \
  ninja-build \
  libgl1-mesa-dev \
  autotools-dev \
  autoconf \
  libtool \
  libfribidi-dev \
  libharfbuzz-dev \
  libfontconfig1-dev \
  libx11-dev \
  nasm \
  libxv-dev \
  libva-dev \
  liblcms2-dev \
  libdrm-dev \
  libasound2-dev \
  libgnutls28-dev \
  libmp3lame-dev \
  libvorbis-dev \
  libopus-dev \
  libtheora-dev \
  libvpx-dev \
  libx264-dev \
  libx265-dev \
  libpulse-dev \
  libxext-dev \
  libxpresent-dev \
  libxrandr-dev \
  libxss-dev \
  libwebp-dev \
  libxkbcommon-dev \
  libpulse-dev \
  libxkbcommon-x11-dev \
  binutils \
  python3-pip \
  fuse3 \
  libpipewire-0.2-dev \
  libfreetype-dev \
  glslang-dev \
  wget \
  libxcb-cursor0 libxcb-ewmh2 libxcb-icccm4 luajit libluajit-5.1-dev libpcsclite1 libxcb-keysyms1 libxcb-shape0 libjpeg-dev \ 
    libfontconfig1-dev \
    libfreetype-dev \
    libgtk-3-dev \
    libx11-dev \
    libx11-xcb-dev \
    libxcb-cursor-dev \
    libxcb-glx0-dev \
    libxcb-icccm4-dev \
    libxcb-image0-dev \
    libxcb-keysyms1-dev \
    libxcb-randr0-dev \
    libxcb-render-util0-dev \
    libxcb-shape0-dev \
    libxcb-shm0-dev \
    libxcb-sync-dev \
    libxcb-util-dev \
    libxcb-xfixes0-dev \
    libxcb-xkb-dev \
    libxcb1-dev \
    libxext-dev \
    libxfixes-dev \
    libxi-dev \
    libxkbcommon-dev \
    libxkbcommon-x11-dev \
    libxrender-dev \
    libmediainfo0v5
RUN pip3 install meson
RUN useradd -m builder
RUN wget https://github.com/Kitware/CMake/releases/download/v4.0.3/cmake-4.0.3-linux-x86_64.sh -O /tmp/cmake.sh
RUN chmod +x /tmp/cmake.sh && /tmp/cmake.sh --skip-license --prefix=/usr
RUN git clone https://github.com/google/shaderc.git /deps/shaderc && cd /deps/shaderc && /deps/shaderc/utils/git-sync-deps && mkdir -p /deps/shaderc/build && cd /deps/shaderc/build && \
  cmake -GNinja -DCMAKE_BUILD_TYPE=Release -DSHADERC_SKIP_TESTS=ON -DSHADERC_SKIP_EXAMPLES=ON \
  /deps/shaderc && \
  ninja && ninja install && rm -rf /deps/shaderc
RUN git clone https://github.com/Cyan4973/xxHash.git /deps/xxHash && cd /deps/xxHash && make && make install && rm -rf /deps/xxHash
RUN git clone https://code.videolan.org/videolan/dav1d.git /deps/dav1d && cd /deps/dav1d && git checkout 1.5.1 && \
  mkdir -p /deps/dav1d/build && cd /deps/dav1d/build && \
  meson setup .. --default-library=static --buildtype=release --prefix=/usr && \
  ninja && ninja install && rm -rf /deps/dav1d
#RUN git clone https://gitlab.freedesktop.org/wayland/wayland.git /deps/wayland
#RUN cd /deps/wayland && git checkout 1.24 && \
#  meson setup build --prefix=/usr -Ddocumentation=false -Ddtd_validation=false && \
#  ninja -C build install
#RUN git clone https://gitlab.freedesktop.org/wayland/wayland-protocols.git /deps/wayland-protocols
#RUN cd /deps/wayland-protocols && git checkout 1.45 && \
#  meson setup build --prefix=/usr -Dtests=false && \
#  ninja -C build install
RUN wget https://download.qt.io/official_releases/qt/6.9/6.9.1/single/qt-everywhere-src-6.9.1.tar.xz -O /tmp/qt.tar.xz && tar -xf /tmp/qt.tar.xz -C /deps && rm /tmp/qt.tar.xz && mkdir /deps/qt-build && cd /deps/qt-build && \
  /deps/qt-everywhere-src-6.9.1/configure -opensource -confirm-license -nomake examples -nomake tests -release -prefix /usr -skip qtwayland -skip qtwebengine -skip qtwebview -skip qt3d -skip qtdeclarative -skip qtscript -skip qtserialport -skip qttools -skip qtquick3d -skip qtxmlpatterns -skip qtcanvas3d -skip qtgraphs -skip qtlocation -skip qtdoc -skip qtlottie -skip qt5compat -skip qtmqtt -skip qtopcua -skip qtquick3dphysics -skip qtquickeffectmaker -skip qtquicktimeline -skip qttranslations -skip qtvirtualkeyboard -skip qtactiveqt -skip qtshadertools -skip qtmultimedia -skip qtspeech -skip qtcoap -skip qtconnectivity -skip qtdatavis3d -skip qtcharts -skip qtgrpc -skip qtwebsockets -skip qthttpserver -skip qtlanguageserver -skip qtpositioning -skip qtnetworkauth -skip qtremoteobjects -skip qtscmxml -skip qtsensors -skip qtserialbus -skip qtwebchannel -skip qtscxml && \
  cd /deps/qt-build && cmake --build . --parallel && cmake --install . && rm -rf /deps/qt-everywhere-src-6.9.1 /deps/qt-build
RUN git clone https://github.com/mpv-player/mpv-build.git /deps/mpv-build/ && cd /deps/mpv-build && echo "-Djavascript=disabled" > mpv_options \
  && echo "--disable-debug" > ffmpeg_options \
  && echo "--disable-doc" >> ffmpeg_options \
  && echo "--enable-encoder=png" >> ffmpeg_options \
  && echo "--enable-gnutls" >> ffmpeg_options \
  && echo "--enable-gpl" >> ffmpeg_options \
  && echo "--enable-version3" >> ffmpeg_options \
  && echo "--enable-libass" >> ffmpeg_options \
  && echo "--enable-libdav1d" >> ffmpeg_options \
  && echo "--enable-libfreetype" >> ffmpeg_options \
  && echo "--enable-libmp3lame" >> ffmpeg_options \
  && echo "--enable-libopus" >> ffmpeg_options \
  && echo "--enable-libtheora" >> ffmpeg_options \
  && echo "--enable-libvorbis" >> ffmpeg_options \
  && echo "--enable-libvpx" >> ffmpeg_options \
  && echo "--enable-libx264" >> ffmpeg_options \
  && echo "--enable-libx265" >> ffmpeg_options \
  && echo "--enable-libwebp" >> ffmpeg_options \
  && /deps/mpv-build/rebuild -j32 \
  && cp /deps/mpv-build/build_libs/bin/ffmpeg /usr/bin/ffmpeg \
  && cp /deps/mpv-build/mpv/build/libmpv.so.2.5.0 /usr/lib/libmpv.so.2.5.0 \
  && rm -rf /deps/mpv-build
