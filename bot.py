# ==================== SETUP STAR FOLDERS ====================
# Run this script to create folder structure and organize your media

import os
import shutil
from pathlib import Path

def setup_folders():
    """Create all necessary folders for the Star system"""
    
    folders = [
        "tsega_photos/preview",
        "tsega_photos/full",
        "tsega_photos/premium",
        "tsega_videos/preview",
        "tsega_videos/full",
        "backups"
    ]
    
    for folder in folders:
        Path(folder).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created: {folder}")
    
    print("\n📁 Folder structure ready!")
    print("\n📌 HOW TO USE:")
    print("1. Put your preview photos in: tsega_photos/preview/")
    print("2. Put your full photos in: tsega_photos/full/")
    print("3. Put premium content in: tsega_photos/premium/")
    print("4. Put video previews in: tsega_videos/preview/")
    print("5. Put full videos in: tsega_videos/full/")
    print("\n💰 PRICING:")
    print("   • Preview photos: 5 Stars")
    print("   • Full photos: 50 Stars")
    print("   • Premium photos: 200 Stars")
    print("   • Video previews: 10 Stars")
    print("   • Full videos: 100 Stars")

def quick_organize():
    """Quickly organize existing media files"""
    
    # Check if you have existing photos
    if os.path.exists("tsega_photos"):
        files = os.listdir("tsega_photos")
        photos = [f for f in files if f.endswith(('.jpg', '.jpeg', '.png'))]
        
        if photos:
            print(f"\n📸 Found {len(photos)} photos")
            
            # Move first 5 to preview
            for i, photo in enumerate(photos[:5]):
                src = f"tsega_photos/{photo}"
                dst = f"tsega_photos/preview/{photo}"
                shutil.move(src, dst)
                print(f"   Moved to preview: {photo}")
            
            # Move next 5 to full
            for i, photo in enumerate(photos[5:10]):
                src = f"tsega_photos/{photo}"
                dst = f"tsega_photos/full/{photo}"
                shutil.move(src, dst)
                print(f"   Moved to full: {photo}")
    
    print("\n✅ Organization complete!")

if __name__ == "__main__":
    setup_folders()
    
    answer = input("\nDo you want to quickly organize existing photos? (y/n): ")
    if answer.lower() == 'y':
        quick_organize()
