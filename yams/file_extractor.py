import gradio as gr
from glob import glob
import os
import shutil
from tqdm import tqdm 
import time
import zipfile
import tempfile
import psutil
import re
import json
from datetime import datetime

class FileDownloader():
    def __init__(self):
        self.all_files = []

    def interface(self):
        with gr.Row():
            msense_group = gr.CheckboxGroup(label="📁 MotionSenSE path")
            msense_path = gr.Dropdown(label="📁 Custom MotionSenSE path", allow_custom_value=True)
            refreash_path_btn = gr.Button("🔄 Refresh / Start over")

        file_explorer_btn = gr.Button("Browse session")

        enc_table = gr.CheckboxGroup(label="Available session")

        file_explorer_btn.click(self.get_available_files, 
                                inputs=[msense_path, msense_group],
                                outputs=enc_table)

        download_btn2 = gr.Button("Get selected sessions 📂")

        label = gr.Text("", label="(Optional) Note", visible=False)
        
        extract_btn = gr.Button("Get Files 📂", visible=False)
        confirm_btn = gr.Button("", visible=False)

        info_panel = gr.Text(label='Status')

        download_btn = default_refresh_btn()

        download_btn2.click(self.download_selected_files, inputs=enc_table, outputs=[info_panel, download_btn])

        extract_btn.click(prompt_device_name, outputs=[label, confirm_btn, extract_btn])

        confirm_btn.click(get_msense_files, inputs=[msense_path, msense_group, label], outputs=[info_panel, download_btn])
        refreash_path_btn.click(interface_refresh_reset, outputs=[msense_path, msense_group, download_btn,
                                                        label,
                                                        extract_btn,
                                                        confirm_btn])
        
    def download_selected_files(self, enc_list):
        all_matched = {}
        for src_path, src_files in self.all_files.items():
            matched_files = []
            mac_addr = f"dev-{time.strftime("%y%m%d%H%M")}"
            print(src_files)
            for file in src_files:
                f = os.path.basename(file)

                # include uuid.txt and mac addr
                if f.endswith("uuid.txt"): 
                    matched_files.append(file)

                    mac_pattern = r'(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}'
                    with open(file, 'r') as uuid_file:
                        content = uuid_file.read()
                        mac_addr = re.findall(mac_pattern, content)
                        if len(mac_addr) > 0: 
                            mac_addr = mac_addr[0]
                            mac_addr = look_up_device_name(mac_addr).replace(':', '-')
                    continue

                # include bin file with desired encoding prefixed
                if any(f.startswith(enc) for enc in enc_list) and f.endswith('.bin'):
                    matched_files.append(file)

            all_matched[mac_addr] = matched_files
            print(all_matched)

        # start copying
        with tempfile.TemporaryDirectory() as dst_dir:
            num_src_dirs = len(all_matched.keys())
            for i, (dev_name, file_list) in enumerate(all_matched.items()):
                gr.Info(f"Start file extraction {i+1} / {num_src_dirs}...")
                progress = gr.Progress()
                progress(0, desc=f"Start copying {len(file_list)} files for drive {i+1} / {num_src_dirs}...")

                os.makedirs(os.path.join(dst_dir, dev_name))

                for src_path in progress.tqdm(file_list, desc=f"copying data {i+1} / {num_src_dirs}... consider getting a coffee..."):
                    dst_path = os.path.join(dst_dir, dev_name, os.path.basename(src_path))
                    print(src_path, dst_path)
                    shutil.copy(src_path, dst_path)

            # zipping up
            zip_filename = os.path.join(tempfile.gettempdir(), f"{time.strftime("%y%m%d%H%M")}_msense.zip")
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(dst_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        arcname = os.path.relpath(full_path, dst_dir)
                        zipf.write(full_path, arcname=arcname)

            return "File ready", gr.DownloadButton(label="🎉Download data", value=zip_filename, interactive=True)


    def get_available_files(self, src_path, src_path_grp):
        # merge input directories
        print(src_path, src_path_grp)
        if src_path not in src_path_grp and src_path != '' and src_path: src_path_grp.append(src_path) 
        print('=====', src_path_grp)

        # file_info = {}
        file_info = []
        all_encoding = set() 

        self.all_files = {}

        progress = gr.Progress()

        for i, src_path in enumerate(src_path_grp):
            file_list = sorted(glob(os.path.join(src_path, '*.bin')))
            # print(file_list)

            uuid_list = glob(os.path.join(src_path, '*.txt'))
            file_list.extend(uuid_list)

            self.all_files[src_path] = file_list

            progress(0, desc=f"Start copying {len(file_list)} files for drive {i+1} / {len(src_path_grp)}...")

            for f in file_list:
                f = os.path.basename(f)
                if 'ac' in f:
                    match = re.match(r'(?:(\d+))?ac(\d+)\.bin$', f)
                    if match:
                        encoding = match.group(1)  # can be None
                        timestamp = int(match.group(2))

                        # Convert to local time
                        dt = datetime.fromtimestamp(timestamp)
                        timestamp = dt.strftime('%m/%d/%y')

                        # quick way to determine encoding technique
                        if int(encoding) > 32000:
                            sub = encoding[:-2]
                            ses = encoding[-2:]
                            # print(f"sub={sub}, ses={ses}")
                            alias = f"sub-{sub}, ses-{ses} ({timestamp})"
                        else:
                            alias = f"{encoding} ({timestamp})"

                        if encoding not in all_encoding:
                            all_encoding.add(encoding)

                        # file_info[alias] = encoding
                        file_info.append((alias, encoding))

        return gr.CheckboxGroup(file_info)



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

    checkbox_grp = gr.CheckboxGroup(choices=flash_drives, value=flash_drives)

    return new_dropdown, checkbox_grp

def interface_refresh_reset():
    dropdown, checkboxes = get_flash_drives()
    return dropdown, checkboxes, default_refresh_btn(), gr.Text("1", label="(Optional) Note", visible=False), gr.Button("Get Files 📂", visible=False), gr.Button("", visible=False)

def get_device_info(file_path="device_info.json"):
    if not os.path.exists(file_path):
        print(f"{file_path} does not exist.")
        return None

    with open(file_path, 'r') as f:
        data = json.load(f)

    mac_table = {v: k for k, v in data.items()}
    return mac_table

def look_up_device_name(mac_addr, file_path="device_info.json"):
    mac_table = get_device_info(file_path=file_path)
    if mac_table is None: return mac_addr

    if mac_addr in mac_table.keys():
        return mac_table[mac_addr]
    else:
        return mac_addr
    
def combine_zips(src_path_list, output_zip_path):
    with zipfile.ZipFile(output_zip_path, 'w') as output_zip:
        def copy_from(zip_path, subfolder_name):
            with zipfile.ZipFile(zip_path, 'r') as src_zip:
                for file_info in src_zip.infolist():
                    if file_info.is_dir(): continue
                    new_path = os.path.join(subfolder_name, file_info.filename)                    
                    with src_zip.open(file_info) as src_file:
                        output_zip.writestr(new_path, src_file.read())
        
        for zip_path in src_path_list: copy_from(zip_path, os.path.basename(zip_path).replace('.zip', ''))


def get_available_files(src_path, src_path_grp):
    # merge input directories
    print(src_path, src_path_grp)
    if src_path not in src_path_grp and src_path != '' and src_path: src_path_grp.append(src_path) 
    print('=====', src_path_grp)

    # file_info = {}
    file_info = []
    all_encoding = set() 

    for i, src_path in enumerate(src_path_grp):
        file_list = sorted(glob(os.path.join(src_path, '*.bin')))
        # print(file_list)

        for f in file_list:
            f = os.path.basename(f)
            if 'ac' in f:
                match = re.match(r'(?:(\d+))?ac(\d+)\.bin$', f)
                if match:
                    encoding = match.group(1)  # can be None
                    timestamp = int(match.group(2))

                    # Convert to local time
                    dt = datetime.fromtimestamp(timestamp)
                    timestamp = dt.strftime('%m/%d/%y')

                    # quick way to determine encoding technique
                    if int(encoding) > 32000:
                        sub = encoding[:-2]
                        ses = encoding[-2:]
                        print(f"sub={sub}, ses={ses}")
                        alias = f"sub-{sub}, ses-{ses} ({timestamp})"
                    else:
                        alias = f"{encoding} ({timestamp})"

                    if encoding not in all_encoding:
                        all_encoding.add(encoding)

                    # file_info[alias] = encoding
                    file_info.append((alias, encoding))

            # info = f"Enc={encoding}, Date={timestamp}, {f}"
            # print(number1, number2)
            # print(info)
    return gr.CheckboxGroup(file_info)
            
            


def get_msense_files(src_path, src_path_grp, label):
    # if label == "":
    #     gr.Warning("Wristband name cannot be empty")
    #     return "", gr.DownloadButton("No file to be downloaded", interactive=False)

    if src_path not in src_path_grp: src_path_grp.append(src_path) 

    zip_path_list = []
    for i, src_path in enumerate(src_path_grp):
        gr.Info(f"Start file extraction {i+1} / {len(src_path_grp)}...")

        progress = gr.Progress()

        file_list = glob(os.path.join(src_path, '*.bin'))
        print(file_list)

        uuid_list = glob(os.path.join(src_path, '*.txt'))

        print(uuid_list)
        file_list.extend(uuid_list)

        progress(0, desc=f"Start copying {len(file_list)} files for drive {i+1} / {len(src_path_grp)}...")

        dst_dir = tempfile.gettempdir()
        dst_files = []

        mac_addr = f"dev-{time.strftime("%y%m%d%H%M")}"
        try:
            counter = 1
            for f in progress.tqdm(file_list, desc=f"copying data {i+1} / {len(src_path_grp)}... consider getting a coffee..."):
                dst_path = os.path.join(dst_dir, os.path.basename(f))
                shutil.copy(f, dst_path)
                dst_files.append(dst_path)
                counter += 1

                if dst_path.endswith('.txt'):
                    mac_pattern = r'(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}'
                    with open(dst_path, 'r') as file:
                        content = file.read()
                        mac_addr = re.findall(mac_pattern, content)
                        if len(mac_addr) > 0: mac_addr = mac_addr[0]

            # try looking up dev name
            dev_name = look_up_device_name(mac_addr).replace(":", "-")
            
            zip_name = f"{dev_name}{label}.zip"
            zip_path = create_zip(zip_name, dst_files)
            zip_path_list.append(zip_path)
            
        except Exception as e:
            gr.Error(str(e))
            return str(e), gr.DownloadButton("No file to be downloaded", interactive=False)
        
    combined_zip_path = os.path.join(tempfile.gettempdir(), f"{time.strftime("%y%m%d%H%M")}_msense.zip")
    combine_zips(zip_path_list, combined_zip_path)
    
    gr.Info(f"File ready")
    return f"Successfully extracted {len(file_list)} to {os.path.basename(zip_path)}", gr.DownloadButton(label="🎉Download data", value=combined_zip_path, interactive=True)

def download_selected_files(session_table):
    print(session_table)


def file_extractor_interface():
    with gr.Row():
        msense_group = gr.CheckboxGroup(label="📁 MotionSenSE path")
        msense_path = gr.Dropdown(label="📁 Custom MotionSenSE path", allow_custom_value=True)
        refreash_path_btn = gr.Button("🔄 Refresh / Start over")

    file_explorer_btn = gr.Button("Browse data")

    session_table = gr.CheckboxGroup(label="Available session")

    file_explorer_btn.click(get_available_files, 
                            inputs=[msense_path, msense_group],
                            outputs=session_table)

    download_btn2 = gr.Button("Get selected sessions")

    download_btn2.click(download_selected_files, inputs=session_table)


    label = gr.Text("", label="(Optional) Note", visible=False)
    
    extract_btn = gr.Button("Get Files 📂")
    confirm_btn = gr.Button("", visible=False)

    info_panel = gr.Text(label='Status')

    download_btn = default_refresh_btn()

    extract_btn.click(prompt_device_name, outputs=[label, confirm_btn, extract_btn])

    confirm_btn.click(get_msense_files, inputs=[msense_path, msense_group, label], outputs=[info_panel, download_btn])
    refreash_path_btn.click(interface_refresh_reset, outputs=[msense_path, msense_group, download_btn,
                                                       label,
                                                       extract_btn,
                                                       confirm_btn])

def prompt_device_name():
    return gr.Text("", label="(Optional) Note", visible=True), gr.Button("Confirm name & Start 🪪", visible=True), gr.Button("Get Files 📂", visible=False)

def default_refresh_btn():
    return gr.DownloadButton("No file to be downloaded", interactive=False)