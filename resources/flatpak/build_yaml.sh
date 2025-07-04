#!/usr/bin/env bash

./flatpak-pip-generator --build-only --yaml poetry-core
./flatpak-pip-generator --build-only --yaml expandvars
./flatpak-pip-generator --yaml cffi

AWK_PROG='
    BEGIN { inside_block = 0 }
    # Handle continuation lines
    /\\$/ {
      if (inside_block == 0 && $0 ~ package) { inside_block = 1 }
      if (inside_block == 1) { next }
    }
    {
      # End of a multi-line block
      if (inside_block == 1 && !/\\$/) { inside_block = 0; next }
      if (inside_block == 0 && $0 ~ package) { next }
      print
    }'
awk -v package="pyqt6" "$AWK_PROG" "../../requirements-client.txt" \
  | awk -v package="brotlicffi" "$AWK_PROG" \
  | awk -v package="colorama" "$AWK_PROG" \
  > "requirements-client.txt"

./flatpak-pip-generator --requirements-file requirements-client.txt --ignore-pkg cffi==1.17.1 --yaml
