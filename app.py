import asyncio
import json
import logging
import os
import sys
import subprocess
import platform
from datetime import datetime, timezone
import pandas as pd
import requests
import re
import traceback
from datasets import Dataset
import gradio as gr
import shutil
import signal
import time
import unicodedata

# ตั้งค่า virtual display สำหรับ Hugging Face Spaces
is_on_spaces = os.environ.get('SPACE_ID') is not None
xvfb_process = None

def start_xvfb():
    global xvfb_process
    try:
        # ตรวจสอบว่า Xvfb ถูกติดตั้งหรือไม่
        result = subprocess.run(['which', 'Xvfb'], check=True, capture_output=True)
        
        # ตรวจสอบว่ามี display :0 ทำงานอยู่หรือไม่
        try:
            subprocess.run(['pkill', '-f', 'Xvfb.*:0'], check=False)
            time.sleep(1)  # รอให้ process เก่าถูกปิด
        except:
            pass
            
        # เริ่ม Xvfb บน display :0
        xvfb_process = subprocess.Popen([
            'Xvfb', ':0',
            '-screen', '0', '1280x1024x24',
            '-ac',
            '+extension', 'RANDR',
            '+render',
            '-noreset'
        ])
        
        # ตั้งค่า environment variable
        os.environ['DISPLAY'] = ':0'
        
        # รอให้ Xvfb พร้อมใช้งาน
        time.sleep(2)
        
        # ตรวจสอบว่า Xvfb ทำงานอยู่
        if xvfb_process.poll() is not None:
            raise Exception("Xvfb failed to start")
            
        print("Started Xvfb successfully")
        return True
    except Exception as e:
        print(f"Failed to start Xvfb: {str(e)}")
        return False

if is_on_spaces:
    # ตั้งค่า DISPLAY สำหรับ Hugging Face Spaces
    if not os.environ.get('DISPLAY'):
        os.environ['DISPLAY'] = ':0'  # ใช้ display :0 ที่ถูกตั้งค่าใน postBuild
    
    # ตรวจสอบว่า Xvfb พร้อมใช้งานหรือไม่
    if shutil.which('Xvfb'):
        if not start_xvfb():
            print("WARNING: Could not start Xvfb, Playwright may not work correctly")
    else:
        print("Xvfb not found, Playwright may not work correctly")

# ตัวแปรแสดงว่ากำลังใช้ fallback mode หรือไม่
USE_FALLBACK = False

def convert_html_to_markdown(html_content):
    """แปลง HTML เป็น Markdown format โดยคงรูปแบบโค้ดและตารางไว้"""
    if not html_content:
        return html_content
    
    # แก้ไขปัญหา \r\n ก่อนอื่น
    html_content = html_content.replace('\r\n', '\n').replace('\r', '\n')
    
    # แปลงโค้ดบล็อก
    html_content = re.sub(
        r'<pre[^>]*><code[^>]*class="language-(\w+)"[^>]*>(.*?)</code></pre>',
        r'```\1\n\2\n```',
        html_content,
        flags=re.DOTALL
    )
    
    html_content = re.sub(
        r'<pre[^>]*><code[^>]*>(.*?)</code></pre>',
        r'```\n\1\n```',
        html_content,
        flags=re.DOTALL
    )
    
    html_content = re.sub(
        r'<pre[^>]*>(.*?)</pre>',
        r'```\n\1\n```',
        html_content,
        flags=re.DOTALL
    )
    
    # แปลงโค้ด inline
    html_content = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html_content)
    
    # แปลงตาราง
    def convert_table(match):
        table_html = match.group(0)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        
        if not rows:
            return table_html
        
        markdown_table = '\n'
        for i, row in enumerate(rows):
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
            if cells:
                # ทำความสะอาดเนื้อหาใน cell
                clean_cells = []
                for cell in cells:
                    cell_text = re.sub(r'<[^>]*>', '', cell).strip()
                    clean_cells.append(cell_text)
                
                markdown_table += '| ' + ' | '.join(clean_cells) + ' |\n'
                
                # เพิ่ม separator หลังแถวแรก
                if i == 0:
                    markdown_table += '|' + ' --- |' * len(clean_cells) + '\n'
        
        return markdown_table + '\n'
    
    html_content = re.sub(r'<table[^>]*>.*?</table>', convert_table, html_content, flags=re.DOTALL)
    
    # แปลงรายการ
    html_content = re.sub(r'<ul[^>]*>(.*?)</ul>', lambda m: convert_list(m.group(1), '- '), html_content, flags=re.DOTALL)
    html_content = re.sub(r'<ol[^>]*>(.*?)</ol>', lambda m: convert_list(m.group(1), '1. '), html_content, flags=re.DOTALL)
    
    # แปลงลิงก์
    html_content = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', html_content)
    
    # แปลงตัวหนา/เอียง
    html_content = re.sub(r'<(strong|b)[^>]*>(.*?)</\1>', r'**\2**', html_content)
    html_content = re.sub(r'<(em|i)[^>]*>(.*?)</\1>', r'*\2*', html_content)
    
    # แปลงหัวข้อ
    for i in range(1, 7):
        html_content = re.sub(f'<h{i}[^>]*>(.*?)</h{i}>', f'\n{"#" * i} \\1\n', html_content)
    
    # แปลงบรรทัดใหม่
    html_content = re.sub(r'<br[^>]*>', '\n', html_content)
    html_content = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', html_content, flags=re.DOTALL)
    
    # ลบ HTML tags ที่เหลือ
    html_content = re.sub(r'<[^>]*>', '', html_content)
    
    # ทำความสะอาด HTML entities
    html_content = html_content.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    html_content = html_content.replace('&quot;', '"').replace('&#x27;', "'")
    
    return html_content

def convert_list(list_content, prefix):
    """แปลงรายการ HTML เป็น Markdown"""
    items = re.findall(r'<li[^>]*>(.*?)</li>', list_content, re.DOTALL)
    result = '\n'
    for i, item in enumerate(items):
        item_text = re.sub(r'<[^>]*>', '', item).strip()
        if prefix == '1. ':
            result += f'{i + 1}. {item_text}\n'
        else:
            result += f'{prefix}{item_text}\n'
    return result + '\n'

