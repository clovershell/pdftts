from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, 
                          QScrollArea, QSizePolicy)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QCursor, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint, QRectF
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
        
        # 高亮相关变量
        self.highlight_boxes = []  # 存储当前高亮的文字框坐标
        self.ocr_dpi_scale = 200 / 72.0  # OCR使用的DPI与显示DPI的缩放比例
        
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
        
        # 在图像上绘制高亮框
        if self.highlight_boxes:
            image = self._draw_highlights(image)
        
        # 显示图像
        qpixmap = QPixmap.fromImage(image)
        self.page_label.setPixmap(qpixmap)
        
        # 更新页码信息
        self.page_info = f"第 {self.current_page + 1} 页，共 {len(self.pdf_document)} 页"
        
        # 发送页面变更信号
        self.page_changed.emit()

    def _draw_highlights(self, image):
        """在图像上绘制高亮框"""
        # 创建QPainter在图像上绘制
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)  # 启用反锯齿
        
        # 设置高亮颜色（黄色半透明，增加透明度）
        highlight_color = QColor(255, 255, 0, 100)  # RGBA: 黄色，40%透明度
        border_color = QColor(255, 200, 0, 180)     # 边框颜色：深黄色，70%透明度
        
        painter.setBrush(QBrush(highlight_color))
        painter.setPen(QPen(border_color, 3))  # 增加边框宽度到3像素
        
        for box_coords in self.highlight_boxes:
            # 将OCR坐标转换为当前显示图像的坐标
            scaled_coords = self._scale_coords_to_display(box_coords)
            if scaled_coords:
                # 创建多边形并填充
                points = [QPoint(int(x), int(y)) for x, y in scaled_coords]
                painter.drawPolygon(points)
                
                # 添加一个稍微内缩的高亮边框，增强视觉效果
                inner_highlight = QColor(255, 255, 100, 50)  # 更浅的黄色
                painter.setBrush(QBrush(inner_highlight))
                painter.setPen(QPen(QColor(255, 255, 0, 120), 1))
                
                # 计算内缩的坐标点（向内缩小2像素）
                if len(points) >= 4:
                    # 简单的内缩处理
                    center_x = sum(p.x() for p in points) / len(points)
                    center_y = sum(p.y() for p in points) / len(points)
                    
                    inner_points = []
                    for p in points:
                        # 向中心方向内缩2像素
                        dx = p.x() - center_x
                        dy = p.y() - center_y
                        if dx != 0 or dy != 0:
                            factor = max(0.1, 1 - 2 / max(abs(dx), abs(dy)))
                            new_x = center_x + dx * factor
                            new_y = center_y + dy * factor
                            inner_points.append(QPoint(int(new_x), int(new_y)))
                        else:
                            inner_points.append(p)
                    
                    if len(inner_points) >= 3:
                        painter.drawPolygon(inner_points)
        
        painter.end()
        return image

    def _scale_coords_to_display(self, ocr_coords):
        """将OCR坐标转换为当前显示图像的坐标
        
        Args:
            ocr_coords: OCR返回的四个角点坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        
        Returns:
            缩放后的坐标列表
        """
        try:
            # OCR使用200 DPI，PDF显示使用当前zoom_factor
            # 由于OCR图像和显示图像都是基于同一个PDF页面，我们需要考虑两者的分辨率差异
            
            # OCR图像的DPI缩放系数
            ocr_dpi = 200
            pdf_base_dpi = 72
            ocr_scale = ocr_dpi / pdf_base_dpi  # OCR相对于PDF基础分辨率的缩放
            
            # 当前显示图像的缩放系数
            display_scale = self.zoom_factor
            
            # 从OCR坐标到显示坐标的转换比例
            scale_ratio = display_scale / ocr_scale
            
            scaled_coords = []
            for x, y in ocr_coords:
                scaled_x = x * scale_ratio
                scaled_y = y * scale_ratio
                scaled_coords.append([scaled_x, scaled_y])
            
            return scaled_coords
        except Exception as e:
            print(f"坐标转换错误: {e}")
            return None

    def highlight_text_box(self, box_coords):
        """高亮显示指定的文字框 (使用 QPainter 机制)
        
        Args:
            box_coords: 文字框的四个角点坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                        这些是原始OCR坐标，将在 _draw_highlights 中被缩放。
        """
        # 增加对 box_coords 的有效性检查
        if not box_coords or \
           not isinstance(box_coords, list) or \
           not all(isinstance(coord, (list, tuple)) and len(coord) == 2 
                   for coord in box_coords):
            print(f"PDFViewer: Invalid or empty box_coords for highlight: {box_coords}")
            self.highlight_boxes = [] # 清空以防无效数据残留
            self.update_page_view() # 更新视图以移除可能存在的旧高亮
            return

        # main.py 中的 on_text_segment_started 会先调用 clear_highlights,
        # 所以这里直接设置新的高亮框
        self.highlight_boxes = [box_coords]
        self.update_page_view() # 重新绘制页面以显示高亮

    def clear_highlights(self):
        """清除所有高亮 (使用 QPainter 机制)"""
        if not self.highlight_boxes: # 如果已经为空，则无需更新
            return
        self.highlight_boxes = []
        self.update_page_view() # 重新绘制页面以移除高亮

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