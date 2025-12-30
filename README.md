<p align="center">
    <img src="https://raw.githubusercontent.com/christofsteel/syng/refs/heads/main/resources/icons/hicolor/512x512/apps/rocks.syng.Syng.png"
        height="130">

_Easily host karaoke events_
<p align="center">

[![Matrix](https://img.shields.io/matrix/syng%3Amatrix.org?logo=matrix&label=%23syng%3Amatrix.org)](https://matrix.to/#/#syng:matrix.org)
[![Mastodon Follow](https://img.shields.io/mastodon/follow/113266262154630635?domain=https%3A%2F%2Ffloss.social&style=flat&logo=mastodon&logoColor=white)](https://floss.social/@syng)
[![PyPI - Version](https://img.shields.io/pypi/v/syng?logo=pypi)](https://pypi.org/project/syng/)
[![Flathub Version](https://img.shields.io/flathub/v/rocks.syng.Syng?logo=flathub)](https://flathub.org/apps/rocks.syng.Syng)
[![PyPI - License](https://img.shields.io/pypi/l/syng)](https://www.gnu.org/licenses/agpl-3.0.en.html)
[![Website](https://img.shields.io/website?url=https%3A%2F%2Fsyng.rocks%2F&label=syng.rocks)](https://syng.rocks)
[![Forgejo Pipeline Status](https://git.k-fortytwo.de/christofsteel/syng/badges/workflows/check.yaml/badge.svg?logo=python&label=mypy%2Bruff)](https://git.k-fortytwo.de/christofsteel/syng)


**Syng.Rocks!** is an all-in-one karaoke software, consisting of a *backend server*, a *web frontend* and a *playback client*.
Karaoke performers can search a library using the web frontend, and add songs to the queue.
The playback client retrieves songs from the backend server and plays them in order.

You can play songs from **YouTube**, an **S3** storage or simply share local **files**.

The playback client uses [mpv](https://mpv.io/) for playback and can therefore play a variety of file formats, such as `mp3+cdg`, `webm`, `mp4`, ...

Join our [matrix room](https://matrix.to/#/#syng:matrix.org) or follow us on [mastodon](https://floss.social/@syng) for update notifications and support.

# Screenshots
<img src="https://raw.githubusercontent.com/christofsteel/syng/b963d09aee58531ab7ea61ddf04ee169fba57a63/resources/screenshots/syng.png" alt="Main Window" height=200/> <img src="https://raw.githubusercontent.com/christofsteel/syng/b963d09aee58531ab7ea61ddf04ee169fba57a63/resources/screenshots/syng_advanced.png" alt="Main Window (Advanced)" height=200/>

<img src="https://raw.githubusercontent.com/christofsteel/syng/b963d09aee58531ab7ea61ddf04ee169fba57a63/resources/screenshots/syng_web2.png" alt="Web Interface" height=200/> <img src="https://raw.githubusercontent.com/christofsteel/syng/b963d09aee58531ab7ea61ddf04ee169fba57a63/resources/screenshots/syng_mobile_search.png" alt="Web Interface on Mobile" height=200/> 

<img src="https://raw.githubusercontent.com/christofsteel/syng/b963d09aee58531ab7ea61ddf04ee169fba57a63/resources/screenshots/syng_player_next_up.png" alt="Player (next up)" height=200/> <img src="https://raw.githubusercontent.com/christofsteel/syng/b963d09aee58531ab7ea61ddf04ee169fba57a63/resources/screenshots/syng_player_song.png" alt="Player playing a song" height=200/>

# Client

[![Get in on Flathub](https://flathub.org/api/badge?locale=en)](https://flathub.org/apps/rocks.syng.Syng)

To host a karaoke event, you only need to use the playback client. You can use the publicly available instance at https://syng.rocks as your server.

## Installation

### Linux

The preferred way to install the client is via [Flathub](https://flathub.org/apps/rocks.syng.Syng).

Alternatively Syng.Rocks! can be installed via the _Python Package Index_ (PyPI). When installing the client it is mandatory to include the `client` flag:

    pip install 'syng[client]'

This installs both the playback client (`syng client`) and a configuration GUI (`syng gui`). 

**Note:** When installing via PyPI, you need to have [libmpv](https://mpv.io/) installed on machine of the playback client. Additionally, since version 2.2.1, you also need to have [deno](https://github.com/denoland/deno/) installed for proper YouTube support.

The Syng.Rocks! client is also packaged for Arch Linux in the [Arch Linux user repository](https://aur.archlinux.org/packages/syng-client)

### Windows

Windows support is experimental, but you can download the current version from [Releases](https://github.com/christofsteel/syng/releases). No installation necessary, you can just run the `exe`.


## Usage

See [Website](https://site.syng.rocks).

# Server

If you want to host your own Syng.Rocks! server, you can do that, but you can also use the publicly available Syng.Rocks! instance at https://syng.rocks.

## Python Package Index

You can install the server via pip:

    pip install syng

and then run via:

    syng server

The server is also automatically available if you install the client. 

There exists one optional dependency for the server: `alt-profanity-check`. If this package is installed, each username is checked for profanity, otherwise no such check happens.

## Docker

Alternatively you can run the server using docker. It listens on port 8080 and reads a key file at `/app/keys.txt` when configured as private or restricted.

    docker run --rm -v /path/to/your/keys.txt:/app/keys.txt -p 8080:8080 ghcr.io/christofsteel/syng -H 0.0.0.0

## Arch Linux

The Syng.Rocks! server is also packaged for Arch Linux in the [Arch Linux user repository](https://aur.archlinux.org/packages/syng-server)

## Configuration

See [Website](https://site.syng.rocks).
