"""
Response2DOCX FAST - Wrapper tối ưu tốc độ
Thay thế response2docx_batch.py để nhanh gấp 5-10 lần
"""
from docx import Document
from process.batch_processor import BatchProcessorOptimized
from process.response2docx import add_summary_at_end
import traceback
import time


def response2docx_batch_v3(
    file_paths, 
    prompt, 
    output_filename, 
    project_id, 
    creds, 
    model_name,
    question_type="tracnghiem"
):
    try:
        
        print(f"\n{'='*70}")
        print(f"⚡ SINH {question_type.upper()} - FAST MODE")
        print(f"{'='*70}\n")
        
        required_count = 80 if question_type == "tracnghiem" else 40
        
        # KHỞI TẠO
        doc = Document()
        processor = BatchProcessorOptimized(project_id, creds, model_name)
        
        print(f"📋 Yêu cầu: {required_count} câu")
        print(f"Config tối ưu:")
        print(f"   - Batch size: {processor.config.batch_size}")
        print(f"   - Max retry: {processor.config.max_retry_per_batch}")
        print(f"   - Quick validation: {processor.config.skip_minor_validation}")
        print(f"   - Parallel images: {processor.config.parallel_image_generation}\n")
        
        # XỬ LÝ NHANH
        storage, all_failed_nums = processor.process_all_batches(
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
    return response2docx_batch_v3(
        file_paths, prompt, output_filename,
        project_id, creds, model_name, question_type
    )