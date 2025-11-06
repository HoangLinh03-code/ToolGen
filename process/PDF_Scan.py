"""
Module quét và phân tích nội dung PDF để sinh câu hỏi chính xác
"""
import os
import re
from typing import List, Dict, Tuple
from api.callAPI import VertexClient


class PDFScanner:
    """Class quét và phân tích nội dung từ 3 file PDF: SGK, SBT, SGV"""
    
    def __init__(self, project_id: str, creds, model_name: str = "gemini-2.5-pro"):
        """
        Args:
            project_id: Google Cloud Project ID
            creds: Service account credentials
            model_name: Model name để quét PDF
        """
        self.client = VertexClient(project_id, creds, model_name)
        self.pdf_types = {
            "sgk": "Sách Giáo Khoa",
            "sbt": "Sách Bài Tập", 
            "sgv": "Sách Giáo Viên"
        }
    
    def identify_pdf_types(self, pdf_files: List[str]) -> Dict[str, str]:
        """
        Nhận diện loại của mỗi file PDF
        
        Args:
            pdf_files: Danh sách đường dẫn file PDF
            
        Returns:
            Dict {pdf_path: pdf_type} - VD: {"/path/to/file.pdf": "sgk"}
        """
        print(f"\n{'='*70}")
        print("\n🔍 NHẬN DIỆN LOẠI FILE PDF\n")
        print(f"{'='*70}\n")
        
        pdf_mapping = {}
        
        for pdf_path in pdf_files:
            filename = os.path.basename(pdf_path).lower()
            
            # Nhận diện dựa trên tên file
            if "sgk" in filename or "sach_giao_khoa" in filename or "giaokhoa" in filename:
                pdf_type = "sgk"
            elif "sbt" in filename or "sach_bai_tap" in filename or "baitap" in filename:
                pdf_type = "sbt"
            elif "sgv" in filename or "sach_giao_vien" in filename or "giaovien" in filename:
                pdf_type = "sgv"
            else:
                # Nếu không nhận diện được, gán mặc định theo thứ tự
                if not pdf_mapping:
                    pdf_type = "sgk"
                elif len(pdf_mapping) == 1:
                    pdf_type = "sbt"
                else:
                    pdf_type = "sgv"
            
            pdf_mapping[pdf_path] = pdf_type
            print(f"\n   ✓ {os.path.basename(pdf_path)} → {self.pdf_types[pdf_type]}\n")
        
        print()
        return pdf_mapping
    
    def scan_pdf_content(self, pdf_files: List[str]) -> Dict[str, str]:
        """
        Quét nội dung của từng file PDF
        
        Args:
            pdf_files: Danh sách đường dẫn file PDF
            
        Returns:
            Dict {pdf_type: content_summary}
        """
        print(f"\n{'='*70}")
        print("📖 QUÉT NỘI DUNG PDF")
        print(f"{'='*70}\n")
        
        pdf_mapping = self.identify_pdf_types(pdf_files)
        content_summaries = {}
        
        scan_prompt = """
# NHIỆM VỤ: PHÂN TÍCH NỘI DUNG PDF

Hãy phân tích file PDF này và trả về thông tin sau:

## 1. CHỦ ĐỀ CHÍNH
- Tên bài/chương
- Các chủ đề chính được đề cập
- Phạm vi kiến thức

## 2. CÁC KHÁI NIỆM QUAN TRỌNG
Liệt kê các khái niệm, thuật ngữ, định nghĩa quan trọng

## 3. KẾT CẤU NỘI DUNG
- Các phần/mục chính
- Số trang cho mỗi phần

## 4. LOẠI NỘI DUNG
- Lý thuyết
- Bài tập
- Ví dụ minh họa
- Hình ảnh/sơ đồ quan trọng

## YÊU CẦU:
- Trả về nội dung ngắn gọn, súc tích (500-800 từ)
- Tập trung vào kiến thức cốt lõi
- Không thêm lời mở đầu hay kết luận
"""
        
        for pdf_path, pdf_type in pdf_mapping.items():
            print(f"📄 Đang quét {self.pdf_types[pdf_type]}: {os.path.basename(pdf_path)}\n")
            
            try:
                content = self.client.send_data_to_AI(
                    prompt=scan_prompt,
                    file_paths=[pdf_path],
                    temperature=0.55
                )
                content_summaries[pdf_type] = content
                print(f"\n   ✓ Hoàn thành ({len(content)} ký tự)\n")
                print(f"   Preview: {content[:100]}...\n")
                
            except Exception as e:
                print(f"   ✗ Lỗi khi quét: {e}\n")
                content_summaries[pdf_type] = ""
        
        return content_summaries
    
    def generate_topic_guide(self, content_summaries: Dict[str, str]) -> str:
        """
        Tạo hướng dẫn chủ đề từ nội dung đã quét
        
        Args:
            content_summaries: Dict {pdf_type: content}
            
        Returns:
            Topic guide string để thêm vào prompt
        """
        print(f"\n{'='*70}")
        print("🎯 TẠO HƯỚNG DẪN CHỦ ĐỀ")
        print(f"{'='*70}\n")
        
        guide_parts = [
            "# PHẠM VI CHỦ ĐỀ VÀ KIẾN THỨC (TỪ PDF ĐÃ QUÉT)",
            "",
            "**LƯU Ý QUAN TRỌNG:**",
            "- Câu hỏi PHẢI bám sát nội dung các file PDF đã quét",
            "- KHÔNG được lệch chủ đề hoặc thêm kiến thức ngoài phạm vi bài học",
            "- Tập trung vào các khái niệm, định nghĩa đã được đề cập trong tài liệu",
            "- Sử dụng ngôn ngữ và thuật ngữ giống hệt trong sách nhưng không trích dẫn nguyên văn và không trích dẫn từ trong sách ra",
            ""
        ]
        
        # Thêm nội dung từ từng loại PDF
        for pdf_type in ["sgk", "sbt", "sgv"]:
            if pdf_type in content_summaries and content_summaries[pdf_type]:
                guide_parts.append(f"## NỘI DUNG TỪ {self.pdf_types[pdf_type].upper()}")
                guide_parts.append("")
                guide_parts.append(content_summaries[pdf_type])
                guide_parts.append("")
        
        guide_parts.extend([
            "## YÊU CẦU KHI SINH CÂU HỎI",
            "1. **Bám sát chủ đề:** Mọi câu hỏi phải dựa trên nội dung trên",
            "2. **Không lạc đề:** Tuyệt đối không sinh câu hỏi về chủ đề khác",
            "3. **Đa dạng nguồn:** Kết hợp kiến thức từ cả 3 loại tài liệu",
            "4. **Độ sâu phù hợp:** Phù hợp với mức độ trong tài liệu",
            ""
        ])
        
        topic_guide = "\n".join(guide_parts)
        
        print(f"✓ Đã tạo hướng dẫn chủ đề ({len(topic_guide)} ký tự)\n")
        return topic_guide
    
    def enhance_prompt_with_topic_guide(self, original_prompt: str, 
                                       pdf_files: List[str]) -> str:
        """
        Cải thiện prompt bằng cách thêm hướng dẫn chủ đề từ PDF
        
        Args:
            original_prompt: Prompt gốc
            pdf_files: Danh sách file PDF
            
        Returns:
            Enhanced prompt với topic guide
        """
        print(f"\n{'='*70}")
        print("🔧 CẢI THIỆN PROMPT VỚI HƯỚNG DẪN CHỦ ĐỀ")
        print(f"{'='*70}\n")
        
        # Quét nội dung PDF
        content_summaries = self.scan_pdf_content(pdf_files)
        
        # Tạo topic guide
        topic_guide = self.generate_topic_guide(content_summaries)
        
        # Chèn topic guide vào đầu prompt (sau phần LƯU Ý QUAN TRỌNG)
        lines = original_prompt.split("\n")
        
        # Tìm vị trí phù hợp để chèn (sau ## YÊU CẦU CHUNG hoặc ## VAI TRÒ)
        insert_index = 0
        for i, line in enumerate(lines):
            if "## YÊU CẦU CHUNG" in line or "## MỤC TIÊU" in line:
                insert_index = i
                break
        
        # Chèn topic guide
        enhanced_lines = (
            lines[:insert_index] + 
            ["", topic_guide, ""] + 
            lines[insert_index:]
        )
        
        enhanced_prompt = "\n".join(enhanced_lines)
        
        print(f"✓ Đã cải thiện prompt")
        print(f"   - Prompt gốc: {len(original_prompt)} ký tự")
        print(f"   - Prompt mới: {len(enhanced_prompt)} ký tự")
        print(f"   - Thêm: {len(enhanced_prompt) - len(original_prompt)} ký tự\n")
        
        return enhanced_prompt


