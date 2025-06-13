# ไฟล์สำหรับติดตั้ง dependencies สำหรับ Playwright บน Hugging Face Space
import os
import subprocess
import sys
import platform

print("กำลังติดตั้ง system dependencies สำหรับ Playwright...")

# ตรวจสอบว่ากำลังรันบน Hugging Face Spaces หรือไม่
is_on_spaces = os.environ.get('SPACE_ID') is not None
is_linux = platform.system() == "Linux"

print(f"ระบบปฏิบัติการ: {platform.system()}")
print(f"รันบน Hugging Face Spaces: {'ใช่' if is_on_spaces else 'ไม่ใช่'}")

# สำหรับ HF Spaces ซึ่งเป็น Linux
if is_on_spaces and is_linux:
    print("กำลังติดตั้ง dependencies สำหรับ Hugging Face Spaces...")
    
    # ติดตั้ง apt dependencies ที่จำเป็น (ไม่ต้องใช้ sudo บน HF Spaces)
    try:
        print("ติดตั้งแพ็กเกจ apt ที่จำเป็น...")
        subprocess.run(["apt-get", "update", "-y"], check=False)
        
        # ติดตั้ง chromium-browser
        try:
            subprocess.run(["apt-get", "install", "-y", "chromium-browser"], check=False)
            print("ติดตั้ง chromium-browser สำเร็จ")
            
            # ตั้งค่า environment variable
            os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'] = '/usr/bin/chromium-browser'
            
            # บันทึกลงใน ~/.bashrc เพื่อให้ใช้งานได้ในครั้งต่อไป
            with open(os.path.expanduser("~/.bashrc"), "a") as bashrc:
                bashrc.write('\nexport PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser\n')
        except Exception as chrome_error:
            print(f"ไม่สามารถติดตั้ง chromium-browser: {chrome_error}")
        
        # ติดตั้งแพ็กเกจที่จำเป็นสำหรับ Chromium
        apt_packages = [
            "libnss3", "libnspr4", "libatk1.0-0", "libatk-bridge2.0-0",
            "libatspi2.0-0", "libxcomposite1", "libxdamage1", "libgbm1",
            "libpango-1.0-0", "libcairo-gobject2", "fonts-liberation",
            "libx11-xcb1", "libxcb-dri3-0", "libxss1", "libxtst6",
            "xdg-utils", "libdrm2", "libxkbcommon0", "libxrandr2"
        ]
        
        for pkg in apt_packages:
            try:
                subprocess.run(["apt-get", "install", "-y", pkg], check=False)
                print(f"ติดตั้ง {pkg} สำเร็จ")
            except Exception as pkg_error:
                print(f"ไม่สามารถติดตั้ง {pkg}: {pkg_error}")
    
    except Exception as apt_error:
        print(f"ไม่สามารถอัปเดตหรือติดตั้งแพ็กเกจ: {apt_error}")
    
    # ติดตั้ง dependencies ด้วย playwright install-deps โดยตรง
    try:
        print("ติดตั้ง dependencies ด้วย playwright install-deps...")
        subprocess.run(["playwright", "install-deps", "chromium"], check=False)
    except Exception as pw_error:
        print(f"ไม่สามารถติดตั้ง dependencies ด้วย playwright: {pw_error}")
        try:
            print("ลองใช้ python -m playwright...")
            subprocess.run(["python", "-m", "playwright", "install-deps", "chromium"], check=False)
        except Exception as pw_error2:
            print(f"ไม่สามารถติดตั้ง dependencies ด้วย python -m: {pw_error2}")

# สำหรับระบบ Linux ทั่วไป
elif is_linux:
    # ตรวจสอบว่ามีสิทธิ์ sudo หรือไม่
    try:
        has_sudo = subprocess.run(["which", "sudo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0
        
        if has_sudo:
            # ติดตั้ง dependencies ด้วย apt
            try:
                print("ติดตั้ง dependencies ผ่าน APT...")
                subprocess.run(["sudo", "apt-get", "update", "-y"], check=False)
                subprocess.run([
                    "sudo", "apt-get", "install", "-y",
                    "chromium-browser", "libnss3", "libnspr4", "libatk1.0-0", "libatk-bridge2.0-0",
                    "libatspi2.0-0", "libxcomposite1", "libxdamage1", "libgbm1", "libpango-1.0-0",
                    "libcairo-gobject2", "fonts-liberation", "libx11-xcb1", "libxcb-dri3-0", 
                    "libxss1", "libxtst6", "xdg-utils"
                ], check=False)
            except Exception as e:
                print(f"Error installing dependencies with apt: {str(e)}")
            
            # ติดตั้ง dependencies ด้วย playwright install-deps
            try:
                print("ติดตั้ง dependencies ผ่าน Playwright...")
                subprocess.run(["sudo", "npx", "playwright", "install-deps", "chromium"], check=False)
            except Exception as e:
                print(f"Error installing dependencies with playwright: {str(e)}")
        else:
            print("ไม่มีสิทธิ์ sudo สำหรับติดตั้ง system dependencies")
    except Exception as sudo_error:
        print(f"เกิดข้อผิดพลาดในการตรวจสอบสิทธิ์ sudo: {sudo_error}")

# ติดตั้ง Playwright browsers สำหรับทุกระบบ
try:
    print("ติดตั้ง Playwright browsers...")
    
    # ตรวจสอบว่า chromium-browser มีอยู่หรือไม่
    chromium_path = None
    if is_linux:
        if os.path.exists("/usr/bin/chromium-browser"):
            chromium_path = "/usr/bin/chromium-browser"
        else:
            try:
                which_result = subprocess.run(["which", "chromium-browser"], 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.PIPE, 
                                           text=True, 
                                           check=False)
                if which_result.returncode == 0:
                    chromium_path = which_result.stdout.strip()
            except Exception:
                pass
    
    if chromium_path:
        # ใช้ chromium ที่มีอยู่แล้ว
        print(f"ใช้ Chromium ที่มีอยู่แล้วที่: {chromium_path}")
        os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'] = chromium_path
        
        # ยืนยันการติดตั้ง playwright browsers
        subprocess.run(["playwright", "install", "chromium"], check=False)
    else:
        # ติดตั้ง Chromium browser
        subprocess.run(["playwright", "install", "chromium"], check=False)
    
    print("ติดตั้ง Chromium browser สำเร็จ")
except Exception as browser_error:
    print(f"ไม่สามารถติดตั้ง Playwright browsers: {browser_error}")
    try:
        # ลองใช้ python -m
        subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=False)
        print("ติดตั้ง Chromium browser ผ่าน python -m สำเร็จ")
    except Exception as python_error:
        print(f"ไม่สามารถติดตั้ง browsers ด้วย python -m: {python_error}")

print("เสร็จสิ้นการติดตั้ง dependencies")
