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
        "Send me 3 screenshots in order:\n"
        "1️⃣ Front page of ID\n"
        "2️⃣ Back page of ID\n"
        "3️⃣ Photo + QR code\n\n"
        "⚠️ *Tips for best results:*\n"
        "• Take clear, well-lit screenshots\n"
        "• Ensure text is not blurry\n"
        "• Capture entire ID sections\n"
        "• Send images in correct order",
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
    
    print(f"📸 User {user_id}: Image {img_index} saved")
    
    # Show image info
    try:
        img = Image.open(img_path)
        print(f"   Size: {img.size}, Mode: {img.mode}")
    except:
        pass
    
    # Acknowledge receipt
    if img_index < 3:
        await update.message.reply_text(f"✅ Image {img_index}/3 received")
        return
    
    # All images received
    await update.message.reply_text("⏳ Processing all 3 images...")
    
    try:
        print("=" * 70)
        print(f"🔄 PROCESSING USER {user_id}")
        print("=" * 70)
        
        # Step 1: OCR on first image (front)
        await update.message.reply_text("🔍 Reading front page...")
        print("\n--- FRONT PAGE OCR ---")
        front_text = ocr_image(user_sessions[user_id][0])
        
        # Step 2: OCR on second image (back)
        await update.message.reply_text("🔍 Reading back page...")
        print("\n--- BACK PAGE OCR ---")
        back_text = ocr_image(user_sessions[user_id][1])
        
        # Combine texts
        combined_text = f"FRONT:\n{front_text}\n\nBACK:\n{back_text}"
        
        # Save OCR output for debugging
        debug_path = os.path.join(user_dir, "ocr_output.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(combined_text)
        print(f"📁 OCR output saved to: {debug_path}")
        
        # Send OCR preview to user
        preview = ""
        if front_text:
            preview += f"*Front page (first 300 chars):*\n```\n{front_text[:300]}\n```\n\n"
        if back_text:
            preview += f"*Back page (first 300 chars):*\n```\n{back_text[:300]}\n```"
        
        if preview:
            await update.message.reply_text(preview, parse_mode='Markdown')
        
        # Parse the data
        await update.message.reply_text("📋 Extracting ID information...")
        data = parse_fayda(front_text, back_text)
        
        # Show what we found
        found = {k: v for k, v in data.items() if v}
        print(f"\n📊 FOUND {len(found)} FIELDS:")
        for key, value in found.items():
            print(f"   {key}: {value}")
        
        if len(found) < 2:
            fields_list = ", ".join(found.keys()) if found else "nothing"
            await update.message.reply_text(
                f"⚠️ *Only found: {fields_list}*\n\n"
                f"Common issues:\n"
                f"• Screenshots might be blurry\n"
                f"• Text might be too small\n"
                f"• Try retaking clearer screenshots\n\n"
                f"*OCR extracted {len(front_text)+len(back_text)} characters total*",
                parse_mode='Markdown'
            )
            return
        
        # Generate ID
        await update.message.reply_text("🎨 Generating ID card...")
        output_path = os.path.join(user_dir, "final_id.png")
        
        success = generate_id(
            data, 
            user_sessions[user_id][0],  # Front image
            user_sessions[user_id][2],  # QR image
            output_path
        )
        
        if success:
            await update.message.reply_photo(
                photo=open(output_path, "rb"),
                caption=f"✅ *ID Generated!*\nFound {len(found)} fields including:\n{', '.join(list(found.keys())[:3])}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Failed to generate ID image")
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")
    
    finally:
        # Cleanup session
        if user_id in user_sessions:
            del user_sessions[user_id]

# ================= OCR =================

def ocr_image(path: str) -> str:
    """Extract text from image."""
    try:
        print(f"Processing: {os.path.basename(path)}")
        
        # Open image
        img = Image.open(path)
        original_size = img.size
        print(f"  Original size: {original_size}")
        
        # Resize if too small (helps OCR)
        if img.size[0] < 500 or img.size[1] < 500:
            scale = 2.0
            new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            print(f"  Resized to: {new_size}")
        
        # Convert to grayscale
        img = img.convert('L')
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)  # Increased contrast
        
        # Sharpen
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)
        
        # Try different OCR configurations
        texts = []
        
        # Config 1: Amharic + English
        try:
            text1 = pytesseract.image_to_string(
                img,
                lang='amh+eng',
                config='--psm 6 --oem 3'
            )
            texts.append(("amh+eng", text1))
        except:
            pass
        
        # Config 2: English only
        try:
            text2 = pytesseract.image_to_string(
                img,
                lang='eng',
                config='--psm 6 --oem 3'
            )
            texts.append(("eng", text2))
        except:
            pass
        
        # Config 3: Auto page segmentation
        try:
            text3 = pytesseract.image_to_string(
                img,
                lang='amh+eng',
                config='--psm 3 --oem 3'
            )
            texts.append(("auto", text3))
        except:
            pass
        
        # Choose the best result (most text)
        best_text = ""
        best_config = ""
        for config, text in texts:
            if len(text.strip()) > len(best_text.strip()):
                best_text = text
                best_config = config
        
        print(f"  Best config: {best_config}, Characters: {len(best_text)}")
        
        if best_text:
            # Count Amharic characters
            amh_chars = sum(1 for c in best_text if '\u1200' <= c <= '\u137F')
            print(f"  Amharic characters: {amh_chars}")
            print(f"  First 200 chars: {best_text[:200].replace(chr(10), ' ')}")
        
        return best_text.strip()
        
    except Exception as e:
        print(f"❌ OCR failed: {e}")
        return ""

