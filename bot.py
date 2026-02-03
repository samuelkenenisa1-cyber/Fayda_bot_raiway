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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(BASE_DIR, "tmp")
TEMPLATE_PATH = os.path.join(BASE_DIR, "template.png")
FONT_PATH = os.path.join(BASE_DIR, "font.ttf")

os.makedirs(TMP_DIR, exist_ok=True)

# User session storage
user_sessions = {}

# ================= OCR =================

def ocr_image(path: str) -> str:
    """Extract text from image using enhanced preprocessing."""
    try:
        print(f"🔍 Starting OCR on: {path}")
        
        # Open and preprocess image
        img = Image.open(path)
        
        # Convert to grayscale
        img = img.convert('L')
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        
        # Sharpen
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)
        
        # Increase brightness if needed
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.2)
        
        # Save preprocessed image for debugging
        debug_path = path.replace(".png", "_preprocessed.png")
        img.save(debug_path)
        print(f"✅ Saved preprocessed image: {debug_path}")
        
        # Try multiple OCR configurations
        configs = [
            '--psm 6 --oem 3',  # Assume uniform block of text
            '--psm 11',         # Sparse text
            '--psm 12',         # Sparse text with orientation
        ]
        
        best_text = ""
        
        for config in configs:
            try:
                text = pytesseract.image_to_string(
                    img,
                    lang='amh+eng',
                    config=config
                )
                print(f"📝 Config {config}: Found {len(text)} chars")
                
                # Check if this config found Ethiopian text
                ethiopian_chars = sum(1 for char in text if '\u1200' <= char <= '\u137F')
                if ethiopian_chars > 2 and len(text) > len(best_text):
                    best_text = text
                    print(f"✅ Better text found with config: {config}")
            except Exception as config_error:
                print(f"⚠️ Config {config} failed: {config_error}")
                continue
        
        # If no Ethiopian text found, try English only
        if not best_text or sum(1 for char in best_text if '\u1200' <= char <= '\u137F') < 3:
            print("🔄 Trying English-only OCR...")
            try:
                text = pytesseract.image_to_string(
                    img,
                    lang='eng',
                    config='--psm 6 --oem 3'
                )
                if len(text) > len(best_text):
                    best_text = text
            except:
                pass
        
        print(f"📊 Final OCR result: {len(best_text)} characters")
        print("=" * 50)
        print(best_text[:500])  # Print first 500 chars
        print("=" * 50)
        
        return best_text
        
    except Exception as e:
        print(f"❌ OCR Error: {e}")
        import traceback
        traceback.print_exc()
        return ""
# ================= PARSING =================

def extract(patterns, text):
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""

