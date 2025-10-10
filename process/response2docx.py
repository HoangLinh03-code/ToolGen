
# from docx import Document
# from api.callAPI import VertexClient
# from process.text2Image import generate_image_from_text
# from docx.shared import Inches, Pt, RGBColor
# from docx.enum.text import WD_ALIGN_PARAGRAPH
# from io import BytesIO
# import zipfile, subprocess, re
# from tempfile import NamedTemporaryFile
# from docx.oxml import parse_xml
# import traceback

# def latex_to_omml_via_pandoc(latex_math_dollar):
#     """Chuyển đổi LaTeX sang OMML qua Pandoc"""
#     try:
#         with NamedTemporaryFile(suffix=".docx", delete=False) as temp_docx:
#             result = subprocess.run(
#                 ['pandoc', '--from=latex', '--to=docx', '-o', temp_docx.name],
#                 input=latex_math_dollar,
#                 text=True,
#                 capture_output=True,
#                 creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
#             )

#             if result.returncode != 0:
#                 print(f"⚠️ Pandoc error: {result.stderr}")
#                 return None
            
#             with zipfile.ZipFile(temp_docx.name, 'r') as z:
#                 xml_content = z.read('word/document.xml').decode('utf-8')
        
#         match = re.search(r'(<m:oMath[^>]*>.*?</m:oMath>)', xml_content, re.DOTALL)
#         return match.group(1) if match else None
    
#     except Exception as e:
#         print(f"Lỗi latex_to_omml: {e}")
#         return None


# def insert_equation_into_paragraph(latex_math_dollar, paragraph):
#     """Chèn công thức toán học vào paragraph"""
#     omml_str = latex_to_omml_via_pandoc(latex_math_dollar)
    
#     if not omml_str:
#         paragraph.add_run(f" [{latex_math_dollar}] ")
#         return
    
#     if 'xmlns:m=' not in omml_str:
#         omml_str = re.sub(
#             r'<m:oMath',
#             r'<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"',
#             omml_str,
#             count=1
#         )
    
#     try:
#         omml_element = parse_xml(omml_str)
#         run = paragraph.add_run()
#         run._r.append(omml_element)
#     except Exception as e:
#         print(f"Lỗi chèn equation: {e}")
#         paragraph.add_run(f" [{latex_math_dollar}] ")


# def clean_latex_math(latex_raw):
#     """Làm sạch và chuẩn hóa LaTeX"""
#     latex_raw = re.sub(r'\\/', '', latex_raw)
#     latex_raw = re.sub(r'\\operatorname\s*{\s*([^}]*)\s*}', 
#                        lambda m: m.group(1).replace(' ', ''), latex_raw)
#     latex_raw = re.sub(r'\\root\s*(\d+)\s*{([^}]*)}', r'\\sqrt[\1]{\2}', latex_raw)
#     latex_raw = re.sub(r'\\root\s*{(\d+)}\s*\\of\s*{([^}]*)}', r'\\sqrt[\1]{\2}', latex_raw)
#     latex_raw = re.sub(r'\\root\s*(\d+)\s*\\sqrt\s*{([^}]*)}', r'\\sqrt[\1]{\2}', latex_raw)
#     latex_raw = re.sub(r'([a-zA-Z])\s*\\frac\s*{([^}]+)}\s*{([^}]+)}', 
#                        r'\1^{\\frac{\2}{\3}}', latex_raw)
#     latex_raw = re.sub(r'\\sp\s*{([^}]*)}', r'^{\1}', latex_raw)
#     latex_raw = re.sub(r'{\\bf\s*([^}]*)}', r'\1', latex_raw)
#     latex_raw = re.sub(r'\\\s*log', r'\\log', latex_raw)
#     latex_raw = re.sub(r'\\bigskip', '', latex_raw)
#     latex_raw = re.sub(r'\\nonumber', '', latex_raw)
#     latex_raw = latex_raw.replace(r'\?', '?')
#     latex_raw = re.sub(r'\\cdot\s*(?=\w)', r'\\cdot ', latex_raw)
#     latex_raw = latex_raw.replace(r'\dotstan', r'\\cdot \\tan')
#     latex_raw = re.sub(r'(?<!\\)(\bln\b|\blog\b|\bsin\b|\bcos\b|\btan\b|\blog_{?\d*}?)', 
#                        r'\\\1', latex_raw)
#     latex_raw = re.sub(r'(\\Leftrightarrow|\\Rightarrow|\\rightarrow)(?=\w)', r'\1 ', latex_raw)
#     latex_raw = latex_raw.replace(r'\\n', r'\n')
    
