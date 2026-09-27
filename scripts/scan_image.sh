#!/usr/bin/env sh
set -eu

image_ref="${1:-jailbreak-framework:readiness}"
trivy_image="aquasec/trivy:0.69.3@sha256:bcc376de8d77cfe086a917230e818dc9f8528e3c852f7b1aff648949b6258d1c"
scan_dir="$(mktemp -d "${TMPDIR:-/tmp}/jbf-image-scan.XXXXXX")"

cleanup() {
    rm -rf "$scan_dir"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$scan_dir/cache"
docker save --output "$scan_dir/image.tar" "$image_ref"

docker run --rm \
    --network=bridge \
    --user "$(id -u):$(id -g)" \
    --volume "$scan_dir/cache:/tmp/trivy-cache" \
    "$trivy_image" \
    image --cache-dir /tmp/trivy-cache --download-db-only --no-progress

docker run --rm \
    --network=none \
    --user "$(id -u):$(id -g)" \
    --volume "$scan_dir/cache:/tmp/trivy-cache" \
    --volume "$scan_dir/image.tar:/scan/image.tar:ro" \
    "$trivy_image" \
    image \
    --cache-dir /tmp/trivy-cache \
    --input /scan/image.tar \
    --skip-db-update \
    --scanners vuln \
    --severity HIGH,CRITICAL \
    --ignore-unfixed \
    --exit-code 1 \
    --no-progress
