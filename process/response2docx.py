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
from process.ques_valid import validate_and_fix_response
from process.PDF_Scan import enhance_prompt_with_pdf_scan, regenerate_missing_questions
from enum import Enum

def validate_and_regenerate_if_needed(AIresponse_final, enhanced_prompt, 
                                      all_allowed_topics, all_keywords,
                                      client, question_type, max_attempts=3):
    """
    Kiểm tra câu hỏi, nếu không đúng format/chủ đề thì sinh lại
    """
    from process.ques_valid import QuestionValidator, validate_question_topic
    from difflib import SequenceMatcher
    
    attempt = 0
    current_text = AIresponse_final
    required_count = 80 if question_type == "tracnghiem" else 40
    
    while attempt < max_attempts:
        attempt += 1
        print(f"\n{'='*70}")
        print(f"LẦN KIỂM TRA & SINH LẠI {attempt}/{max_attempts}")
        print(f"{'='*70}")
        
        validator = QuestionValidator(question_type=question_type)
        parsed_questions = validator.parse_questions(current_text)
        
        # 1. Kiểm tra format
        invalid_validations, missing_nums = validator.validate_all_questions(current_text)
        
        # 2. Kiểm tra chủ đề
        off_topic_questions = []
        for q_num, q_text in parsed_questions.items():
            if not validate_question_topic(q_text, all_allowed_topics, all_keywords):
                off_topic_questions.append(q_num)
        
        # 3. Kiểm tra header thừa
        header_pattern = re.compile(r'(MỨC\s+ĐỘ|LEVEL|PHẦN\s+\d+|###?\s+)', re.IGNORECASE)
        header_found = bool(re.search(header_pattern, current_text))
        
        print(f"\n📊 KẾT QUẢ KIỂM TRA:")
        print(f"   - Tổng câu: {len(parsed_questions)}/{required_count}")
        print(f"   - Format hợp lệ: {len(parsed_questions) - len(invalid_validations)}")
        print(f"   - Format lỗi: {len(invalid_validations)}")
        if off_topic_questions:
            print(f"   - Lạc chủ đề: {len(off_topic_questions)} (câu {off_topic_questions[:5]}...)")
        if missing_nums:
            print(f"   - Thiếu câu: {len(missing_nums)} (câu {missing_nums[:5]}...)")
        if header_found:
            print(f"   - Có header thừa: Có")
            
        # 4. Kiểm tra trùng lặp giữa các câu
        duplicate_pairs = []
        questions_list = list(parsed_questions.items())
        
        for i, (num1, text1) in enumerate(questions_list):
            content1 = re.sub(r'\*\*Câu\s+\d+:?\*\*', '', text1).strip()
            content1 = content1.split('**Lời giải:**')[0].strip()[:250]
            
            for num2, text2 in questions_list[i+1:]:
                content2 = re.sub(r'\*\*Câu\s+\d+:?\*\*', '', text2).strip()
                content2 = content2.split('**Lời giải:**')[0].strip()[:250]
                
                similarity = SequenceMatcher(None, content1, content2).ratio()
                if similarity > 0.65:
                    duplicate_pairs.append((num1, num2, similarity))
                    
        print(f"\n📊 KẾT QUẢ KIỂM TRA:")
        
        # 👇 THÊM THÔNG BÁO TRÙNG
        if duplicate_pairs:
            print(f"   - Trùng lặp: {len(duplicate_pairs)} cặp")
            for num1, num2, sim in duplicate_pairs[:3]:
                print(f"      • Câu {num1} ≈ Câu {num2} ({sim*100:.1f}%)")
        
        
        # Nếu hết lỗi -> OK
        if (not invalid_validations and not off_topic_questions and 
            not missing_nums and not header_found):
            print(f"\n✅ ĐẬT TIÊU CHUẨN! Không cần sinh lại.")
            return current_text
        
        # Nếu vẫn còn lỗi và còn lần -> Sinh lại
        if attempt < max_attempts:
            print(f"\n🔄 Còn lỗi, yêu cầu sinh lại (lần {attempt+1})...")
            
            problems = []
            if invalid_validations:
                problem_nums = [v.question_num for v in invalid_validations[:5]]
                problems.append(f"Format lỗi câu: {problem_nums}")
            if off_topic_questions:
                problems.append(f"Lạc chủ đề câu: {off_topic_questions[:5]}")
            if missing_nums:
                problems.append(f"Thiếu câu: {missing_nums[:5]}")
            if duplicate_pairs:
                dup_nums = [f"{n1}-{n2}" for n1, n2, _ in duplicate_pairs[:3]]
                problems.append(f"Trùng lặp: {', '.join(dup_nums)}")
            if header_found:
                problems.append("Có header thừa cần xóa")
            
            regenerate_prompt = f"""{enhanced_prompt}

⚠️ **CẢNH BÁO - CẤP ĐỘ CAO: CẦN SỬA NGAY**

Những lỗi phát hiện:
{chr(10).join([f'  • {p}' for p in problems])}

**YÊU CẦU SỬA CHỮA BẮTBUỘC:**
1. XÓA HOÀN TOÀN mọi dòng tiêu đề mức độ (VD: "MỨC ĐỘ NHẬN BIẾT", "LEVEL...")
2. CHỈ GIỮ format câu hỏi chuẩn, không thêm header hay giới thiệu nào
3. Định dạng bắt buộc: **Câu X:** + nội dung + 4 đáp án (A,B,C,D) + **Lời giải:** + mã đáp án + #### + giải thích
4. TUYỆT ĐỐI KHÔNG thêm bất kỳ text mở đầu/kết luận nào ngoài các câu hỏi
5. Mỗi câu PHẢI liên quan ĐẾN (không phải trích từ) allowed_topics: {list(all_allowed_topics)[:3]}...
6. Nội dung câu hỏi phải SÁNG TẠO, không copy nguyên văn từ tài liệu

Hãy sửa/sinh lại toàn bộ và trả về CHỈ nội dung câu hỏi, không có bất kỳ text khác.
"""
            
            try:
                fixed_response = client.send_data_to_check(
                    prompt=regenerate_prompt,
                    temperature=0.5  # Giảm nhiệt độ để ổn định hơn
                )
                
                # Làm sạch response
                fixed_response = clean_level_headers(fixed_response)
                current_text = fixed_response
                
            except Exception as e:
                print(f"❌ Lỗi khi gọi API sửa: {e}")
                return current_text
        else:
            # Hết lần -> dừng
            print(f"\n❌ Đã chạy {max_attempts} lần vẫn còn lỗi.")
            print(f"Gợi ý: Kiểm tra prompt hoặc model được sử dụng.")
            return current_text
    
    return current_text