#     latex_raw = latex_raw.strip()
#     if not (latex_raw.startswith('$') and latex_raw.endswith('$')):
#         latex_raw = f"${latex_raw}$"
    
#     return latex_raw


# def process_text(text, paragraph, bold=False):
#     """Xử lý text có công thức LaTeX"""
#     if not text:
#         return
    
#     text = text.replace("<br>", "\n").replace("<br/>", "\n") \
#                .replace("<Br>", "\n").replace("<Br/>", "\n")
#     text = re.sub(r'</?(div|p|u|span|font|i|b)\b[^>]*>', '', text)
#     text = text.replace("&nbsp;", "").replace("&lt;", "").replace("&gt;", "")
    
#     pattern = r'(\$[^$]+\$|\\\[.*?\\\])'
#     parts = re.split(pattern, text)
    
#     for part in parts:
#         if not part:
#             continue
        
#         if part.startswith('$') or part.startswith('\\['):
#             try:
#                 latex_expr = clean_latex_math(part)
#                 insert_equation_into_paragraph(latex_expr, paragraph)
#             except Exception as e:
#                 print(f"Lỗi xử lý LaTeX: {e}")
#                 run = paragraph.add_run(part)
#                 if bold:
#                     run.bold = True
#         else:
#             cleaned_part = re.sub(r'^\s*/', '', part)
#             run = paragraph.add_run(cleaned_part)
#             if bold:
#                 run.bold = True


# def handle_image_generation(description, doc):
#     """Xử lý sinh ảnh với kích thước vừa phải và căn giữa"""
#     try:
#         print(f" \n → Đang sinh ảnh: {description[:50]}... \n")
#         image_bytes = generate_image_from_text(description)
        
#         img_paragraph = doc.add_paragraph()
#         img_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
#         run = img_paragraph.add_run()
#         run.add_picture(BytesIO(image_bytes), width=Inches(2.5))
        
#         print("\n  ✓ Đã sinh ảnh thành công\n")
#         return True, img_paragraph
    
#     except Exception as e:
#         print(f"\n  ✗ Không thể sinh ảnh: {e}\n")
#         img_paragraph = doc.add_paragraph()
#         img_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
#         run = img_paragraph.add_run(f"[HÌNH ẢNH MINH HỌA: {description}]")
#         run.font.color.rgb = RGBColor(128, 128, 128)
#         run.italic = True
#         run.font.size = Pt(9)
#         return False, img_paragraph


# def process_bold_text(text, paragraph):
#     """Xử lý text có **bold**"""
#     current_text = text
    
#     while "**" in current_text:
#         start_bold = current_text.find("**")
#         end_bold = current_text.find("**", start_bold + 2)
        
#         if start_bold == -1 or end_bold == -1:
#             process_text(current_text, paragraph)
#             break
        
#         if start_bold > 0:
#             process_text(current_text[:start_bold], paragraph)
        
#         bold_text = current_text[start_bold + 2:end_bold]
#         process_text(bold_text, paragraph, bold=True)
        
#         current_text = current_text[end_bold + 2:]
    
#     if current_text:
#         process_text(current_text, paragraph)


# def count_questions_in_response(response_text, question_type):
#     """
#     Đếm số câu hỏi trong response từ AI
    
#     Args:
#         response_text: Nội dung response từ AI
#         question_type: "tracnghiem" hoặc "dungsai"
    
#     Returns:
#         int: Số câu hỏi đếm được
#     """
#     # Đếm số lần xuất hiện của pattern "Câu X:" hoặc "**Câu X:**"
#     pattern = r'\*?\*?Câu\s+\d+[:\.]?\*?\*?'
#     matches = re.findall(pattern, response_text, re.IGNORECASE)
#     count = len(matches)
    