# เพิ่มฟังก์ชันสำรองใช้ requests แทน Playwright
def extract_chats_with_requests(url):
    print("กำลังใช้โหมดสำรอง (Requests) แทน Playwright...")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml"
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # จะ raise exception ถ้า status code เป็น 4xx หรือ 5xx
        
        # ดึงข้อมูลบทสนทนา
        messages = []
        
        # พยายามหา user/assistant messages ในหน้า
        user_pattern = r'<div[^>]*data-message-author-role="user"[^>]*>(.*?)<\/div>'
        assistant_pattern = r'<div[^>]*data-message-author-role="assistant"[^>]*>(.*?)<\/div>'
        
        # หา messages ด้วย regex
        user_matches = re.findall(user_pattern, response.text, re.DOTALL)
        assistant_matches = re.findall(assistant_pattern, response.text, re.DOTALL)        # สร้าง messages แบบสลับกัน user และ assistant
        for i in range(max(len(user_matches), len(assistant_matches))):
            if i < len(user_matches):
                # แปลง HTML เป็น markdown format สำหรับโค้ดและตาราง
                content = convert_html_to_markdown(user_matches[i])
                content = clean_content(content)
                if content.strip():
                    messages.append({
                        "role": "user",
                        "content": content.strip(),
                        "timestamp": None
                    })
            
            if i < len(assistant_matches):
                # แปลง HTML เป็น markdown format สำหรับโค้ดและตาราง
                content = convert_html_to_markdown(assistant_matches[i])
                content = clean_content(content)
                if content.strip():
                    messages.append({
                        "role": "ChatGPT",
                        "content": content.strip(),
                        "timestamp": None
                    })
        
        # ถ้าไม่พบ messages ด้วยวิธีข้างต้น ให้ลองวิธีที่ 2
        if not messages:
            print("ไม่พบข้อความด้วยวิธีที่ 1 กำลังลองวิธีที่ 2...")
            # หา messages จาก conversation data ที่อยู่ใน JSON
            json_pattern = r'<script id="__NEXT_DATA__" type="application\/json">(.*?)<\/script>'
            json_matches = re.findall(json_pattern, response.text, re.DOTALL)
            
            if json_matches:
                try:
                    data = json.loads(json_matches[0])
                    # ลองหา conversation data ในโครงสร้าง JSON
                    # (โครงสร้างอาจแตกต่างกันไปตามรูปแบบการ share ของ ChatGPT)
                    if "props" in data and "pageProps" in data["props"]:
                        page_props = data["props"]["pageProps"]
                        if "conversation" in page_props:
                            conversation = page_props["conversation"]
                            if "mapping" in conversation:
                                for msg_id, msg_data in conversation["mapping"].items():
                                    if "message" in msg_data:
                                        message = msg_data["message"]
                                        if "content" in message and "author" in message:
                                            role = "user" if message["author"]["role"] == "user" else "ChatGPT"
                                            content = ""
                                            for part in message["content"]["parts"]:
                                                content += part
                                            
                                            # ทำความสะอาดเนื้อหา
                                            content = clean_content(content)
                                            
                                            if content.strip():
                                                messages.append({
                                                    "role": role,
                                                    "content": content,
                                                    "timestamp": None
                                                })
                except Exception as json_error:
                    print(f"เกิดข้อผิดพลาดในการแกะข้อมูล JSON: {str(json_error)}")
        
        print(f"ดึงข้อมูลจาก URL สำเร็จ ค้นพบ {len(messages)} ข้อความ")
        return messages
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลด้วย Requests: {str(e)}")
        traceback.print_exc()
        return []

async def extract_formatted_content(page, element):
    """ดึงเนื้อหาแบบคงรูปแบบ รวมโค้ดและตาราง"""
    try:
        # ดึง HTML ของ element
        html_content = await element.inner_html()
        
        # แปลง HTML เป็น text แต่คงรูปแบบโค้ดและตาราง
        formatted_content = await page.evaluate('''(html) => {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = html;
            
            // แปลงโค้ดบล็อก
            const codeBlocks = tempDiv.querySelectorAll('pre code, pre, code');
            codeBlocks.forEach(block => {
                const isBlock = block.tagName === 'PRE' || block.parentElement?.tagName === 'PRE';
                const language = block.className.match(/language-([a-zA-Z0-9]+)/) ?
                    block.className.match(/language-([a-zA-Z0-9]+)/)[1] : '';
                
                if (isBlock) {
                    // โค้ดบล็อก
                    const codeText = block.textContent || block.innerText;
                    block.outerHTML = language ?
                        '\\n```' + language + '\\n' + codeText + '\\n```\\n' :
                        '\\n```\\n' + codeText + '\\n```\\n';
                } else {
                    // โค้ด inline
                    const codeText = block.textContent || block.innerText;
                    block.outerHTML = '`' + codeText + '`';
                }
            });
            
            // แปลงตาราง
            const tables = tempDiv.querySelectorAll('table');
            tables.forEach(table => {
                let markdownTable = '\n';
                const rows = table.querySelectorAll('tr');
                
                rows.forEach((row, rowIndex) => {
                    const cells = row.querySelectorAll('td, th');
                    const cellTexts = Array.from(cells).map(cell => 
                        (cell.textContent || cell.innerText).trim()
                    );
                    markdownTable += '| ' + cellTexts.join(' | ') + ' |\n';
                    
                    // เพิ่ม separator หลังแถวหัว
                    if (rowIndex === 0 && cells.length > 0) {
                        markdownTable += '|' + ' --- |'.repeat(cells.length) + '\n';
                    }
                });
                
                table.outerHTML = markdownTable + '\n';
            });
            
            // แปลงรายการ (lists)
            const lists = tempDiv.querySelectorAll('ul, ol');
            lists.forEach(list => {
                const items = list.querySelectorAll('li');
                let listText = '\n';
                items.forEach((item, index) => {
                    const prefix = list.tagName === 'UL' ? '- ' : `${index + 1}. `;
                    listText += prefix + (item.textContent || item.innerText).trim() + '\n';
                });
                list.outerHTML = listText + '\n';
            });
            
            // แปลงลิงก์
            const links = tempDiv.querySelectorAll('a');
            links.forEach(link => {
                const href = link.getAttribute('href');
                const text = link.textContent || link.innerText;
                if (href && href !== text) {
                    link.outerHTML = `[${text}](${href})`;
                } else {
                    link.outerHTML = text;
                }
            });
            
            // แปลงตัวหนา/เอียง
            const bolds = tempDiv.querySelectorAll('strong, b');
            bolds.forEach(bold => {
                const text = bold.textContent || bold.innerText;
                bold.outerHTML = `**${text}**`;
            });
            
            const italics = tempDiv.querySelectorAll('em, i');
            italics.forEach(italic => {
                const text = italic.textContent || italic.innerText;
                italic.outerHTML = `*${text}*`;
            });
            
            // แปลงหัวข้อ
            const headings = tempDiv.querySelectorAll('h1, h2, h3, h4, h5, h6');
            headings.forEach(heading => {
                const level = parseInt(heading.tagName.substring(1));
                const text = heading.textContent || heading.innerText;
                const hashes = '#'.repeat(level);
                heading.outerHTML = `\n${hashes} ${text}\n`;
            });
            
            return tempDiv.textContent || tempDiv.innerText || '';
        }''', html_content)
        
        return formatted_content.strip()
        
    except Exception as e:
        print(f"Error extracting formatted content: {e}")
        # fallback ไปใช้ inner_text ธรรมดา
        return await element.inner_text()

