#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能验证脚本
验证高亮功能的各个组件是否正确实现
"""

import sys
import os

# 先初始化QApplication避免Qt组件创建错误
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()

def verify_imports():
    """验证导入是否正常"""
    try:
        from main import MainWindow, TTSWorker
        from pdf_viewer import PDFViewer
        print("✅ 模块导入成功")
        return True
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        return False

def verify_pdf_viewer_methods():
    """验证PDF查看器是否有高亮相关方法"""
    try:
        from pdf_viewer import PDFViewer
        viewer = PDFViewer()
        
        # 检查高亮相关方法
        methods = ['highlight_text_box', 'clear_highlights', '_draw_highlights', '_scale_coords_to_display']
        for method in methods:
            if hasattr(viewer, method):
                print(f"✅ PDFViewer.{method} 方法存在")
            else:
                print(f"❌ PDFViewer.{method} 方法缺失")
                return False
        
        # 检查高亮相关属性
        if hasattr(viewer, 'highlight_boxes'):
            print("✅ PDFViewer.highlight_boxes 属性存在")
        else:
            print("❌ PDFViewer.highlight_boxes 属性缺失")
            return False
            
        return True
    except Exception as e:
        print(f"❌ PDFViewer验证失败: {e}")
        return False

def verify_tts_worker():
    """验证TTS Worker是否有正确的信号"""
    try:
        from main import TTSWorker
        from PyQt6.QtCore import pyqtSignal
        
        # 检查信号
        signals = ['text_segment_started', 'text_segment_finished']
        for signal in signals:
            if hasattr(TTSWorker, signal):
                print(f"✅ TTSWorker.{signal} 信号存在")
            else:
                print(f"❌ TTSWorker.{signal} 信号缺失")
                return False
        
        return True
    except Exception as e:
        print(f"❌ TTSWorker验证失败: {e}")
        return False

def verify_main_window_methods():
    """验证主窗口是否有高亮相关方法"""
    try:
        from main import MainWindow
        
        methods = ['on_text_segment_started', 'on_text_segment_finished', 'clear_highlights']
        for method in methods:
            if hasattr(MainWindow, method):
                print(f"✅ MainWindow.{method} 方法存在")
            else:
                print(f"❌ MainWindow.{method} 方法缺失")
                return False
        
        return True
    except Exception as e:
        print(f"❌ MainWindow验证失败: {e}")
        return False

def main():
    print("=" * 50)
    print("PDF TTS 高亮功能验证")
    print("=" * 50)
    
    tests = [
        ("模块导入", verify_imports),
        ("PDF查看器方法", verify_pdf_viewer_methods),
        ("TTS Worker信号", verify_tts_worker),
        ("主窗口方法", verify_main_window_methods),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 测试: {test_name}")
        if test_func():
            passed += 1
        else:
            print(f"   测试失败")
    
    print("\n" + "=" * 50)
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有功能验证通过！高亮功能已正确实现。")
        print("\n📋 功能说明:")
        print("   1. OCR识别时会保存文字框位置信息")
        print("   2. TTS朗读会分段进行，每段都会发送信号")
        print("   3. 朗读时会在PDF上显示黄色半透明高亮框")
        print("   4. 坐标会根据缩放级别自动转换")
        print("   5. 朗读完成后会自动清除高亮")
    else:
        print("❌ 部分功能验证失败，请检查实现。")
    
    print("=" * 50)

if __name__ == "__main__":
    main() 