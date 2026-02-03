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

# ================= BOT HANDLERS (DEFINE FIRST) =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user_sessions[update.effective_user.id] = []
    await update.message.reply_text(
        "📄 *Fayda ID Bot*\n\n"
        "Send me 3 screenshots in order:\n"
        "1️⃣ Front page of ID\n"
        "2️⃣ Back page of ID\n"
        "3️⃣ Photo + QR code\n\n"
        "I'll extract the information and generate a formatted ID card.",
        parse_mode='Markdown'
    )

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
                "Please ensure images are clear and well-lit."
            )
            return
        
        # Parse the data
        combined_text = f"{front_text}\n{back_text}"
        data = parse_fayda(combined_text)
        
        # Check if we got essential data
        found_fields = [key for key, value in data.items() if value]
        
        if len(found_fields) < 3:
            await update.message.reply_text(
                f"⚠️ Could not find enough ID information.\n"
                f"Found: {', '.join(found_fields) if found_fields else 'Nothing'}"
            )
            return
        
        # Generate the ID card
        await update.message.reply_text("🎨 Generating ID card...")
        output_path = os.path.join(user_dir, "final_id.png")
        
        success = generate_id(
            data, 
            user_sessions[user_id][0],  # Front image
            user_sessions[user_id][2],  # Third image (QR)
            output_path
        )
        
        if success and os.path.exists(output_path):
            await update.message.reply_photo(
                photo=open(output_path, "rb"),
                caption=f"✅ Fayda ID Generated!\nFound: {', '.join(found_fields[:3])}"
            )
        else:
            await update.message.reply_text("❌ Failed to generate ID image.")
    
    except Exception as e:
        error_msg = f"❌ Processing error: {str(e)}"
        print(error_msg)
        await update.message.reply_text(error_msg)
    
    finally:
        # Cleanup
        if user_id in user_sessions:
            del user_sessions[user_id]

# ================= OCR =================

def ocr_image(path: str) -> str:
    """Extract text from image using enhanced preprocessing."""
    try:
        print(f"🔍 Starting OCR on: {path}")
        
        # Open and preprocess image
        img = Image.open(path)
        img = img.convert('L')
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        
        # Sharpen
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)
        
        # Try OCR with Amharic + English
        text = pytesseract.image_to_string(
            img,
            lang='amh+eng',
            config='--psm 6 --oem 3'
        )
        
        print(f"📝 OCR found {len(text)} characters")
        if text:
            print("First 200 chars:", text[:200])
        
        return text.strip()
        
    except Exception as e:
        print(f"❌ OCR Error: {e}")
        return ""

# ================= PARSING =================

def parse_fayda(text: str) -> dict:
    """Parse Ethiopian Fayda ID information from OCR text."""
    print("🔍 Parsing OCR text...")
    
    data = {
        "name": "",
        "dob": "",
        "sex": "",
        "expiry": "",
        "fan": "",
        "fin": "",
        "sin": "",
        "nationality": "",
        "address": "",
        "phone": "",
        "issue_date": "",
    }
    
    # Split into lines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    print("📄 OCR Lines:")
    for i, line in enumerate(lines[:10]):  # Show first 10 lines
        print(f"  {i}: {line}")
    
    # Simple extraction - look for keywords in lines
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # Name patterns
        if not data["name"]:
            if "ስም" in line or "name" in line_lower:
                if i + 1 < len(lines):
                    data["name"] = lines[i + 1].strip()
        
        # Date of Birth
        if not data["dob"]:
            if "የትውልድ" in line or "birth" in line_lower or "dob" in line_lower:
                # Extract date pattern
                date_match = re.search(r'\d{2}/\d{2}/\d{4}', line)
                if date_match:
                    data["dob"] = date_match.group(0)
        
        # FAN/FCN number
        if not data["fan"]:
            if "fcn" in line_lower or "fan" in line_lower:
                # Extract numbers
                num_match = re.search(r'(\d{4}\s*\d{4}\s*\d{4}\s*\d{4})', line)
                if num_match:
                    data["fan"] = num_match.group(1)
        
        # Phone number
        if not data["phone"]:
            if "ስልክ" in line or "phone" in line_lower:
                phone_match = re.search(r'(\d{10})', line)
                if phone_match:
                    data["phone"] = phone_match.group(1)
    
    print("📋 Parsed data:")
    for key, value in data.items():
        if value:
            print(f"  {key}: {value}")
    
    return data

