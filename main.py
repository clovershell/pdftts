import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QFileDialog, QToolBar, 
                           QStatusBar, QVBoxLayout, QWidget, QScrollArea)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QIcon, QKeySequence
import fitz  # PyMuPDF

from pdf_viewer import PDFViewer

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.current_file = None
        
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
        
        # 放大 - Ctrl++
        zoom_in_shortcut = QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Plus)
        zoom_in_action = QAction("放大", self)
        zoom_in_action.setShortcut(zoom_in_shortcut)
        zoom_in_action.triggered.connect(self.pdf_viewer.zoom_in)
        self.addAction(zoom_in_action)
        
        # 缩小 - Ctrl+-
        zoom_out_shortcut = QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Minus)
        zoom_out_action = QAction("缩小", self)
        zoom_out_action.setShortcut(zoom_out_shortcut)
        zoom_out_action.triggered.connect(self.pdf_viewer.zoom_out)
        self.addAction(zoom_out_action)
        
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
        prev_action.setStatusTip("查看上一页")
        prev_action.triggered.connect(self.pdf_viewer.prev_page)
        toolbar.addAction(prev_action)
        
        # 下一页
        next_action = QAction("下一页", self)
        next_action.setStatusTip("查看下一页")
        next_action.triggered.connect(self.pdf_viewer.next_page)
        toolbar.addAction(next_action)
        
        # 放大
        zoom_in_action = QAction("放大", self)
        zoom_in_action.setStatusTip("放大视图")
        zoom_in_action.triggered.connect(self.pdf_viewer.zoom_in)
        toolbar.addAction(zoom_in_action)
        
        # 缩小
        zoom_out_action = QAction("缩小", self)
        zoom_out_action.setStatusTip("缩小视图")
        zoom_out_action.triggered.connect(self.pdf_viewer.zoom_out)
        toolbar.addAction(zoom_out_action)
        
    def open_file(self):
        # 在PyQt6中，不再使用QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开PDF文件", "", "PDF文件 (*.pdf)"
        )
        
        if file_path:
            self.current_file = file_path
            self.statusBar.showMessage(f"已打开: {file_path}")
            self.pdf_viewer.load_pdf(file_path)
            self.setWindowTitle(f"PDF阅读器 - {os.path.basename(file_path)}")
            self.update_status_bar()
            
    def update_status_bar(self):
        """更新状态栏信息"""
        if self.pdf_viewer.pdf_document:
            page_info = self.pdf_viewer.page_info
            self.statusBar.showMessage(page_info)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
