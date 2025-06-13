#!/bin/bash
set -e  # Exit on error

# ติดตั้ง dependencies สำหรับ Playwright บน Linux/Hugging Face Spaces
echo "กำลังติดตั้ง dependencies สำหรับ ChatGPT Dumper..."

# Function to check if package is installed
check_package() {
    dpkg -l "$1" &> /dev/null
}

# Function to install package if not present
install_package() {
    if ! check_package "$1"; then
        echo "กำลังติดตั้ง $1..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y "$1" || echo "ไม่สามารถติดตั้ง $1 ได้"
    else
        echo "$1 ติดตั้งอยู่แล้ว"
    fi
}

# ตรวจสอบระบบปฏิบัติการ
if [[ "$(uname)" == "Linux" ]]; then
    echo "ตรวจพบระบบปฏิบัติการ Linux กำลังติดตั้ง dependencies..."
    
    # ตรวจสอบว่าอยู่บน Hugging Face Spaces หรือไม่
    if [[ -n "${SPACE_ID}" ]]; then
        echo "กำลังติดตั้งบน Hugging Face Space..."
        
        # อัปเดต package lists
        apt-get update -y || echo "ไม่สามารถอัปเดต apt ได้ แต่จะดำเนินการต่อ"
        
        # ติดตั้ง dependencies ที่จำเป็น
        PACKAGES=(
            "chromium-browser"
            "libnss3"
            "libnspr4"
            "libatk1.0-0"
            "libatk-bridge2.0-0"
            "libatspi2.0-0"
            "libxcomposite1"
            "libxdamage1"
            "libgbm1"
            "libpango-1.0-0"
            "libcairo-gobject2"
            "fonts-liberation"
            "libx11-xcb1"
            "libxcb-dri3-0"
            "libxss1"
            "libxtst6"
            "xdg-utils"
            "libdrm2"
            "libxkbcommon0"
            "libxrandr2"
        )

        for pkg in "${PACKAGES[@]}"; do
            install_package "$pkg"
        done

        # ตั้งค่า Playwright environment
        mkdir -p ~/.cache/ms-playwright
        chmod 777 ~/.cache/ms-playwright

        # ตั้งค่า environment variables
        export PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright
        export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
        
        # บันทึกค่าลงใน .bashrc
        grep -qxF "export PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright" ~/.bashrc || \
            echo "export PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright" >> ~/.bashrc
        grep -qxF "export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1" ~/.bashrc || \
            echo "export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1" >> ~/.bashrc
        
    else
        # สำหรับ Linux ทั่วไปที่ไม่ใช่ HF Spaces
        if command -v sudo &> /dev/null; then
            echo "ติดตั้ง dependencies ด้วย sudo..."
            sudo apt-get update -y
            sudo apt-get install -y chromium-browser
            sudo apt-get install -y "${PACKAGES[@]}"
        else
            echo "ไม่มีสิทธิ์ sudo ไม่สามารถติดตั้ง dependencies ได้"
            exit 1
        fi
    fi
    
    # ตรวจสอบ Chromium path
    if [ -f /usr/bin/chromium-browser ]; then
        CHROMIUM_PATH="/usr/bin/chromium-browser"
    elif [ -f /usr/bin/chromium ]; then
        CHROMIUM_PATH="/usr/bin/chromium"
    else
        echo "ไม่พบ Chromium ในตำแหน่งมาตรฐาน"
        exit 1
    fi
    
    echo "พบ Chromium ที่: $CHROMIUM_PATH"
    export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="$CHROMIUM_PATH"
    grep -qxF "export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=$CHROMIUM_PATH" ~/.bashrc || \
        echo "export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=$CHROMIUM_PATH" >> ~/.bashrc
fi

# ติดตั้ง Python packages
echo "กำลังติดตั้ง Python packages..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# ติดตั้ง playwright
echo "กำลังติดตั้ง playwright..."
python -m pip install --upgrade playwright
python -m playwright install-deps chromium

# ตรวจสอบการติดตั้ง
echo "กำลังตรวจสอบการติดตั้ง..."
if [[ "$(uname)" == "Linux" ]]; then
    if [ -f "$CHROMIUM_PATH" ]; then
        echo "✓ Chromium ติดตั้งสำเร็จ"
        if [ -x "$CHROMIUM_PATH" ]; then
            echo "✓ Chromium สามารถเรียกใช้งานได้"
        else
            echo "กำลังตั้งค่าสิทธิ์การเรียกใช้งาน Chromium..."
            chmod +x "$CHROMIUM_PATH"
        fi
    else
        echo "× การติดตั้ง Chromium ล้มเหลว"
        exit 1
    fi
fi

echo "การติดตั้ง dependencies เสร็จสิ้น!"
