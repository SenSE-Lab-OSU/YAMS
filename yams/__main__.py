import gradio as gr
from yams.uuid_extractor import uuid_extractor_interface, device_manager_interface
from yams.bt_scanner import bt_scanner_interface
from yams.file_extractor import file_extractor_interface
from yams.data_explorer import DataExplorer
from yams.data_extraction import data_extraction_interface
from yams.msense_collector import MsenseController

def main():
    with gr.Blocks(title="YAMS") as demo:
        with gr.Tab("⌚️ MotionSenSE controller"):
            m = MsenseController()
            m.interface()
        with gr.Tab("📂 File downloader"):
            file_extractor_interface()
        with gr.Tab("📋 UUID extractor"):
            uuid_extractor_interface()
        # with gr.Tab("📡 Bluetooth scanner"):
        #     bt_scanner_interface()       
        with gr.Tab("📊 Data viewer"):
            data_explorer = DataExplorer()
            data_explorer.interface()
        with gr.Tab("🛠️ Data extractor"):
            data_extraction_interface()
        with gr.Tab("📒 Device manager"):
            device_manager_interface()
        

        gr.Markdown(
            "[YAMS](https://github.com/SenSE-Lab-OSU/YAMS): Yet Another MotionSenSE Service utility",
            elem_id="footer"
        )

    demo.queue()
    demo.launch(inbrowser=True)
    

if __name__ == '__main__':
    main()