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

def generate_id(data: dict, photo_qr_path: str, output_path: str):
    template = Image.open(TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(template)

    font = ImageFont.truetype(FONT_PATH, 28)

    # ---- TEXT POSITIONS (ADJUST TO YOUR TEMPLATE) ----
    positions = {
        "name": (280, 180),
        "fan": (280, 230),
        "fin": (280, 280),
        "sin": (280, 330),
        "nationality": (280, 380),
        "dob": (280, 430),
        "address": (280, 480),
        "phone": (280, 530),
        "issue_date": (40, 620),  # left edge
    }

    for key, pos in positions.items():
        draw.text(pos, data.get(key, ""), fill="black", font=font)

    # ---- PHOTO + QR ----
    pq = Image.open(photo_qr_path).convert("RGBA")
    pq = pq.resize((220, 280))

    template.paste(pq, (40, 180))

    template.save(output_path)


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
        generate_id(data, user_sessions[user_id][2], output_path)

        await update.message.reply_photo(
            photo=open(output_path, "rb"),
            caption="✅ Fayda ID generated"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

    finally:
        user_sessions.pop(user_id, None)


# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🤖 Fayda Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
