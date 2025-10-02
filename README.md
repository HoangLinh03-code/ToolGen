# GenQues - Công cụ tạo câu hỏi và xử lý hình ảnh

generative Question là một dự án Python dùng để:
- Sinh câu hỏi trắc nghiệm và câu hỏi đúng sai ở tất cả các môn học ở tất cả cấp độ.
- Lưu câu hỏi đã gen sang file `.docx`.
- Sinh hình ảnh từ văn bản bằng Google Generative AI dùng imagen 3.

---

## Yêu cầu hệ thống

- Python >= 3.10
- Virtual environment (khuyến nghị)
- Kết nối Internet để gọi API Google Generative AI

---

## Cài đặt

1. Clone dự án:

```bash
git clone https://github.com/HoangLinh03-code/ToolGen/
cd ToolGen
```

2. Tạo mô trường ảo
- Windows:
```bash
python -m venv env
```
- Với linux có thể sẽ khác, nên sử dụng python3 khi dùng linux
- Với windows user:
```bash
env\Scripts\activate.bat
```
- Với linux user:
```bash
source env/bin/activate
```
3. Tải thư viện
```bash
pip install -r requirement.txt
```
4. Chạy chương trình
```bash
python GenQues.py
```
