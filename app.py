import gradio as gr
from uuid_extractor import uuid_extractor_interface
from bt_scanner import bt_scanner_interface
from file_extractor import file_extractor_interface

if __name__ == '__main__':
    with gr.Blocks() as demo:
        with gr.Tab("UUID extractor"):
            uuid_extractor_interface()
        with gr.Tab("Bluetooth scanner"):
            bt_scanner_interface()
        with gr.Tab("File extractor"):
            file_extractor_interface()

    demo.launch()