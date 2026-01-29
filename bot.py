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
        "name": extract_field(lines, ["ሙሉ ስም", "Full Name"]),
        "dob": extract_field(lines, ["የትውልድ ቀን", "Date of Birth"]),
        "sex": extract_field(lines, ["ፆታ", "Sex"]),
        "expiry": extract_field(lines, ["የሚያበቃበት ቀን", "Date of Expiry"]),
        "issue": extract_field(lines, ["የተሰጠበት ቀን", "Date of Issue"]),
        "fan": extract_field(lines, ["FAN"]),
        "fin": extract_field(lines, ["FIN"]),
        "phone": extract_field(lines, ["ስልክ", "Phone"]),
        "nationality": extract_field(lines, ["ዜግነት", "Nationality"]),
        "address": extract_field(lines, ["አድራሻ", "Address"]),
    }
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
    doc = update.message.document
    if not doc.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("❌ Please send a Fayda ID PDF file.")
        return

    file = await doc.get_file()
    await file.download_to_drive("id.pdf")

    # ---- Extract text from PDF
    text = ""
    with pdfplumber.open("id.pdf") as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""

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

def main():
    import sys
    import traceback
    try:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

    print("🤖 Bot started...")
    app.run_polling()