# ตรวจสอบระบบปฏิบัติการ
is_linux = platform.system() == "Linux"

# ติดตั้ง system dependencies สำหรับ Playwright บน Linux
if is_linux:
    try:
        print("กำลังตรวจสอบและติดตั้ง system dependencies สำหรับ Playwright บน Linux...")
        # ตรวจสอบว่ามีสิทธิ์ sudo หรือไม่
        has_sudo = subprocess.run(
            ["which", "sudo"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        ).returncode == 0
        
        # ทดลองติดตั้ง dependencies กับ playwright install-deps
        if has_sudo:
            try:
                print("ทดลองติดตั้ง system dependencies ด้วย playwright install-deps...")
                subprocess.run(
                    ["sudo", "playwright", "install-deps", "chromium"],
                    check=False
                )
            except Exception as e:
                print(f"ไม่สามารถติดตั้ง dependencies ด้วย playwright install-deps: {str(e)}")
                print("ทดลองติดตั้ง dependencies ด้วย apt-get...")
                # ถ้าไม่สำเร็จให้ใช้ apt-get
                try:
                    subprocess.run([
                        "sudo", "apt-get", "update", "-y"
                    ], check=False)
                    subprocess.run([
                        "sudo", "apt-get", "install", "-y",
                        "libnss3", "libnspr4", "libatk1.0-0", "libatk-bridge2.0-0",
                        "libatspi2.0-0", "libxcomposite1", "libxdamage1"
                    ], check=False)
                except Exception as apt_error:
                    print(f"ไม่สามารถติดตั้ง dependencies ด้วย apt-get: {str(apt_error)}")
        else:
            print("ไม่มีสิทธิ์ sudo สำหรับติดตั้ง system dependencies")
            
        print("เสร็จสิ้นการตรวจสอบ system dependencies")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการติดตั้ง system dependencies: {str(e)}")

# ติดตั้ง Playwright browsers อัตโนมัติ
try:
    from playwright.async_api import async_playwright
    print("ตรวจสอบการติดตั้ง Playwright browsers...")
    # ตรวจสอบว่า Playwright browsers ได้ถูกติดตั้งแล้วหรือไม่
    import tempfile
    with tempfile.NamedTemporaryFile(delete=True) as temp:
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            stdout=temp,
            stderr=temp,
            check=False
        )
        if result.returncode != 0:
            print("กำลังติดตั้ง Playwright browsers...")
            subprocess.run(["playwright", "install", "chromium"], check=True)
            print("ติดตั้ง Playwright browsers เรียบร้อยแล้ว")
        else:
            print("Playwright browsers ได้รับการติดตั้งแล้ว")
except Exception as e:
    print(f"เกิดข้อผิดพลาดในการติดตั้ง Playwright: {str(e)}")
    
CHUNK_SIZE = 10
OUTPUT_FORMAT = "json"  # "json" หรือ "txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def clean_role(role):
    if not role:
        return "unknown"
    role = role.strip().lower()
    if "user" in role:
        return "user"
    if "assistant" in role or "chatgpt" in role:
        return "ChatGPT"
    return role

def clean_emoji(text):
    """ฟังก์ชันลบ emoji และสัญลักษณ์พิเศษออกจากข้อความ แต่เก็บข้อความภาษาไทยและอังกฤษไว้"""
    if not text:
        return text
    
    # ลบ emoji ด้วย regex pattern (รุนแรงน้อยลง)
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U0001f926-\U0001f937"
        u"\U00002640-\u2642" 
        u"\U00002600-\U000027BF"
        u"\u200d"
        u"\ufe0f"  # dingbats
        "]+", flags=re.UNICODE)
    
    # ลบ emoji
    cleaned_text = emoji_pattern.sub(r'', text)
    
    # ลบช่องว่างเกิน แต่เก็บบรรทัดใหม่ไว้
    cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)
    cleaned_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned_text)
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text

