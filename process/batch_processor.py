"""
Batch Processor V2.1 - Enhanced with Final Recovery Phase
Workflow: Sinh → Validate → Storage → Sort → Ghi DOCX → Recovery Phase
"""
import time
import re
from typing import List, Dict, Tuple
from dataclasses import dataclass
from api.callAPI import VertexClient
from process.ques_valid import QuestionValidator, ValidQuestionStorage
from process.PDF_Scan import enhance_prompt_with_pdf_scan
from docx import Document


@dataclass
class BatchConfig:
    """Cấu hình xử lý batch"""
    batch_size: int = 10  # Số câu mỗi batch
    max_retry_per_batch: int = 10  # Số lần retry tối đa mỗi batch
    max_write_retry: int = 10  # Số lần retry khi ghi docx lỗi
    max_final_recovery_retry: int = 12  # Số lần retry trong phase recovery cuối cùng


class BatchProcessorV2:
    """
    Batch Processor với workflow mới + Recovery Phase:
    1. Sinh batch → Validate → Lưu Storage
    2. Regen invalid → Validate → Lưu Storage
    3. Khi đủ 10 valid → Sort → Ghi DOCX
    4. Confirm ghi thành công → Chuyển batch tiếp
    5. *** PHASE CUỐI: Recovery tất cả câu thất bại ***
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
        doc: Document = None
    ) -> Tuple[ValidQuestionStorage, List[int]]:
        """
        Xử lý tất cả các batch theo workflow mới + Recovery Phase
        
        Returns:
            (storage, missing_nums)
        """
        required_count = 80 if question_type == "tracnghiem" else 40
        storage = ValidQuestionStorage()
        all_failed_nums = []  # Câu không thể sinh/ghi được trong các batch
        
        print(f"\n{'='*70}")
        print(f"🎯 BẮT ĐẦU XỬ LÝ {required_count} CÂU THEO WORKFLOW MỚI")
        print(f"{'='*70}\n")
        
        # Scan PDF
        print("📖 Bước 1: Scan PDF và tạo topic guide...")
        enhanced_prompt = enhance_prompt_with_pdf_scan(
            prompt_content, pdf_files, self.project_id, self.creds
        )
        
        # Khởi tạo image tracker
        from process.text2Image import calculate_optimal_image_count, ImageGenerationTracker
        target_image_count = calculate_optimal_image_count(required_count, 0.17)
        self.image_tracker = ImageGenerationTracker(target_image_count)
        
        print(f"🖼️  Target ảnh: {target_image_count} (~17%)")
        
        # Tính số batch
        num_batches = (required_count + self.config.batch_size - 1) // self.config.batch_size
        print(f"📦 Tổng số batch: {num_batches} (mỗi batch {self.config.batch_size} câu)\n")
        
        # ============ PHASE 1: XỬ LÝ TỪNG BATCH ============
        print(f"\n{'='*70}")
        print("🔥 PHASE 1: XỬ LÝ CÁC BATCH CHÍNH")
        print(f"{'='*70}\n")
        
        for batch_idx in range(num_batches):
            batch_start = batch_idx * self.config.batch_size + 1
            batch_end = min((batch_idx + 1) * self.config.batch_size, required_count)
            batch_nums = list(range(batch_start, batch_end + 1))
            
            print(f"\n{'='*70}")
            print(f"📦 BATCH {batch_idx + 1}/{num_batches}: Câu {batch_start}-{batch_end}")
            print(f"{'='*70}\n")
            
            # Xử lý batch này với workflow mới
            failed_in_batch = self._process_single_batch_v2(
                batch_nums,
                enhanced_prompt,
                storage,
                question_type,
                doc
            )
            
            all_failed_nums.extend(failed_in_batch)
            
            print(f"\n✅ Hoàn thành Batch {batch_idx + 1}")
            print(f"   - Câu đã ghi vào DOCX: {len(batch_nums) - len(failed_in_batch)}/{len(batch_nums)}")
            print(f"   - Câu thất bại: {len(failed_in_batch)}")
            if failed_in_batch:
                print(f"   - Danh sách thất bại: {failed_in_batch}")
        
        # ============ PHASE 2: RECOVERY CUỐI CÙNG ============
        if all_failed_nums:
            print(f"\n{'='*70}")
            print("🔄 PHASE 2: RECOVERY - XỬ LÝ CÂU THẤT BẠI")
            print(f"{'='*70}\n")
            
            print(f"⚠️  Có {len(all_failed_nums)} câu thất bại từ Phase 1")
            print(f"📋 Danh sách: {all_failed_nums[:20]}")
            if len(all_failed_nums) > 20:
                print(f"   ... và {len(all_failed_nums) - 20} câu khác")
            print(f"\n🔄 Bắt đầu recovery với max {self.config.max_final_recovery_retry} lần retry...\n")
            
            # Gọi recovery phase
            final_failed = self._final_recovery_phase(
                all_failed_nums,
                enhanced_prompt,
                storage,
                question_type,
                doc
            )
            
            # Cập nhật danh sách thất bại cuối cùng
            all_failed_nums = final_failed
        
        # ============ TỔNG KẾT ============
        print(f"\n{'='*70}")
        print(f"📊 TỔNG KẾT TOÀN BỘ QUY TRÌNH")
        print(f"{'='*70}")
        print(f"✅ Câu đã ghi DOCX: {storage.get_valid_count()}/{required_count}")
        print(f"❌ Tổng câu thất bại CUỐI CÙNG: {len(all_failed_nums)}")
        if all_failed_nums:
            print(f"📋 Danh sách: {all_failed_nums}")
        else:
            print(f"🎉 HOÀN THÀNH 100% - Không có câu thất bại!")
        
        if self.image_tracker:
            print(f"\n🖼️  THỐNG KÊ ẢNH:")
            print(f"   - Đã sinh: {self.image_tracker.generated_count}/{target_image_count}")
            print(f"   - Placeholder: {self.image_tracker.placeholder_count}")
            print(f"   - Failed: {self.image_tracker.failed_count}")
        
        print(f"{'='*70}\n")
        
        return storage, all_failed_nums
    
    def _final_recovery_phase(
        self,
        failed_nums: List[int],
        enhanced_prompt: str,
        storage: ValidQuestionStorage,
        question_type: str,
        doc: Document
    ) -> List[int]:
        """
        PHASE RECOVERY CUỐI CÙNG: Xử lý tất cả câu thất bại
        
        Workflow:
        1. Regen từng câu (max 12 retry)
        2. Validate ngay
        3. Nếu valid → Ghi DOCX (max 10 retry)
        4. Track câu cuối cùng vẫn thất bại
        
        Returns:
            List số câu CUỐI CÙNG vẫn thất bại
        """
        final_failed = []
        successfully_recovered = []
        
        for qnum in failed_nums:
            print(f"\n{'─'*70}")
            print(f"🔄 RECOVERY Câu {qnum}")
            print(f"{'─'*70}\n")
            
            recovered = False
            
            # Thử regen + validate + write (max 12 lần)
            for attempt in range(1, self.config.max_final_recovery_retry + 1):
                print(f"   🔄 Lần thử {attempt}/{self.config.max_final_recovery_retry}...")
                
                # STEP 1: REGEN
                print(f"      📝 Đang regen câu {qnum}...")
                new_qtext = self._regenerate_single_question(
                    qnum,
                    enhanced_prompt,
                    storage,
                    question_type
                )
                
                if not new_qtext:
                    print(f"      ❌ Regen thất bại")
                    time.sleep(2)
                    continue
                
                print(f"      ✅ Regen thành công")
                
                # STEP 2: VALIDATE
                validator = QuestionValidator(question_type=question_type)
                validation = validator.validate_single_question(new_qtext, qnum)
                
                if not validation.is_valid:
                    print(f"      ❌ Validation thất bại: {', '.join(validation.missing_parts)}")
                    time.sleep(2)
                    continue
                
                print(f"      ✅ Validation passed")
                
                # STEP 3: CẬP NHẬT STORAGE
                storage.replace_question(qnum, new_qtext)
                
                # STEP 4: GHI VÀO DOCX
                print(f"      ✍️  Đang ghi vào DOCX...")
                
                write_success = False
                for write_attempt in range(1, self.config.max_write_retry + 1):
                    try:
                        self._write_question_to_doc(
                            qnum, new_qtext, doc, question_type,
                            image_tracker=self.image_tracker
                        )
                        
                        print(f"      ✅ Ghi DOCX thành công!")
                        write_success = True
                        recovered = True
                        successfully_recovered.append(qnum)
                        break
                        
                    except Exception as e:
                        print(f"      ❌ Lỗi ghi DOCX (lần {write_attempt}): {str(e)[:60]}")
                        
                        if write_attempt < self.config.max_write_retry:
                            print(f"      🔄 Regen lại để sửa lỗi...")
                            # Regen lại trong vòng lặp write
                            new_qtext = self._regenerate_single_question(
                                qnum, enhanced_prompt, storage, question_type
                            )
                            if new_qtext:
                                storage.replace_question(qnum, new_qtext)
                                time.sleep(1)
                        else:
                            break
                
                if recovered:
                    print(f"\n   🎉 RECOVERY THÀNH CÔNG câu {qnum}")
                    break
                else:
                    print(f"      ⚠️  Attempt {attempt} không thành công, thử lại...")
                    time.sleep(3)
            
            if not recovered:
                print(f"\n   💔 RECOVERY THẤT BẠI câu {qnum} sau {self.config.max_final_recovery_retry} lần")
                final_failed.append(qnum)
        
        # Tổng kết recovery phase
        print(f"\n{'='*70}")
        print(f"📊 KẾT QUẢ RECOVERY PHASE")
        print(f"{'='*70}")
        print(f"✅ Recovery thành công: {len(successfully_recovered)}/{len(failed_nums)}")
        print(f"❌ Vẫn thất bại: {len(final_failed)}")
        if final_failed:
            print(f"📋 Danh sách cuối cùng thất bại: {final_failed}")
        print(f"{'='*70}\n")
        
        return final_failed
    
    def _process_single_batch_v2(
        self,
        batch_nums: List[int],
        enhanced_prompt: str,
        storage: ValidQuestionStorage,
        question_type: str,
        doc: Document
    ) -> List[int]:
        """
        Xử lý một batch theo workflow MỚI:
        1. Sinh → Validate → Lưu Storage
        2. Regen invalid → Validate → Lưu Storage
        3. Đủ 10 valid → Sort → Ghi DOCX
        
        Returns:
            List số câu thất bại (không thể ghi vào DOCX)
        """
        print(f"\n{'─'*70}")
        print(f"📄 BẮT ĐẦU XỬ LÝ BATCH")
        print(f"📋 Câu cần xử lý: {batch_nums}")
        print(f"{'─'*70}\n")
        
        # PHASE 1: SINH + VALIDATE + LƯU STORAGE
        print(f"🔍 PHASE 1: SINH VÀ VALIDATE")
        print(f"{'─'*60}\n")
        
        for retry in range(1, self.config.max_retry_per_batch + 1):
            # Tính câu còn thiếu trong storage
            missing_in_storage = [n for n in batch_nums if not storage.has_question(n)]
            
            if not missing_in_storage:
                print(f"🎉 Đã có đủ {len(batch_nums)} câu valid trong storage!\n")
                break
            
            print(f"\n🔄 Lần thử {retry}/{self.config.max_retry_per_batch}")
            print(f"🔍 Cần sinh: {len(missing_in_storage)} câu: {missing_in_storage}\n")
            
            # Tạo prompt cho batch này
            batch_prompt = self._create_batch_prompt(
                missing_in_storage,
                enhanced_prompt,
                storage,
                question_type
            )
            
            # Sinh câu hỏi
            try:
                print(f"📤 Gửi yêu cầu AI sinh {len(missing_in_storage)} câu...")
                response = self.client.send_data_to_check(
                    prompt=batch_prompt,
                    temperature=0.45 + (retry * 0.05)
                )
                
                if not response:
                    print(f"⚠️  AI trả về rỗng, thử lại...")
                    time.sleep(3)
                    continue
                
                print(f"✅ Nhận được response ({len(response)} ký tự)\n")
                
                # Parse và validate - CHỈ LƯU VÀO STORAGE
                newly_valid = self._validate_and_store_only(
                    response,
                    missing_in_storage,
                    storage,
                    question_type
                )
                
                print(f"\n📊 Kết quả lần thử {retry}:")
                print(f"   ✅ Valid → Storage: {len(newly_valid)} câu")
                print(f"   ❌ Còn thiếu: {len(missing_in_storage) - len(newly_valid)} câu")
                
            except Exception as e:
                print(f"❌ Lỗi khi sinh câu: {str(e)}\n")
                time.sleep(3)
        
        # Kiểm tra storage có đủ không
        valid_in_storage = [n for n in batch_nums if storage.has_question(n)]
        missing_in_storage = [n for n in batch_nums if not storage.has_question(n)]
        
        print(f"\n{'─'*60}")
        print(f"📊 KẾT QUẢ PHASE 1:")
        print(f"   ✅ Có trong storage: {len(valid_in_storage)}/{len(batch_nums)}")
        print(f"   ❌ Vẫn thiếu: {len(missing_in_storage)}")
        if missing_in_storage:
            print(f"   📋 Danh sách thiếu: {missing_in_storage}")
        print(f"{'─'*60}\n")
        
        # PHASE 2: GHI VÀO DOCX
        print(f"\n🖊️  PHASE 2: GHI VÀO DOCX")
        print(f"{'─'*60}\n")
        
        if not valid_in_storage:
            print(f"⚠️  Không có câu nào valid trong storage → Bỏ qua phase 2")
            return batch_nums
        
        # Sort theo thứ tự
        valid_in_storage.sort()
        
        failed_to_write = []  # Câu không thể ghi vào DOCX
        
        for qnum in valid_in_storage:
            print(f"\n🖊️  Đang ghi câu {qnum} vào DOCX...")
            
            qtext = storage.valid_questions[qnum]
            
            # Thử ghi vào DOCX với retry
            write_success = False
            
            for write_attempt in range(1, self.config.max_write_retry + 1):
                try:
                    print(f"   Lần thử {write_attempt}/{self.config.max_write_retry}...")
                    
                    # Ghi vào DOCX
                    self._write_question_to_doc(
                        qnum, qtext, doc, question_type,
                        image_tracker=self.image_tracker
                    )
                    
                    print(f"   ✅ Ghi thành công câu {qnum}")
                    write_success = True
                    break
                    
                except Exception as e:
                    print(f"   ❌ Lỗi ghi câu {qnum}: {str(e)[:60]}")
                    
                    if write_attempt < self.config.max_write_retry:
                        print(f"   🔄 Đang regen câu {qnum}...")
                        
                        # Regen câu này
                        new_qtext = self._regenerate_single_question(
                            qnum,
                            enhanced_prompt,
                            storage,
                            question_type
                        )
                        
                        if new_qtext:
                            # Cập nhật storage
                            storage.replace_question(qnum, new_qtext)
                            qtext = new_qtext
                            print(f"   ✅ Đã regen thành công, thử ghi lại...")
                        else:
                            print(f"   ❌ Không thể regen câu {qnum}")
                            break
            
            if not write_success:
                print(f"   💔 Không thể ghi câu {qnum} sau {self.config.max_write_retry} lần thử")
                failed_to_write.append(qnum)
        
        print(f"\n{'─'*60}")
        print(f"📊 KẾT QUẢ PHASE 2:")
        print(f"   ✅ Đã ghi vào DOCX: {len(valid_in_storage) - len(failed_to_write)}/{len(valid_in_storage)}")
        print(f"   ❌ Không thể ghi: {len(failed_to_write)}")
        if failed_to_write:
            print(f"   📋 Danh sách: {failed_to_write}")
        print(f"{'─'*60}\n")
        
        # Tổng kết batch
        total_failed = list(set(missing_in_storage + failed_to_write))
        
        return total_failed
    
    def _validate_and_store_only(
        self,
        response: str,
        expected_nums: List[int],
        storage: ValidQuestionStorage,
        question_type: str
    ) -> List[int]:
        """
        Validate và LƯU VÀO STORAGE (KHÔNG GHI DOCX)
        
        Returns:
            List số câu đã valid và lưu storage
        """
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
                print(f"   ✅ Câu {qnum}: Valid → LƯU STORAGE")
            else:
                print(f"   ❌ Câu {qnum}: Thiếu {', '.join(validation.missing_parts)}")
        
        return newly_valid
    
    def _write_question_to_doc(
        self, 
        qnum: int, 
        qtext: str, 
        doc: Document, 
        question_type: str,
        image_tracker=None
    ):
        """
        Ghi MỘT câu hỏi vào DOCX
        Raise exception nếu có lỗi để caller có thể retry
        """
        from process.response2docx import (
            is_question_title, is_answer_option, is_solution_header,
            is_correct_answer, is_separator, is_image_line,
            extract_image_description, process_text, process_bold_text,
            handle_image_generation
        )
        from docx.shared import Pt
        
        lines = qtext.split("\n")
        
        # Parse components
        title_line = None
        content_lines = []
        image_desc = None
        answers = []
        solution_header = None
        correct_answer = None
        explanation_lines = []
        
        # State tracking
        in_title = False
        in_content = False
        in_answers = False
        in_solution = False
        in_explanation = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 1. Question Title
            if is_question_title(line):
                title_line = line.replace("**", "").strip()
                in_title = True
                in_content = False
                continue
            
            # 2. Image (có thể ở giữa content)
            if is_image_line(line):
                image_desc = extract_image_description(line)
                continue
            
            # 3. Answer Options
            if is_answer_option(line):
                answers.append(line)
                in_content = False
                in_answers = True
                continue
            
            # 4. Solution Header
            if is_solution_header(line):
                solution_header = line.replace("**", "").strip()
                in_answers = False
                in_solution = True
                continue
            
            # 5. Correct Answer
            if in_solution and is_correct_answer(line):
                correct_answer = line.strip()
                continue
            
            # 6. Separator ####
            if is_separator(line):
                in_solution = False
                in_explanation = True
                continue
            
            # 7. Explanation
            if in_explanation and line:
                explanation_lines.append(line)
                continue
            
            # 8. Content
            if in_title and not in_answers and not in_solution and not in_explanation:
                content_lines.append(line)
                continue
        
        # ============ VALIDATION TRƯỚC KHI GHI ============
        errors = []
        if not title_line:
            errors.append("Thiếu tiêu đề")
        if len(content_lines) < 1:
            errors.append("Thiếu nội dung")
        if len(answers) < 4:
            errors.append(f"Thiếu đáp án ({len(answers)}/4)")
        if not solution_header:
            errors.append("Thiếu header lời giải")
        if not correct_answer:
            errors.append("Thiếu đáp án đúng")
        if len(explanation_lines) < 1:
            errors.append("Thiếu giải thích")
        
        if errors:
            error_msg = ", ".join(errors)
            raise Exception(error_msg)
        
        # ============ GHI VÀO DOCX ============
        
        # 1. Tiêu đề
        p = doc.add_paragraph()
        run = p.add_run(title_line)
        run.bold = True
        run.font.size = Pt(12)
        
        # 2. Nội dung câu hỏi
        for line in content_lines:
            if line.strip():
                p = doc.add_paragraph()
                if "**" in line:
                    process_bold_text(line, p)
                else:
                    process_text(line, p)
        
        # 3. Hình ảnh
        if image_desc:
            should_generate = False
            if image_tracker:
                should_generate = image_tracker.should_generate(qnum, 80)
            
            try:
                success, img_para, is_placeholder = handle_image_generation(
                    image_desc,
                    doc,
                    attempt_generate=should_generate,
                    tracker=image_tracker
                )
            except Exception as img_error:
                print(f"   ⚠️  Lỗi khi sinh ảnh: {img_error}")
                p = doc.add_paragraph()
                run = p.add_run(f"[HÌNH ẢNH: {image_desc}]")
                from docx.shared import RGBColor
                run.font.color.rgb = RGBColor(255, 140, 0)
                run.italic = True
        
        # 4. Đáp án
        for ans in answers[:4]:
            p = doc.add_paragraph()
            process_text(ans, p)
        
        # 5. Khoảng cách
        doc.add_paragraph()
        
        # 6. Lời giải header
        p = doc.add_paragraph()
        run = p.add_run(solution_header)
        run.bold = True
        
        # 7. Đáp án đúng
        p = doc.add_paragraph()
        run = p.add_run(correct_answer)
        run.bold = True
        
        # 8. Separator
        p = doc.add_paragraph()
        run = p.add_run("####")
        run.bold = True
        
        # 9. Giải thích
        max_lines = 5 if question_type == "tracnghiem" else len(explanation_lines)
        for line in explanation_lines[:max_lines]:
            if line.strip():
                p = doc.add_paragraph()
                if "**" in line:
                    process_bold_text(line, p)
                else:
                    process_text(line, p)
    
    def _regenerate_single_question(
        self,
        qnum: int,
        enhanced_prompt: str,
        storage: ValidQuestionStorage,
        question_type: str
    ) -> str:
        """
        Sinh lại MỘT câu hỏi
        
        Returns:
            Text câu hỏi mới (hoặc None nếu thất bại)
        """
        # Tạo prompt
        regen_prompt = self._create_batch_prompt(
            [qnum],
            enhanced_prompt,
            storage,
            question_type
        )
        
        try:
            response = self.client.send_data_to_check(
                prompt=regen_prompt,
                temperature=0.6
            )
            
            if not response:
                return None
            
            # Parse
            validator = QuestionValidator(question_type=question_type)
            questions = validator.parse_questions(response)
            
            if qnum not in questions:
                return None
            
            qtext = questions[qnum]
            
            # Validate
            validation = validator.validate_single_question(qtext, qnum)
            
            if validation.is_valid:
                return qtext
            else:
                return None
                
        except Exception as e:
            return None
    
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
            "**LƯU Ý**: Không được phép trích dẫn từ trong sách ra",
            "",
            "BẮT ĐẦU SINH:",
            ""
        ])
        
        return "\n".join(prompt_parts)
    
    def _get_level_guidance_for_batch(self, batch_nums: List[int], question_type: str) -> str:
        """Tạo hướng dẫn mức độ cho batch"""
        
        if question_type == "tracnghiem":
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
                "- Câu 1-24: Mức độ Nhận biết (câu hỏi ngắn gọn, kiểm tra khả năng nhớ)",
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