# ================= IMAGE GENERATION =================

def generate_id(data: dict, front_path: str, qr_path: str, output_path: str):
    """Generate ID card with extracted data."""
    try:
        # Open template
        template = Image.open(TEMPLATE_PATH).convert("RGBA")
        draw = ImageDraw.Draw(template)
        
        # Load font
        try:
            font = ImageFont.truetype(FONT_PATH, 40)
        except:
            font = ImageFont.load_default()
        
        # ======================
        # FRONT SIDE
        # ======================
        
        # 1️⃣ Full Name (x: 210, y: 1120)
        name = data.get("name", "")
        if name:
            draw.text((210, 1120), name, fill="black", font=font)
        
        # 2️⃣ Date of Birth (x: 210, y: 1235)
        dob = data.get("dob", "")
        if dob:
            draw.text((210, 1235), dob, fill="black", font=font)
        
        # 3️⃣ Sex (x: 210, y: 1325)
        sex = data.get("sex", "")
        if sex:
            draw.text((210, 1325), sex, fill="black", font=font)
        
        # 4️⃣ Date of Expiry (x: 210, y: 1410)
        expiry = data.get("expiry", "")
        if expiry:
            draw.text((210, 1410), expiry, fill="black", font=font)
        
        # 5️⃣ FAN (x: 210, y: 1515)
        fan = data.get("fan", "")
        if fan:
            draw.text((210, 1515), fan, fill="black", font=font)
        
        # 6️⃣ SN (x: 390, y: 1555)
        sin = data.get("sin", "")
        if sin:
            draw.text((390, 1555), sin, fill="black", font=font)
        
        # 7️⃣ Date of Issue - vertical (x: 1120, y: 360)
        issue_date = data.get("issue_date", "")
        if issue_date:
            # Create vertical text
            vertical_img = Image.new("RGBA", (780, 80), (255, 255, 255, 0))
            vertical_draw = ImageDraw.Draw(vertical_img)
            vertical_draw.text((0, 0), issue_date, fill="black", font=font)
            rotated = vertical_img.rotate(90, expand=True)
            template.paste(rotated, (1120, 360), rotated)
        
        # ======================
        # BACK SIDE
        # ======================
        
        # 8️⃣ Phone Number (x: 120, y: 1220)
        phone = data.get("phone", "")
        if phone:
            draw.text((120, 1220), phone, fill="black", font=font)
        
        # 9️⃣ Nationality (x: 120, y: 1320)
        nationality = data.get("nationality", "")
        if nationality:
            draw.text((120, 1320), nationality, fill="black", font=font)
        
        # 🔟 Address (x: 120, y: 1425)
        address = data.get("address", "")
        if address:
            # Simple single line address
            draw.text((120, 1425), address[:50], fill="black", font=font)
        
        # 1️⃣1️⃣ FIN (x: 760, y: 1220)
        fin = data.get("fin", "")
        if fin:
            draw.text((760, 1220), fin, fill="black", font=font)
        
        # ======================
        # PHOTOS & QR CODE
        # ======================
        
        try:
            # Main ID Photo (x: 120, y: 140, w: 300, h: 380)
            if os.path.exists(front_path):
                photo = Image.open(front_path).convert("RGBA")
                photo = photo.resize((300, 380))
                template.paste(photo, (120, 140), photo)
            
            # QR Code (x: 1470, y: 40, w: 520, h: 520)
            if os.path.exists(qr_path):
                qr_img = Image.open(qr_path).convert("RGBA")
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
        return False

# ================= MAIN =================

def main():
    """Start the bot application."""
    print("🚀 Starting Fayda ID Bot...")
    
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
        print(f"❌ Failed to start bot: {e}")

if __name__ == "__main__":
    main()
