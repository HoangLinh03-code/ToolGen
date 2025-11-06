from docx import Document
from api.callAPI import VertexClient
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
import zipfile, subprocess, re
from tempfile import NamedTemporaryFile
from docx.oxml import parse_xml
import traceback
from process.ques_valid import ValidQuestionStorage, regenerate_invalid_questions
from process.text2Image import generate_image_from_text,calculate_optimal_image_count, ImageGenerationTracker
from process.PDF_Scan import enhance_prompt_with_pdf_scan
from enum import Enum

# ============ LATEX & EQUATION FUNCTIONS ============
# (Giữ nguyên các hàm latex như cũ - không thay đổi)

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
                return None
            
            with zipfile.ZipFile(temp_docx.name, 'r') as z:
                xml_content = z.read('word/document.xml').decode('utf-8')
        
        match = re.search(r'(<m:oMath[^>]*>.*?</m:oMath>)', xml_content, re.DOTALL)
        return match.group(1) if match else None
    
    except Exception as e:
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
def sanitize_ai_artifacts(raw_text: str) -> str:
    """Loại bỏ hội thoại/thinking của AI, code fences và tiền tố không mong muốn."""
    if not raw_text:
        return raw_text
    text = raw_text
    # Remove common chat prefixes
    text = re.sub(r'(?im)^\s*(assistant|user|system)\s*:\s*', '', text)
    text = re.sub(r'(?im)^\s*(assistant|bot|ai)\s*(đang|:)?.*$', lambda m: '' if len(m.group(0)) < 60 else m.group(0), text)
    # Remove code fences
    text = re.sub(r'```[a-zA-Z0-9_-]*\n?', '', text)
    text = text.replace('```', '')
    # Remove obvious chain-of-thought markers
    text = re.sub(r'(?im)^(thought|reasoning|chain[- ]of[- ]thought|let\'s|sure,|as an ai).*$', '', text)
    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

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