def parse_fayda(text: str) -> dict:
    """Parse Ethiopian Fayda ID information from OCR text."""
    print("🔍 Parsing OCR text for Ethiopian ID fields...")
    
    # Initialize with empty values
    data = {
        "name": "",
        "dob": "",
        "sex": "",
        "expiry": "",
        "fan": "",  # FAN/FCN
        "fin": "",
        "sin": "",
        "nationality": "",
        "address": "",
        "phone": "",
        "issue_date": "",
    }
    
    # Split into lines and clean
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    print("📄 OCR Lines found:")
    for i, line in enumerate(lines):
        print(f"  {i:2d}: {line}")
    
    # Common Ethiopian ID field patterns (Amharic and English)
    field_patterns = {
        "name": [
            r"ስም[:\s]*([ሀ-ፐ\s]+[ሀ-ፐ])",
            r"Name[:\s]*([A-Za-z\s]+[A-Za-z])",
            r"መሉ ስሞ[:\s]*([ሀ-ፐ\s]+[ሀ-ፐ])",
            r"Full Name[:\s]*([A-Za-z\s]+[A-Za-z])",
        ],
        "dob": [
            r"የትውልድ ቀን[:\s]*([\d/.-]+)",
            r"Date of Birth[:\s]*([\d/.-]+)",
            r"DOB[:\s]*([\d/.-]+)",
        ],
        "sex": [
            r"ፆታ[:\s]*([ሀ-ፐ]+)",
            r"Sex[:\s]*([A-Za-z]+)",
            r"Gender[:\s]*([A-Za-z]+)",
        ],
        "expiry": [
            r"የሚያበቃበት ቀን[:\s]*([\d/.-]+)",
            r"Date of Expiry[:\s]*([\d/.-]+)",
            r"Expiry[:\s]*([\d/.-]+)",
        ],
        "fan": [
            r"FCN[:\s]*([\d\s]+)",
            r"FAN[:\s]*([\d\s]+)",
            r"ቁጥር[:\s]*([\d\s]+)",
        ],
        "fin": [
            r"FIN[:\s]*([\d]+)",
        ],
        "sin": [
            r"SN[:\s]*([\d]+)",
            r"Serial[:\s]*([\d]+)",
        ],
        "nationality": [
            r"ዜግነት[:\s]*([ሀ-ፐ]+)",
            r"Nationality[:\s]*([A-Za-z]+)",
        ],
        "phone": [
            r"ስልክ[:\s]*([\d\s\+]+)",
            r"Phone[:\s]*([\d\s\+]+)",
            r"Tel[:\s]*([\d\s\+]+)",
        ],
        "issue_date": [
            r"የተሰጠበት ቀን[:\s]*([\d/.-]+)",
            r"Date of Issue[:\s]*([\d/.-]+)",
            r"Issue[:\s]*([\d/.-]+)",
        ],
    }
    
    # Address is a multi-line field, we'll handle it differently
    address_lines = []
    
    # Extract data using patterns
    for field, patterns in field_patterns.items():
        if field == "address":
            continue  # Handle separately
            
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data[field] = match.group(1).strip()
                print(f"✅ Found {field}: {data[field]}")
                break
    
    # Extract address (look for address-related keywords and capture following lines)
    address_keywords = ["አድራሻ", "Address", "Location", "ክልል", "Region"]
    
    for i, line in enumerate(lines):
        for keyword in address_keywords:
            if keyword.lower() in line.lower():
                # Capture this line and next few lines as address
                address_start = i
                address_end = min(i + 4, len(lines))  # Next 4 lines max
                address_lines = lines[address_start:address_end]
                
                # Clean the address lines
                cleaned_address = []
                for addr_line in address_lines:
                    # Remove the keyword itself
                    clean_line = re.sub(f"{keyword}[:\s]*", "", addr_line, flags=re.IGNORECASE)
                    if clean_line.strip():
                        cleaned_address.append(clean_line.strip())
                
                if cleaned_address:
                    data["address"] = " ".join(cleaned_address)
                    print(f"✅ Found address: {data['address']}")
                break
    
    # If no address found with keywords, try to capture multi-word lines
    if not data["address"]:
        # Look for longer lines that might be addresses
        for line in lines:
            words = line.split()
            if 3 <= len(words) <= 10:  # Address-like lines
                # Check if it doesn't contain other field keywords
                other_fields = ["ስም", "Name", "DOB", "ቀን", "Date", "FCN", "FAN", "Phone", "ስልክ"]
                if not any(field in line for field in other_fields):
                    data["address"] = line
                    print(f"📌 Possible address found: {line}")
                    break
    
    print("=" * 50)
    print("📋 PARSED DATA SUMMARY:")
    for key, value in data.items():
        print(f"  {key:12}: {value or '(Not found)'}")
    print("=" * 50)
    
    return data
# ================= IMAGE GENERATION =================

