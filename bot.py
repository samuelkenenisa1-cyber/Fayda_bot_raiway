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
    img = Image.open(path).convert("L")

    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)

    text = pytesseract.image_to_string(
        img,
        lang="amh+eng",
        config="--psm 6"
    )
    return text


# ================= PARSING =================

def extract(patterns, text):
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""

def parse_fayda(text: str) -> dict:
    return {
        "name": extract([
            r"Name[:\s]*([A-Za-z\s]+)",
            r"ስም[:\s]*([ሀ-ፐ\s]+)"
        ], text),

        "fan": extract([
            r"FAN[:\s]*([A-Z0-9]+)"
        ], text),

        "fin": extract([
            r"FIN[:\s]*([0-9]+)"
        ], text),

        "sin": extract([
            r"SIN[:\s]*([0-9]+)"
        ], text),

        "nationality": extract([
            r"Nationality[:\s]*([A-Za-z]+)",
            r"ዜግነት[:\s]*([ሀ-ፐ]+)"
        ], text),

        "dob": extract([
            r"Date of Birth[:\s]*([\d/.-]+)",
            r"የትውልድ ቀን[:\s]*([\d/.-]+)"
        ], text),

        "address": extract([
            r"Address[:\s]*(.+)",
            r"አድራሻ[:\s]*(.+)"
        ], text),

        "phone": extract([
            r"Phone[:\s]*(\+?\d+)"
        ], text),

        "issue_date": extract([
            r"Date of Issue[:\s]*([\d/.-]+)",
            r"የተሰጠበት ቀን[:\s]*([\d/.-]+)"
        ], text),
    }


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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions[update.effective_user.id] = []
    await update.message.reply_text(
        "📄 Send Fayda ID screenshots in this order:\n"
        "1️⃣ Front page\n"
        "2️⃣ Back page\n"
        "3️⃣ Photo + QR"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_sessions:
        user_sessions[user_id] = []

    photo = update.message.photo[-1]
    file = await photo.get_file()

    user_dir = os.path.join(TMP_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    img_index = len(user_sessions[user_id]) + 1
    img_path = os.path.join(user_dir, f"{img_index}.png")

    await file.download_to_drive(img_path)
    user_sessions[user_id].append(img_path)

    if img_index < 3:
        await update.message.reply_text(f"✅ Image {img_index}/3 received")
        return

    await update.message.reply_text("⏳ Processing Fayda ID...")

    try:
        front_text = ocr_image(user_sessions[user_id][0])
        back_text = ocr_image(user_sessions[user_id][1])

        data = parse_fayda(front_text + "\n" + back_text)

        output_path = os.path.join(user_dir, "final_id.png")
        success = generate_id(
    data, 
    user_sessions[user_id][0],  # Front image (contains photo)
    user_sessions[user_id][2],  # Third image (contains QR)
    output_path
)
        await update.message.reply_photo(
            photo=open(output_path, "rb"),
            caption="✅ Fayda ID generated"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

    finally:
        user_sessions.pop(user_id, None)

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