import os
MAX_RETRIES = int(os.getenv("MAX_IMAGE_RETRIES", "3"))
def handle_image_generation(description, doc, attempt_generate=True, tracker=None):
    """
    Xử lý sinh ảnh với tracking chi tiết và debug
    
    Args:
        description: Mô tả ảnh
        doc: Document object
        attempt_generate: Có thử sinh ảnh không
        tracker: ImageGenerationTracker object
        
    Returns:
        (success, paragraph, is_placeholder)
    """
    from io import BytesIO
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    import time
    
    print(f"\n{'─'*70}")
    print(f"🖼️  HANDLE IMAGE GENERATION")
    print(f"{'─'*70}")
    print(f"📝 Description: {description[:80]}...")
    print(f"🎯 Attempt generate: {attempt_generate}")
    
    img_paragraph = doc.add_paragraph()
    img_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Nếu không thử sinh ảnh, trả về placeholder luôn
    if not attempt_generate:
        print(f"⏭️  Skipping generation (attempt_generate=False)")
        run = img_paragraph.add_run(f"[HÌNH ẢNH MINH HỌA: {description}]")
        run.font.color.rgb = RGBColor(128, 128, 128)
        run.italic = True
        
        if tracker:
            tracker.record_placeholder()
        
        print(f"✅ Added placeholder")
        print(f"{'─'*70}\n")
        return False, img_paragraph, True
    
    # Thử sinh ảnh THẬT
    print(f"🎨 Attempting to generate image...")
    
    try:
        start_time = time.time()
        
        # GỌI HÀM SINH ẢNH
        image_bytes = generate_image_from_text(description, max_retries=MAX_RETRIES)
        
        generation_time = time.time() - start_time
        print(f"⏱️  Generation took {generation_time:.2f}s")
        
        # KIỂM TRA KẾT QUẢ
        if image_bytes is None or len(image_bytes) == 0:
            print(f"❌ Generation returned None or empty bytes")
            print(f"   → Adding placeholder instead")
            
            run = img_paragraph.add_run(f"[HÌNH ẢNH MINH HỌA: {description}]")
            run.font.color.rgb = RGBColor(255, 140, 0)  # Màu cam
            run.italic = True
            run.bold = True
            
            if tracker:
                tracker.record_failed()
                tracker.record_placeholder()
            
            print(f"{'─'*70}\n")
            return False, img_paragraph, True
        
        # THÀNH CÔNG - THÊM ẢNH VÀO DOCUMENT
        print(f"✅ Got image bytes: {len(image_bytes)} bytes")
        print(f"📄 Adding to document...")
        
        run = img_paragraph.add_run()
        run.add_picture(BytesIO(image_bytes), width=Inches(3.5))
        
        print(f"✅ Image added to document successfully")
        
        if tracker:
            tracker.record_success(generation_time)
        
        print(f"{'─'*70}\n")
        return True, img_paragraph, False
    
    except Exception as e:
        print(f"❌ EXCEPTION during image generation:")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        print(f"   → Adding placeholder")
        
        run = img_paragraph.add_run(f"[HÌNH ẢNH MINH HỌA: {description}]")
        run.font.color.rgb = RGBColor(255, 0, 0)  # Màu đỏ
        run.italic = True
        run.bold = True
        
        if tracker:
            tracker.record_failed()
            tracker.record_placeholder()
        
        print(f"{'─'*70}\n")
        return False, img_paragraph, True

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
        self.should_generate_image = True
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
        return len(self.explanation_lines) >= 1
    
    def is_complete(self):
        return (
            self.title and
            self.has_content() and
            self.has_answers() and
            self.solution_header and
            self.correct_answer and
            self.has_explanation()
        )
    
    def _dedupe_answers(self):
        """Giữ tối đa 4 đáp án, loại trùng theo nội dung (không phân biệt chữ A-D)."""
        seen_contents = set()
        unique_answers = []
        for ans in self.answers:
            # Chuẩn hóa nội dung để so trùng: bỏ tiền tố A./B)/... và khoảng trắng
            content = re.sub(r'^[A-Da-d][\.)]\s*', '', ans).strip()
            norm = re.sub(r'\s+', ' ', content.lower())
            if norm in seen_contents:
                continue
            seen_contents.add(norm)
            unique_answers.append(ans)
            if len(unique_answers) == 4:
                break
        self.answers = unique_answers

    def flush_to_doc(self, doc, image_tracker=None, skipped_log=None, written_log=None, question_type="tracnghiem"):
        """
        Ghi câu hỏi vào document
        
        Returns:
            bool - True nếu ghi thành công, False nếu câu không hợp lệ
        """
        # VALIDATION
        if self.answers:
            self._dedupe_answers()

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
            
            print(f"\n   ❌ Câu {self.question_num} THIẾU: {', '.join(missing)} → KHÔNG GHI VÀO DOC\n")
            if skipped_log is not None and self.question_num:
                skipped_log.append(self.question_num)
            return False
        
        print(f"\n{'='*70}")
        print(f"📝 FLUSHING QUESTION {self.question_num} TO DOCUMENT")
        print(f"{'='*70}")
        
        # 1. Thêm tiêu đề
        title_para = doc.add_paragraph()
        run = title_para.add_run(self.title)
        run.bold = True
        run.font.size = Pt(12)
        print(f"✅ Added title")
        
        # 2. Thêm nội dung
        for line in self.content_lines:
            if line.strip():
                para = doc.add_paragraph()
                if "**" in line:
                    process_bold_text(line, para)
                else:
                    process_text(line, para)
        print(f"✅ Added content ({len(self.content_lines)} lines)")
        
        # 3. Thêm hình ảnh (NẾU CÓ) - CHỈ MỘT LẦN!
        if self.image_description:
            print(f"\n🖼️  Processing image:")
            print(f"   Description: {self.image_description[:60]}...")
            print(f"   Should generate: {self.should_generate_image}")
            
            success, img_para, is_placeholder = handle_image_generation(
                self.image_description, 
                doc,
                attempt_generate=self.should_generate_image,
                tracker=image_tracker
            )
            
            if success:
                print(f"   ✅ Image generated successfully")
            else:
                print(f"   📝 Used placeholder")
        else:
            print(f"ℹ️  No image for this question")
        
        # 4. Thêm đáp án
        for answer in self.answers:
            answer_para = doc.add_paragraph()
            process_text(answer, answer_para)
        print(f"✅ Added {len(self.answers)} answers")
        
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
        if question_type == "dungsai":
            explanation_to_write = self.explanation_lines
        else:
            explanation_to_write = self.explanation_lines[:max(1, min(5, len(self.explanation_lines)))]
        
        for line in explanation_to_write:
            if line.strip():
                para = doc.add_paragraph()
                if "**" in line:
                    process_bold_text(line, para)
                else:
                    process_text(line, para)
        print(f"✅ Added explanation ({len(explanation_to_write)} lines)")
        
        print(f"\n✅ Câu {self.question_num}: ÄÃ£ ghi vào document thành công")
        print(f"{'='*70}\n")
        
        if written_log is not None and self.question_num:
            written_log.append(self.question_num)
        
        return True

