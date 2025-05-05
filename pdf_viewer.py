from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, 
                          QScrollArea, QSizePolicy)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QCursor
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint
import fitz  # PyMuPDF
import io
import numpy as np
import cv2

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
        self._page_count = 0
        
        # 添加鼠标拖动相关变量
        self.drag_enabled = False
        self.drag_start_pos = QPoint()
        self.scroll_start_pos = QPoint()
        self.setCursor(Qt.CursorShape.OpenHandCursor)  # 设置默认光标为手形
        
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
            self._page_count = len(self.pdf_document)
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
    
    def get_current_page_image(self) -> QImage | None:
        """获取当前页面的 QImage 对象"""
        if not self.pdf_document or self.current_page < 0:
            return None
        
        page = self.pdf_document.load_page(self.current_page)
        # 使用更高的 DPI 来提高 OCR 准确率
        zoom_matrix = fitz.Matrix(self.zoom_factor * 2, self.zoom_factor * 2) 
        pix = page.get_pixmap(matrix=zoom_matrix, alpha=False)
        
        # 转换为 QImage
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        return image.copy() # 返回副本以防原始数据被修改
        
    def get_current_page_image_bytes(self, dpi=200) -> bytes | None:
        """获取当前页面的图像字节数据（PNG格式）
        
        Args:
            dpi: 分辨率（每英寸点数），越高识别越精确但处理越慢
            
        Returns:
            bytes: PNG格式的图像字节数据，如果无法获取则返回None
        """
        if not self.pdf_document or self.current_page < 0:
            return None
            
        try:
            # 使用PyMuPDF直接获取高分辨率图像
            page = self.pdf_document.load_page(self.current_page)
            
            # 计算合适的缩放矩阵，基于请求的DPI
            # 标准PDF分辨率是72 DPI，所以我们计算缩放系数
            zoom = dpi / 72.0
            zoom_matrix = fitz.Matrix(zoom, zoom)
            
            # 渲染页面到像素图
            pix = page.get_pixmap(matrix=zoom_matrix, alpha=False)
            
            # 转换为PNG格式的字节数据
            png_bytes = pix.tobytes("png")
            
            print(f"生成了 {len(png_bytes)/1024:.1f}KB 大小的页面图像，用于OCR处理")
            return png_bytes
            
        except Exception as e:
            print(f"获取页面图像字节数据时出错: {e}")
            return None

    def update_view(self):
        """更新视图"""
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

    def wheelEvent(self, event):
        """处理鼠标滚轮事件"""
        modifiers = event.modifiers()
        # 优先尝试 pixelDelta，如果为0再尝试 angleDelta
        delta_y = event.pixelDelta().y()
        if delta_y == 0:
            delta_y = event.angleDelta().y()
        
        # 使用统一的 delta 变量名，简化后续逻辑
        delta = delta_y 
        
        # 检查是否按下了Ctrl键
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
        else:
            # 如果没有按修饰键，则正常滚动
            super().wheelEvent(event)

    def go_to_page(self, page_num):
        """跳转到指定页面"""
        if not self.pdf_document:
            return
            
        if 0 <= page_num < len(self.pdf_document):
            self.current_page = page_num
            self.update_page_view()
            return True
        return False
        
    @property
    def current_page_num(self):
        """获取当前页码"""
        return self.current_page
        
    @property
    def page_count(self):
        """获取PDF总页数"""
        return self._page_count if self.pdf_document else 0

    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 记录拖动起始位置
            self.drag_enabled = True
            self.drag_start_pos = event.position().toPoint()
            self.scroll_start_pos = QPoint(self.horizontalScrollBar().value(),
                                         self.verticalScrollBar().value())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)  # 改变光标为抓取状态
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """处理鼠标移动事件"""
        if self.drag_enabled:
            # 计算移动距离
            current_pos = event.position().toPoint()
            delta = current_pos - self.drag_start_pos
            
            # 更新滚动条位置 (注意方向是相反的，所以用减法)
            new_pos_x = self.scroll_start_pos.x() - delta.x()
            new_pos_y = self.scroll_start_pos.y() - delta.y()
            
            # 设置新的滚动位置
            self.horizontalScrollBar().setValue(new_pos_x)
            self.verticalScrollBar().setValue(new_pos_y)
            
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton and self.drag_enabled:
            self.drag_enabled = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)  # 恢复光标为手形
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            
    def leaveEvent(self, event):
        """鼠标离开控件区域时的事件"""
        # 确保鼠标离开区域时重置拖动状态
        self.drag_enabled = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().leaveEvent(event)