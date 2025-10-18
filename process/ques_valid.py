import re
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass
from api.callAPI import VertexClient

@dataclass
class QuestionValidation:
    """Class lưu kết quả kiểm tra một câu hỏi"""
    question_num: int
    has_title: bool = False
    has_content: bool = False
    has_image: bool = False
    answer_count: int = 0
    has_solution_header: bool = False
    has_correct_answer: bool = False
    has_separator: bool = False
    has_explanation: bool = False
    explanation_length: int = 0  # Số dòng giải thích
    
    @property
    def is_valid(self) -> bool:
        """Kiểm tra câu hỏi có hợp lệ không"""
        return (
            self.has_title and
            self.has_content and
            self.answer_count == 4 and
            self.has_solution_header and
            self.has_correct_answer and
            self.has_separator and
            self.has_explanation and
            self.explanation_length >= 1  # Ít nhất 3 dòng giải thích cho đáp án đúng
        )
    
    @property
    def missing_parts(self) -> List[str]:
        """Liệt kê các phần bị thiếu"""
        missing = []
        if not self.has_title:
            missing.append("Tiêu đề câu hỏi")
        if not self.has_content:
            missing.append("Nội dung câu hỏi")
        if self.answer_count < 4:
            missing.append(f"Đáp án (chỉ có {self.answer_count}/4)")
        if not self.has_solution_header:
            missing.append("Header 'Lời giải'")
        if not self.has_correct_answer:
            missing.append("Đáp án đúng (1-4 hoặc 1010)")
        if not self.has_separator:
            missing.append("Dấu phân cách ####")
        if not self.has_explanation:
            missing.append("Giải thích")
        elif self.explanation_length < 1:
            missing.append(f"Giải thích quá ngắn ({self.explanation_length} dòng, cần ít nhất 3 dòng cho đáp án đúng)")
        return missing

