import gradio as gr
from glob import glob
import os
import shutil
from tqdm import tqdm 

def get_msense_files(src_path, dst_path):
    file_list = glob(os.path.join(src_path, '*.bin'))
    print(file_list)

    try:
        os.makedirs(dst_path, exist_ok=True)
        for f in tqdm(file_list):
            shutil.copy(f, os.path.join(dst_path, os.path.basename(f)))
        return f"Successfully extracted {len(file_list)} to directory {dst_path}"
    except Exception as e:
        return str(e)

def file_extractor_interface():
    with gr.Column():
        msense_path = gr.Text("F:\\", label="MotionSenSE path")
        dst_path = gr.Text("data", label="Target path")
        extract_btn = gr.Button("Get Files")

        info_panel = gr.Text()

    extract_btn.click(get_msense_files, inputs=[msense_path, dst_path], outputs=info_panel)
