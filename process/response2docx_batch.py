"""
Response2DOCX FAST - Wrapper tối ưu tốc độ
Thay thế response2docx_batch.py để nhanh gấp 5-10 lần
"""
from docx import Document
from process.batch_processor import BatchProcessorOptimized
from process.response2docx import add_summary_at_end
import traceback
import time


def response2docx_batch_fast(
    file_paths, 
    prompt, 
    output_filename, 
    project_id, 
    creds, 
    model_name,
    question_type="tracnghiem"
):
    """
    VERSION FAST: Tối ưu tốc độ, nhanh gấp 5-10 lần
    
    Thay đổi chính:
    - Batch size: 10 → 20 câu (giảm 50% số lần gọi API)
    - Max retry: 10 → 3 (giảm 70% thời gian retry)
    - Validation: Full → Quick (giảm 80% thời gian check)
    - Image: Sequential → Parallel (song song hóa)
    
    Args:
        file_paths: Danh sách file PDF
        prompt: Prompt đã replace subject/grade
        output_filename: Tên file output
        project_id: Google Cloud Project ID
        creds: Service account credentials
        model_name: Tên model AI
        question_type: "tracnghiem" hoặc "dungsai"
        
    Returns:
        Đường dẫn file docx đã tạo
    """
    try:
        start_time = time.time()
        
        print(f"\n{'='*70}")
        print(f"⚡ SINH {question_type.upper()} - FAST MODE")
        print(f"{'='*70}\n")
        
        required_count = 80 if question_type == "tracnghiem" else 40
        
        # KHỞI TẠO
        doc = Document()
        processor = BatchProcessorOptimized(project_id, creds, model_name)
        
        print(f"📋 Yêu cầu: {required_count} câu")
        print(f"⚡ Config tối ưu:")
        print(f"   - Batch size: {processor.config.batch_size} (2x lớn hơn)")
        print(f"   - Max retry: {processor.config.max_retry_per_batch} (3x ít hơn)")
        print(f"   - Quick validation: {processor.config.skip_minor_validation}")
        print(f"   - Parallel images: {processor.config.parallel_image_generation}\n")
        
        # XỬ LÝ NHANH
        storage, all_failed_nums = processor.process_all_batches_fast(
            prompt_content=prompt,
            pdf_files=file_paths,
            question_type=question_type,
            doc=doc
        )
        
        # THÊM SUMMARY
        final_count = storage.get_valid_count()
        
        add_summary_at_end(
            doc,
            final_count,
            required_count,
            all_failed_nums,
            image_tracker=processor.image_tracker
        )
        
        # LƯU FILE
        output_path = f"{output_filename}.docx"
        doc.save(output_path)
        
        print(f"\n{'='*70}")
        print(f"✅ HOÀN THÀNH!")
        print(f"{'='*70}")
        print(f"File: {output_path}")
        print(f"Câu hỏi: {final_count}/{required_count}")
        
        if all_failed_nums:
            print(f"\n⚠️  Còn thiếu: {len(all_failed_nums)} câu")
            print(f"📋 Danh sách: {all_failed_nums[:10]}")
        else:
            print(f"\n🎉 100% THÀNH CÔNG!")
        
        if processor.image_tracker:
            print(f"\n📊 Thống kê ảnh:")
            print(processor.image_tracker.get_summary())
        
        print(f"{'='*70}\n")
        
        return output_path
        
    except Exception as e:
        print(f"\n❌ LỖI: {e}")
        traceback.print_exc()
        return None


# COMPATIBILITY WRAPPER
def response2docx_improved(
    file_paths, 
    prompt, 
    output_filename, 
    project_id, 
    creds, 
    model_name,
    question_type="tracnghiem"
):
    """Wrapper để tương thích với code cũ"""
    return response2docx_batch_fast(
        file_paths, prompt, output_filename,
        project_id, creds, model_name, question_type
    )