class ValidQuestionStorage:
    """Class lưu trữ các câu hỏi đã hợp lệ để tránh sinh lại"""
    
    def __init__(self):
        self.valid_questions: Dict[int, str] = {}  # {question_num: question_text}
        self.valid_nums: Set[int] = set()
    
    def add_valid_question(self, question_num: int, question_text: str):
        """Thêm câu hỏi hợp lệ vào storage"""
        # Cho phép thay thế nếu đã tồn tại (dùng cho trường hợp regen/sửa câu)
        self.valid_questions[question_num] = question_text
        self.valid_nums.add(question_num)

    def replace_question(self, question_num: int, question_text: str):
        """Thay thế nội dung câu hỏi (nếu đã có thì ghi đè)."""
        self.valid_questions[question_num] = question_text
        self.valid_nums.add(question_num)
    
    def get_valid_count(self) -> int:
        """Đếm số câu hợp lệ"""
        return len(self.valid_questions)
    
    def get_missing_nums(self, required_count: int) -> List[int]:
        """Lấy danh sách số câu còn thiếu"""
        required_nums = set(range(1, required_count + 1))
        missing = sorted(required_nums - self.valid_nums)
        return missing
    
    def reconstruct_full_text(self, required_count=None) -> str:
        """Ghép lại text đầy đủ từ các câu hợp lệ, luôn sắp xếp đúng thứ tự từ 1 đến required_count (nếu có)"""
        if required_count is not None:
            question_nums = list(range(1, required_count + 1))
        else:
            question_nums = sorted(self.valid_questions.keys())
        parts = []
        for qn in question_nums:
            if qn in self.valid_questions:
                parts.append(self.valid_questions[qn])
        return "\n\n".join(parts)

    def count_questions_with_image(self) -> int:
        """Đếm số câu có hình ảnh trong valid_questions"""
        pattern = re.compile(r'\[HÌNH ?ẢNH[\]:]', re.IGNORECASE)
        count = 0
        for text in self.valid_questions.values():
            if pattern.search(text):
                count += 1
        return count

    def count_level_distribution(self, level_regexes=None) -> dict:
        """Đếm số câu ở mỗi mức độ theo heading (trả ra dict)"""
        if not level_regexes:
            level_regexes = {
                'Nhận biết': re.compile(r'(MỨC ĐỘ|#|##|###)?\s*Nhận biết', re.IGNORECASE),
                'Thông hiểu': re.compile(r'(MỨC ĐỘ|#|##|###)?\s*Thông hiểu', re.IGNORECASE),
                'Vận dụng': re.compile(r'(MỨC ĐỘ|#|##|###)?\s*Vận dụng(?! cao)', re.IGNORECASE),
                'Vận dụng cao': re.compile(r'(MỨC ĐỘ|#|##|###)?\s*Vận dụng cao', re.IGNORECASE)
            }
        levels_count = {lv: 0 for lv in level_regexes}
        for text in self.valid_questions.values():
            for lv, rgx in level_regexes.items():
                if rgx.search(text):
                    levels_count[lv] += 1
                    break
        return levels_count
    
    def get_question_level_by_number(self, question_num: int, question_type: str = "tracnghiem") -> str:
        """Xác định mức độ nhận thức dựa trên số thứ tự câu hỏi"""
        if question_type == "tracnghiem":
            if 1 <= question_num <= 24:
                return "Nhận biết"
            elif 25 <= question_num <= 48:
                return "Thông hiểu"
            elif 49 <= question_num <= 72:
                return "Vận dụng"
            elif 73 <= question_num <= 80:
                return "Vận dụng cao"
        else:  # dungsai
            if 1 <= question_num <= 20:
                return "Thông hiểu"
            elif 21 <= question_num <= 32:
                return "Vận dụng"
            elif 33 <= question_num <= 40:
                return "Vận dụng cao"
        return "Không xác định"

    def validate_distribution(self, required_count, required_img_percent=0.2, level_targets=None, question_type="tracnghiem"):
        """Kiểm tra số lượng hình và mức độ theo tỷ lệ định nghĩa"""
        results = {}
        # Check ảnh
        img_count = self.count_questions_with_image()
        min_required_img = int(round(required_count * required_img_percent))
        results["image_enough"] = img_count >= min_required_img
        results["img_have"] = img_count
        results["img_need"] = min_required_img

        # Check mức độ dựa trên số thứ tự câu hỏi (chính xác hơn)
        if not level_targets:
            if question_type == "tracnghiem":
                level_targets = {
                    'Nhận biết': 24,    # Câu 1-24
                    'Thông hiểu': 24,   # Câu 25-48
                    'Vận dụng': 24,     # Câu 49-72
                    'Vận dụng cao': 8,  # Câu 73-80
                }
            else:  # dungsai
                level_targets = {
                    'Thông hiểu': 20,   # Câu 1-20
                    'Vận dụng': 12,     # Câu 21-32
                    'Vận dụng cao': 8,  # Câu 33-40
                }
        
        # Đếm câu hỏi theo mức độ dựa trên số thứ tự
        levels_count = {}
        for lv in level_targets.keys():
            levels_count[lv] = 0
        
        for qnum in self.valid_nums:
            level = self.get_question_level_by_number(qnum, question_type)
            if level in levels_count:
                levels_count[level] += 1
        
        level_ok = True
        short_levels = {}
        for lv, req_num in level_targets.items():
            have = levels_count.get(lv, 0)
            short = req_num - have
            short_levels[lv] = short if short > 0 else 0
            if have < req_num:
                level_ok = False
        results['level_ok'] = level_ok
        results['level_stat'] = levels_count
        results['level_target'] = level_targets
        results['level_short'] = short_levels
        return results
    
    def has_question(self, question_num: int) -> bool:
        """Kiểm tra câu hỏi đã tồn tại chưa"""
        return question_num in self.valid_nums