class MissingQuestionFixer:
    """Class xử lý sinh lại câu hỏi bị thiếu
    CHÚ Ý: Các hàm generate phải nhận prompt đã replace subject/grade, không tự ý đọc lại từ file hoặc nhận biến gốc chưa qua replace!
    """
    def __init__(self, project_id: str, creds, model_name: str = "gemini-2.5-pro"):
        self.client = VertexClient(project_id, creds, model_name)
    
    def generate_missing_questions(self, missing_nums: List[int], 
                                   original_prompt: str,
                                   existing_text: str,
                                   question_type: str = "tracnghiem") -> str:
        """
        Sinh lại các câu hỏi bị thiếu. 
        original_prompt PHẢI là prompt đã thay thế subject/grade (không tự đọc lại file nguyên gốc!)
        """
        print(f"\n{'='*70}")
        print(f"🔄 SINH LẠI {len(missing_nums)} CÂU BỊ THIẾU")
        print(f"{'='*70}\n")
        
        if not missing_nums:
            return ""
        
        # Lấy nội dung câu hỏi hiện có để tham khảo
        existing_questions = self._extract_existing_questions(existing_text)
        
        # Tạo prompt sinh lại
        regenerate_prompt = self._create_regenerate_prompt(
            missing_nums,
            original_prompt,
            existing_questions,
            question_type
        )
        
        # Sinh câu hỏi mới
        try:
            print(f"📤 Gửi yêu cầu sinh {len(missing_nums)} câu...")
            new_questions = self.client.send_data_to_check(
                prompt=regenerate_prompt,
                temperature=0.75
            )
            print(f"✓ Đã nhận {len(new_questions)} ký tự\n")
            return new_questions
            
        except Exception as e:
            print(f"✗ Lỗi khi sinh câu: {e}\n")
            return ""
    
    def _extract_existing_questions(self, text: str) -> Dict[int, str]:
        """Trích xuất các câu hỏi hiện có"""
        questions = {}
        lines = text.split("\n")
        current_num = None
        current_lines = []
        
        for line in lines:
            match = re.match(r'^\*?\*?Câu\s+(\d+)', line, re.IGNORECASE)
            if match:
                if current_num and current_lines:
                    questions[current_num] = "\n".join(current_lines)
                current_num = int(match.group(1))
                current_lines = [line]
            elif current_num:
                current_lines.append(line)
        
        if current_num and current_lines:
            questions[current_num] = "\n".join(current_lines)
        
        return questions
    
    def _create_regenerate_prompt(self, missing_nums: List[int],
                                  original_prompt: str,
                                  existing_questions: Dict[int, str],
                                  question_type: str) -> str:
        """Tạo prompt để sinh lại câu hỏi"""
        
        prompt_parts = [
            "# YÊU CẦU SINH LẠI CÂU HỎI BỊ THIẾU",
            "",
            "## BỐI CẢNH",
            f"Bạn đang sinh đề thi {question_type}. Một số câu hỏi bị thiếu hoặc không đầy đủ.",
            "",
            "## CÁC CÂU CẦN SINH LẠI",
            f"Sinh chính xác {len(missing_nums)} câu sau: {', '.join(map(str, missing_nums[:20]))}",
            "" if len(missing_nums) <= 20 else f"... và {len(missing_nums)-20} câu khác",
            "",
            "## YÊU CẦU TUYỆT ĐỐI",
            "1. **Không trùng lặp:** Nội dung phải HOÀN TOÀN KHÁC với các câu đã có",
            "2. **Đúng số thứ tự:** Mỗi câu phải có đúng số thứ tự trong danh sách trên",
            "3. **Đầy đủ format:** Mỗi câu phải có: tiêu đề, nội dung, đáp án, lời giải, giải thích (ít nhất 2 dòng)",
            "4. **Không thêm gì khác:** Chỉ trả về nội dung câu hỏi, không lời mở đầu/kết",
            "",
            "## MỘT SỐ CÂU ĐÃ CÓ (ĐỂ TRÁNH TRÙNG LẶP)",
            ""
        ]
        
        # Thêm 3-5 câu mẫu để tránh trùng
        sample_questions = list(existing_questions.items())[:5]
        for num, content in sample_questions:
            preview = content.split("\n")[1:3]  # Lấy 2 dòng đầu
            prompt_parts.append(f"**Câu {num}:** {' '.join(preview)[:100]}...")
            prompt_parts.append("")
        
        prompt_parts.extend([
            "## HƯỚNG DẪN SINH CÂU GỐC",
            "```",
            original_prompt[:2000],  # Lấy 2000 ký tự đầu
            "```",
            "",
            "## BẮT ĐẦU SINH CÂU HỎI MỚI",
            f"Hãy sinh chính xác {len(missing_nums)} câu hỏi hoàn toàn mới, không trùng lặp:",
            ""
        ])
        
        return "\n".join(prompt_parts)


