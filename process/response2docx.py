import json
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from api.callAPI import VertexClient
from process.text2Image import generate_image_from_text, get_image_size_for_aspect_ratio
from io import BytesIO
import os
import sys
import threading
import time

# Global lock để bảo vệ file operations
_FILE_LOCK = threading.RLock()
_OUTPUT_DIR_LOCK = threading.RLock()

def get_app_path():
    """Lấy đường dẫn chứa file .exe hoặc file script đang chạy"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def ensure_output_folder_for_batch(batch_name):
    """
    Tạo folder riêng cho từng batch bài học
    Cấu trúc: output/{batch_name}/
    """
    base_path = get_app_path()
    output_base = os.path.join(base_path, "output")
    batch_folder = os.path.join(output_base, batch_name)
    
    with _OUTPUT_DIR_LOCK:
        # Tạo thư mục base/output nếu chưa có
        if not os.path.exists(output_base):
            try:
                os.makedirs(output_base, exist_ok=True)
                print(f"✅ Đã tạo thư mục: {output_base}")
            except OSError as e:
                print(f"❌ Lỗi không thể tạo thư mục output: {e}")
                return None
        
        # Tạo thư mục riêng cho batch (bài học)
        if not os.path.exists(batch_folder):
            try:
                os.makedirs(batch_folder, exist_ok=True)
                print(f"✅ Đã tạo thư mục batch: {batch_folder}")
            except OSError as e:
                print(f"❌ Lỗi không thể tạo thư mục batch '{batch_name}': {e}")
                return None
    
    return batch_folder

def save_document_securely(doc, batch_name, file_name):
    """
    Hàm lưu file DOCX với thread-safety
    
    Args:
        doc: Document object
        batch_name: Tên batch (sẽ tạo folder có tên này)
        file_name: Tên file mà không cần .docx
    
    Returns:
        Đường dẫn file hoặc None
    """
    # Tạo folder cho batch
    batch_folder = ensure_output_folder_for_batch(batch_name)
    
    if not batch_folder:
        return None

    output_path = os.path.join(batch_folder, f"{file_name}.docx")
    
    # ============================================================
    # LOCK: Bảo vệ toàn bộ quá trình save file
    # ============================================================
    with _FILE_LOCK:
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Lưu file với chế độ độc quyền (overwrite)
                doc.save(output_path)
                
                # Xác nhận file tồn tại
                if os.path.exists(output_path):
                    file_size = os.path.getsize(output_path)
                    print(f"✅ Đã lưu file: {output_path} ({file_size} bytes)")
                    return output_path
                else:
                    raise FileNotFoundError(f"File không được tạo: {output_path}")
                    
            except PermissionError as e:
                print(f"⚠️ Lỗi permission lần {retry_count + 1}: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(0.5)  # Delay trước khi retry
                continue
                
            except Exception as e:
                print(f"❌ Lỗi khi lưu file docx: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(0.5)
                continue
        
        # Nếu sau 3 lần vẫn fail
        print(f"❌ Không thể lưu file sau {max_retries} lần thử: {output_path}")
        return None

def clean_json_string(text):
    """Làm sạch chuỗi JSON trước khi parse"""
    text = text.strip()
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
    repaired_text = client.send_data_to_check(prompt_fix)
    return clean_json_string(repaired_text)

def parse_json_safely(json_str, client):
    """Thử parse, nếu lỗi thì nhờ AI sửa"""
    cleaned_str = clean_json_string(json_str)
    
    try:
        return json.loads(cleaned_str, strict=False)
    except json.JSONDecodeError as e:
        print(f"Lỗi JSON lần 1: {e}")
        
    try:
        repaired_str = repair_json_with_ai(cleaned_str, client)
        return json.loads(repaired_str, strict=False)
    except json.JSONDecodeError as e:
        print(f"Lỗi JSON lần 2 (AI bó tay): {e}")
        return None

def generate_or_get_image(hinh_anh_data):
    """
    Xử lý sinh ảnh hoặc trả về placeholder
    
    Returns:
        tuple: (image_bytes, placeholder_text)
        - Nếu sinh ảnh thành công: (bytes, None)
        - Nếu cần placeholder: (None, "text mô tả")
    """
    if not hinh_anh_data.get("co_hinh", False):
        return None, None
    
    loai = hinh_anh_data.get("loai", "tu_mo_ta")
    mo_ta = hinh_anh_data.get("mo_ta", "")
    
    # Trường hợp: Sinh ảnh từ mô tả
    if loai == "tu_mo_ta" and mo_ta:
        try:
            print(f"🎨 Đang sinh ảnh từ mô tả: {mo_ta[:50]}...")
            image_bytes = generate_image_from_text(mo_ta)
            if image_bytes:
                print("✅ Sinh ảnh thành công!")
                return image_bytes, None
        except Exception as e:
            print(f"❌ Lỗi khi sinh ảnh: {e}")
    
    # Trường hợp: Lỗi hoặc không có mô tả - dùng placeholder
    placeholder = f"🖼️ [Cần chèn hình ảnh: {mo_ta if mo_ta else 'Không có mô tả'}]"
    return None, placeholder

def insert_image_or_placeholder(doc, hinh_anh_data):
    """
    Chèn ảnh hoặc placeholder vào document
    """
    image_bytes, placeholder = generate_or_get_image(hinh_anh_data)
    
    if image_bytes:
        # Chèn ảnh thật
        try:
            image_stream = BytesIO(image_bytes)
            doc.add_picture(image_stream, width=Inches(4))
            last_paragraph = doc.paragraphs[-1]
            last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception as e:
            print(f"❌ Lỗi khi chèn ảnh vào DOCX: {e}")
            # Fallback về placeholder
            p = doc.add_paragraph()
            run = p.add_run(f"⚠️ [Lỗi chèn ảnh: {str(e)}]")
            run.font.color.rgb = RGBColor(255, 0, 0)
            run.italic = True
    
    elif placeholder:
        # Chèn placeholder với format đẹp
        p = doc.add_paragraph()
        run = p.add_run(placeholder)
        run.font.color.rgb = RGBColor(200, 0, 0)  # Màu đỏ nhạt
        run.italic = True
        run.bold = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

def response2docx_json(file_path, prompt, file_name, project_id, creds, model_name, batch_name=None):
    client = VertexClient(project_id, creds, model_name)
    
    # Nếu không có batch_name, lấy từ file_name (bỏ đi _TN hoặc _DS)
    if not batch_name:
        batch_name = file_name.replace("_TN", "").replace("_DS", "")
    
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
        "loai": "tu_mo_ta",
        "mo_ta": "Mô tả hình ảnh để sinh..."
      }},
      "dap_an": [
        {{"ky_hieu": "A", "noi_dung": "Đáp án A"}},
        {{"ky_hieu": "B", "noi_dung": "Đáp án B"}},
        {{"ky_hieu": "C", "noi_dung": "Đáp án C"}},
        {{"ky_hieu": "D", "noi_dung": "Đáp án D"}}
      ],
      "dap_an_dung": 2,
      "giai_thich": "Giải thích chi tiết TUYỆT ĐỐI KHÔNG giải thích các đáp án sai khác..."
    }}
  ]
}}

LƯU Ý: 
- "dap_an_dung" phải là Số (1/2/3/4) tương ứng A/B/C/D, KHÔNG phải chữ cái
- Với hình ảnh:
  + Nếu cần sinh ảnh: "loai": "tu_mo_ta", "mo_ta": "Mô tả chi tiết để sinh ảnh"
  + Nếu KHÔNG có hình ảnh: "hinh_anh": {{"co_hinh": false}}
"""
    
    print("Đang gửi request tới AI...")
    ai_response = client.send_data_to_AI(prompt_json, file_path)
    data = parse_json_safely(ai_response, client)
    if not data:
        print("❌ Không thể lấy dữ liệu JSON từ AI sau nhiều nỗ lực.")
        return None
    
    data = check_and_fix_questions(data, client)
    doc = create_docx_from_json(data)
    
    # SỬ DỤNG HÀM SAVE THREAD-SAFE VỚI BATCH FOLDER
    output_path = save_document_securely(doc, batch_name, file_name)
    print(f"Đã lưu file: {output_path}")
    return output_path

