# %%
import gradio as gr
from glob import glob
import os
import re
import json
import tempfile
from yams.file_extractor import get_flash_drives

device_info = {}


def device_manager_interface():
    file_path = "device_info.json"
    txt = gr.Text(file_path, label="Device info")

    if not os.path.exists(file_path):
        with open(file_path, "w") as f: json.dump({}, f)

    with open(file_path, "r") as f:
        device_info = json.load(f)
    
    info = gr.JSON(device_info, label="Device info")

    read_btn = gr.Button(f"Read {file_path}")
    write_btn = gr.Button(f"Save {file_path}")

    read_btn.click(read_device_info, inputs=txt, outputs=info)
    write_btn.click(write_device_info, inputs=[txt, info])

def read_device_info(file_path):
    with open(file_path, "r") as f:
        device_info = json.load(f)
    return device_info

def write_device_info(file_path, device_info):
    with open(file_path, "w") as f:
        json.dump(device_info, f, indent=4)


def get_uuid_from_path(target_path):
    file_list = glob(os.path.join(target_path, 'uuid.txt'))

    if len(file_list) > 0:
        with open(file_list[0], 'r') as f:
            txt = f.read()

            mac_pattern = r'([0-9A-Fa-f]{2}[:]){5}([0-9A-Fa-f]{2})'
            match = re.search(mac_pattern, txt)

            try:
                print("found mac addr", match.group(0))
                return match.group(0)
            except Exception as e:
                return str(e)
    else:
        return "No MotionSenSE found. Plug in or change MotionSenSE path?"
    

def save_device_info(output_path):
    global device_info
    output_path = os.path.join(tempfile.gettempdir(), os.path.basename(output_path))
    with open(output_path, "w") as f:
        json.dump(device_info, f, indent=4)
    return gr.DownloadButton(label=f"Download {os.path.basename(output_path)}", value=output_path)


def add_device_info(serial, uuid):
    global device_info
    device_info[serial] = uuid
    return device_info


def reset_device_info():
    global device_info
    device_info = {}
    return device_info

def update_download(output_name):
    global device_info
    return save_device_info(output_name)


def get_attached_drive():
    dropdown, _ = get_flash_drives()
    return dropdown

def uuid_extractor_interface():
    with gr.Column():
        with gr.Row():
            msense_path = gr.Dropdown(label="📁 MotionSenSE path", allow_custom_value=True)
            refreash_path_btn = gr.Button("🔄 Refresh")
            refreash_path_btn.click(get_attached_drive, outputs=msense_path)
        extract_btn = gr.Button("🔧 Get UUID")

    with gr.Column():
        uuid_field = gr.Text("UUID will be shown here", label="UUID")
        msense_serial = gr.Text("4ANA002", label="Serial number")
        add_btn = gr.Button("📝 Add uuid-serial pair")

    with gr.Row():
        device_info_preview = gr.JSON(device_info, label="Device info")
        json_reset_btn = gr.Button("🚮 Clear device info")

    with gr.Row():
        output_name = gr.Text("device_info.json", label="Output file name")
        save_btn = gr.DownloadButton("💾 Save device info")

    extract_btn.click(get_uuid_from_path, inputs=msense_path, outputs=uuid_field)
    add_btn.click(add_device_info, inputs=[msense_serial, uuid_field], outputs=device_info_preview)
    save_btn.click(save_device_info, inputs=output_name, outputs=save_btn)
    json_reset_btn.click(reset_device_info, outputs=device_info_preview)

    device_info_preview.change(update_download, inputs=output_name, outputs=save_btn)