from typing import List
def add_summary_at_end(doc, question_count_in_doc: int, 
                       required_count: int, 
                       missing_nums: List[int],
                       image_tracker=None):
    """
    Thêm bảng tóm tắt vào CUỐI document (đơn giản hơn)
    """
    # Thêm ngắt trang
    doc.add_page_break()
    
    # Thêm tiêu đề
    heading = doc.add_heading('THÔNG TIN BỔ SUNG', level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Thông tin tổng quan
    para = doc.add_paragraph()
    para.add_run("📊 Số câu hỏi trong đề: ").bold = True
    run = para.add_run(f"{question_count_in_doc}/{required_count}")
    if question_count_in_doc < required_count:
        run.font.color.rgb = RGBColor(255, 0, 0)
    else:
        run.font.color.rgb = RGBColor(0, 128, 0)
    run.bold = True
    run.font.size = Pt(14)
    
    # Thông tin ảnh
    if image_tracker:
        doc.add_paragraph()
        para = doc.add_paragraph()
        para.add_run("🖼️  Thống kê ảnh:").bold = True
        
        para = doc.add_paragraph(style='List Bullet')
        para.add_run(f"Ảnh sinh thành công: {image_tracker.generated_count}")
        
        para = doc.add_paragraph(style='List Bullet')
        para.add_run(f"Ảnh placeholder: {image_tracker.placeholder_count}")
        
        para = doc.add_paragraph(style='List Bullet')
        total_images = image_tracker.generated_count + image_tracker.placeholder_count
        para.add_run(f"Tổng cộng: {total_images}")
    
    # Nếu có câu thiếu
    if missing_nums:
        doc.add_paragraph()
        
        para = doc.add_paragraph()
        run = para.add_run(f"\n⚠️  CÒN THIẾU {len(missing_nums)} CÂU HỎI")
        run.bold = True
        run.font.color.rgb = RGBColor(255, 0, 0)
        run.font.size = Pt(14)
        
        doc.add_paragraph()
        
        para = doc.add_paragraph()
        para.add_run("\n💡 Danh sách câu cần bổ sung:").bold = True
        
        # Chia nhóm 10 câu/dòng
        for i in range(0, len(missing_nums), 10):
            chunk = missing_nums[i:i+10]
            para = doc.add_paragraph(style='List Bullet')
            run = para.add_run("Câu " + ", ".join(map(str, chunk)))
            run.font.color.rgb = RGBColor(255, 0, 0)
        
        doc.add_paragraph()
        
        para = doc.add_paragraph()
        para.add_run("\n📝 Hướng dẫn:").bold = True
        para = doc.add_paragraph()
        para.add_run("\n1. Tìm vị trí các câu thiếu trong đề bài")
        para = doc.add_paragraph()
        para.add_run("\n2. Bổ sung nội dung câu hỏi theo đúng format")
        para = doc.add_paragraph()
        para.add_run("\n3. Đảm bảo câu hỏi có đầy đủ: tiêu đề, nội dung, đáp án, lời giải")
    
    else:
        doc.add_paragraph()
        para = doc.add_paragraph()
        run = para.add_run("✅ CÂU HỎI ĐÃ ĐẦY ĐỦ - NẾU CẦN THÌ BỔ SUNG ẢNH MINH HỌA")
        run.bold = True
        run.font.color.rgb = RGBColor(0, 128, 0)
        run.font.size = Pt(14)



# ============ MAIN FUNCTION V3 WITH PDF SCANNER ============

# ====== CHÚ Ý: MỌI PROMPT TRUYỀN VÀO response2docx_improved PHẢI LÀ prompt động (đã thay thế subject/grade phù hợp), không được truyền gốc từ file =====
def response2docx_improved(file_paths, prompt, output_filename, project_id, 
                           creds, model_name, question_type="tracnghiem"):
    """
    VERSION 4: TỐI ƯU BỘ NHỚ VÀ LOGIC
    CHÚ Ý: prompt truyền vào từ ngoài PHẢI là prompt đã qua replace subject/grade!
    """
    try:
        print(f"\n{'='*70}")
        print(f"SINH {question_type.upper()} - VERSION 4 (OPTIMIZED)")
        print(f"{'='*70}\n")
        
        required_count = 80 if question_type == "tracnghiem" else 40
        target_image_count = calculate_optimal_image_count(required_count)
        
        print(f"📋 Yêu cầu: {required_count} câu")
        print(f"🖼️  Ảnh tối ưu: {target_image_count} ảnh (~15%)\n")
        
        # ============ BƯỚC 0: QUÉT PDF ============
        print(f"{'='*70}")
        print("BƯỚC 0: QUÉT PDF VÀ TẠO TOPIC GUIDE")
        print(f"{'='*70}\n")
        
        enhanced_prompt = enhance_prompt_with_pdf_scan(
            prompt, file_paths, project_id, creds
        )
        
        # ============ KHỞI TẠO STORAGE ============
        storage = ValidQuestionStorage()
        client = VertexClient(project_id, creds, model_name)
        
        # ============ BƯỚC 1: SINH BATCH ĐẦU TIÊN ============
        print(f"\n{'='*70}")
        print("BƯỚC 1: SINH BATCH ĐẦU TIÊN")
        print(f"{'='*70}\n")
        
        # ============ BƯỚC 2: VÒNG LẶP SINH BỔ SUNG ============
        print(f"\n{'='*70}")
        print("BƯỚC 2: SINH BỔ SUNG CÂU THIẾU/LỖI")
        print(f"{'='*70}\n")

        max_rounds = 10  # Tăng số vòng lặp
        round_num = 0

        previous_valid_count = storage.get_valid_count()
        while storage.get_valid_count() < required_count and round_num < max_rounds:
            round_num += 1
            
            # Lấy danh sách câu cần sinh (cả thiếu và lỗi)
            missing_nums = storage.get_missing_nums(required_count)
            
            if not missing_nums:
                print("\n🎉 ĐÃ ĐỦ SỐ LƯỢNG CÂU HỢP LỆ!")
                break
            
            print(f"\n{'─'*70}")
            print(f"\nVòng {round_num}: Còn thiếu {len(missing_nums)} câu\n")
            print(f"Danh sách: {missing_nums[:15]}" + (f"..." if len(missing_nums) > 15 else ""))
            print(f"\n{'─'*70}\n")
            
            # Sinh tối đa 15 câu/lần để tránh quá tải
            batch_size = min(10, len(missing_nums))
            batch_nums = missing_nums[:batch_size]
            
            print(f"\n📤 Yêu cầu AI sinh {len(batch_nums)} câu...")
            
            # Sinh các câu thiếu
            new_text = regenerate_invalid_questions(
                batch_nums,
                enhanced_prompt,  # PHẢI DÙNG PROMPT ĐÃ REPLACE, KHÔNG ĐỌC FILE LẠI!
                storage,
                client,
                question_type,
                max_attempts=7
            )
            
            if not new_text:
                print("⚠️ Không thể sinh thêm. Thử tăng số lần retry hoặc kiểm tra prompt.")
                
                # Thử lại với batch nhỏ hơn
                if batch_size > 5:
                    print(f"🔄 Thử lại với batch nhỏ hơn ({batch_size//2} câu)...")
                    continue
                else:
                    break
            
            current_valid = storage.get_valid_count()
            print(f"\n✓ Hiện có {current_valid}/{required_count} câu hợp lệ")
            
            # Nếu không tiến triển sau 3 vòng liên tiếp, dừng
            if round_num >= 5 and current_valid <= previous_valid_count:
                print("\n⚠️ Không có tiến triển. Dừng lại.\n")
                break
            previous_valid_count = current_valid

            # Kiểm tra cuối cùng
        final_missing = storage.get_missing_nums(required_count)
        if final_missing:
            print(f"\n{'='*70}")
            print(f"\n⚠️  CẢNH BÁO: VẪN CÒN {len(final_missing)} CÂU THIẾU\n")
            print(f"{'='*70}")
            print(f"\nDanh sách: {final_missing[:20]}" + (f"... và {len(final_missing)-20} câu khác" if len(final_missing) > 20 else ""))
            print(f"\n💡 Gợi ý:")
            print(f"\n   - Chạy lại hàm với số vòng lặp cao hơn")
            print(f"\n   - Kiểm tra prompt có rõ ràng không")
            print(f"\n   - Kiểm tra PDF có đủ nội dung không")
            print(f"{'='*70}\n")
        
        # ============ BƯỚC 3: TẠO DOCUMENT ============
        print(f"\n{'='*70}")
        print("\nBƯỚC 3: TẠO DOCUMENT\n")
        print(f"{'='*70}\n")
        
        doc = Document()
        target_image_count = calculate_optimal_image_count(required_count)
        image_tracker = ImageGenerationTracker(target_image_count)

        print(f"🖼️  Mục tiêu ảnh: {target_image_count} (~15%)")
        
        # Ghép lại text từ storage
        final_text = storage.reconstruct_full_text()
        # Làm sạch hội thoại AI trước khi xử lý
        final_text = sanitize_ai_artifacts(final_text)
        lines = final_text.split("\n")
        
        question_count_in_doc = 0  # Số câu hợp lệ trong document
        skipped_or_failed_nums = []  # Theo dõi câu bị bỏ qua/không ghi được
        written_nums = []  # Theo dõi câu thực sự đã ghi vào DOCX
        
        buffer = QuestionBuffer()
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # ========== HEADING ==========
            if is_heading(line):
                if buffer.question_num > 0:
                    if buffer.flush_to_doc(doc, image_tracker, skipped_log=skipped_or_failed_nums, written_log=written_nums, question_type=question_type):
                        question_count_in_doc += 1  # CHỈ TĂNG NẾU GHI THÀNH CÔNG
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
                    if buffer.flush_to_doc(doc, image_tracker, skipped_log=skipped_or_failed_nums, written_log=written_nums, question_type=question_type):
                        question_count_in_doc += 1  # CHỈ TĂNG NẾU GHI THÀNH CÔNG
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
            
            # ========== IMAGE (LOGIC TỐI ƯU) ==========
            if is_image_line(line):
                img_desc = extract_image_description(line)
                
                if img_desc:
                    # Quyết định có sinh ảnh thật không
                    should_gen = image_tracker.should_generate(
                        buffer.question_num, 
                        required_count
                    )
                    
                    # Lưu mô tả + flag
                    buffer.image_description = img_desc
                    buffer.should_generate_image = should_gen
                    
                    if should_gen:
                        print(f"\n   → Sẽ sinh ảnh {image_tracker.generated_count + 1}/{target_image_count}\n")
                    else:
                        print(f"   → Sẽ dùng placeholder\n")
                
                i += 1
                continue
            
            # ========== ANSWER OPTIONS ==========
            if is_answer_option(line):
                buffer.answers.append(line)
                buffer.state = QuestionState.IN_ANSWERS
                print(f"   → Đáp án {len(buffer.answers)}\n")
                i += 1
                continue
            
            # ========== SOLUTION HEADER ==========
            if is_solution_header(line):
                buffer.solution_header = line.replace("**", "").strip()
                buffer.state = QuestionState.IN_SOLUTION_HEADER
                print(f"   → Lời giải\n")
                i += 1
                continue
            
            # ========== CORRECT ANSWER ==========
            if buffer.state == QuestionState.IN_SOLUTION_HEADER and is_correct_answer(line):
                buffer.correct_answer = line.strip()
                buffer.state = QuestionState.IN_CORRECT_ANSWER
                print(f"   → Đáp án: {line.strip()}\n")
                i += 1
                continue
            
            # ========== SEPARATOR #### ==========
            if is_separator(line):
                buffer.state = QuestionState.AFTER_SEPARATOR
                i += 1
                continue
            
            # ========== EXPLANATION ==========
            if buffer.state in [QuestionState.AFTER_SEPARATOR, QuestionState.IN_EXPLANATION]:
                if line.strip():
                    buffer.explanation_lines.append(line)
                    buffer.state = QuestionState.IN_EXPLANATION
                i += 1
                continue
            
            # ========== QUESTION CONTENT ==========
            if buffer.state in [QuestionState.IN_TITLE, QuestionState.IN_CONTENT]:
                buffer.content_lines.append(line)
                buffer.state = QuestionState.IN_CONTENT
                i += 1
                continue
            
            i += 1
        
        # Flush buffer cuối
        if buffer.question_num > 0:
            if buffer.flush_to_doc(doc, image_tracker, skipped_log=skipped_or_failed_nums, written_log=written_nums, question_type=question_type):
                question_count_in_doc += 1  # CHỈ TĂNG NẾU GHI THÀNH CÔNG
        
        # Tính missing dựa trên những câu THỰC SỰ đã ghi vào docx
        written_set = set(written_nums)
        missing_nums = sorted(set(range(1, required_count + 1)) - written_set)
        # Ghi log bổ sung để truy vết rõ ràng
        if skipped_or_failed_nums:
            print(f"\n🧾 Danh sách số câu bị bỏ qua/không ghi được: {sorted(set(skipped_or_failed_nums))}\n")
        print(f"\n🧾 Danh sách số câu đã ghi: {sorted(written_set)}\n")
        add_summary_at_end(
            doc, 
            question_count_in_doc, 
            required_count, 
            missing_nums,
            image_tracker
        )
        
        # ========== LƯU FILE ==========
        output_path = f"{output_filename}.docx"
        doc.save(output_path)
        
        print(f"\n{'='*70}\n")
        print(f"✅ HOÀN THÀNH!\n")
        print(f"{'='*70}")
        print(f"\nFile: {output_path}\n")
        print(f"Câu hỏi: {question_count_in_doc}/{required_count}\n")
        
        if question_count_in_doc < required_count:
            missing_count = required_count - question_count_in_doc
            print(f"\n ⚠️  CÒN THIẾU: {missing_count} câu\n")
            print(f"💡 Các câu thiếu: {skipped_or_failed_nums}\n")
        
        print(f"\n📊 THỐNG KÊ ẢNH:")
        print(image_tracker.get_summary())
                
        print(f"{'='*70}\n")
        
        return output_path
    
    except Exception as e:
        print(f"\n❌ LỖI: {e}")
        traceback.print_exc()
        return None