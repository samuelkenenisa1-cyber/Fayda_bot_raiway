import os
import re
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
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

def extract_fuzzy(lines, keywords):
    for i, line in enumerate(lines):
        for key in keywords:
            if key.lower() in line.lower():
                parts = re.split(r"[:\-]", line, 1)
                if len(parts) > 1:
                    return parts[1].strip()
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
    return ""

def parse_fayda(text: str):
    lines = [normalize(l) for l in text.splitlines() if l.strip()]

    print("=== DEBUG: OCR LINES ===")
    for i, l in enumerate(lines):
        print(f"{i}: {l}")

    data = {
        "name": extract_fuzzy(lines, ["First, Middle, Surname", "መሉ ስሞ"]),
        "fan": extract_fuzzy(lines, ["FCN", "FAN"]),
        "dob": extract_fuzzy(lines, ["Date of Birth", "የትውልድ ቀን"]),
        "issue": extract_fuzzy(lines, ["Date of Issue", "የተሰጠበት ቀን"]),
        "sex": "",
        "phone": "",
        "nationality": "",
        "address": "",
        "expiry": "",
        "fin": "",
    }

    for l in lines:
        if "Male" in l:
            data["sex"] = "ወንድ | Male"
        elif "Female" in l:
            data["sex"] = "ሴት | Female"

        phone = re.search(r"\b09\d{8}\b", l)
        if phone:
            data["phone"] = phone.group()

        if "Ethiopian" in l or "ኢትዮጵያዊ" in l:
            data["nationality"] = "ኢትዮጵያዊ | Ethiopian"

    address_parts = []
    for i, l in enumerate(lines):
        if "Region" in l and i + 1 < len(lines):
            address_parts.append(lines[i + 1])
        if "Subcity" in l and i + 1 < len(lines):
            address_parts.append(lines[i + 1])
        if "Woreda" in l and i + 1 < len(lines):
            address_parts.append(lines[i + 1])

    if address_parts:
        data["address"] = ", ".join(address_parts)

    print("=== PARSED DATA ===")
    for k, v in data.items():
        print(k, ":", v)

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
    file = await doc.get_file()
    await file.download_to_drive("id.pdf")

    ocr_text = ""

    images = convert_from_path("id.pdf", dpi=300)
    for img in images:
        img_np = np.array(img)
        gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]

        ocr_text += pytesseract.image_to_string(
            gray, lang="amh+eng", config="--psm 6"
        )

    if not ocr_text.strip():
        await update.message.reply_text("❌ OCR failed.")
        return

    data = parse_fayda(ocr_text)

    img = Image.open(TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_main = ImageFont.truetype(FONT_PATH, 26)
    font_small = ImageFont.truetype(FONT_PATH, 22)

    bilingual_draw(draw, 420, 215, data["name"], font_main, font_small)
    bilingual_draw(draw, 420, 265, data["dob"], font_main, font_small)
    bilingual_draw(draw, 420, 315, data["sex"], font_main, font_small)
    draw.text((220, 540), data["fan"], fill="#000", font=font_small)

    output = "final_id.png"
    img.save(output)

    await update.message.reply_photo(photo=open(output, "rb"))

    os.remove("id.pdf")
    os.remove(output)

# ======================
# COMMANDS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send Fayda ID PDF.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.run_polling()

if __name__ == "__main__":
    main()
