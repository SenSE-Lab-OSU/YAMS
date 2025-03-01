from bleak import BleakClient
import asyncio
import struct
import gradio as gr

characteristic_bat = "2A19"
characteristic_model = "2A24"
characteristic_collection = "da39c931-1d81-48e2-9c68-d0ae4bbd351f"

async def get_battery_status(addr):
    async with BleakClient(addr) as client:
        value = await client.read_gatt_char(characteristic_bat)
    return value

async def get_device_status(addr):
    info = {}
    async with BleakClient(addr) as client:
        # battery
        bat = await client.read_gatt_char(characteristic_bat)
        bat = str(bat[0])
        info['battery'] = bat

        # model number
        model = await client.read_gatt_char(characteristic_model)
        info['model'] = model.decode('utf-8')

        # record status
        status = await client.read_gatt_char(characteristic_collection)
        info['status'] = str(status[0])

    return info

def status_updater():
    import random
    return f"this is a random {random.random()}"

if __name__ == '__main__':
    addr = "F1:A9:8C:25:AD:1E"

    # a = asyncio.run(get_device_status(addr))
    # print(a)

    with gr.Blocks() as demo:
        memo = gr.Text("info will be displayed here")
        demo.load(fn=status_updater, inputs=None, outputs=memo)

    demo.queue().launch()

