# PyQt6 PDF阅读器

这是一个基于PyQt6和PyMuPDF的简单PDF阅读器应用程序。

## 功能

- 打开PDF文件
- 浏览PDF页面（上一页/下一页）
- 缩放功能（放大/缩小）
- 简洁的用户界面
- 键盘快捷键支持

## 安装依赖

在使用此应用程序之前，请确保安装所需的依赖项：

```bash
pip install -r requirements.txt
```

## 使用方法

运行主程序：

```bash
python main.py
```

## 操作说明

1. 点击"打开"按钮选择PDF文件
2. 使用"上一页"和"下一页"按钮浏览页面
3. 使用"放大"和"缩小"按钮调整视图大小

## 键盘快捷键

| 功能 | 快捷键 |
|------|--------|
| 打开文件 | Ctrl+O |
| 下一页 | 右箭头, Page Down |
| 上一页 | 左箭头, Page Up |
| 放大 | Ctrl++ |
| 缩小 | Ctrl+- |

## 系统要求

- Python 3.7+
- PyQt6
- PyMuPDF (fitz) 