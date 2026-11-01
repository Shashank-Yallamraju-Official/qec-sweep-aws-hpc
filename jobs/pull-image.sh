#!/usr/bin/env bash
# Pulls an image once per digest into a cache every node can read, and names the file.
# usage: pull-image.sh oras://host/repo:tag [cache dir]
# prints: <digest> <path to the .sif>
# A tag can move; a digest cannot. The registry is asked what the tag points at,
# which is a header, not a download, and the image is only pulled when no file
# under that digest exists yet. A run then records the digest it actually ran.
set -euo pipefail
uri=$1 cache=${2:-/scratch/images}
reference=${uri#oras://}
host=${reference%%/*}
repository=${reference#*/}
tag=${repository##*:}
repository=${repository%:*}
manifest="https://$host/v2/$repository/manifests/$tag"
accept='Accept: application/vnd.oci.image.manifest.v1+json'

header() { tr -d '\r' | sed -n "s/^$1: *//Ip" | head -1; }
field() { sed -n "s/.*$1=\"\([^\"]*\)\".*/\1/p"; }

# An anonymous request is answered with where to fetch a pull token (RFC 6750).
challenge=$(curl -sS -I -H "$accept" "$manifest" | header www-authenticate)
auth=()
if [[ $challenge == Bearer* ]]; then
  realm=$(field realm <<<"$challenge") service=$(field service <<<"$challenge") scope=$(field scope <<<"$challenge")
  token=$(curl -sS "$realm?service=$service&scope=$scope" | jq -r .token)
  auth=(-H "Authorization: Bearer $token")
fi
digest=$(curl -sS -I -H "$accept" "${auth[@]+"${auth[@]}"}" "$manifest" | header docker-content-digest)
[[ $digest == sha256:* ]] || { echo "no digest for $uri" >&2; exit 1; }

sif=$cache/${digest#sha256:}.sif
if [[ ! -f $sif ]]; then
  mkdir -p "$cache"
  partial=$(mktemp "$cache/.pull.XXXXXX")
  trap 'rm -f "$partial"' EXIT
  # apptainer reports the digest it pulled on stderr; the file is kept only if it
  # is the one the registry named, since the tag could move between the two calls.
  pulled=$(apptainer pull --force "$partial" "$uri" 2>&1 | tee >(cat >&2) | sed -n 's/^INFO: *Digest: *//p')
  [[ $pulled == "$digest" ]] || { echo "$uri moved from $digest to $pulled while pulling" >&2; exit 1; }
  mv -f "$partial" "$sif"
fi
echo "$digest $sif"
