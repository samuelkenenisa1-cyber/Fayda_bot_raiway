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
    """Parse Ethiopian Fayda ID from OCR text with detailed logging."""
    print("\n" + "="*80)
    print("🔍 PARSING OCR TEXT - DETAILED DEBUG")
    print("="*80)
    
    data = {
        "name": "", "dob": "", "sex": "", "expiry": "",
        "fan": "", "fin": "", "sin": "", 
        "nationality": "", "address": "", "phone": "", 
        "issue_date": "",
    }
    
    # Save raw OCR for analysis
    raw_ocr = f"=== FRONT TEXT ===\n{front_text}\n\n=== BACK TEXT ===\n{back_text}"
    print(raw_ocr)
    
    # Combine and clean lines
    all_text = front_text + "\n" + back_text
    lines = [line.strip() for line in all_text.split('\n') if line.strip()]
    
    print(f"\n📄 TOTAL LINES FROM OCR: {len(lines)}")
    for i, line in enumerate(lines):
        print(f"{i:3d}: '{line}'")
    
    print("\n" + "-"*80)
    print("🔎 SEARCHING FOR SPECIFIC PATTERNS")
    print("-"*80)
    
    # 1. NAME - Look for exact pattern from your OCR
    print("\n1. Searching for NAME...")
    for i, line in enumerate(lines):
        if "ሙሉ ስም" in line or "Full Name" in line:
            print(f"   Found name header at line {i}: '{line}'")
            # Check next 3 lines
            for j in range(i+1, min(i+4, len(lines))):
                print(f"   Checking line {j}: '{lines[j]}'")
                # Look for Amharic characters
                if any('\u1200' <= c <= '\u137F' for c in lines[j]):
                    data["name"] = lines[j].strip()
                    print(f"   ✅ Found name: '{data['name']}'")
                    break
            break
    
    # 2. DATE OF BIRTH
    print("\n2. Searching for DATE OF BIRTH...")
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if "የትውልድ" in line or "date of birth" in line_lower or "dob" in line_lower:
            print(f"   Found DOB header at line {i}: '{line}'")
            # Look for date pattern in this line or next
            search_text = line + " " + (lines[i+1] if i+1 < len(lines) else "")
            print(f"   Searching in: '{search_text[:50]}...'")
            
            # Try different date patterns
            patterns = [
                r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
                r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
                r'\d{2}-\d{2}-\d{4}',  # DD-MM-YYYY
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, search_text)
                if matches:
                    data["dob"] = matches[0]
                    print(f"   ✅ Found DOB with pattern {pattern}: '{data['dob']}'")
                    break
            break
    
    # 3. FCN/FAN NUMBER
    print("\n3. Searching for FCN/FAN...")
    for i, line in enumerate(lines):
        line_no_spaces = line.replace(" ", "")
        print(f"   Line {i} (no spaces): '{line_no_spaces[:50]}...'")
        
        # Look for 16-digit number
        fan_match = re.search(r'(\d{16})', line_no_spaces)
        if fan_match:
            data["fan"] = fan_match.group(1)
            print(f"   ✅ Found FCN: '{data['fan']}'")
            break
        
        # Also check for "ካርድ" followed by numbers
        if "ካርድ" in line:
            print(f"   Found 'ካርድ' at line {i}")
            numbers = re.findall(r'\d+', line)
            if numbers:
                print(f"   Numbers in line: {numbers}")
                longest = max(numbers, key=len)
                if len(longest) >= 12:
                    data["fan"] = longest
                    print(f"   ✅ Found FCN from 'ካርድ': '{data['fan']}'")
                    break
    
    # 4. PHONE NUMBER
    print("\n4. Searching for PHONE...")
    for i, line in enumerate(lines):
        if "ስልክ" in line or "Phone" in line:
            print(f"   Found phone header at line {i}: '{line}'")
            # Look for 10-digit number
            phone_match = re.search(r'(\d{10})', line.replace(" ", ""))
            if phone_match:
                data["phone"] = phone_match.group(1)
                print(f"   ✅ Found phone in same line: '{data['phone']}'")
                break
            
            # Check next line
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                phone_match = re.search(r'(\d{10})', next_line.replace(" ", ""))
                if phone_match:
                    data["phone"] = phone_match.group(1)
                    print(f"   ✅ Found phone in next line: '{data['phone']}'")
                    break
    
    # 5. SEX/GENDER
    print("\n5. Searching for SEX...")
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if "sex" in line_lower or "ፆታ" in line:
            print(f"   Found sex header at line {i}: '{line}'")
            # Check for male/female
            if "male" in line_lower or "ወንድ" in line:
                data["sex"] = "ወንድ | Male"
                print(f"   ✅ Found sex in same line: '{data['sex']}'")
                break
            elif i + 1 < len(lines):
                next_line = lines[i + 1].lower()
                if "male" in next_line or "ወንድ" in lines[i + 1]:
                    data["sex"] = "ወንድ | Male"
                    print(f"   ✅ Found sex in next line: '{data['sex']}'")
                    break
    
    # 6. FIN
    print("\n6. Searching for FIN...")
    for i, line in enumerate(lines):
        if "FIN" in line:
            print(f"   Found FIN at line {i}: '{line}'")
            # Extract all numbers from the line
            numbers = re.findall(r'\d+', line.replace(" ", ""))
            if numbers:
                print(f"   Numbers in line: {numbers}")
                # Take the longest number (likely FIN)
                longest = max(numbers, key=len)
                if len(longest) >= 12:
                    data["fin"] = longest
                    print(f"   ✅ Found FIN: '{data['fin']}'")
                    break
    
    # 7. NATIONALITY
    print("\n7. Searching for NATIONALITY...")
    for i, line in enumerate(lines):
        if "ዜግነት" in line or "Nationality" in line:
            print(f"   Found nationality header at line {i}: '{line}'")
            # Check next line
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if "ኢትዮጵያ" in next_line or "Ethiopian" in next_line:
                    data["nationality"] = "ኢትዮጵያ | Ethiopian"
                    print(f"   ✅ Found nationality: '{data['nationality']}'")
                    break
    
    # 8. ADDRESS
    print("\n8. Searching for ADDRESS...")
    for i, line in enumerate(lines):
        if "አድራሻ" in line or "Address" in line:
            print(f"   Found address header at line {i}: '{line}'")
            # Collect next 3-5 lines
            address_lines = []
            for j in range(i + 1, min(i + 6, len(lines))):
                addr_line = lines[j]
                # Skip if it looks like another field
                if any(keyword in addr_line for keyword in ["ስም", "Name", "Phone", "FIN", "Nationality"]):
                    break
                if addr_line.strip():
                    address_lines.append(addr_line.strip())
                    print(f"   Address line {j}: '{addr_line}'")
            
            if address_lines:
                data["address"] = " | ".join(address_lines)
                print(f"   ✅ Found address: '{data['address'][:50]}...'")
            break
    
    # 9. EXPIRY DATE
    print("\n9. Searching for EXPIRY DATE...")
    for i, line in enumerate(lines):
        if "የሚያበቃበት" in line or "Expiry" in line.lower():
            print(f"   Found expiry header at line {i}: '{line}'")
            # Look for date pattern
            date_match = re.search(r'\d{4}/\d{2}/\d{2}', line)
            if date_match:
                data["expiry"] = date_match.group()
                print(f"   ✅ Found expiry: '{data['expiry']}'")
                break
            elif i + 1 < len(lines):
                next_line = lines[i + 1]
                date_match = re.search(r'\d{4}/\d{2}/\d{2}', next_line)
                if date_match:
                    data["expiry"] = date_match.group()
                    print(f"   ✅ Found expiry in next line: '{data['expiry']}'")
                    break
    
    print("\n" + "="*80)
    print("📋 FINAL PARSED DATA SUMMARY")
    print("="*80)
    
    found_count = 0
    for key, value in data.items():
        if value:
            found_count += 1
            print(f"✅ {key:12}: '{value}'")
        else:
            print(f"❌ {key:12}: NOT FOUND")
    
    print(f"\n📊 Total fields found: {found_count}/11")
    
    return data