def clean_content(content):
    """ทำความสะอาดเนื้อหาข้อความ โดยคงรูปแบบโค้ดและตารางไว้"""
    if not content:
        return content
    
    # แก้ไขปัญหา \r\n ให้เป็น \n ปกติ
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    
    # ลบ emoji
    content = clean_emoji(content)
    
    # เก็บโค้ดบล็อกไว้ก่อน (```...```)
    code_blocks = []
    code_pattern = r'```[\s\S]*?```'
    
    def store_code_block(match):
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks)-1}__"
    
    content = re.sub(code_pattern, store_code_block, content)
    
    # เก็บโค้ดแบบ inline ไว้ก่อน (`...`)
    inline_codes = []
    inline_pattern = r'`[^`\n]+`'
    
    def store_inline_code(match):
        inline_codes.append(match.group(0))
        return f"__INLINE_CODE_{len(inline_codes)-1}__"
    
    content = re.sub(inline_pattern, store_inline_code, content)
    
    # เก็บตารางไว้ก่อน (รูปแบบ Markdown table)
    tables = []
    table_pattern = r'\|[^\n]*\|[\s]*\n\|[-\s:]+\|[\s]*\n(?:\|[^\n]*\|[\s]*\n)+'
    
    def store_table(match):
        tables.append(match.group(0))
        return f"__TABLE_{len(tables)-1}__"
    
    content = re.sub(table_pattern, store_table, content)
    
    # ลบ HTML tags ที่เหลือ (ยกเว้นที่อยู่ในโค้ด)
    content = re.sub(r'<(?!code|pre)[^>]*>', '', content)
    
    # ลบอักขระพิเศษที่ไม่ต้องการ
    content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]', '', content)
    
    # จัดการช่องว่างและบรรทัดใหม่ (ไม่กระทบกับโค้ดและตาราง)
    # ลดบรรทัดว่างเกินแต่คงบรรทัดใหม่ปกติไว้
    content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)  # ลดบรรทัดว่างเกิน
    content = re.sub(r'[ \t]+', ' ', content)  # ลดช่องว่างเกิน แต่ไม่แตะบรรทัดใหม่
    
    # คืนตารางกลับ
    for i, table in enumerate(tables):
        content = content.replace(f"__TABLE_{i}__", table)
    
    # คืนโค้ด inline กลับ
    for i, inline_code in enumerate(inline_codes):
        content = content.replace(f"__INLINE_CODE_{i}__", inline_code)
    
    # คืนโค้ดบล็อกกลับ
    for i, code_block in enumerate(code_blocks):
        content = content.replace(f"__CODE_BLOCK_{i}__", code_block)
    
    content = content.strip()
    
    return content

def chunk_messages(messages, chunk_size):
    chunks = []
    for i in range(0, len(messages), chunk_size):
        chunk = messages[i:i+chunk_size]
        ts = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        conv = [{"role": m["role"], "content": m["content"]} for m in chunk]
        chunks.append({
            "timestamp": ts,
            "conversation": conv
        })
    return chunks

def save_json(chunks, filename="chat_output.json"):
    # แก้ไขการ encode บรรทัดใหม่ก่อนบันทึก
    for chunk in chunks:
        for conv in chunk.get("conversation", []):
            if "content" in conv:
                # แก้ไข \r\n ให้เป็น \n ปกติ
                conv["content"] = conv["content"].replace('\r\n', '\n').replace('\r', '\n')
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    logging.info(f"Saved JSON output: {filename}")

