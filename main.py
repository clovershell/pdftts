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

global was_stopped
was_stopped = False

# ==================== TTS Worker ====================
# 使用 QThread 处理耗时任务，避免 UI 冻结
class TTSWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    text_segment_started = pyqtSignal(int)  # 新增：开始朗读某个文字段的信号，参数为段落索引
    text_segment_finished = pyqtSignal(int)  # 新增：完成朗读某个文字段的信号，参数为段落索引
    request_speak = pyqtSignal(str, int)  # 新增：请求主线程朗读文字的信号
    
    def __init__(self, text_segments, ocr_boxes):
        super().__init__()
        self.text_segments = text_segments  # 文字段列表
        self.ocr_boxes = ocr_boxes  # 对应的文字框位置信息列表
        self.stop_requested = False
        self.current_segment_index = 0
        self.segment_completed = False

    def run(self):
        try:
            print(f"TTSWorker开始：准备朗读 {len(self.text_segments)} 个文字段")
            
            for i in range(len(self.text_segments)):
                if self.stop_requested:
                    print(f"TTSWorker: 收到停止请求 (在循环顶部)，退出朗读循环. 段落索引: {i}")
                    break
                self.current_segment_index = i
                current_text = self.text_segments[i]
                if was_stopped:
                    self.text_segment_started.emit(i - 1 if i > 0 else 0)
                else:   
                    self.text_segment_started.emit(i)
                self.segment_completed = False
                self.request_speak.emit(current_text, i)
                
                timeout_counter = 0
                max_timeout_counts = 300
                while not self.segment_completed and not self.stop_requested and timeout_counter < max_timeout_counts:
                    QThread.msleep(100)
                    timeout_counter += 1
                    if timeout_counter % 50 == 0:
                        print(f"TTSWorker: 段落 {i + 1} - 等待朗读响应... (已等待 {timeout_counter/10:.1f}秒), seg_ok={self.segment_completed}, stop_req={self.stop_requested}")
                
                if self.stop_requested:
                    print(f"TTSWorker: 段落 {i + 1} 朗读被停止 (在等待后检测到).")
                    break
                if timeout_counter >= max_timeout_counts and not self.segment_completed:
                    print(f"TTSWorker: 朗读段落 {i + 1} 超时")
                    self.error.emit(f"朗读段落 {i + 1} 超时")
                    break
                if not self.segment_completed:
                    print(f"TTSWorker: 警告 - 段落 {i + 1} 等待结束，但 segment_completed 仍然为 False 且未停止/超时。")

                self.text_segment_finished.emit(i)
                if i < len(self.text_segments) - 1 and not self.stop_requested:
                    QThread.msleep(100)
            
            if self.stop_requested:
                print("TTSWorker: 循环因 stop_requested 而终止.")
            else:
                print("TTSWorker: 所有段落处理完成 (循环正常结束).")
        except Exception as e:
            print(f"TTSWorker: run 方法发生异常: {e}")
            self.error.emit(f"TTS 错误: {e}")
        finally:
            print(f"TTSWorker: run 方法结束 (finally块), stop_requested={self.stop_requested}. 发送 finished 信号。")
            self.finished.emit()

    def on_segment_complete(self):
        """主线程通知段落朗读完成"""
        self.segment_completed = True

    def stop(self):
        print("TTSWorker: stop() 方法被调用。")
        self.stop_requested = True
        global was_stopped
        was_stopped = True


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()  # 首先初始化 UI，包括创建 statusBar
        self.current_file = None
        self.tts_worker = None
        self.is_stopping = False  # 新增：停止标志，避免竞态条件
        self.config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        self.session_history = {} # 用于存储 {file_path: page_num}
        self.last_opened_file = None # 记录最后一个打开的文件路径

        # 初始化 TTS 引擎（在主线程中）
        self._init_tts_engine()

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

        # 添加F9作为识别并朗读的额外快捷键
        ocr_f9_shortcut = QKeySequence(Qt.Key.Key_F9)
        ocr_f9_action = QAction("识别并朗读(F9)", self)
        ocr_f9_action.setShortcut(ocr_f9_shortcut)
        ocr_f9_action.triggered.connect(self.start_ocr_and_read)
        self.addAction(ocr_f9_action)

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
        prev_action.setStatusTip("查看上一页 (左箭头, PgUp)")
        prev_action.triggered.connect(self.pdf_viewer.prev_page)
        toolbar.addAction(prev_action)
        
        # 下一页
        next_action = QAction("下一页", self)
        next_action.setStatusTip("查看下一页 (右箭头, PgDown)")
        next_action.triggered.connect(self.pdf_viewer.next_page)
        toolbar.addAction(next_action)
        
        # 放大
        zoom_in_action = QAction("放大", self)
        zoom_in_action.setStatusTip("放大视图 (Ctrl+=, Ctrl+滚轮上)")
        zoom_in_action.triggered.connect(self.pdf_viewer.zoom_in)
        toolbar.addAction(zoom_in_action)
        
        # 缩小
        zoom_out_action = QAction("缩小", self)
        zoom_out_action.setStatusTip("缩小视图 (Ctrl+- , Ctrl+滚轮下)")
        zoom_out_action.triggered.connect(self.pdf_viewer.zoom_out)
        toolbar.addAction(zoom_out_action)
        
        toolbar.addSeparator()

        # OCR & Read
        ocr_action = QAction("识别并朗读", self)
        ocr_action.setStatusTip("识别当前页面文字并朗读 (F9或Ctrl+R)")
        ocr_action.triggered.connect(self.start_ocr_and_read)
        toolbar.addAction(ocr_action)

        # Stop Reading
        stop_action = QAction("停止朗读", self)
        stop_action.setStatusTip("停止当前朗读")
        stop_action.triggered.connect(self.stop_reading)
        toolbar.addAction(stop_action)
        
        # Clear Highlights
        clear_highlights_action = QAction("清除高亮", self)
        clear_highlights_action.setStatusTip("清除页面上的所有高亮标记")
        clear_highlights_action.triggered.connect(self.clear_highlights)
        toolbar.addAction(clear_highlights_action)
        
    def open_file(self, file_path=None, page_num=0):
        # 在打开新文件之前，如果当前有文件打开，保存其状态
        if self.current_file and self.pdf_viewer.pdf_document:
            current_page = self.pdf_viewer.current_page_num
            self.session_history[self.current_file] = current_page
            print(f"已保存文件 {os.path.basename(self.current_file)} 的状态到历史记录: 页码 {current_page}")
            # 考虑在这里调用 self.save_session() 以便立即持久化，
            # 但通常在关闭或明确保存操作时持久化更好，以避免频繁IO。
            # 目前的逻辑是在 closeEvent 中保存，这意味着切换文件时的页码只在内存中，直到程序关闭。
            # 如果希望切换文件时也立即保存到json，可以在这里取消注释下面这行：
            # self.save_session() 

        # 如果没有提供 file_path (例如通过工具栏按钮触发)，则弹出文件对话框
        if not file_path:
            file_path_candidate, _ = QFileDialog.getOpenFileName(
                self, "打开PDF文件", "", "PDF文件 (*.pdf)"
            )
            if not file_path_candidate: # 用户取消了对话框
                return
            file_path = file_path_candidate
        
        if file_path and os.path.exists(file_path):
            # 停止之前的朗读 (如果存在)
            self.stop_reading()

            self.current_file = file_path
            self.last_opened_file = file_path # 更新最后一个打开的文件
            self.statusBar.showMessage(f"正在打开: {file_path}")
            self.pdf_viewer.load_pdf(file_path)
            self.setWindowTitle(f"PDF阅读器 - {os.path.basename(file_path)}")

            # 确定要跳转到的页码
            # 如果 page_num > 0 (通常由 load_last_session 传入)，则优先使用它
            page_to_open = page_num 
            if page_to_open <= 0: # 如果 page_num 未指定或为0，尝试从历史记录加载
                page_to_open = self.session_history.get(file_path, 0)
            
            if page_to_open > 0 and page_to_open < self.pdf_viewer.page_count:
                self.pdf_viewer.go_to_page(page_to_open)
                print(f"已跳转到文件 {os.path.basename(file_path)} 的页码: {page_to_open}")
            else:
                self.pdf_viewer.go_to_page(0) # 默认打开第一页

            self.update_status_bar()
            
            # 可以在此处也调用一次 save_session，以确保新打开的文件及其初始页码（或历史页码）被记录
            # self.save_session() 
        elif file_path: # file_path 提供了但文件不存在
            self.statusBar.showMessage(f"错误: 文件 {file_path} 不存在。")
            print(f"错误: 文件 {file_path} 不存在。")
            # 如果尝试打开的文件不存在，从历史记录中移除（如果存在）
            if file_path in self.session_history:
                del self.session_history[file_path]
                print(f"已从历史记录中移除无效文件: {file_path}")
            if self.last_opened_file == file_path:
                self.last_opened_file = None # 如果是最后一个打开的文件，也清除
            # self.save_session() # 可以选择保存这个移除操作

    def update_status_bar(self):
        """更新状态栏信息"""
        if self.pdf_viewer.pdf_document:
            page_info = self.pdf_viewer.page_info
            self.statusBar.showMessage(page_info)

    def start_ocr_and_read(self):
        """启动 OCR 识别和 TTS 朗读 """
        print(f"开始OCR识别和朗读，当前状态: is_stopping={self.is_stopping}, worker存在={self.tts_worker is not None}")
        self.pdf_viewer.clear_highlights() # 在开始新的一轮OCR前也清除一次
        
        if not self.current_file:
            self.statusBar.showMessage("请先打开一个PDF文件")
            return
        if not self.ocr:
            self.statusBar.showMessage("OCR引擎未成功加载，无法识别")
            return
        if self.tts_worker and self.tts_worker.isRunning():
             self.statusBar.showMessage("检测到正在朗读，先停止当前朗读...")
             self.stop_reading()
             # 短暂等待确保TTS真正停止
             if self.tts_worker and self.tts_worker.isRunning():
                 self.tts_worker.wait(1000)  # 最多等待1秒

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
            self.ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False) 
            result = self.ocr.ocr(img_np, cls=True)
            if result and result[0]: # PaddleOCR 返回 [[lines...]] 格式
                # 提取识别结果中的文本内容和位置信息
                text_data = []  # 存储 (box_coords, text_content, confidence, y_center) 的元组
                
                for line in result[0]:
                    if line and len(line) >= 2:
                        # line[0] 是文字框的四个角点坐标
                        # line[1] 是 (文字内容, 置信度)
                        box_coords = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                        text_content = line[1][0]
                        confidence = line[1][1]
                        
                        # 只保留置信度较高的结果
                        if confidence > 0.5:
                            # 计算文字框的中心Y坐标用于排序
                            y_coords = [point[1] for point in box_coords]
                            y_center = sum(y_coords) / len(y_coords)
                            # 计算文字框的中心X坐标用于同行内排序
                            x_coords = [point[0] for point in box_coords]
                            x_center = sum(x_coords) / len(x_coords)
                            
                            text_data.append((box_coords, text_content, confidence, y_center, x_center))
                
                # 按照阅读顺序排序：先按Y坐标（从上到下），再按X坐标（从左到右）
                # 对于Y坐标相近的文字（可能在同一行），按X坐标排序
                def sort_key(item):
                    y_center = item[3]
                    x_center = item[4]
                    # 将Y坐标量化到行，相近的Y坐标归为同一行
                    row = int(y_center // 20)  # 假设行高约20像素
                    return (row, x_center)
                
                text_data.sort(key=sort_key)
                
                # 过滤空或仅含空格的文本段
                filtered_text_segments = []
                filtered_ocr_boxes = []
                for box_coords, text_content, confidence, _, _ in text_data:
                    if text_content and text_content.strip(): # 确保文本非空且去除首尾空格后非空
                        filtered_text_segments.append(text_content)
                        filtered_ocr_boxes.append(box_coords)
                    else:
                        # 可选：打印被过滤掉的文本段信息，用于调试
                        print(f"OCR: Filtered out empty/whitespace segment: '{text_content}'")
                
                # 更新MainWindow的当前文本和框数据为过滤后的结果
                self.current_ocr_boxes = filtered_ocr_boxes
                self.current_text_segments = filtered_text_segments
                
                # 打印部分识别结果以供调试
                if filtered_text_segments:
                    print(f"识别到 {len(filtered_text_segments)} 个有效文字块 (已过滤空值)")
                    # 以下是可选的更详细的打印，如果需要可以取消注释
                    # print(f"所有有效文字段:")
                    # for i, segment in enumerate(filtered_text_segments):
                    #     print(f"  [{i+1}] {segment}")
                    # full_text = " ".join(filtered_text_segments)
                    # print(f"合并文本 (前200字符):\n{full_text[:200]}...") 
                
                if filtered_text_segments: # 使用过滤后的数据启动TTS
                    self.statusBar.showMessage("识别完成，准备朗读...")
                    self._start_tts_with_segments(filtered_text_segments, filtered_ocr_boxes)
                else:
                    self.statusBar.showMessage("未识别到有效文字 (所有识别结果均为空或空格)")
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

    def _start_tts_with_segments(self, text_segments, ocr_boxes):
        """在主线程中创建并启动分段 TTS QThread Worker"""
        print(f"MainWindow: _start_tts_with_segments - 准备朗读 {len(text_segments)} 个文字段...")
        # 重置停止标志
        self.is_stopping = False
        
        # 确保TTS引擎可用并处于正确状态
        print("MainWindow: _start_tts_with_segments - 调用 _ensure_tts_engine_ready() 检查引擎...")
        if not self._ensure_tts_engine_ready():
            self.statusBar.showMessage("TTS引擎初始化失败，无法朗读")
            print("MainWindow: _start_tts_with_segments - _ensure_tts_engine_ready() 返回 False. 无法朗读.")
            return
        print("MainWindow: _start_tts_with_segments - _ensure_tts_engine_ready() 返回 True. 引擎应可用.")
                
        # 检查并停止之前的朗读任务
        if self.tts_worker and self.tts_worker.isRunning():
            print("MainWindow: _start_tts_with_segments - 检测到正在运行的旧 TTS worker，先停止...")
            self.stop_reading() # stop_reading 内部会处理旧 worker 和旧引擎
            # stop_reading 后，tts_engine 应该被重新初始化了，再次确认
            print("MainWindow: _start_tts_with_segments - 旧 worker 停止后，再次调用 _ensure_tts_engine_ready()...")
            if not self._ensure_tts_engine_ready():
                self.statusBar.showMessage("停止旧朗读后TTS引擎初始化失败")
                print("MainWindow: _start_tts_with_segments - 停止旧worker后引擎检查失败. 无法朗读.")
                return
            print("MainWindow: _start_tts_with_segments - 停止旧worker后引擎检查成功.")

        # 在启动新的 TTSWorker 前，直接测试当前主线程的 self.tts_engine
        try:
            # print("MainWindow: _start_tts_with_segments - 【预朗读测试】准备朗读 '引擎测试...\'\")
            self.tts_engine.say("") # 使用无声的空格作为预热
            self.tts_engine.runAndWait()
            print("MainWindow: _start_tts_with_segments - 【预朗读测试】'空格' runAndWait() 调用完成.")
        except Exception as e_pre_speak:
            print(f"MainWindow: _start_tts_with_segments - 【预朗读测试】失败: {e_pre_speak}")
            self.statusBar.showMessage(f"TTS预朗读测试失败: {e_pre_speak}")
            # 如果预朗读失败，可能需要再次尝试初始化或报错返回
            print("MainWindow: _start_tts_with_segments - 预朗读失败，尝试最后一次重新初始化引擎...")
            if self._init_tts_engine(): # _init_tts_engine 内部也使用空格ping
                print("MainWindow: _start_tts_with_segments - 最后一次重新初始化成功，再次尝试预朗读...")
                try:
                    self.tts_engine.say("") # 再次使用空格
                    self.tts_engine.runAndWait()
                    print("MainWindow: _start_tts_with_segments - 【预朗读再次测试】成功.")
                except Exception as e_pre_speak2:
                    print(f"MainWindow: _start_tts_with_segments - 【预朗读再次测试】仍然失败: {e_pre_speak2}")
                    self.statusBar.showMessage("TTS引擎彻底无法工作")
                    return # 彻底放弃
            else:
                print("MainWindow: _start_tts_with_segments - 最后一次重新初始化失败. 放弃.")
                self.statusBar.showMessage("TTS引擎初始化彻底失败")
                return
            
        print(f"MainWindow: _start_tts_with_segments - 创建新的 TTSWorker 实例，准备朗读 {len(text_segments)} 个段落.")
        self.tts_worker = TTSWorker(text_segments, ocr_boxes)
        # 连接信号和槽
        self.tts_worker.finished.connect(self.on_tts_finished)
        self.tts_worker.error.connect(self.on_tts_error)
        self.tts_worker.text_segment_started.connect(self.on_text_segment_started)
        self.tts_worker.text_segment_finished.connect(self.on_text_segment_finished)
        self.tts_worker.request_speak.connect(self.on_request_speak)  # 新增：连接朗读请求信号
        # 启动线程
        self.tts_worker.start()
        self.statusBar.showMessage("正在朗读...")

    def on_text_segment_started(self, segment_index):
        """开始朗读某个文字段时的槽函数"""
        sender_worker = self.sender()
        if sender_worker != self.tts_worker or not self.tts_worker:
            print(f"MainWindow: 忽略来自过时或无效 worker 的 text_segment_started 信号。 Sender: {sender_worker}, Current: {self.tts_worker}")
            return

        # 首先清除所有现有高亮
        self.pdf_viewer.clear_highlights()

        if hasattr(self, 'current_ocr_boxes') and segment_index < len(self.current_ocr_boxes):
            box_coords = self.current_ocr_boxes[segment_index]
            # 在PDF查看器上高亮显示当前朗读的文字框
            self.pdf_viewer.highlight_text_box(box_coords)
            
            # 更新状态栏显示当前朗读进度
            if hasattr(self, 'current_text_segments') and segment_index < len(self.current_text_segments):
                current_text = self.current_text_segments[segment_index]
                total_segments = len(self.current_text_segments)
                self.statusBar.showMessage(f"正在朗读 ({segment_index + 1}/{total_segments}): {current_text[:30]}...")
                print(f"开始朗读段落 {segment_index + 1}/{total_segments}: {current_text[:50]}...")
    
    def on_text_segment_finished(self, segment_index):
        """完成朗读某个文字段时的槽函数"""
        sender_worker = self.sender()
        if sender_worker != self.tts_worker or not self.tts_worker:
            print(f"MainWindow: 忽略来自过时或无效 worker 的 text_segment_finished 信号。 Sender: {sender_worker}, Current: {self.tts_worker}")
            return

        if hasattr(self, 'current_text_segments') and segment_index < len(self.current_text_segments):
            total_segments = len(self.current_text_segments)
            print(f"完成朗读段落 {segment_index + 1}/{total_segments}")
            
            # 如果是最后一段，提前更新状态
            if segment_index == total_segments - 1:
                self.statusBar.showMessage("朗读即将完成...")
        
        # 可选：在朗读完成后短暂保持高亮，然后清除
        # 这里简单地保持高亮，等待下一段开始或者朗读完全结束时清除
        pass

    def stop_reading(self):
        """停止 TTS 朗读"""
        if self.tts_worker and self.tts_worker.isRunning():
            self.statusBar.showMessage("正在停止朗读...")
            print("请求停止 TTS worker...")
            
            # 设置停止标志
            self.is_stopping = True
            
            # 先停止主线程的TTS引擎
            if self.tts_engine:
                try:
                    self.tts_engine.stop()
                    print("主线程TTS引擎已停止")
                except Exception as e:
                    print(f"停止主线程TTS引擎时出错: {e}")
            
            # 然后请求停止worker
            self.tts_worker.stop()
            
            # 等待worker停止
            if not self.tts_worker.wait(3000):  # 增加等待时间到3秒
                print("警告: TTS worker 未能在超时内停止")
            
            print("TTS worker 已停止或超时。准备重新初始化TTS引擎。")
            QApplication.processEvents() # 处理任何挂起的Qt事件
            QThread.msleep(100) # 增加一个短暂的延迟，给TTS驱动一些时间

            # 彻底重新初始化TTS引擎以确保下次使用时状态正常
            print("停止后重新初始化TTS引擎...")
            if not self._init_tts_engine():
                print("警告: TTS引擎重新初始化失败")
            
            # 最后清理worker引用
            self.tts_worker = None
            
            # 清除高亮
            self.pdf_viewer.clear_highlights()
            
            # 清除停止标志
            self.is_stopping = False
            
            self.statusBar.showMessage("朗读已停止")
        else:
            # 确保停止标志被清除
            self.is_stopping = False

    def on_tts_finished(self):
        """TTS Worker 完成时的槽函数"""
        print("TTS worker finished signal received.")
        # 清除高亮
        self.pdf_viewer.clear_highlights()
        
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
        # 清除高亮
        self.pdf_viewer.clear_highlights()
        
        sender_worker = self.sender()
        if sender_worker == self.tts_worker:
             self.statusBar.showMessage(f"朗读错误: {error_message}")
             self.tts_worker = None # 清理 worker 引用
        else:
             print("警告: 收到了一个未知或过时 TTS worker 的 error 信号。")

    def save_session(self):
        """保存当前会话信息到配置文件"""
        if not self.current_file and not self.session_history: # 如果没有任何东西可保存
            return

        if self.current_file: # 如果当前有打开的文件，更新其页码
            self.session_history[self.current_file] = self.pdf_viewer.current_page_num
            self.last_opened_file = self.current_file
            
        session_data = {
            "session_history": self.session_history,
            "last_opened_file": self.last_opened_file
        }
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=4) # 使用 indent 使 JSON 更易读
            print(f"会话信息已保存: {session_data}")
        except Exception as e:
            print(f"保存会话信息时出错: {e}")
    
    def load_last_session(self):
        """加载上次会话信息并打开文件"""
        if not os.path.exists(self.config_file):
            self.statusBar.showMessage("未找到配置文件。")
            return
            
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
                
            self.session_history = session_data.get("session_history", {})
            self.last_opened_file = session_data.get("last_opened_file")
            
            page_to_open = 0
            if self.last_opened_file and os.path.exists(self.last_opened_file):
                page_to_open = self.session_history.get(self.last_opened_file, 0)
                print(f"正在打开上次的文件: {self.last_opened_file}, 页码: {page_to_open}")
                self.open_file(self.last_opened_file, page_to_open)
            elif self.session_history: # 如果没有last_opened_file，但历史记录不为空，尝试打开历史记录中的第一个
                # 这是一个可选行为，也可以选择不打开任何文件
                first_file_in_history = next(iter(self.session_history), None)
                if first_file_in_history and os.path.exists(first_file_in_history):
                    page_to_open = self.session_history.get(first_file_in_history, 0)
                    print(f"打开历史记录中的文件: {first_file_in_history}, 页码: {page_to_open}")
                    self.open_file(first_file_in_history, page_to_open)
                else:
                    self.statusBar.showMessage("上次打开的文件路径无效或历史记录为空。")
            else:
                self.statusBar.showMessage("没有上次会话信息或文件路径无效。")

        except json.JSONDecodeError:
            self.statusBar.showMessage("配置文件格式错误。")
            print("加载会话信息失败：配置文件格式错误。")
        except Exception as e:
            self.statusBar.showMessage(f"加载会话出错: {type(e).__name__}")
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

    def clear_highlights(self):
        """清除页面高亮"""
        self.pdf_viewer.clear_highlights()
        self.statusBar.showMessage("已清除高亮标记")

    def on_request_speak(self, text, segment_index):
        """处理朗读请求（在主线程中执行）"""
        requesting_worker = self.sender()
        if not isinstance(requesting_worker, TTSWorker):
            print(f"MainWindow: on_request_speak - sender 不是 TTSWorker 实例: {requesting_worker}")
            return

        try:
            # 1. 如果请求的 worker 自身已被明确要求停止，则不应朗读，并通知其完成以便退出。
            if requesting_worker.stop_requested:
                print(f"MainWindow: on_request_speak - 请求的 worker {requesting_worker} 已标记为停止，跳过朗读。段落: {segment_index + 1}")
                requesting_worker.on_segment_complete()
                return

            # 2. 如果 MainWindow 正在执行全局停止操作 (self.is_stopping is True)
            #    并且这个停止操作是针对当前发出请求的 worker (requesting_worker == self.tts_worker),
            #    那么也应该跳过朗读。
            #    如果 self.is_stopping is True 但 requesting_worker != self.tts_worker，
            #    这意味着 MainWindow 正在停止另一个 worker，此时这个旧 worker 的请求也应被忽略。
            if self.is_stopping:
                if requesting_worker == self.tts_worker:
                    print(f"MainWindow: on_request_speak - MainWindow正在停止当前worker {requesting_worker}，跳过朗读。段落: {segment_index + 1}")
                else:
                    # 这种情况理论上不常发生，因为旧 worker 应在被替换前停止。但作为防御。
                    print(f"MainWindow: on_request_speak - MainWindow全局停止中，但请求来自过时/非当前worker {requesting_worker} (当前应为 {self.tts_worker})，跳过。段落: {segment_index + 1}")
                requesting_worker.on_segment_complete() # 让它结束等待
                return
            
            # 3. 如果当前 MainWindow 有一个活动的 tts_worker，但这个请求不是来自它，
            #    那么这个请求来自一个过时的 worker，应该忽略。
            if self.tts_worker and self.tts_worker != requesting_worker:
                print(f"MainWindow: on_request_speak - 请求来自过时worker {requesting_worker}，但当前活动worker是 {self.tts_worker}。跳过朗读。段落: {segment_index + 1}")
                requesting_worker.on_segment_complete()
                return

            # 4. 确保TTS引擎可用
            if not self._ensure_tts_engine_ready():
                print(f"MainWindow: on_request_speak - 错误: 无法确保TTS引擎可用. 段落: {segment_index + 1}")
                # 仅在 worker 未被要求停止时才发送错误信号
                if not requesting_worker.stop_requested:
                    requesting_worker.error.emit("TTS引擎状态异常，无法朗读")
                else: # 否则，让它完成以退出
                    requesting_worker.on_segment_complete()
                return
            
            # 5. 执行朗读
            speech_successful = False
            try:
                # 在实际朗读前再次检查 worker 是否已被要求停止 (因为 runAndWait 是阻塞的)
                if requesting_worker.stop_requested:
                    print(f"MainWindow: on_request_speak - 朗读前检测到 worker {requesting_worker} 已停止。段落: {segment_index + 1}")
                    requesting_worker.on_segment_complete()
                    return

                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
                speech_successful = True
            except RuntimeError as tts_runtime_error:
                print(f"MainWindow: on_request_speak - TTS引擎朗读时出错 (RuntimeError): {tts_runtime_error}. 段落: {segment_index + 1}")
                # 可以在这里尝试重新初始化引擎并重试一次，如果适用
                # if self._ensure_tts_engine_ready(): ...
            except Exception as general_tts_error:
                print(f"MainWindow: on_request_speak - TTS引擎朗读时发生未知错误: {general_tts_error}. 段落: {segment_index + 1}")

            # 6. 回调请求的 worker
            # 检查朗读后 worker 是否被要求停止
            if requesting_worker.stop_requested:
                print(f"MainWindow: on_request_speak - 朗读后检测到 worker {requesting_worker} 已停止。段落: {segment_index + 1}")
                requesting_worker.on_segment_complete()
            elif speech_successful:
                requesting_worker.on_segment_complete()
            else:
                # 确保 worker 仍然存在且未被要求停止才发送错误
                if not requesting_worker.stop_requested: # 避免在已停止的worker上触发error
                    requesting_worker.error.emit(f"朗读段落 {segment_index + 1} 失败")
                else: # 如果在朗读失败的同时也被要求停止了，也标记为完成
                    requesting_worker.on_segment_complete()
                    
        except Exception as e:
            print(f"MainWindow: on_request_speak - 发生外部错误: {e}. 段落: {segment_index if 'segment_index' in locals() else '未知'}")
            # 确保回调给正确的 worker，并检查其状态
            if requesting_worker:
                if not requesting_worker.stop_requested:
                    requesting_worker.error.emit(f"朗读时发生严重错误: {e}")
                else: # 如果 worker 已被要求停止，则通知完成以允许干净退出
                    requesting_worker.on_segment_complete()

    def _init_tts_engine(self):
        """初始化或重新初始化TTS引擎"""
        try:
            # 如果已有引擎，先清理
            # if hasattr(self, 'tts_engine') and self.tts_engine:
            #     try:
            #         # self.tts_engine.stop() # stop() 只是停止当前话语
            #         del self.tts_engine
            #         self.tts_engine = None
            #         print("旧 TTS 引擎已del并置空")
            #     except Exception as e:
            #         print(f"清理旧TTS引擎时出错: {e}")
            
            # 创建新的TTS引擎
            self.tts_engine = pyttsx3.init()
            
            # 设置TTS引擎属性（确保引擎处于正确状态）
            voices = self.tts_engine.getProperty('voices')
            if voices:
                # 尝试设置中文语音（如果可用）
                for voice in voices:
                    if 'chinese' in voice.name.lower() or 'zh' in voice.id.lower():
                        self.tts_engine.setProperty('voice', voice.id)
                        break
            
            # 设置语速（可选）
            self.tts_engine.setProperty('rate', 200)  # 每分钟200词

            # 尝试一个快速的 "ping" 来确保引擎工作
            try:
                # self.tts_engine.say("你好") # 使用一个简短的实际词语
                self.tts_engine.say("") # 改回使用空格进行 ping
                self.tts_engine.runAndWait() # 确保它能完成一个循环
            except Exception as ping_error:
                # print(f"TTS引擎初始化后ping测试失败 (使用 '你好'): {ping_error}")
                print(f"TTS引擎初始化后ping测试失败 (使用空格): {ping_error}")
                # 将特定错误封装，以便上层可以判断
                # raise RuntimeError("TTS engine ping test failed after init with '你好'") from ping_error
                raise RuntimeError("TTS engine ping test failed after init with space") from ping_error
            
            # print("TTS引擎初始化并ping测试成功 (使用 '你好')")
            print("TTS引擎初始化并ping测试成功 (使用空格)")
            return True
        except Exception as e:
            self.tts_engine = None
            print(f"TTS引擎初始化失败: {e}")
            return False

    def _ensure_tts_engine_ready(self):
        """确保TTS引擎处于可用状态"""
        if not self.tts_engine:
            print("TTS引擎为空，尝试重新初始化...")
            return self._init_tts_engine()
        
        try:
            # 测试引擎是否正常工作
            # 获取一个简单的属性来检查引擎状态
            _ = self.tts_engine.getProperty('rate')
            return True
        except Exception as e:
            print(f"TTS引擎状态异常: {e}，重新初始化...")
            return self._init_tts_engine()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
