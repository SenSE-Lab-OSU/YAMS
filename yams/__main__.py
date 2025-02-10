import gradio as gr
from yams.uuid_extractor import uuid_extractor_interface
from yams.bt_scanner import bt_scanner_interface
from yams.file_extractor import file_extractor_interface

if __name__ == '__main__':
    with gr.Blocks(title="YAMS") as demo:
        with gr.Tab("📂 File extractor"):
            file_extractor_interface()
        with gr.Tab("📋 UUID extractor"):
            uuid_extractor_interface()
        with gr.Tab("📡 Bluetooth scanner"):
            bt_scanner_interface()         

        gr.Markdown(
            "[YAMS](https://github.com/SenSE-Lab-OSU/YAMS): Yet Another MotionSenSE Service utility",
            elem_id="footer"
        )
    demo.launch()