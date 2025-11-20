import json
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from api.callAPI import VertexClient
from process.text2Image import generate_image_from_text
from io import BytesIO
import os
import sys
def get_app_path():
    """Lấy đường dẫn chứa file .exe hoặc file script đang chạy"""
    if getattr(sys, 'frozen', False):
        # Nếu đang chạy file .exe
        return os.path.dirname(sys.executable)
    else:
        # Nếu đang chạy code python thường
        return os.path.dirname(os.path.abspath(__file__))

def save_document_securely(doc, file_name):
    """Hàm lưu file an toàn: tự tạo folder output và dùng đường dẫn tuyệt đối"""
    # 1. Lấy đường dẫn gốc nơi đặt file exe
    base_path = get_app_path()
    
    # 2. Định nghĩa folder output
    output_dir = os.path.join(base_path, "output")
    
    # 3. Tự động tạo folder nếu chưa có
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Đã tạo thư mục: {output_dir}")
        except OSError as e:
            print(f"Lỗi không thể tạo thư mục output: {e}")
            return None

    # 4. Tạo đường dẫn file đầy đủ
    output_path = os.path.join(output_dir, f"{file_name}.docx")
    
    # 5. Lưu file
    try:
        doc.save(output_path)
        print(f"Đã lưu file tại: {output_path}")
        return output_path
    except Exception as e:
        print(f"Lỗi khi lưu file docx: {e}")
        return None

def clean_json_string(text):
    """Làm sạch chuỗi JSON trước khi parse"""
    text = text.strip()
    # Loại bỏ markdown code block
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return text.strip()

def repair_json_with_ai(broken_json_str, client):
    """Gửi chuỗi JSON lỗi cho AI nhờ sửa"""
    print("⚠️ Phát hiện lỗi cú pháp JSON. Đang yêu cầu AI sửa lại...")
    prompt_fix = f"""
    Đoạn JSON sau đây bị lỗi cú pháp (thường do dấu ngoặc kép chưa được escape hoặc thiếu dấu phẩy):
    
    {broken_json_str}
    
    NHIỆM VỤ:
    1. Tìm và sửa lỗi cú pháp JSON (escape quotes, thêm phẩy, đóng ngoặc...).
    2. TUYỆT ĐỐI KHÔNG thay đổi nội dung văn bản tiếng Việt.
    3. CHỈ TRẢ VỀ JSON ĐÃ SỬA (Không giải thích, không markdown).
    """
    # Gọi AI để sửa (dùng hàm send_data_to_check hoặc send_data_to_AI đều được)
    # Ở đây ta tận dụng hàm send_data_to_check cho nhanh
    repaired_text = client.send_data_to_check(prompt_fix)
    return clean_json_string(repaired_text)

def parse_json_safely(json_str, client):
    """Thử parse, nếu lỗi thì nhờ AI sửa, thử tối đa 2 lần"""
    cleaned_str = clean_json_string(json_str)
    
    # Lần thử 1: Parse trực tiếp
    try:
        # strict=False cho phép chấp nhận một số lỗi nhỏ như \n trong string
        return json.loads(cleaned_str, strict=False)
    except json.JSONDecodeError as e:
        print(f"Lỗi JSON lần 1: {e}")
        
    # Lần thử 2: Nhờ AI sửa rồi parse lại
    try:
        repaired_str = repair_json_with_ai(cleaned_str, client)
        return json.loads(repaired_str, strict=False)
    except json.JSONDecodeError as e:
        print(f"Lỗi JSON lần 2 (AI bó tay): {e}")
        return None

