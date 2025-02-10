import gradio as gr
from bleak import BleakScanner
import asyncio

device_info = {}

async def bleak_scan(filter_key):
    global device_info
    devices = await BleakScanner.discover()
    for d in devices:
        # print(dir(d))
        # print(d.name, d.address)
        name = f"{d.name}"
        addr = f"{d.address}"

        if filter_key in name:
            device_info[f"{addr} - {name}"] = addr

    print(device_info)


def search_bt_devices(filter_key):
    global device_info
    asyncio.run(bleak_scan(filter_key))
    return gr.CheckboxGroup(choices=list(device_info.keys()), 
                            value=list(device_info.keys()))


def connect_devices(devices):
    print(devices)  # TODO
    gr.Warning("Not implemented ⛔️!", duration=5)


def bt_scanner_interface():
    text = gr.Text("MSense", label="Device filter")
    bt_search = gr.Button("Search Bluetooth devices ⌚")

    available_devices = gr.CheckboxGroup()

    bt_search.click(search_bt_devices, inputs=text, outputs=available_devices)

    bt_connect = gr.Button("Connect selected devices ☑️")

    bt_connect.click(connect_devices, inputs=available_devices)


