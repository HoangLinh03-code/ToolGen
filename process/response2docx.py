
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

_FILE_LOCK = threading.RLock()
_OUTPUT_DIR_LOCK = threading.RLock()

def get_app_path():
    """Lấy đường dẫn chứa file .exe hoặc script"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

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
2. KHÔNG thay đổi nội dung tiếng Việt
3. CHỈ TRẢ VỀ JSON ĐÃ SỬA (không markdown)
    """
    repaired_text = client.send_data_to_check(prompt_fix)
    return clean_json_string(repaired_text)

def parse_json_safely(json_str: str, client) -> Optional[Dict]:
    """Parse JSON an toàn với retry AI"""
    cleaned_str = clean_json_string(json_str)
    
    # Thử parse lần 1
    try:
        return json.loads(cleaned_str, strict=False)
    except json.JSONDecodeError as e:
        print(f"❌ Lỗi JSON lần 1: {e}")
    
    # Thử sửa bằng AI
    try:
        repaired_str = repair_json_with_ai(cleaned_str, client)
        return json.loads(repaired_str, strict=False)
    except json.JSONDecodeError as e:
        print(f"❌ Lỗi JSON lần 2: {e}")
        return None

def generate_or_get_image(hinh_anh_data: Dict) -> tuple:
    """
    Xử lý sinh ảnh hoặc trả về placeholder
    Returns: (image_bytes, placeholder_text)
    """
    if not hinh_anh_data.get("co_hinh", False):
        return None, None
    
    mo_ta = hinh_anh_data.get("mo_ta", "")
    loai = hinh_anh_data.get("loai", "tu_mo_ta")
    
    # Sinh ảnh từ mô tả
    if loai == "tu_mo_ta" and mo_ta:
        try:
            print(f"🎨 Đang sinh ảnh: {mo_ta[:50]}...")
            from process.text2Image import generate_image_from_text
            image_bytes = generate_image_from_text(mo_ta)
            if image_bytes:
                print("✅ Sinh ảnh thành công!")
                return image_bytes, None
        except Exception as e:
            print(f"❌ Lỗi sinh ảnh: {e}")
    
    # Fallback: placeholder
    placeholder = f"🖼️ [Cần chèn hình: {mo_ta if mo_ta else 'Không có mô tả'}]"
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
      "noi_dung": "Nội dung câu hỏi",
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
      "doan_thong_tin": "Đoạn văn bản...",
      "hinh_anh": {
        "co_hinh": true,
        "loai": "tu_mo_ta",
        "mo_ta": "Mô tả để sinh ảnh..."
      },
      "cac_y": [
        {"ky_hieu": "a", "noi_dung": "Phát biểu a", "dung": false},
        {"ky_hieu": "b", "noi_dung": "Phát biểu b", "dung": true},
        {"ky_hieu": "c", "noi_dung": "Phát biểu c", "dung": false},
        {"ky_hieu": "d", "noi_dung": "Phát biểu d", "dung": true}
      ],
      "dap_an_dung_sai": "0101",
      "giai_thich": [
        {"y": "a", "noi_dung_y": "Phát biểu a", "giai_thich": "Giải thích...", "ket_luan": "SAI"},
        {"y": "b", "noi_dung_y": "Phát biểu b", "giai_thich": "Giải thích...", "ket_luan": "ĐÚNG"}
      ]
    }
  ]
}
"""
        
        return "{}"
    
    @staticmethod
    def wrap_user_prompt(user_prompt: str, question_type: str) -> str:
        """
        Wrap prompt người dùng với các instruction cần thiết
        """
        json_hint = PromptBuilder.build_json_structure_hint(question_type)
        
        return f"""{user_prompt}

