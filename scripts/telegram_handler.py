#!/usr/bin/env python3
"""
Telegram handler for /recipe command
Called when user sends: /recipe <url>
"""

import sys
import subprocess
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: /recipe <video-url>")
        sys.exit(1)
    
    url = sys.argv[1]
    
    # Validate URL
    valid_platforms = ['tiktok', 'instagram', 'youtube', 'youtu.be']
    if not any(p in url.lower() for p in valid_platforms):
        print(f"⚠️ Unsupported platform. Supported: {', '.join(valid_platforms)}")
        sys.exit(1)
    
    # Run the pipeline
    pipeline = "/home/jonathan/clawd/recipes/scripts/pipeline.py"
    result = subprocess.run(
        ["python3", pipeline, url],
        capture_output=True,
        text=True,
        timeout=300
    )
    
    if result.returncode == 0:
        # Extract recipe name from output
        for line in result.stdout.split('\n'):
            if line.startswith('Recipe:'):
                title = line.replace('Recipe:', '').strip()
                print(f"✅ Added recipe: **{title}**")
                print(f"🔗 https://jonahenk.github.io/recipes/")
                break
    else:
        print("❌ Failed to process recipe")
        print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)

if __name__ == "__main__":
    main()
