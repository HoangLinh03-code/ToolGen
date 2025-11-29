
import json
import os
import sys
import threading
import time
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
from typing import Dict, List, Optional, Any
import zipfile
import subprocess
import re
from tempfile import NamedTemporaryFile
from docx.oxml import parse_xml
import traceback

_FILE_LOCK = threading.RLock()
_OUTPUT_DIR_LOCK = threading.RLock()

def get_app_path():
    """Lấy đường dẫn chứa file .exe hoặc script"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def latex_to_omml_via_pandoc(latex_math_dollar):
    """Chuyển đổi LaTeX sang OMML qua Pandoc"""
    try:
        with NamedTemporaryFile(suffix=".docx", delete=False) as temp_docx:
            temp_docx.close()
            # Cờ ẩn cửa sổ console đen khi gọi subprocess
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                ['pandoc', '--from=latex', '--to=docx', '-o', temp_docx.name],
                input=latex_math_dollar,
                text=True,
                capture_output=True,
                encoding='utf-8',
                creationflags=creation_flags
            )
 
            if result.returncode != 0:
                # print(f"⚠️ Pandoc error: {result.stderr}")
                # return None
                if os.path.exists(temp_docx.name): os.unlink(temp_docx.name)
                return None
            xml_content = ""
            with zipfile.ZipFile(temp_docx.name, 'r') as z:
                xml_content = z.read('word/document.xml').decode('utf-8')
            
            if os.path.exists(temp_docx.name):
                os.unlink(temp_docx.name)
       
        match = re.search(r'(<m:oMath[^>]*>.*?</m:oMath>)', xml_content, re.DOTALL)
        return match.group(1) if match else None
   
    except FileNotFoundError:
        print("❌ LỖI: Không tìm thấy 'pandoc.exe'. Hãy đảm bảo file này nằm cùng thư mục với phần mềm.")
        return None
    except Exception as e:
        print(f"Lỗi latex_to_omml: {e}")
        return None

def insert_equation_into_paragraph(latex_math_dollar, paragraph):
    """Chèn công thức toán học vào paragraph"""
    omml_str = latex_to_omml_via_pandoc(latex_math_dollar)
   
    if not omml_str:
        paragraph.add_run(f" [{latex_math_dollar}] ")
        return
   
    if 'xmlns:m=' not in omml_str:
        omml_str = re.sub(
            r'<m:oMath',
            r'<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"',
            omml_str,
            count=1
        )
   
    try:
        omml_element = parse_xml(omml_str)
        run = paragraph.add_run()
        run._r.append(omml_element)
    except Exception as e:
        print(f"Lỗi chèn equation: {e}")
        paragraph.add_run(f" [{latex_math_dollar}] ")

def clean_latex_math(latex_raw):
    """Làm sạch và chuẩn hóa LaTeX"""
    latex_raw = re.sub(r'\\/', '', latex_raw)
    latex_raw = re.sub(r'\\operatorname\s*{\s*([^}]*)\s*}',
                       lambda m: m.group(1).replace(' ', ''), latex_raw)
    latex_raw = re.sub(r'\\root\s*(\d+)\s*{([^}]*)}', r'\\sqrt[\1]{\2}', latex_raw)
    latex_raw = re.sub(r'\\root\s*{(\d+)}\s*\\of\s*{([^}]*)}', r'\\sqrt[\1]{\2}', latex_raw)
    latex_raw = re.sub(r'\\root\s*(\d+)\s*\\sqrt\s*{([^}]*)}', r'\\sqrt[\1]{\2}', latex_raw)
    latex_raw = re.sub(r'([a-zA-Z])\s*\\frac\s*{([^}]+)}\s*{([^}]+)}',
                       r'\1^{\\frac{\2}{\3}}', latex_raw)
    latex_raw = re.sub(r'\\sp\s*{([^}]*)}', r'^{\1}', latex_raw)
    latex_raw = re.sub(r'{\\bf\s*([^}]*)}', r'\1', latex_raw)
    latex_raw = re.sub(r'\\\s*log', r'\\log', latex_raw)
    latex_raw = re.sub(r'\\bigskip', '', latex_raw)
    latex_raw = re.sub(r'\\nonumber', '', latex_raw)
    latex_raw = latex_raw.replace(r'\?', '?')
    latex_raw = re.sub(r'\\cdot\s*(?=\w)', r'\\cdot ', latex_raw)
    latex_raw = latex_raw.replace(r'\dotstan', r'\cdot \tan')
    latex_raw = re.sub(r'(?<!\\)(\bln\b|\blog\b|\bsin\b|\bcos\b|\btan\b|\blog_{?\d*}?)',
                       r'\\\1', latex_raw)
    latex_raw = re.sub(r'(\\Leftrightarrow|\\Rightarrow|\\rightarrow)(?=\w)', r'\1 ', latex_raw)
    latex_raw = latex_raw.replace(r'\\n', r'\n')
   
    latex_raw = latex_raw.strip()
    latex_raw = latex_raw.replace('\n', ' ').replace('\r', '')
    if not (latex_raw.startswith('$') and latex_raw.endswith('$')):
        latex_raw = f"${latex_raw}$"
   
    return latex_raw

def process_text_with_latex(text, paragraph, bold=False):
    """Xử lý text có công thức LaTeX với fallback an toàn"""
    if not text:
        return
    
    # 🔍 DEBUG: In ra text trước khi xử lý
    # print(f"🔍 Processing text: {text[:100]}...")
    text = repair_broken_latex(text)
    text = text.replace("<br>", "\n").replace("<br/>", "\n") \
               .replace("<Br>", "\n").replace("<Br/>", "\n")
    text = re.sub(r'</?(div|p|u|span|font|i|b)\b[^>]*>', '', text)
    text = text.replace("&nbsp;", "").replace("&lt;", "").replace("&gt;", "")
   
    pattern = r'(\$[^$]+\$|\\\[.*?\\\])'
    parts = re.split(pattern, text)
    
    # 🔍 DEBUG: In ra các parts
    # print(f"🔍 Split into {len(parts)} parts")
    # for i, part in enumerate(parts):
    #     if part and (part.startswith('$') or part.startswith('\\[')):
    #         print(f"   Part {i}: LATEX -> {part[:50]}")
    #     elif part:
    #         print(f"   Part {i}: TEXT -> {part[:50]}")
   
    for part in parts:
        if not part:
            continue
       
        if part.startswith('$') or part.startswith('\\['):
            try:
                latex_expr = clean_latex_math(part)
                # print(f"✅ Inserting equation: {latex_expr}")
                insert_equation_into_paragraph(latex_expr, paragraph)
            except Exception as e:
                print(f"Lỗi xử lý LaTeX: {e}")
                run = paragraph.add_run(part)
                if bold:
                    run.bold = True
        else:
            cleaned_part = re.sub(r'^\s*/', '', part)
            run = paragraph.add_run(cleaned_part)
            if bold:
                run.bold = True

def ensure_output_folder_for_batch(batch_name):
    """Tạo folder riêng cho batch"""
    base_path = get_app_path()
    output_base = os.path.join(base_path, "output")
    batch_folder = os.path.join(output_base, batch_name)
    
    with _OUTPUT_DIR_LOCK:
        os.makedirs(output_base, exist_ok=True)
        os.makedirs(batch_folder, exist_ok=True)
    
    return batch_folder

def save_document_securely(doc, batch_name, file_name):
    """Lưu file DOCX với thread-safety"""
    batch_folder = ensure_output_folder_for_batch(batch_name)
    if not batch_folder:
        return None

    output_path = os.path.join(batch_folder, f"{file_name}.docx")
    
    with _FILE_LOCK:
        max_retries = 3
        for retry_count in range(max_retries):
            try:
                doc.save(output_path)
                if os.path.exists(output_path):
                    file_size = os.path.getsize(output_path)
                    print(f"✅ Đã lưu file: {output_path} ({file_size} bytes)")
                    return output_path
            except Exception as e:
                print(f"⚠️ Lỗi lưu file lần {retry_count + 1}: {e}")
                if retry_count < max_retries - 1:
                    time.sleep(0.5)
        
        print(f"❌ Không thể lưu file sau {max_retries} lần thử")
        return None

def clean_json_string(text: str) -> str:
    """Làm sạch chuỗi JSON"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def repair_json_with_ai(broken_json_str: str, client) -> str:
    """Gửi JSON lỗi cho AI sửa"""
    print("⚠️ JSON lỗi. Đang yêu cầu AI sửa...")
    prompt_fix = f"""
Đoạn JSON sau bị lỗi cú pháp:

{broken_json_str}

NHIỆM VỤ:
1. Sửa lỗi cú pháp JSON (escape quotes, thêm phẩy, đóng ngoặc)
2. KHÔNG thay đổi nội dung Tiếng Việt
3. CHỈ TRẢ VỀ JSON ĐÃ SỬA (không markdown)
    """
    repaired_text = client.send_data_to_check(prompt_fix)
    return clean_json_string(repaired_text)
