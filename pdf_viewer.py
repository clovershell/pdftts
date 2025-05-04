from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, 
                          QScrollArea, QSizePolicy)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, pyqtSignal
import fitz  # PyMuPDF
import io

class PDFViewer(QScrollArea):
    # 定义信号
    page_changed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.initUI()
        self.current_page = 0
        self.zoom_factor = 1.0
        self.pdf_document = None
        self.page_info = "请打开PDF文件"
        
    def initUI(self):
        # 设置滚动区域属性
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 创建内容区域
        self.content_widget = QWidget()
        self.setWidget(self.content_widget)
        
        # 创建布局
        self.layout = QVBoxLayout(self.content_widget)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 创建用于显示PDF页面的标签
        self.page_label = QLabel("请打开PDF文件")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.layout.addWidget(self.page_label)
    
    def load_pdf(self, file_path):
        """加载PDF文件"""
        try:
            self.pdf_document = fitz.open(file_path)
            self.current_page = 0
            self.zoom_factor = 1.0
            self.update_page_view()
            self.page_changed.emit()
        except Exception as e:
            self.page_label.setText(f"无法打开PDF文件: {e}")
            self.page_info = "打开PDF文件失败"
            self.page_changed.emit()
    
    def update_page_view(self):
        """更新页面视图"""
        if not self.pdf_document or self.current_page >= len(self.pdf_document):
            return
        
        # 获取当前页面
        page = self.pdf_document[self.current_page]
        
        # 应用缩放
        zoom_matrix = fitz.Matrix(self.zoom_factor, self.zoom_factor)
        pixmap = page.get_pixmap(matrix=zoom_matrix)
        
        # 转换为QImage
        img_data = pixmap.samples
        image = QImage(img_data, pixmap.width, pixmap.height, 
                       pixmap.stride, QImage.Format.Format_RGB888)
        
        # 显示图像
        pixmap = QPixmap.fromImage(image)
        self.page_label.setPixmap(pixmap)
        
        # 更新页码信息
        self.page_info = f"第 {self.current_page + 1} 页，共 {len(self.pdf_document)} 页"
        
        # 发送页面变更信号
        self.page_changed.emit()
    
    def next_page(self):
        """跳转到下一页"""
        if self.pdf_document and self.current_page < len(self.pdf_document) - 1:
            self.current_page += 1
            self.update_page_view()
    
    def prev_page(self):
        """跳转到上一页"""
        if self.pdf_document and self.current_page > 0:
            self.current_page -= 1
            self.update_page_view()
    
    def zoom_in(self):
        """放大视图"""
        if self.pdf_document:
            self.zoom_factor *= 1.2
            self.update_page_view()
    
    def zoom_out(self):
        """缩小视图"""
        if self.pdf_document:
            self.zoom_factor *= 0.8
            self.update_page_view() 