## QUAN TRỌNG: ĐỊNH DẠNG ĐẦU RA
1. Trả về ĐÚNG định dạng JSON hợp lệ
2. Nếu có dấu ngoặc kép ("), hãy escape thành \\" hoặc dùng dấu nháy đơn (')
3. KHÔNG thêm markdown backticks
4. Tuân thủ CHÍNH XÁC cấu trúc JSON sau:

```json
{json_hint}
```

LƯU Ý VỀ HÌNH ẢNH:
- Nếu cần sinh ảnh: "loai": "tu_mo_ta", "mo_ta": "Mô tả chi tiết"
- Nếu KHÔNG có ảnh: "hinh_anh": {{"co_hinh": false}}
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
        Tự động nhóm câu hỏi dựa trên field 'muc_do'
        KHÔNG hard-code mapping
        """
        grouped = {}
        for cau in data.get("cau_hoi", []):
            muc_do = cau.get("muc_do", "unknown")
            if muc_do not in grouped:
                grouped[muc_do] = []
            grouped[muc_do].append(cau)
        
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
        p.add_run(cau['noi_dung'])
        
        # Hình ảnh
        hinh_anh = cau.get("hinh_anh", {})
        if hinh_anh.get("co_hinh"):
            insert_image_or_placeholder(self.doc, hinh_anh)
        
        # Đáp án
        for dap_an in cau.get("dap_an", []):
            p_da = self.doc.add_paragraph()
            p_da.add_run(f"{dap_an['ky_hieu']}. {dap_an['noi_dung']}")
        
        # Lời giải
        p_lg = self.doc.add_paragraph()
        p_lg.add_run("Lời giải:").bold = True
        
        if "dap_an_dung" in cau:
            p_dung = self.doc.add_paragraph()
            p_dung.add_run(f"{cau['dap_an_dung']}").bold = True
            self.doc.add_paragraph("####")
        
        # Giải thích
        giai_thich = cau.get("giai_thich", "")
        for line in giai_thich.split("\n"):
            if line.strip():
                self.doc.add_paragraph(line.strip())
        
        # Kết luận
        if "dap_an_dung" in cau:
            dap_an_num = cau['dap_an_dung']
            noi_dung_dap_an = cau['dap_an'][dap_an_num-1]['noi_dung']
            p_ket_luan = self.doc.add_paragraph()
            run = p_ket_luan.add_run(f"Vậy đáp án đúng là: {noi_dung_dap_an}")
            run.bold = True
    
    def render_question_dung_sai(self, cau: Dict):
        """Render câu hỏi đúng/sai"""
        # Số câu
        p = self.doc.add_paragraph()
        p.add_run(f"Câu {cau['stt']}:").bold = True
        
        # Đoạn thông tin
        if cau.get("doan_thong_tin"):
            self.doc.add_paragraph(cau.get("doan_thong_tin", ""))
        
        # Hình ảnh
        hinh_anh = cau.get("hinh_anh", {})
        if hinh_anh.get("co_hinh"):
            insert_image_or_placeholder(self.doc, hinh_anh)
        
        # Các ý a, b, c, d
        for y in cau.get("cac_y", []):
            self.doc.add_paragraph(f"{y['ky_hieu']}) {y['noi_dung']}")
        
        # Lời giải
        p_lg = self.doc.add_paragraph()
        p_lg.add_run("Lời giải:").bold = True
        
        p_da = self.doc.add_paragraph()
        p_da.add_run(cau.get("dap_an_dung_sai", "")).bold = True
        self.doc.add_paragraph("####")
        
        # Giải thích từng ý
        for gt in cau.get("giai_thich", []):
            p_gt = self.doc.add_paragraph()
            p_gt.add_run(f"- {gt.get('noi_dung_y', '')} - ")
            run_kl = p_gt.add_run(f"{gt.get('ket_luan', 'SAI')}.")
            run_kl.bold = True
            
            if gt.get('giai_thich'):
                self.doc.add_paragraph(gt.get('giai_thich', ''))
    
    def render_all(self, data: Dict):
        """
        Main render function - TỰ ĐỘNG DETECT loại đề
        """
        self.render_title(data)
        
        # Auto-group
        grouped = self.auto_group_questions(data)
        
        # Detect loại đề
        loai_de = data.get("loai_de", "")
        
        # Render từng nhóm
        for muc_do in ["nhan_biet", "thong_hieu", "van_dung", "van_dung_cao"]:
            if muc_do not in grouped:
                continue
            
            # Thêm header
            section_title = self.get_section_title(muc_do)
            self.doc.add_heading(section_title, level=2)
            
            # Render câu hỏi
            for cau in grouped[muc_do]:
                if loai_de == "dung_sai":
                    self.render_question_dung_sai(cau)
                else:
                    self.render_question_trac_nghiem(cau)

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
    """
    Main function - LINH HOẠT với mọi loại prompt
    
    Args:
        question_type: "trac_nghiem_4_dap_an" hoặc "dung_sai"
    """
    from api.callAPI import VertexClient
    
    client = VertexClient(project_id, creds, model_name)
    
    if not batch_name:
        batch_name = file_name.replace("_TN", "").replace("_DS", "")
    
    # 1. Wrap prompt với JSON structure hint
    final_prompt = PromptBuilder.wrap_user_prompt(prompt, question_type)
    
    # 2. Gửi request AI
    print("📤 Đang gửi request tới AI...")
    ai_response = client.send_data_to_AI(final_prompt, file_path)
    
    # 3. Parse JSON
    data = parse_json_safely(ai_response, client)
    if not data:
        print("❌ Không thể parse JSON từ AI")
        return None
    
    # 4. Optional: Check & fix với AI
    # data = check_and_fix_questions(data, client)
    
    # 5. Render DOCX động
    doc = Document()
    renderer = DynamicDocxRenderer(doc)
    renderer.render_all(data)
    
    # 6. Lưu file
    output_path = save_document_securely(doc, batch_name, file_name)
    print(f"✅ Đã lưu file: {output_path}")
    return output_path

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

