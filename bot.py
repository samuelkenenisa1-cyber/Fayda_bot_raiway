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
    """Normalize Ethiopian punctuation to standard."""
    return text.replace("፡", ":").replace("፣", ",").strip()

def split_bilingual(value: str):
    """Split bilingual text (Amharic|English)."""
    if "|" in value:
        am, en = value.split("|", 1)
        return am.strip(), en.strip()
    return value.strip(), value.strip()

def extract_field(lines, keys):
    """Extract field value from text lines."""
    for i, line in enumerate(lines):
        for key in keys:
            if key in line:
                if ":" in line:
                    return line.split(":", 1)[1].strip()
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
    return ""

def parse_fayda(text: str):
    """Extract data from Ethiopian Fayda ID text."""
    lines = [normalize(l) for l in text.splitlines() if l.strip()]
    
    data = {
        "name": "",
        "dob": "",
        "sex": "",
        "expiry": "",  # Note: Not in standard Fayda ID
        "issue": "",   # Note: Not in standard Fayda ID
        "fan": "",     # FCN (Fayda Card Number)
        "fin": "",     # Note: Not in standard Fayda ID
        "phone": "",
        "nationality": "",
        "address": "",
    }
    
    print("=== DEBUG: PDF LINES ===")
    for i, line in enumerate(lines):
        print(f"Line {i}: {line}")
    
    # Extract name (from "መት ስሞ / First, Middle, Surname")
    for i, line in enumerate(lines):
        if "መት ስሞ" in line or "First, Middle, Surname" in line:
            if i + 1 < len(lines):
                data["name"] = lines[i + 1].strip()
                print(f"✓ Found name: {data['name']}")
                break
    
    # Extract FCN (Fayda Card Number)
    for line in lines:
        if "FCN:" in line:
            data["fan"] = line.replace("FCN:", "").strip()
            print(f"✓ Found FCN: {data['fan']}")
            break
    
    # Extract Date of Birth
    for line in lines:
        if "የትውልድ ቀን" in line or "Date of Birth" in line:
            # Try to extract date pattern (DD/MM/YYYY)
            dates = re.findall(r'\d{2}/\d{2}/\d{4}', line)
            if dates:
                data["dob"] = dates[0]
                print(f"✓ Found DOB: {data['dob']}")
            break
    
    # Extract Sex
    for i, line in enumerate(lines):
        if "SEX" in line or "+ /" in line:
            # Look for Male/Female
            if "Male" in line:
                data["sex"] = "ወንድ | Male"
                print(f"✓ Found sex: Male")
                break
            elif "Female" in line:
                data["sex"] = "ሴት | Female"
                print(f"✓ Found sex: Female")
                break
            # Check next line
            elif i + 1 < len(lines):
                next_line = lines[i + 1]
                if "Male" in next_line:
                    data["sex"] = "ወንድ | Male"
                    print(f"✓ Found sex: Male")
                    break
                elif "Female" in next_line:
                    data["sex"] = "ሴት | Female"
                    print(f"✓ Found sex: Female")
                    break
    
    # Extract Phone Number
    for line in lines:
        if "ስልክ" in line or "Phone Number" in line:
            phone_match = re.search(r'\d{10}', line)
            if phone_match:
                data["phone"] = phone_match.group(0)
                print(f"✓ Found phone: {data['phone']}")
            break
    
    # Extract Nationality
    for line in lines:
        if "ኢትዮጵያዊ" in line or "Ethiopian" in line:
            data["nationality"] = "ኢትዮጵያዊ | Ethiopian"
            print("✓ Found nationality: Ethiopian")
            break
    
    # Build Address from Region, Subcity, Woreda
    address_parts = []
    for i, line in enumerate(lines):
        if "ክልል / Region" in line and i + 1 < len(lines):
            address_parts.append(lines[i + 1].strip())
        elif "ክፍለ ከተማ / ም / Subcity / zone" in line and i + 1 < len(lines):
            address_parts.append(lines[i + 1].strip())
        elif "መረጃ / Woreda" in line and i + 1 < len(lines):
            address_parts.append(lines[i + 1].strip())
    
    if address_parts:
        data["address"] = ", ".join(address_parts)
        print(f"✓ Found address: {data['address']}")
    
    print("=== DEBUG: PARSED DATA ===")
    for key, value in data.items():
        print(f"  {key}: {value}")
    
    return data

def draw_vertical_text(base_img, text, position):
    """Draw vertically oriented text."""
    temp = Image.new("RGBA", (400, 60), (255, 255, 255, 0))
    d = ImageDraw.Draw(temp)
    font = ImageFont.truetype(FONT_PATH, 22)
    d.text((0, 0), text, fill="#2b2b2b", font=font)
    rotated = temp.rotate(90, expand=1)
    base_img.paste(rotated, position, rotated)

def bilingual_draw(draw, x, y, value, font_main, font_small):
    """Draw bilingual text (Amharic above English)."""
    am, en = split_bilingual(value)
    draw.text((x, y), am, fill="#2b2b2b", font=font_main)
    draw.text((x, y + 26), en, fill="#2b2b2b", font=font_small)

