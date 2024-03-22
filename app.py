import os
from tkinter import *
from tkinter import filedialog
from PIL import Image
from PIL import UnidentifiedImageError

def convert_images():
    format = choice.get()
    print(format)
    print(input_folder)
    print(output_folder)
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(('.webp', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')):
            try:
                filepath = os.path.join(input_folder, filename)
                output_filename, _ = os.path.splitext(filename)  # 分离文件名和扩展名
                output_path = os.path.join(output_folder, output_filename + '.' + format)
                img = Image.open(filepath)
                # 转换格式，例如从PNG转换为JPG
                img.save(output_path, format, optimize=True)
                print(f"Converted {filename}")
            except UnidentifiedImageError:
                print(f"Cannot convert {filename}. File may be corrupt or not supported.")

def browse_input_folder():
    global input_folder
    input_folder = filedialog.askdirectory()
    print(input_folder)

def browse_output_folder():
    global output_folder
    output_folder = filedialog.askdirectory()
    print(output_folder)

def selected_format(format):
    format = choice.get()
    print(format)

# 创建主窗口
root = Tk()
root.title("Batch Image Converter")

choice = StringVar()
input_folder = ""
output_folder = ""

# 添加控件
input_folder_button = Button(root, text="Select Input Folder", command=browse_input_folder)
input_folder_button.pack()

output_folder_button = Button(root, text="Select Output Folder", command= browse_output_folder)
output_folder_button.pack()

format_menu = OptionMenu(root, choice, "PNG", "JPG", "BMP", "GIF", "TIFF", command=selected_format)
format_menu.pack()

convert_button = Button(root, text="Start Conversion", command= convert_images)
convert_button.pack()

root.mainloop()
