#!/bin/bash
# สคริปต์เริ่มต้นสำหรับ Hugging Face Spaces

# ติดตั้ง Chromium และ dependencies ที่จำเป็น
echo "กำลังติดตั้ง dependencies สำหรับ Playwright..."

# ติดตั้ง chromium-browser
apt-get update -y
apt-get install -y chromium-browser

# ตั้งค่า environment variable
export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
echo "export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser" >> ~/.bashrc

# ติดตั้ง Python packages 
pip install -r requirements.txt

# ติดตั้ง playwright
pip install playwright
python -m playwright install chromium
python -m playwright install-deps chromium

# เริ่มต้นแอปพลิเคชัน
python app.py
