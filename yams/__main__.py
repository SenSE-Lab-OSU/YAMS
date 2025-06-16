import gradio as gr
from yams.uuid_extractor import uuid_extractor_interface, device_manager_interface
from yams.bt_scanner import bt_scanner_interface
from yams.file_extractor import FileDownloader
from yams.data_explorer import DataExplorer
from yams.data_extraction import data_extraction_interface, data_extraction_pro_interface
from yams.msense_collector import MsenseController, session_manager_interface
from yams.config import __version__

def main():
    with gr.Blocks(title="YAMS") as demo:
        with gr.Tab("⌚️ MotionSenSE controller"):
            m = MsenseController()
            m.interface()
        with gr.Tab("📂 File downloader"):
            d = FileDownloader()
            d.interface()
        with gr.Tab("📋 UUID extractor"):
            uuid_extractor_interface()
        # with gr.Tab("📡 Bluetooth scanner"):
        #     bt_scanner_interface()       
        with gr.Tab("📊 Data viewer"):
            data_explorer = DataExplorer()
            data_explorer.interface()
        with gr.Tab("🛠️ Data extractor"):
            data_extraction_interface()
        with gr.Tab("🛠️ Data extractor pro"):
            data_extraction_pro_interface()
        with gr.Tab("📒 Extensions"):
            with gr.Accordion(label="📒 Device manager"):
                device_manager_interface()
            with gr.Accordion(label="📊 Session manager"):
                session_manager_interface()
        

        gr.Markdown(
            f"[YAMS](https://github.com/SenSE-Lab-OSU/YAMS) v{__version__}: Yet Another MotionSenSE Service utility",
            elem_id="footer"
        )

    demo.queue()
    demo.launch(inbrowser=True)
    

if __name__ == '__main__':
    main()