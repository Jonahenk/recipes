#!/usr/bin/env python3
"""
Recipe Pipeline - Full automation from URL to GitHub
Usage: python3 pipeline.py <video_url>
"""

import os
import sys
import json
import subprocess
import tempfile
import shutil
import urllib.request
import time

def run_command(cmd, cwd=None, timeout=300):
    """Run a shell command and return output"""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout
    )
    if result.returncode != 0:
        print(f"Command failed: {cmd}")
        print(f"Error: {result.stderr}")
        return None
    return result.stdout.strip()

def download_video(url, api_key, work_dir, max_retries=3):
    """Download video via Cobalt with retry logic for Railway sleep"""
    print("[1/5] Downloading video via Cobalt...")
    
    cobalt_url = "https://cobalt.jsgroenendijk.nl"
    
    for attempt in range(max_retries):
        try:
            # Call Cobalt API
            data = json.dumps({"url": url}).encode()
            req = urllib.request.Request(
                f"{cobalt_url}/",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Api-Key {api_key}"
                },
                method="POST"
            )
            
            response = urllib.request.urlopen(req, timeout=30)
            result = json.loads(response.read().decode())
            
            if result.get("status") != "tunnel":
                print(f"  ⚠️ Cobalt error: {result}")
                if attempt < max_retries - 1:
                    print(f"  Retrying in 5 seconds... ({attempt + 1}/{max_retries})")
                    time.sleep(5)
                    continue
                return None
            
            video_url = result["url"]
            filename = result.get("filename", "video.mp4")
            
            # Download the video
            video_path = os.path.join(work_dir, "video.mp4")
            urllib.request.urlretrieve(video_url, video_path)
            
            size = os.path.getsize(video_path)
            print(f"  ✓ Downloaded: {filename} ({size // 1024 // 1024}MB)")
            return video_path
            
        except Exception as e:
            print(f"  ⚠️ Attempt {attempt + 1} failed: {str(e)[:100]}")
            if attempt < max_retries - 1:
                # Railway free tier sleeps after inactivity - wait for wake
                print(f"  Waiting for Railway instance to wake up... (5s)")
                time.sleep(5)
            else:
                print(f"  ✗ Failed after {max_retries} attempts")
                return None
    
    return None

def extract_audio(video_path, work_dir):
    """Extract audio from video"""
    print("[2/6] Extracting audio...")
    
    audio_path = os.path.join(work_dir, "audio.wav")
    cmd = f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 16000 -ac 1 "{audio_path}" -y'
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}")
        return None
    
    size = os.path.getsize(audio_path)
    print(f"  ✓ Audio extracted: {size // 1024}KB")
    return audio_path

def extract_thumbnail(video_path, work_dir):
    """Extract thumbnail from video (at 3 second mark)"""
    print("[3/6] Extracting thumbnail...")
    
    thumb_path = os.path.join(work_dir, "thumbnail.jpg")
    # Extract frame at 3 seconds, scale to 800px width
    cmd = f'ffmpeg -i "{video_path}" -ss 00:00:03 -vframes 1 -q:v 2 -vf "scale=800:-1" "{thumb_path}" -y'
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️ Thumbnail extraction failed: {result.stderr[:100]}")
        return None
    
    size = os.path.getsize(thumb_path)
    print(f"  ✓ Thumbnail: {size // 1024}KB")
    return thumb_path

def transcribe(audio_path):
    """Transcribe audio with Whisper"""
    print("[4/6] Transcribing with Whisper...")
    
    whisper_dir = os.path.expanduser("~/whisper.cpp")
    whisper_bin = os.path.join(whisper_dir, "build/bin/whisper-cli")
    model_path = os.path.join(whisper_dir, "models/ggml-base.bin")
    
    cmd = f'"{whisper_bin}" -m "{model_path}" -f "{audio_path}" -l auto --no-timestamps -otxt'
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Whisper error: {result.stderr}")
        return None
    
    txt_path = audio_path + ".txt"
    with open(txt_path, 'r') as f:
        transcription = f.read().strip()
    
    print(f"  ✓ Transcribed: {len(transcription)} chars")
    return transcription

def extract_recipe(transcription, source_url, api_key):
    """Extract recipe structure using Gemini"""
    print("[5/6] Extracting recipe structure...")
    
    # Detect platform from URL
    platform = "unknown"
    creator = "unknown"
    if "tiktok" in source_url:
        platform = "tiktok"
    elif "instagram" in source_url:
        platform = "instagram"
    elif "youtube" in source_url:
        platform = "youtube"
    
    prompt = f"""Extract a recipe from this cooking video transcription and output as JSON.

Transcription:
{transcription}

Source: {source_url}
Platform: {platform}

Output ONLY this JSON structure:
{{"title": "Recipe Title", "source": {{"url": "{source_url}", "platform": "{platform}", "creator": "@{creator}"}}, "metadata": {{"time": "X minutes", "difficulty": "easy/medium/hard", "tags": ["tag1", "tag2"]}}, "ingredients": [{{"item": "name", "amount": "quantity or null", "prep": "chopped/etc or null", "note": "optional note"}}], "instructions": ["step 1", "step 2"], "notes": "any extra notes"}}

Rules:
- Use null for unknown amounts
- Include prep notes in "prep" field (chopped, minced, etc.)
- Estimate time from video description
- Tags should include cuisine type and key ingredients
- Keep instructions clear and actionable
- Be concise"""

    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }
    
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    response = urllib.request.urlopen(req)
    result = json.loads(response.read().decode())
    
    text = result['candidates'][0]['content']['parts'][0]['text']
    recipe = json.loads(text)
    
    print(f"  ✓ Extracted: {recipe.get('title', 'Unknown')}")
    return recipe