#     print(f"\n📊 Phát hiện {count} câu hỏi trong response ({question_type})")
#     return count


# def generate_retry_prompt(original_prompt, missing_count, question_type, previous_response):
#     """
#     Tạo prompt yêu cầu sinh thêm câu hỏi còn thiếu
    
#     Args:
#         original_prompt: Prompt gốc
#         missing_count: Số câu còn thiếu
#         question_type: "tracnghiem" hoặc "dungsai"
#         previous_response: Response trước đó (để tránh trùng lặp)
    
#     Returns:
#         str: Prompt mới
#     """
#     if question_type == "tracnghiem":
#         total_required = 80
#         question_desc = "trắc nghiệm 4 đáp án"
#     else:
#         total_required = 40
#         question_desc = "đúng/sai (4 phát biểu a,b,c,d)"
    
#     retry_prompt = f"""
# ⚠️ CẢNH BÁO: Response trước đó THIẾU {missing_count} câu hỏi!

# YÊU CẦU:
# - Tạo CHÍNH XÁC {total_required} câu hỏi {question_desc}
# - Hiện tại chỉ có {total_required - missing_count} câu
# - Cần bổ sung thêm {missing_count} câu còn thiếu

# 🚨 QUAN TRỌNG:
# 1. Đảm bảo đủ {total_required} câu, không thiếu, không thừa
# 2. Các câu mới KHÔNG được trùng lặp với câu đã có
# 3. Tuân thủ CHÍNH XÁC format và yêu cầu trong prompt gốc
# 4. Phân bố đều theo các mức độ và phần nội dung như yêu cầu

# 📝 CÁC CÂU ĐÃ CÓ (để tránh trùng lặp):
# {previous_response[:2000]}...
# [Đã cắt bớt để tiết kiệm token]

# ---

# {original_prompt}

# 🎯 LƯU Ý ĐẶC BIỆT: 
# - Trả về đầy đủ {total_required} câu (bao gồm cả câu cũ + câu mới)
# - Đánh số lại từ Câu 1 đến Câu {total_required}
# - Kiểm tra kỹ trước khi trả về
# """
    
#     return retry_prompt


# def response2docx_improved(file_paths, prompt, output_filename, project_id, 
#                           creds, model_name, question_type="tracnghiem",
#                           max_retries=3):
#     """
#     Hàm cải tiến sinh DOCX với kiểm soát số lượng câu hỏi
    
#     Args:
#         file_paths: Danh sách file PDF
#         prompt: Prompt gốc
#         output_filename: Tên file output
#         project_id: Google Cloud project ID
#         creds: Credentials
#         model_name: Tên model AI
#         question_type: "tracnghiem" (80 câu) hoặc "dungsai" (40 câu)
#         max_retries: Số lần retry tối đa nếu thiếu câu
    
#     Returns:
#         str: Đường dẫn file output hoặc None nếu lỗi
#     """
#     try:
#         print(f"\n=== Bắt đầu sinh {question_type} ===\n")
        
#         # Xác định số câu yêu cầu
#         required_count = 80 if question_type == "tracnghiem" else 40
        
#         client = VertexClient(project_id, creds, model_name)
        
#         # Vòng lặp retry
#         for attempt in range(max_retries):
#             print(f"\n🔄 Lần thử {attempt + 1}/{max_retries}")
            
#             # Gọi API lần đầu hoặc retry
#             if attempt == 0:
#                 print("  → Gửi prompt gốc...")
#                 AIresponse = client.send_data_to_AI(prompt, file_paths)
#             else:
#                 print(f"  → Retry với prompt bổ sung (thiếu {missing_count} câu)...")
#                 retry_prompt = generate_retry_prompt(
#                     prompt, missing_count, question_type, AIresponse
#                 )
#                 AIresponse = client.send_data_to_AI(retry_prompt, file_paths)
            
#             # Đếm số câu
#             question_count = count_questions_in_response(AIresponse, question_type)
            