class QuestionValidator:
    """Class kiểm tra và bổ sung câu hỏi"""
    
    def __init__(self, question_type: str = "tracnghiem"):
        """
        Args:
            question_type: "tracnghiem" hoặc "dungsai"
        """
        self.question_type = question_type
        self.required_count = 80 if question_type == "tracnghiem" else 40
    
    def parse_questions(self, text: str) -> Dict[int, str]:
        """
        Tách text thành từng câu hỏi riêng biệt
        
        Returns:
            Dict {question_num: question_text}
        """
        questions = {}
        # Làm sạch hội thoại/thinking và code fences ở mức thô trước khi parse
        cleaned = re.sub(r'```[a-zA-Z0-9_-]*\n?', '', text)
        cleaned = cleaned.replace('```', '')
        cleaned = re.sub(r'(?im)^\s*(assistant|user|system)\s*:\s*.*$', '', cleaned)
        cleaned = re.sub(r'(?im)^(thought|reasoning|chain[- ]of[- ]thought|let\'s|as an ai).*$', '', cleaned)
        lines = cleaned.split("\n")
        current_question_num = None
        current_question_lines = []
        
        for line in lines:
            # Phát hiện tiêu đề câu hỏi mới
            match = re.match(r'^\*?\*?Câu\s+(\d+)[:\.]?\*?\*?', line, re.IGNORECASE)
            if match:
                # Lưu câu hỏi cũ
                if current_question_num is not None and current_question_lines:
                    questions[current_question_num] = "\n".join(current_question_lines)
                
                # Bắt đầu câu hỏi mới
                current_question_num = int(match.group(1))
                current_question_lines = [line]
            else:
                # Tiếp tục câu hỏi hiện tại
                if current_question_num is not None:
                    current_question_lines.append(line)
        
        # Lưu câu hỏi cuối
        if current_question_num is not None and current_question_lines:
            questions[current_question_num] = "\n".join(current_question_lines)
        
        return questions
    
    def validate_single_question(self, question_text: str, question_num: int) -> QuestionValidation:
        """
        Kiểm tra một câu hỏi có đầy đủ thành phần không
        
        Args:
            question_text: Nội dung câu hỏi
            question_num: Số thứ tự câu hỏi
            
        Returns:
            QuestionValidation object
        """
        validation = QuestionValidation(question_num=question_num)
        lines = question_text.split("\n")
        
        in_explanation = False
        explanation_lines = 0
        
        for line in lines:
            # Sanitize AI dialogue/thinking inline while validating
            if re.match(r'(?im)^\s*(assistant|user|system)\s*:\s*', line):
                continue
            if re.match(r'(?im)^(thought|reasoning|chain[- ]of[- ]thought|let\'s|as an ai)', line.strip()):
                continue
            if line.strip().startswith('```'):
                continue
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # 1. Kiểm tra tiêu đề
            if re.match(r'^\*?\*?Câu\s+\d+[:\.]?\*?\*?', line, re.IGNORECASE):
                validation.has_title = True
            
            # 2. Kiểm tra có nội dung câu hỏi (dòng không phải đáp án, không phải header)
            elif (not re.match(r'^[A-Da-d][\.\)]', line_stripped) and
                  not re.match(r'^\*?\*?Lời giải[:\.]?\*?\*?', line, re.IGNORECASE) and
                  not re.match(r'^[1-4]$', line_stripped) and
                  not re.match(r'^[01]{4}$', line_stripped) and
                  line_stripped != "####" and
                  not in_explanation):
                validation.has_content = True
            
            # 3. Kiểm tra hình ảnh
            if re.search(r'\[?\s*(HÌNH ẢNH|Hình ảnh|hình ảnh)', line, re.IGNORECASE):
                validation.has_image = True
            
            # 4. Đếm đáp án A/B/C/D hoặc a)/b)/c)/d)
            if re.match(r'^[A-Da-d][\.\)]', line_stripped):
                validation.answer_count += 1
            
            # 5. Kiểm tra header "Lời giải"
            if re.match(r'^\*?\*?Lời giải[:\.]?\*?\*?', line, re.IGNORECASE):
                validation.has_solution_header = True
            
            # 6. Kiểm tra đáp án đúng (1-4 hoặc 1010)
            if re.match(r'^[1-4]$', line_stripped) or re.match(r'^[01]{4}$', line_stripped):
                validation.has_correct_answer = True
            
            # 7. Kiểm tra dấu phân cách ####
            if line_stripped == "####":
                validation.has_separator = True
                in_explanation = True
            
            # 8. Đếm dòng giải thích (sau dấu ####)
            if in_explanation and line_stripped and line_stripped != "####":
                explanation_lines += 1
        
        validation.has_explanation = explanation_lines > 0
        validation.explanation_length = explanation_lines
        
        return validation
    
    def validate_all_questions(self, text: str) -> Tuple[List[QuestionValidation], List[int]]:
        """
        Kiểm tra toàn bộ đề bài
        Returns:
            Tuple (list_validations, missing_question_numbers)
        """
        print(f"\n{'='*60}")
        print(f"🔍 BẮT ĐẦU KIỂM TRA ĐỀ BÀI")
        print(f"{'='*60}\n")
        
        questions = self.parse_questions(text)
        validations = []
        
        print(f"📊 Tìm thấy {len(questions)} câu trong đề bài")
        print(f"📋 Yêu cầu: {self.required_count} câu\n")
        
        # Lưu lại các câu question_num -> text để hỗ trợ kiểm tra phân bố
        temp_storage = ValidQuestionStorage()
        for qnum, qtext in questions.items():
            temp_storage.add_valid_question(qnum, qtext)
        
        # Kiểm tra từng câu có trong text
        for qnum, qtext in sorted(questions.items()):
            validation = self.validate_single_question(qtext, qnum)
            validations.append(validation)
            
            if not validation.is_valid:
                print(f"⚠️  Câu {qnum}: THIẾU - {', '.join(validation.missing_parts)}")
            else:
                print(f"✅ Câu {qnum}: Hợp lệ")
        
        # Tìm câu bị thiếu hoàn toàn
        existing_nums = set(questions.keys())
        required_nums = set(range(1, self.required_count + 1))
        missing_nums = sorted(required_nums - existing_nums)
        
        if missing_nums:
            print(f"\n❌ THIẾU HOÀN TOÀN {len(missing_nums)} CÂU: {missing_nums[:10]}" + 
                  (f" và {len(missing_nums)-10} câu khác" if len(missing_nums) > 10 else ""))
        
        print(f"\n{'='*60}")
        print(f"📊 KẾT QUẢ KIỂM TRA")
        print(f"{'='*60}")
        valid_count = sum(1 for v in validations if v.is_valid)
        invalid_count = len(validations) - valid_count
        print(f"✅ Câu hợp lệ: {valid_count}")
        print(f"⚠️  Câu thiếu thành phần: {invalid_count}")
        print(f"❌ Câu thiếu hoàn toàn: {len(missing_nums)}")
        print(f"{'='*60}\n")
        
        # --- Validate phân bố mức độ và hình ảnh NẾU đã đủ số lượng câu ---
        if valid_count >= self.required_count:
            dist_stat = temp_storage.validate_distribution(self.required_count, question_type=self.question_type)
            print("▶️ Phân bố mức độ nhận thức:")
            for lv, num in dist_stat['level_stat'].items():
                tar = dist_stat['level_target'][lv]
                short = dist_stat['level_short'][lv]
                status = "OK" if num >= tar else f"Thiếu {short}"
                print(f"- {lv}: {num}/{tar} ({status})")
            if not dist_stat['level_ok']:
                print("❌ Cảnh báo: Chưa đủ phân bố theo mức độ:")
                for lv, n in dist_stat['level_short'].items():
                    if n > 0:
                        print(f"  - Thiếu {n} câu mức {lv}")
                print("Bạn cần sinh/bổ sung đúng các nhóm câu còn thiếu!")
            else:
                print("✅ Đã đủ tỷ lệ các mức độ!")
            print("▶️ Phân bố số câu có hình ảnh:")
            print(f"- Có hình ảnh: {dist_stat['img_have']}/{dist_stat['img_need']} câu ({'Đủ' if dist_stat['image_enough'] else 'Thiếu'})")
            if not dist_stat['image_enough']:
                print(f"❌ Cảnh báo: Chưa đủ số câu có hình ảnh theo yêu cầu!")
        else:
            print("ℹ️ Chưa kiểm tra phân bố mức độ và hình ảnh do chưa đủ số lượng câu hợp lệ.")
        
        return validations, missing_nums
    
    def generate_fix_prompt(self, validations: List[QuestionValidation], 
                           missing_nums: List[int],
                           original_prompt: str,
                           full_text: str,
                           image_short_count: int = 0,
                           levels_short_dict: dict = None) -> str:
        """
        Tạo prompt để AI bổ sung/sửa các câu hỏi.
        Có thể truyền thêm số lượng câu thiếu hình ảnh (image_short_count) và dict thiếu mức độ (levels_short_dict) để AI ưu tiên sinh đúng nhóm còn thiếu, tránh lạc phân bố!
        """
        # Lấy các câu cần sửa
        questions_to_fix = [v for v in validations if not v.is_valid]
        
        if not questions_to_fix and not missing_nums:
            return None  # Không cần sửa gì
        
        prompt_parts = [
            "# YÊU CẦU BỔ SUNG VÀ SỬA CHỮA ĐỀ BÀI\n",
            "## TÌNH TRẠNG HIỆN TẠI\n"
        ]

        # Báo thêm về thiếu hình ảnh / mức độ nếu có
        custom_notice = []
        if image_short_count and image_short_count > 0:
            custom_notice.append(f"- 💡 Còn thiếu {image_short_count} câu có hình ảnh. Phải ưu tiên bổ sung group này!")
        if levels_short_dict:
            for lv, n in levels_short_dict.items():
                if n > 0:
                    custom_notice.append(f"- 💡 Thiếu {n} câu mức '{lv}'. Phải ưu tiên sinh group này!")
        if custom_notice:
            prompt_parts.append("\n".join(custom_notice)+"\n")
        
        # Thêm hướng dẫn phân bố mức độ cụ thể
        if self.question_type == "tracnghiem":
            prompt_parts.extend([
                "\n## 🎯 QUY TẮC PHÂN BỐ MỨC ĐỘ (80 CÂU TRẮC NGHIỆM)\n",
                "**TUYỆT ĐỐI PHẢI TUÂN THEO THỨ TỰ SAU:**\n",
                "- Câu 1-24: MỨC ĐỘ NHẬN BIẾT (30%)\n",
                "- Câu 25-48: MỨC ĐỘ THÔNG HIỂU (30%)\n", 
                "- Câu 49-72: MỨC ĐỘ VẬN DỤNG (30%)\n",
                "- Câu 73-80: MỨC ĐỘ VẬN DỤNG CAO (10%)\n",
                "\n**QUAN TRỌNG:** Khi sinh câu hỏi, phải xác định rõ câu đó thuộc mức độ nào và sinh theo đúng đặc điểm của mức độ đó!\n"
            ])
        else:  # dungsai
            prompt_parts.extend([
                "\n## 🎯 QUY TẮC PHÂN BỐ MỨC ĐỘ (40 CÂU ĐÚNG/SAI)\n",
                "**TUYỆT ĐỐI PHẢI TUÂN THEO THỨ TỰ SAU:**\n",
                "- Câu 1-20: MỨC ĐỘ THÔNG HIỂU (50%)\n",
                "- Câu 21-32: MỨC ĐỘ VẬN DỤNG (30%)\n",
                "- Câu 33-40: MỨC ĐỘ VẬN DỤNG CAO (20%)\n",
                "\n**QUAN TRỌNG:** Khi sinh câu hỏi, phải xác định rõ câu đó thuộc mức độ nào và sinh theo đúng đặc điểm của mức độ đó!\n"
            ])
        
        # 1. Liệt kê câu thiếu hoàn toàn
        if missing_nums:
            prompt_parts.append(f"\n### ❌ THIẾU HOÀN TOÀN {len(missing_nums)} CÂU:")
            prompt_parts.append(f"Các câu số: {', '.join(map(str, missing_nums[:20]))}")
            if len(missing_nums) > 20:
                prompt_parts.append(f"... và {len(missing_nums)-20} câu khác")
            prompt_parts.append("\n**YÊU CẦU:** Sinh đầy đủ các câu này theo đúng format.\n")
        
        # 2. Liệt kê câu thiếu thành phần
        if questions_to_fix:
            prompt_parts.append(f"\n### ⚠️  CÓ {len(questions_to_fix)} CÂU THIẾU THÀNH PHẦN:")
            for v in questions_to_fix[:10]:  # Chỉ liệt kê 10 câu đầu
                prompt_parts.append(f"\n**Câu {v.question_num}:**")
                for missing_part in v.missing_parts:
                    prompt_parts.append(f"  - Thiếu: {missing_part}")
            
            if len(questions_to_fix) > 10:
                prompt_parts.append(f"\n... và {len(questions_to_fix)-10} câu khác cũng thiếu thành phần")
            
            prompt_parts.append("\n**YÊU CẦU:** Bổ sung đầy đủ các phần còn thiếu.\n")
        
        # 3. Yêu cầu cụ thể
        prompt_parts.extend([
            "\n## YÊU CẦU CHI TIẾT\n",
            "1. **Đối với câu THIẾU HOÀN TOÀN:** Sinh lại toàn bộ câu hỏi theo đúng format",
            "2. **Đối với câu THIẾU THÀNH PHẦN:** Chỉ bổ sung phần thiếu, GIỮ NGUYÊN phần đã có",
            "3. **Format bắt buộc:**",
            "   - Tiêu đề: **Câu X:**",
            "   - Nội dung câu hỏi (ít nhất 2-3 dòng)",
            "   - 4 đáp án A, B, C, D (hoặc a), b), c), d) với đúng/sai)",
            "   - Header: **Lời giải:**",
            "   - Đáp án đúng: 1 số từ 1-4 (hoặc mã 1010 với đúng/sai)",
            "   - Dấu phân cách: ####",
            "   - Giải thích tối thiểu 3 dòng, CHỈ giải thích đáp án đúng, không giải thích các đáp án sai",
            "4. **TUYỆT ĐỐI KHÔNG:**",
            "   - Thay đổi số thứ tự câu hỏi",
            "   - Thay đổi nội dung các câu đã hợp lệ",
            "   - Thêm lời mở đầu, hội thoại, thinking, hoặc kết thúc ngoài yêu cầu",
            "\n## FORMAT MONG MUỐN\n"
        ])
        
        # 4. Thêm format mẫu
        if self.question_type == "tracnghiem":
            prompt_parts.extend([
                "```",
                "**Câu X:**",
                "[Nội dung câu hỏi]",
                "[HÌNH ẢNH: mô tả] (nếu cần)",
                "",
                "A. [Đáp án 1]",
                "B. [Đáp án 2]",
                "C. [Đáp án 3]",
                "D. [Đáp án 4]",
                "**Lời giải:** (chỉ giải thích đáp án đúng, tối thiểu 3 dòng)",
                "2",
                "####",
                "[Giải thích chi tiết, tối thiểu 3 dòng, chỉ lý do đáp án 2 đúng]",
                "```\n"
            ])
        else:  # dungsai
            prompt_parts.extend([
                "```",
                "**Câu X:**",
                "[Đoạn văn 50-100 từ mô tả tình huống]",
                "[HÌNH ẢNH: mô tả] (nếu cần)",
                "",
                "a) [Phát biểu 1]",
                "b) [Phát biểu 2]",
                "c) [Phát biểu 3]",
                "d) [Phát biểu 4]",
                "**Lời giải:** (chỉ giải thích vì sao từng phát biểu đúng/sai, tránh hội thoại)",
                "1010",
                "####",
                "- [Nội dung phát biểu a] là ĐÚNG. Giải thích 1-2 dòng.",
                "",
                "- [Nội dung phát biểu b] là SAI. Giải thích 1-2 dòng.",
                "...",
                "```\n"
            ])
        
        # 5. Đính kèm đề hiện tại
        prompt_parts.extend([
            "\n## ĐỀ BÀI HIỆN TẠI (để tham khảo)\n",
            "```",
            full_text[:5000],  # Chỉ lấy 5000 ký tự đầu để tránh quá dài
            "```\n" if len(full_text) > 5000 else "```\n",
            "\n## BẮT ĐẦU BỔ SUNG/SỬA CHỮA\n",
            "Hãy trả về TOÀN BỘ đề bài đã được sửa chữa và bổ sung đầy đủ.",
            "GIỮ NGUYÊN các câu đã hợp lệ, chỉ sửa/thêm các câu có vấn đề.\n"
        ])
        
        return "\n".join(prompt_parts)
    
    def fix_questions_with_ai(self, text: str, original_prompt: str,
                             client: VertexClient, max_attempts: int = 7) -> str:
        """
        Tự động kiểm tra và bổ sung câu hỏi bằng AI
        Khi regen, nếu phát hiện thiếu mức độ hoặc hình ảnh, sẽ thêm chú dẫn rõ ràng vào prompt gửi AI!
        """
        current_text = text
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            print(f"\n{'='*60}")
            print(f"🔄 VÒNG KIỂM TRA VÀ SỬA LẦN {attempt}/{max_attempts}")
            print(f"{'='*60}\n")
            
            # Kiểm tra
            validations, missing_nums = self.validate_all_questions(current_text)
            
            # Kiểm tra phân bổ mức độ/hình ảnh nếu đã đủ basic
            temp_storage = ValidQuestionStorage()
            for v in validations:
                if v.is_valid:
                    temp_storage.add_valid_question(v.question_num, f"dummy") # chỉ cần num không cần text
            dist_stat = temp_storage.validate_distribution(self.required_count, question_type=self.question_type)
            img_short = dist_stat['img_need'] - dist_stat['img_have'] if dist_stat['img_need'] > dist_stat['img_have'] else 0
            levels_short = dist_stat['level_short']
            # Tạo prompt sửa
            fix_prompt = self.generate_fix_prompt(
                validations, missing_nums, original_prompt, current_text,
                image_short_count=img_short, levels_short_dict=levels_short
            )
            
            print(f"\n📤 Gửi yêu cầu sửa chữa đến AI...")
            print(f"   - Số câu cần sửa thành phần: {len([v for v in validations if not v.is_valid])}")
            print(f"   - Số câu thiếu hoàn toàn: {len(missing_nums)}\n")
            
            # Gọi AI
            try:
                fixed_text = client.send_data_to_check(prompt=fix_prompt)
                current_text = fixed_text
                print(f"✅ Đã nhận phản hồi từ AI\n")
            except Exception as e:
                print(f"❌ Lỗi khi gọi AI: {e}\n")
                break
        
        # Kiểm tra lần cuối
        print(f"\n{'='*60}")
        print(f"🔍 KIỂM TRA CUỐI CÙNG")
        print(f"{'='*60}\n")
        validations, missing_nums = self.validate_all_questions(current_text)
        invalid_questions = [v for v in validations if not v.is_valid]
        
        if not invalid_questions and not missing_nums:
            print("\n🎉 ĐỀ BÀI ĐÃ HOÀN CHỈNH!\n")
        else:
            print(f"\n⚠️  VẪN CÒN {len(invalid_questions)} CÂU THIẾU THÀNH PHẦN")
            print(f"⚠️  VẪN CÒN {len(missing_nums)} CÂU THIẾU HOÀN TOÀN")
            print(f"💡 Bạn có thể chạy lại hoặc kiểm tra thủ công.\n")
        
        return current_text


