import os
import logging
from PIL import Image, ImageDraw, ImageFont
import pytesseract

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ==============================
# CONFIG
# ==============================

BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"

# If Windows, set path like below:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

OUTPUT_FOLDER = "output"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO)

# ==============================
# FIELD COORDINATES (EDIT THESE)
# ==============================
# (x, y) = where text will be inserted

FIELD_COORDS = {
    "FULL_NAME": (250, 180),
    "DOB": (250, 240),
    "SEX": (250, 300),
    "EXPIRY": (250, 360),
    "FAN": (250, 420),
    "PHONE": (250, 480),
    "NATIONALITY": (250, 540),
    "ADDRESS": (250, 600),
}

# ==============================
# PHOTO + QR COORDINATES
# ==============================

PHOTO_BOX = (900, 150, 1150, 420)  # left, top, right, bottom
QR_BOX = (900, 450, 1150, 700)

# ==============================
# LOAD FONT
# ==============================

def load_font():
    try:
        return ImageFont.truetype("arial.ttf", 32)
    except:
        return ImageFont.load_default()


# ==============================
# PROCESS ID IMAGE
# ==============================

def process_id(input_path, output_path):
    img = Image.open(input_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = load_font()

    inserted_count = 0

    # -------- INSERT SAMPLE DATA --------
    # Replace with your DB or OCR values
    sample_data = {
        "FULL_NAME": "SAMUEL KENENISA",
        "DOB": "01-01-1998",
        "SEX": "M",
        "EXPIRY": "2035",
        "FAN": "123456789",
        "PHONE": "0912345678",
        "NATIONALITY": "ETHIOPIAN",
        "ADDRESS": "ADDIS ABABA",
    }

    for field, position in FIELD_COORDS.items():
        value = sample_data.get(field, "")

        if value:
            draw.text(position, value, fill=(0, 0, 0), font=font)
            inserted_count += 1
            print(f"Inserted {field} -> {value}")

    # -------- DEBUG DRAW BOXES --------
    # Remove later if not needed
    draw.rectangle(PHOTO_BOX, outline="red", width=3)
    draw.rectangle(QR_BOX, outline="blue", width=3)

    img.save(output_path)

    return inserted_count


# ==============================
# TELEGRAM HANDLERS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send Fayda ID image (.jpg/.png/.pdf)\nI will prepare it for print."
    )


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.document.get_file()

        input_path = os.path.join(OUTPUT_FOLDER, "input.png")
        output_path = os.path.join(OUTPUT_FOLDER, "result.png")

        await file.download_to_drive(input_path)

        inserted = process_id(input_path, output_path)

        await update.message.reply_text(
            f"✅ Your Fayda ID is Ready!\n📊 Inserted {inserted} fields"
        )

        await update.message.reply_photo(open(output_path, "rb"))

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        print(e)


# ==============================
# RUN BOT
# ==============================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