def generate_id(data: dict, front_path: str, back_path: str, output_path: str):
    """Generate ID card with extracted data using exact coordinates."""
    try:
        # Open template (assuming it's 2048x1270 or similar size)
        template = Image.open(TEMPLATE_PATH).convert("RGBA")
        draw = ImageDraw.Draw(template)
        
        # Load font
        try:
            # Use different font sizes based on field
            font_large = ImageFont.truetype(FONT_PATH, 42)
            font_medium = ImageFont.truetype(FONT_PATH, 36)
            font_small = ImageFont.truetype(FONT_PATH, 32)
            font_vertical = ImageFont.truetype(FONT_PATH, 30)
        except:
            # Fallback to default fonts if custom font fails
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_vertical = ImageFont.load_default()
        
        # ======================
        # FRONT SIDE (1270 × 2048)
        # ======================
        
        # 1️⃣ Full Name (x: 210, y: 1120, w: 820, h: 95)
        name = data.get("name", "")
        if name:
            # Split bilingual text
            if "|" in name:
                am_name, en_name = name.split("|", 1)
                draw.text((210, 1120), am_name.strip(), fill="black", font=font_large)
                draw.text((210, 1160), en_name.strip(), fill="black", font=font_medium)
            else:
                draw.text((210, 1120), name, fill="black", font=font_large)
        
        # 2️⃣ Date of Birth (x: 210, y: 1235, w: 820, h: 75)
        dob = data.get("dob", "")
        if dob:
            draw.text((210, 1235), dob, fill="black", font=font_medium)
        
        # 3️⃣ Sex (x: 210, y: 1325, w: 400, h: 65)
        sex = data.get("sex", "")
        if sex:
            # Format as Amharic|English
            if "|" in sex:
                am_sex, en_sex = sex.split("|", 1)
                draw.text((210, 1325), am_sex.strip(), fill="black", font=font_medium)
                draw.text((210, 1365), en_sex.strip(), fill="black", font=font_small)
            else:
                draw.text((210, 1325), sex, fill="black", font=font_medium)
        
        # 4️⃣ Date of Expiry (x: 210, y: 1410, w: 820, h: 75)
        expiry = data.get("expiry", "")
        if expiry:
            draw.text((210, 1410), expiry, fill="black", font=font_medium)
        
        # 5️⃣ FAN (x: 210, y: 1515, w: 300, h: 70)
        fan = data.get("fan", "")
        if fan:
            # Format FAN with spaces every 4 digits
            formatted_fan = ' '.join([fan[i:i+4] for i in range(0, len(fan), 4)])
            draw.text((210, 1515), formatted_fan, fill="black", font=font_large)
        
        # 6️⃣ SN - Serial Number (x: 390, y: 1555, w: 640, h: 95)
        sin = data.get("sin", "")
        if sin:
            draw.text((390, 1555), sin, fill="black", font=font_small)
        
        # 7️⃣ Date of Issue - vertical text (x: 1120, y: 360, w: 80, h: 780)
        issue_date = data.get("issue_date", "")
        if issue_date:
            # Create vertical text
            vertical_img = Image.new("RGBA", (780, 80), (255, 255, 255, 0))
            vertical_draw = ImageDraw.Draw(vertical_img)
            vertical_draw.text((0, 0), issue_date, fill="black", font=font_vertical)
            rotated = vertical_img.rotate(90, expand=True)
            template.paste(rotated, (1120, 360), rotated)
        
        # ======================
        # BACK SIDE (1285 × 2048)
        # ======================
        
        # 8️⃣ Phone Number (x: 120, y: 1220, w: 600, h: 85)
        phone = data.get("phone", "")
        if phone:
            draw.text((120, 1220), phone, fill="black", font=font_medium)
        
        # 9️⃣ Nationality (x: 120, y: 1320, w: 600, h: 85)
        nationality = data.get("nationality", "")
        if nationality:
            draw.text((120, 1320), nationality, fill="black", font=font_medium)
        
        # 🔟 Address - Multi-line (x: 120, y: 1425, w: 750, h: 420)
        address = data.get("address", "")
        if address:
            # Simple multi-line text (you might need textwrap for better formatting)
            lines = []
            current_line = ""
            words = address.split()
            
            for word in words:
                test_line = f"{current_line} {word}".strip()
                # Check if line would be too wide (approximate)
                if len(test_line) < 30:  # Adjust based on font size
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            
            if current_line:
                lines.append(current_line)
            
            # Draw each line
            for i, line in enumerate(lines[:5]):  # Max 5 lines
                y_pos = 1425 + (i * 80)  # 80px line height
                draw.text((120, y_pos), line, fill="black", font=font_small)
        
        # 1️⃣1️⃣ FIN (x: 760, y: 1220, w: 480, h: 90)
        fin = data.get("fin", "")
        if fin:
            draw.text((760, 1220), fin, fill="black", font=font_large)
        
        # ======================
        # PHOTOS & QR CODE
        # ======================
        
        try:
            # Main ID Photo (x: 120, y: 140, w: 300, h: 380)
            if os.path.exists(front_path):
                photo = Image.open(front_path).convert("RGBA")
                # Crop to get just the photo area (you might need to adjust)
                # For now, resize and place
                photo = photo.resize((300, 380))
                template.paste(photo, (120, 140), photo)
            
            # QR Code (x: 1470, y: 40, w: 520, h: 520)
            if os.path.exists(back_path):
                qr_img = Image.open(back_path).convert("RGBA")
                qr_img = qr_img.resize((520, 520))
                template.paste(qr_img, (1470, 40), qr_img)
                
        except Exception as img_error:
            print(f"⚠️ Could not add images: {img_error}")
        
        # Save the final image
        template.save(output_path)
        print(f"✅ Generated ID saved to: {output_path}")
        return True
        
    except Exception as e:
        print(f"❌ Image generation error: {e}")
        import traceback
        traceback.print_exc()
        return False