#             # Kiểm tra đủ số câu chưa
#             if question_count >= required_count:
#                 print(f"  ✅ Đủ {question_count}/{required_count} câu!")
#                 break
#             else:
#                 missing_count = required_count - question_count
#                 print(f"  ⚠️ Thiếu {missing_count} câu ({question_count}/{required_count})")
                
#                 if attempt == max_retries - 1:
#                     print(f"  ❌ Đã thử {max_retries} lần nhưng vẫn thiếu câu!")
#                     print(f"  ⚠️ Tiếp tục xử lý với {question_count} câu hiện có...")
#                 else:
#                     print(f"  🔄 Sẽ thử lại lần {attempt + 2}...")
        
#         # 2. Kiểm tra lại nội dung
#         prompt_check = f'''Tôi có một đề bao gồm các câu hỏi sau:
# ```
# {AIresponse}
# ```
# Bạn hãy kiểm tra đề đó theo các yêu cầu sau:
# * Yêu cầu về tính đúng sai:
# - Nếu đề bài sai, sinh lại toàn bộ đề bài và lời giải của câu hỏi đó.
# - Nếu lời giải (hoặc giải thích) sai, sinh lại lời giải (giải thích) chính xác. Độ dài ít nhất 4 dòng (60 từ).
# * Yêu cầu về nội dung:
# - Nếu lời giải ngắn, sinh lại lời giải dài ít nhất 4 dòng (60 từ).
# - Nếu các công thức toán học chưa được biểu diễn dưới dạng LaTeX, chuyển toàn bộ công thức toán học sang dạng LaTeX (Kể cả số mũ hay chỉ số).
# * Yêu cầu trả về:
# - Trả về duy nhất đề bài bao gồm toàn bộ câu hỏi.
# - Lược bỏ tất cả những phần không liên quan đến các câu hỏi: "Tất nhiên rồi,...", "Tôi sẽ...", "Tôi hiểu...",...
# - 🚨 QUAN TRỌNG: Đảm bảo đủ {required_count} câu hỏi, không thiếu!
# '''
        
#         print("\n  → Đang kiểm tra và tối ưu nội dung...\n")
#         AIresponse_final = client.send_data_to_check(prompt=prompt_check)
        
#         # Đếm lại sau khi check
#         final_count = count_questions_in_response(AIresponse_final, question_type)
#         print(f"\n📊 Số câu sau khi check: {final_count}/{required_count}")
        
#         if final_count < required_count:
#             print(f"⚠️ CẢNH BÁO: Vẫn thiếu {required_count - final_count} câu sau khi check!")
        
#         print("\n  ✓ Đã nhận phản hồi từ AI\n")
        
#         # 3. Tạo document
#         doc = Document()
#         lines = AIresponse_final.split("\n")
        
#         image_failed_count = 0
#         in_question = False
#         in_loi_giai = False
#         waiting_for_separator = False
#         question_content_lines = []
        
#         i = 0
#         while i < len(lines):
#             line = lines[i].strip()
            
#             if not line:
#                 i += 1
#                 continue
            
#             # 1. Phát hiện tiêu đề câu hỏi
#             if re.match(r'^\*?\*?Câu\s+\d+[:\.]?\*?\*?', line, re.IGNORECASE):
#                 if in_question:
#                     doc.add_paragraph()
                
#                 in_question = True
#                 in_loi_giai = False
#                 waiting_for_separator = False
#                 question_content_lines = []
                
#                 question_para = doc.add_paragraph()
#                 question_text = line.replace("**", "").strip()
#                 run = question_para.add_run(question_text)
#                 run.bold = True
#                 run.font.size = Pt(12)
                
#                 i += 1
#                 continue
            
#             # 2. Xử lý hình ảnh
#             if re.search(r'\[?\s*(HÌNH ẢNH|Hình ảnh|hình ảnh)', line, re.IGNORECASE):
#                 cleaned = re.sub(r'\[?\s*(HÌNH ẢNH|Hình ảnh|hình ảnh)\s*[:\]]?', '', line, flags=re.IGNORECASE)
#                 cleaned = cleaned.replace("[", "").replace("]", "").strip()
                
