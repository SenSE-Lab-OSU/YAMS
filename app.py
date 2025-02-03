import gradio as gr
from uuid_extractor import uuid_extractor_interface
from bt_scanner import bt_scanner_interface

if __name__ == '__main__':
    with gr.Blocks() as demo:
        with gr.Tab("UUID extractor"):
            uuid_extractor_interface()
        with gr.Tab("Bluetooth scanner"):
            bt_scanner_interface()

    demo.launch()