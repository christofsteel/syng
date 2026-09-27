function get_latest_release() {
  PROJECT=$1
  curl -s https://api.github.com/repos/$PROJECT/releases/latest | jq '.assets[] | .browser_download_url'
}

function get_tag_from_url() {
  sed "s!.*/download/\([^/]*\).*!\1!" <<< $1
}

function get_hash_from_url() {
  sed "s!.*git-\([^\.]*\)\.7z\"!\1!" <<< $1
}

function get_latest_python() {
  curl -s https://www.python.org/api/v2/downloads/release/?format=json | jq '.[] | .name' | grep -P "^\"Python \d+.\d+.\d+\"$" | sed 's/"Python \(.*\)"/\1/' | sort --version-sort | tail -n 1
}

function get_latest_tag() {
  PROJECT=$1
  curl -s https://api.github.com/repos/$PROJECT/releases/latest | jq '.tag_name' | sed 's/\"\(.*\)\"/\1/'
}