def response2docx_json(file_path, prompt, file_name, project_id, creds, model_name):
    """
    Phiên bản tối ưu sử dụng JSON thay vì text string
    """
    client = VertexClient(project_id, creds, model_name)
    
    # Yêu cầu AI trả về JSON
    prompt_json = f"""{prompt}

## QUAN TRỌNG: ĐỊNH DẠNG ĐẦU RA
1. Trả về ĐÚNG định dạng JSON hợp lệ.
2. Nếu trong nội dung câu hỏi/đáp án có dấu ngoặc kép ("), hãy thay thế bằng dấu nháy đơn (') hoặc escape nó (\").
3. Không thêm bất kỳ ký tự nào ngoài JSON.
Trả về ĐÚNG định dạng JSON sau (không thêm markdown backticks):
{{
  "loai_de": "trac_nghiem_4_dap_an",
  "tong_so_cau": 80,
  "cau_hoi": [
    {{
      "stt": 1,
      "muc_do": "nhan_biet",
      "phan": "Phần I",
      "noi_dung": "Nội dung câu hỏi",
      "hinh_anh": {{
        "co_hinh": true,
        "loai": "tu_pdf",
        "mo_ta": "Hình 5 - Lấy từ trang 10 của file PDF",
        "trang": 10,
        "so_hinh": 5
      }},
      "dap_an": [
        {{"ky_hieu": "A", "noi_dung": "Đáp án A"}},
        {{"ky_hieu": "B", "noi_dung": "Đáp án B"}},
        {{"ky_hieu": "C", "noi_dung": "Đáp án C"}},
        {{"ky_hieu": "D", "noi_dung": "Đáp án D"}}
      ],
      "dap_an_dung": 2,
      "giai_thich": "Giải thích chi tiết..."
    }}
  ]
}}

LƯU Ý: "dap_an_dung" phải là Số (1/2/3/4) tương ứng A/B/C/D, KHÔNG phải chữ cái

Nếu câu hỏi KHÔNG có hình ảnh:
"hinh_anh": {{"co_hinh": false}}
"""
    
    print("Đang gửi request tới AI...")
    ai_response = client.send_data_to_AI(prompt_json, file_path)
    data = parse_json_safely(ai_response, client)
    if not data:
        print("❌ Không thể lấy dữ liệu JSON từ AI sau nhiều nỗ lực.")
        return None
    
    # Kiểm tra và sửa lỗi nếu cần
    data = check_and_fix_questions(data, client)
    
    # Tạo DOCX từ JSON
    doc = create_docx_from_json(data)
    
    output_path = save_document_securely(doc, file_name)
    print(f"Đã lưu file: {output_path}")
    return output_path


def check_and_fix_questions(data, client):
    """
    Kiểm tra và sửa lỗi các câu hỏi
    """
    prompt_check = f'''Kiểm tra bộ câu hỏi JSON sau:
```json
{json.dumps(data, ensure_ascii=False, indent=2)}
```

Yêu cầu:
1. Kiểm tra tính đúng đắn của đáp án
2. Kiểm tra độ dài giải thích (tối thiểu 60 từ)
3. Sửa lỗi nếu có

Trả về JSON đã được sửa (format giống input, không thêm markdown):
'''
    
    response = client.send_data_to_check(prompt=prompt_check)
    
    try:
        clean_response = response.strip()
        if clean_response.startswith("```json"):
            clean_response = clean_response[7:]
        if clean_response.startswith("```"):
            clean_response = clean_response[3:]
        if clean_response.endswith("```"):
            clean_response = clean_response[:-3]
        
        fixed_data = json.loads(clean_response.strip())
        return fixed_data
    except:
        print("Không thể sửa lỗi, trả về data gốc")
        return data


