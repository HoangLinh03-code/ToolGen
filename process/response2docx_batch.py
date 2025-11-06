"""
Response2DOCX Batch V3 - Tích hợp workflow mới
Wrapper để tích hợp BatchProcessorV2 vào hệ thống
"""
from docx import Document
from api.callAPI import VertexClient
from process.batch_processor import BatchProcessorV2
from process.ques_valid import ValidQuestionStorage
from process.response2docx import add_summary_at_end
import traceback


def response2docx_batch_v3(
    file_paths, 
    prompt, 
    output_filename, 
    project_id, 
    creds, 
    model_name,
    question_type="tracnghiem"
):
    """
    VERSION 3: Workflow mới với Storage trước → DOCX sau
    
    Workflow:
    1. Sinh batch → Validate → Lưu Storage
    2. Regen invalid → Validate → Lưu Storage  
    3. Đủ 10 valid trong Storage → Sort → Ghi DOCX
    4. Confirm ghi thành công → Batch tiếp
    
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
        print(f"🚀 SINH {question_type.upper()} - VERSION 3 (NEW WORKFLOW)")
        print(f"{'='*70}\n")
        
        required_count = 80 if question_type == "tracnghiem" else 40
        
        # ============ KHỞI TẠO ============
        doc = Document()
        processor = BatchProcessorV2(project_id, creds, model_name)
        
        print(f"📋 Yêu cầu: {required_count} câu")
        print(f"📦 Batch size: {processor.config.batch_size} câu/batch")
        print(f"🔄 Max retry/batch: {processor.config.max_retry_per_batch}")
        print(f"✍️  Max write retry: {processor.config.max_write_retry}\n")
        
        # ============ XỬ LÝ THEO BATCH ============
        print(f"{'='*70}")
        print("BƯỚC 1: XỬ LÝ TẤT CẢ BATCH")
        print(f"{'='*70}\n")
        
        storage, all_failed_nums = processor.process_all_batches(
            prompt_content=prompt,
            pdf_files=file_paths,
            question_type=question_type,
            doc=doc  # Truyền doc để ghi trực tiếp trong phase 2
        )
        
        # ============ XỬ LÝ CÂU THẤT BẠI (NẾU CÓ) ============
        if all_failed_nums:
            print(f"\n{'='*70}")
            print("BƯỚC 2: XỬ LÝ CÂU THẤT BẠI")
            print(f"{'='*70}\n")
            
            print(f"⚠️  Có {len(all_failed_nums)} câu không thể xử lý")
            print(f"📋 Danh sách: {all_failed_nums}")
            print(f"💡 Các câu này sẽ được đánh dấu trong summary\n")
        
        # ============ THÊM SUMMARY ============
        final_count = storage.get_valid_count()
        final_missing = all_failed_nums  # Những câu thất bại
        
        add_summary_at_end(
            doc,
            final_count,
            required_count,
            final_missing,
            image_tracker=processor.image_tracker
        )
        
        # ============ LƯU FILE ============
        output_path = f"{output_filename}.docx"
        doc.save(output_path)
        
        print(f"\n{'='*70}")
        print(f"✅ HOÀN THÀNH!")
        print(f"{'='*70}")
        print(f"📄 File: {output_path}")
        print(f"✅ Câu hỏi: {final_count}/{required_count}")
        
        if final_missing:
            print(f"⚠️  Còn thiếu/thất bại: {len(final_missing)} câu")
            print(f"📋 Danh sách: {final_missing[:10]}")
            if len(final_missing) > 10:
                print(f"   ... và {len(final_missing) - 10} câu khác")
        else:
            print(f"🎉 ĐẦY ĐỦ 100%!")
        
        if processor.image_tracker:
            print(f"\n📊 Thống kê ảnh:")
            print(processor.image_tracker.get_summary())
        
        print(f"{'='*70}\n")
        
        return output_path
        
    except Exception as e:
        print(f"\n❌ LỖI NGHIÊM TRỌNG: {e}")
        traceback.print_exc()
        return None


# ============ COMPATIBILITY WRAPPER ============
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
    Chuyển sang dùng workflow mới (V3)
    """
    return response2docx_batch_v3(
        file_paths,
        prompt,
        output_filename,
        project_id,
        creds,
        model_name,
        question_type
    )