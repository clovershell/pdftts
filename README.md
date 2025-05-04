# PyQt6 PDF阅读器与语音助手

这是一个基于PyQt6和PyMuPDF的PDF阅读器应用程序，集成了OCR识别和TTS语音朗读功能。

## 功能

- 打开PDF文件
- 浏览PDF页面（上一页/下一页）
- 缩放功能（放大/缩小）
- OCR文字识别（基于PaddleOCR）
- TTS语音朗读（基于pyttsx3）
- 自动保存上次会话（文件位置和页码）
- 简洁的用户界面
- 完善的键盘快捷键支持

## 安装依赖

在使用此应用程序之前，请确保安装所需的依赖项：

```bash
pip install -r requirements.txt
```

主要依赖包括：
- PyQt6：用于GUI界面
- PyMuPDF (fitz)：PDF文件处理
- PaddleOCR：文字识别
- pyttsx3：文本转语音
- OpenCV (cv2)：图像处理
- Pillow (PIL)：图像处理

## 使用方法

运行主程序：

```bash
python main.py
```

## 操作说明

1. 点击"打开"按钮选择PDF文件
2. 使用"上一页"和"下一页"按钮浏览页面
3. 使用"放大"和"缩小"按钮调整视图大小
4. 点击"识别并朗读"按钮，对当前页面进行OCR识别并朗读内容
5. 点击"停止朗读"按钮，随时中断语音播放

## 键盘快捷键

| 功能 | 快捷键 |
|------|--------|
| 打开文件 | Ctrl+O |
| 下一页 | 右箭头, Page Down |
| 上一页 | 左箭头, Page Up |
| 放大 | Ctrl++ |
| 缩小 | Ctrl+- |
| 识别并朗读 | Ctrl+R |
| 停止朗读 | Ctrl+T |

## 系统要求

- Python 3.7+
- PyQt6
- PyMuPDF (fitz)
- PaddleOCR
- pyttsx3
- OpenCV
- Pillow

## 特别说明

- 首次运行时，PaddleOCR会自动下载中文识别模型
- 应用程序会自动保存上次打开的文件和页码，下次启动时自动恢复
- OCR识别和TTS朗读在后台线程中运行，不会阻塞主界面 