FROM archlinux:latest
RUN pacman -Syu --noconfirm \
  alsa-lib \
  base-devel \
  desktop-file-utils \
  ffmpeg \
  git \
  glibc \
  hicolor-icon-theme \
  jack \
  lcms2 \
  libarchive \
  libass \
  libbluray \
  libcdio \
  libcdio-paranoia \
  libdrm \
  libdvdnav \
  libdvdread \
  libegl \
  libgl \
  libglvnd \
  libjpeg-turbo \
  libplacebo \
  libpulse \
  libsixel \
  libva \
  libvdpau \
  libx11 \
  libxext \
  libxkbcommon \
  libxpresent \
  libxrandr \
  libxss \
  libxv \
  luajit \
  mesa \
  meson \
  nasm \
  patchelf \
  libpipewire \
  rubberband \
  openal \
  uchardet \
  vulkan-headers \
  vulkan-icd-loader \
  wayland \
  wayland-protocols \
  wget \
  xorg-server-xvfb \
  zlib \
  zsync
  RUN pacman -S --noconfirm fuse2
  RUN pacman -S --noconfirm squashfs-tools
  RUN useradd -m builder
  USER builder