# ================= PARSING =================

def parse_fayda(front_text: str, back_text: str) -> dict:
    """Parse Ethiopian Fayda ID from OCR text (specific to your format)."""
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
    
    print(f"📄 Total lines: {len(lines)}")
    for i, line in enumerate(lines):
        print(f"{i:2d}: {line}")
    
    # ============================================
    # 1. NAME - Look for "ሙሉ ስም | Full Name" pattern
    # ============================================
    for i, line in enumerate(lines):
        if "ሙሉ ስም | Full Name" in line or "Full Name" in line:
            # Your format shows name on next line
            if i + 1 < len(lines):
                name_line = lines[i + 1]
                print(f"📍 Found name line: '{name_line}'")
                
                # Your format: "ሳሙኤል ቀነኒሳ ሰልባና 5 Samuel Kenenisa Selbana g"
                # Extract Amharic and English parts
                parts = name_line.split()
                am_name_parts = []
                en_name_parts = []
                in_english = False
                
                for part in parts:
                    # Check if part contains Amharic characters
                    has_amharic = any('\u1200' <= c <= '\u137F' for c in part)
                    has_latin = any('A' <= c <= 'Z' or 'a' <= c <= 'z' for c in part)
                    
                    if has_amharic and not in_english:
                        am_name_parts.append(part)
                    elif has_latin:
                        in_english = True
                        en_name_parts.append(part)
                
                if am_name_parts:
                    data["name"] = " ".join(am_name_parts) + " | " + " ".join(en_name_parts)
                    print(f"✅ Name: {data['name']}")
                break
    
    # ============================================
    # 2. DATE OF BIRTH - "የትውልድ ቀን | Date of Birth"
    # ============================================
    for i, line in enumerate(lines):
        if "የትውልድ ቀን | Date of Birth" in line or "Date of Birth" in line:
            if i + 1 < len(lines):
                dob_line = lines[i + 1]
                print(f"📍 Found DOB line: '{dob_line}'")
                
                # Your format: "07/10/1992 | 2000/Jun/14"
                # Extract the Ethiopian date (first part)
                if "|" in dob_line:
                    eth_date = dob_line.split("|")[0].strip()
                    data["dob"] = eth_date
                    print(f"✅ DOB: {data['dob']}")
                else:
                    # Try to find date pattern
                    date_match = re.search(r'\d{2}/\d{2}/\d{4}', dob_line)
                    if date_match:
                        data["dob"] = date_match.group()
                        print(f"✅ DOB: {data['dob']}")
                break
    
    # ============================================
    # 3. SEX - "Sex" then "ወንድ | Male"
    # ============================================
    for i, line in enumerate(lines):
        if "Sex" in line or "ፆታ" in line:
            # Your format shows sex on same line or next
            if "ወንድ | Male" in line or "Male" in line:
                data["sex"] = "ወንድ | Male"
                print(f"✅ Sex: {data['sex']}")
                break
            elif i + 1 < len(lines):
                next_line = lines[i + 1]
                if "ወንድ | Male" in next_line or "Male" in next_line:
                    data["sex"] = "ወንድ | Male"
                    print(f"✅ Sex: {data['sex']}")
                    break
    
    # ============================================
    # 4. EXPIRY DATE - "የሚያበቃበት ቀን | Date of Expiry"
    # ============================================
    for i, line in enumerate(lines):
        if "የሚያበቃበት ቀን | Date of Expiry" in line or "Date of Expiry" in line:
            if i + 1 < len(lines):
                expiry_line = lines[i + 1]
                print(f"📍 Found expiry line: '{expiry_line}'")
                
                # Extract date (first date pattern found)
                date_match = re.search(r'\d{4}/\d{2}/\d{2}', expiry_line)
                if date_match:
                    data["expiry"] = date_match.group()
                    print(f"✅ Expiry: {data['expiry']}")
                break
    
    # ============================================
    # 5. FAN/FCN - Look for card number
    # ============================================
    for i, line in enumerate(lines):
        # Look for "ካርድ" followed by numbers (from your OCR: "ካርድ 503592")
        if "ካርድ" in line:
            # Extract all numbers from this line
            numbers = re.findall(r'\d+', line)
            if numbers:
                # Take the longest number (likely the FCN)
                longest_num = max(numbers, key=len)
                if len(longest_num) >= 12:  # FCN is usually 16 digits
                    data["fan"] = longest_num
                    print(f"✅ FCN: {data['fan']}")
                    break
    
    # Also search for 16-digit pattern anywhere
    if not data["fan"]:
        for line in lines:
            # Look for 16 consecutive digits
            fan_match = re.search(r'(\d{16})', line.replace(" ", ""))
            if fan_match:
                data["fan"] = fan_match.group(1)
                print(f"✅ FCN (pattern): {data['fan']}")
                break
    
    # ============================================
    # 6. PHONE NUMBER - "ስልክ | Phone Number"
    # ============================================
    for i, line in enumerate(lines):
        if "ስልክ | Phone Number" in line or "Phone Number" in line:
            # Your OCR shows: "ስልክ | Phone Number on 60103 wi |FIN"
            # Extract phone number from this or next line
            phone_match = re.search(r'(\d{10})', line)
            if phone_match:
                data["phone"] = phone_match.group(1)
                print(f"✅ Phone: {data['phone']}")
                break
            
            # Check next line
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                phone_match = re.search(r'(\d{10})', next_line)
                if phone_match:
                    data["phone"] = phone_match.group(1)
                    print(f"✅ Phone (next line): {data['phone']}")
                    break
    
    # ============================================
    # 7. FIN - Look for "FIN" with numbers
    # ============================================
    for line in lines:
        if "FIN" in line:
            # Extract numbers after FIN
            fin_match = re.search(r'FIN\s*(\d{4}\s?\d{4}\s?\d{4}\s?\d{4}|\d{13,16})', line)
            if fin_match:
                fin_num = fin_match.group(1).replace(" ", "")
                if len(fin_num) >= 12:
                    data["fin"] = fin_num
                    print(f"✅ FIN: {data['fin']}")
                    break
    
    # ============================================
    # 8. NATIONALITY - "ዜግነት | Nationality"
    # ============================================
    for i, line in enumerate(lines):
        if "ዜግነት | Nationality" in line or "Nationality" in line:
            if i + 1 < len(lines):
                nat_line = lines[i + 1]
                # Check if it contains "ኢትዮጵያ" or "Ethiopian"
                if "ኢትዮጵያ" in nat_line or "Ethiopian" in nat_line:
                    data["nationality"] = "ኢትዮጵያ | Ethiopian"
                    print(f"✅ Nationality: {data['nationality']}")
                break
    
    # ============================================
    # 9. ADDRESS - "አድራሻ | Address"
    # ============================================
    address_lines = []
    for i, line in enumerate(lines):
        if "አድራሻ | Address" in line or "Address" in line:
            # Collect next few lines for address
            for j in range(i + 1, min(i + 5, len(lines))):
                addr_line = lines[j]
                # Stop if we hit another field
                if any(keyword in addr_line for keyword in ["ስም", "Name", "Date", "Phone", "FIN", "Nationality"]):
                    break
                if addr_line.strip() and len(addr_line.strip()) > 2:
                    address_lines.append(addr_line.strip())
            
            if address_lines:
                data["address"] = " ".join(address_lines)
                print(f"✅ Address: {data['address'][:50]}...")
            break
    
    # ============================================
    # 10. SN (SERIAL NUMBER) - Look near barcode
    # ============================================
    # SN is often near barcode or as a separate number
    for line in lines:
        # Look for patterns like "SN: 123456" or serial numbers
        sn_match = re.search(r'(?:SN|Serial)[:\s]*(\d+)', line, re.IGNORECASE)
        if sn_match:
            data["sin"] = sn_match.group(1)
            print(f"✅ SN: {data['sin']}")
            break
    
    # ============================================
    # 11. DATE OF ISSUE - Might be on right side
    # ============================================
    # Look for issue date patterns
    for line in lines:
        if "የተሰጠበት ቀን" in line or "Date of Issue" in line:
            date_match = re.search(r'\d{4}/\d{2}/\d{2}', line)
            if date_match:
                data["issue_date"] = date_match.group()
                print(f"✅ Issue Date: {data['issue_date']}")
                break
    
    print("\n" + "="*60)
    print("📋 PARSING RESULTS")
    print("="*60)
    for key, value in data.items():
        if value:
            print(f"✅ {key:12}: {value}")
        else:
            print(f"❌ {key:12}: Not found")
    
    return data

