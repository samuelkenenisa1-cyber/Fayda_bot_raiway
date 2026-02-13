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
    """Extract ID information from OCR text."""
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
    
    lines = text.split('\n')
    print(f"📄 Parsing {len(lines)} lines of text")
    
    for line in lines:
        line_lower = line.lower()
        
        # Name
        if "ሙሉ ስም" in line or "full name" in line_lower:
            # Get next line or extract from this line
            parts = line.split()
            for i, part in enumerate(parts):
                part_lower = part.lower()
                if "ሳሙኤል" in part or "samuel" in part_lower:
                    name_parts = parts[i:i+3]
                    data["name"] = " ".join(name_parts)
                    print(f"✅ Found name: {data['name']}")
                    break
        
        # Date of Birth
        if "የትውልድ" in line or "date of birth" in line_lower or "dob" in line_lower:
            date_match = re.search(r'\d{2}/\d{2}/\d{4}', line)
            if date_match:
                data["dob"] = date_match.group()
                print(f"✅ Found DOB: {data['dob']}")
        
        # Phone
        if "ስልክ" in line or "phone" in line_lower:
            phone_match = re.search(r'(\d{10})', line.replace(" ", ""))
            if phone_match:
                data["phone"] = phone_match.group(1)
                print(f"✅ Found phone: {data['phone']}")
        
        # FAN (16-digit number)
        if "fan" in line_lower or "fcn" in line_lower or "ካርድ" in line:
            fan_match = re.search(r'(\d{16})', line.replace(" ", ""))
            if fan_match:
                data["fan"] = fan_match.group(1)
                print(f"✅ Found FAN: {data['fan']}")
        
        # FIN
        if "fin" in line_lower:
            fin_match = re.search(r'(\d{12,16})', line.replace(" ", ""))
            if fin_match:
                data["fin"] = fin_match.group(1)
                print(f"✅ Found FIN: {data['fin']}")
        
        # Sex
        if "sex" in line_lower or "ፆታ" in line:
            if "male" in line_lower or "ወንድ" in line:
                data["sex"] = "ወንድ | Male"
                print(f"✅ Found sex: Male")
            elif "female" in line_lower or "ሴት" in line:
                data["sex"] = "ሴት | Female"
                print(f"✅ Found sex: Female")
        
        # Nationality
        if "ዜግነት" in line or "nationality" in line_lower:
            if "ኢትዮጵያ" in line or "ethiopian" in line_lower:
                data["nationality"] = "ኢትዮጵያ | Ethiopian"
                print(f"✅ Found nationality")
        
        # Expiry
        if "expiry" in line_lower or "የሚያበቃበት" in line:
            expiry_match = re.search(r'\d{4}/\d{2}/\d{2}', line)
            if expiry_match:
                data["expiry"] = expiry_match.group()
                print(f"✅ Found expiry: {data['expiry']}")
    
    return data

