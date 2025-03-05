import gradio as gr
from glob import glob
import os
import shutil
from tqdm import tqdm 
import time
import zipfile
import tempfile
import psutil

def create_zip(filename, file_paths):
    temp_dir = tempfile.gettempdir()
    zip_path = os.path.join(temp_dir, filename)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in file_paths:
            zipf.write(file, arcname=os.path.basename(file))  # Store without full path
    return zip_path

def get_flash_drives():
    flash_drives = []
    for partition in psutil.disk_partitions():
        if "removable" in partition.opts.lower() or "usb" in partition.device.lower():
            flash_drives.append(partition.device)
    new_dropdown = gr.Dropdown(choices=flash_drives, value=flash_drives[0] if len(flash_drives) > 0 else None, allow_custom_value=True)
    return new_dropdown

def interface_refresh_reset():
    dropdown = get_flash_drives()
    return dropdown, default_refresh_btn(), gr.Text("1", label="Wristband name", visible=False), gr.Button("Get Files 📂", visible=True), gr.Button("", visible=False)

def get_msense_files(src_path, label):
    if label == "":
        gr.Warning("Wristband name cannot be empty")
        return "", gr.DownloadButton("No file to be downloaded", interactive=False)

    gr.Info("Start file extraction...")
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
        gr.Info(f"File ready")
        return f"Successfully extracted {len(file_list)} to {os.path.basename(zip_path)}", gr.DownloadButton(label="🎉Download data", value=zip_path, interactive=True)
    except Exception as e:
        gr.Error(str(e))
        return str(e), gr.DownloadButton("No file to be downloaded", interactive=False)

def file_extractor_interface():
    with gr.Column():
        with gr.Row():
            msense_path = gr.Dropdown(label="📁 MotionSenSE path", allow_custom_value=True)
            refreash_path_btn = gr.Button("🔄 Refresh / Start over")

        label = gr.Text("", label="Wristband name", visible=False)
        extract_btn = gr.Button("Get Files 📂")
        confirm_btn = gr.Button("", visible=False)

        info_panel = gr.Text(label='Status')

    # files = gr.File(label="Extracted zip file")

    download_btn = default_refresh_btn()

    extract_btn.click(prompt_device_name, outputs=[label, confirm_btn, extract_btn])

    label.change(check_label, inputs=label)

    confirm_btn.click(get_msense_files, inputs=[msense_path, label], outputs=[info_panel, download_btn])
    refreash_path_btn.click(interface_refresh_reset, outputs=[msense_path, download_btn,
                                                       label,
                                                       extract_btn,
                                                       confirm_btn])

def prompt_device_name():
    return gr.Text("", label="Wristband name", visible=True), gr.Button("Confirm name & Start 🪪", visible=True), gr.Button("Get Files 📂", visible=False)

def default_refresh_btn():
    return gr.DownloadButton("No file to be downloaded", interactive=False)

def check_label(label):
    if label == "":
        gr.Warning("Device name cannot be empty")