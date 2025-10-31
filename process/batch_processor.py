"""
Module xử lý sinh câu hỏi theo batch với thuật toán chia để trị

Workflow:
1. Chia 80/40 câu thành các batch 10 câu
2. Mỗi batch: sinh → validate → ghi docx (nếu valid) → lưu số thiếu
3. Sau tất cả batch: xử lý câu thiếu → ghi vào cuối docx

Author: AI Assistant
Date: 2025
"""
import time
from typing import List, Dict, Tuple
from dataclasses import dataclass
from api.callAPI import VertexClient
from process.ques_valid import (
    QuestionValidator, 
    ValidQuestionStorage,
    regenerate_invalid_questions
)
from process.PDF_Scan import enhance_prompt_with_pdf_scan


@dataclass
class BatchConfig:
    """Cấu hình xử lý batch"""
    batch_size: int = 5  # Số câu mỗi batch
    max_retry_per_batch: int = 10  # Số lần retry tối đa mỗi batch
    max_final_retry: int = 10  # Số lần retry cho câu thiếu cuối cùng


class BatchProcessor:
    """
    Class xử lý sinh câu hỏi theo batch với validation và retry
    
    Workflow:
    1. Chia 80/40 câu thành các batch 10 câu
    2. Mỗi batch: sinh → validate → ghi docx (câu valid) → lưu số câu thiếu
    3. Cuối: xử lý tất cả câu thiếu → ghi vào cuối docx
    """
    
    def __init__(self, project_id: str, creds, model_name: str = "gemini-2.5-pro"):
        self.client = VertexClient(project_id, creds, model_name)
        self.project_id = project_id
        self.creds = creds
        self.config = BatchConfig()
        self.image_tracker = None 
    
    def process_all_batches(
        self,
        prompt_content: str,
        pdf_files: List[str],
        question_type: str = "tracnghiem",
        doc = None
    ) -> Tuple[ValidQuestionStorage, List[int]]:
        """Xử lý tất cả các batch"""
        required_count = 80 if question_type == "tracnghiem" else 40
        storage = ValidQuestionStorage()
        all_missing_nums = []
        
        print(f"\n{'='*70}")
        print(f"🎯 BẮT ĐẦU XỬ LÝ {required_count} CÂU THEO BATCH")
        print(f"{'='*70}\n")
        
        # Scan PDF
        print("📖 Bước 1: Scan PDF và tạo topic guide...")
        enhanced_prompt = enhance_prompt_with_pdf_scan(
            prompt_content, pdf_files, self.project_id, self.creds
        )
        
        # ===== FIX: KHỞI TẠO IMAGE TRACKER =====
        from process.text2Image import calculate_optimal_image_count, ImageGenerationTracker
        target_image_count = calculate_optimal_image_count(required_count, 0.2)  # 20%
        self.image_tracker = ImageGenerationTracker(target_image_count)
        
        print(f"🖼️  Target ảnh: {target_image_count} (~20%)")
        # ========================================
        
        # Tính số batch
        num_batches = (required_count + self.config.batch_size - 1) // self.config.batch_size
        print(f"📦 Tổng số batch: {num_batches} (mỗi batch {self.config.batch_size} câu)\n")
        
        # Xử lý từng batch
        for batch_idx in range(num_batches):
            batch_start = batch_idx * self.config.batch_size + 1
            batch_end = min((batch_idx + 1) * self.config.batch_size, required_count)
            batch_nums = list(range(batch_start, batch_end + 1))
            
            print(f"\n{'='*70}")
            print(f"📦 BATCH {batch_idx + 1}/{num_batches}: Câu {batch_start}-{batch_end}")
            print(f"{'='*70}\n")
            
            # Xử lý batch này
            missing_in_batch = self._process_single_batch(
                batch_nums,
                enhanced_prompt,
                storage,
                question_type,
                doc
            )
            
            all_missing_nums.extend(missing_in_batch)
            
            print(f"\n✅ Hoàn thành Batch {batch_idx + 1}")
            print(f"   - Câu valid: {len(batch_nums) - len(missing_in_batch)}/{len(batch_nums)}")
            print(f"   - Câu thiếu: {len(missing_in_batch)}")
            if missing_in_batch:
                print(f"   - Danh sách thiếu: {missing_in_batch}")
        
        print(f"\n{'='*70}")
        print(f"📊 TỔNG KẾT TẤT CẢ BATCH")
        print(f"{'='*70}")
        print(f"✅ Câu valid: {storage.get_valid_count()}/{required_count}")
        print(f"❌ Tổng câu thiếu: {len(all_missing_nums)}")
        if all_missing_nums:
            print(f"📋 Danh sách: {all_missing_nums[:20]}")
            if len(all_missing_nums) > 20:
                print(f"   ... và {len(all_missing_nums) - 20} câu khác")
        
        # ===== FIX: IN SUMMARY ẢNH =====
        if self.image_tracker:
            print(f"\n🖼️  THỐNG KÊ ẢNH:")
            print(f"   - Đã sinh: {self.image_tracker.generated_count}/{target_image_count}")
            print(f"   - Placeholder: {self.image_tracker.placeholder_count}")
            print(f"   - Failed: {self.image_tracker.failed_count}")
        # =================================
        
        print(f"{'='*70}\n")
        
        return storage, all_missing_nums
    
    def _process_single_batch(
        self,
        batch_nums: List[int],
        enhanced_prompt: str,
        storage: ValidQuestionStorage,
        question_type: str,
        doc
    ) -> List[int]:
        """
        Xử lý một batch với retry
        
        Returns:
            List số câu thiếu sau khi đã retry max lần
        """
        missing_nums = list(batch_nums)  # Ban đầu coi tất cả là thiếu
        
        for retry in range(1, self.config.max_retry_per_batch + 1):
            if not missing_nums:
                print(f"🎉 Batch hoàn thành! Tất cả câu đã valid.\n")
                break
            
            print(f"\n{'─'*70}")
            print(f"🔄 Lần thử {retry}/{self.config.max_retry_per_batch}")
            print(f"📝 Cần sinh: {len(missing_nums)} câu: {missing_nums}")
            print(f"{'─'*70}\n")
            
            # Tạo prompt cho batch này
            batch_prompt = self._create_batch_prompt(
                missing_nums,
                enhanced_prompt,
                storage,
                question_type
            )
            
            # Sinh câu hỏi
            try:
                print(f"📤 Gửi yêu cầu AI sinh {len(missing_nums)} câu...")
                response = self.client.send_data_to_check(
                    prompt=batch_prompt,
                    temperature=0.65 + (retry * 0.05)  # Tăng dần temperature
                )
                
                if not response:
                    print(f"⚠️  AI trả về rỗng, thử lại...")
                    time.sleep(3)
                    continue
                
                print(f"✅ Nhận được response ({len(response)} ký tự)\n")
                
                # Parse và validate
                newly_valid = self._validate_and_store(
                    response,
                    missing_nums,
                    storage,
                    question_type,
                    doc
                )
                
                # Cập nhật danh sách còn thiếu
                missing_nums = [n for n in missing_nums if n not in newly_valid]
                
                print(f"\n📊 Kết quả lần thử {retry}:")
                print(f"   ✅ Sinh thành công: {len(newly_valid)} câu")
                print(f"   ❌ Còn thiếu: {len(missing_nums)} câu")
                
                if not missing_nums:
                    print(f"   🎉 Batch hoàn thành!\n")
                    break
                
            except Exception as e:
                print(f"❌ Lỗi khi sinh câu: {str(e)}\n")
                time.sleep(3)
        
        # Sau khi đã retry max lần
        if missing_nums:
            print(f"\n⚠️  Sau {self.config.max_retry_per_batch} lần thử:")
            print(f"   ❌ Vẫn thiếu {len(missing_nums)} câu: {missing_nums}")
            print(f"   💾 Lưu vào danh sách xử lý sau\n")
        
        return missing_nums
    
    def _create_batch_prompt(
        self,
        batch_nums: List[int],
        enhanced_prompt: str,
        storage: ValidQuestionStorage,
        question_type: str
    ) -> str:
        """Tạo prompt cho một batch cụ thể"""
        
        # Lấy mẫu từ câu đã valid
        existing_samples = []
        for qnum in sorted(storage.valid_nums)[:3]:
            if qnum in storage.valid_questions:
                qtext = storage.valid_questions[qnum]
                preview = qtext.split("\n")[1:3]
                existing_samples.append(f"Câu {qnum}: {' '.join(preview)[:80]}...")
        
        # Xác định mức độ cho batch này
        level_guidance = self._get_level_guidance_for_batch(batch_nums, question_type)
        
        prompt_parts = [
            enhanced_prompt,
            "",
            "# YÊU CẦU ĐẶC BIỆT CHO BATCH NÀY",
            "",
            f"## 🎯 DANH SÁCH CÂU CẦN SINH (BẮT BUỘC)",
            f"Sinh CHÍNH XÁC {len(batch_nums)} câu sau:",
            f"**{', '.join(map(str, batch_nums))}**",
            "",
            level_guidance,
            "",
            "## 📋 MỘT SỐ CÂU ĐÃ HỢP LỆ (TRÁNH TRÙNG LẶP)",
        ]
        
        if existing_samples:
            prompt_parts.extend(existing_samples)
        else:
            prompt_parts.append("(Chưa có câu nào)")
        
        prompt_parts.extend([
            "",
            "## ⚠️ YÊU CẦU TUYỆT ĐỐI",
            "1. **CHỈ sinh các câu trong danh sách trên, ĐÚNG SỐ THỨ TỰ**",
            "2. **Nội dung HOÀN TOÀN KHÁC với các câu đã có**",
            "3. **Mỗi câu PHẢI ĐẦY ĐỦ format:** tiêu đề, nội dung, đáp án, lời giải, giải thích (≥3 dòng)",
            "4. **BÁM SÁT chủ đề từ PDF đã quét, không lạc đề**",
            "5. **KHÔNG thêm lời mở đầu/kết thúc**",
            "6. **Sinh theo ĐÚNG mức độ tương ứng với số thứ tự câu**",
            "",
            "BẮT ĐẦU SINH:",
            ""
        ])
        
        return "\n".join(prompt_parts)
    
    def _get_level_guidance_for_batch(self, batch_nums: List[int], question_type: str) -> str:
        """Tạo hướng dẫn mức độ cho batch"""
        
        if question_type == "tracnghiem":
            # Phân tích mức độ của batch
            levels_in_batch = {}
            for qnum in batch_nums:
                if 1 <= qnum <= 24:
                    level = "Nhận biết"
                elif 25 <= qnum <= 48:
                    level = "Thông hiểu"
                elif 49 <= qnum <= 72:
                    level = "Vận dụng"
                else:
                    level = "Vận dụng cao"
                levels_in_batch[level] = levels_in_batch.get(level, 0) + 1
            
            guidance = ["## 🎯 MỨC ĐỘ CỦA BATCH NÀY", ""]
            for level, count in levels_in_batch.items():
                guidance.append(f"- **{level}:** {count} câu")
            
            guidance.extend([
                "",
                "**QUAN TRỌNG:** Mỗi câu phải được sinh theo đúng mức độ tương ứng với số thứ tự:",
                "- Câu 1-24: Mức độ Nhận biết (câu hỏi ngắn gọn, kiểm tra nhớ)",
                "- Câu 25-48: Mức độ Thông hiểu (giải thích, so sánh)",
                "- Câu 49-72: Mức độ Vận dụng (áp dụng vào tình huống)",
                "- Câu 73-80: Mức độ Vận dụng cao (phân tích phức tạp)"
            ])
        else:  # dungsai
            levels_in_batch = {}
            for qnum in batch_nums:
                if 1 <= qnum <= 20:
                    level = "Thông hiểu"
                elif 21 <= qnum <= 32:
                    level = "Vận dụng"
                else:
                    level = "Vận dụng cao"
                levels_in_batch[level] = levels_in_batch.get(level, 0) + 1
            
            guidance = ["## 🎯 MỨC ĐỘ CỦA BATCH NÀY", ""]
            for level, count in levels_in_batch.items():
                guidance.append(f"- **{level}:** {count} câu")
            
            guidance.extend([
                "",
                "**QUAN TRỌNG:** Mỗi câu phải được sinh theo đúng mức độ:",
                "- Câu 1-20: Mức độ Thông hiểu",
                "- Câu 21-32: Mức độ Vận dụng",
                "- Câu 33-40: Mức độ Vận dụng cao"
            ])
        
        return "\n".join(guidance)
    
    def _validate_and_store(
        self,
        response: str,
        expected_nums: List[int],
        storage: ValidQuestionStorage,
        question_type: str,
        doc
    ) -> List[int]:
        """
        Validate và lưu câu hỏi, ghi trực tiếp vào docx nếu có
        FIX: Truyền image_tracker để sinh ảnh đúng
        
        Returns:
            List số câu đã valid thành công
        """
        from process.ques_valid import QuestionValidator
        
        validator = QuestionValidator(question_type=question_type)
        questions = validator.parse_questions(response)
        
        newly_valid = []
        
        for qnum, qtext in sorted(questions.items()):
            # Chỉ xử lý câu trong danh sách expected
            if qnum not in expected_nums:
                print(f"   ⚠️  Câu {qnum}: Không trong batch này, bỏ qua")
                continue
            
            # Validate
            validation = validator.validate_single_question(qtext, qnum)
            
            if validation.is_valid:
                # Lưu vào storage
                storage.replace_question(qnum, qtext)
                newly_valid.append(qnum)
                
                # GHI TRỰC TIẾP VÀO DOCX nếu có
                if doc:
                    try:
                        # ===== FIX: TRUYỀN IMAGE_TRACKER VÀO =====
                        self._write_question_to_doc(
                            qnum, qtext, doc, question_type,
                            image_tracker=self.image_tracker  # ADD THIS
                        )
                        # =========================================
                        print(f"   ✅ Câu {qnum}: Valid → GHI VÀO DOCX\n")
                    except Exception as e:
                        print(f"   ⚠️  Câu {qnum}: Valid nhưng lỗi ghi docx: {e}")
                else:
                    print(f"   ✅ Câu {qnum}: Valid → LƯU STORAGE\n")
            else:
                print(f"   ❌ Câu {qnum}: Thiếu {', '.join(validation.missing_parts)}\n")
        
        return newly_valid
    
    def _write_question_to_doc(self, qnum: int, qtext: str, doc, question_type: str, 
                            image_tracker=None):
        """
        Ghi một câu hỏi vào docx
        FIX: Sinh ảnh đúng như response2docx.py
        """
        from process.response2docx import (
            is_question_title, is_answer_option, is_solution_header,
            is_correct_answer, is_separator, is_image_line,
            extract_image_description, process_text, process_bold_text,
            handle_image_generation  # IMPORT handle_image_generation
        )
        from docx.shared import Pt, RGBColor
        
        lines = qtext.split("\n")
        
        title_line = None
        content_lines = []
        image_desc = None
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
            elif is_image_line(line):
                image_desc = extract_image_description(line)
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
            elif title_line and not is_answer_option(line):
                content_lines.append(line)
        
        # Ghi vào doc
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
        
        # ===== FIX: SINH ẢNH ĐÚNG NHƯ response2docx.py =====
        if image_desc:
            print(f"\n   🖼️  Phát hiện ảnh: {image_desc[:60]}...")
            
            # Quyết định có sinh ảnh thật không
            should_generate = False
            if image_tracker:
                should_generate = image_tracker.should_generate(qnum, 80)  # 80 hoặc 40
                print(f"      Decision: {'✅ Sinh thật' if should_generate else '📝 Placeholder'}")
            
            # Gọi hàm handle_image_generation từ response2docx.py
            success, img_para, is_placeholder = handle_image_generation(
                image_desc,
                doc,
                attempt_generate=should_generate,
                tracker=image_tracker
            )
            
            if success:
                print(f"      ✅ Đã sinh ảnh thành công")
            else:
                print(f"      📝 Dùng placeholder")
        # ====================================================
        
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
        
        # Giải thích (tối đa 5 dòng cho tracnghiem)
        max_lines = 5 if question_type == "tracnghiem" else len(explanation_lines)
        for line in explanation_lines[:max_lines]:
            if line.strip():
                p = doc.add_paragraph()
                if "**" in line:
                    process_bold_text(line, p)
                else:
                    process_text(line, p)
    
    def process_missing_questions(
        self,
        all_missing_nums: List[int],
        enhanced_prompt: str,
        storage: ValidQuestionStorage,
        question_type: str,
        doc
    ) -> int:
        """
        Xử lý tất cả câu thiếu sau khi đã xử lý hết batch
        FIX: Truyền image_tracker
        
        Returns:
            Số câu đã sinh thành công
        """
        if not all_missing_nums:
            print("\n🎉 Không có câu thiếu! Hoàn thành 100%\n")
            return 0
        
        print(f"\n{'='*70}")
        print(f"🔧 XỬ LÝ CÂU THIẾU CUỐI CÙNG")
        print(f"{'='*70}")
        print(f"📋 Tổng số câu thiếu: {len(all_missing_nums)}")
        print(f"🔍 Danh sách: {all_missing_nums[:20]}")
        if len(all_missing_nums) > 20:
            print(f"   ... và {len(all_missing_nums) - 20} câu khác")
        print(f"{'='*70}\n")
        
        success_count = 0
        remaining = list(all_missing_nums)
        
        for retry in range(1, self.config.max_final_retry + 1):
            if not remaining:
                break
            
            print(f"\n{'─'*70}")
            print(f"🔄 Lần thử {retry}/{self.config.max_final_retry}")
            print(f"🔍 Còn {len(remaining)} câu: {remaining[:10]}")
            if len(remaining) > 10:
                print(f"   ... và {len(remaining) - 10} câu khác")
            print(f"{'─'*70}\n")
            
            # Sinh lại batch câu thiếu (tối đa 15 câu/lần)
            batch_size = min(15, len(remaining))
            batch_to_gen = remaining[:batch_size]
            
            batch_prompt = self._create_batch_prompt(
                batch_to_gen,
                enhanced_prompt,
                storage,
                question_type
            )
            
            try:
                print(f"📤 Sinh {len(batch_to_gen)} câu...")
                response = self.client.send_data_to_check(
                    prompt=batch_prompt,
                    temperature=0.7 + (retry * 0.1)
                )
                
                if not response:
                    print(f"⚠️  Không nhận được response, thử lại...")
                    time.sleep(3)
                    continue
                
                # ===== FIX: VALIDATE VÀ STORE VỚI IMAGE_TRACKER =====
                newly_valid = self._validate_and_store(
                    response,
                    batch_to_gen,
                    storage,
                    question_type,
                    doc  # image_tracker đã có trong self
                )
                # ====================================================
                
                success_count += len(newly_valid)
                remaining = [n for n in remaining if n not in newly_valid]
                
                print(f"✅ Sinh thành công: {len(newly_valid)} câu")
                print(f"❌ Còn thiếu: {len(remaining)} câu")
                
            except Exception as e:
                print(f"❌ Lỗi: {str(e)}")
                time.sleep(3)
        
        print(f"\n{'='*70}")
        print(f"📊 KẾT QUẢ XỬ LÝ CÂU THIẾU")
        print(f"{'='*70}")
        print(f"✅ Đã sinh thêm: {success_count} câu")
        print(f"❌ Vẫn thiếu: {len(remaining)} câu")
        if remaining:
            print(f"📋 Danh sách còn thiếu: {remaining}")
        
        # ===== FIX: IN SUMMARY ẢNH CUỐI CÙNG =====
        if self.image_tracker:
            print(f"\n🖼️  THỐNG KÊ ẢNH CUỐI CÙNG:")
            print(self.image_tracker.get_summary())
        # =========================================
        
        print(f"{'='*70}\n")
        
        return success_count