def sanitize_latex_json(text: str) -> str:
    pattern = r'(?<!\\)\\(?![\\"/bfnrtu])'

    return re.sub(pattern, r'\\\\', text)

def parse_json_safely(json_str: str, client) -> Optional[Dict]:
    """Parse JSON an toàn với Sanitization và Retry AI"""
    # 1. Clean markdown
    cleaned_str = clean_json_string(json_str)
    
    # 2. Bước quan trọng: Sanitize LaTeX backslashes bằng thuật toán (nhanh và chính xác hơn AI)
    sanitized_str = sanitize_latex_json(cleaned_str)
    
    # Thử parse lần 1 (với chuỗi đã sanitize)
    try:
        return json.loads(sanitized_str, strict=False)
    except json.JSONDecodeError as e:
        print(f"❌ Lỗi JSON lần 1 (Logic): {e}")
        # Debug: In ra đoạn lỗi để kiểm tra nếu cần
        start = max(0, e.pos - 20)
        end = min(len(sanitized_str), e.pos + 20)
        print(f"Context: ...{sanitized_str[start:end]}...")
    
    # Thử sửa bằng AI (Fallback cuối cùng)
    try:
        # Lưu ý: Gửi chuỗi gốc (cleaned_str) hoặc chuỗi đã sanitize tùy chiến lược. 
        # Thường gửi chuỗi gốc để AI tự định dạng lại từ đầu sẽ an toàn hơn về ngữ nghĩa.
        repaired_str = repair_json_with_ai(cleaned_str, client)
        
        # Sau khi AI sửa, vẫn nên sanitize lại một lần nữa để chắc chắn
        repaired_str = sanitize_latex_json(repaired_str)
        
        return json.loads(repaired_str, strict=False)
    except json.JSONDecodeError as e:
        print(f"❌ Lỗi JSON lần 2 (AI Give up): {e}")
        return None
