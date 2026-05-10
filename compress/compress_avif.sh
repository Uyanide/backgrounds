#!/usr/bin/env bash

set -euo pipefail

DEPENDENCIES=(oavif magick)
TARGET_SSIMULACRA2=85
MAX_DIMENSION=2560
OAVIF_PARAMS=("--speed" "0" "--score-tgt" "$TARGET_SSIMULACRA2" )

for dep in "${DEPENDENCIES[@]}"; do
    if ! type "$dep" &> /dev/null; then
        echo "Error: $dep is not installed." >&2
        exit 1
    fi
done

path="$(dirname "$(realpath "$0")")"

image_dir="$path/.."
output_dir="$path/../avif"

mkdir -p "$output_dir"

mapfile -d '' -t input_images < <(
    find "$image_dir" -maxdepth 1 -type f \( \
        -iname '*.jpg' -o \
        -iname '*.jpeg' -o \
        -iname '*.png' -o \
        -iname '*.webp' \
    \) -print0
)

tmp_image="$(mktemp --suffix=.png)"
cleanup() {
    rm -f "$tmp_image"
}
trap cleanup EXIT

for image in "${input_images[@]}"; do
    filename="$(basename "$image")"
    output_file="$output_dir/${filename%.*}.avif"

    if [[ -f "$output_file" ]]; then
        echo "Skipping $image, output already exists."
        continue
    fi

    magick "$image" -filter Lanczos -resize "${MAX_DIMENSION}x${MAX_DIMENSION}>" -strip -quality 100 "$tmp_image"

    oavif "${OAVIF_PARAMS[@]}" "$tmp_image" "$output_file"
done
