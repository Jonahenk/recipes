#!/bin/bash
# Recipe Pipeline Script
# Usage: ./recipe.sh [URL]

set -e

URL="$1"
if [ -z "$URL" ]; then
    echo "Usage: ./recipe.sh <video-url>"
    exit 1
fi

# Config
COBALT_URL="https://cobalt.jsgroenendijk.nl"
COBALT_API_KEY="DVmbGlgwzCGBbYtnBQnoRiRDXFGChVlc"
WHISPER_DIR="$HOME/whisper.cpp"
WHISPER_BIN="$WHISPER_DIR/build/bin/whisper-cli"
WHISPER_MODEL="$WHISPER_DIR/models/ggml-base.bin"
WORK_DIR="/tmp/recipe-$(date +%s)"
REPO_DIR="/home/jonathan/clawd/recipes"

echo "=== Recipe Pipeline ==="
echo "URL: $URL"
echo ""

# Create work dir
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Step 1: Download video via Cobalt
echo "[1/4] Downloading video..."
curl -X POST "$COBALT_URL/" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -H "Authorization: Api-Key $COBALT_API_KEY" \
    -d "{\"url\":\"$URL\"}" \
    -o cobalt-response.json 2>/dev/null

# Parse response - Cobalt returns {"status":"tunnel","url":"...","filename":"..."}
VIDEO_URL=$(cat cobalt-response.json | grep -o '"url":"[^"]*"' | head -1 | cut -d'"' -f4)
FILENAME=$(cat cobalt-response.json | grep -o '"filename":"[^"]*"' | cut -d'"' -f4)

if [ -z "$VIDEO_URL" ]; then
    echo "ERROR: Failed to get download URL from Cobalt"
    cat cobalt-response.json
    exit 1
fi

echo "Downloading: $FILENAME"
curl -L "$VIDEO_URL" -o video.mp4 2>/dev/null
echo "Video downloaded: $(ls -lh video.mp4 | awk '{print $5}')"
echo ""

# Step 2: Extract audio
echo "[2/4] Extracting audio..."
ffmpeg -i video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 audio.wav 2>/dev/null || {
    echo "ERROR: Failed to extract audio"
    exit 1
}
echo "Audio extracted: $(ls -lh audio.wav | awk '{print $5}')"
echo ""

# Step 3: Transcribe
echo "[3/4] Transcribing with Whisper..."
"$WHISPER_BIN" -m "$WHISPER_MODEL" -f audio.wav -l auto --no-timestamps -otxt 2>/dev/null || {
    echo "ERROR: Transcription failed"
    exit 1
}
echo "Transcription complete"
echo ""

# Step 4: Output transcription
echo "=== TRANSCRIPTION ==="
cat audio.wav.txt
echo ""
echo "=== Transcription saved to: $WORK_DIR/audio.wav.txt ==="

# Cleanup (keep work dir for now for debugging)
# rm -rf "$WORK_DIR"
