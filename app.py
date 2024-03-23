import os
from tkinter import *
from tkinter import ttk
import tkinter as tk
from tkinter import filedialog
from PIL import Image
from PIL import UnidentifiedImageError
import threading


def check_folder_exist(folder):
    if not os.path.exists(folder):
        return False
    else:
        return True
    

def thread_convert_images():
    threads = []
    if check_folder_exist(input_folder) == False:
        tk.messagebox.showinfo("错误消息", "输入文件夹不存在")  
        return
    if check_folder_exist(output_folder) == False:
        tk.messagebox.showinfo("错误消息", "输出文件夹不存在")  
        return
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(('.webp', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')):
            thread = threading.Thread(target=format_images, args=([filename]))
            thread.start()
            threads.append(thread)
    
    # 等待所有线程执行完毕
    for thread in threads:
        thread.join()
                   
    # 全部执行之后，弹出提示框转换完成
    tk.messagebox.showinfo("转换完成", "转换完成")  

def convert_images():
    thread = threading.Thread(target=thread_convert_images) 
    thread.daemon = True
    thread.start() 
    
    
     
    
def format_images(filename):
    format = choice.get()
    try:
        filepath = os.path.join(input_folder, filename)
        output_filename, _ = os.path.splitext(filename)  # 分离文件名和扩展名
        output_path = os.path.join(output_folder, output_filename + '.' + format)
        img = Image.open(filepath)
        # 转换格式，例如从PNG转换为JPG
        if img.mode == "P":
            img = img.convert('RGB')
        img.save(output_path, format, optimize=True)
        print(f"Converted {filename}")
    except UnidentifiedImageError:
        print(f"Cannot convert {filename}. File may be corrupt or not supported.")    

def browse_input_folder():
    global input_folder
    input_folder = filedialog.askdirectory()

def browse_output_folder():
    global output_folder
    output_folder = filedialog.askdirectory()

def selected_format(format):
    format = choice.get()
    print(format)

# 创建主窗口
root = Tk()
root.title("Batch Image Converter")

# 设置窗口大小
root.geometry("800x600")

choice = StringVar()
input_folder = ""
output_folder = ""

format_list = ("PNG", "JPEG", "BMP", "GIF", "TIFF", "WEBP")
#choice.set(format_list[0])

# 添加控件
# label 选择图片位置
input_folder_label = ttk.Label(root, text="选择图片位置:")
input_folder_label.grid(row=0,column=0,pady=10,padx=20)
input_folder_button = ttk.Button(root, text="Select Input Folder", width=50,command=browse_input_folder)
input_folder_button.grid(row=0,column=1,columnspan=2,pady=10,padx=20 )

output_folder_label = ttk.Label(root, text="选择图片输出位置:")
output_folder_label.grid(row=1,column=0,pady=10,padx=20)
output_folder_button = ttk.Button(root, text="Select Output Folder", width=50,command= browse_output_folder)
output_folder_button.grid(row=1,column=1,columnspan=2,pady=10,padx=20)

# label 图片转换格式
format_label = ttk.Label(root, text="图片转换格式:")
format_label.grid(row=2,column=0,pady=10,padx=20)
format_menu = ttk.OptionMenu(root, choice, "PNG" ,*format_list, command=selected_format)
format_menu.grid(row=2,column=1,columnspan=2,pady=10,padx=20)

convert_button = ttk.Button(root, text="开始转换", command= convert_images)
convert_button.grid(row=3,column=0,columnspan=4)

root.mainloop()