# ================= IMAGE GENERATION =================

def generate_id(data: dict, photo_path: str, qr_path: str, output_path: str):
    """Generate ID card with extracted data."""
    try:
        template = Image.open(TEMPLATE_PATH).convert("RGBA")
        draw = ImageDraw.Draw(template)
        
        # Try to load font, fallback to default
        try:
            font_large = ImageFont.truetype(FONT_PATH, 42)
            font_medium = ImageFont.truetype(FONT_PATH, 36)
            font_small = ImageFont.truetype(FONT_PATH, 32)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # FRONT SIDE
        fields_front = [
            ("name", 210, 1120, font_large),
            ("dob", 210, 1235, font_medium),
            ("sex", 210, 1325, font_medium),
            ("expiry", 210, 1410, font_medium),
            ("fan", 210, 1515, font_large),
            ("sin", 390, 1555, font_small),
        ]
        
        for field, x, y, font in fields_front:
            value = data.get(field, "")
            if value:
                draw.text((x, y), value, fill="black", font=font)
                print(f"   Placed {field} at ({x},{y})")
        
        # Date of Issue (vertical)
        issue_date = data.get("issue_date", "")
        if issue_date:
            vertical_img = Image.new("RGBA", (780, 80), (255, 255, 255, 0))
            vertical_draw = ImageDraw.Draw(vertical_img)
            vertical_draw.text((0, 0), issue_date, fill="black", font=font_small)
            rotated = vertical_img.rotate(90, expand=True)
            template.paste(rotated, (1120, 360), rotated)
            print(f"   Placed issue_date vertically")
        
        # BACK SIDE
        fields_back = [
            ("phone", 120, 1220, font_medium),
            ("nationality", 120, 1320, font_medium),
            ("fin", 760, 1220, font_large),
        ]
        
        for field, x, y, font in fields_back:
            value = data.get(field, "")
            if value:
                draw.text((x, y), value, fill="black", font=font)
                print(f"   Placed {field} at ({x},{y})")
        
        # Address (multi-line)
        address = data.get("address", "")
        if address:
            # Simple single line for now
            draw.text((120, 1425), address[:40], fill="black", font=font_small)
            print(f"   Placed address: {address[:20]}...")
        
        # Add photos
        try:
            # Main photo
            if os.path.exists(photo_path):
                photo = Image.open(photo_path).convert("RGBA")
                # Try to crop to face area (adjust based on your screenshots)
                # For now, resize and place
                photo = photo.resize((300, 380))
                template.paste(photo, (120, 140), photo)
                print("   Added main photo")
            
            # QR code
            if os.path.exists(qr_path):
                qr_img = Image.open(qr_path).convert("RGBA")
                qr_img = qr_img.resize((520, 520))
                template.paste(qr_img, (1470, 40), qr_img)
                print("   Added QR code")
        except Exception as e:
            print(f"⚠️ Image placement error: {e}")
        
        template.save(output_path)
        print(f"✅ Generated: {output_path}")
        return True
        
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

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
    
    print("🤖 Bot is running and ready!")
    app.run_polling()

if __name__ == "__main__":
    main()
