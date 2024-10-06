<p align="center">
    <img src="https://raw.githubusercontent.com/christofsteel/syng/refs/heads/main/resources/icons/hicolor/512x512/apps/rocks.syng.Syng.png"
        height="130">
<p align="center">

[![Matrix](https://img.shields.io/matrix/syng%3Amatrix.org?logo=matrix&label=%23syng%3Amatrix.org)](https://matrix.to/#/#syng:matrix.org)
[![PyPI - Version](https://img.shields.io/pypi/v/syng?logo=pypi)](https://pypi.org/project/syng/)
[![Flathub Version](https://img.shields.io/flathub/v/rocks.syng.Syng?logo=flathub)](https://flathub.org/apps/rocks.syng.Syng)
[![PyPI - License](https://img.shields.io/pypi/l/syng)](https://www.gnu.org/licenses/agpl-3.0.en.html)
[![Website](https://img.shields.io/website?url=https%3A%2F%2Fsyng.rocks%2F&label=syng.rocks)](https://syng.rocks)
[![Gitlab Pipeline Status](https://img.shields.io/gitlab/pipeline-status/christofsteel%2Fsyng2?gitlab_url=https%3A%2F%2Fgit.k-fortytwo.de%2F&branch=main&logo=python&label=mypy%2Bruff)](https://git.k-fortytwo.de/christofsteel/syng2)

Easily host karaoke events.

**Syng** is an all-in-one karaoke software, consisting of a *backend server*, a *web frontend* and a *playback client*.
Karaoke performers can search a library using the web frontend, and add songs to the queue.
The playback client retrieves songs from the backend server and plays them in order.

You can play songs from **YouTube**, an **S3** storage or simply share local **files**.

The playback client uses [mpv](https://mpv.io/) for playback and can therefore play a variety of file formats, such as `mp3+cdg`, `webm`, `mp4`, ...

# Client

[![Get in on Flathub](https://flathub.org/api/badge?locale=en)](https://flathub.org/apps/rocks.syng.Syng)

To host a karaoke event, you only need to use the playback client. You can use the publicly available instance at https://syng.rocks as your server.

## Installation

### Linux

The preferred way to install the client is via [Flathub](https://flathub.org/apps/rocks.syng.Syng).

Alternatively Syng can be installed via the _Python Package Index_ (PyPI). When installing the client it is mandatory to include the `client` flag:

    pip install 'syng[client]'

This installs both the playback client (`syng client`) and a configuration GUI (`syng gui`). 

**Note:** When installing via PyPI, you need to have [mpv](https://mpv.io/) installed on the playback client, and the `mpv` binary must be in your `PATH`.

### Windows

Windows support is experimental, but you can download the current version from [Releases](https://github.com/christofsteel/syng/releases). No installation necessary, you can just run the `exe`.


## Configuration

You can host karaoke events using the default configuration. But if you need more advanced configuration, you can either configure Syng using the GUI or via a text editor by editing `~/.config/syng/config.yaml`. There are the following settings:

  * `server`: URL of the server to connect to.
  * `room`: The room code for your karaoke event. Can be chosen arbitrarily, but must be unique. Unused rooms will be deleted after some time. _Note:_ Everyone, that has access to the room code can join the karaoke event.
  * `secret`: The admin password for your karaoke event. If you want to reconnect with a playback client to a room, these must match. Additionally, this unlocks admin capabilities to a web client, when given under "Advanced" in the web client.
  * `waiting_room_policy`: One of `none`, `optional`, `forced`. When a performer wants to be added to the playback queue, but has already a song queued, they can be added to the _waiting room_. `none` disables this behavior and performers can have multiple songs in the queue, `optional` gives the performer a notification, and they can decide for themselves, and `forced` puts them in the waiting room every time. Once the current song of a performer leaves the queue, the song from the waiting room will be added to the queue.
  * `last_song`: `none` or a time in [ISO 8601](https://en.wikipedia.org/wiki/ISO_8601). When a song is added to the queue, and its ending time exceeds this value, it is rejected.
  * `preview_duration`: Before every song, there is a short slide for the next performer. This sets how long it is shown in seconds.
  * `key`: If the server, you want to connect to is in _private_ or _restricted_ mode, this will authenticate the client. Private server reject unauthenticated playback clients, restricted servers limit the searching to be _client only_.
  * `mpv_options`: additional options forwarded to `mpv`.
  * `show_advanced`: show advanced options in the configuration GUI.

In addition to the general config, has its own configuration under the `sources` key of the configuration.

### YouTube

Configuration is done under `sources` → `youtube` with the following settings:

  * `enabled`: `true` or `false`.
  * `channels`: list of YouTube channels. If this is a nonempty list, Syng will only search these channels, otherwise YouTube will be searched as a whole.
  * `tmp_dir`: YouTube videos will be downloaded before playback. This sets the directory, where YouTube videos are stored.
  * `start_streaming`: `true` or `false`. If `true`, videos will be streamed directly using `mpv`, if the video is not cached beforehand. Otherwise, Syng waits for the video to be downloaded.  

### S3

Configuration is done under `sources` → `s3` with the following settings:

  * `enabled`: `true` or `false`.
  * `extensions`: List of extensions to be searched. For karaoke songs, that separate audio and video (e.g. CDG files), you can use `mp3+cdg` to signify, that the audio part is a `mp3` file and the video is a `cdg` file. For karaoke songs, that do not separate this (e.g. mp4 files), you can simply use `mp4`.
  * `endpoint`: Endpoint of the s3.
  * `access_key` Access key for the s3.
  * `secret_key`: Secret key for the s3.
  * `secure`: If `true` uses `ssl`, otherwise not.
  * `bucket`: Bucket for the karaoke files.
  * `index_file`: Cache file, that contains the filenames of the karaoke files in the s3.
  * `tmp_dir`: Temporary download directory of the karaoke files.

### Files

Configuration is done under `sources` → `files` with the following settings:

  * `enabled`: `true` or `false`.
  * `extensions`: List of extensions to be searched. For karaoke songs, that separate audio and video (e.g. CDG files), you can use `mp3+cdg` to signify, that the audio part is a `mp3` file and the video is a `cdg` file. For karaoke songs, that do not separate this (e.g. mp4 files), you can simply use `mp4`.
  * `dir`: Directory, where the karaoke files are stored. 

### Default configuration

```
config:
  key: ''
  last_song: null
  preview_duration: 3
  room: <Random room code>
  secret: <Random secret>
  server: https://syng.rocks
  waiting_room_policy: none
  mpv_options: ''
  show_advanced: False
sources:
  files:
    dir: .
    enabled: false
    extensions:
    - mp3+cdg
  s3:
    access_key: ''
    bucket: ''
    enabled: false
    endpoint: ''
    extensions:
    - mp3+cdg
    index_file: ~/.cache/syng/s3-index
    secret_key: ''
    secure: true
    tmp_dir: /tmp/syng
  youtube:
    channels: []
    enabled: true
    start_streaming: false
    tmp_dir: /tmp/syng
```

# Server

If you want to host your own Syng server, you can do that, but you can also use the publicly available Syng instance at https://syng.rocks.

## Installation

Installation is done via pip.

    pip install 'syng[server]'

## Running

Running `syng server` will start the server.
  
## Configuration

Configuration is done via command line arguments, see `syng server --help` for an overview. 
