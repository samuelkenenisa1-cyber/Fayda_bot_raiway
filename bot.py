import os
import re
import asyncio
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import pytesseract
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Set Tesseract path for Railway
TESSERACT_PATH = "/usr/bin/tesseract"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(BASE_DIR, "tmp")
TEMPLATE_PATH = os.path.join(BASE_DIR, "template.png")
FONT_PATH = os.path.join(BASE_DIR, "font.ttf")

os.makedirs(TMP_DIR, exist_ok=True)

# User session storage
user_sessions = {}

# ================= BOT HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user_id = update.effective_user.id
    user_sessions[user_id] = []
    
    await update.message.reply_text(
        "📄 *Fayda ID Bot*\n\n"
        "Send me 3 screenshots in this order:\n"
        "1️⃣ Front page of ID (text only)\n"
        "2️⃣ Back page of ID (text only)\n"
        "3️⃣ Photo + QR code page\n\n"
        "I'll extract information and generate a formatted ID card.",
        parse_mode='Markdown'
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads."""
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("Please send /start first")
        return
    
    # Get the highest quality photo
    photo = update.message.photo[-1]
    file = await photo.get_file()
    
    # Create user directory
    user_dir = os.path.join(TMP_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    # Save image
    img_index = len(user_sessions[user_id]) + 1
    img_path = os.path.join(user_dir, f"{img_index}.png")
    await file.download_to_drive(img_path)
    user_sessions[user_id].append(img_path)
    
    print(f"📸 User {user_id}: Image {img_index} saved - {os.path.getsize(img_path)} bytes")
    
    # Acknowledge receipt
    if img_index < 3:
        await update.message.reply_text(f"✅ Image {img_index}/3 received")
        return
    
    # All images received
    await update.message.reply_text("⏳ Processing all 3 images...")
    
    try:
        print("\n" + "="*80)
        print(f"🔄 PROCESSING USER {user_id}")
        print("="*80)
        
        # Save original images for debugging
        for i, img_path in enumerate(user_sessions[user_id]):
            print(f"📁 Image {i+1}: {img_path} ({os.path.getsize(img_path)} bytes)")
        
        # Step 1: OCR on first image (front)
        print("\n--- OCR ON FRONT PAGE ---")
        front_text = ocr_image(user_sessions[user_id][0])
        
        # Save OCR result
        front_ocr_path = os.path.join(user_dir, "front_ocr.txt")
        with open(front_ocr_path, "w", encoding="utf-8") as f:
            f.write(front_text)
        print(f"💾 Saved front OCR to: {front_ocr_path}")
        
        # Step 2: OCR on second image (back)
        print("\n--- OCR ON BACK PAGE ---")
        back_text = ocr_image(user_sessions[user_id][1])
        
        # Save OCR result
        back_ocr_path = os.path.join(user_dir, "back_ocr.txt")
        with open(back_ocr_path, "w", encoding="utf-8") as f:
            f.write(back_text)
        print(f"💾 Saved back OCR to: {back_ocr_path}")
        
        # Show OCR preview in chat
        ocr_preview = f"*OCR Results:*\n\n"
        if front_text:
            ocr_preview += f"*Front page (first 200 chars):*\n```\n{front_text[:200]}\n```\n\n"
        if back_text:
            ocr_preview += f"*Back page (first 200 chars):*\n```\n{back_text[:200]}\n```"
        
        await update.message.reply_text(ocr_preview, parse_mode='Markdown')
        
        # Parse the data
        print("\n--- PARSING DATA ---")
        data = parse_fayda(front_text, back_text)
        
        # Save parsed data
        data_path = os.path.join(user_dir, "parsed_data.txt")
        with open(data_path, "w", encoding="utf-8") as f:
            for key, value in data.items():
                f.write(f"{key}: {value}\n")
        print(f"💾 Saved parsed data to: {data_path}")
        
        # Show what we found
        found = {k: v for k, v in data.items() if v}
        
        print(f"\n📊 FOUND {len(found)} FIELDS:")
        for key, value in found.items():
            print(f"   {key}: {value}")
        
        if len(found) < 3:
            fields_list = ", ".join(found.keys()) if found else "nothing"
            await update.message.reply_text(
                f"⚠️ *Only found: {fields_list}*\n\n"
                f"OCR extracted {len(front_text)+len(back_text)} characters.\n"
                f"Please send clearer screenshots.",
                parse_mode='Markdown'
            )
            return
        
        # Generate ID
        print("\n--- GENERATING ID CARD ---")
        output_path = os.path.join(user_dir, "final_id.png")
        
        # First, let's check if template and font exist
        print(f"🔍 Checking required files:")
        print(f"   Template: {TEMPLATE_PATH} - {'✅ Exists' if os.path.exists(TEMPLATE_PATH) else '❌ Missing'}")
        print(f"   Font: {FONT_PATH} - {'✅ Exists' if os.path.exists(FONT_PATH) else '❌ Missing'}")
        
        if not os.path.exists(TEMPLATE_PATH):
            await update.message.reply_text("❌ Template image is missing!")
            return
        
        success = generate_id(
            data, 
            user_sessions[user_id][2],  # Third image has photo + QR
            output_path
        )
        
        if success:
            print(f"✅ Generated ID saved: {output_path} ({os.path.getsize(output_path)} bytes)")
            
            # Create debug image with grid
            debug_path = os.path.join(user_dir, "debug_grid.png")
            create_debug_grid(TEMPLATE_PATH, debug_path)
            print(f"✅ Debug grid saved: {debug_path}")
            
            # Send both images
            with open(output_path, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"✅ *ID Generated!*\nFound {len(found)} fields.",
                    parse_mode='Markdown'
                )
            
            # Send debug grid
            with open(debug_path, "rb") as debug_photo:
                await update.message.reply_photo(
                    photo=debug_photo,
                    caption="🔍 Debug: Red boxes show where text should go",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text("❌ Failed to generate ID image")
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}")
    
    finally:
        # Cleanup session
        if user_id in user_sessions:
            del user_sessions[user_id]

# ================= OCR =================

def ocr_image(path: str) -> str:
    """Extract text from image."""
    try:
        print(f"🔍 OCR on: {os.path.basename(path)}")
        
        # Open image
        img = Image.open(path)
        print(f"   Size: {img.size}, Mode: {img.mode}")
        
        # Preprocess
        img = img.convert('L')  # Grayscale
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(3.0)  # High contrast
        
        # OCR with multiple configs
        texts = []
        
        # Config 1: Amharic + English
        try:
            text1 = pytesseract.image_to_string(
                img,
                lang='amh+eng',
                config='--psm 6 --oem 3'
            )
            texts.append(text1)
            print(f"   Config 1: {len(text1)} chars")
        except Exception as e:
            print(f"   Config 1 failed: {e}")
        
        # Config 2: Auto orientation
        try:
            text2 = pytesseract.image_to_string(
                img,
                lang='amh+eng',
                config='--psm 3 --oem 3'
            )
            texts.append(text2)
            print(f"   Config 2: {len(text2)} chars")
        except:
            pass
        
        # Choose best text
        best_text = max(texts, key=len) if texts else ""
        
        print(f"   Best result: {len(best_text)} chars")
        if best_text:
            print(f"   First 100 chars: {best_text[:100].replace(chr(10), ' ')}")
        
        return best_text.strip()
        
    except Exception as e:
        print(f"❌ OCR failed: {e}")
        return ""

# ================= PARSING =================

def parse_fayda(front_text: str, back_text: str) -> dict:
    """Parse Ethiopian Fayda ID from OCR text."""
    print("\n" + "="*60)
    print("🔍 PARSING OCR TEXT")
    print("="*60)
    
    data = {
        "name": "", "dob": "", "sex": "", "expiry": "",
        "fan": "", "fin": "", "sin": "", 
        "nationality": "", "address": "", "phone": "", 
        "issue_date": "",
    }
    
    # Combine text
    all_text = front_text + "\n" + back_text
    lines = [line.strip() for line in all_text.split('\n') if line.strip()]
    
    print(f"📄 Total lines from OCR: {len(lines)}")
    for i, line in enumerate(lines[:20]):  # Show first 20 lines
        print(f"{i:2d}: {line}")
    
    # SIMPLE EXTRACTION - Just look for patterns in the text
    
    # 1. Look for name patterns
    for i, line in enumerate(lines):
        if "ሙሉ ስም" in line or "Full Name" in line:
            # Check next line
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                print(f"📍 Possible name on line {i+1}: '{next_line}'")
                # Clean up OCR noise
                cleaned = re.sub(r'[^\w\s|]', '', next_line)
                data["name"] = cleaned.strip()
                break
    
    # 2. Look for date of birth
    for line in lines:
        if "የትውልድ" in line or "Date of Birth" in line:
            # Extract date pattern
            date_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
            if date_match:
                data["dob"] = date_match.group(1)
            break
    
    # 3. Look for FCN/FAN (16-digit number)
    for line in lines:
        # Remove spaces and look for 16 consecutive digits
        no_spaces = line.replace(" ", "")
        fan_match = re.search(r'(\d{16})', no_spaces)
        if fan_match:
            data["fan"] = fan_match.group(1)
            break
    
    # 4. Look for phone number
    for line in lines:
        if "ስልክ" in line or "Phone" in line:
            phone_match = re.search(r'(\d{10})', line.replace(" ", ""))
            if phone_match:
                data["phone"] = phone_match.group(1)
                break
    
    # 5. Look for FIN
    for line in lines:
        if "FIN" in line:
            # Extract numbers after FIN
            fin_match = re.search(r'FIN\s*([\d\s]+)', line)
            if fin_match:
                fin_num = re.sub(r'\s+', '', fin_match.group(1))
                if len(fin_num) >= 12:
                    data["fin"] = fin_num
                    break
    
    # 6. Look for address
    for i, line in enumerate(lines):
        if "አድራሻ" in line or "Address" in line:
            # Collect next few lines
            address_parts = []
            for j in range(i+1, min(i+4, len(lines))):
                addr_line = lines[j]
                if addr_line and len(addr_line) > 3:
                    address_parts.append(addr_line)
            if address_parts:
                data["address"] = " ".join(address_parts)
                break
    
    print("\n📋 PARSED DATA:")
    for key, value in data.items():
        print(f"   {key:12}: '{value}'")
    
    return data

# ================= IMAGE GENERATION =================

def generate_id(data: dict, photo_qr_path: str, output_path: str):
    """Generate ID card with extracted data."""
    try:
        print(f"\n🎨 GENERATING ID CARD")
        print(f"   Template: {TEMPLATE_PATH}")
        print(f"   Photo/QR source: {photo_qr_path}")
        print(f"   Output: {output_path}")
        
        # Open template
        template = Image.open(TEMPLATE_PATH).convert("RGBA")
        print(f"   Template size: {template.size}")
        
        draw = ImageDraw.Draw(template)
        
        # Try to load font
        font_size = 40
        try:
            if os.path.exists(FONT_PATH):
                font = ImageFont.truetype(FONT_PATH, font_size)
                print(f"   Using font: {FONT_PATH} size {font_size}")
            else:
                font = ImageFont.load_default()
                print(f"   Using default font (custom font not found)")
        except Exception as font_error:
            print(f"   Font error: {font_error}")
            font = ImageFont.load_default()
        
        print(f"\n📝 PLACING TEXT:")
        
        # Define text positions with your coordinates
        text_positions = {
            "name": (210, 1120, "FRONT - Full Name"),
            "dob": (210, 1235, "FRONT - Date of Birth"),
            "sex": (210, 1325, "FRONT - Sex"),
            "expiry": (210, 1410, "FRONT - Expiry Date"),
            "fan": (210, 1515, "FRONT - FAN"),
            "sin": (390, 1555, "FRONT - SN"),
            "phone": (120, 1220, "BACK - Phone"),
            "nationality": (120, 1320, "BACK - Nationality"),
            "address": (120, 1425, "BACK - Address"),
            "fin": (760, 1220, "BACK - FIN"),
        }
        
        # Place each field
        for field, (x, y, description) in text_positions.items():
            value = data.get(field, "")
            if value:
                print(f"   ✅ {description} at ({x},{y}): '{value[:30]}...'")
                draw.text((x, y), str(value), fill="black", font=font)
            else:
                print(f"   ❌ {description} at ({x},{y}): NO DATA")
        
        # Date of Issue (vertical)
        issue_date = data.get("issue_date", "")
        if issue_date:
            print(f"   ✅ Date of Issue (vertical) at (1120,360): '{issue_date}'")
            # Create vertical text
            vertical_img = Image.new("RGBA", (780, 80), (255, 255, 255, 0))
            vertical_draw = ImageDraw.Draw(vertical_img)
            vertical_draw.text((0, 0), issue_date, fill="black", font=font)
            rotated = vertical_img.rotate(90, expand=True)
            template.paste(rotated, (1120, 360), rotated)
        
        print(f"\n📸 PROCESSING IMAGES:")
        
        # Crop and place images from 3rd screenshot
        try:
            photo_qr_img = Image.open(photo_qr_path).convert("RGBA")
            print(f"   Source image size: {photo_qr_img.size}")
            
            # Crop photo (160, 70, 560, 520)
            try:
                photo_crop = photo_qr_img.crop((160, 70, 560, 520))
                photo_crop = photo_crop.resize((300, 380))
                template.paste(photo_crop, (120, 140), photo_crop)
                print(f"   ✅ Photo cropped: (160,70,560,520) → (120,140,420,520)")
            except Exception as photo_err:
                print(f"   ❌ Photo crop failed: {photo_err}")
            
            # Crop QR (80, 650, 640, 1250)
            try:
                qr_crop = photo_qr_img.crop((80, 650, 640, 1250))
                qr_crop = qr_crop.resize((520, 520))
                template.paste(qr_crop, (1470, 40), qr_crop)
                print(f"   ✅ QR cropped: (80,650,640,1250) → (1470,40,1990,560)")
            except Exception as qr_err:
                print(f"   ❌ QR crop failed: {qr_err}")
                
        except Exception as img_err:
            print(f"   ❌ Image processing failed: {img_err}")
        
        # Save the image
        template.save(output_path)
        print(f"\n✅ Saved to: {output_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_debug_grid(template_path: str, output_path: str):
    """Create a debug image showing text positions."""
    try:
        template = Image.open(template_path).convert("RGBA")
        draw = ImageDraw.Draw(template)
        
        # Draw red boxes at text positions
        positions = [
            ((210, 1120, 210+820, 1120+95), "Name"),
            ((210, 1235, 210+820, 1235+75), "DOB"),
            ((210, 1325, 210+400, 1325+65), "Sex"),
            ((210, 1410, 210+820, 1410+75), "Expiry"),
            ((210, 1515, 210+300, 1515+70), "FAN"),
            ((390, 1555, 390+640, 1555+95), "SN"),
            ((1120, 360, 1120+80, 360+780), "Issue Date"),
            ((120, 1220, 120+600, 1220+85), "Phone"),
            ((120, 1320, 120+600, 1320+85), "Nationality"),
            ((120, 1425, 120+750, 1425+420), "Address"),
            ((760, 1220, 760+480, 1220+90), "FIN"),
            ((120, 140, 120+300, 140+380), "Photo"),
            ((1470, 40, 1470+520, 40+520), "QR"),
        ]
        
        for (x1, y1, x2, y2), label in positions:
            draw.rectangle([(x1, y1), (x2, y2)], outline="red", width=3)
            draw.text((x1, y1-25), label, fill="red")
        
        template.save(output_path)
        return True
    except Exception as e:
        print(f"❌ Debug grid failed: {e}")
        return False

# ================= MAIN =================

def main():
    """Start the bot."""
    print("🚀 Starting Fayda ID Bot...")
    
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN not set!")
        return
    
    # Check required files
    print("🔍 Checking files:")
    print(f"   Template: {TEMPLATE_PATH} - {'✅' if os.path.exists(TEMPLATE_PATH) else '❌'}")
    print(f"   Font: {FONT_PATH} - {'✅' if os.path.exists(FONT_PATH) else '❌'}")
    
    if not os.path.exists(TEMPLATE_PATH):
        print("❌ Template image is missing!")
        return
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("🤖 Bot is running and ready!")
    app.run_polling()

if __name__ == "__main__":
    main()