# ==================== FUNCTIONS ĐỂ TÍCH HỢP VÀO response2docx.py ====================

def validate_and_fix_response(AIresponse: str, original_prompt: str,
                              client: VertexClient, question_type: str = "tracnghiem") -> str:
    """
    CHÚ Ý: original_prompt PHẢI LÀ prompt đã được thay thế subject/grade động!
    """
    validator = QuestionValidator(question_type=question_type)
    fixed_text = validator.fix_questions_with_ai(
        AIresponse, 
        original_prompt, 
        client,
        max_attempts=7
    )
    return fixed_text

# ====== CHÚ Ý: PROMPT PHẢI LUÔN LÀ BẢN ĐÃ REPLACE subject/grade TUYỆT ĐỐI KHÔNG ĐỌC FILE LẠI ======
def regenerate_invalid_questions(invalid_nums: List[int], 
                                 original_prompt: str,
                                 storage: ValidQuestionStorage,
                                 client: VertexClient,
                                 question_type: str = "tracnghiem",
                                 max_attempts: int = 7) -> str:
    """
    Sinh lại chỉ các câu không hợp lệ/thiếu
    CHÚ Ý: original_prompt phải truyền bản đã thay thế subject/grade động.
    """
    if not invalid_nums:
        return ""
    
    print(f"\n{'='*60}")
    print(f"\n🔄 SINH LẠI {len(invalid_nums)} CÂU\n")
    print(f"Danh sách: {invalid_nums[:20]}" + (f"... và {len(invalid_nums)-20} câu khác" if len(invalid_nums) > 20 else ""))
    print(f"\n{'='*60}\n")
    
    # Lấy mẫu từ các câu hợp lệ để tránh trùng
    existing_samples = []
    for qnum in sorted(storage.valid_nums)[:5]:
        qtext = storage.valid_questions[qnum]
        preview = qtext.split("\n")[1:3]
        existing_samples.append(f"Câu {qnum}: {' '.join(preview)[:80]}...")
    
    # Tạo prompt sinh lại với hướng dẫn phân bố mức độ
    level_guidance = ""
    if question_type == "tracnghiem":
        level_guidance = """
## 🎯 QUY TẮC PHÂN BỐ MỨC ĐỘ (80 CÂU TRẮC NGHIỆM)
**TUYỆT ĐỐI PHẢI TUÂN THEO THỨ TỰ SAU:**
- Câu 1-24: MỨC ĐỘ NHẬN BIẾT (30%) - Câu hỏi ngắn gọn, kiểm tra khả năng nhớ và nhận diện
- Câu 25-48: MỨC ĐỘ THÔNG HIỂU (30%) - Kiểm tra khả năng giải thích, so sánh, phân loại
- Câu 49-72: MỨC ĐỘ VẬN DỤNG (30%) - Kiểm tra khả năng áp dụng kiến thức vào tình huống thực tế
- Câu 73-80: MỨC ĐỘ VẬN DỤNG CAO (10%) - Câu hỏi phức tạp, đòi hỏi tư duy phản biện và sáng tạo

**QUAN TRỌNG:** Khi sinh câu hỏi, phải xác định rõ câu đó thuộc mức độ nào và sinh theo đúng đặc điểm của mức độ đó!
"""
    else:  # dungsai
        level_guidance = """
## 🎯 QUY TẮC PHÂN BỐ MỨC ĐỘ (40 CÂU ĐÚNG/SAI)
**TUYỆT ĐỐI PHẢI TUÂN THEO THỨ TỰ SAU:**
- Câu 1-20: MỨC ĐỘ THÔNG HIỂU (50%) - Kiểm tra khả năng giải thích và so sánh
- Câu 21-32: MỨC ĐỘ VẬN DỤNG (30%) - Kiểm tra khả năng áp dụng kiến thức vào tình huống thực tế
- Câu 33-40: MỨC ĐỘ VẬN DỤNG CAO (20%) - Câu hỏi phức tạp, đòi hỏi tư duy phản biện và sáng tạo

**QUAN TRỌNG:** Khi sinh câu hỏi, phải xác định rõ câu đó thuộc mức độ nào và sinh theo đúng đặc điểm của mức độ đó!
"""

    # Tạo prompt sinh lại
    regenerate_prompt = f"""{original_prompt}

# YÊU CẦU BỔ SUNG CÂU HỎI

## TÌNH HUỐNG
Đã có {storage.get_valid_count()} câu hợp lệ. Cần sinh lại {len(invalid_nums)} câu BỊ LỖI hoặc THIẾU.

{level_guidance}

## CÁC CÂU CẦN SINH (QUAN TRỌNG)
Sinh CHÍNH XÁC các câu sau: {', '.join(map(str, invalid_nums[:20]))}
{'... và ' + str(len(invalid_nums)-20) + ' câu khác' if len(invalid_nums) > 20 else ''}

## MỘT SỐ CÂU ĐÃ HỢP LỆ (TRÁNH TRÙNG LẶP)
{chr(10).join(existing_samples)}

## YÊU CẦU TUYỆT ĐỐI
1. CHỈ sinh các câu trong danh sách trên, ĐÚNG SỐ THỨ TỰ
2. Nội dung HOÀN TOÀN KHÁC với các câu đã có
3. Mỗi câu PHẢI ĐẦY ĐỦ format: tiêu đề, nội dung, 4 đáp án, lời giải, giải thích (tối thiểu 3 dòng)
4. BÁM SÁT chủ đề từ PDF đã quét
5. KHÔNG thêm lời mở đầu/kết thúc
6. **QUAN TRỌNG:** Mỗi câu phải được sinh theo đúng mức độ nhận thức tương ứng với số thứ tự của nó!

BẮT ĐẦU SINH:
"""
    successfully_generated = []
    
    # Sinh với retry
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"\n   Lần thử {attempt}/{max_attempts}...")
            new_text = client.send_data_to_check(
                prompt=regenerate_prompt,
                temperature=0.65 + (attempt * 0.1)
            )
            
            # Parse và validate từng câu mới sinh
            from process.ques_valid import QuestionValidator
            validator = QuestionValidator(question_type=question_type)
            new_questions = validator.parse_questions(new_text)
            
            print(f"   📝 Nhận được {len(new_questions)} câu từ AI")
            
            # Validate và lưu từng câu
            newly_valid = []
            for qnum, qtext in sorted(new_questions.items()):
                # Chỉ xử lý câu trong danh sách cần sinh
                if qnum not in invalid_nums:
                    print(f"   ⏭️  Câu {qnum}: Không trong danh sách cần sinh, bỏ qua")
                    continue
                
                # Cho phép ghi đè câu đã có nếu đang sinh lại để sửa
                if storage.has_question(qnum):
                    print(f"   ✏️  Câu {qnum}: Đang thay thế nội dung cũ bằng nội dung mới")
                
                # Validate
                validation = validator.validate_single_question(qtext, qnum)
                
                if validation.is_valid:
                    # Ghi đè/ghi mới đều qua replace cho rõ ràng
                    storage.replace_question(qnum, qtext)
                    newly_valid.append(qnum)
                    successfully_generated.append(qnum)
                    print(f"\n   ✅ Câu {qnum}: Hợp lệ → LƯU\n")
                else:
                    print(f"\n   ❌ Câu {qnum}: Vẫn thiếu {', '.join(validation.missing_parts)}\n")
            
            # Kiểm tra xem còn câu nào cần sinh không
            remaining = [n for n in invalid_nums if n not in successfully_generated]
            
            if not remaining:
                print(f"\n   🎉 Đã sinh đủ tất cả {len(invalid_nums)} câu!\n")
                break
            else:
                print(f"\n   ⚠️  Còn {len(remaining)} câu cần sinh tiếp")
                # Cập nhật danh sách cần sinh cho lần thử tiếp theo
                invalid_nums = remaining
                
        except Exception as e:
            print(f"   ✗ Lỗi: {e}")
    
    # Ghép lại text từ các câu đã sinh thành công
    result_parts = []
    for qnum in sorted(successfully_generated):
        result_parts.append(storage.valid_questions[qnum])
    
    print(f"\n📊 Kết quả: Sinh thành công {len(successfully_generated)} câu")
    return "\n\n".join(result_parts)


