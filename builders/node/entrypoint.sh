#!/bin/bash
set -e

# Usage function
usage() {
    echo "Usage: $0 <build-type> <input-file> <output-file>"
    echo "  build-type: js or css"
    echo "  input-file: path to input file relative to /build"
    echo "  output-file: path to output file relative to /build"
    exit 1
}

# Check if we have all required arguments
if [ "$#" -ne 3 ]; then
    usage
fi

BUILD_TYPE=$1
INPUT_FILE=$2
OUTPUT_FILE=$3

# Create output directory if it doesn't exist
mkdir -p "$(dirname "$OUTPUT_FILE")"

# Install dependencies if package.json exists
if [ -f "package.json" ]; then
    echo "Found package.json, installing dependencies..."
    # Use npm ci if there's a package-lock.json, otherwise use npm install
    if [ -f "package-lock.json" ]; then
        npm ci --quiet
    else
        npm install --quiet
    fi
fi

case $BUILD_TYPE in
    "js")
        echo "Building JavaScript/TypeScript: $INPUT_FILE -> $OUTPUT_FILE"
        esbuild "$INPUT_FILE" \
            --bundle \
            --minify \
            --sourcemap \
            --target=es6 \
            --outfile="$OUTPUT_FILE"
        ;;
    "css")
        echo "Building CSS: $INPUT_FILE -> $OUTPUT_FILE"
        postcss "$INPUT_FILE" \
            --output "$OUTPUT_FILE" \
            --use autoprefixer \
            --use tailwindcss
        ;;
    *)
        echo "Error: Unknown build type '$BUILD_TYPE'"
        usage
        ;;
esac 