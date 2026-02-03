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
    
    print(f"📸 User {user_id}: Image {img_index} saved")
    
    # Show image info
    try:
        img = Image.open(img_path)
        print(f"   Size: {img.size}")
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
        front_text = ocr_image(user_sessions[user_id][0])
        
        # Step 2: OCR on second image (back)
        await update.message.reply_text("🔍 Reading back page...")
        back_text = ocr_image(user_sessions[user_id][1])
        
        # Parse the data
        await update.message.reply_text("📋 Extracting ID information...")
        data = parse_fayda(front_text, back_text)
        
        # Show what we found
        found = {k: v for k, v in data.items() if v}
        
        if len(found) < 4:
            fields_list = ", ".join(found.keys()) if found else "nothing"
            await update.message.reply_text(
                f"⚠️ *Only found: {fields_list}*\n\n"
                f"Please send clearer screenshots.",
                parse_mode='Markdown'
            )
            return
        
        # Generate ID
        await update.message.reply_text("🎨 Generating ID card...")
        output_path = os.path.join(user_dir, "final_id.png")
        
        success = generate_id(
            data, 
            user_sessions[user_id][2],  # Third image has photo + QR
            output_path
        )
        
        if success:
            # Create summary message
            summary = f"✅ *ID Generated Successfully!*\n\n"
            summary += f"*Extracted Data:*\n"
            for key, value in found.items():
                if value and len(value) < 50:  # Show shorter values
                    summary += f"• *{key.title()}*: {value}\n"
            
            await update.message.reply_photo(
                photo=open(output_path, "rb"),
                caption=summary,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Failed to generate ID image")
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
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
        
        # Enhance for better OCR
        img = img.convert('L')  # Grayscale
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        
        # Try OCR with Amharic + English
        text = pytesseract.image_to_string(
            img,
            lang='amh+eng',
            config='--psm 6 --oem 3'
        )
        
        print(f"  Characters extracted: {len(text)}")
        return text.strip()
        
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
    
    print(f"📄 Total lines: {len(lines)}")
    
    # 1. NAME - "ሙሉ ስም | Full Name"
    for i, line in enumerate(lines):
        if "ሙሉ ስም | Full Name" in line:
            if i + 1 < len(lines):
                name_line = lines[i + 1]
                # Extract name parts
                parts = name_line.split()
                am_parts = []
                en_parts = []
                
                for part in parts:
                    # Check if part contains Amharic
                    if any('\u1200' <= c <= '\u137F' for c in part):
                        am_parts.append(part)
                    elif any('A' <= c <= 'Z' or 'a' <= c <= 'z' for c in part):
                        en_parts.append(part)
                
                if am_parts and en_parts:
                    data["name"] = " ".join(am_parts) + " | " + " ".join(en_parts)
                    print(f"✅ Name: {data['name']}")
                break
    
    # 2. DATE OF BIRTH - "የትውልድ ቀን | Date of Birth"
    for i, line in enumerate(lines):
        if "የትውልድ ቀን | Date of Birth" in line:
            if i + 1 < len(lines):
                dob_line = lines[i + 1]
                # Extract first date (07/10/1992)
                date_match = re.search(r'\d{2}/\d{2}/\d{4}', dob_line)
                if date_match:
                    data["dob"] = date_match.group()
                    print(f"✅ DOB: {data['dob']}")
                break
    
    # 3. SEX - Look for "ወንድ | Male"
    for i, line in enumerate(lines):
        if "Sex" in line:
            # Check this line and next
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
    
    # 4. EXPIRY DATE - "የሚያበቃበት ቀን | Date of Expiry"
    for i, line in enumerate(lines):
        if "የሚያበቃበት ቀን | Date of Expiry" in line:
            if i + 1 < len(lines):
                expiry_line = lines[i + 1]
                date_match = re.search(r'\d{4}/\d{2}/\d{2}', expiry_line)
                if date_match:
                    data["expiry"] = date_match.group()
                    print(f"✅ Expiry: {data['expiry']}")
                break
    
    # 5. FAN/FCN - Look for card number
    for line in lines:
        if "ካርድ" in line:
            # Extract longest number in the line
            numbers = re.findall(r'\d+', line)
            if numbers:
                longest = max(numbers, key=len)
                if len(longest) >= 12:
                    data["fan"] = longest
                    print(f"✅ FCN: {data['fan']}")
                    break
    
    # 6. PHONE NUMBER - "ስልክ | Phone Number"
    for i, line in enumerate(lines):
        if "ስልክ | Phone Number" in line:
            # Extract 10-digit number
            phone_match = re.search(r'(\d{10})', line)
            if phone_match:
                data["phone"] = phone_match.group(1)
                print(f"✅ Phone: {data['phone']}")
                break
            
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                phone_match = re.search(r'(\d{10})', next_line)
                if phone_match:
                    data["phone"] = phone_match.group(1)
                    print(f"✅ Phone (next line): {data['phone']}")
                    break
    
    # 7. FIN - Look for "FIN" with numbers
    for line in lines:
        if "FIN" in line:
            # Extract numbers after FIN
            fin_match = re.search(r'FIN\s*(\d[\d\s]+)', line)
            if fin_match:
                fin_num = re.sub(r'\s+', '', fin_match.group(1))
                if len(fin_num) >= 12:
                    data["fin"] = fin_num
                    print(f"✅ FIN: {data['fin']}")
                    break
    
    # 8. NATIONALITY - "ዜግነት | Nationality"
    for i, line in enumerate(lines):
        if "ዜግነት | Nationality" in line:
            if i + 1 < len(lines):
                nat_line = lines[i + 1]
                if "ኢትዮጵያ" in nat_line or "Ethiopian" in nat_line:
                    data["nationality"] = "ኢትዮጵያ | Ethiopian"
                    print(f"✅ Nationality: {data['nationality']}")
                break
    
    # 9. ADDRESS - "አድራሻ | Address"
    address_lines = []
    for i, line in enumerate(lines):
        if "አድራሻ | Address" in line:
            # Collect next 3 lines
            for j in range(i + 1, min(i + 4, len(lines))):
                addr_line = lines[j]
                if addr_line.strip() and len(addr_line.strip()) > 2:
                    address_lines.append(addr_line.strip())
            
            if address_lines:
                data["address"] = " ".join(address_lines)
                print(f"✅ Address: {data['address'][:50]}...")
            break
    
    # 10. SN - Look for serial number
    for line in lines:
        if "SN" in line or "Serial" in line:
            sn_match = re.search(r'(?:SN|Serial)[:\s]*(\d+)', line, re.IGNORECASE)
            if sn_match:
                data["sin"] = sn_match.group(1)
                print(f"✅ SN: {data['sin']}")
                break
    
    print("\n" + "="*60)
    print("📋 PARSING RESULTS")
    print("="*60)
    for key, value in data.items():
        if value:
            print(f"✅ {key:12}: {value}")
    
    return data

# ================= IMAGE GENERATION =================

def generate_id(data: dict, photo_qr_path: str, output_path: str):
    """Generate ID card with extracted data and cropped images."""
    try:
        template = Image.open(TEMPLATE_PATH).convert("RGBA")
        draw = ImageDraw.Draw(template)
        
        # Load font
        try:
            font_large = ImageFont.truetype(FONT_PATH, 42)
            font_medium = ImageFont.truetype(FONT_PATH, 36)
            font_small = ImageFont.truetype(FONT_PATH, 32)
        except:
            # Fallback fonts
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        print("\n🖌️ Placing text on template...")
        
        # ======================
        # FRONT SIDE TEXT
        # ======================
        
        # 1️⃣ Full Name (x: 210, y: 1120)
        name = data.get("name", "")
        if name:
            # Take only first part if too long
            if len(name) > 40:
                name = name[:40] + "..."
            draw.text((210, 1120), name, fill="black", font=font_large)
            print(f"   Name at (210, 1120): {name[:20]}...")
        
        # 2️⃣ Date of Birth (x: 210, y: 1235)
        dob = data.get("dob", "")
        if dob:
            draw.text((210, 1235), dob, fill="black", font=font_medium)
            print(f"   DOB at (210, 1235): {dob}")
        
        # 3️⃣ Sex (x: 210, y: 1325)
        sex = data.get("sex", "")
        if sex:
            draw.text((210, 1325), sex, fill="black", font=font_medium)
            print(f"   Sex at (210, 1325): {sex}")
        
        # 4️⃣ Date of Expiry (x: 210, y: 1410)
        expiry = data.get("expiry", "")
        if expiry:
            draw.text((210, 1410), expiry, fill="black", font=font_medium)
            print(f"   Expiry at (210, 1410): {expiry}")
        
        # 5️⃣ FAN (x: 210, y: 1515)
        fan = data.get("fan", "")
        if fan:
            # Format with spaces every 4 digits
            formatted = ' '.join([fan[i:i+4] for i in range(0, len(fan), 4)])
            draw.text((210, 1515), formatted, fill="black", font=font_large)
            print(f"   FAN at (210, 1515): {formatted[:20]}...")
        
        # 6️⃣ SN (x: 390, y: 1555)
        sin = data.get("sin", "")
        if sin:
            draw.text((390, 1555), sin, fill="black", font=font_small)
            print(f"   SN at (390, 1555): {sin}")
        
        # 7️⃣ Date of Issue - vertical (x: 1120, y: 360)
        issue_date = data.get("issue_date", "")
        if issue_date:
            # Create vertical text
            vertical_img = Image.new("RGBA", (780, 80), (255, 255, 255, 0))
            vertical_draw = ImageDraw.Draw(vertical_img)
            vertical_draw.text((0, 0), issue_date, fill="black", font=font_small)
            rotated = vertical_img.rotate(90, expand=True)
            template.paste(rotated, (1120, 360), rotated)
            print(f"   Issue date (vertical) at (1120, 360)")
        
        # ======================
        # BACK SIDE TEXT
        # ======================
        
        # 8️⃣ Phone Number (x: 120, y: 1220)
        phone = data.get("phone", "")
        if phone:
            draw.text((120, 1220), phone, fill="black", font=font_medium)
            print(f"   Phone at (120, 1220): {phone}")
        
        # 9️⃣ Nationality (x: 120, y: 1320)
        nationality = data.get("nationality", "")
        if nationality:
            draw.text((120, 1320), nationality, fill="black", font=font_medium)
            print(f"   Nationality at (120, 1320): {nationality}")
        
        # 🔟 Address (x: 120, y: 1425) - single line for now
        address = data.get("address", "")
        if address:
            # Truncate if too long
            if len(address) > 50:
                address = address[:50] + "..."
            draw.text((120, 1425), address, fill="black", font=font_small)
            print(f"   Address at (120, 1425): {address[:30]}...")
        
        # 1️⃣1️⃣ FIN (x: 760, y: 1220)
        fin = data.get("fin", "")
        if fin:
            draw.text((760, 1220), fin, fill="black", font=font_large)
            print(f"   FIN at (760, 1220): {fin}")
        
        # ======================
        # CROP AND ADD PHOTOS
        # ======================
        
        print("\n📸 Cropping and placing images...")
        
        try:
            # Open the 3rd screenshot (photo + QR)
            photo_qr_img = Image.open(photo_qr_path).convert("RGBA")
            print(f"   Source image size: {photo_qr_img.size}")
            
            # 1. CROP PHOTO (from your coordinates)
            # Photo bounding box: (160, 70, 560, 520)
            photo_box = (160, 70, 560, 520)
            print(f"   Photo crop box: {photo_box}")
            
            try:
                photo_crop = photo_qr_img.crop(photo_box)
                # Resize to template size (300x380)
                photo_crop = photo_crop.resize((300, 380))
                # Place on template at (120, 140)
                template.paste(photo_crop, (120, 140), photo_crop)
                print("   ✅ Photo cropped and placed")
            except Exception as photo_err:
                print(f"   ❌ Photo cropping failed: {photo_err}")
                # Fallback: use whole image resized
                fallback = photo_qr_img.resize((300, 380))
                template.paste(fallback, (120, 140), fallback)
                print("   ⚠️ Used fallback photo")
            
            # 2. CROP QR CODE (from your coordinates)
            # QR bounding box: (80, 650, 640, 1250)
            qr_box = (80, 650, 640, 1250)
            print(f"   QR crop box: {qr_box}")
            
            try:
                qr_crop = photo_qr_img.crop(qr_box)
                # Resize to template size (520x520)
                qr_crop = qr_crop.resize((520, 520))
                # Place on template at (1470, 40)
                template.paste(qr_crop, (1470, 40), qr_crop)
                print("   ✅ QR code cropped and placed")
            except Exception as qr_err:
                print(f"   ❌ QR cropping failed: {qr_err}")
                # Try to find QR in image
                qr_width = 640 - 80  # 560
                qr_height = 1250 - 650  # 600
                qr_ratio = qr_width / qr_height
                
                # Use a portion of the image
                qr_portion = photo_qr_img.crop((0, photo_qr_img.height//2, 
                                                photo_qr_img.width, photo_qr_img.height))
                qr_portion = qr_portion.resize((520, 520))
                template.paste(qr_portion, (1470, 40), qr_portion)
                print("   ⚠️ Used fallback QR")
                
        except Exception as img_error:
            print(f"⚠️ Image processing error: {img_error}")
        
        # Save the final image
        template.save(output_path)
        print(f"\n✅ Generated ID saved to: {output_path}")
        print(f"   File size: {os.path.getsize(output_path)} bytes")
        
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
