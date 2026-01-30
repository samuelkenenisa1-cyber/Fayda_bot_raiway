import os
import re
import pdfplumber
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
from PIL import Image, ImageDraw, ImageFont

# ======================
# CONFIG
# ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")

TEMPLATE_PATH = "template.png"
FONT_PATH = "font.ttf"

# ======================
# UTILITIES
# ======================

def normalize(text: str) -> str:
    return text.replace("፡", ":").replace("፣", ",").strip()

def split_bilingual(value: str):
    if "|" in value:
        am, en = value.split("|", 1)
        return am.strip(), en.strip()
    return value.strip(), value.strip()

def extract_field(lines, keys):
    for i, line in enumerate(lines):
        for key in keys:
            if key in line:
                if ":" in line:
                    return line.split(":", 1)[1].strip()
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
    return ""

def parse_fayda(text: str):
    lines = [normalize(l) for l in text.splitlines() if l.strip()]
    
    data = {
        "name": "",
        "dob": "",
        "sex": "",
        "expiry": "",
        "issue": "",
        "fan": "",  # This should be FCN in your PDF
        "fin": "",
        "phone": "",
        "nationality": "",
        "address": "",
    }
    
    # Debug: Print all lines to see what we're working with
    print("=== DEBUG: PDF LINES ===")
    for i, line in enumerate(lines):
        print(f"Line {i}: {line}")
    
    # Extract name (appears after "መት ስሞ" line)
    for i, line in enumerate(lines):
        if "መት ስሞ" in line or "First, Middle, Surname" in line:
            if i + 1 < len(lines):
                data["name"] = lines[i + 1].strip()
                break
    
    # Extract FCN (Fayda Card Number)
    for line in lines:
        if "FCN:" in line:
            data["fan"] = line.replace("FCN:", "").strip()
            break
    
    # Extract Date of Birth
    for line in lines:
        if "የትውልድ ቀን" in line or "Date of Birth" in line:
            # Get everything after the label
            if "/" in line:
                parts = line.split("/", 1)
                if len(parts) > 1:
                    data["dob"] = parts[1].strip()
            else:
                # Try to extract date pattern
                import re
                dates = re.findall(r'\d{2}/\d{2}/\d{4}', line)
                if dates:
                    data["dob"] = dates[0]
            break
    
    # Extract Sex
    for i, line in enumerate(lines):
        if "SEX" in line or "+ /" in line:
            # Look for Male/Female in this line or next
            if "Male" in line or "Female" in line:
                data["sex"] = "Male" if "Male" in line else "Female"
            elif i + 1 < len(lines):
                next_line = lines[i + 1]
                if "Male" in next_line or "Female" in next_line:
                    data["sex"] = "Male" if "Male" in next_line else "Female"
            break
    
    # Extract Phone
    for line in lines:
        if "ስልክ" in line or "Phone Number" in line:
            # Try to find phone number (10 digits)
            import re
            phone_match = re.search(r'\d{10}', line)
            if phone_match:
                data["phone"] = phone_match.group(0)
            break
    
    # Extract Nationality
    for line in lines:
        if "ኢትዮጵያዊ" in line or "Ethiopian" in line:
            data["nationality"] = "ኢትዮጵያዊ | Ethiopian"
            break
    
    print("=== DEBUG: PARSED DATA ===")
    for key, value in data.items():
        print(f"{key}: {value}")
    
    return data

def draw_vertical_text(base_img, text, position):
    temp = Image.new("RGBA", (400, 60), (255, 255, 255, 0))
    d = ImageDraw.Draw(temp)
    font = ImageFont.truetype(FONT_PATH, 22)
    d.text((0, 0), text, fill="#2b2b2b", font=font)
    rotated = temp.rotate(90, expand=1)
    base_img.paste(rotated, position, rotated)

def bilingual_draw(draw, x, y, value, font_main, font_small):
    am, en = split_bilingual(value)
    draw.text((x, y), am, fill="#2b2b2b", font=font_main)
    draw.text((x, y + 26), en, fill="#2b2b2b", font=font_small)

# ======================
# MAIN HANDLER
# ======================

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
     print("🟢 handle_pdf function CALLED")
    doc = update.message.document
    print(f"📄 File name: {doc.file_name}")
    if not doc.file_name.lower().endswith(".pdf"):
        print("❌ File is not a PDF")
        await update.message.reply_text("❌ Please send a Fayda ID PDF file.")
        return
    print("✅ File is a PDF. Starting download...")

    file = await doc.get_file()
    await file.download_to_drive("id.pdf")

    # ---- Extract text from PDF
    text = ""
    with pdfplumber.open("id.pdf") as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
             print("=== RAW PDF TEXT ===")
    print(text[:500])  # Print first 500 chars
    print("=== END TEXT ===")
    data = parse_fayda(text)

    # ---- Load template
    img = Image.open(TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_main = ImageFont.truetype(FONT_PATH, 26)
    font_small = ImageFont.truetype(FONT_PATH, 22)

    # ======================
    # FRONT SIDE
    # ======================
    bilingual_draw(draw, 420, 215, data["name"], font_main, font_small)
    bilingual_draw(draw, 420, 265, data["dob"], font_main, font_small)
    bilingual_draw(draw, 420, 315, data["sex"], font_main, font_small)
    bilingual_draw(draw, 420, 365, data["expiry"], font_main, font_small)

    draw.text((220, 540), data["fan"], fill="#2b2b2b", font=font_small)

    draw_vertical_text(
        img,
        f"የተሰጠበት ቀን | {data['issue']}",
        position=(35, 300)
    )

    # ======================
    # BACK SIDE
    # ======================
    bilingual_draw(draw, 1150, 160, data["phone"], font_main, font_small)
    bilingual_draw(draw, 1150, 225, data["nationality"], font_main, font_small)
    bilingual_draw(draw, 1150, 300, data["address"], font_main, font_small)

    draw.text((1150, 525), data["fin"], fill="#000000", font=font_main)

    # ---- Save output
    output_path = "final_id.png"
    img.save(output_path)

    await update.message.reply_photo(photo=open(output_path, "rb"))

    # ---- Cleanup
    for f in ["id.pdf", output_path]:
        if os.path.exists(f):
            os.remove(f)

# ======================
# BOOTSTRAP
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send your Fayda National ID PDF and I will generate a printable ID image."
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temporary handler to debug document reception."""
    doc = update.message.document
    print(f"📁 DEBUG: Received a document!")
    print(f"    File Name: {doc.file_name}")
    print(f"    MIME Type: {doc.mime_type}")
    print(f"    File Size: {doc.file_size} bytes")
    
    # Check if it's a PDF
    if doc.file_name and doc.file_name.lower().endswith('.pdf'):
        print("    ✅ This is a PDF. Calling the original handler...")
        # Call your original processing function
        await handle_pdf(update, context)
    else:
        await update.message.reply_text("❌ Please send a PDF file.")

def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
