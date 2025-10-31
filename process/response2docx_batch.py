"""
response2docx với batch processing - Version 5
Tích hợp thuật toán chia để trị
"""
from docx import Document
from api.callAPI import VertexClient
from process.batch_processor import BatchProcessor, BatchConfig
from process.ques_valid import ValidQuestionStorage
from process.response2docx import (
    add_summary_at_end,
    ImageGenerationTracker,
    calculate_optimal_image_count
)
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import traceback


def response2docx_batch_v5(
    file_paths, 
    prompt, 
    output_filename, 
    project_id, 
    creds, 
    model_name,
    question_type="tracnghiem"
):
    """
    VERSION 5: Xử lý theo batch với thuật toán chia để trị
    FIX: Truyền image_tracker vào add_summary_at_end
    
    Workflow:
    1. Scan PDF + prompt
    2. Chia thành các batch 5 câu
    3. Mỗi batch: sinh → validate → ghi docx → lưu thiếu
    4. Xử lý tất cả câu thiếu → ghi cuối file
    
    Args:
        file_paths: Danh sách file PDF
        prompt: Prompt đã replace subject/grade
        output_filename: Tên file output (không có .docx)
        project_id: Google Cloud Project ID
        creds: Service account credentials
        model_name: Tên model AI
        question_type: "tracnghiem" hoặc "dungsai"
        
    Returns:
        Đường dẫn file docx đã tạo
    """
    try:
        print(f"\n{'='*70}")
        print(f"🚀 SINH {question_type.upper()} - VERSION 5 (BATCH PROCESSING)")
        print(f"{'='*70}\n")
        
        required_count = 80 if question_type == "tracnghiem" else 40
        
        # ============ KHỞI TẠO ============
        doc = Document()
        processor = BatchProcessor(project_id, creds, model_name)
        
        # ===== FIX: SỬ DỤNG IMAGE_TRACKER TỪ PROCESSOR =====
        # KHÔNG CẦN tạo image_tracker riêng ở đây nữa
        # Vì processor.process_all_batches đã tạo rồi
        # ====================================================
        
        print(f"📋 Yêu cầu: {required_count} câu")
        print(f"📦 Batch size: {processor.config.batch_size} câu/batch")
        print(f"🔄 Max retry/batch: {processor.config.max_retry_per_batch}")
        # print(f"🖼️  Target images: {image_tracker.target_count}\n")  # BỎ DÒNG NÀY
        
        # ============ XỬ LÝ THEO BATCH ============
        print(f"{'='*70}")
        print("BƯỚC 1: XỬ LÝ THEO BATCH")
        print(f"{'='*70}\n")
        
        storage, all_missing_nums = processor.process_all_batches(
            prompt_content=prompt,
            pdf_files=file_paths,
            question_type=question_type,
            doc=doc  # Truyền doc để ghi trực tiếp
        )
        
        # ============ XỬ LÝ CÂU THIẾU ============
        if all_missing_nums:
            print(f"\n{'='*70}")
            print("BƯỚC 2: XỬ LÝ CÂU THIẾU")
            print(f"{'='*70}\n")
            
            # Re-scan PDF cho câu thiếu
            from process.PDF_Scan import enhance_prompt_with_pdf_scan
            enhanced_prompt = enhance_prompt_with_pdf_scan(
                prompt, file_paths, project_id, creds
            )
            
            success_count = processor.process_missing_questions(
                all_missing_nums,
                enhanced_prompt,
                storage,
                question_type,
                doc
            )
            
            if success_count > 0:
                print(f"✅ Đã bổ sung thêm {success_count} câu vào cuối file")
        
        # ============ THÊM SUMMARY ============
        final_count = storage.get_valid_count()
        final_missing = storage.get_missing_nums(required_count)
        
        # ===== FIX: TRUYỀN IMAGE_TRACKER TỪ PROCESSOR =====
        add_summary_at_end(
            doc,
            final_count,
            required_count,
            final_missing,
            image_tracker=processor.image_tracker  # THÊM DÒNG NÀY
        )
        # ==================================================
        
        # ============ LƯU FILE ============
        output_path = f"{output_filename}.docx"
        doc.save(output_path)
        
        print(f"\n{'='*70}")
        print(f"✅ HOÀN THÀNH!")
        print(f"{'='*70}")
        print(f"📄 File: {output_path}")
        print(f"✅ Câu hỏi: {final_count}/{required_count}")
        
        if final_missing:
            print(f"⚠️  Còn thiếu: {len(final_missing)} câu")
            print(f"📋 Danh sách: {final_missing[:10]}")
            if len(final_missing) > 10:
                print(f"   ... và {len(final_missing) - 10} câu khác")
        else:
            print(f"🎉 ĐẦY ĐỦ 100%!")
        
        # ===== FIX: IN SUMMARY TỪ PROCESSOR.IMAGE_TRACKER =====
        if processor.image_tracker:
            print(f"\n📊 Thống kê ảnh:")
            print(processor.image_tracker.get_summary())
        # ======================================================
        
        print(f"{'='*70}\n")
        
        return output_path
        
    except Exception as e:
        print(f"\n❌ LỖI NGHIÊM TRỌNG: {e}")
        traceback.print_exc()
        return None