def generate_or_get_image(hinh_anh_data: Dict) -> tuple:
    """
    Xử lý gọi hàm sinh ảnh.
    Returns: (image_bytes, placeholder_text) - image_bytes là 1 object duy nhất
    """
    mo_ta = hinh_anh_data.get("mo_ta", hinh_anh_data.get("description", ""))
    mo_ta = str(mo_ta).strip()
    loai = hinh_anh_data.get("loai", "tu_mo_ta")
    
    if loai == "tu_mo_ta" and mo_ta:
        try:
            from process.text2Image import generate_image_from_text
            # Hàm này trả về 1 bytes object (hoặc None)
            image_bytes = generate_image_from_text(mo_ta)
            if image_bytes:
                return image_bytes, None
            else:
                # Nếu API trả về None (do lỗi mạng hoặc quota)
                return None, f"⚠️ [Lỗi sinh ảnh] Server không trả về ảnh cho mô tả: {mo_ta}"
        except Exception as e:
            print(f"❌ Lỗi sinh ảnh: {e}")
            return None, f"⚠️ [Lỗi Code] {str(e)}"
    
    placeholder = f"🖼️ [Cần chèn hình: {mo_ta}]"
    return None, placeholder

def insert_image_or_placeholder(doc: Document, hinh_anh_data: Dict):
    """Chèn ảnh hoặc placeholder vào document"""
    image_bytes, placeholder = generate_or_get_image(hinh_anh_data)
    
    if image_bytes:
        try:
            image_stream = BytesIO(image_bytes)
            doc.add_picture(image_stream, width=Inches(4))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception as e:
            print(f"❌ Lỗi chèn ảnh: {e}")
            p = doc.add_paragraph()
            run = p.add_run(f"⚠️ [Lỗi chèn ảnh: {str(e)}]")
            run.font.color.rgb = RGBColor(255, 0, 0)
            run.italic = True
    
    elif placeholder:
        p = doc.add_paragraph()
        run = p.add_run(placeholder)
        run.font.color.rgb = RGBColor(200, 0, 0)
        run.italic = True
        run.bold = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    return doc

