# Syng

Syng is an all-in-one karaoke software, consisting of a *backend server*, a *web frontend* and a *playback client*.
Karaoke performers can search a library using the web frontend, and add songs to the queue.
The playback client retrieves songs from the backend server and plays them in order.

Currently, songs can be accessed using the following sources:

  - **YouTube.** The backend server queries YouTube for the song and forwards the URL to the playback client. The playback client then downloads the video from YouTube for playback.
  - **S3.** The backend server holds a list of all file paths accessible through the s3 storage, and forwards the chosen path to the playback client. The playback client then downloads the needed files from the s3 for playback.
  - **Files.** Same as S3, but all files reside locally on the playback client.

The playback client uses `mpv` for playback and can therefore play a variety of file formats, such as `mp3+cdg`, `webm`, `mp4`, ...

# Installation

For a clean installation we recommend installing syng inside a virtualenv.

## Server

    pip install "syng[server] @ git+https://github.com/christofsteel/syng.git"

This installs the server part (`syng server`), if you want to self-host a syng server. There is a publicly available syng instance at https://syng.rocks.

## Client

    pip install "syng[client] @ git+https://github.com/christofsteel/syng.git"

This installs both the playback client (`syng client`) and a configuration GUI (`syng gui`). 

**Note:** You need to have `mpv` installed on the playback client.