def write_question_to_doc_simple(qtext: str, doc, question_type: str):
    """
    Ghi một câu hỏi vào docx (simplified version)
    
    Chỉ ghi nội dung text cơ bản, không xử lý hình ảnh phức tạp
    """
    from process.response2docx import (
        is_question_title, is_answer_option, is_solution_header,
        is_correct_answer, is_separator, process_text, process_bold_text
    )
    
    lines = qtext.split("\n")
    
    # Parse components
    title_line = None
    content_lines = []
    answers = []
    solution_header = None
    correct_answer = None
    explanation_lines = []
    in_explanation = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if is_question_title(line):
            title_line = line.replace("**", "").strip()
        elif is_answer_option(line):
            answers.append(line)
        elif is_solution_header(line):
            solution_header = line.replace("**", "").strip()
        elif solution_header and is_correct_answer(line):
            correct_answer = line.strip()
        elif is_separator(line):
            in_explanation = True
        elif in_explanation and line:
            explanation_lines.append(line)
        elif title_line and not answers:
            content_lines.append(line)
    
    # Write to doc
    if title_line:
        p = doc.add_paragraph()
        run = p.add_run(title_line)
        run.bold = True
        run.font.size = Pt(12)
    
    for line in content_lines:
        if line.strip():
            p = doc.add_paragraph()
            if "**" in line:
                process_bold_text(line, p)
            else:
                process_text(line, p)
    
    for ans in answers:
        p = doc.add_paragraph()
        process_text(ans, p)
    
    doc.add_paragraph()
    
    if solution_header:
        p = doc.add_paragraph()
        run = p.add_run(solution_header)
        run.bold = True
    
    if correct_answer:
        p = doc.add_paragraph()
        run = p.add_run(correct_answer)
        run.bold = True
    
    p = doc.add_paragraph()
    run = p.add_run("####")
    run.bold = True
    
    # Giải thích
    max_lines = 5 if question_type == "tracnghiem" else len(explanation_lines)
    for line in explanation_lines[:max_lines]:
        if line.strip():
            p = doc.add_paragraph()
            if "**" in line:
                process_bold_text(line, p)
            else:
                process_text(line, p)


# ============ COMPATIBILITY ============
def response2docx_improved(
    file_paths, 
    prompt, 
    output_filename, 
    project_id, 
    creds, 
    model_name,
    question_type="tracnghiem"
):
    """
    Wrapper để tương thích với code cũ
    Chuyển sang dùng batch processing
    """
    return response2docx_batch_v5(
        file_paths,
        prompt,
        output_filename,
        project_id,
        creds,
        model_name,
        question_type
    )