class PromptBuilder:
    """
    Builder tạo prompt động dựa trên cấu hình
    Cho phép thay đổi prompt mà không sửa code
    """
    
    @staticmethod
    def build_json_structure_hint(question_type: str) -> str:
        """
        Tạo hint cấu trúc JSON dựa trên loại đề
        Đây là phần duy nhất cần thay đổi khi muốn format mới
        """
        if question_type == "trac_nghiem_4_dap_an":
            return """
{
  "loai_de": "trac_nghiem_4_dap_an",
  "tong_so_cau": 80,
  "cau_hoi": [
    {
      "stt": 1,
      "muc_do": "nhan_biet",
      "phan": "Phần I",
      "noi_dung": "Nội dung câu hỏi...",
      "hinh_anh": {
        "co_hinh": true,
        "loai": "tu_mo_ta",
        "mo_ta": "Mô tả để sinh ảnh..."
      },
      "dap_an": [
        {"ky_hieu": "A", "noi_dung": "Đáp án A"},
        {"ky_hieu": "B", "noi_dung": "Đáp án B"},
        {"ky_hieu": "C", "noi_dung": "Đáp án C"},
        {"ky_hieu": "D", "noi_dung": "Đáp án D"}
      ],
      "dap_an_dung": 2,
      "giai_thich": "Giải thích chi tiết..."
    }
  ]
}
"""
        
        elif question_type == "dung_sai":
            return """
{
  "loai_de": "dung_sai",
  "tong_so_cau": 40,
  "cau_hoi": [
    {
      "stt": 1,
      "muc_do": "thong_hieu",
      "phan": "Phần I",
      "doan_thong_tin": "Nội dung...",
      "hinh_anh": { "co_hinh": true, "loai": "tu_mo_ta", "mo_ta": "Mô tả để sinh ảnh..." },
      "cac_y": [
        {"ky_hieu": "a", "noi_dung": "Phát biểu a", "dung": false},
        {"ky_hieu": "b", "noi_dung": "Phát biểu b", "dung": true},
        {"ky_hieu": "c", "noi_dung": "Phát biểu c", "dung": false},
        {"ky_hieu": "d", "noi_dung": "Phát biểu d", "dung": true}
      ],
      "dap_an_dung_sai": "0101",
      "giai_thich": [
        {"y": "a", "noi_dung_y": "...", "ket_luan": "SAI", "giai_thich": "BẮT BUỘC GIẢI THÍCH CHI TIẾT TẠI ĐÂY"},
        {"y": "b", "noi_dung_y": "...", "ket_luan": "ĐÚNG", "giai_thich": "BẮT BUỘC GIẢI THÍCH CHI TIẾT TẠI ĐÂY"},
        {"y": "c", "noi_dung_y": "...", "ket_luan": "SAI", "giai_thich": "BẮT BUỘC GIẢI THÍCH CHI TIẾT TẠI ĐÂY"},
        {"y": "d", "noi_dung_y": "...", "ket_luan": "ĐÚNG", "giai_thich": "BẮT BUỘC GIẢI THÍCH CHI TIẾT TẠI ĐÂY"}
      ]
    }
  ]
}
"""
        elif question_type == "tra_loi_ngan":
            return """
{
  "loai_de": "tra_loi_ngan",
  "tong_so_cau": 30,
  "cau_hoi": [
    {
      "stt": 1,
      "muc_do": "nhan_biet",
      "phan": "Phần I",
      "noi_dung": "Nội dung câu hỏi...",
      "hinh_anh": {
        "co_hinh": true,
        "loai": "tu_mo_ta",
        "mo_ta": "Mô tả để sinh ảnh..."
      },
      "dap_an": "đáp án ngắn gọn",
      "giai_thich": "Giải thích chi tiết 80-120 từ về cách tính toán/suy luận để có đáp án..."
    }
  ]
}
"""
        
        return "{}"
    
    @staticmethod
    def wrap_user_prompt(user_prompt: str, question_type: str) -> str:
        json_hint = PromptBuilder.build_json_structure_hint(question_type)
        
        # PROMPT MỚI: Ngắn gọn, súc tích, tập trung vào JSON và $
        return f"""{user_prompt}

----------------
### YÊU CẦU NGHIÊM NGẶT VỀ DỮ LIỆU (BẮT BUỘC TUÂN THỦ 100%):
- Mọi trường trong câu hỏi và đáp án PHẢI có dữ liệu.
- Nếu đáp án là hình ảnh hoặc ký hiệu, hãy mô tả nó bằng lời (Ví dụ: "Hình vẽ tam giác", "Ký hiệu Rỗng").

1. **FORMAT JSON**: 
   - Trả về DUY NHẤT một chuỗi JSON hợp lệ.
   - Không thêm markdown (```json), không thêm lời dẫn.
   - Không được để trường dữ liệu bị `null` hoặc bỏ trống.

2. **QUY TẮC SỬ DỤNG LaTeX ($) - HÃY LINH HOẠT:**
   - **KHOA HỌC TỰ NHIÊN:** + BẮT BUỘC dùng dấu `$` bao quanh các công thức, phương trình, ký hiệu biến số, phản ứng hóa học.
     + Ví dụ: "Hàm số $y = x^2 + 2x + 1$", "Chất $H_2SO_4$ đặc", "Gia tốc $a = 2 m/s^2$".
     + Phân số dùng: $\\frac{{tu}}{{mau}}$.
   
   - **KHOA HỌC XÃ HỘI:**
     + VIẾT VĂN BẢN BÌNH THƯỜNG.
     + KHÔNG dùng `$` cho các con số thông thường, ngày tháng năm, hoặc danh từ riêng.
     + Ví dụ ĐÚNG: "Ngày 2/9/1945", "Dân số là 90 triệu người".
     + Ví dụ SAI (Cấm): "$Ngày 2/9/1945$", "$90 triệu$".

3. **HÌNH ẢNH MINH HỌA (QUAN TRỌNG - BẮT BUỘC CHECK)**:
   - Tư duy: "Nội dung này có cần hình minh họa để học sinh hiểu rõ hơn không?"
   - Áp dụng cho **MỌI LĨNH VỰC** (Khoa học Tự nhiên & Xã hội):
     + **Toán/Lý/Hóa**: Nếu có hình học, đồ thị, mạch điện, thí nghiệm, cấu trúc phân tử... -> BẮT BUỘC điền mô tả vào `"mo_ta"`.
     + **Sử/Địa/Văn**: Nếu có lược đồ trận đánh, bản đồ địa lý, biểu đồ dân số, di tích lịch sử, chân dung nhân vật... -> BẮT BUỘC điền mô tả vào `"mo_ta"`.
   - **Cách viết mô tả ("mo_ta")**:
     + Viết chi tiết để công cụ vẽ tranh (AI) có thể tái tạo lại được.
     + Ví dụ Toán: "Tam giác ABC vuông tại A, đường cao AH..."
     + Ví dụ Sử: "Lược đồ trận Điện Biên Phủ, các mũi tên tấn công từ vây quanh lòng chảo..."
     + Ví dụ Địa: "Bản đồ hình chữ S của Việt Nam, đánh dấu vị trí thủ đô Hà Nội..."

### MẪU JSON:
{json_hint}
"""