def save_txt(messages, filename="chat_output.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        for m in messages:
            f.write(f"[{m['role']}] {m['content']}\n\n")
    logging.info(f"Saved TXT output: {filename}")

def save_csv(messages, filename="chat_output.csv"):
    df = pd.DataFrame(messages)
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    logging.info(f"Saved CSV output: {filename}")

def save_parquet(messages, filename="chat_output.parquet"):
    df = pd.DataFrame(messages)
    df.to_parquet(filename, index=False)
    logging.info(f"Saved Parquet output: {filename}")

def save_hf_dataset(messages, filename="chat_output_hf"):
    ds = Dataset.from_pandas(pd.DataFrame(messages))
    ds.save_to_disk(filename)
    logging.info(f"Saved Hugging Face Dataset: {filename}")

def save_custom_format(messages, filename="chat_output_custom.json"):
    """บันทึกไฟล์ในรูปแบบ custom ที่มี key 'from' และ 'value'"""
    custom_data = []
    for m in messages:
        role = m["role"].lower()
        if role == "user":
            from_role = "human"
        elif role == "chatgpt":
            from_role = "gpt"
        else:
            from_role = role
        custom_data.append({
            "from": from_role,
            "value": m["content"]
        })
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(custom_data, f, ensure_ascii=False, indent=2)
    logging.info(f"Saved custom format output: {filename}")

def save_grouped_custom_format(messages, filename="chat_output_grouped.json"):
    """บันทึกไฟล์ในรูปแบบ grouped custom ที่มี id, conversations, type, language, source, class"""
    grouped = []
    i = 0
    n = len(messages)
    while i < n:
        conversations = []
        # human
        if i < n and messages[i]["role"].lower() in ("user", "human"):
            conversations.append({
                "from": "human",
                "value": messages[i]["content"]
            })
            i += 1
        # gpt
        if i < n and messages[i]["role"].lower() in ("chatgpt", "gpt", "assistant"):
            conversations.append({
                "from": "gpt",
                "value": messages[i]["content"]
            })
            i += 1
        if conversations:
            grouped.append({
                "id": len(grouped),
                "conversations": conversations,
                "type": "general",
                "language": "en",
                "source": "general_en",
                "class": "major"
            })
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(grouped, f, ensure_ascii=False, indent=4)
    logging.info(f"Saved grouped custom format output: {filename}")

async def extract_chats(url):
    global USE_FALLBACK
    
    if USE_FALLBACK:
        # ใช้ fallback mode ด้วย requests เมื่อ playwright ไม่ทำงาน
        return extract_chats_with_requests(url)
    
    # พยายามใช้ playwright ก่อน
    try:
        async with async_playwright() as p:
            print("กำลังตรวจสอบสภาพแวดล้อม...")
            is_on_spaces = os.environ.get('SPACE_ID') is not None
            is_linux = platform.system() == "Linux"
            print(f"ระบบปฏิบัติการ: {platform.system()}")
            print(f"รันบน Hugging Face Spaces: {'ใช่' if is_on_spaces else 'ไม่ใช่'}")

            # ตรวจสอบ environment variables
            chromium_path = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH')
            if not chromium_path and is_linux:
                chromium_candidates = [
                    "/usr/bin/chromium-browser",
                    "/usr/bin/chromium",
                    shutil.which("chromium-browser"),
                    shutil.which("chromium"),
                ]
                chromium_path = next((p for p in chromium_candidates if p and os.path.exists(p)), None)
            
            print(f"Chromium path ที่พบ: {chromium_path}")            # ตรวจสอบและสร้างไดเรกทอรี cache
            cache_dir = os.path.expanduser("~/.cache/ms-playwright")
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir, exist_ok=True)
                os.chmod(cache_dir, 0o777)

            try:
                # ตรวจสอบ DISPLAY
                display = os.environ.get('DISPLAY')
                if not display and is_linux:
                    print("ไม่พบ DISPLAY environment variable, กำลังตั้งค่าเป็น :0")
                    os.environ['DISPLAY'] = ':0'  # ใช้ :0 แทน :99 เพื่อให้สอดคล้องกับ postBuild

                launch_options = {
                    "headless": True,
                    "args": [
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-gpu',
                        '--disable-software-rasterizer',
                        '--disable-extensions',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding',
                        '--disable-features=TranslateUI',
                        '--disable-ipc-flooding-protection',
                        '--disable-blink-features=AutomationControlled',
                        '--no-first-run',
                        '--no-default-browser-check',
                        '--hide-scrollbars',
                        '--mute-audio',
                        '--headless=new'
                    ]
                }

                if chromium_path:
                    launch_options["executable_path"] = chromium_path
                    print(f"กำลังใช้ Chromium ที่: {chromium_path}")

                print("กำลังเปิด browser...")
                browser = await p.chromium.launch(**launch_options)
                print("เปิด browser สำเร็จ")
            except Exception as e:
                error_msg = str(e)
                print(f"ไม่สามารถเปิด browser: {error_msg}")

                # ตรวจสอบประเภทของข้อผิดพลาด
                common_errors = {
                    "Missing X server": "ไม่พบ X server",
                    "Host system is missing dependencies": "ขาด system dependencies",
                    "Failed to launch browser": "ไม่สามารถเปิด browser",
                    "No usable sandbox": "ปัญหา sandbox",
                    "cannot open display": "ไม่สามารถเปิด display"
                }                
                error_type = next((key for key in common_errors if key in error_msg), None)
                if error_type:
                    print(f"ตรวจพบปัญหา: {common_errors[error_type]}")
                    
                    try:
                        # แก้ไขปัญหาตามประเภทข้อผิดพลาด
                        if "display" in error_msg.lower() or "X server" in error_msg:
                            print("กำลังตั้งค่า virtual display...")
                            subprocess.run(['pkill', '-f', 'Xvfb.*:0'], check=False)
                            time.sleep(1)
                            subprocess.Popen(['Xvfb', ':0', '-screen', '0', '1280x1024x24'])
                            time.sleep(2)
                            os.environ['DISPLAY'] = ':0'
                        
                        if "dependencies" in error_msg:
                            print("กำลังติดตั้ง dependencies เพิ่มเติม...")
                            # ลองติดตั้งด้วยวิธีต่างๆ
                            try:
                                print("Installing dependencies...")
                                
                                # วิธีที่ 1: ใช้ playwright install-deps โดยตรง
                                result1 = subprocess.run(
                                    ["python", "-m", "playwright", "install-deps", "chromium"], 
                                    capture_output=True, text=True, timeout=60
                                )
                                
                                if result1.returncode != 0:
                                    print("Trying to install dependencies with apt-get...")
                                    # วิธีที่ 2: ติดตั้งแพ็กเกจที่จำเป็นโดยตรง
                                    missing_packages = [
                                        "libnss3", "libnspr4", "libatk1.0-0", "libatk-bridge2.0-0",
                                        "libcups2", "libatspi2.0-0", "libxcomposite1", "libxdamage1",
                                        "libgbm1", "libpango-1.0-0", "libcairo-gobject2", "fonts-liberation",
                                        "libx11-xcb1", "libxcb-dri3-0", "libxss1", "libxtst6", "xdg-utils"
                                    ]
                                    
                                    for pkg in missing_packages:
                                        subprocess.run(
                                            ["apt-get", "install", "-y", pkg], 
                                            capture_output=True, text=True, timeout=30
                                        )
                                    
                                    print("Successfully installed missing packages")
                                else:
                                    print("Successfully installed dependencies with playwright")
                                    
                            except subprocess.TimeoutExpired:
                                print("Installation timeout, continuing...")
                            except Exception as install_error:
                                print(f"Error: {str(install_error)}")
                                # ไม่ต้อง raise error เพื่อให้ลองใช้ fallback
                        
                        if "sandbox" in error_msg:
                            print("เพิ่ม arguments สำหรับแก้ปัญหา sandbox...")
                            launch_options["args"].extend([
                                '--disable-gpu-sandbox',
                                '--no-zygote',
                                '--single-process'
                            ])
                        
                        # ลองเปิด browser อีกครั้ง
                        print("ลองเปิด browser อีกครั้ง...")
                        browser = await p.chromium.launch(**launch_options)
                        print("เปิด browser สำเร็จหลังแก้ไขปัญหา")
                    except Exception as retry_error:
                        print(f"ยังไม่สามารถเปิด browser ได้: {str(retry_error)}")
                        print("เปลี่ยนไปใช้ fallback mode...")
                        USE_FALLBACK = True
                        return extract_chats_with_requests(url)
                else:
                    print("เปลี่ยนไปใช้ fallback mode...")
                    USE_FALLBACK = True
                    return extract_chats_with_requests(url)
            
            page = await browser.new_page()
            logging.info(f"Loading share page: {url}")
            await page.goto(url)
            print("กำลังรอให้หน้าเว็บโหลดเสร็จ...")
            
            # รอให้หน้าเว็บโหลดเสร็จและรอข้อมูลบทสนทนา
            try:
                await page.wait_for_selector('[data-message-author-role]', timeout=30000)
                print("พบข้อมูลบทสนทนาแล้ว")
            except:
                print("รอให้หน้าเว็บโหลดข้อมูลเพิ่มเติม...")
                await page.wait_for_timeout(5000)
            
            # ลองหาด้วย selector หลายแบบ
            selectors_to_try = [
                '[data-message-author-role]',
                '[data-testid*="conversation-turn"]',
                '.text-message',
                '[class*="message"]',
                '[role="article"]'
            ]
            
            chat_blocks = []
            for selector in selectors_to_try:
                try:
                    blocks = await page.query_selector_all(selector)
                    if blocks:
                        print(f"พบข้อมูลด้วย selector: {selector} ({len(blocks)} elements)")
                        chat_blocks = blocks
                        break
                except:
                    continue
            
            if not chat_blocks:
                print("ไม่พบข้อมูลบทสนทนาด้วย selector ปกติ กำลังลองวิธีอื่น...")
                # ลองดึงข้อมูลจาก script tags
                script_content = await page.evaluate('''() => {
                    const scripts = document.querySelectorAll('script');
                    for (const script of scripts) {
                        if (script.textContent && script.textContent.includes('conversation')) {
                            return script.textContent;
                        }
                    }
                    return null;
                }''')
                
                if script_content:
                    print("พบข้อมูลใน script tags กำลังแยกข้อมูล...")
                    # ส่งข้อมูลไปให้ fallback function ประมวลผล
                    await browser.close()
                    return extract_chats_with_requests(url)
                else:
                    print("ไม่พบข้อมูลบทสนทนา")
                    await browser.close()
                    return []
            
            print(f"พบ {len(chat_blocks)} elements ที่มีข้อมูลบทสนทนา")
            messages = []
            for block in chat_blocks:
                role = clean_role(await block.get_attribute("data-message-author-role"))
                
                # ดึงข้อมูลแบบรักษารูปแบบ (รวมโค้ดและตาราง)
                content = await extract_formatted_content(page, block)
                
                print(f"ดึงข้อความ: [{role}] {content[:100]}...")  # debug
                
                # ทำความสะอาดเนื้อหา (แต่คงรูปแบบโค้ดและตารางไว้)
                content = clean_content(content)
                
                if not content:
                    print(f"ข้อความว่างหลังทำความสะอาด สำหรับ role: {role}")  # debug
                    continue
                    
                messages.append({
                    "role": role,
                    "content": content,
                    "timestamp": None
                })
                
            print(f"จำนวนข้อความที่ได้หลังกรอง: {len(messages)}")  # debug
            await browser.close()
            logging.info(f"Extracted {len(messages)} messages")
            return messages
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการใช้ Playwright: {str(e)}")
        print("เปลี่ยนไปใช้ fallback mode...")
        USE_FALLBACK = True
        return extract_chats_with_requests(url)

