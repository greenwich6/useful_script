import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import requests
import pyttsx3
from vosk import Model, KaldiRecognizer
import pyaudio
import queue
import time
import os

# DeepSeek API 配置
API_KEY = "sk-47f1d92d349043a68d5971b183ca5557"  # 你的 DeepSeek API Key
API_URL = "https://api.deepseek.com/v1/chat/completions"

# 初始化语音识别（使用中文模型）
model = Model("model")  # 替换为中文模型文件的实际路径
recognizer = KaldiRecognizer(model, 16000)

# 初始化语音合成
engine = pyttsx3.init()

# 设置语音合成语言为中文
voices = engine.getProperty('voices')
for voice in voices:
    if "Chinese" in voice.name or "中文" in voice.name:
        engine.setProperty('voice', voice.id)
        break

# 设置语音合成速度和音量
engine.setProperty('rate', 150)  # 语速
engine.setProperty('volume', 1.0)  # 音量

# 初始化麦克风
try:
    mic = pyaudio.PyAudio()
    stream = mic.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8192)
except Exception as e:
    print("麦克风初始化失败:", e)
    stream = None

# 用于线程间通信的队列
message_queue = queue.Queue()  # 用于界面更新
api_queue = queue.Queue()      # 用于 API 调用

# 录音状态标志
is_recording = False

# API 调用缓存
api_cache = {}

# 调用 DeepSeek API
def get_deepseek_response(prompt):
    # 检查缓存
    if prompt in api_cache:
        return api_cache[prompt]

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500
    }
    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            text = response.json()["choices"][0]["message"]["content"]
            text = " ".join(text.split())
            api_cache[prompt] = text  # 缓存结果
            return text
        else:
            return f"抱歉，我无法回答这个问题。错误代码: {response.status_code}"
    except Exception as e:
        return f"API 调用失败: {str(e)}"

# 播放语音
def speak(text):
    max_length = 100  # 每段文本的最大长度
    segments = [text[i:i+max_length] for i in range(0, len(text), max_length)]
    for segment in segments:
        engine.say(segment)
    engine.runAndWait()

# 更新对话显示区域
def update_display(text):
    chat_display.config(state=tk.NORMAL)
    chat_display.insert(tk.END, text + "\n")
    chat_display.config(state=tk.DISABLED)
    chat_display.yview(tk.END)  # 自动滚动到底部

# 处理 API 调用
def process_api_queue():
    while True:
        prompt = api_queue.get()  # 从队列中获取用户输入
        response = get_deepseek_response(prompt)  # 调用 API
        message_queue.put(f"AI: {response}\n")  # 将 API 响应放入消息队列
        threading.Thread(target=speak, args=(response,), daemon=True).start()  # 语音播放在独立线程中

# 录音并识别语音
def record_and_recognize():
    global is_recording
    if not stream:
        message_queue.put("错误: 麦克风未初始化。\n")
        return

    is_recording = True
    print("开始录音...")
    start_time = time.time()
    timeout = 10  # 录音超时时间（秒）

    while is_recording:
        data = stream.read(4096)
        if recognizer.AcceptWaveform(data):
            text = recognizer.Result()
            text = eval(text)["text"]  # 提取识别结果
            if text:
                print("用户说:", text)
                message_queue.put(f"你: {text}\n")  # 更新界面
                api_queue.put(text)  # 将用户输入放入 API 队列
            break
        elif time.time() - start_time > timeout:  # 超时退出
            message_queue.put("录音超时，请重试。\n")
            break

    is_recording = False
    print("录音结束。")

# 处理开始录音按钮点击事件
def on_record_button_click():
    if is_recording:
        message_queue.put("已经在录音中...\n")
        return
    threading.Thread(target=record_and_recognize, daemon=True).start()

# 处理停止录音按钮点击事件
def on_stop_button_click():
    global is_recording
    is_recording = False
    message_queue.put("录音已停止。\n")

# 处理输入框回车事件
def on_entry_return(event):
    user_input = user_entry.get()
    if user_input:
        message_queue.put(f"你: {user_input}\n")  # 更新界面
        user_entry.delete(0, tk.END)
        api_queue.put(user_input)  # 将用户输入放入 API 队列

# 检查消息队列并更新界面
def check_queue():
    try:
        while True:
            message = message_queue.get_nowait()
            update_display(message)
    except queue.Empty:
        pass
    root.after(100, check_queue)  # 每 100 毫秒检查一次队列

# 创建 GUI 界面
root = tk.Tk()
root.title("AI 助手 - 中文版")
root.geometry("800x600")  # 设置更大的窗口大小

# 使用 ttk 控件美化界面
style = ttk.Style()
style.configure("TButton", padding=6, font=("Helvetica", 12))
style.configure("TEntry", padding=6, font=("Helvetica", 12))

# 对话显示区域
chat_display = scrolledtext.ScrolledText(root, wrap=tk.WORD, state=tk.DISABLED, width=100, height=30, font=("Helvetica", 12))
chat_display.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

# 按钮框架
button_frame = ttk.Frame(root)
button_frame.pack(pady=5)

# 开始录音按钮
record_button = ttk.Button(button_frame, text="开始录音", command=on_record_button_click)
record_button.pack(side=tk.LEFT, padx=5)

# 停止录音按钮
stop_button = ttk.Button(button_frame, text="停止录音", command=on_stop_button_click)
stop_button.pack(side=tk.LEFT, padx=5)

# 输入框
user_entry = ttk.Entry(root, width=50)
user_entry.pack(pady=5)
user_entry.bind("<Return>", on_entry_return)

# 启动 API 处理线程
threading.Thread(target=process_api_queue, daemon=True).start()

# 启动队列检查
root.after(100, check_queue)

# 运行主循环
root.mainloop()