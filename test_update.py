from update_checker import GithubUpdateChecker

checker = GitHubUpdateChecker("1.0.0", "HoangLinh03-code/ToolGen")

# Giả lập chạy update bằng file có sẵn
test_result = checker.install_update(r"D:\ToolGen\GenQues_new.exe")

print("Kết quả test:", test_result)