def validate_conversation(messages):
    if not messages:
        logging.warning("No messages found")
        return []
    
    # ทำความสะอาดข้อความและกรองเฉพาะข้อความที่ถูกต้อง
    cleaned = []
    for m in messages:
        if m["role"] in ("user", "ChatGPT"):
            content = clean_content(m["content"])
            if content.strip():
                cleaned.append({
                    "role": m["role"],
                    "content": content,
                    "timestamp": m.get("timestamp")
                })
    
    if not cleaned:
        logging.warning("No valid user/ChatGPT messages after cleaning")
    return cleaned

def preview_data(messages, max_items=3, max_length=150):
    """สร้างตัวอย่างข้อมูลแชทสำหรับแสดงผลในหน้า interface"""
    preview = []
    for msg in messages[:max_items]:
        role = msg["role"]
        content = msg["content"]
        if len(content) > max_length:
            content = content[:max_length] + "..."
        preview.append(f"[{role}] {content}")
    
    if len(messages) > max_items:
        preview.append(f"... และอีก {len(messages) - max_items} ข้อความ")
    
    return "\n\n".join(preview)

async def main(url, export_format=None):
    messages = await extract_chats(url)
    messages = validate_conversation(messages)
    fmt = export_format or OUTPUT_FORMAT
    filename = None
    
    if fmt == "json":
        chunks = chunk_messages(messages, CHUNK_SIZE)
        filename = "chat_output.json"
        save_json(chunks, filename)
    elif fmt == "txt":
        filename = "chat_output.txt"
        save_txt(messages, filename)
    elif fmt == "csv":
        filename = "chat_output.csv"
        save_csv(messages, filename)
    elif fmt == "parquet":
        filename = "chat_output.parquet"
        save_parquet(messages, filename)
    elif fmt == "hf":
        filename = "chat_output_hf"
        save_hf_dataset(messages, filename)
        filename = None  # Folder, not file
    elif fmt == "custom":
        filename = "chat_output_custom.json"
        save_custom_format(messages, filename)
    elif fmt == "grouped":
        filename = "chat_output_grouped.json"
        save_grouped_custom_format(messages, filename)
    else:
        logging.error("Unknown output format")
        
    return filename, messages

