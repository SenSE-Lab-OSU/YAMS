import gradio as gr
from glob import glob
import os
import shutil
from tqdm import tqdm 
import time
import zipfile
import tempfile
# import psutil

def create_zip(filename, file_paths):
    temp_dir = tempfile.gettempdir()
    zip_path = os.path.join(temp_dir, filename)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in file_paths:
            zipf.write(file, arcname=os.path.basename(file))  # Store without full path

    return zip_path

# def get_flash_drives():
#     flash_drives = []
#     for partition in psutil.disk_partitions():
#         if "removable" in partition.opts.lower() or "usb" in partition.device.lower():
#             flash_drives.append(partition.device)
#     return flash_drives

def get_msense_files(src_path, label):
    progress = gr.Progress()

    file_list = glob(os.path.join(src_path, '*.bin'))
    print(file_list)

    uuid_list = glob(os.path.join(src_path, '*.txt'))

    print(uuid_list)
    file_list.extend(uuid_list)

    progress(0, desc=f"Start copying {len(file_list)} files...")

    dst_dir = tempfile.gettempdir()
    dst_files = []

    try:
        counter = 1
        for f in progress.tqdm(file_list, desc="copying data... consider getting a coffee..."):
            dst_path = os.path.join(dst_dir, os.path.basename(f))
            shutil.copy(f, dst_path)
            dst_files.append(dst_path)
            counter += 1
        
        datetime_str = time.strftime("%y%m%d%H%M")
        zip_name = f"{datetime_str}-{label}.zip"
        zip_path = create_zip(zip_name, dst_files)
        return f"Successfully extracted {len(file_list)} to directory {dst_path}", zip_path
    except Exception as e:
        return str(e), None

def file_extractor_interface():
    with gr.Column():
        msense_path = gr.Text("F:\\", label="MotionSenSE path")
        label = gr.Text("msense4", label="Wristband name")
        extract_btn = gr.Button("Get Files 📂")

        info_panel = gr.Text(label='Status')

    files = gr.File(label="Extracted zip file")

    extract_btn.click(get_msense_files, inputs=[msense_path, label], outputs=[info_panel, files])
