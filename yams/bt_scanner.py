import gradio as gr
from bleak import BleakScanner
import asyncio
from bleak import BleakClient
import struct
from yams.bluetooth_device import characteristic_bat, get_device_status
from apscheduler.schedulers.background import BackgroundScheduler


device_info = {}
dev_status = {}

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
                            value=list(device_info.keys()),
                            label="Available devices")


def get_dev_status(devices):
    info = {}
    # print(info)

    scheduler = BackgroundScheduler()
    scheduler.add_job(get_dev_status_job, "interval", seconds=10, args=[devices]) 
    scheduler.start()

    return gr.Button("update status", interactive=True)

def get_dev_status_job(devices):
    global dev_status
    info = {}

    try:
        for dev in devices:
            info[dev] = asyncio.run(get_device_status(device_info[dev]))
        print(info)
        dev_status = info
    except Exception as e:
        print(str(e))


async def erase_dev(addr):
    rst_char = "da39c934-1d81-48e2-9c68-d0ae4bbd351f"
    try:
        async with BleakClient(addr) as client:
            gr.Info(f"Erasing {client.address}")
            value = struct.pack("<I", int(68))
            await client.write_gatt_char(rst_char, value)
    except Exception as e:
        print(str(e))
        gr.Error(f"⚠️{str(e)}")

async def write_dev(addr, val, characteristics="da39c931-1d81-48e2-9c68-d0ae4bbd351f"):
    try:
        async with BleakClient(addr) as client:
            gr.Info(f"collection control {client.address} {val}")
            value = struct.pack("<I", int(val))
            await client.write_gatt_char(characteristics, value)
    except Exception as e:
        print(str(e))
        gr.Error(f"⚠️{str(e)}")


async def get_dev(addr, key):
    info = {addr: 'null'}
    try:
        async with BleakClient(addr) as client:
            value = await client.read_gatt_char(key)
            info[addr] = value
    except Exception as e:
        print(str(e))
        gr.Error(f"⚠️{str(e)}")

    return info


def erase_flash_data(available_devices):
    gr.Info("Erasing flash data...")

    print(available_devices)
    for k in available_devices:
        asyncio.run(erase_dev(device_info[k]))
        
    return gr.Number(value=None, label="Erase code"), gr.Checkbox(label="Enable erase feature", value=False), gr.Button("Erase flash data", interactive=False)


def update_status():
    global dev_status
    print(dev_status)
    return gr.JSON(dev_status, visible=True)


def bt_scanner_interface():
    text = gr.Text("MSense", label="Device filter", scale=2)

    bt_search = gr.Button("Search Bluetooth devices 📱")

    with gr.Row():
        available_devices = gr.CheckboxGroup(label="Available devices")
        with gr.Column():
            bt_status = gr.Button("(Experimental) Get device status ✅")
            bt_update_status = gr.Button("(Experimental) Update status", interactive=False)

    dev_panel = gr.JSON(visible=False)
    
    bt_search.click(search_bt_devices, inputs=[text], outputs=available_devices)    
    bt_status.click(get_dev_status, inputs=available_devices, outputs=bt_update_status)
    bt_update_status.click(update_status, outputs=dev_panel)
    

    with gr.Accordion(label="Device control", open=True):
        # conect_btn = gr.Button("Connect selected", interactive=False)
        # memo_page = gr.Text(label="Status memo")

        with gr.Row():
            start_btn = gr.Button("Start▶️")
            stop_btn = gr.Button("Stop🛑")

        start_btn.click(collection_ctl_start, inputs=[available_devices])
        stop_btn.click(collection_ctl_stop, inputs=[available_devices])
        

    # erase control
    with gr.Accordion(label="🚨🚨🚨Danger zone🚨🚨🚨", open=False):
        erase_passcode = gr.Number(label="Erase code")
        erase_enable = gr.Checkbox(label="Enable erase feature")
        
        erase_btn = gr.Button("Erase flash data", interactive=False)
        erase_btn.click(erase_flash_data, inputs=[available_devices],
                        outputs=[erase_passcode, erase_enable, erase_btn])

        erase_enable.change(set_erase_feature, inputs=[erase_enable, erase_passcode], outputs=[erase_btn])

def collection_ctl_start(devices):
    gr.Info("Collection control starting... 🦭")
    collection_ctl(devices, True)
    gr.Info("✅✅✅ All done ✅✅✅")

def collection_ctl_stop(devices):
    gr.Info("Collection control stoping... 🛑")
    collection_ctl(devices, False)
    gr.Info("✅✅✅ All done ✅✅✅")

def collection_ctl(devices, start_collect):
    if start_collect:
        val = 1
    else:
        val = 0

    for k in devices:
        asyncio.run(write_dev(device_info[k], val))

def set_erase_feature(erase_enable, erase_passcode):
    if erase_enable:
        if erase_passcode == 68:
            gr.Warning("Erase feature is enabled!")
            return gr.Button("Erase flash data", interactive=True)
        else:
            gr.Warning("Incorrect password")
            return gr.Button("Erase flash data", interactive=False)
    else:
        gr.Info("Erase feature disabled")
        return gr.Button("Erase flash data", interactive=False)