def gradio_interface(url, export_format, use_fallback=False):
    global USE_FALLBACK
    USE_FALLBACK = use_fallback
    
    if not url or not url.strip().startswith("http"):
        return "กรุณากรอกลิงก์ ChatGPT Share URL ที่ถูกต้อง", None
    if not export_format:
        return "กรุณาเลือกรูปแบบการส่งออก (Export Format)", None
    
    if use_fallback:
        print("กำลังใช้โหมดสำรอง (fallback mode) ด้วย Requests")
    else:
        print("กำลังใช้โหมดปกติด้วย Playwright")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        filename, messages = loop.run_until_complete(main(url, export_format))
        preview = preview_data(messages)
        result_message = f"ดึงข้อมูลสำเร็จ: {len(messages)} ข้อความ\n\nตัวอย่างข้อมูล:\n{preview}"
        if filename:
            return result_message + f"\n\nบันทึกข้อมูลในรูปแบบ {export_format.upper()} เสร็จสิ้น! ไฟล์ที่บันทึก: {filename}", filename  # Thai: Saved in format ... complete!
        else:
            return result_message + f"\n\nบันทึกข้อมูลในรูปแบบ {export_format.upper()} เสร็จสิ้น!", None
    except Exception as e:
        return f"เกิดข้อผิดพลาด: {str(e)}", None

def sanitize_url(url):
    if url is None:
        return ""
    # ลบ whitespace และ newline characters
    return url.strip()

iface = gr.Interface(
    fn=lambda url, format, use_fallback=False: gradio_interface(sanitize_url(url), format, use_fallback),
    inputs=[
        gr.Textbox(
            label="ลิงก์ ChatGPT Share URL",
            info="กรอกลิงก์ที่ต้องการดึงบทสนทนา เช่น https://chatgpt.com/share/xxxx",
            placeholder="https://chatgpt.com/share/xxxx",
            lines=1
        ),
        gr.Radio(
            choices=["txt", "json", "csv", "parquet", "hf", "custom", "grouped"],
            label="เลือกรูปแบบการส่งออก (Export Format)",
            info="เลือกไฟล์ที่ต้องการบันทึก",
            value="json"
        ),
        gr.Checkbox(
            label="ใช้โหมดสำรอง (ไม่ใช้ Playwright)",
            info="เลือกตัวเลือกนี้หากเกิดปัญหาในการใช้งาน Playwright"
        )
    ],
    outputs=[
        gr.Textbox(label="ผลลัพธ์ (Result)", lines=10),
        gr.File(label="ดาวน์โหลดไฟล์ข้อมูล (Download File)")
    ],
    title="ChatGPT Dumper",
    description="""<div style="text-align: center; margin-bottom: 10px">
                 <h3>Extract and save ChatGPT conversations with code blocks and tables preserved</h3>
                 <div style="display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; margin: 10px 0;">
                      <span class="format-badge"><i class="fas fa-file-alt"></i> TXT</span>
                      <span class="format-badge"><i class="fas fa-file-code"></i> JSON</span>
                      <span class="format-badge"><i class="fas fa-table"></i> CSV</span>
                      <span class="format-badge"><i class="fas fa-database"></i> Parquet</span>
                      <span class="format-badge"><i class="fas fa-brain"></i> HF Dataset</span>
                  </div>
                 <div style="margin: 10px 0; font-size: 14px; color: #666;">
                     <i class="fas fa-check"></i> รองรับโค้ดบล็อก (```code```) | <i class="fas fa-check"></i> รองรับตาราง Markdown | <i class="fas fa-check"></i> รองรับ Unicode ภาษาไทย
                 </div>
                 </div>""",
    article=(
        "<div style='padding: 20px;'>"
        "<h1>ChatGPT Conversation Dumper</h1>"
        "<p>เครื่องมือสำหรับดึงข้อมูลบทสนทนาจาก ChatGPT shared links</p>"
        "<div style='background-color: #d1ecf1; color: #0c5460; padding: 15px; margin: 10px 0; border-radius: 5px; border: 1px solid #bee5eb;'>"
        "<h3 style='color: #0c5460; margin-top: 0;'><i class='fas fa-info-circle'></i> คำแนะนำการแก้ไขปัญหา</h3>"
       "<p>หากเกิดข้อผิดพลาด <code>Host system is missing dependencies</code> ให้ทำดังนี้</p>"
       "<ol style='margin-left: 20px;'>"
       "<li>ลองเลือกตัวเลือก \"ใช้โหมดสำรอง\" เพื่อใช้ระบบสำรองแทน Playwright</li>"
       "<li>ระบบสำรองจะใช้ Requests ในการดึงข้อมูลแทน ซึ่งไม่ต้องการ dependencies เพิ่มเติม</li>"
       "</ol>"
       "</div>"

       "<div style='background-color: #fff3cd; color: #856404; padding: 15px; margin: 10px 0; border-radius: 5px; border: 1px solid #ffeeba;'>"
       "<h3 style='color: #856404; margin-top: 0;'><i class='fas fa-exclamation-triangle'></i> คำเตือนเรื่องทรัพย์สินทางปัญญา</h3>"
       "<p>ระบบนี้เป็นทรัพย์สินทางปัญญา ห้ามคัดลอก แก้ไข หรือนำไปใช้เพื่อการพาณิชย์โดยไม่ได้รับอนุญาต</p>"
       "<ul style='margin-left: 20px;'>"
       "<li><i class='fas fa-ban'></i> ห้ามคัดลอกโค้ด หรือส่วนใดส่วนหนึ่งของระบบ</li>"
       "<li><i class='fas fa-ban'></i> ห้ามแก้ไขหรือดัดแปลง เพื่อสร้างผลงานใหม่</li>"
       "<li><i class='fas fa-ban'></i> ห้ามจำหน่าย หรือแจกจ่ายต่อโดยไม่ได้รับอนุญาต</li>"
       "<li><i class='fas fa-check'></i> อนุญาตให้ใช้งาน เฉพาะเพื่อการทดสอบและเรียนรู้เท่านั้น</li>"
       "</ul>"
       "<p style='margin-bottom: 0;'>สงวนลิขสิทธิ์ © 2025 - All Rights Reserved</p>"
       "<p style='font-style: italic; margin-top: 15px;'>การใช้งานระบบนี้ถือว่าท่านรับทราบและยอมรับเงื่อนไขข้างต้น</p>"
       "</div>"
       "<div style='background-color: #d4edda; color: #155724; padding: 15px; margin: 10px 0; border-radius: 5px; border: 1px solid #c3e6cb;'>"
       "<h3 style='color: #155724; margin-top: 0;'><i class='fas fa-book'></i> วิธีใช้งาน</h3>"
       "<ol style='margin-left: 20px;'>"
       "<li>วางลิงก์ ChatGPT Share ในช่อง URL (เช่น https://chatgpt.com/share/xxxx)</li>"
       "<li>เลือกรูปแบบไฟล์ที่ต้องการดาวน์โหลด</li>"
       "<li>หากเกิดปัญหา ให้เลือกตัวเลือก \"ใช้โหมดสำรอง\"</li>"
       "<li>กดปุ่ม Submit เพื่อดึงข้อมูล</li>"
       "<li>ดาวน์โหลดข้อมูลผ่านปุ่มดาวน์โหลดที่ปรากฏ</li>"
       "</ol>"
       "</div>"
    
       "<div style='background-color: #f8f9fa; color: #495057; padding: 15px; margin: 10px 0; border-radius: 5px; border: 1px solid #dee2e6;'>"
       "<h3 style='color: #495057; margin-top: 0;'><i class='fas fa-wrench'></i> ฟีเจอร์ใหม่: รองรับโค้ดและตาราง</h3>"
       "<p><strong>ระบบตอนนี้รองรับการดึงข้อมูลแบบคงรูปแบบ:</strong></p>"
       "<ul style='margin-left: 20px;'>"
       "<li><i class='fas fa-laptop-code'></i> <strong>โค้ดบล็อก:</strong> รักษารูปแบบ <code>```language</code> และ <code>```</code></li>"
       "<li><i class='fas fa-keyboard'></i> <strong>โค้ด inline:</strong> รักษารูปแบบ <code>`code`</code></li>"
       "<li><i class='fas fa-table'></i> <strong>ตาราง:</strong> แปลงเป็น Markdown table format</li>"
       "<li><i class='fas fa-list'></i> <strong>รายการ:</strong> รักษารูปแบบ bullet points และ numbered lists</li>"
       "<li><i class='fas fa-link'></i> <strong>ลิงก์:</strong> รักษารูปแบบ <code>[text](url)</code></li>"
       "<li><i class='fas fa-star'></i> <strong>ตัวหนา/เอียง:</strong> รักษารูปแบบ <code>**bold**</code> และ <code>*italic*</code></li>"
       "</ul>"
       "<p style='margin-bottom: 0;'><em>เหมาะสำหรับการบันทึกบทสนทนาที่มีโค้ดและข้อมูลเชิงเทคนิค</em></p>"
       "</div>"
       "</div>"),
    theme=gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="orange",
        font=[gr.themes.GoogleFont("Sarabun"), "ui-sans-serif", "system-ui", "sans-serif"]
    ),
    css="""
    .format-badge {
        background-color: #f8f9fa;
        padding: 5px 10px;
        border-radius: 15px;
        font-weight: 500;
        border: 1px solid #dee2e6;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .gradio-container {
        max-width: 850px !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    """
)

