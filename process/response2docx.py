from docx import Document
from api.callAPI import VertexClient
from process.text2Image import generate_image_from_text
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
import zipfile, subprocess, re
from tempfile import NamedTemporaryFile
from docx.oxml import parse_xml
import traceback

def latex_to_omml_via_pandoc(latex_math_dollar):
    """Chuyển đổi LaTeX sang OMML qua Pandoc"""
    try:
        with NamedTemporaryFile(suffix=".docx", delete=False) as temp_docx:
            result = subprocess.run(
                ['pandoc', '--from=latex', '--to=docx', '-o', temp_docx.name],
                input=latex_math_dollar,
                text=True,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )

            if result.returncode != 0:
                print(f"⚠️ Pandoc error: {result.stderr}")
                return None
            
            with zipfile.ZipFile(temp_docx.name, 'r') as z:
                xml_content = z.read('word/document.xml').decode('utf-8')
        
        match = re.search(r'(<m:oMath[^>]*>.*?</m:oMath>)', xml_content, re.DOTALL)
        return match.group(1) if match else None
    
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
    latex_raw = latex_raw.replace(r'\dotstan', r'\\cdot \\tan')
    latex_raw = re.sub(r'(?<!\\)(\bln\b|\blog\b|\bsin\b|\bcos\b|\btan\b|\blog_{?\d*}?)', 
                       r'\\\1', latex_raw)
    latex_raw = re.sub(r'(\\Leftrightarrow|\\Rightarrow|\\rightarrow)(?=\w)', r'\1 ', latex_raw)
    latex_raw = latex_raw.replace(r'\\n', r'\n')
    
    latex_raw = latex_raw.strip()
    if not (latex_raw.startswith('$') and latex_raw.endswith('$')):
        latex_raw = f"${latex_raw}$"
    
    return latex_raw


def process_text(text, paragraph, bold=False):
    """Xử lý text có công thức LaTeX"""
    if not text:
        return
    
    text = text.replace("<br>", "\n").replace("<br/>", "\n") \
               .replace("<Br>", "\n").replace("<Br/>", "\n")
    text = re.sub(r'</?(div|p|u|span|font|i|b)\b[^>]*>', '', text)
    text = text.replace("&nbsp;", "").replace("&lt;", "").replace("&gt;", "")
    
    pattern = r'(\$[^$]+\$|\\\[.*?\\\])'
    parts = re.split(pattern, text)
    
    for part in parts:
        if not part:
            continue
        
        if part.startswith('$') or part.startswith('\\['):
            try:
                latex_expr = clean_latex_math(part)
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


def handle_image_generation(description, doc):
    """Xử lý sinh ảnh với kích thước vừa phải và căn giữa"""
    try:
        print(f" \n → Đang sinh ảnh: {description[:50]}... \n")
        image_bytes = generate_image_from_text(description)
        
        # Tạo paragraph mới cho ảnh
        img_paragraph = doc.add_paragraph()
        
        # Thêm ảnh với kích thước nhỏ hơn (2.5 inches ~ 6.35cm)
        run = img_paragraph.add_run()
        picture = run.add_picture(BytesIO(image_bytes), width=Inches(3))
        
        # Căn giữa ảnh bằng cách set alignment cho paragraph
        img_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Thêm spacing sau ảnh
        img_paragraph.paragraph_format.space_after = Pt(6)
        
        print("\n  ✓ Đã sinh ảnh thành công\n")
        return True, img_paragraph
    
    except Exception as e:
        print(f"\n  ✗ Không thể sinh ảnh: {e}\n")
        # Tạo placeholder với căn giữa
        img_paragraph = doc.add_paragraph()
        img_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = img_paragraph.add_run(f"[HÌNH ẢNH MINH HỌA: {description}]")
        run.font.color.rgb = RGBColor(128, 128, 128)
        run.italic = True
        run.font.size = Pt(9)
        return False, img_paragraph


