#!/bin/bash
# สคริปต์สำหรับรันบน Hugging Face Spaces

echo "กำลังเริ่มต้น ChatGPT Dumper บน Hugging Face Spaces..."

# ตรวจสอบว่า chromium-browser ถูกติดตั้งแล้วหรือยัง
if [ ! -f /usr/bin/chromium-browser ]; then
  echo "ไม่พบ Chromium browser กำลังติดตั้ง..."
  apt-get update -y
  apt-get install -y chromium-browser
  echo "ติดตั้ง Chromium browser เสร็จสิ้น"
fi

# ตั้งค่า environment variable
export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser

# ตรวจสอบว่า Playwright ถูกติดตั้งแล้วหรือยัง
if ! python -c "import playwright" &> /dev/null; then
  echo "ไม่พบ Playwright กำลังติดตั้ง..."
  pip install playwright
  echo "ติดตั้ง Playwright เสร็จสิ้น"
fi

# ติดตั้ง system dependencies สำหรับ Playwright
python -m playwright install-deps chromium

# เริ่มต้นแอปพลิเคชัน
python app.py