# ============ FUNCTIONS ĐỂ TÍCH HỢP VÀO response2docx.py ====================

def enhance_prompt_with_pdf_scan(prompt: str, pdf_files: List[str],
                                 project_id: str, creds) -> str:
    """
    Hàm tiện ích để thêm topic guide vào prompt
    
    Usage trong response2docx_improved():
        prompt = enhance_prompt_with_pdf_scan(prompt, file_paths, project_id, creds)
    """
    scanner = PDFScanner(project_id, creds)
    enhanced_prompt = scanner.enhance_prompt_with_topic_guide(prompt, pdf_files)
    return enhanced_prompt


def regenerate_missing_questions(missing_nums: List[int],
                                 original_prompt: str,
                                 existing_text: str,
                                 project_id: str,
                                 creds,
                                 question_type: str = "tracnghiem") -> str:
    """
    Hàm tiện ích để sinh lại câu hỏi thiếu
    
    Usage trong response2docx_improved():
        new_questions = regenerate_missing_questions(
            missing_nums, prompt, current_text, 
            project_id, creds, question_type
        )
    """
    fixer = MissingQuestionFixer(project_id, creds)
    new_questions = fixer.generate_missing_questions(
        missing_nums, original_prompt, existing_text, question_type
    )
    return new_questions