#                 if cleaned:
#                     success, img_para = handle_image_generation(cleaned, doc)
#                     if not success:
#                         image_failed_count += 1
                
#                 i += 1
#                 continue
            
#             # 3. Xử lý đáp án A, B, C, D (trắc nghiệm) hoặc a), b), c), d) (đúng/sai)
#             if re.match(r'^[A-Da-d][\.\)]', line):
#                 answer_para = doc.add_paragraph()
#                 process_text(line, answer_para)
                
#                 i += 1
#                 continue
            
#             # 4. Phát hiện "Lời giải:"
#             if re.match(r'^\*?\*?Lời giải[:\.]?\*?\*?', line, re.IGNORECASE):
#                 in_loi_giai = True
#                 waiting_for_separator = False
                
#                 doc.add_paragraph()
                
#                 solution_para = doc.add_paragraph()
#                 solution_text = line.replace("**", "").strip()
#                 run = solution_para.add_run(solution_text)
#                 run.bold = True
                
#                 i += 1
#                 continue
            
#             # 5. Xử lý đáp án đúng
#             if in_loi_giai and not waiting_for_separator:
#                 # Đúng/sai: 1010, 0110, ...
#                 if re.match(r'^[01]{4}$', line.strip()):
#                     answer_para = doc.add_paragraph()
#                     run = answer_para.add_run(line.strip())
#                     run.bold = True
#                     waiting_for_separator = True
#                     i += 1
#                     continue
                
#                 # Trắc nghiệm: 1, 2, 3, 4
#                 if re.match(r'^[1-4]$', line.strip()):
#                     answer_para = doc.add_paragraph()
#                     run = answer_para.add_run(line.strip())
#                     run.bold = True
#                     waiting_for_separator = True
#                     i += 1
#                     continue
            
#             # 6. Xử lý dấu phân cách ####
#             if line.strip() == "####":
#                 separator_para = doc.add_paragraph()
#                 run = separator_para.add_run("####")
#                 run.bold = True
#                 waiting_for_separator = False
                
#                 i += 1
#                 continue
            
#             # 7. Xử lý heading
#             if line.startswith("### "):
#                 heading_text = line.replace("### ", "").strip()
#                 doc.add_heading(heading_text, level=3)
#                 i += 1
#                 continue
            
#             if line.startswith("## "):
#                 heading_text = line.replace("## ", "").strip()
#                 doc.add_heading(heading_text, level=2)
#                 i += 1
#                 continue
            
#             if line.startswith("# "):
#                 heading_text = line.replace("# ", "").strip()
#                 doc.add_heading(heading_text, level=1)
#                 i += 1
#                 continue
            
#             # 8. Xử lý text thông thường
#             paragraph = doc.add_paragraph()
#             if "**" in line:
#                 process_bold_text(line, paragraph)
#             else:
#                 process_text(line, paragraph)
            
#             i += 1
        
#         # 4. Lưu file
#         output_path = f"{output_filename}.docx"
#         doc.save(output_path)
        
#         print(f"\n  ✓ Đã lưu file: {output_path}")
#         print(f"  📊 Tổng kết: {final_count}/{required_count} câu")
#         if image_failed_count > 0:
#             print(f"  ⚠️ {image_failed_count} hình ảnh không sinh được (đã thêm placeholder)")
        
#         return output_path
    
#     except Exception as e:
#         print(f"✗ LỖI NGHIÊM TRỌNG: {e}")
#         traceback.print_exc()
#         return None

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
        
        img_paragraph = doc.add_paragraph()
        img_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        run = img_paragraph.add_run()
        run.add_picture(BytesIO(image_bytes), width=Inches(2.5))
        
        print("\n  ✓ Đã sinh ảnh thành công\n")
        return True, img_paragraph
    
    except Exception as e:
        print(f"\n  ✗ Không thể sinh ảnh: {e}\n")
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
        
        if start_bold > 0:
            process_text(current_text[:start_bold], paragraph)
        
        bold_text = current_text[start_bold + 2:end_bold]
        process_text(bold_text, paragraph, bold=True)
        
        current_text = current_text[end_bold + 2:]
    
    if current_text:
        process_text(current_text, paragraph)