def check_and_fix_questions(data, client):
    """Kiểm tra và sửa lỗi các câu hỏi"""
    prompt_check = f'''Kiểm tra bộ câu hỏi JSON sau:
```json
{json.dumps(data, ensure_ascii=False, indent=2)}
```

Yêu cầu:
1. Kiểm tra tính đúng đắn của đáp án
2. Kiểm tra độ dài giải thích (tối thiểu 60 từ)
3. Sửa lỗi nếu có

Trả về JSON đã sửa (format giống input, không thêm markdown):
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
    """Tạo file DOCX từ JSON data"""
    doc = Document()
    
    title = doc.add_heading(f'Đề {data.get("loai_de", "").upper()}', level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Nhóm câu hỏi theo mức độ
    cau_hoi_theo_muc = {}
    for cau in data.get("cau_hoi", []):
        muc_do = cau.get("muc_do", "")
        if muc_do not in cau_hoi_theo_muc:
            cau_hoi_theo_muc[muc_do] = []
        cau_hoi_theo_muc[muc_do].append(cau)
    
    muc_do_mapping = {
        "nhan_biet": "I. CÂU HỎI NHẬN BIẾT",
        "thong_hieu": "II. CÂU HỎI THÔNG HIỂU",
        "van_dung": "III. CÂU HỎI VẬN DỤNG",
        "van_dung_cao": "IV. CÂU HỎI VẬN DỤNG CAO"
    }
    
    for muc_do in ["nhan_biet", "thong_hieu", "van_dung", "van_dung_cao"]:
        if muc_do not in cau_hoi_theo_muc:
            continue
        
        doc.add_heading(muc_do_mapping.get(muc_do, muc_do.upper()), level=2)
        
        for cau in cau_hoi_theo_muc[muc_do]:
            render_question(doc, cau)
    
    return doc

def render_question(doc, cau):
    """Render một câu hỏi vào document"""
    # Câu hỏi
    p = doc.add_paragraph()
    p.add_run(f"Câu {cau['stt']}: ").bold = True
    p.add_run(cau['noi_dung'])
    
    # Hình ảnh (nếu có)
    hinh_anh = cau.get("hinh_anh", {})
    if hinh_anh.get("co_hinh"):
        insert_image_or_placeholder(doc, hinh_anh)
    
    # Đáp án
    for dap_an in cau.get("dap_an", []):
        p_da = doc.add_paragraph()
        p_da.add_run(f"{dap_an['ky_hieu']}. {dap_an['noi_dung']}")
    
    # Lời giải
    p_lg = doc.add_paragraph()
    p_lg.add_run("Lời giải:").bold = True
    
    # Đáp án đúng
    if "dap_an_dung" in cau:
        p_dung = doc.add_paragraph()
        dap_an_num = cau['dap_an_dung']
        p_dung.add_run(f"{dap_an_num}").bold = True
        doc.add_paragraph("####")
    
    # Giải thích
    giai_thich = cau.get("giai_thich", "")
    for line in giai_thich.split("\n"):
        if line.strip():
            doc.add_paragraph(line.strip())
    
    # Kết luận
    if "dap_an_dung" in cau:
        dap_an_num = cau['dap_an_dung']
        noi_dung_dap_an = cau['dap_an'][dap_an_num-1]['noi_dung']
        p_ket_luan = doc.add_paragraph()
        run_ket_luan = p_ket_luan.add_run(f"Vậy đáp án đúng là: {noi_dung_dap_an}")
        run_ket_luan.bold = True

def render_question_dung_sai(doc, cau):
    """Render chi tiết một câu hỏi Đúng/sai"""
    # Số câu
    p = doc.add_paragraph()
    p.add_run(f"Câu {cau['stt']}:").bold = True
    
    # Đoạn thông tin
    if cau.get("doan_thong_tin"):
        doc.add_paragraph(cau.get("doan_thong_tin", ""))
    
    # Hình ảnh - Xử lý hình ảnh nếu có
    hinh_anh = cau.get("hinh_anh", {})
    if hinh_anh.get("co_hinh"):
        insert_image_or_placeholder(doc, hinh_anh)
    
    # Các ý a, b, c, d
    for y in cau.get("cac_y", []):
        doc.add_paragraph(f"{y['ky_hieu']}) {y['noi_dung']}")
    
    # Lời giải
    p_lg = doc.add_paragraph()
    p_lg.add_run("Lời giải:").bold = True
    
    # Đáp án chuỗi nhị phân (ví dụ: 0101)
    p_da = doc.add_paragraph()
    p_da.add_run(cau.get("dap_an_dung_sai", "")).bold = True
    
    # Dòng phân cách
    doc.add_paragraph("####")
    
    # Giải thích chi tiết từng ý
    for gt in cau.get("giai_thich", []):
        p_gt = doc.add_paragraph()
        
        # Format: "- Nội dung ý - KẾT LUẬN."
        p_gt.add_run(f"- {gt.get('noi_dung_y', '')} - ")
        run_ket_luan = p_gt.add_run(f"{gt.get('ket_luan', 'SAI')}.")
        run_ket_luan.bold = True
        
        # Nội dung giải thích
        if gt.get('giai_thich'):
            p_giai_thich = doc.add_paragraph(gt.get('giai_thich', ''))
            p_giai_thich.alignment = WD_ALIGN_PARAGRAPH.LEFT

def response2docx_dung_sai_json(file_path, prompt, file_name, project_id, creds, model_name, batch_name=None):
    client = VertexClient(project_id, creds, model_name)
    
    # Nếu không có batch_name, lấy từ file_name (bỏ đi _TN hoặc _DS)
    if not batch_name:
        batch_name = file_name.replace("_TN", "").replace("_DS", "")
    
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
        "loai": "tu_mo_ta",
        "mo_ta": "Mô tả hình ảnh để sinh..."
      }},
      "cac_y": [
        {{"ky_hieu": "a", "noi_dung": "Phát biểu a", "dung": false}},
        {{"ky_hieu": "b", "noi_dung": "Phát biểu b", "dung": true}},
        {{"ky_hieu": "c", "noi_dung": "Phát biểu c", "dung": false}},
        {{"ky_hieu": "d", "noi_dung": "Phát biểu d", "dung": true}}
      ],
      "dap_an_dung_sai": "0101",
      "giai_thich": [
        {{"y": "a", "noi_dung_y": "Phát biểu a", "giai_thich": "Giải thích chi tiết...", "ket_luan": "SAI"}},
        {{"y": "b", "noi_dung_y": "Phát biểu b", "giai_thich": "Giải thích chi tiết...", "ket_luan": "ĐÚNG"}},
        {{"y": "c", "noi_dung_y": "Phát biểu c", "giai_thich": "Giải thích chi tiết...", "ket_luan": "SAI"}},
        {{"y": "d", "noi_dung_y": "Phát biểu d", "giai_thích": "Giải thích chi tiết...", "ket_luan": "ĐÚNG"}}
      ]
    }}
  ]
}}

LƯU Ý: 
- Với hình ảnh:
  + Nếu cần sinh ảnh: "loai": "tu_mo_ta", "mo_ta": "Mô tả chi tiết để sinh ảnh"
  + Nếu KHÔNG có hình ảnh: "hinh_anh": {{"co_hinh": false}}
- Giải thích không trích trong đoạn văn, độ dài khoảng 3-4 dòng
"""
    
    print("Đang gửi request tới AI...")
    ai_response = client.send_data_to_AI(prompt_json, file_path)
    
    data = parse_json_safely(ai_response, client)
    
    if not data:
        print("❌ Không thể lấy dữ liệu JSON từ AI.")
        return None
    
    doc = create_docx_dung_sai(data)
    
    # SỬ DỤNG HÀM SAVE THREAD-SAFE VỚI BATCH FOLDER
    output_path = save_document_securely(doc, batch_name, file_name)
    print(f"Đã lưu file: {output_path}")
    return output_path

def create_docx_dung_sai(data):
    """
    Tạo DOCX cho câu hỏi Đúng/sai có phân chia mức độ (Header)
    Logic mapping:
    - 1-19: Thông hiểu
    - 20-32: Vận dụng
    - 33-40: Vận dụng cao
    """
    doc = Document()
    
    title = doc.add_heading('ĐỀ TRẮC NGHIỆM ĐÚNG/SAI', level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # 1. Định nghĩa Mapping hiển thị
    muc_do_display = {
        "thong_hieu": "I. CÂU HỎI THÔNG HIỂU",
        "van_dung": "II. CÂU HỎI VẬN DỤNG",
        "van_dung_cao": "III. CÂU HỎI VẬN DỤNG CAO"
    }
    
    # 2. Khởi tạo các nhóm chứa câu hỏi
    cau_hoi_theo_muc = {
        "thong_hieu": [],
        "van_dung": [],
        "van_dung_cao": []
    }
    
    # 3. Phân loại câu hỏi vào nhóm dựa trên STT
    list_cau_hoi = sorted(data.get("cau_hoi", []), key=lambda x: x.get("stt", 0))
    
    for cau in list_cau_hoi:
        stt = cau.get("stt", 0)
        
        # Logic mapping STT -> Mức Độ
        if 1 <= stt <= 19:
            key = "thong_hieu"
        elif 20 <= stt <= 32:
            key = "van_dung"
        elif 33 <= stt <= 40:
            key = "van_dung_cao"
        else:
            # Fallback cho các câu nằm ngoài range (ví dụ > 40)
            key = "van_dung_cao"
            
        cau_hoi_theo_muc[key].append(cau)
        
    # 4. Render tuần tự theo thứ tự mức độ mong muốn
    render_order = ["thong_hieu", "van_dung", "van_dung_cao"]
    
    for muc_do in render_order:
        ds_cau_hoi = cau_hoi_theo_muc.get(muc_do, [])
        
        # Chỉ render nếu nhóm đó có câu hỏi
        if ds_cau_hoi:
            # Thêm Heading Mức Độ
            header_text = muc_do_display.get(muc_do, muc_do.upper())
            doc.add_heading(header_text, level=2)
            
            # Render từng câu hỏi trong nhóm
            for cau in ds_cau_hoi:
                render_question_dung_sai(doc, cau)
                
    return doc