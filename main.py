import os
import shutil
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    FSInputFile
)
import fitz  # PyMuPDF
from pdf2docx import Converter
import pandas as pd
import pdfplumber

BOT_TOKEN = os.getenv("8678211885:AAHIpB6Zw_A2kv8OaCdMBmqP1n27iu65k_M")
WEB_APP_URL = os.getenv("https://arindamwandar-maker.github.io/pdf-ad-gate/")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# user_id -> {"converted_path": str, "cleanup_dir": str}
user_state = {}

@dp.message(F.document)
async def process_incoming_pdf(message: Message):
    if not (message.document.file_name and message.document.file_name.lower().endswith(".pdf")):
        await message.reply("Please upload a PDF document.")
        return

    user_id = message.from_user.id
    user_dir = f"/tmp/bot_{user_id}"
    os.makedirs(user_dir, exist_ok=True)
    
    pdf_input = os.path.join(user_dir, "input.pdf")
    
    file_info = await bot.get_file(message.document.file_id)
    await bot.download_file(file_info.file_path, pdf_input)

    # Offer conversion choices
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 To Word (.docx)", callback_data="conv_word"),
            InlineKeyboardButton(text="📊 To Excel (.xlsx)", callback_data="conv_excel")
        ],
        [
            InlineKeyboardButton(text="🖼️ To Image (.png)", callback_data="conv_png"),
            InlineKeyboardButton(text="🗜️ Compress PDF", callback_data="conv_compress")
        ]
    ])

    await message.reply("PDF received! Choose an action:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("conv_"))
async def handle_conversion(callback: CallbackQuery):
    action = callback.data
    user_id = callback.from_user.id
    user_dir = f"/tmp/bot_{user_id}"
    pdf_input = os.path.join(user_dir, "input.pdf")

    if not os.path.exists(pdf_input):
        await callback.message.reply("Session expired. Please send the PDF again.")
        await callback.answer()
        return

    await callback.message.edit_text("⏳ Processing your file, please wait...")
    output_path = None

    try:
        if action == "conv_word":
            output_path = os.path.join(user_dir, "converted.docx")
            cv = Converter(pdf_input)
            cv.convert(output_path, start=0, end=None)
            cv.close()

        elif action == "conv_excel":
            output_path = os.path.join(user_dir, "converted.xlsx")
            extracted_tables = []
            with pdfplumber.open(pdf_input) as pdf:
                for page in pdf.pages:
                    table = page.extract_table()
                    if table:
                        extracted_tables.extend(table)
            
            if extracted_tables:
                df = pd.DataFrame(extracted_tables[1:], columns=extracted_tables[0])
                df.to_excel(output_path, index=False)
            else:
                # Fallback to empty excel if no table detected
                pd.DataFrame({"Info": ["No distinct tables detected in PDF"]}).to_excel(output_path, index=False)

        elif action == "conv_png":
            output_path = os.path.join(user_dir, "page_1.png")
            doc = fitz.open(pdf_input)
            page = doc.load_page(0)  # first page
            pix = page.get_pixmap(dpi=150)
            pix.save(output_path)
            doc.close()

        elif action == "conv_compress":
            output_path = os.path.join(user_dir, "compressed.pdf")
            doc = fitz.open(pdf_input)
            doc.save(output_path, garbage=4, deflate=True, clean=True)
            doc.close()

        # Cache file path awaiting the ad view
        user_state[user_id] = {
            "file": output_path,
            "dir": user_dir
        }

        # Show button that opens Adsgram Mini App
        unlock_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🎬 Watch Ad to Download",
                web_app=WebAppInfo(url=WEB_APP_URL)
            )
        ]])

        await callback.message.reply(
            "✅ File converted successfully!\nWatch a 15-second sponsor video to claim your file:",
            reply_markup=unlock_keyboard
        )

    except Exception as e:
        await callback.message.reply(f"Conversion failed: {str(e)}")
    
    await callback.answer()


@dp.message(F.web_app_data)
async def handle_ad_unlock(message: Message):
    if message.web_app_data.data == "UNLOCKED_OK":
        user_id = message.from_user.id
        data = user_state.get(user_id)

        if data and os.path.exists(data["file"]):
            file_to_send = FSInputFile(data["file"])
            await message.reply_document(
                document=file_to_send,
                caption="Here is your file! Thank you for watching the sponsor clip."
            )
            # Clean up local storage
            shutil.rmtree(data["dir"], ignore_errors=True)
            user_state.pop(user_id, None)
        else:
            await message.reply("File expired or unavailable. Please re-send your PDF.")


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