def count_questions_in_response(response_text, question_type):
    """Đếm số câu hỏi trong response từ AI"""
    pattern = r'\*?\*?Câu\s+\d+[:\.]?\*?\*?'
    matches = re.findall(pattern, response_text, re.IGNORECASE)
    count = len(matches)
    
    print(f"\n📊 Phát hiện {count} câu hỏi trong response ({question_type})")
    return count


def generate_retry_prompt(original_prompt, missing_count, question_type, previous_response):
    """Tạo prompt yêu cầu sinh thêm câu hỏi còn thiếu"""
    if question_type == "tracnghiem":
        total_required = 80
        question_desc = "trắc nghiệm 4 đáp án"
    else:
        total_required = 40
        question_desc = "đúng/sai (4 phát biểu a,b,c,d)"
    
    retry_prompt = f"""
⚠️ CẢNH BÁO: Response trước đó THIẾU {missing_count} câu hỏi!

YÊU CẦU:
- Tạo CHÍNH XÁC {total_required} câu hỏi {question_desc}
- Hiện tại chỉ có {total_required - missing_count} câu
- Cần bổ sung thêm {missing_count} câu còn thiếu

🚨 QUAN TRỌNG:
1. Đảm bảo đủ {total_required} câu, không thiếu, không thừa
2. Các câu mới KHÔNG được trùng lặp với câu đã có
3. Tuân thủ CHÍNH XÁC format và yêu cầu trong prompt gốc
4. Phân bố đều theo các mức độ và phần nội dung như yêu cầu

📝 CÁC CÂU ĐÃ CÓ (để tránh trùng lặp):
{previous_response[:2000]}...
[Đã cắt bớt để tiết kiệm token]

---

{original_prompt}

🎯 LƯU Ý ĐẶC BIỆT: 
- Trả về đầy đủ {total_required} câu (bao gồm cả câu cũ + câu mới)
- Đánh số lại từ Câu 1 đến Câu {total_required}
- Kiểm tra kỹ trước khi trả về
"""
    
    return retry_prompt


def response2docx_improved(file_paths, prompt, output_filename, project_id, 
                          creds, model_name, question_type="tracnghiem",
                          max_retries=3):
    """
    Hàm cải tiến sinh DOCX với kiểm soát số lượng câu hỏi
    """
    try:
        print(f"\n=== Bắt đầu sinh {question_type} ===\n")
        
        # Xác định số câu yêu cầu
        required_count = 80 if question_type == "tracnghiem" else 40
        
        client = VertexClient(project_id, creds, model_name)
        
        # Vòng lặp retry
        for attempt in range(max_retries):
            print(f"\n🔄 Lần thử {attempt + 1}/{max_retries}")
            
            # Gọi API lần đầu hoặc retry
            if attempt == 0:
                print("  → Gửi prompt gốc...")
                AIresponse = client.send_data_to_AI(prompt, file_paths)
            else:
                print(f"  → Retry với prompt bổ sung (thiếu {missing_count} câu)...")
                retry_prompt = generate_retry_prompt(
                    prompt, missing_count, question_type, AIresponse
                )
                AIresponse = client.send_data_to_AI(retry_prompt, file_paths)
            
            # Đếm số câu
            question_count = count_questions_in_response(AIresponse, question_type)
            
            # Kiểm tra đủ số câu chưa
            if question_count >= required_count:
                print(f"  ✅ Đủ {question_count}/{required_count} câu!")
                break
            else:
                missing_count = required_count - question_count
                print(f"  ⚠️ Thiếu {missing_count} câu ({question_count}/{required_count})")
                
                if attempt == max_retries - 1:
                    print(f"  ❌ Đã thử {max_retries} lần nhưng vẫn thiếu câu!")
                    print(f"  ⚠️ Tiếp tục xử lý với {question_count} câu hiện có...")
                else:
                    print(f"  🔄 Sẽ thử lại lần {attempt + 2}...")
        
        # 2. Kiểm tra lại nội dung
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
- 🚨 QUAN TRỌNG: Đảm bảo đủ {required_count} câu hỏi, không thiếu!
- 🚨 ĐẶC BIỆT: Giữ nguyên thứ tự format:
  + Câu X. [Nội dung câu hỏi]
  + [HÌNH ẢNH: ...] (nếu có - phải sau đề bài, trước các đáp án)
  + A. [Đáp án 1]
  + B. [Đáp án 2]
  + C. [Đáp án 3]
  + D. [Đáp án 4]
  + Lời giải
  + Đáp án đúng: [X]
  + ####
  + Giải thích: [Chi tiết]