# ================= BOT HANDLERS =================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads."""
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        user_sessions[user_id] = []
    
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
    
    print(f"📸 Image {img_index} saved: {img_path}")
    print(f"   File size: {os.path.getsize(img_path)} bytes")
    
    # Show a preview of the image
    try:
        img = Image.open(img_path)
        print(f"   Image size: {img.size}")
    except:
        pass
    
    # Acknowledge receipt
    if img_index < 3:
        await update.message.reply_text(f"✅ Image {img_index}/3 received")
        return
    
    # All images received, start processing
    await update.message.reply_text("⏳ Processing images...")
    
    try:
        print("=" * 60)
        print("🔄 STARTING OCR PROCESSING")
        print("=" * 60)
        
        # Perform OCR on first two images (front and back)
        await update.message.reply_text("🔍 Extracting text from images...")
        
        front_text = ocr_image(user_sessions[user_id][0])
        back_text = ocr_image(user_sessions[user_id][1])
        
        if not front_text.strip() and not back_text.strip():
            await update.message.reply_text(
                "❌ Could not extract any text from images.\n"
                "Please ensure:\n"
                "• Images are clear and well-lit\n"
                "• Text is not blurry\n"
                "• Screenshots show the ID clearly"
            )
            return
        
        # Send OCR preview to user
        combined_preview = f"📄 *OCR Preview:*\n```\n"
        if front_text:
            combined_preview += f"Front page:\n{front_text[:200]}...\n\n"
        if back_text:
            combined_preview += f"Back page:\n{back_text[:200]}..."
        combined_preview += "\n```"
        
        await update.message.reply_text(combined_preview, parse_mode='Markdown')
        
        # Parse the data
        combined_text = f"{front_text}\n{back_text}"
        data = parse_fayda(combined_text)
        
        # Check if we got essential data
        found_fields = [key for key, value in data.items() if value]
        print(f"📊 Found {len(found_fields)} fields: {found_fields}")
        
        if len(found_fields) < 3:  # At least name, dob, and one ID number
            await update.message.reply_text(
                "⚠️ Could not find enough ID information.\n"
                "Make sure the screenshots clearly show:\n"
                "• Full name\n• Date of birth\n• FCN/FAN number\n\n"
                f"Found: {', '.join(found_fields) if found_fields else 'Nothing'}"
            )
            return
        
        # Generate the ID card
        await update.message.reply_text("🎨 Generating ID card...")
        output_path = os.path.join(user_dir, "final_id.png")
        
        success = generate_id(
            data, 
            user_sessions[user_id][0],  # Front image (contains photo)
            user_sessions[user_id][2],  # Third image (contains QR)
            output_path
        )
        
        if success and os.path.exists(output_path):
            await update.message.reply_photo(
                photo=open(output_path, "rb"),
                caption=f"✅ Fayda ID Generated!\nFound: {', '.join(found_fields[:5])}"
            )
        else:
            await update.message.reply_text("❌ Failed to generate ID image.")
    
    except Exception as e:
        error_msg = f"❌ Processing error: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        await update.message.reply_text(error_msg)
    
    finally:
        # Cleanup
        if user_id in user_sessions:
            del user_sessions[user_id]

def draw_multiline_text(draw, text, position, font, max_width):
    """Draw text with automatic line wrapping."""
    x, y = position
    lines = []
    words = text.split()
    
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        # Get text width
        bbox = draw.textbbox((0, 0), test_line, font=font)
        text_width = bbox[2] - bbox[0]
        
        if text_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    # Draw lines
    line_height = font.size + 10
    for i, line in enumerate(lines):
        draw.text((x, y + (i * line_height)), line, fill="black", font=font)
    
    return len(lines)
# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🤖 Fayda Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