# ======================
# MAIN HANDLER
# ======================

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle PDF document uploads."""
    print("🟢 handle_pdf function CALLED")
    
    if not update.message or not update.message.document:
        await update.message.reply_text("❌ No document received.")
        return
    
    doc = update.message.document
    print(f"📄 File name: {doc.file_name}")
    print(f"📦 File size: {doc.file_size} bytes")
    
    # Validate PDF
    if not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
        print("❌ File is not a PDF")
        await update.message.reply_text("❌ Please send a Fayda ID PDF file.")
        return
    
    print("✅ Valid PDF detected. Starting download...")
    
    try:
        # Download the PDF
        file = await doc.get_file()
        await file.download_to_drive("id.pdf")
        print("✅ PDF downloaded successfully")
        
        # Extract text from PDF
        text = ""
        try:
            with pdfplumber.open("id.pdf") as pdf:
                print(f"📑 PDF has {len(pdf.pages)} page(s)")
                
                for i, page in enumerate(pdf.pages):
                    # Try standard extraction
                    page_text = page.extract_text() or ""
                    
                    # If no text, try with tolerance
                    if not page_text.strip():
                        page_text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
                    
                    # If still no text, try extracting words
                    if not page_text.strip():
                        words = page.extract_words()
                        if words:
                            page_text = " ".join([w['text'] for w in words])
                    
                    print(f"📄 Page {i+1}: Extracted {len(page_text)} characters")
                    text += page_text + "\n"
                    
        except Exception as pdf_error:
            print(f"❌ PDF extraction error: {pdf_error}")
            await update.message.reply_text("❌ Could not read the PDF. It might be scanned or corrupted.")
            return
        
        print("=== RAW PDF TEXT (first 1000 chars) ===")
        print(text[:1000] if text else "(Empty)")
        print("=== END TEXT ===")
        
        if not text.strip():
            await update.message.reply_text("❌ No text found in PDF. Please send a text-based PDF.")
            return
        
        # Parse the extracted data
        data = parse_fayda(text)
        
        # Check if we got essential data
        if not data["name"] and not data["fan"]:
            await update.message.reply_text("⚠️ Could not extract ID information. Check PDF format.")
            return
        
        print("🎨 Generating ID image...")
        
        # Load template and fonts
        if not os.path.exists(TEMPLATE_PATH):
            print(f"❌ Template file not found: {TEMPLATE_PATH}")
            await update.message.reply_text("❌ Template image missing. Contact admin.")
            return
            
        if not os.path.exists(FONT_PATH):
            print(f"❌ Font file not found: {FONT_PATH}")
            await update.message.reply_text("❌ Font file missing. Contact admin.")
            return
        
        try:
            img = Image.open(TEMPLATE_PATH).convert("RGBA")
            draw = ImageDraw.Draw(img)
            
            font_main = ImageFont.truetype(FONT_PATH, 26)
            font_small = ImageFont.truetype(FONT_PATH, 22)
            
            print("🖌️ Drawing text on template...")
            
            # FRONT SIDE
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
            
            # BACK SIDE
            bilingual_draw(draw, 1150, 160, data["phone"], font_main, font_small)
            bilingual_draw(draw, 1150, 225, data["nationality"], font_main, font_small)
            bilingual_draw(draw, 1150, 300, data["address"], font_main, font_small)
            
            draw.text((1150, 525), data["fin"], fill="#000000", font=font_main)
            
            # Save and send
            output_path = "final_id.png"
            img.save(output_path)
            print(f"✅ Image saved: {output_path}")
            
            await update.message.reply_photo(
                photo=open(output_path, "rb"),
                caption="✅ ID processed successfully!"
            )
            
        except Exception as image_error:
            print(f"❌ Image generation error: {image_error}")
            await update.message.reply_text("❌ Error generating ID image.")
            
        finally:
            # Cleanup temporary files
            for f in ["id.pdf", "final_id.png"]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                        print(f"🧹 Cleaned up: {f}")
                    except:
                        pass
                        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        await update.message.reply_text("❌ An error occurred while processing the PDF.")

# ======================
# COMMAND HANDLERS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome_text = """
👋 *Welcome to Fayda ID Bot*

Send me your *Fayda National ID PDF* and I will generate a printable ID image.

📋 *Requirements:*
• Send the PDF file directly (not as a link)
• Ensure the PDF is text-based (not scanned)
• The PDF should be from the official Fayda system

📄 *How to use:*
1. Get your Fayda ID PDF from the official system
2. Send it here as a document
3. Receive your formatted ID image

⚠️ *Disclaimer:*
This bot processes IDs for personal use only.
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = """
🆘 *Help - Fayda ID Bot*

*Available Commands:*
/start - Start the bot
/help - Show this help message

*Troubleshooting:*
• Empty template? Your PDF might be scanned, not text-based
• No response? Send the PDF as a *document* (not photo)
• Wrong data? Ensure your PDF is from the official Fayda system

*Support:*
Contact the bot administrator for issues.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads."""
    print("📁 DEBUG: Received a document!")
    
    if not update.message or not update.message.document:
        await update.message.reply_text("❌ No document received.")
        return
    
    doc = update.message.document
    print(f"    File Name: {doc.file_name}")
    print(f"    MIME Type: {doc.mime_type}")
    print(f"    File Size: {doc.file_size} bytes")
    
    # Check if it's a PDF
    if doc.file_name and doc.file_name.lower().endswith('.pdf'):
        print("    ✅ This is a PDF. Processing...")
        await handle_pdf(update, context)
    else:
        await update.message.reply_text("❌ Please send a PDF file.")

# ======================
# MAIN APPLICATION
# ======================

def main():
    """Start the bot."""
    print("🚀 Initializing Fayda ID Bot...")
    
    # Check environment
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN environment variable not set!")
        raise RuntimeError("BOT_TOKEN is not set. Add it in Railway Variables.")
    
    print("✅ Environment check passed")
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    print("✅ Application created")
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ Handlers registered")
    print("🤖 Bot started and polling...")
    
    # Start polling
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
