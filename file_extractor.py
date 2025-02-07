import gradio as gr
from glob import glob
import os
import shutil
from tqdm import tqdm 
import time

def get_msense_files(src_path, dst_path):
    progress = gr.Progress()

    file_list = glob(os.path.join(src_path, '*.bin'))
    print(file_list)

    uuid_list = glob(os.path.join(src_path, '*.txt'))

    print(uuid_list)
    file_list.extend(uuid_list)

    progress(0, desc=f"Start copying {len(file_list)} files...")

    try:
        os.makedirs(dst_path, exist_ok=True)
        counter = 1
        for f in progress.tqdm(file_list, desc="copying data... consider getting a coffee..."):
            # yield f"({counter}/{len(file_list)}) moving {f}..."
            shutil.copy(f, os.path.join(dst_path, os.path.basename(f)))
            counter += 1
        time.sleep(1)
        return f"Successfully extracted {len(file_list)} to directory {dst_path}"
    except Exception as e:
        return str(e)

def file_extractor_interface():
    with gr.Column():
        msense_path = gr.Text("F:\\", label="MotionSenSE path")
        dst_path = gr.Text("data", label="Target path")
        extract_btn = gr.Button("Get Files")

        info_panel = gr.Text(label='Status')

    extract_btn.click(get_msense_files, inputs=[msense_path, dst_path], outputs=info_panel)
