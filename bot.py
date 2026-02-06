# ================= IMPORTS =================
import os
import re
import asyncio
from PIL import Image, ImageDraw, ImageFont
import requests
import base64
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8249944716:AAEvqH81z0JKk_My4Jv9WgEraxnHO-UHK80")
OCR_API_KEY = "K82925383988957"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "template.png")
FONT_PATH = os.path.join(BASE_DIR, "font.ttf")

# User session storage
user_sessions = {}

# ================= OCR FUNCTION =================
def ocr_space_api(image_path: str, language: str = 'eng') -> str:
    """Use OCR.Space API for text extraction."""
    try:
        with open(image_path, 'rb') as image_file:
            img_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        
        url = "https://api.ocr.space/parse/image"
        payload = {
            'base64Image': f'data:image/png;base64,{img_base64}',
            'language': language,
            'isOverlayRequired': False,
            'OCREngine': 2,
        }
        
        headers = {'apikey': OCR_API_KEY, 'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(url, data=payload, headers=headers)
        result = response.json()
        
        if result.get('IsErroredOnProcessing', False):
            print(f"❌ OCR error: {result.get('ErrorMessage', 'Unknown')}")
            return ""
        
        parsed_text = ""
        for item in result.get('ParsedResults', []):
            parsed_text += item.get('ParsedText', '') + "\n"
        
        print(f"✅ OCR: {len(parsed_text)} chars")
        return parsed_text.strip()
        
    except Exception as e:
        print(f"❌ OCR failed: {e}")
        return ""

# ================= HELPER FUNCTIONS =================
def cleanup_user_session(user_id: int):
    """Clean up user session and files."""
    print(f"🧹 Cleaning user {user_id}")
    if user_id in user_sessions:
        # Delete files
        import glob
        patterns = [
            f"/tmp/fayda_bot/user_{user_id}_*",
            f"/tmp/user_{user_id}_*"
        ]
        for pattern in patterns:
            for file_path in glob.glob(pattern):
                try:
                    os.remove(file_path)
                except:
                    pass
        del user_sessions[user_id]
        print(f"✅ Cleaned up")

# ================= BOT HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user_id = update.effective_user.id
    user_sessions[user_id] = {"images": [], "data": {}, "step": 0}
    print(f"🚀 New session for user {user_id}")
    
    await update.message.reply_text(
        "📄 *Fayda ID Bot*\n\n"
        "Send me 3 screenshots in order:\n"
        "1️⃣ Front page\n2️⃣ Back page\n3️⃣ Photo+QR\n\n"
        "I'll generate an ID card.",
        parse_mode='Markdown'
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads."""
    user_id = update.effective_user.id
    print(f"\n📸 Photo from user {user_id}")
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {"images": [], "data": {}, "step": 0}
    
    # Get and save photo
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        
        temp_dir = "/tmp/fayda_bot"
        os.makedirs(temp_dir, exist_ok=True)
        
        img_index = len(user_sessions[user_id]["images"])
        img_path = os.path.join(temp_dir, f"user_{user_id}_{img_index}.png")
        
        await file.download_to_drive(img_path)
        user_sessions[user_id]["images"].append(img_path)
        
        await update.message.reply_text(f"✅ Image {img_index + 1}/3 received")
        
        if len(user_sessions[user_id]["images"]) < 3:
            return
        
        print("🎯 All 3 images received!")
        await process_user_images(update, user_id)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        await update.message.reply_text("❌ Error processing image")

async def process_user_images(update: Update, user_id: int):
    """Process all 3 images for a user."""
    try:
        print(f"\n🔄 Processing images for user {user_id}")
        
        if user_id not in user_sessions or len(user_sessions[user_id]["images"]) < 3:
            await update.message.reply_text("❌ Need 3 images")
            return
        
        images = user_sessions[user_id]["images"]
        await update.message.reply_text("⏳ Processing...")
        
        # Test OCR
        front_text = ocr_space_api(images[0])
        
        # Create test image
        output_path = f"/tmp/fayda_bot/user_{user_id}_output.png"
        test_img = Image.new('RGB', (800, 400), color='white')
        draw = ImageDraw.Draw(test_img)
        
        draw.text((10, 10), "Fayda ID Bot - Test", fill='black')
        draw.text((10, 50), f"User: {user_id}", fill='blue')
        draw.text((10, 90), f"OCR chars: {len(front_text)}", fill='green')
        draw.text((10, 130), "✅ Bot is working!", fill='purple')
        
        test_img.save(output_path)
        
        # Send to user
        with open(output_path, "rb") as photo_file:
            await update.message.reply_photo(
                photo=photo_file,
                caption="🧪 *Test Output* - Bot is working!",
                parse_mode='Markdown'
            )
        
        print(f"✅ Processing complete")
        
    except Exception as e:
        print(f"❌ Processing error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")
    
    finally:
        cleanup_user_session(user_id)

# ================= MAIN =================
def main():
    """Start the bot."""
    print("🚀 Starting Fayda ID Bot...")
    
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN not set!")
        return
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
