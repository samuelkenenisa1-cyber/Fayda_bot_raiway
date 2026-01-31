import os
import re
import pytesseract
import cv2
import numpy as np
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv("BOT_TOKEN")
TEMPLATE_PATH = "template.png"
FONT_PATH = "font.ttf"

user_sessions = {}

# ======================
# UTILITIES
# ======================

def ocr_image(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]
    return pytesseract.image_to_string(
        gray, lang="amh+eng", config="--psm 6"
    )

def extract(lines, keys):
    for i, l in enumerate(lines):
        for k in keys:
            if k.lower() in l.lower():
                parts = re.split(r"[:\-]", l, 1)
                if len(parts) > 1:
                    return parts[1].strip()
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
    return ""

def parse_front(text):
    lines = text.splitlines()
    return {
        "name": extract(lines, ["First, Middle, Surname", "መሉ ስሞ"]),
        "dob": extract(lines, ["Date of Birth", "የትውልድ ቀን"]),
        "fan": extract(lines, ["FAN", "FCN"]),
        "issue": extract(lines, ["Date of Issue", "የተሰጠበት ቀን"]),
        "sex": "ወንድ | Male" if "Male" in text else "ሴት | Female" if "Female" in text else ""
    }

def parse_back(text):
    lines = text.splitlines()
    phone = re.search(r"\b09\d{8}\b", text)
    return {
        "phone": phone.group() if phone else "",
        "nationality": "ኢትዮጵያዊ | Ethiopian" if "Ethiopian" in text else "",
        "address": extract(lines, ["Region", "Subcity", "Woreda"]),
        "fin": extract(lines, ["FIN", "SIN"]),
    }

def draw_bilingual(draw, x, y, value, font_main, font_small):
    if "|" in value:
        am, en = value.split("|", 1)
        draw.text((x, y), am.strip(), font=font_main, fill="#000")
        draw.text((x, y + 26), en.strip(), font=font_small, fill="#000")
    else:
        draw.text((x, y), value, font=font_main, fill="#000")

# ======================
# IMAGE HANDLER
# ======================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_sessions:
        user_sessions[user_id] = []

    photo = update.message.photo[-1]
    file = await photo.get_file()
    path = f"{user_id}_{len(user_sessions[user_id])}.jpg"
    await file.download_to_drive(path)

    user_sessions[user_id].append(path)

    count = len(user_sessions[user_id])
    await update.message.reply_text(f"📸 Image {count}/3 received")

    if count < 3:
        return

    # ======================
    # PROCESS 3 IMAGES
    # ======================

    front_text = ocr_image(user_sessions[user_id][0])
    back_text = ocr_image(user_sessions[user_id][1])
    photo_qr_img = Image.open(user_sessions[user_id][2])

    data = {}
    data.update(parse_front(front_text))
    data.update(parse_back(back_text))

    # ======================
    # RENDER TEMPLATE
    # ======================

    img = Image.open(TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_main = ImageFont.truetype(FONT_PATH, 26)
    font_small = ImageFont.truetype(FONT_PATH, 22)

    draw_bilingual(draw, 420, 215, data["name"], font_main, font_small)
    draw_bilingual(draw, 420, 265, data["dob"], font_main, font_small)
    draw_bilingual(draw, 420, 315, data["sex"], font_main, font_small)
    draw.text((220, 540), data["fan"], font=font_small, fill="#000")

    draw_bilingual(draw, 1150, 160, data["phone"], font_main, font_small)
    draw_bilingual(draw, 1150, 225, data["nationality"], font_main, font_small)
    draw_bilingual(draw, 1150, 300, data["address"], font_main, font_small)

    # PHOTO + QR
    photo_qr_img = photo_qr_img.resize((300, 300))
    img.paste(photo_qr_img, (100, 150))

    out = f"{user_id}_final.png"
    img.save(out)

    await update.message.reply_photo(photo=open(out, "rb"))

    # CLEANUP
    for f in user_sessions[user_id]:
        os.remove(f)
    os.remove(out)
    del user_sessions[user_id]

# ======================
# COMMANDS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Send 3 screenshots in order:\n"
        "1️⃣ Front page\n"
        "2️⃣ Back page\n"
        "3️⃣ Photo + QR\n"
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()

if __name__ == "__main__":
    main()
