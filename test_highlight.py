#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高亮功能测试脚本
测试OCR识别和朗读高亮功能是否正常工作
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import MainWindow
from PyQt6.QtWidgets import QApplication

def main():
    """测试程序入口"""
    print("启动PDF TTS应用程序...")
    print("功能测试说明：")
    print("1. 打开一个包含中文文字的PDF文件")
    print("2. 点击'识别并朗读'按钮或按F9键")
    print("3. 观察是否有黄色半透明高亮框显示在朗读的文字上")
    print("4. 验证是否会连续朗读整页所有文字（不只是第一行）")
    print("5. 高亮框应该跟随朗读进度移动")
    print("6. 状态栏应该显示朗读进度（x/总数）")
    print("7. 测试停止朗读和清除高亮功能")
    print("-" * 60)
    print("💡 新架构说明：")
    print("   - TTS引擎在主线程中初始化和运行")
    print("   - QThread只负责控制流程和发送信号")
    print("   - 每个文字段在主线程中完整朗读后再继续下一段")
    print("-" * 60)
    print("🔍 预期的控制台输出：")
    print("   TTS引擎初始化成功")
    print("   识别到 X 个文字块")
    print("   TTSWorker开始：准备朗读 X 个文字段")
    print("   主线程开始朗读段落 1: xxx...")
    print("   主线程完成朗读段落 1")
    print("   主线程开始朗读段落 2: xxx...")
    print("   主线程完成朗读段落 2")
    print("   ...")
    print("-" * 60)
    print("❗ 如果仍然卡住，请检查：")
    print("   - TTS引擎是否初始化成功")
    print("   - 是否有'主线程开始朗读'的输出")
    print("   - 是否有'主线程完成朗读'的输出")
    print("-" * 60)
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 