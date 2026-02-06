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
    """Handle /start command - SIMPLIFIED."""
    user_id = update.effective_user.id
    
    # Initialize or reset session
    user_sessions[user_id] = {
        "images": [],
        "data": {},
        "step": 0
    }
    
    print(f"🚀 New session for user {user_id}")
    
    await update.message.reply_text(
        "📄 *Fayda ID Bot*\n\n"
        "Send me 3 screenshots in this order:\n"
        "1️⃣ Front page of ID\n"
        "2️⃣ Back page of ID\n"
        "3️⃣ Photo + QR code page\n\n"
        "I'll extract information and generate an ID card.",
        parse_mode='Markdown'
    )
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads - FIXED SESSION VERSION."""
    user_id = update.effective_user.id
    print(f"\n📸 Photo from user {user_id}")
    
    # DEBUG: Show all current sessions
    print(f"📋 Current sessions: {list(user_sessions.keys())}")
    
    # Initialize session if not exists
    if user_id not in user_sessions:
        print(f"❌ No session for user {user_id}, creating new one...")
        user_sessions[user_id] = {
            "images": [],
            "data": {},
            "step": 0
        }
        # Don't ask to /start - just accept the photo
        # await update.message.reply_text("Please send /start first")
        # return
    
    print(f"✅ Session found for user {user_id}")
    
    # Get photo
    try:
        photo = update.message.photo[-1]
        print(f"   Photo size: {photo.file_size} bytes")
    except Exception as e:
        print(f"❌ Failed to get photo: {e}")
        await update.message.reply_text("❌ Failed to get photo")
        return
    
    file = await photo.get_file()
    
    # Create temp directory
    temp_dir = "/tmp/fayda_bot"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Save image
    img_index = len(user_sessions[user_id]["images"])
    img_path = os.path.join(temp_dir, f"user_{user_id}_{img_index}.png")
    
    print(f"💾 Saving image {img_index + 1} to: {img_path}")
    
    try:
        await file.download_to_drive(img_path)
        file_size = os.path.getsize(img_path)
        print(f"✅ Saved: {file_size} bytes")
        
        user_sessions[user_id]["images"].append(img_path)
        
        # Send acknowledgement
        await update.message.reply_text(f"✅ Image {img_index + 1}/3 received")
        
        # Check if we have all 3 images
        if len(user_sessions[user_id]["images"]) < 3:
            print(f"⏳ Waiting for more images ({len(user_sessions[user_id]['images'])}/3)")
            return
        
        print("\n🎯 ALL 3 IMAGES RECEIVED!")
        print(f"   Images: {user_sessions[user_id]['images']}")
        
        # Process the images
        await process_user_images(update, user_id)
        
    except Exception as e:
        print(f"❌ Error saving image: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text("❌ Error saving image")
        async def process_user_images(update: Update, user_id: int):
    """Process all 3 images for a user."""
    try:
        print(f"\n🔄 PROCESSING images for user {user_id}")
        
        if user_id not in user_sessions:
            await update.message.reply_text("❌ Session expired. Please send /start")
            return
        
        images = user_sessions[user_id]["images"]
        if len(images) < 3:
            await update.message.reply_text(f"❌ Need 3 images, got {len(images)}")
            return
        
        await update.message.reply_text("⏳ Processing images...")
        
        # Test OCR on first image only (for now)
        print("🔍 Testing OCR on first image...")
        front_text = ocr_space_api(images[0])
        print(f"   OCR result: {len(front_text)} chars")
        
        if front_text:
            await update.message.reply_text(f"✅ OCR extracted {len(front_text)} characters")
        else:
            await update.message.reply_text("❌ OCR failed")
        
        # Create a simple test image
        output_path = f"/tmp/fayda_bot/user_{user_id}_output.png"
        print(f"🎨 Creating test image at: {output_path}")
        
        # Create test image
        test_img = Image.new('RGB', (800, 400), color='white')
        draw = ImageDraw.Draw(test_img)
        
        # Add test text
        draw.text((10, 10), "Fayda ID Bot - Test Output", fill='black')
        draw.text((10, 50), f"User: {user_id}", fill='blue')
        draw.text((10, 90), f"Images received: {len(images)}", fill='green')
        draw.text((10, 130), f"OCR chars: {len(front_text)}", fill='red')
        draw.text((10, 170), "✅ Bot is working!", fill='purple')
        
        # Save
        test_img.save(output_path)
        print(f"✅ Test image created: {os.path.getsize(output_path)} bytes")
        
        # Send to user
        with open(output_path, "rb") as photo_file:
            await update.message.reply_photo(
                photo=photo_file,
                caption="🧪 *Test Output* - Bot is working!\nNext: Add OCR and template",
                parse_mode='Markdown'
            )
        
        print(f"✅ Processing complete for user {user_id}")
        
    except Exception as e:
        print(f"❌ Processing error: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(f"❌ Processing error: {str(e)[:100]}")
    
    finally:
        # Cleanup
        cleanup_user_session(user_id)
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
        
        import glob
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
    """MINIMAL TEST VERSION - just place photos, no text."""
    print(f"\n🎨 GENERATE_ID CALLED - MINIMAL TEST")
    print(f"   Photo/QR path: {photo_qr_path}")
    print(f"   Output path: {output_path}")
    print(f"   Data fields: {[k for k, v in data.items() if v]}")
    
    try:
        # Just create a simple image to test
        test_img = Image.new('RGB', (500, 300), color='white')
        draw = ImageDraw.Draw(test_img)
        draw.text((10, 10), "TEST IMAGE - Bot is working!", fill='black')
        draw.text((10, 40), f"Found {len([v for v in data.values() if v])} fields", fill='blue')
        
        # Save it
        test_img.save(output_path)
        print(f"✅ Created test image at {output_path}")
        
        # Also create a debug version
        debug_path = output_path.replace(".png", "_debug.png")
        debug_img = Image.new('RGB', (500, 300), color='yellow')
        debug_draw = ImageDraw.Draw(debug_img)
        debug_draw.text((10, 10), "DEBUG IMAGE", fill='red')
        debug_draw.text((10, 40), f"Photo path exists: {os.path.exists(photo_qr_path)}", fill='red')
        debug_img.save(debug_path)
        print(f"✅ Created debug image at {debug_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ generate_id failed: {e}")
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
