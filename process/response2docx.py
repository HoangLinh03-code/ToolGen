from docx import Document
from api.callAPI import VertexClient
from process.text2Image import generate_image_from_text
from docx.shared import Inches, Pt, RGBColor
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
        # Fallback: Thêm text thuần nếu không convert được
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


def handle_image_generation(description, doc, paragraph):
    """Xử lý sinh ảnh với fallback"""
    try:
        print(f"  → Đang sinh ảnh: {description[:50]}...")
        image_bytes = generate_image_from_text(description)
        
        section = doc.sections[0]
        usable_width = section.page_width - section.left_margin - section.right_margin
        doc.add_picture(BytesIO(image_bytes), width=usable_width)
        
        print("  ✓ Đã sinh ảnh thành công")
        return True
    
    except Exception as e:
        print(f"  ✗ Không thể sinh ảnh: {e}")
        # Thêm placeholder thay vì crash
        run = paragraph.add_run(f"\n[HÌNH ẢNH MINH HỌA: {description}]\n")
        run.font.color.rgb = RGBColor(255, 0, 0)  # Màu đỏ
        run.italic = True
        return False


def parse_dungsai_answer(answer_line):
    """
    Parse dòng đáp án đúng/sai
    Input: "1010" hoặc "ĐSĐS" hoặc "a) Đ, b) S, c) Đ, d) S"
    Output: ['Đ', 'S', 'Đ', 'S']
    """
    answer_line = answer_line.strip().upper()
    
    # Kiểu 1: 1010
    if re.match(r'^[01]+$', answer_line):
        return ['Đ' if c == '1' else 'S' for c in answer_line]
    
    # Kiểu 2: ĐSĐS
    if re.match(r'^[ĐDS]+$', answer_line):
        return list(answer_line)
    
    # Kiểu 3: a) Đ, b) S...
    matches = re.findall(r'[ĐDS]', answer_line)
    if matches:
        return matches
    
    return []


def response2docx_improved(file_paths, prompt, output_filename, project_id, 
                          creds, model_name, question_type="tracnghiem"):
    """
    Hàm cải tiến sinh DOCX với xử lý lỗi tốt hơn
    
    question_type: "tracnghiem" (80 câu) hoặc "dungsai" (40 câu)
    """
    try:
        print(f"\n=== Bắt đầu sinh {question_type} ===\n")
        
        # 1. Gọi API
        client = VertexClient(project_id, creds, model_name)
        AIresponse = client.send_data_to_AI(prompt, file_paths)
        
        # 2. Kiểm tra lại (check prompt)
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
        parts = AIresponse_final.split("\n")
        
        image_failed_count = 0
        
        for idx, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            
            # Xử lý hình ảnh
            if ("Hình ảnh:" in part) or ("HÌNH ẢNH:" in part) or ("hình ảnh:" in part):
                paragraph = doc.add_paragraph()
                
                # Xử lý bold text nếu có
                if "**" in part:
                    process_bold_text(part, paragraph)
                
                # Extract mô tả ảnh
                cleaned_part = part.replace("[", "").replace("]", "") \
                                  .replace("Hình ảnh:", "").replace("HÌNH ẢNH:", "") \
                                  .replace("hình ảnh:", "").replace("**", "").strip()
                
                if cleaned_part:
                    success = handle_image_generation(cleaned_part, doc, paragraph)
                    if not success:
                        image_failed_count += 1
                    
                    # Thêm mô tả text
                    run = paragraph.add_run(f"\n[Mô tả ảnh: {cleaned_part}]\n")
                    run.font.size = Pt(9)
                    run.italic = True
                
                continue
            
            # Xử lý heading
            if part.startswith("### "):
                heading_text = part.replace("### ", "").strip()
                doc.add_heading(heading_text, level=3)
                continue
            
            if part.startswith("## "):
                heading_text = part.replace("## ", "").strip()
                doc.add_heading(heading_text, level=2)
                continue
            
            if part.startswith("# "):
                heading_text = part.replace("# ", "").strip()
                doc.add_heading(heading_text, level=1)
                continue
            
            # Xử lý đáp án đúng/sai (dạng đặc biệt)
            if question_type == "dungsai":
                # Phát hiện dòng đáp án: 1010 hoặc ĐSĐS
                if re.match(r'^[01ĐSDS]{4}, part.strip().upper()$', part):
                    answers = parse_dungsai_answer(part)
                    if answers:
                        paragraph = doc.add_paragraph()
                        labels = ['a)', 'b)', 'c)', 'd)']
                        answer_text = ', '.join([f"{labels[i]} {answers[i]}" for i in range(len(answers))])
                        run = paragraph.add_run(answer_text)
                        run.bold = True
                        continue
            
            # Xử lý text thông thường với bold
            paragraph = doc.add_paragraph()
            if "**" in part:
                process_bold_text(part, paragraph)
            else:
                process_text(part, paragraph)
        
        # 4. Lưu file
        output_path = f"{output_filename}.docx"
        doc.save(output_path)
        
        print(f"  ✓ Đã lưu file: {output_path}")
        if image_failed_count > 0:
            print(f"  ⚠️ {image_failed_count} hình ảnh không sinh được (đã thêm placeholder)")
        
        return output_path
    
    except Exception as e:
        print(f"✗ LỖI NGHIÊM TRỌNG: {e}")
        traceback.print_exc()
        return None


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