#!/usr/bin/env sh
set -eu

image_ref="${1:-jailbreak-framework:readiness}"
output_path="${2:-dist/jailbreak-framework.sbom.cdx.json}"
trivy_image="aquasec/trivy:0.69.3@sha256:bcc376de8d77cfe086a917230e818dc9f8528e3c852f7b1aff648949b6258d1c"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/jbf-sbom.XXXXXX")"

cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT HUP INT TERM

case "$output_path" in
    /*) ;;
    *) output_path="$(pwd)/$output_path" ;;
esac
output_dir="$(dirname -- "$output_path")"
output_name="$(basename -- "$output_path")"
mkdir -p "$work_dir/cache" "$output_dir"

docker save --output "$work_dir/image.tar" "$image_ref"

docker run --rm \
    --network=bridge \
    --user "$(id -u):$(id -g)" \
    --volume "$work_dir/cache:/tmp/trivy-cache" \
    "$trivy_image" \
    image --cache-dir /tmp/trivy-cache --download-db-only --no-progress

docker run --rm \
    --network=none \
    --user "$(id -u):$(id -g)" \
    --volume "$work_dir/cache:/tmp/trivy-cache" \
    --volume "$work_dir/image.tar:/scan/image.tar:ro" \
    --volume "$output_dir:/output" \
    "$trivy_image" \
    image \
    --cache-dir /tmp/trivy-cache \
    --input /scan/image.tar \
    --skip-db-update \
    --format cyclonedx \
    --output "/output/$output_name" \
    --no-progress

chmod 0644 "$output_path"
printf 'CycloneDX SBOM written to %s\n' "$output_path"
