import sys
import os
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QFileDialog, QToolBar, 
                           QStatusBar, QVBoxLayout, QWidget, QScrollArea, QLabel)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QWheelEvent
import fitz  # PyMuPDF
import numpy as np
import cv2
import pyttsx3
from paddleocr import PaddleOCR
import threading
import io
from PIL import Image

from pdf_viewer import PDFViewer

# ==================== TTS Worker ====================
# 使用 QThread 处理耗时任务，避免 UI 冻结
class TTSWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, text):
        super().__init__()
        self.text = text
        self.engine = pyttsx3.init()
        self.stop_requested = False
        self.idle_count = 0  # 添加空闲检测计数器

    def run(self):
        try:
            self.engine.say(self.text)
            # 使用 non-blocking loop 允许中断
            self.engine.startLoop(False)
            while True: # 使用更明确的循环
                if self.stop_requested:
                    print("TTSWorker: 收到停止请求，尝试结束循环。")
                    # 尝试停止引擎并结束循环
                    if self.engine:
                        self.engine.stop() # 尝试立即停止发声
                    break # 退出循环

                self.engine.iterate() # 处理事件

                # 改进的完成状态检测
                if not self.engine.isBusy():
                    self.idle_count += 1
                    print(f"TTSWorker: 引擎空闲检测 ({self.idle_count}/3)")
                    # 连续3次检测到空闲状态才认为真正完成
                    if self.idle_count >= 3:
                        print("TTSWorker: 检测到引擎不再繁忙，结束循环。")
                        break
                else:
                    self.idle_count = 0  # 如果又变忙，重置计数器

                QThread.msleep(100) # 稍微增加休眠时间

        except Exception as e:
            self.error.emit(f"TTS 错误: {e}")
        finally:
            # 确保引擎停止
            try:
                self.engine.stop()
                if hasattr(self.engine, 'endLoop') and callable(self.engine.endLoop):
                    self.engine.endLoop()
            except Exception as e:
                print(f"尝试结束TTS引擎时出错: {e}")
            
            print("TTSWorker: run 方法结束，发送 finished 信号。")
            self.finished.emit()

    def stop(self):
        print("TTSWorker: stop() 方法被调用。")
        self.stop_requested = True
        # 尝试停止引擎 (可能不是立即生效)
        if self.engine:
           self.engine.stop()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()  # 首先初始化 UI，包括创建 statusBar
        self.current_file = None
        self.tts_worker = None
        self.config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        
        # 初始化 OCR (首次运行时会自动下载模型)
        # 指定使用中文识别模型，启用角度分类
        try:
            self.ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False) 
            self.statusBar.showMessage("OCR引擎加载成功")
        except Exception as e:
            self.ocr = None
            self.statusBar.showMessage(f"加载OCR引擎失败: {e}")
            print(f"错误：无法加载 PaddleOCR: {e}") # 添加打印方便调试

        # 加载上次的文件和页码
        self.load_last_session()
        
    def initUI(self):
        self.setWindowTitle("PDF阅读器")
        self.setGeometry(100, 100, 800, 600)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建PDF查看区域
        self.pdf_viewer = PDFViewer()
        layout.addWidget(self.pdf_viewer)
        
        # 创建工具栏
        self.create_toolbar()
        
        # 创建状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("就绪")
        
        # 连接页面变更信号
        self.pdf_viewer.page_changed.connect(self.update_status_bar)
        
        # 添加键盘快捷键
        self.setup_shortcuts()
        
    def setup_shortcuts(self):
        """设置键盘快捷键"""
        # 打开文件 - Ctrl+O
        open_shortcut = QKeySequence(QKeySequence.StandardKey.Open)
        open_action = QAction("打开文件", self)
        open_action.setShortcut(open_shortcut)
        open_action.triggered.connect(self.open_file)
        self.addAction(open_action)
        
        # 下一页 - 右箭头, PgDown
        next_page_shortcut1 = QKeySequence(Qt.Key.Key_Right)
        next_page_action1 = QAction("下一页", self)
        next_page_action1.setShortcut(next_page_shortcut1)
        next_page_action1.triggered.connect(self.pdf_viewer.next_page)
        self.addAction(next_page_action1)
        
        next_page_shortcut2 = QKeySequence(Qt.Key.Key_PageDown)
        next_page_action2 = QAction("下一页", self)
        next_page_action2.setShortcut(next_page_shortcut2)
        next_page_action2.triggered.connect(self.pdf_viewer.next_page)
        self.addAction(next_page_action2)
        
        # 上一页 - 左箭头, PgUp
        prev_page_shortcut1 = QKeySequence(Qt.Key.Key_Left)
        prev_page_action1 = QAction("上一页", self)
        prev_page_action1.setShortcut(prev_page_shortcut1)
        prev_page_action1.triggered.connect(self.pdf_viewer.prev_page)
        self.addAction(prev_page_action1)
        
        prev_page_shortcut2 = QKeySequence(Qt.Key.Key_PageUp)
        prev_page_action2 = QAction("上一页", self)
        prev_page_action2.setShortcut(prev_page_shortcut2)
        prev_page_action2.triggered.connect(self.pdf_viewer.prev_page)
        self.addAction(prev_page_action2)
        
        # 放大 - Ctrl+=
        zoom_in_shortcut = QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Equal)
        zoom_in_action = QAction("放大", self)
        zoom_in_action.setShortcut(zoom_in_shortcut)
        zoom_in_action.triggered.connect(self.pdf_viewer.zoom_in)
        self.addAction(zoom_in_action)
        
        # 缩小 - Ctrl+-
        zoom_out_shortcut = QKeySequence(QKeySequence.StandardKey.ZoomOut)
        zoom_out_action = QAction("缩小", self)
        zoom_out_action.setShortcut(zoom_out_shortcut)
        zoom_out_action.triggered.connect(self.pdf_viewer.zoom_out)
        self.addAction(zoom_out_action)
        
        # 鼠标滚轮快捷键
        # Ctrl+滚轮上 - 上一页
        # Ctrl+滚轮下 - 下一页
        # 这些快捷键在 PDFViewer 的 wheelEvent 中处理
        
        # 添加 OCR 和停止快捷键 (可选)
        ocr_shortcut = QKeySequence("Ctrl+R")
        ocr_action = QAction("识别并朗读", self)
        ocr_action.setShortcut(ocr_shortcut)
        ocr_action.triggered.connect(self.start_ocr_and_read)
        self.addAction(ocr_action)

        stop_tts_shortcut = QKeySequence("Ctrl+T")
        stop_tts_action = QAction("停止朗读", self)
        stop_tts_action.setShortcut(stop_tts_shortcut)
        stop_tts_action.triggered.connect(self.stop_reading)
        self.addAction(stop_tts_action)
        
    def create_toolbar(self):
        toolbar = QToolBar("主工具栏")
        self.addToolBar(toolbar)
        
        # 打开文件
        open_action = QAction("打开", self)
        open_action.setStatusTip("打开PDF文件")
        open_action.triggered.connect(self.open_file)
        toolbar.addAction(open_action)
        
        # 上一页
        prev_action = QAction("上一页", self)
        prev_action.setStatusTip("查看上一页 (左箭头, PgUp 或 Ctrl+滚轮上)")
        prev_action.triggered.connect(self.pdf_viewer.prev_page)
        toolbar.addAction(prev_action)
        
        # 下一页
        next_action = QAction("下一页", self)
        next_action.setStatusTip("查看下一页 (右箭头, PgDown 或 Ctrl+滚轮下)")
        next_action.triggered.connect(self.pdf_viewer.next_page)
        toolbar.addAction(next_action)
        
        # 放大
        zoom_in_action = QAction("放大", self)
        zoom_in_action.setStatusTip("放大视图 (Ctrl+=)")
        zoom_in_action.triggered.connect(self.pdf_viewer.zoom_in)
        toolbar.addAction(zoom_in_action)
        
        # 缩小
        zoom_out_action = QAction("缩小", self)
        zoom_out_action.setStatusTip("缩小视图 (Ctrl+-)")
        zoom_out_action.triggered.connect(self.pdf_viewer.zoom_out)
        toolbar.addAction(zoom_out_action)
        
        toolbar.addSeparator()

        # OCR & Read
        ocr_action = QAction("识别并朗读", self)
        ocr_action.setStatusTip("识别当前页面文字并朗读")
        ocr_action.triggered.connect(self.start_ocr_and_read)
        toolbar.addAction(ocr_action)

        # Stop Reading
        stop_action = QAction("停止朗读", self)
        stop_action.setStatusTip("停止当前朗读")
        stop_action.triggered.connect(self.stop_reading)
        toolbar.addAction(stop_action)
        
    def open_file(self, file_path=None, page_num=0):
        if not file_path:
            # 在PyQt6中，不再使用QFileDialog.Options()
            file_path, _ = QFileDialog.getOpenFileName(
                self, "打开PDF文件", "", "PDF文件 (*.pdf)"
            )
        
        if file_path:
            self.current_file = file_path
            self.statusBar.showMessage(f"已打开: {file_path}")
            self.pdf_viewer.load_pdf(file_path)
            if page_num > 0 and page_num < self.pdf_viewer.page_count:
                self.pdf_viewer.go_to_page(page_num)
            self.setWindowTitle(f"PDF阅读器 - {os.path.basename(file_path)}")
            self.update_status_bar()
            # 文件打开时，确保停止之前的朗读 (如果存在)
            self.stop_reading()
            
    def update_status_bar(self):
        """更新状态栏信息"""
        if self.pdf_viewer.pdf_document:
            page_info = self.pdf_viewer.page_info
            self.statusBar.showMessage(page_info)

    def start_ocr_and_read(self):
        """启动 OCR 识别和 TTS 朗读 """
        if not self.current_file:
            self.statusBar.showMessage("请先打开一个PDF文件")
            return
        if not self.ocr:
            self.statusBar.showMessage("OCR引擎未成功加载，无法识别")
            return
        if self.tts_worker and self.tts_worker.isRunning():
             self.statusBar.showMessage("正在朗读中，请先停止")
             return # 或者先停止再开始？目前设计为不允许重叠

        self.statusBar.showMessage("正在识别当前页面...")
        QApplication.processEvents() # 刷新UI显示状态

        # 1. 获取当前页面图像 (假设 pdf_viewer 有此方法)
        try:
            # 增加DPI以提高识别精度
            image_bytes = self.pdf_viewer.get_current_page_image_bytes(dpi=200) 
            if not image_bytes:
                self.statusBar.showMessage("无法获取当前页面图像")
                return
            
            # 将字节流转换为 OpenCV 格式 (NumPy array)
            pil_image = Image.open(io.BytesIO(image_bytes))
            # PaddleOCR 需要 BGR 格式
            img_np = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR) 

        except AttributeError:
             self.statusBar.showMessage("错误: PDFViewer缺少 get_current_page_image_bytes 方法")
             print("错误: PDFViewer缺少 get_current_page_image_bytes 方法")
             return
        except Exception as e:
             self.statusBar.showMessage(f"获取或处理图像时出错: {e}")
             print(f"获取或处理图像时出错: {e}")
             return

        # 2. 在后台线程运行 OCR (更耗时)
        # 使用标准 threading，因为 PaddleOCR 可能与 QThread 有兼容问题
        self.ocr_thread = threading.Thread(target=self._run_ocr, args=(img_np,))
        self.ocr_thread.start()


    def _run_ocr(self, img_np):
        """在单独线程中执行 OCR """
        try:
            result = self.ocr.ocr(img_np, cls=True)
            if result and result[0]: # PaddleOCR 返回 [[lines...]] 格式
                # 提取识别结果中的文本内容
                texts = [line[1][0] for line in result[0] if line and len(line) >= 2]
                
                # 首先连接所有文本行，使用实际的换行符
                full_text = "\n".join(texts) 
                
                # 然后替换显式的换行符字符串 "\n"（这可能是OCR错误识别的结果）
                full_text = full_text.replace("\\n", "")
                
                # 使用适当的标点符号替换实际的换行符，以便朗读时有停顿
                # 如果文本已经有标点符号，则不需要添加
                full_text = full_text.replace("\n", "").replace(",,", ",").replace(", ,", ",")
                
                # 打印部分识别结果以供调试，限制长度避免过多输出
                print(f"识别结果 (前200字符):\n{full_text[:200]}...") 
                
                if full_text:
                    # OCR 完成后，切换回主线程启动 TTS Worker
                    # 使用 QMetaObject.invokeMethod 或 signal/slot 保证线程安全
                    # 这里简化处理：直接在主线程消息循环中调用后续方法似乎也可以，
                    # 但更健壮的方式是发信号。为简单起见，先直接调用。
                    # 注意：statusBar 更新需要在主线程完成
                    self.statusBar.showMessage("识别完成，准备朗读...")
                    self._start_tts(full_text) # 调用在主线程创建TTS Worker的方法
                else:
                    self.statusBar.showMessage("未识别到文字")
            else:
                self.statusBar.showMessage("未识别到文字")

        except Exception as e:
            # 确保错误信息能正确显示，处理潜在的 f-string 问题
            try:
                error_msg = f"OCR 识别失败: {str(e)}" 
            except Exception:
                error_msg = "OCR 识别失败: 发生未知错误"
            self.statusBar.showMessage(error_msg)
            print(error_msg) # 在控制台打印详细错误

    def _start_tts(self, text):
         """在主线程中创建并启动 TTS QThread Worker"""
         # 检查并停止之前的朗读任务
         if self.tts_worker and self.tts_worker.isRunning():
             print("检测到正在运行的 TTS worker，先停止...")
             self.tts_worker.stop() # 请求停止
             self.tts_worker.wait(2000) # 等待最多2秒结束
             if self.tts_worker.isRunning():
                 print("警告：旧的 TTS worker 未能在超时内停止。")
             # self.tts_worker = None # 在 finished 或 error 信号中处理

         print(f"准备朗读文本 (前100字符): {text[:100]}...")
         self.tts_worker = TTSWorker(text)
         # 连接信号和槽
         self.tts_worker.finished.connect(self.on_tts_finished)
         self.tts_worker.error.connect(self.on_tts_error)
         # 启动线程
         self.tts_worker.start()
         self.statusBar.showMessage("正在朗读...")

    def stop_reading(self):
        """停止 TTS 朗读"""
        if self.tts_worker and self.tts_worker.isRunning():
            self.statusBar.showMessage("正在停止朗读...")
            print("请求停止 TTS worker...")
            self.tts_worker.stop()
            # 让 on_tts_finished 信号处理状态消息更新
        else:
            # 如果没有活动的 worker，也清空状态栏消息或设为默认
            # self.statusBar.showMessage("当前没有在朗读") 
            pass # 或者保持当前状态栏消息

    def on_tts_finished(self):
        """TTS Worker 完成时的槽函数"""
        print("TTS worker finished signal received.")
        # 检查 worker 是否仍然存在且是我们期望的那个
        sender_worker = self.sender() 
        if sender_worker == self.tts_worker:
             if self.tts_worker.stop_requested:
                  print("朗读被用户停止。")
                  self.statusBar.showMessage("朗读已停止")
             else:
                  print("朗读正常完成。")
                  self.statusBar.showMessage("朗读完毕")
             self.tts_worker = None # 清理 worker 引用
        else:
             print("警告: 收到了一个未知或过时 TTS worker 的 finished 信号。")


    def on_tts_error(self, error_message):
        """TTS Worker 发生错误时的槽函数"""
        print(f"TTS worker error signal received: {error_message}")
        sender_worker = self.sender()
        if sender_worker == self.tts_worker:
             self.statusBar.showMessage(f"朗读错误: {error_message}")
             self.tts_worker = None # 清理 worker 引用
        else:
             print("警告: 收到了一个未知或过时 TTS worker 的 error 信号。")

    def save_session(self):
        """保存当前会话信息到配置文件"""
        if not self.current_file:
            return
            
        session_data = {
            "last_file": self.current_file,
            "last_page": self.pdf_viewer.current_page_num
        }
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f)
            print(f"会话信息已保存: {session_data}")
        except Exception as e:
            print(f"保存会话信息时出错: {e}")
    
    def load_last_session(self):
        """加载上次会话信息并打开文件"""
        if not os.path.exists(self.config_file):
            return
            
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
                
            last_file = session_data.get("last_file")
            last_page = session_data.get("last_page", 0)
            
            if last_file and os.path.exists(last_file):
                print(f"正在打开上次的文件: {last_file}, 页码: {last_page}")
                self.open_file(last_file, last_page)
        except Exception as e:
            print(f"加载上次会话信息时出错: {e}")

    def closeEvent(self, event):
        """关闭窗口时确保停止 TTS 并保存会话信息"""
        print("主窗口关闭事件触发...")
        # 保存当前会话信息
        self.save_session()
        
        self.stop_reading() 
        # 等待TTS线程结束，设置超时
        if self.tts_worker:
             print("等待 TTS worker 结束...")
             if not self.tts_worker.wait(1000): # 等待1秒
                 print("警告: TTS worker 未能在关闭时正常结束。")
        
        print("继续关闭窗口...")
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