def generate_color_scheme(title):
    """Generate a color scheme based on recipe title"""
    import hashlib
    
    # Create hash from title
    hash_val = int(hashlib.md5(title.encode()).hexdigest(), 16)
    
    # Generate hue from hash (0-360)
    hue = hash_val % 360
    
    # Create complementary color scheme
    return {
        "primary": f"hsl({hue}, 80%, 55%)",
        "secondary": f"hsl({(hue + 30) % 360}, 70%, 60%)",
        "accent": f"hsl({(hue + 180) % 360}, 75%, 50%)",
        "gradient": f"linear-gradient(135deg, hsl({hue}, 80%, 55%), hsl({(hue + 40) % 360}, 70%, 60%))"
    }

def save_to_github(recipe, transcription, thumbnail_path=None):
    """Save recipe to GitHub repo"""
    print("[6/6] Saving to GitHub...")
    
    repo_dir = "/home/jonathan/clawd/recipes"
    
    # Create slug from title
    slug = recipe['title'].lower().replace(' ', '-').replace('/', '-')
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')
    
    # Generate and add color scheme
    recipe['colors'] = generate_color_scheme(recipe['title'])
    
    # Copy thumbnail to repo if exists
    if thumbnail_path and os.path.exists(thumbnail_path):
        thumb_dest = os.path.join(repo_dir, "recipes", f"{slug}.jpg")
        shutil.copy(thumbnail_path, thumb_dest)
        recipe['thumbnail'] = f"recipes/{slug}.jpg"
    
    # Save full recipe
    recipe_path = os.path.join(repo_dir, "recipes", f"{slug}.json")
    with open(recipe_path, 'w') as f:
        json.dump(recipe, f, indent=2)
    
    # Update index
    index_path = os.path.join(repo_dir, "data", "recipes.json")
    with open(index_path, 'r') as f:
        index = json.load(f)
    
    # Add to index (avoid duplicates)
    existing = [r for r in index['recipes'] if r['source']['url'] == recipe['source']['url']]
    if not existing:
        index_entry = {
            "title": recipe['title'],
            "source": recipe['source'],
            "metadata": recipe['metadata'],
            "colors": recipe['colors']
        }
        if recipe.get('thumbnail'):
            index_entry['thumbnail'] = recipe['thumbnail']
        index['recipes'].append(index_entry)
        
        with open(index_path, 'w') as f:
            json.dump(index, f, indent=2)
    
    # Commit and push
    os.chdir(repo_dir)
    run_command('git add -A')
    run_command(f'git commit -m "Add recipe: {recipe["title"]}"')
    run_command('git push origin main')
    
    print(f"  ✓ Committed: {slug}.json")
    return f"https://jonahenk.github.io/recipes/"

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 pipeline.py <video_url>")
        sys.exit(1)
    
    video_url = sys.argv[1].strip()
    
    # Check if already exists
    repo_dir = "/home/jonathan/clawd/recipes"
    index_path = os.path.join(repo_dir, "data", "recipes.json")
    with open(index_path, 'r') as f:
        index = json.load(f)
    
    # Normalize URL for comparison (remove trailing slashes)
    normalized_url = video_url.rstrip('/')
    for existing in index['recipes']:
        if existing['source']['url'].rstrip('/') == normalized_url:
            print(f"⚠️ Recipe already exists: {existing['title']}")
            print(f"🔗 https://jonahenk.github.io/recipes/")
            return None
    
    cobalt_key = "DVmbGlgwzCGBbYtnBQnoRiRDXFGChVlc"
    gemini_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    
    if not gemini_key:
        print("Error: GEMINI_API_KEY or GOOGLE_API_KEY not set")
        sys.exit(1)
    
    # Create temp directory
    work_dir = tempfile.mkdtemp(prefix='recipe-')
    
    try:
        print(f"=== Recipe Pipeline ===")
        print(f"URL: {video_url}")
        print()
        
        # Step 1: Download
        video_path = download_video(video_url, cobalt_key, work_dir)
        if not video_path:
            print("Failed to download video")
            return None
        
        # Step 2: Extract audio
        audio_path = extract_audio(video_path, work_dir)
        if not audio_path:
            print("Failed to extract audio")
            return None
        
        # Step 3: Extract thumbnail
        thumbnail_path = extract_thumbnail(video_path, work_dir)
        
        # Step 4: Transcribe
        transcription = transcribe(audio_path)
        if not transcription:
            print("Failed to transcribe")
            return None
        
        # Step 5: Extract recipe
        recipe = extract_recipe(transcription, video_url, gemini_key)
        if not recipe:
            print("Failed to extract recipe")
            return None
        
        # Step 6: Save to GitHub
        site_url = save_to_github(recipe, transcription, thumbnail_path)
        
        print()
        print(f"=== Done! ===")
        print(f"Recipe: {recipe['title']}")
        print(f"Site: {site_url}")
        
        return recipe
        
    finally:
        # Cleanup
        shutil.rmtree(work_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