'''
        
        print("\n  → Đang kiểm tra và tối ưu nội dung...\n")
        AIresponse_final = client.send_data_to_check(prompt=prompt_check)
        
        # Đếm lại sau khi check
        final_count = count_questions_in_response(AIresponse_final, question_type)
        print(f"\n📊 Số câu sau khi check: {final_count}/{required_count}")
        
        if final_count < required_count:
            print(f"⚠️ CẢNH BÁO: Vẫn thiếu {required_count - final_count} câu sau khi check!")
        
        print("\n  ✓ Đã nhận phản hồi từ AI\n")
        
        # 3. Tạo document với STATE MACHINE rõ ràng
        doc = Document()
        lines = AIresponse_final.split("\n")
        
        # STATE MACHINE
        class State:
            IDLE = 0
            IN_QUESTION = 1
            IN_ANSWERS = 2
            IN_SOLUTION_HEADER = 3
            IN_SOLUTION_ANSWER = 4
            IN_SOLUTION_EXPLAIN = 5
        
        current_state = State.IDLE
        image_failed_count = 0
        current_question_has_image = False
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # 1. Phát hiện tiêu đề câu hỏi (BẮT ĐẦU CÂU MỚI)
            if re.match(r'^\*?\*?Câu\s+\d+[\.:]\*?\*?', line, re.IGNORECASE):
                # Reset state cho câu mới
                current_state = State.IN_QUESTION
                current_question_has_image = False
                
                # Thêm khoảng cách giữa các câu
                if i > 0:
                    doc.add_paragraph()
                
                # Tạo tiêu đề câu hỏi
                question_para = doc.add_paragraph()
                question_text = line.replace("**", "").strip()
                run = question_para.add_run(question_text)
                run.bold = True
                run.font.size = Pt(12)
                
                i += 1
                continue
            
            # 2. Xử lý HÌNH ẢNH (CHỈ trong state IN_QUESTION, trước đáp án)
            if current_state == State.IN_QUESTION and \
               re.search(r'\[?\s*(HÌNH ẢNH|Hình ảnh)', line, re.IGNORECASE):
                
                cleaned = re.sub(r'\[?\s*(HÌNH ẢNH|Hình ảnh)\s*[:\]]?', '', 
                                line, flags=re.IGNORECASE)
                cleaned = cleaned.replace("[", "").replace("]", "").strip()
                
                if cleaned and not current_question_has_image:
                    success, img_para = handle_image_generation(cleaned, doc)
                    if not success:
                        image_failed_count += 1
                    current_question_has_image = True
                
                i += 1
                continue
            
            # 3. Xử lý ĐỀ BÀI (text sau tiêu đề câu, trước đáp án)
            if current_state == State.IN_QUESTION and \
               not re.match(r'^[A-D][\.\)]', line):
                
                # Đây là nội dung đề bài
                question_content_para = doc.add_paragraph()
                if "**" in line:
                    process_bold_text(line, question_content_para)
                else:
                    process_text(line, question_content_para)
                
                i += 1
                continue
            
            # 4. Xử lý ĐÁP ÁN A, B, C, D
            answer_match = re.match(r'^([A-D])[\.\)]\s*(.+)', line)
            if answer_match and current_state in [State.IN_QUESTION, State.IN_ANSWERS]:
                current_state = State.IN_ANSWERS
                
                answer_letter = answer_match.group(1)
                answer_content = answer_match.group(2).strip()
                
                answer_para = doc.add_paragraph()
                
                # In đậm chữ cái đáp án
                run_letter = answer_para.add_run(f"{answer_letter}. ")
                run_letter.bold = True
                
                # Nội dung đáp án
                process_text(answer_content, answer_para)
                
                i += 1
                continue
            
            # 5. Phát hiện "Lời giải:"
            if re.match(r'^\*?\*?Lời giải[:\.]?\*?\*?', line, re.IGNORECASE):
                current_state = State.IN_SOLUTION_HEADER
                
                doc.add_paragraph()
                
                solution_para = doc.add_paragraph()
                solution_text = line.replace("**", "").strip()
                run = solution_para.add_run(solution_text)
                run.bold = True
                
                i += 1
                continue
            
            # 6. Xử lý "Đáp án đúng: X"
            if current_state == State.IN_SOLUTION_HEADER and \
               re.match(r'Đáp án đúng:', line, re.IGNORECASE):
                
                answer_para = doc.add_paragraph()
                process_text(line, answer_para)
                
                i += 1
                continue
            
            # 7. Xử lý đáp án đúng (1010 hoặc 1,2,3,4)
            if current_state == State.IN_SOLUTION_HEADER:
                # Đúng/sai: 1010, 0110, ...
                if re.match(r'^[01]{4}$', line.strip()):
                    current_state = State.IN_SOLUTION_ANSWER
                    answer_para = doc.add_paragraph()
                    run = answer_para.add_run(line.strip())
                    run.bold = True
                    i += 1
                    continue
                
                # Trắc nghiệm: 1, 2, 3, 4
                if re.match(r'^[1-4]$', line.strip()):
                    current_state = State.IN_SOLUTION_ANSWER
                    answer_para = doc.add_paragraph()
                    run = answer_para.add_run(line.strip())
                    run.bold = True
                    i += 1
                    continue
            
            # 8. Xử lý dấu phân cách ####
            if line.strip() == "####":
                current_state = State.IN_SOLUTION_EXPLAIN
                
                separator_para = doc.add_paragraph()
                run = separator_para.add_run("####")
                run.bold = True
                
                i += 1
                continue
            
            # 9. Xử lý GIẢI THÍCH (không cho phép chèn ảnh)
            if current_state == State.IN_SOLUTION_EXPLAIN:
                # BẮT BUỘC: Không xử lý hình ảnh trong phần giải thích
                # Chỉ xử lý text
                
                if line.startswith("Giải thích:"):
                    explain_para = doc.add_paragraph()
                    run = explain_para.add_run("Giải thích:")
                    run.bold = True
                    
                    # Phần text sau "Giải thích:"
                    remaining = line[len("Giải thích:"):].strip()
                    if remaining:
                        process_text(remaining, explain_para)
                else:
                    # Text giải thích thông thường
                    explain_para = doc.add_paragraph()
                    if "**" in line:
                        process_bold_text(line, explain_para)
                    else:
                        process_text(line, explain_para)
                
                i += 1
                continue
            
            # 10. Xử lý heading
            if line.startswith("### "):
                heading_text = line.replace("### ", "").strip()
                doc.add_heading(heading_text, level=3)
                current_state = State.IDLE
                i += 1
                continue
            
            if line.startswith("## "):
                heading_text = line.replace("## ", "").strip()
                doc.add_heading(heading_text, level=2)
                current_state = State.IDLE
                i += 1
                continue
            
            if line.startswith("# "):
                heading_text = line.replace("# ", "").strip()
                doc.add_heading(heading_text, level=1)
                current_state = State.IDLE
                i += 1
                continue
            
            # 11. Xử lý text thông thường (fallback)
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
        print(f"  📊 Tổng kết: {final_count}/{required_count} câu")
        if image_failed_count > 0:
            print(f"  ⚠️ {image_failed_count} hình ảnh không sinh được (đã thêm placeholder)")
        
        return output_path
    
    except Exception as e:
        print(f"✗ LỖI NGHIÊM TRỌNG: {e}")
        traceback.print_exc()
        return None