# ============================================================================
# PHẦN 5: DYNAMIC DOCX RENDERER (MỚI - AUTO-ADAPT)
# ============================================================================

class DynamicDocxRenderer:
    """
    Renderer tự động thích ứng với cấu trúc JSON
    KHÔNG hard-code logic render
    """
    
    def __init__(self, doc: Document):
        self.doc = doc
    
    def render_title(self, data: Dict):
        """Render tiêu đề tự động"""
        loai_de = data.get("loai_de", "").upper()
        title = self.doc.add_heading(f'ĐỀ {loai_de}', level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    def auto_group_questions(self, data: Dict) -> Dict[str, List]:
        """
        Tự động nhóm câu hỏi và CHUẨN HÓA key muc_do từ Tiếng Việt sang code.
        Giúp người dùng thoải mái viết prompt "Vận dụng", "Nhận biết"... mà không bị lỗi file trắng.
        """
        grouped = {}
        for cau in data.get("cau_hoi", []):
            # 1. Lấy dữ liệu thô từ AI (ví dụ: "Vận dụng", "Nhận biết", "Thông hiểu")
            # Chuyển về chữ thường để dễ so sánh
            raw_muc_do = str(cau.get("muc_do", "unknown")).lower().strip()
            
            # 2. Logic "Phiên dịch" thông minh (Mapping)
            # Ưu tiên check "cao" trước để phân biệt "Vận dụng" và "Vận dụng cao"
            if "cao" in raw_muc_do:
                muc_do_chuan = "van_dung_cao"
            elif "dụng" in raw_muc_do or "dung" in raw_muc_do:
                muc_do_chuan = "van_dung"
            elif "thông" in raw_muc_do or "thong" in raw_muc_do:
                muc_do_chuan = "thong_hieu"
            elif "nhận" in raw_muc_do or "nhan" in raw_muc_do:
                muc_do_chuan = "nhan_biet"
            else:
                # Trường hợp AI ghi nội dung lạ, mặc định đưa vào Vận dụng 
                # để đảm bảo câu hỏi vẫn hiện ra trong file (tránh lỗi trang trắng)
                muc_do_chuan = "van_dung" 
            
            # 3. Gom nhóm theo key chuẩn
            if muc_do_chuan not in grouped:
                grouped[muc_do_chuan] = []
            grouped[muc_do_chuan].append(cau)
        
        # Sắp xếp theo STT trong mỗi nhóm
        for key in grouped:
            grouped[key].sort(key=lambda x: x.get("stt", 0))
        
        return grouped
    
    def get_section_title(self, muc_do: str) -> str:
        """
        Tạo tiêu đề section dựa trên mức độ
        CÓ THỂ mở rộng bằng config file
        """
        mapping = {
            "nhan_biet": "I. CÂU HỎI NHẬN BIẾT",
            "thong_hieu": "II. CÂU HỎI THÔNG HIỂU",
            "van_dung": "III. CÂU HỎI VẬN DỤNG",
            "van_dung_cao": "IV. CÂU HỎI VẬN DỤNG CAO"
        }
        return mapping.get(muc_do, muc_do.upper())
    
    def render_question_trac_nghiem(self, cau: Dict):
        """Render câu hỏi trắc nghiệm 4 đáp án"""
        # Câu hỏi
        p = self.doc.add_paragraph()
        p.add_run(f"Câu {cau['stt']}: ").bold = True
        process_text_with_latex(cau['noi_dung'], p)
        
        # Hình ảnh
        hinh_anh = cau.get("hinh_anh", {})
        if hinh_anh.get("co_hinh"):
            insert_image_or_placeholder(self.doc, hinh_anh)
        
        # Đáp án - THÊM XỬ LÝ LATEX
        for dap_an in cau.get("dap_an", []):
            p_da = self.doc.add_paragraph()
            run_ky_hieu = p_da.add_run(f"{dap_an['ky_hieu']}. ")
            process_text_with_latex(dap_an['noi_dung'], p_da) 
        
        # Lời giải
        p_lg = self.doc.add_paragraph()
        p_lg.add_run("Lời giải:").bold = True
        
        if "dap_an_dung" in cau:
            p_dung = self.doc.add_paragraph()
            p_dung.add_run(f"{cau['dap_an_dung']}").bold = True
            self.doc.add_paragraph("####")
        
        # Giải thích - THÊM XỬ LÝ LATEX
        giai_thich = cau.get("giai_thich", "")
        for line in giai_thich.split("\n"):
            if line.strip():
                p_gt = self.doc.add_paragraph()
                process_text_with_latex(line.strip(), p_gt)  
        
        # Kết luận - THÊM XỬ LÝ LATEX
        if "dap_an_dung" in cau:
            dap_an_num = cau['dap_an_dung']
            noi_dung_dap_an = cau['dap_an'][dap_an_num-1]['noi_dung']
            p_ket_luan = self.doc.add_paragraph()
            run = p_ket_luan.add_run("Vậy đáp án đúng là: ")
            run.bold = True
            process_text_with_latex(noi_dung_dap_an, p_ket_luan, bold=True) 
    
    def render_question_dung_sai(self, cau: Dict):
        """Render câu hỏi đúng/sai"""
        # Số câu
        p = self.doc.add_paragraph()
        p.add_run(f"Câu {cau['stt']}:").bold = True
        
        # Đoạn thông tin - THÊM XỬ LÝ LATEX
        if cau.get("doan_thong_tin"):
            p_doan = self.doc.add_paragraph()
            process_text_with_latex(cau.get("doan_thong_tin", ""), p_doan)  
        
        # Hình ảnh
        hinh_anh = cau.get("hinh_anh", {})
        if hinh_anh.get("co_hinh"):
            insert_image_or_placeholder(self.doc, hinh_anh)
        
        # Các ý a, b, c, d - THÊM XỬ LÝ LATEX
        for y in cau.get("cac_y", []):
            p_y = self.doc.add_paragraph()
            p_y.add_run(f"{y['ky_hieu']}) ")
            process_text_with_latex(y['noi_dung'], p_y)  
        
        # Lời giải
        p_lg = self.doc.add_paragraph()
        p_lg.add_run("Lời giải:").bold = True
        
        p_da = self.doc.add_paragraph()
        p_da.add_run(cau.get("dap_an_dung_sai", "")).bold = True
        self.doc.add_paragraph("####")
        
        # Giải thích từng ý - THÊM XỬ LÝ LATEX
        for gt in cau.get("giai_thich", []):
            p_gt = self.doc.add_paragraph()
            p_gt.add_run("- ")
            process_text_with_latex(gt.get('noi_dung_y', ''), p_gt)  
            run_kl = p_gt.add_run(f" - {gt.get('ket_luan', 'SAI')}.")
            run_kl.bold = True
            
            if gt.get('giai_thich'):
                p_gt_detail = self.doc.add_paragraph()
                process_text_with_latex(gt.get('giai_thich', ''), p_gt_detail)  
    
    def render_question_tra_loi_ngan(self, cau: Dict):
        """Render câu hỏi trả lời ngắn"""
        # Câu hỏi
        p = self.doc.add_paragraph()
        p.add_run(f"Câu {cau['stt']}: ").bold = True
        process_text_with_latex(cau['noi_dung'], p)  
        
        # Hình ảnh (nếu có)
        hinh_anh = cau.get("hinh_anh", {})
        if hinh_anh.get("co_hinh"):
            insert_image_or_placeholder(self.doc, hinh_anh)
        
        # Đáp án - THÊM XỬ LÝ LATEX
        p_da = self.doc.add_paragraph()
        run_label = p_da.add_run("Đáp án: ")
        run_label.bold = True
        
        raw_ans = str(cau.get('dap_an', '')).strip()
        if raw_ans.startswith("[[") and raw_ans.endswith("]]"):
            final_ans = raw_ans
        else:
            final_ans = f"[[{raw_ans}]]"
        
        # XỬ LÝ LATEX TRONG ĐÁP ÁN
        process_text_with_latex(final_ans, p_da, bold=True)  
        
        # Lời giải header
        p_lg = self.doc.add_paragraph()
        p_lg.add_run("Lời giải").bold = True
        self.doc.add_paragraph("####")
        
        # Giải thích chi tiết - ĐÃ CÓ XỬ LÝ LATEX
        giai_thich = cau.get("giai_thich", "")
        lines = giai_thich.replace('\\n', '\n').split('\n')
        
        for line in lines:
            text = line.strip()
            if not text or text == "####":
                continue
            
            is_bold = False
            if text.startswith("**") and text.endswith("**"):
                text = text[2:-2]
                is_bold = True
            
            check_text = text.replace('*', '').strip().lower()
            if check_text.startswith("vậy"):
                is_bold = True
                text = text.replace('**', '')

            p_gt = self.doc.add_paragraph()
            process_text_with_latex(text, p_gt, bold=is_bold)  
    
    def render_all(self, data: Dict):
        """
        Main render function - Có hỗ trợ chia PHẦN (PART) bên trong Mức độ
        """
        self.render_title(data)
        
        # 1. Auto-group theo mức độ (Nhận biết, Thông hiểu...)
        grouped = self.auto_group_questions(data)
        
        # 2. Detect loại đề
        loai_de = data.get("loai_de", "")
        
        # 3. Render từng nhóm MỨC ĐỘ
        # Thứ tự ưu tiên render
        order_muc_do = ["nhan_biet", "thong_hieu", "van_dung", "van_dung_cao"]
        
        for muc_do in order_muc_do:
            if muc_do not in grouped:
                continue
            
            # Lấy danh sách câu hỏi trong mức độ này
            questions = grouped[muc_do]
            if not questions:
                continue
            section_title = self.get_section_title(muc_do)
            self.doc.add_heading(section_title, level=2)
            current_phan = None

            for cau in questions:
                # Lấy tên phần của câu hiện tại
                phan_cua_cau = str(cau.get("phan", "")).strip()
                
                # Nếu câu này thuộc một phần mới -> In Header Phần
                if phan_cua_cau and phan_cua_cau != current_phan:
                    # In ra header cấp 3 (VD: Phần 1: Đội ngũ...)
                    # Dùng màu hoặc in đậm để phân biệt
                    p_phan = self.doc.add_heading(phan_cua_cau.upper(), level=3)
                    p_phan.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    current_phan = phan_cua_cau
                
                # Render nội dung câu hỏi như bình thường
                if loai_de == "dung_sai":
                    self.render_question_dung_sai(cau)
                elif loai_de == "tra_loi_ngan":
                    self.render_question_tra_loi_ngan(cau)
                else:
                    self.render_question_trac_nghiem(cau)

def repair_broken_latex(text: str) -> str:
    """
    Tự động phát hiện và đóng dấu $ bị thiếu.
    Ví dụ: "... là $(-5; 4)." -> "... là $(-5; 4)$."
    """
    # 1. Đếm số lượng dấu $
    count = text.count('$')
    
    # Nếu số lượng là chẵn (0, 2, 4...) -> Khả năng cao là đã đủ cặp -> Return
    if count % 2 == 0:
        return text

    # 2. Nếu số lượng là LẺ -> Chắc chắn thiếu 1 dấu đóng
    # Tìm vị trí dấu $ cuối cùng
    last_idx = text.rfind('$')
    
    # Lấy đoạn text từ dấu $ đó đến hết
    segment = text[last_idx:]
    
    # Logic vá:
    # Nếu kết thúc bằng dấu câu (.,;:) -> Chèn $ vào trước dấu câu
    if text.endswith('.') or text.endswith(',') or text.endswith(';') or text.endswith(':'):
        return text[:-1] + '$' + text[-1]
    
    # Nếu không có dấu câu -> Chèn $ vào cuối cùng
    return text + '$'

def response2docx_flexible(
    file_path: str,
    prompt: str,
    file_name: str,
    project_id: str,
    creds: str,
    model_name: str,
    question_type: str = "trac_nghiem_4_dap_an",
    batch_name: Optional[str] = None
) -> Optional[str]:
    try:
        from api.callAPI import VertexClient
        
        client = VertexClient(project_id, creds, model_name)
        
        if not batch_name:
            batch_name = file_name.replace("_TN", "").replace("_DS", "").replace("_TLN", "")
        
        # 1. Wrap prompt với JSON structure hint
        final_prompt = PromptBuilder.wrap_user_prompt(prompt, question_type)
        
        # 2. Gửi request AI
        print("📤 Đang gửi request tới AI...")
        ai_response = client.send_data_to_AI(final_prompt, file_path)
        
        # 3. Parse JSON
        print("🔄 Đang parse JSON...")
        data = parse_json_safely(ai_response, client)
        if not data:
            print("❌ Không thể parse JSON từ AI")
            return None
        
        print(f"✅ Parse thành công: {data.get('tong_so_cau', 0)} câu hỏi")
        
        # 4. Render DOCX động
        print("📝 Đang tạo DOCX...")
        doc = Document()
        renderer = DynamicDocxRenderer(doc)
        
        try:
            renderer.render_all(data)
            print("✅ Render DOCX thành công")
        except Exception as e:
            print(f"❌ Lỗi khi render DOCX: {e}")
            traceback.print_exc()
            return None
        
        # 5. Lưu file
        print("💾 Đang lưu file...")
        output_path = save_document_securely(doc, batch_name, file_name)
        
        if output_path:
            print(f"✅ Hoàn thành: {output_path}")
        else:
            print("❌ Không thể lưu file")
            
        return output_path
    
    except Exception as e:
        print(f"❌ LỖI NGHIÊM TRỌNG: {e}")
        traceback.print_exc()
        return None

def response2docx_json(file_path, prompt, file_name, project_id, creds, model_name, batch_name=None):
    """Wrapper cho trắc nghiệm 4 đáp án (legacy)"""
    return response2docx_flexible(
        file_path, prompt, file_name, project_id, creds, model_name,
        question_type="trac_nghiem_4_dap_an",
        batch_name=batch_name
    )

def response2docx_dung_sai_json(file_path, prompt, file_name, project_id, creds, model_name, batch_name=None):
    """Wrapper cho đúng/sai (legacy)"""
    return response2docx_flexible(
        file_path, prompt, file_name, project_id, creds, model_name,
        question_type="dung_sai",
        batch_name=batch_name
    )
    
def response2docx_tra_loi_ngan_json(file_path, prompt, file_name, project_id, creds, model_name, batch_name=None):
    """Wrapper cho trả lời ngắn (legacy compatibility)"""
    return response2docx_flexible(
        file_path, prompt, file_name, project_id, creds, model_name,
        question_type="tra_loi_ngan",
        batch_name=batch_name
    )

class ConfigManager:
    """
    Quản lý cấu hình qua file JSON
    Cho phép thay đổi TOÀN BỘ behavior mà không sửa code
    """
    
    DEFAULT_CONFIG = {
        "section_mapping": {
            "nhan_biet": "I. CÂU HỎI NHẬN BIẾT",
            "thong_hieu": "II. CÂU HỎI THÔNG HIỂU",
            "van_dung": "III. CÂU HỎI VẬN DỤNG",
            "van_dung_cao": "IV. CÂU HỎI VẬN DỤNG CAO" 
        },
        "section_order": ["nhan_biet", "thong_hieu", "van_dung", "van_dung_cao"],
        "auto_fix": True,
        "image_width_inches": 4,
        "retry_json_parse": 2
    }
    
    @classmethod
    def load_config(cls, config_path: str = "config.json") -> Dict:
        """Load config từ file hoặc dùng default"""
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return cls.DEFAULT_CONFIG
    
    @classmethod
    def save_config(cls, config: Dict, config_path: str = "config.json"):
        """Lưu config để tái sử dụng"""
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