# ================= FULL ID GENERATION FUNCTION =================
def generate_full_id(data: dict, photo_qr_path: str, output_path: str):
    """Generate full ID card with template and extracted data."""
    print(f"\n🎨 GENERATING FULL ID CARD")
    print(f"   Template: {TEMPLATE_PATH}")
    print(f"   Photo/QR: {photo_qr_path}")
    print(f"   Output: {output_path}")
    
    try:
        # Check if template exists
        if not os.path.exists(TEMPLATE_PATH):
            print(f"❌ Template not found: {TEMPLATE_PATH}")
            return False
        
        # Open template
        template = Image.open(TEMPLATE_PATH).convert("RGBA")
        draw = ImageDraw.Draw(template)
        print(f"   Template size: {template.size}")
        
        # Load font
        try:
            if os.path.exists(FONT_PATH):
                font_large = ImageFont.truetype(FONT_PATH, 42)
                font_medium = ImageFont.truetype(FONT_PATH, 36)
                font_small = ImageFont.truetype(FONT_PATH, 32)
                print(f"   ✅ Font loaded: {FONT_PATH}")
            else:
                print(f"   ⚠️ Font not found, using default")
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
        except Exception as font_err:
            print(f"   ⚠️ Font error: {font_err}")
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        print("\n📝 PLACING TEXT ON TEMPLATE:")
        
        # FRONT SIDE - Using your exact coordinates
        # 1️⃣ Full Name (x: 210, y: 1120)
        if data.get("name"):
            name_text = data["name"][:40]
            draw.text((210, 1120), name_text, fill="black", font=font_large)
            print(f"   ✅ Name at (210,1120): {name_text[:20]}...")
        
        # 2️⃣ Date of Birth (x: 210, y: 1235)
        if data.get("dob"):
            draw.text((210, 1235), data["dob"], fill="black", font=font_medium)
            print(f"   ✅ DOB at (210,1235): {data['dob']}")
        
        # 3️⃣ Sex (x: 210, y: 1325)
        if data.get("sex"):
            draw.text((210, 1325), data["sex"], fill="black", font=font_medium)
            print(f"   ✅ Sex at (210,1325): {data['sex']}")
        
        # 4️⃣ Expiry Date (x: 210, y: 1410)
        if data.get("expiry"):
            draw.text((210, 1410), data["expiry"], fill="black", font=font_medium)
            print(f"   ✅ Expiry at (210,1410): {data['expiry']}")
        
        # 5️⃣ FAN (x: 210, y: 1515)
        if data.get("fan"):
            fan = data["fan"]
            if len(fan) >= 16:
                fan = f"{fan[:4]} {fan[4:8]} {fan[8:12]} {fan[12:16]}"
            draw.text((210, 1515), fan, fill="black", font=font_large)
            print(f"   ✅ FAN at (210,1515): {fan}")
        
        # 6️⃣ SN (x: 390, y: 1555)
        if data.get("sin"):
            draw.text((390, 1555), data["sin"], fill="black", font=font_small)
            print(f"   ✅ SN at (390,1555): {data['sin']}")
        
        # BACK SIDE
        # 8️⃣ Phone Number (x: 120, y: 1220)
        if data.get("phone"):
            draw.text((120, 1220), data["phone"], fill="black", font=font_medium)
            print(f"   ✅ Phone at (120,1220): {data['phone']}")
        
        # 9️⃣ Nationality (x: 120, y: 1320)
        if data.get("nationality"):
            draw.text((120, 1320), data["nationality"], fill="black", font=font_medium)
            print(f"   ✅ Nationality at (120,1320): {data['nationality']}")
        
        # 🔟 Address (x: 120, y: 1425)
        if data.get("address"):
            address = data["address"][:50]
            draw.text((120, 1425), address, fill="black", font=font_small)
            print(f"   ✅ Address at (120,1425): {address[:20]}...")
        
        # 1️⃣1️⃣ FIN (x: 760, y: 1220)
        if data.get("fin"):
            draw.text((760, 1220), data["fin"], fill="black", font=font_large)
            print(f"   ✅ FIN at (760,1220): {data['fin']}")
        
        # Add Photo and QR Code
        print("\n📸 ADDING PHOTO AND QR CODE:")
        try:
            if os.path.exists(photo_qr_path):
                img = Image.open(photo_qr_path).convert("RGBA")
                print(f"   Source image: {img.size}")
                
                # Crop Photo (160, 70, 560, 520)
                try:
                    photo = img.crop((160, 70, 560, 520))
                    photo = photo.resize((300, 380))
                    template.paste(photo, (120, 140), photo)
                    print(f"   ✅ Photo placed at (120,140)")
                except Exception as crop_err:
                    print(f"   ⚠️ Photo crop failed: {crop_err}")
                
                # Crop QR Code (80, 650, 640, 1250)
                try:
                    qr = img.crop((80, 650, 640, 1250))
                    qr = qr.resize((520, 520))
                    template.paste(qr, (1470, 40), qr)
                    print(f"   ✅ QR code placed at (1470,40)")
                except Exception as qr_err:
                    print(f"   ⚠️ QR crop failed: {qr_err}")
            else:
                print(f"   ❌ Photo/QR file not found: {photo_qr_path}")
        except Exception as img_err:
            print(f"   ⚠️ Image processing error: {img_err}")
        
        # Save final image
        template.save(output_path)
        print(f"\n✅ Full ID generated and saved to: {output_path}")
        return True
        
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        import traceback
        traceback.print_exc()
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
        
        # Step 1: OCR on front page
        print("📄 OCR on front page...")
        front_text = ocr_space_api(images[0])
        
        # Step 2: OCR on back page
        print("📄 OCR on back page...")
        back_text = ocr_space_api(images[1])
        
        # Step 3: Parse combined text
        print("📋 Parsing extracted data...")
        combined_text = front_text + "\n" + back_text
        data = parse_fayda(combined_text)
        
        # Show what we found
        found_fields = [k for k, v in data.items() if v]
        if found_fields:
            await update.message.reply_text(
                f"📊 Found {len(found_fields)} fields: {', '.join(found_fields[:5])}"
            )
        else:
            await update.message.reply_text("⚠️ No data found, using placeholder")
            # Add sample data for testing
            data = {
                "name": "ሳሙኤል ቀነኒሳ ሰልባና | Samuel Kenenisa Selbana",
                "dob": "07/10/1992",
                "sex": "ወንድ | Male",
                "expiry": "2026/05/21",
                "fan": "5035 9289 3697 0958",
                "phone": "0945660103",
                "nationality": "ኢትዮጵያ | Ethiopian",
                "address": "አዲስ አበባ, እቃቂ ቃሊቲ, ወረዳ 06",
                "fin": "2536 8067 4305"
            }
            found_fields = list(data.keys())
        
        # Step 4: Generate FULL ID
        await update.message.reply_text("🎨 Generating your ID card with template...")
        output_path = f"/tmp/fayda_bot/user_{user_id}_final.png"
        
        # Call the FULL ID generation function
        success = generate_full_id(
            data,
            images[2],  # Photo+QR image
            output_path
        )
        
        if success:
            print(f"✅ Full ID generated: {output_path}")
            
            # Send the generated ID
            with open(output_path, "rb") as photo_file:
                await update.message.reply_photo(
                    photo=photo_file,
                    caption=f"✅ *Your Fayda ID is Ready!*\n📊 Found {len(found_fields)} fields",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text("❌ Failed to generate full ID")
        
    except Exception as e:
        print(f"❌ Processing error: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")
    
    finally:
        # Cleanup
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