def cleanup():
    """ฟังก์ชันทำความสะอาดก่อนปิดแอป"""
    global xvfb_process
    if xvfb_process is not None:
        try:
            # ส่งสัญญาณ SIGTERM ให้ Xvfb
            xvfb_process.terminate()
            # รอให้ process ปิดตัวเอง
            xvfb_process.wait(timeout=5)
        except:
            # ถ้ารอนานเกินไป ให้บังคับปิด
            try:
                xvfb_process.kill()
            except:
                pass
        finally:
            xvfb_process = None
    
    # ลบไฟล์ lock ของ X11 ถ้ามี
    try:
        lock_file = '/tmp/.X99-lock'
        if os.path.exists(lock_file):
            os.remove(lock_file)
    except:
        pass

if __name__ == "__main__":
    def run_app():        
        if is_on_spaces:
            # บน Hugging Face Spaces
            try:
                # ตรวจสอบ Xvfb
                if subprocess.run(['which', 'Xvfb'], capture_output=True).returncode == 0:
                    print("Found Xvfb installation")
                    # ตรวจสอบว่า display :0 ทำงานอยู่หรือไม่
                    display_check = subprocess.run(['pgrep', '-f', 'Xvfb.*:0'], capture_output=True)
                    if display_check.returncode == 0:
                        print("Xvfb is already running on display :0")
                        os.environ['DISPLAY'] = ':0'
                    else:
                        print("Starting Xvfb on display :0")
                        # เริ่ม Xvfb บน display :0
                        subprocess.Popen(['Xvfb', ':0', '-screen', '0', '1280x1024x24', '-ac', '+extension', 'RANDR', '+render', '-noreset'], 
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        time.sleep(2)
                        os.environ['DISPLAY'] = ':0'
                else:
                    print("Xvfb not found, Playwright may not work correctly")
            except Exception as e:
                print(f"Error setting up Xvfb: {str(e)}")

            # Launch Gradio interface
            iface.launch(
                server_name="0.0.0.0",
                server_port=7860,
                share=False,
                ssl_verify=False
            )
        else:
            # บนเครื่องโลคอล
            iface.launch(share=True)
    
    # ลงทะเบียนฟังก์ชัน cleanup สำหรับการปิดแอปอย่างถูกต้อง
    import atexit
    atexit.register(cleanup)
    
    try:
        # ดักจับ SIGTERM signal
        signal.signal(signal.SIGTERM, lambda *args: (cleanup(), sys.exit(0)))
        run_app()
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        cleanup()
    except Exception as e:
        print(f"Error running app: {str(e)}")
        cleanup()
        sys.exit(1)
    
    if len(sys.argv) > 1 and sys.argv[1] == "install-deps":
        # รันสคริปต์ติดตั้ง dependencies
        try:
            import install_deps
            print("ติดตั้ง dependencies เสร็จสิ้น")
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการติดตั้ง dependencies: {str(e)}")
    elif len(sys.argv) > 1 and sys.argv[1] == "web":
        # รันในโหมด web ด้วย share=True
        iface.launch(share=True)
    else:
        # รันแอพตามปกติ
        run_app()