def process_bold_text(text, paragraph):
    """Xử lý text có **bold**"""
    current_text = text
    
    while "**" in current_text:
        start_bold = current_text.find("**")
        end_bold = current_text.find("**", start_bold + 2)
        
        if start_bold == -1 or end_bold == -1:
            process_text(current_text, paragraph)
            break
        
        # Text trước **
        if start_bold > 0:
            process_text(current_text[:start_bold], paragraph)
        
        # Text in đậm
        bold_text = current_text[start_bold + 2:end_bold]
        process_text(bold_text, paragraph, bold=True)
        
        # Phần còn lại
        current_text = current_text[end_bold + 2:]
    
    # Text cuối cùng
    if current_text:
        process_text(current_text, paragraph)


def response2docx_improved(file_paths, prompt, output_filename, project_id, 
                          creds, model_name, question_type="tracnghiem"):
    """
    Hàm cải tiến sinh DOCX với format chuẩn
    
    question_type: "tracnghiem" (80 câu) hoặc "dungsai" (40 câu)
    Format theo prompt:
    
    TRẮC NGHIỆM:
    **Câu X:**
    [Đề bài - nội dung văn bản]
    [HÌNH ẢNH nếu có]
    
    A. [Đáp án 1]
    B. [Đáp án 2]
    C. [Đáp án 3]
    D. [Đáp án 4]
    
    Lời giải:
    [X] (số thứ tự 1-4)
    ####
    [Giải thích chi tiết]
    
    ĐÚNG/SAI:
    **Câu X:**
    [Đoạn văn liền mạch 50-100 từ]
    [HÌNH ẢNH nếu có]
    
    a) [Phát biểu 1]
    b) [Phát biểu 2]
    c) [Phát biểu 3]
    d) [Phát biểu 4]
    
    Lời giải:
    1010 (1=Đúng, 0=Sai)
    ####
    - [Nội dung phát biểu] là ĐÚNG/SAI.
    Giải thích chi tiết (ít nhất 3 dòng)...
    """
    try:
        print(f"\n=== Bắt đầu sinh {question_type} ===\n")
        
        # 1. Gọi API
        client = VertexClient(project_id, creds, model_name)
        AIresponse = client.send_data_to_AI(prompt, file_paths)
        
        # 2. Kiểm tra lại
        prompt_check = f'''Tôi có một đề bao gồm các câu hỏi sau:
```
{AIresponse}
```
Bạn hãy kiểm tra đề đó theo các yêu cầu sau:
* Yêu cầu về tính đúng sai:
- Nếu đề bài sai, sinh lại toàn bộ đề bài và lời giải của câu hỏi đó.
- Nếu lời giải (hoặc giải thích) sai, sinh lại lời giải (giải thích) chính xác. Độ dài ít nhất 4 dòng (60 từ).
* Yêu cầu về nội dung:
- Nếu lời giải ngắn, sinh lại lời giải dài ít nhất 4 dòng (60 từ).
- Nếu các công thức toán học chưa được biểu diễn dưới dạng LaTeX, chuyển toàn bộ công thức toán học sang dạng LaTeX (Kể cả số mũ hay chỉ số).
* Yêu cầu trả về:
- Trả về duy nhất đề bài bao gồm toàn bộ câu hỏi.
- Lược bỏ tất cả những phần không liên quan đến các câu hỏi: "Tất nhiên rồi,...", "Tôi sẽ...", "Tôi hiểu...",...
'''
        
        print("\n  → Đang kiểm tra và tối ưu nội dung...\n")
        AIresponse_final = client.send_data_to_check(prompt=prompt_check)
        print("\n  ✓ Đã nhận phản hồi từ AI\n")
        
        # 3. Tạo document
        doc = Document()
        lines = AIresponse_final.split("\n")
        
        image_failed_count = 0
        in_question = False
        in_loi_giai = False
        waiting_for_separator = False
        question_content_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # 1. Phát hiện tiêu đề câu hỏi: **Câu X:** hoặc Câu X:
            if re.match(r'^\*?\*?Câu\s+\d+[:\.]?\*?\*?', line, re.IGNORECASE):
                # Thêm khoảng cách trước câu mới (trừ câu đầu)
                if in_question:
                    doc.add_paragraph()
                
                in_question = True
                in_loi_giai = False
                waiting_for_separator = False
                question_content_lines = []
                
                # Xử lý tiêu đề câu
                question_para = doc.add_paragraph()
                question_text = line.replace("**", "").strip()
                run = question_para.add_run(question_text)
                run.bold = True
                run.font.size = Pt(12)
                
                i += 1
                continue
            
            # 2. Xử lý hình ảnh
            if re.search(r'\[?\s*(HÌNH ẢNH|Hình ảnh|hình ảnh)', line, re.IGNORECASE):
                # Extract mô tả
                cleaned = re.sub(r'\[?\s*(HÌNH ẢNH|Hình ảnh|hình ảnh)\s*[:\]]?', '', line, flags=re.IGNORECASE)
                cleaned = cleaned.replace("[", "").replace("]", "").strip()
                
                if cleaned:
                    success, img_para = handle_image_generation(cleaned, doc)
                    if not success:
                        image_failed_count += 1
                
                i += 1
                continue
            
            # 3. Xử lý đáp án A, B, C, D (trắc nghiệm) hoặc a), b), c), d) (đúng/sai)
            if re.match(r'^[A-Da-d][\.\)]', line):
                answer_para = doc.add_paragraph()
                process_text(line, answer_para)
                
                i += 1
                continue
            
            # 4. Phát hiện "Lời giải:" hoặc "**Lời giải:**"
            if re.match(r'^\*?\*?Lời giải[:\.]?\*?\*?', line, re.IGNORECASE):
                in_loi_giai = True
                waiting_for_separator = False
                
                # Thêm dòng trống trước "Lời giải:"
                doc.add_paragraph()
                
                solution_para = doc.add_paragraph()
                solution_text = line.replace("**", "").strip()
                run = solution_para.add_run(solution_text)
                run.bold = True
                
                i += 1
                continue
            
            # 5. Xử lý đáp án đúng sau "Lời giải:"
            # - Trắc nghiệm: 1, 2, 3, 4 (số đơn)
            # - Đúng/sai: 1010, 0101, ... (chuỗi 4 ký tự 0/1)
            if in_loi_giai and not waiting_for_separator:
                # Kiểm tra đúng/sai: 1010, 0110, ...
                if re.match(r'^[01]{4}$', line.strip()):
                    answer_para = doc.add_paragraph()
                    run = answer_para.add_run(line.strip())
                    run.bold = True
                    waiting_for_separator = True
                    i += 1
                    continue
                
                # Kiểm tra trắc nghiệm: 1, 2, 3, 4
                if re.match(r'^[1-4]$', line.strip()):
                    answer_para = doc.add_paragraph()
                    run = answer_para.add_run(line.strip())
                    run.bold = True
                    waiting_for_separator = True
                    i += 1
                    continue
            
            # 6. Xử lý dấu phân cách ####
            if line.strip() == "####":
                separator_para = doc.add_paragraph()
                run = separator_para.add_run("####")
                run.bold = True
                waiting_for_separator = False
                
                i += 1
                continue
            
            # 7. Xử lý heading (##, ###)
            if line.startswith("### "):
                heading_text = line.replace("### ", "").strip()
                doc.add_heading(heading_text, level=3)
                i += 1
                continue
            
            if line.startswith("## "):
                heading_text = line.replace("## ", "").strip()
                doc.add_heading(heading_text, level=2)
                i += 1
                continue
            
            if line.startswith("# "):
                heading_text = line.replace("# ", "").strip()
                doc.add_heading(heading_text, level=1)
                i += 1
                continue
            
            # 8. Xử lý text thông thường (đề bài, giải thích)
            paragraph = doc.add_paragraph()
            if "**" in line:
                process_bold_text(line, paragraph)
            else:
                process_text(line, paragraph)
            
            i += 1
        
        # 4. Lưu file
        output_path = f"{output_filename}.docx"
        doc.save(output_path)
        
        print(f"\n  ✓ Đã lưu file: {output_path}")
        if image_failed_count > 0:
            print(f"  ⚠️ {image_failed_count} hình ảnh không sinh được (đã thêm placeholder)")
        
        return output_path
    
    except Exception as e:
        print(f"✗ LỖI NGHIÊM TRỌNG: {e}")
        traceback.print_exc()
        return None