def create_docx_from_json(data):
    """
    Tạo file DOCX từ JSON data
    """
    doc = Document()
    
    # Thêm tiêu đề
    title = doc.add_heading(f'ĐỀ {data.get("loai_de", "").upper()}', level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Nhóm câu hỏi theo mức độ
    cau_hoi_theo_muc = {}
    for cau in data.get("cau_hoi", []):
        muc_do = cau.get("muc_do", "")
        if muc_do not in cau_hoi_theo_muc:
            cau_hoi_theo_muc[muc_do] = []
        cau_hoi_theo_muc[muc_do].append(cau)
    
    # Render từng mức độ
    muc_do_mapping = {
        "nhan_biet": "I. CÂU HỎI NHẬN BIẾT",
        "thong_hieu": "II. CÂU HỎI THÔNG HIỂU",
        "van_dung": "III. CÂU HỎI VẬN DỤNG",
        "van_dung_cao": "IV. CÂU HỎI VẬN DỤNG CAO"
    }
    
    for muc_do in ["nhan_biet", "thong_hieu", "van_dung", "van_dung_cao"]:
        if muc_do not in cau_hoi_theo_muc:
            continue
        
        # Thêm heading mức độ
        doc.add_heading(muc_do_mapping.get(muc_do, muc_do.upper()), level=2)
        
        # Render từng câu hỏi
        for cau in cau_hoi_theo_muc[muc_do]:
            render_question(doc, cau)
    
    return doc


def render_question(doc, cau):
    """
    Render một câu hỏi vào document
    """
    # Câu hỏi
    p = doc.add_paragraph()
    p.add_run(f"Câu {cau['stt']}: ").bold = True
    p.add_run(cau['noi_dung'])
    
    # Hình ảnh (nếu có)
    hinh_anh = cau.get("hinh_anh", {})
    if hinh_anh.get("co_hinh"):
        p_img = doc.add_paragraph()
        p_img.add_run(f"[Hình ảnh: {hinh_anh.get('mo_ta', '')}]").italic = True
    
    # Đáp án (không dùng bullet để tránh gạch đầu dòng)
    for dap_an in cau.get("dap_an", []):
        p_da = doc.add_paragraph()
        p_da.add_run(f"{dap_an['ky_hieu']}. {dap_an['noi_dung']}")
    
    # Lời giải
    p_lg = doc.add_paragraph()
    p_lg.add_run("Lời giải:").bold = True
    
    # Đáp án đúng (dạng số: 1/2/3/4)
    if "dap_an_dung" in cau:
        p_dung = doc.add_paragraph()
        dap_an_num = cau['dap_an_dung']
        # Chuyển số thành chữ cái để hiển thị (1->A, 2->B, 3->C, 4->D)
        p_dung.add_run(f"{dap_an_num}").bold = True
        doc.add_paragraph("####")
    elif "dap_an_dung_sai" in cau:
        # Cho câu hỏi đúng/sai
        p_dung = doc.add_paragraph()
        p_dung.add_run(cau['dap_an_dung_sai']).bold = True
        doc.add_paragraph("####")
    
    # Giải thích
    giai_thich = cau.get("giai_thich", "")
    # Split theo dấu xuống dòng để format đẹp hơn
    for line in giai_thich.split("\n"):
        if line.strip():
            p_gt = doc.add_paragraph(line.strip())
    
    # Kết luận - Đáp án đúng cuối cùng (IN ĐẬM)
    if "dap_an_dung" in cau:
        dap_an_num = cau['dap_an_dung']
        noi_dung_dap_an = cau['dap_an'][dap_an_num-1]['noi_dung']
        p_ket_luan = doc.add_paragraph()
        # Tạo run riêng và set bold=True
        run_ket_luan = p_ket_luan.add_run(f"Vậy đáp án đúng là: {noi_dung_dap_an}")
        run_ket_luan.bold = True  # Đảm bảo in đậm


def response2docx_dung_sai_json(file_path, prompt, file_name, project_id, creds, model_name):
    """
    Phiên bản cho câu hỏi đúng/sai (40 câu) - ĐÃ FIX FORMAT
    """
    client = VertexClient(project_id, creds, model_name)
    
    prompt_json = f"""{prompt}

## QUAN TRỌNG: ĐỊNH DẠNG ĐẦU RA JSON
1. Nếu trong nội dung có dấu ngoặc kép ("), BẮT BUỘC đổi thành dấu nháy đơn (').
2. Đảm bảo cấu trúc JSON hợp lệ tuyệt đối.
3. Trả về JSON format sau (không thêm markdown backticks):
{{
  "loai_de": "dung_sai",
  "tong_so_cau": 40,
  "cau_hoi": [
    {{
      "stt": 1,
      "muc_do": "thong_hieu",
      "phan": "Phần I",
      "doan_thong_tin": "Đoạn văn bản hoặc tình huống...",
      "hinh_anh": {{
        "co_hinh": true,
        "mo_ta": "Mô tả hình ảnh..."
      }},
      "cac_y": [
        {{"ky_hieu": "a", "noi_dung": "Phát biểu a", "dung": false}},
        {{"ky_hieu": "b", "noi_dung": "Phát biểu b", "dung": true}},
        {{"ky_hieu": "c", "noi_dung": "Phát biểu c", "dung": false}},
        {{"ky_hieu": "d", "noi_dung": "Phát biểu d", "dung": true}}
      ],
      "dap_an_dung_sai": "0101",
      "giai_thich": [
        {{"y": "a", "noi_dung_y": "Phát biểu a", "giai_thich": "Giải thích chi tiết cho ý a...", "ket_luan": "SAI"}},
        {{"y": "b", "noi_dung_y": "Phát biểu b", "giai_thich": "Giải thích chi tiết cho ý b...", "ket_luan": "ĐÚNG"}},
        {{"y": "c", "noi_dung_y": "Phát biểu c", "giai_thich": "Giải thích chi tiết cho ý c...", "ket_luan": "SAI"}},
        {{"y": "d", "noi_dung_y": "Phát biểu d", "giai_thích": "Giải thích chi tiết cho ý d...", "ket_luan": "ĐÚNG"}}
      ]
    }}
  ]
}}
- Nếu câu hỏi KHÔNG có hình ảnh:
"hinh_anh": {{"co_hinh": false}}
- Lưu ý: 
Giải thích không trích trong đoạn văn, sử dụng các thông tin liên quan đến kiến thức của phát biểu và "doan_thong_tin" trong json. Tuyệt đối không được viết lan man, độ dài khoảng 3-4 dòng, không làm trích dẫn, sử dụng thông tin và kiến thức thực tế.
"""
    
    print("Đang gửi request tới AI...")
    ai_response = client.send_data_to_AI(prompt_json, file_path)
    
    data = parse_json_safely(ai_response, client)
    
    if not data:
        print("❌ Không thể lấy dữ liệu JSON từ AI.")
        return None
    doc = create_docx_dung_sai(data)
    output_path = save_document_securely(doc, file_name)
    print(f"Đã lưu file: {output_path}")
    return output_path


def create_docx_dung_sai(data):
    """
    Tạo DOCX cho câu hỏi đúng/sai - FORMAT THEO MẪU
    """
    doc = Document()
    
    title = doc.add_heading('ĐỀ TRẮC NGHIỆM ĐÚNG/SAI', level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    for cau in data.get("cau_hoi", []):
        # Số câu
        p = doc.add_paragraph()
        p.add_run(f"Câu {cau['stt']}:").bold = True
        
        # Đoạn thông tin
        doc.add_paragraph(cau.get("doan_thong_tin", ""))
        
        # Hình ảnh
        hinh_anh = cau.get("hinh_anh", {})
        if hinh_anh.get("co_hinh"):
            p_img = doc.add_paragraph()
            p_img.add_run(f"[{hinh_anh.get('mo_ta', '')}]").italic = True
        
        # Các ý a, b, c, d
        for y in cau.get("cac_y", []):
            doc.add_paragraph(f"{y['ky_hieu']}) {y['noi_dung']}")
        
        # Lời giải
        p_lg = doc.add_paragraph()
        p_lg.add_run("Lời giải:").bold = True
        
        # Đáp án (dạng 0101)
        p_da = doc.add_paragraph()
        p_da.add_run(cau.get("dap_an_dung_sai", "")).bold = True
        doc.add_paragraph("####")
        
        # Giải thích từng ý theo đúng format mẫu
        for gt in cau.get("giai_thich", []):
            # Dòng 1: "- [Nội dung phát biểu] - KẾT LUẬN."
            p_gt = doc.add_paragraph()
            p_gt.add_run(f"- {gt.get('noi_dung_y', '')} - ")
            run_ket_luan = p_gt.add_run(f"{gt.get('ket_luan', 'SAI')}.")
            run_ket_luan.bold = True
            
            # Dòng 2: Giải thích chi tiết (xuống dòng ngay sau)
            p_giai_thich = doc.add_paragraph(gt.get('giai_thich', ''))
            p_giai_thich.alignment = WD_ALIGN_PARAGRAPH.LEFT
    
    return doc