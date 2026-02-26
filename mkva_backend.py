import json
import subprocess
import threading
import webview
import os
import sys
from pathlib import Path


class ProApi:
    def __init__(self):
        self.window = None
        self.mkvtoolnix_path = r"C:\Program Files\MKVToolNix\mkvpropedit.exe"

    def set_window(self, window):
        self._window = window

    def _log(self, message):
        """线程安全地向前端发送日志"""
        if self._window:
            msg = message.replace("'", "\\'").replace("\n", "\\n")
            self._window.evaluate_js(f"addLog('{msg}')")

    def _update_progress(self, current, total):
        """更新前端进度条"""
        if self._window:
            self._window.evaluate_js(f"updateProgress({current}, {total})")

    # --- 文件/目录选择 ---
    def select_exe(self):
        files = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=['Executable (*.exe)'])
        return files[0] if files else None

    def select_mkv_files(self):
        files = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True,
                                               file_types=['MKV Files (*.mkv)'])
        return files if files else []

    def select_mkv_folder(self):
        folder = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not folder: return []

        folder_path = folder[0]
        mkv_list = []
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(".mkv"):
                    mkv_list.append(os.path.join(root, file))
        self._log(f"从目录中扫描到 {len(mkv_list)} 个 MKV 文件")
        return mkv_list

    def select_attachments(self):
        files = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True)
        if not files: return []

        valid_paths = []
        for f in files:
            if os.path.getsize(f) >= 2 * 1024 ** 3:
                self._log(f"跳过附件 {os.path.basename(f)}: 超过 2GB 限制")
                continue
            valid_paths.append(f)
        return valid_paths

    # --- 核心逻辑 ---
    def run_add_task(self, exe_path, mkv_list, att_list):
        threading.Thread(target=self._proc_add, args=(exe_path, mkv_list, att_list), daemon=True).start()

    def _proc_add(self, exe, mkvs, atts):
        self._log("=" * 30 + "\n开始批量添加附件...")
        success = 0
        total = len(mkvs)

        for i, mkv in enumerate(mkvs):
            name = os.path.basename(mkv)
            self._log(f"正在处理: {name}")
            cmd = [exe, mkv]
            for a in atts:
                cmd.extend(["--add-attachment", a])

            if self._execute_cmd(cmd):
                success += 1
                self._log(f"  ✅ 成功")
            else:
                self._log(f"  ❌ 失败")
            self._update_progress(i + 1, total)

        self._log(f"任务结束！成功: {success}/{total}")
        self._update_progress(0, 0)

    def run_remove_task(self, exe_path, mkv_list, keyword):
        threading.Thread(target=self._proc_remove, args=(exe_path, mkv_list, keyword), daemon=True).start()

    def _proc_remove(self, exe, mkvs, keyword):
        mkvmerge = os.path.join(os.path.dirname(exe), "mkvmerge.exe")
        self._log("=" * 30 + f"\n开始移除关键词 '{keyword}' 的附件...")
        success = 0
        total = len(mkvs)

        for i, mkv in enumerate(mkvs):
            try:
                # 1. 获取 ID
                res = subprocess.run([mkvmerge, "-J", mkv], capture_output=True, text=True, encoding='utf-8')
                data = json.loads(res.stdout)
                ids = [str(a['id']) for a in data.get('attachments', []) if keyword in a.get('file_name', '')]

                if not ids:
                    self._log(f"跳过: {os.path.basename(mkv)} (未匹配)")
                else:
                    cmd = [exe, mkv]
                    for aid in ids: cmd.extend(["--delete-attachment", aid])
                    if self._execute_cmd(cmd):
                        success += 1
                        self._log(f"已清理: {os.path.basename(mkv)}")
            except Exception as e:
                self._log(f"错误 {os.path.basename(mkv)}: {e}")
            self._update_progress(i + 1, total)

        self._log(f"移除任务完成！修改文件: {success}/{total}")
        self._update_progress(0, 0)

    def _execute_cmd(self, cmd):
        try:
            si = None
            if os.name == 'nt':
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            r = subprocess.run(cmd, capture_output=True, startupinfo=si)
            return r.returncode == 0
        except:
            return False


if __name__ == "__main__":
    api = ProApi()
    # 获取当前脚本所在的绝对路径
    if getattr(sys, 'frozen', False):
        # 如果是打包后的 exe
        base_dir = os.path.dirname(sys.executable)
    else:
        # 如果是直接运行的 py 脚本
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # 拼接 HTML 文件的完整路径
    html_path = os.path.join(base_dir, "mkv_attacher_web.html")

    # 检查文件是否存在，防止路径错误
    if not os.path.exists(html_path):
        print(f"错误：找不到文件 {html_path}")
        # 可以弹出一个简单的提示框
        sys.exit(1)

    # 创建窗口
    window = webview.create_window(
        "MKV 附件增强版",
        url=html_path,  # 使用绝对路径
        js_api=api,
        width=1000,
        height=800
    )
    # 设置 API
    api.set_window(window)
    #webview.start(debug=True)  # 开启调试以便排查点击无反应
    webview.start()