# ============ LATEX & EQUATION FUNCTIONS ============
# (Giữ nguyên các hàm latex như cũ - không thay đổi)



def latex_to_omml_via_pandoc(latex_math_dollar):
    try:
        with NamedTemporaryFile(suffix=".docx", delete=False) as temp_docx:
            result = subprocess.run(
                ['pandoc', '--from=latex', '--to=docx', '-o', temp_docx.name],
                input=latex_math_dollar, text=True, capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
        if result.returncode != 0: return None
        with zipfile.ZipFile(temp_docx.name, 'r') as z:
            xml_content = z.read('word/document.xml').decode('utf-8')
        match = re.search(r'(<m:oMath[^>]*>.*?</m:oMath>)', xml_content, re.DOTALL)
        return match.group(1) if match else None
    except Exception: return None


def insert_equation_into_paragraph(latex_math_dollar, paragraph):
    omml_str = latex_to_omml_via_pandoc(latex_math_dollar)
    if not omml_str:
        paragraph.add_run(f" [{latex_math_dollar}] ")
        return
    if 'xmlns:m=' not in omml_str:
        omml_str = re.sub(r'<m:oMath', r'<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"', omml_str, count=1)
    try:
        omml_element = parse_xml(omml_str)
        run = paragraph.add_run()
        run._r.append(omml_element)
    except Exception:
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
                run = paragraph.add_run(part)
                if bold:
                    run.bold = True
        else:
            cleaned_part = re.sub(r'^\s*/', '', part)
            run = paragraph.add_run(cleaned_part)
            if bold:
                run.bold = True

def process_bold_text(text, paragraph):
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


def handle_image_generation(description, doc):
    """Xử lý sinh ảnh với kích thước và căn giữa"""
    try:
        print(f"   → Đang sinh ảnh: {description[:50]}...")
        image_bytes = generate_image_from_text(description)
        
        img_paragraph = doc.add_paragraph()
        img_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        run = img_paragraph.add_run()
        run.add_picture(BytesIO(image_bytes), width=Inches(3.5))
        
        print("     ✓ Đã sinh ảnh thành công")
        return True, img_paragraph
    
    except Exception as e:
        print(f"     ✗ Không thể sinh ảnh: {e}")
        img_paragraph = doc.add_paragraph()
        img_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = img_paragraph.add_run(f"[HÌNH ẢNH MINH HỌA: {description}]")
        run.font.color.rgb = RGBColor(128, 128, 128)
        run.italic = True
        return False, img_paragraph


# ============ DETECTION FUNCTIONS ============
# (Giữ nguyên các hàm detection như cũ)

def is_image_line(line):
    return bool(re.search(r'\[?\s*(HÌNH ẢNH|Hình ảnh|hình ảnh)', line, re.IGNORECASE))

def extract_image_description(line):
    cleaned = re.sub(r'\[?\s*(HÌNH ẢNH|Hình ảnh|hình ảnh)\s*[:\]]?', '', line, flags=re.IGNORECASE)
    cleaned = cleaned.replace("[", "").replace("]", "").strip()
    return cleaned

def is_question_title(line):
    return bool(re.match(r'^\*?\*?Câu\s+\d+[:\.]?\*?\*?', line, re.IGNORECASE))

def is_answer_option(line):
    return bool(re.match(r'^[A-Da-d][\.\)]', line.strip()))

def is_solution_header(line):
    return bool(re.match(r'^\*?\*?Lời giải[:\.]?\*?\*?', line, re.IGNORECASE))

def is_correct_answer(line):
    stripped = line.strip()
    return bool(re.match(r'^[1-4]$', stripped) or re.match(r'^[01]{4}$', stripped))

def is_separator(line):
    return line.strip() == "####"

def is_heading(line):
    return bool(re.match(r'^#{1,3}\s+', line))


# ============ QUESTION STATE MACHINE ============
# (Giữ nguyên QuestionState và QuestionBuffer như cũ)

class QuestionState(Enum):
    IDLE = "idle"
    IN_TITLE = "in_title"
    IN_CONTENT = "in_content"
    WAITING_IMAGE = "waiting_image"
    IN_ANSWERS = "in_answers"
    IN_SOLUTION_HEADER = "in_solution_header"
    IN_CORRECT_ANSWER = "in_correct_answer"
    AFTER_SEPARATOR = "after_separator"
    IN_EXPLANATION = "in_explanation"


class QuestionBuffer:
    def __init__(self):
        self.question_num = 0
        self.title = ""
        self.content_lines = []
        self.image_description = None
        self.answers = []
        self.solution_header = ""
        self.correct_answer = ""
        self.explanation_lines = []
        self.state = QuestionState.IDLE
    
    def reset(self):
        self.__init__()
    
    def has_content(self):
        return len(self.content_lines) > 0
    
    def has_answers(self):
        return len(self.answers) >= 4
    
    def has_explanation(self):
        return len(self.explanation_lines) > 0
    
    def is_complete(self):
        return (
            self.title and
            self.has_content() and
            self.has_answers() and
            self.solution_header and
            self.correct_answer and
            self.has_explanation()
        )
    
    def flush_to_doc(self, doc):
        if not self.is_complete():
            missing = []
            if not self.title:
                missing.append("tiêu đề")
            if not self.has_content():
                missing.append("nội dung")
            if not self.has_answers():
                missing.append(f"đáp án ({len(self.answers)}/4)")
            if not self.solution_header:
                missing.append("lời giải header")
            if not self.correct_answer:
                missing.append("đáp án đúng")
            if not self.has_explanation():
                missing.append("giải thích")
            
            print(f"   ⚠️ Câu {self.question_num} THIẾU: {', '.join(missing)}")
            return False
        
        # 1. Thêm tiêu đề
        title_para = doc.add_paragraph()
        run = title_para.add_run(self.title)
        run.bold = True
        run.font.size = Pt(12)
        
        # 2. Thêm nội dung
        for line in self.content_lines:
            if line.strip():
                para = doc.add_paragraph()
                if "**" in line:
                    process_bold_text(line, para)
                else:
                    process_text(line, para)
        
        # 3. Thêm hình ảnh (nếu có)
        if self.image_description:
            handle_image_generation(self.image_description, doc)
        
        # 4. Thêm đáp án
        for answer in self.answers:
            answer_para = doc.add_paragraph()
            process_text(answer, answer_para)
        
        # 5. Thêm khoảng cách trước lời giải
        doc.add_paragraph()
        
        # 6. Thêm lời giải header
        solution_para = doc.add_paragraph()
        run = solution_para.add_run(self.solution_header)
        run.bold = True
        
        # 7. Thêm đáp án đúng
        answer_para = doc.add_paragraph()
        run = answer_para.add_run(self.correct_answer)
        run.bold = True
        
        # 8. Thêm separator
        separator_para = doc.add_paragraph()
        run = separator_para.add_run("####")
        run.bold = True
        
        # 9. Thêm giải thích
        for line in self.explanation_lines:
            if line.strip():
                para = doc.add_paragraph()
                if "**" in line:
                    process_bold_text(line, para)
                else:
                    process_text(line, para)
        
        print(f"   ✅ Câu {self.question_num}: Đã ghi vào document")
        return True


# ============ MAIN FUNCTION V3 WITH PDF SCANNER ============
def clean_level_headers(text: str) -> str:
    """Xóa header mức độ không cần thiết từ response"""
    # Xóa các pattern như "MỨC ĐỘ NHẬN BIẾT", "MỨC ĐỘ THÔNG HIỂU", etc.
    patterns_to_remove = [
        r'\n*MỨC\s+ĐỘ\s+\w+\n*',
        r'\n*LEVEL\s+\w+\n*',
        r'\n*### MỨC.*?\n',
        r'\n*## PHẦN.*?\n'
    ]
    
    result = text
    for pattern in patterns_to_remove:
        result = re.sub(pattern, '\n', result, flags=re.IGNORECASE)
    
    # Dọn sạch multiple newlines
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def response2docx_improved(file_paths, prompt, output_filename, project_id, 
                     creds, model_name, question_type="tracnghiem"):
    """
    VERSION 3: Tích hợp PDF Scanner và Missing Question Fixer
    
    Cải tiến mới:
    1. Quét 3 file PDF (SGK, SBT, SGV) để hiểu chủ đề
    2. Tạo topic guide để sinh câu hỏi không lạc đề
    3. Tự động sinh lại câu thiếu với nội dung hoàn toàn khác
    4. Kiểm tra trùng lặp giữa các lần sinh
    """
    try:
        print(f"\n{'='*70}")
        print(f"SINH {question_type.upper()} - VERSION 3 (PDF SCANNER)")
        print(f"{'='*70}\n")
        
        required_count = 80 if question_type == "tracnghiem" else 40
        print(f"Yêu cầu: {required_count} câu\n")
        
        # ============ BƯỚC 0: QUÉT PDF VÀ CẢI THIỆN PROMPT ============
        print(f"{'='*70}")
        print("BƯỚC 0: QUÉT PDF VÀ TẠO TOPIC GUIDE")
        print(f"{'='*70}\n")
        
        enhanced_prompt,all_allowed_topics, all_keywords = enhance_prompt_with_pdf_scan(
            prompt, file_paths, project_id, creds
        )
        
        # ============ BƯỚC 1: BATCH PROCESSING ============
        print(f"{'='*70}")
        print("BƯỚC 1: GEN THEO BATCH")
        print(f"{'='*70}\n")
        
        client = VertexClient(project_id, creds, model_name)
        
        all_responses = []
        generated_count = 0
        MAX_QUESTIONS_PER_REQUEST = 20
        max_attempts = 5
        attempt = 0
        
        while generated_count < required_count and attempt < max_attempts:
            attempt += 1
            remaining = required_count - generated_count
            batch_count = min(MAX_QUESTIONS_PER_REQUEST, remaining)
            
            print(f"\n{'─'*70}")
            print(f"Lần {attempt}: Sinh câu {generated_count+1} đến {generated_count+batch_count}")
            print(f"{'─'*70}")
            
            if generated_count == 0:
                batch_prompt = enhanced_prompt
                print(f"(Lần đầu - gồm cả file PDF và topic guide)")
                batch_response = client.send_data_to_AI(
                    batch_prompt, 
                    file_paths,
                    temperature=0.75
                )
                batch_response = clean_level_headers(batch_response)
            else:
                previous_response = all_responses[-1]
                last_questions = re.findall(r'(\*\*Câu\s+\d+:.*?####.*?)(?=\*\*Câu|\Z)', previous_response, re.DOTALL)
                context_snippet = "\n\n".join(last_questions[-2:])
                batch_prompt = f"""{enhanced_prompt}

**[KIỂM SOÁT CHẤT LƯỢNG - BẮT BUỘC]**
1. TỪ CÂU {generated_count+1} ĐẾN {generated_count+batch_count}
2. KHÔNG sinh header mức độ (VD: "MỨC ĐỘ NHẬN BIẾT") - chỉ sinh nội dung câu
3. KIỂM TRA TỰ: Mỗi câu PHẢI liên quan TRỰ TIẾP đến: {list(all_allowed_topics)[:5]}...
4. TUYỆT ĐỐI KHÔNG lạc sang chủ đề khác ngoài pạm vi trên

YÊU CẦU THÊM CÂU HỎI:
- Bối cảnh: Bạn đã sinh thành công {generated_count} câu. Đây là 2 câu cuối cùng bạn đã làm:
---
{context_snippet}
---
- Nhiệm vụ: Bây giờ, hãy sinh {batch_count} câu hỏi TIẾP THEO (từ câu {generated_count+1} đến {generated_count+batch_count}).
- **MỆNH LỆNH:**
    - TUYỆT ĐỐI KHÔNG sinh lại các câu đã sinh
    - Mỗi câu PHẢI ĐẦY ĐỦ: tiêu đề, nội dung, 4 đáp án, lời giải, giải thích
    - BÁM SÁT chủ đề đã được định nghĩa trong PHẠM VI CHỦ ĐỀ VÀ KIẾN THỨC
    - KHÔNG LẠC ĐỀ sang chủ đề khác
    - KHÔNG THÊM LỜI MỞ ĐẦU HOẶC KẾT LUẬN
"""
                print(f"(Lần {attempt} - không có file PDF)")
                batch_response = client.send_data_to_check(
                    prompt=batch_prompt,
                    temperature=0.8
                )
                # 👇 THÊM ĐOẠN NÀY NGAY SAU
                # Kiểm tra trùng lặp với câu đã có
                from process.ques_valid import QuestionValidator
                validator = QuestionValidator(question_type=question_type)
                new_questions = validator.parse_questions(batch_response)
                existing_questions = validator.parse_questions("\n\n".join(all_responses))

                # Lọc bỏ câu trùng
                duplicates = []
                for new_num, new_text in new_questions.items():
                    new_content = re.sub(r'\*\*Câu\s+\d+:?\*\*', '', new_text).strip()[:200]
                    for exist_num, exist_text in existing_questions.items():
                        exist_content = re.sub(r'\*\*Câu\s+\d+:?\*\*', '', exist_text).strip()[:200]
                        # So sánh độ giống nhau (dùng difflib)
                        from difflib import SequenceMatcher
                        similarity = SequenceMatcher(None, new_content, exist_content).ratio()
                        if similarity > 0.7:  # Trùng > 70%
                            duplicates.append(new_num)
                            break

                if duplicates:
                    print(f"   ⚠️ Phát hiện {len(duplicates)} câu trùng lặp, yêu cầu sinh lại...")
                    # Không thêm vào all_responses, sinh lại batch
                    continue  # Quay lại đầu vòng while

                all_responses.append(batch_response)
            
            # Đếm câu trong batch
            batch_questions = len(re.findall(r'\*?\*?Câu\s+\d+', batch_response, re.IGNORECASE))
            print(f"Kết quả batch: {batch_questions} câu (yêu cầu {batch_count})")
            
            # Cập nhật count
            combined_text = "\n\n".join(all_responses)
            current_count = len(re.findall(r'\*?\*?Câu\s+\d+', combined_text, re.IGNORECASE))
            print(f"Tổng cộng: {current_count}/{required_count} câu")
            
            generated_count = current_count
        
        final_response = "\n\n".join(all_responses)
        
        # ============ BƯỚC 2: VALIDATE & FIX ============
        print(f"\n{'='*70}")
        print("BƯỚC 2: VALIDATE & AUTO-FIX")
        print(f"{'='*70}\n")
        
        AIresponse_final = validate_and_fix_response(
            final_response,
            enhanced_prompt,
            client,
            question_type
        )
        
        print(f"\n{'='*70}")
        print("BƯỚC 2.5: KIỂM TRA CHỦĐỀ & FORMAT CHỈ TỌC")
        print(f"{'='*70}\n")

        AIresponse_final = validate_and_regenerate_if_needed(
            AIresponse_final,
            enhanced_prompt,
            all_allowed_topics,
            all_keywords,
            client,
            question_type,
            max_attempts=3
        )
        
        # ============ BƯỚC 2.5: SINH LẠI CÂU THIẾU (NẾU CÓ) ============
        print(f"\n{'='*70}")
        print("BƯỚC 2.5: KIỂM TRA VÀ SINH LẠI CÂU THIẾU")
        print(f"{'='*70}\n")
        
        # Import validator để kiểm tra
        from process.ques_valid import validate_question_topic, detect_question_level
        from process.ques_valid import QuestionValidator
        validator = QuestionValidator(question_type=question_type)
        parsed_questions = validator.parse_questions(AIresponse_final)
        validations, missing_nums = validator.validate_all_questions(AIresponse_final)
        problematic_questions = []
        level_distribution = {'nhận biết': 0, 'thông hiểu': 0, 'vận dụng': 0, 'vận dụng_cao': 0}
        print(f"\nValidating topics...")
        print(f"  - Allowed topics: {len(all_allowed_topics)}")
        print(f"  - Allowed keywords: {len(all_keywords)}\n")
        for q_num, q_text in parsed_questions.items():
            # Kiểm tra chủ đề
            is_on_topic = validate_question_topic(q_text, all_allowed_topics, all_keywords)
            if not is_on_topic:
                problematic_questions.append((q_num, "lạc chủ đề"))
            
            # Đếm mức độ
            level = detect_question_level(q_text)
            level_distribution[level] += 1

        if validations:
            print(f"\n⚠️ Phát hiện {len(validations)} câu hỏi bị lỗi:")
            for v in validations[:5]:  # Hiển thị 5 câu đầu
                print(f"   - Câu {v.question_num}: {', '.join(v.missing_parts)}")
        else:
            print(f"\n✓ Tất cả câu hỏi đều hợp lệ")
        
        if problematic_questions:
            print(f"\n⚠️ Phát hiện {len(problematic_questions)} câu lạc chủ đề:")
            for q_num, reason in problematic_questions[:5]:
                print(f"   - Câu {q_num}: {reason}")

        print(f"\nPhân bổ mức độ:")
        total_q = len(parsed_questions)
        if total_q > 0:
            print(f"   - Nhận biết: {level_distribution['nhận biết']} ({level_distribution['nhận biết']*100/total_q:.1f}%)")
            print(f"   - Thông hiểu: {level_distribution['thông hiểu']} ({level_distribution['thông hiểu']*100/total_q:.1f}%)")
            print(f"   - Vận dụng: {level_distribution['vận dụng']} ({level_distribution['vận dụng']*100/total_q:.1f}%)")
            print(f"   - Vận dụng cao: {level_distribution['vận dụng_cao']} ({level_distribution['vận dụng_cao']*100/total_q:.1f}%)")
        
        # Nếu vẫn còn câu thiếu, sinh lại
        regeneration_attempts = 0
        max_regeneration_attempts = 3
        
        while missing_nums and regeneration_attempts < max_regeneration_attempts:
            regeneration_attempts += 1
            print(f"\n🔄 Lần sinh lại thứ {regeneration_attempts}/{max_regeneration_attempts}")
            print(f"   Cần sinh lại: {len(missing_nums)} câu\n")
            
            new_questions = regenerate_missing_questions(
                missing_nums,
                enhanced_prompt,
                AIresponse_final,
                project_id,
                creds,
                question_type
            )
            
            if new_questions:
                # Thêm câu mới vào text hiện tại
                AIresponse_final = AIresponse_final + "\n\n" + new_questions
                
                # Validate lại
                validations, missing_nums = validator.validate_all_questions(AIresponse_final)
                
                if not missing_nums:
                    print("✅ Đã sinh đủ tất cả các câu!\n")
                    break
            else:
                print("⚠️ Không thể sinh thêm câu. Dừng lại.\n")
                break
        
        # ============ BƯỚC 3: TẠO DOCUMENT VỚI BUFFER ============
        print(f"\n{'='*70}")
        print("BƯỚC 3: TẠO DOCUMENT VỚI BUFFER")
        print(f"{'='*70}\n")
        
        doc = Document()
        lines = AIresponse_final.split("\n")
        
        buffer = QuestionBuffer()
        image_failed_count = 0
        question_count_in_doc = 0
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # ========== HEADING ==========
            if is_heading(line):
                if buffer.question_num > 0:
                    if buffer.flush_to_doc(doc):
                        question_count_in_doc += 1
                    buffer.reset()
                
                if line.startswith("### "):
                    heading_text = line.replace("### ", "").strip()
                    doc.add_heading(heading_text, level=3)
                elif line.startswith("## "):
                    heading_text = line.replace("## ", "").strip()
                    doc.add_heading(heading_text, level=2)
                elif line.startswith("# "):
                    heading_text = line.replace("# ", "").strip()
                    doc.add_heading(heading_text, level=1)
                
                i += 1
                continue
            
            # ========== QUESTION TITLE ==========
            if is_question_title(line):
                if buffer.question_num > 0:
                    if buffer.flush_to_doc(doc):
                        question_count_in_doc += 1
                        doc.add_paragraph()
                    buffer.reset()
                
                buffer.title = line.replace("**", "").strip()
                buffer.state = QuestionState.IN_TITLE
                
                match = re.match(r'^\*?\*?Câu\s+(\d+)', line)
                if match:
                    buffer.question_num = int(match.group(1))
                    print(f"Câu {buffer.question_num}: {line[:50]}...")
                
                i += 1
                continue
            
            # ========== IMAGE ==========
            if is_image_line(line):
                img_desc = extract_image_description(line)
                if img_desc:
                    buffer.image_description = img_desc
                    print(f"   → Lưu ảnh: {img_desc[:40]}...")
                
                i += 1
                continue
            
            # ========== ANSWER OPTIONS ==========
            if is_answer_option(line):
                buffer.answers.append(line)
                buffer.state = QuestionState.IN_ANSWERS
                print(f"   → Đáp án {len(buffer.answers)}: {line[:35]}...")
                
                i += 1
                continue
            
            # ========== SOLUTION HEADER ==========
            if is_solution_header(line):
                buffer.solution_header = line.replace("**", "").strip()
                buffer.state = QuestionState.IN_SOLUTION_HEADER
                print(f"   → Lời giải")
                
                i += 1
                continue
            
            # ========== CORRECT ANSWER ==========
            if buffer.state == QuestionState.IN_SOLUTION_HEADER and is_correct_answer(line):
                buffer.correct_answer = line.strip()
                buffer.state = QuestionState.IN_CORRECT_ANSWER
                print(f"   → Đáp án đúng: {line.strip()}")
                
                i += 1
                continue
            
            # ========== SEPARATOR #### ==========
            if is_separator(line):
                buffer.state = QuestionState.AFTER_SEPARATOR
                print(f"   → Separator")
                
                i += 1
                continue
            
            # ========== EXPLANATION ==========
            if buffer.state in [QuestionState.AFTER_SEPARATOR, QuestionState.IN_EXPLANATION]:
                if line.strip():
                    buffer.explanation_lines.append(line)
                    buffer.state = QuestionState.IN_EXPLANATION
                    print(f"   → Giải thích: {line[:45]}...")
                
                i += 1
                continue
            
            # ========== QUESTION CONTENT ==========
            if buffer.state in [QuestionState.IN_TITLE, QuestionState.IN_CONTENT]:
                buffer.content_lines.append(line)
                buffer.state = QuestionState.IN_CONTENT
                print(f"   → Nội dung: {line[:45]}...")
                
                i += 1
                continue
            
            i += 1
        
        # ========== FLUSH BUFFER CUỐI CÙNG ==========
        if buffer.question_num > 0:
            if buffer.flush_to_doc(doc):
                question_count_in_doc += 1
        
        # ========== LƯU FILE ==========
        output_path = f"{output_filename}.docx"
        doc.save(output_path)
        
        print(f"\n{'='*70}")
        print(f"✅ HOÀN THÀNH!")
        print(f"{'='*70}")
        print(f"File: {output_path}")
        print(f"Câu hỏi trong document: {question_count_in_doc}/{required_count}")
        if question_count_in_doc < required_count:
            print(f"⚠️  Còn thiếu: {required_count - question_count_in_doc} câu")
        if image_failed_count > 0:
            print(f"Ảnh lỗi: {image_failed_count}")
        print(f"{'='*70}\n")
        
        return output_path
    
    except Exception as e:
        print(f"\n❌ LỖI NGHIÊM TRỌNG: {e}")
        traceback.print_exc()
        return None