# ================= IMAGE GENERATION =================

def generate_id(data: dict, photo_qr_path: str, output_path: str):
    """Generate ID card with data and cropped images."""
    try:
        print(f"\n🎨 GENERATING ID CARD - DEBUG MODE")
        print(f"Data received: {len(data)} fields")
        
        # SHOW ALL DATA
        print("📋 ALL DATA RECEIVED:")
        for key, value in data.items():
            print(f"  {key:12}: '{value}'")
        
        # Open template
        template = Image.open(TEMPLATE_PATH).convert("RGBA")
        print(f"📐 Template size: {template.size}")
        
        draw = ImageDraw.Draw(template)
        
        # Try different font approaches
        font_success = False
        try:
            if os.path.exists(FONT_PATH):
                font_large = ImageFont.truetype(FONT_PATH, 42)
                font_medium = ImageFont.truetype(FONT_PATH, 36)
                font_small = ImageFont.truetype(FONT_PATH, 32)
                print(f"✅ Font loaded: {FONT_PATH}")
                font_success = True
            else:
                print(f"❌ Font file not found: {FONT_PATH}")
                raise FileNotFoundError
        except Exception as font_error:
            print(f"⚠️ Font error: {font_error}")
            print("🔄 Using default font")
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Test font by drawing a test text
        test_position = (50, 50)
        draw.text(test_position, "TEST FONT", fill="red", font=font_large)
        print(f"🧪 Test text drawn at {test_position} in RED")
        
        print("\n📝 PLACING TEXT AT COORDINATES:")
        
        # FRONT SIDE with your exact coordinates
        front_fields = [
            ("name", 210, 1120, font_large, "Full Name"),
            ("dob", 210, 1235, font_medium, "Date of Birth"),
            ("sex", 210, 1325, font_medium, "Sex"),
            ("expiry", 210, 1410, font_medium, "Expiry Date"),
            ("fan", 210, 1515, font_large, "FAN"),
            ("sin", 390, 1555, font_small, "SN"),
        ]
        
        for field, x, y, font, label in front_fields:
            value = data.get(field, "")
            if value:
                print(f"  ✅ {label} at ({x},{y}): '{value[:20]}...'")
                draw.text((x, y), str(value), fill="black", font=font)
                # Draw a green dot at the position for debugging
                draw.ellipse([(x-5, y-5), (x+5, y+5)], fill="green")
            else:
                print(f"  ❌ {label} at ({x},{y}): NO DATA")
        
        # Date of Issue (vertical)
        issue_date = data.get("issue_date", "")
        if issue_date:
            print(f"  ✅ Issue Date (vertical) at (1120,360): '{issue_date}'")
            # Draw a blue box where vertical text should go
            draw.rectangle([(1120, 360), (1120+80, 360+780)], outline="blue", width=2)
        
        # BACK SIDE
        back_fields = [
            ("phone", 120, 1220, font_medium, "Phone"),
            ("nationality", 120, 1320, font_medium, "Nationality"),
            ("address", 120, 1425, font_small, "Address"),
            ("fin", 760, 1220, font_large, "FIN"),
        ]
        
        for field, x, y, font, label in back_fields:
            value = data.get(field, "")
            if value:
                print(f"  ✅ {label} at ({x},{y}): '{value[:20]}...'")
                draw.text((x, y), str(value), fill="black", font=font)
                # Draw a red dot at the position
                draw.ellipse([(x-5, y-5), (x+5, y+5)], fill="red")
            else:
                print(f"  ❌ {label} at ({x},{y}): NO DATA")
        
        # Draw coordinate grid for debugging
        print("\n📐 Drawing debug grid...")
        for x in [210, 120, 760, 390, 1120]:
            for y in [1120, 1235, 1325, 1410, 1515, 1555, 1220, 1320, 1425, 360]:
                draw.ellipse([(x-2, y-2), (x+2, y+2)], fill="blue")
        
        # Add images (keep your existing code)
        print("\n📸 Processing images...")
        try:
            photo_img = Image.open(photo_qr_path).convert("RGBA")
            print(f"  Source image: {photo_img.size}")
            
            # Photo
            photo_crop = photo_img.crop((160, 70, 560, 520))
            photo_crop = photo_crop.resize((300, 380))
            template.paste(photo_crop, (120, 140), photo_crop)
            print(f"  ✅ Photo: (160,70,560,520) → (120,140,420,520)")
            
            # Draw photo area box
            draw.rectangle([(120, 140), (120+300, 140+380)], outline="purple", width=3)
            
            # QR
            qr_crop = photo_img.crop((80, 650, 640, 1250))
            qr_crop = qr_crop.resize((520, 520))
            template.paste(qr_crop, (1470, 40), qr_crop)
            print(f"  ✅ QR: (80,650,640,1250) → (1470,40,1990,560)")
            
            # Draw QR area box
            draw.rectangle([(1470, 40), (1470+520, 40+520)], outline="orange", width=3)
                
        except Exception as img_err:
            print(f"  ⚠️ Image error: {img_err}")
        
        # Save debug version
        debug_path = output_path.replace(".png", "_debug.png")
        template.save(debug_path)
        print(f"\n✅ Debug image saved: {debug_path}")
        
        # Also save the normal version
        template.save(output_path)
        print(f"✅ Final image saved: {output_path}")
        
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
    print("=" * 50)
    
    # Check files
    print("🔍 Checking files:")
    print(f"  Template: {TEMPLATE_PATH} - {'✅' if os.path.exists(TEMPLATE_PATH) else '❌'}")
    print(f"  Font: {FONT_PATH} - {'✅' if os.path.exists(FONT_PATH) else '❌'}")
    
    if os.path.exists(FONT_PATH):
        # Test if font can be loaded
        try:
            test_font = ImageFont.truetype(FONT_PATH, 20)
            print(f"  Font test: ✅ Can load '{FONT_PATH}'")
        except Exception as e:
            print(f"  Font test: ❌ Cannot load: {e}")
    else:
        print("  ⚠️ Font file missing - will use default font")
    
    print("=" * 50)
    
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN not set!")
        return
   
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
