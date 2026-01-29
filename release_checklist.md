# Release Checklist

## General

[ ] Update integrated webclient
[ ] Update dependencies
[ ] Create lockfile
[ ] Create requirements-client.txt and requirements.txt
[ ] Commit and push last changes
[ ] Update version number with uv
[ ] Test that it runs with own server
[ ] Commit and push

## Docker

[ ] Build main and deploy to beta

## Flatpak

[ ] Create new screenshots if needed and commit
[ ] Update metainfo.xml
[ ] Commit and push
[ ] check for new flatpak-pip-generator
[ ] build python yamls via script
[ ] copy up to date rocks.syng.Syng.yaml from flathub repo
[ ] update git hash
[ ] uninstall Syng
[ ] flatpak-builder --force-clean --user --install-deps-from=flathub --repo=repo --install builddir rocks.syng.Syng.yaml    
[ ] Test against beta.syng.rocks
[ ] Update flathub and merge

## Windows

[ ] Update that one line
[ ] Update versions in action file
[ ] Build locally
[ ] Test in VM/Windows-Laptop against beta.syng.rocks

## Release

[ ] tag last commit
[ ] upload to pypi
[ ] deploy docker to stable
[ ] Draft release in github
[ ] Announce on mastoton
"""
🎉 🎤  New Syng version X.Z.Y:
[short message what has changed]

Get it here:
🐧 Flathub: https://flathub.org/apps/rocks.syng.Syng
:windows: Portable + Installer: https://github.com/christofsteel/syng/releases/tag/vX.Y.Z
:python: PyPI: https://pypi.org/project/syng/
:docker: Docker (Server): ghcr.io/christofsteel/syng:X.Y.Z

#python #karaoke #flatpak #openSource #selfHosted #linux #docker #windows #music
"""
