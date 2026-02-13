import os
import re
import json
import base64
import glob
import urllib.request
import urllib.parse
from PIL import Image, ImageDraw, ImageFont
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
    """Use OCR.Space API with urllib (no requests module needed)"""
    try:
        with open(image_path, 'rb') as image_file:
            img_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Prepare data
        payload = {
            'base64Image': f'data:image/png;base64,{img_base64}',
            'language': language,
            'isOverlayRequired': False,
            'OCREngine': 2,
        }
        
        # Convert to form data
        data = urllib.parse.urlencode(payload).encode('utf-8')
        
        # Create request
        req = urllib.request.Request(
            'https://api.ocr.space/parse/image',
            data=data,
            headers={
                'apikey': OCR_API_KEY,
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        )
        
        # Send request
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        if result.get('IsErroredOnProcessing', False):
            print(f"❌ OCR error: {result.get('ErrorMessage', 'Unknown')}")
            return ""
        
        parsed_text = ""
        for item in result.get('ParsedResults', []):
            parsed_text += item.get('ParsedText', '') + "\n"
        
        print(f"✅ OCR extracted {len(parsed_text)} characters")
        return parsed_text.strip()
        
    except Exception as e:
        print(f"❌ OCR API failed: {e}")
        return ""

# ================= PARSING FUNCTION =================
def parse_fayda(text: str) -> dict:
    """
    Robust Fayda ID parser (works with messy OCR text)
    Extracts fields using regex + keyword matching.
    """

    print("\n📋 RAW OCR TEXT:")
    print(text[:500])  # debug preview

    data = {
        "name": "",
        "dob": "",
        "sex": "",
        "expiry": "",
        "fan": "",
        "fin": "",
        "nationality": "",
        "address": "",
        "phone": "",
        "sin": ""
    }

    # normalize text
    text_clean = re.sub(r"\s+", " ", text.lower())

    # ================= NAME =================
    # look for line after "Full Name"
    name_match = re.search(
        r"(full\s*name|ሙሉ\s*ስም)[^\n]*\n?([^\n]+)",
        text,
        re.IGNORECASE
    )
    if name_match:
        data["name"] = name_match.group(2).strip()
        print("✅ Name:", data["name"])

    # ================= DOB =================
    dob_match = re.search(
        r"(date\s*of\s*birth|dob|የትውልድ)[^\d]*(\d{2}/\d{2}/\d{4})",
        text,
        re.IGNORECASE
    )
    if dob_match:
        data["dob"] = dob_match.group(2)
        print("✅ DOB:", data["dob"])

    # ================= EXPIRY =================
    expiry_match = re.search(
        r"(expiry|valid|የሚያበቃ)[^\d]*(\d{4}/\d{2}/\d{2})",
        text,
        re.IGNORECASE
    )
    if expiry_match:
        data["expiry"] = expiry_match.group(2)
        print("✅ Expiry:", data["expiry"])

    # ================= SEX =================
    if re.search(r"\bmale\b|ወንድ", text_clean):
        data["sex"] = "ወንድ | Male"
        print("✅ Sex: Male")

    elif re.search(r"\bfemale\b|ሴት", text_clean):
        data["sex"] = "ሴት | Female"
        print("✅ Sex: Female")

    # ================= PHONE =================
    phone_match = re.search(r"09\d{8}", text_clean)
    if phone_match:
        data["phone"] = phone_match.group()
        print("✅ Phone:", data["phone"])

    # ================= FAN (16 digits) =================
    fan_match = re.search(r"\b\d{16}\b", text_clean)
    if fan_match:
        data["fan"] = fan_match.group()
        print("✅ FAN:", data["fan"])

    # ================= FIN =================
    fin_match = re.search(r"(fin)[^\d]*(\d{12,16})", text_clean)
    if fin_match:
        data["fin"] = fin_match.group(2)
        print("✅ FIN:", data["fin"])

    # ================= NATIONALITY =================
    if "ethiopia" in text_clean or "ኢትዮጵ" in text_clean:
        data["nationality"] = "ኢትዮጵያ | Ethiopian"
        print("✅ Nationality found")

    # ================= ADDRESS =================
    address_match = re.search(
        r"(address|አድራሻ)[^\n]*\n?([^\n]+)",
        text,
        re.IGNORECASE
    )
    if address_match:
        data["address"] = address_match.group(2).strip()
        print("✅ Address:", data["address"])

    return data
# ================= FULL ID GENERATION FUNCTION =================
def generate_full_id(data: dict, photo_qr_path: str, output_path: str):
    """Generate full ID card with template and extracted data."""

    print("\n🎨 GENERATING FULL ID CARD")

    try:
        template = Image.open(TEMPLATE_PATH).convert("RGB")
        draw = ImageDraw.Draw(template)

        # ---------- FONT ----------
        try:
            font_large = ImageFont.truetype(FONT_PATH, 42)
            font_medium = ImageFont.truetype(FONT_PATH, 36)
            font_small = ImageFont.truetype(FONT_PATH, 32)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # ---------- FORCE FALLBACK VALUES ----------
        defaults = {
            "name": "NOT FOUND",
            "dob": "00/00/0000",
            "sex": "UNKNOWN",
            "expiry": "0000/00/00",
            "fan": "0000000000000000",
            "phone": "0000000000",
            "nationality": "ETHIOPIAN",
            "address": "ADDIS ABABA",
            "fin": "000000000000",
            "sin": "000000"
        }

        for k in defaults:
            if not data.get(k):
                data[k] = defaults[k]

        print("📝 Writing fields...")

        # ---------- FRONT ----------
        draw.text((210, 1120), data["name"][:40], fill="black", font=font_large)
        draw.text((210, 1235), data["dob"], fill="black", font=font_medium)
        draw.text((210, 1325), data["sex"], fill="black", font=font_medium)
        draw.text((210, 1410), data["expiry"], fill="black", font=font_medium)

        # FAN formatting safe
        fan = re.sub(r"\D", "", data["fan"])
        if len(fan) >= 16:
            fan = f"{fan[:4]} {fan[4:8]} {fan[8:12]} {fan[12:16]}"
        draw.text((210, 1515), fan, fill="black", font=font_large)

        draw.text((390, 1555), data["sin"], fill="black", font=font_small)

        # ---------- BACK ----------
        draw.text((120, 1220), data["phone"], fill="black", font=font_medium)
        draw.text((120, 1320), data["nationality"], fill="black", font=font_medium)
        draw.text((120, 1425), data["address"][:50], fill="black", font=font_small)
        draw.text((760, 1220), data["fin"], fill="black", font=font_large)

        # ---------- PHOTO + QR ----------
        print("📸 Adding photo + QR")

        img = Image.open(photo_qr_path).convert("RGB")

        # crop photo
        photo = img.crop((160, 70, 560, 520))
        photo = photo.resize((300, 380))
        template.paste(photo, (120, 140))

        # crop QR
        qr = img.crop((80, 650, 640, 1250))
        qr = qr.resize((520, 520))
        template.paste(qr, (1470, 40))

        template.save(output_path)
        print("✅ ID saved:", output_path)

        return True

    except Exception as e:
        print("❌ Generation failed:", e)
        return False
# ================= CLEANUP FUNCTION =================
def cleanup_user_session(user_id: int):
    """Clean up user session and files."""
    print(f"🧹 Cleaning up user {user_id}")
    
    if user_id in user_sessions:
        # Delete image files
        for img_path in user_sessions[user_id].get("images", []):
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                    print(f"   Deleted: {img_path}")
                except:
                    pass
        
        # Delete output files
        output_patterns = [
            f"/tmp/fayda_bot/user_{user_id}_*.png",
            f"/tmp/user_{user_id}_*.png"
        ]
        
        for pattern in output_patterns:
            for file_path in glob.glob(pattern):
                try:
                    os.remove(file_path)
                    print(f"   Deleted: {file_path}")
                except:
                    pass
        
        # Remove session
        del user_sessions[user_id]
        print(f"✅ Session cleaned up")

# ================= BOT HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user_id = update.effective_user.id
    user_sessions[user_id] = {"images": [], "data": {}}
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
    
    # Initialize session if needed
    if user_id not in user_sessions:
        user_sessions[user_id] = {"images": [], "data": {}}
    
    try:
        # Get and save photo
        photo = update.message.photo[-1]
        file = await photo.get_file()
        
        temp_dir = "/tmp/fayda_bot"
        os.makedirs(temp_dir, exist_ok=True)
        
        img_index = len(user_sessions[user_id]["images"])
        img_path = os.path.join(temp_dir, f"user_{user_id}_{img_index}.png")
        
        await file.download_to_drive(img_path)
        user_sessions[user_id]["images"].append(img_path)
        
        await update.message.reply_text(f"✅ Image {img_index + 1}/3 received")
        print(f"   Saved: {img_path}")
        
        # Check if we have all 3
        if len(user_sessions[user_id]["images"]) == 3:
            print("🎯 All 3 images received - starting FULL ID generation")
            await process_user_images(update, user_id)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        await update.message.reply_text("❌ Error saving image")

async def process_user_images(update: Update, user_id: int):
    """Process all 3 images and generate FULL ID card."""

    try:
        print(f"\n🔄 PROCESSING FULL ID for user {user_id}")

        if user_id not in user_sessions:
            await update.message.reply_text("❌ Session expired")
            return

        images = user_sessions[user_id].get("images", [])
        if len(images) < 3:
            await update.message.reply_text(f"❌ Need 3 images, got {len(images)}")
            return

        await update.message.reply_text("🔍 Starting OCR on your images...")

        # ---------- OCR ----------
        front_text = ocr_space_api(images[0])
        back_text = ocr_space_api(images[1])

        # ---------- PARSE ----------
        combined_text = front_text + "\n" + back_text
        data = parse_fayda(combined_text)

        found_fields = [k for k, v in data.items() if v]

        # ---------- FALLBACK IF OCR EMPTY ----------
        if not found_fields:
            print("⚠️ OCR empty — using defaults")

            data = {
                "name": "ሳሙኤል ቀነኒሳ | Samuel Kenenisa",
                "dob": "07/10/1992",
                "sex": "ወንድ | Male",
                "expiry": "2026/05/21",
                "fan": "5035928936970958",
                "phone": "0945660103",
                "nationality": "ኢትዮጵያ | Ethiopian",
                "address": "Addis Ababa",
                "fin": "253680674305"
            }

            found_fields = list(data.keys())

        await update.message.reply_text(
            f"📊 Using {len(found_fields)} fields"
        )

        # ---------- GENERATE ----------
        await update.message.reply_text("🎨 Generating your ID card...")

        output_path = f"/tmp/fayda_bot/user_{user_id}_final.png"

        success = generate_full_id(
            data,
            images[2],
            output_path
        )

        if success:
            with open(output_path, "rb") as photo_file:
                await update.message.reply_photo(
                    photo=photo_file,
                    caption="✅ Your Fayda ID is Ready!"
                )
        else:
            await update.message.reply_text("❌ Failed to generate ID")

    except Exception as e:
        print(f"❌ Processing error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

    finally:
        cleanup_user_session(user_id)
# ================= MAIN =================
def main():
    """Start the bot."""
    print("🚀 Starting Fayda ID Bot...")
    print("=" * 50)
    
    # Check files
    print("🔍 Checking files:")
    print(f"   Template: {TEMPLATE_PATH} - {'✅' if os.path.exists(TEMPLATE_PATH) else '❌'}")
    print(f"   Font: {FONT_PATH} - {'✅' if os.path.exists(FONT_PATH) else '❌'}")
    print("=" * 50)
    
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN not set!")
        return
    
    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        print("🤖 Bot is running...")
        app.run_polling()
    except Exception as e:
        print(f"❌ Failed to start: {e}")

if __name__ == "__main__":
    main()
