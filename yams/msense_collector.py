import gradio as gr
import asyncio
import json
import simplepyble
import datetime
import time
import struct
from functools import partial
from apscheduler.schedulers.background import BackgroundScheduler
import hashlib
# from yams.bt_scanner import get

class MsenseController():
    def __init__(self):
        self.auto_reconnect = True
        self.devices = {}
        self.device_name = self.get_dev_dict()
        self.init_adapter()
        self.active_devices = {}

        self.scheduler = BackgroundScheduler()


    def get_dev_dict(self):
        try:
            with open("device_info.json", 'r') as file:
                device_name = json.load(file)
                device_name = {value: key for key, value in device_name.items()}
        except:
            device_name = {}
        return device_name

    def init_adapter(self):
        adapters = simplepyble.Adapter.get_adapters()
        assert len(adapters) > 0, "No BT adapter found"
        
        self.adapter = adapters[0]
        print(f"Selected adapter: {self.adapter.identifier()} [{self.adapter.address()}]")

    def get_available_devices_checkbox(self, filter_name="MSense"):
        self.scan_devices(filter_name=filter_name)
        return gr.CheckboxGroup(choices=list(self.devices.keys()), 
                                value=list(self.devices.keys()),
                                label="Available devices")

    def scan_devices(self, filter_name="MSense"):
        print("start scanning devices")
        self.adapter.scan_for(5000)
        peripherals = self.adapter.scan_get_results()

        self.devices = {}
        for i, peripheral in enumerate(peripherals):
            if filter_name in peripheral.identifier():
                print(f"{i}: {peripheral.identifier()} [{peripheral.address()}]")
                # try to look up device alias
                if peripheral.identifier() in self.device_name.keys():
                    alias = self.device_name[peripheral.identifier()]
                    name = f"{peripheral.identifier()} ({alias}) [{peripheral.address()}]"
                else:
                    name = f"{peripheral.identifier()} [{peripheral.address()}]"

                self.devices[name] = peripheral


    def connect_devices(self, names):
        del(self.active_devices)
        self.active_devices = {}

        self.log(f"Start connecting to devices: {names}")
        for n in names:
            print(f'==== {n}')
            p = self.devices[n]
            print(f"=== {p.identifier()} at {p.address()}")
            p.set_callback_on_connected(lambda: print(f"{self.tic()}: [INFO] {p.identifier()} is connected"))
            p.set_callback_on_disconnected(lambda: print(f"{self.tic()}: [INFO] {p.identifier()} is disconnected"))
            p.connect()
            self.active_devices[n] = p

    def disconnect_all(self):
        for dev in self.active_devices.values():
            try:
                dev.disconnect()
            except Exception as e:
                print(str(e))

    def tic(self):
        return datetime.datetime.now()
    
    def log(self, msg):
        print(f"{self.tic()}: {msg}")

    def interface(self):
        with gr.Row():
            text = gr.Text("MSense", label="Device filter", scale=2)
            bt_search = gr.Button("Search Bluetooth devices 📱")

        with gr.Row():
            with gr.Column(scale=4):
                available_devices = gr.CheckboxGroup(label="Available devices")
            with gr.Column():
                bt_connect = gr.Button("Connect selected")
                btn_disconnect = gr.Button("Disconnect")

        bt_search.click(self.get_available_devices_checkbox, inputs=[text], outputs=available_devices)    
        bt_connect.click(self.connect_devices, inputs=available_devices)            
        btn_disconnect.click(self.disconnect_all)

        with gr.Accordion(label="Device control", open=True):
            default_sub = "sub-Test"
            default_ses = "sub-00"

            with gr.Row():
                sub_name = gr.Text(default_sub, label="Subject ID")
                ses_name = gr.Text(default_ses, label="Session ID")
                subject_enc = gr.Number(self.get_participant_encoding(default_sub, default_ses), label='Participant encoding (Read-only)', interactive=False)
                sub_name.change(self.get_participant_encoding, inputs=[sub_name, ses_name], outputs=subject_enc)
                ses_name.change(self.get_participant_encoding, inputs=[sub_name, ses_name], outputs=subject_enc)
        
            with gr.Row():
                btn_start = gr.Button("Start▶️")
                btn_stop = gr.Button("Stop🛑")
                btn_start.click(self.start_collection)
                btn_stop.click(self.end_collection)

        with gr.Accordion(label="Advanced options", open=True):
            btn_reconnect = gr.Button("Reconnect")
            btn_reconnect.click(self.reconnect)

            btn_service = gr.Button("Get available services")
            btn_service.click(self.get_selected_device_services, inputs=available_devices)
            with gr.Row():
                btn_monitor_start = gr.Button("Start device monitor")
                btn_monitor_stop = gr.Button("Stop device monitor")

                btn_monitor_start.click(self.start_device_monitor)
                btn_monitor_stop.click(self.stop_device_monitor)

    def start_collection(self):
        for name, p in self.active_devices.items():
            print(name, p.is_connected(), p.is_connectable())
            self.collection_ctl(p, True)

    def end_collection(self):
        for name, p in self.active_devices.items():
            print(name, p.is_connected(), p.is_connectable())
            self.collection_ctl(p, False)
    
    def collection_ctl(self, peripheral, start=True):
        # if starting, do the initialization
        if start:
            # write unix time

            print("==== writing", int(time.time()), time.time())
            peripheral.write_request("da39c930-1d81-48e2-9c68-d0ae4bbd351f", 
                                     "da39c932-1d81-48e2-9c68-d0ae4bbd351f", 
                                     struct.pack("<Q", int(time.time())))
            # write participant hash
            peripheral.write_request("da39c930-1d81-48e2-9c68-d0ae4bbd351f",
                                     "da39c933-1d81-48e2-9c68-d0ae4bbd351f", 
                                     self.participant_byte)

        service_uuid = "da39c930-1d81-48e2-9c68-d0ae4bbd351f"
        characteristic_uuid = "da39c931-1d81-48e2-9c68-d0ae4bbd351f"
        peripheral.write_request(service_uuid, characteristic_uuid, struct.pack("<I", int(start)))

        # ENMO 
        service_uuid = "da39c950-1d81-48e2-9c68-d0ae4bbd351f"
        characteristic_uuid = "da39c951-1d81-48e2-9c68-d0ae4bbd351f"
        contents = peripheral.notify(service_uuid, characteristic_uuid, lambda data: self.enmo_handler(data, peripheral))

    def enmo_handler(self, data, peripheral):
        print(peripheral.identifier(), data)
        packet_counter = data[4:6]
        ENMO = struct.unpack("<f", data[0:4])
        
        packet_counter = struct.unpack("<H", packet_counter)
        horizontal_array = [ENMO[0], packet_counter[0]]
        print("package counter", str(horizontal_array))

    def get_selected_device_services(self, names):
        for n in names:
            p = self.devices[n]
            print(f'======== Services of device {n}')
            self.get_services(p)

    def get_services(self, peripheral):
        services = peripheral.services()
        service_characteristic_pair = []
        for service in services:
            for characteristic in service.characteristics():
                service_characteristic_pair.append((service.uuid(), characteristic.uuid()))

        for i, (service_uuid, characteristic) in enumerate(service_characteristic_pair):
            print(f"{i}: {service_uuid} {characteristic}")

    def reconnect(self):
        for name, p in self.active_devices.items():
            print(f"{name} {p.identifier()} connection status = {p.is_connected()}")
            if not p.is_connected():
                try:
                    p.connect()
                except Exception as e:
                    print(str(e))

    ######
    def check_and_reconnect_devices(self):
        for device in self.active_devices.values():
            try:
                if not device.is_connected():
                    print(f"[INFO] {device.identifier()} disconnected. Attempting to reconnect...")
                    device.connect()
                    if device.is_connected():
                        print(f"[INFO] Reconnected to {device.identifier()}")
                    else:
                        print(f"[WARN] Failed to reconnect to {device.identifier()}")
                else:
                    print(f"[OK] {device.identifier()} is still connected.")
            except Exception as e:
                print(f"[ERROR] Error checking device {device.identifier()}: {e}")

    def start_device_monitor(self, interval_seconds=10):
        if not self.scheduler.running:
            self.scheduler.start()
        if not self.scheduler.get_job("device_monitor"):
            self.scheduler.add_job(self.check_and_reconnect_devices, "interval", seconds=interval_seconds, id="device_monitor")
            print("[INFO] Started device monitor job.")

    def stop_device_monitor(self):
        job = self.scheduler.get_job("device_monitor")
        if job:
            job.remove()
            print("[INFO] Stopped device monitor job.")

    def get_participant_encoding(self, sub, ses):
        name = f"{sub}-{ses}"
        hash_object = hashlib.sha256(name.encode())
        hex_digest = hash_object.hexdigest()
        integer_representation = int(hex_digest, 16) % 32000
        print(name, integer_representation)
        self.participant_byte = struct.pack("<I", integer_representation)
        return integer_representation


if __name__ == "__main__":
    adapters = simplepyble.Adapter.get_adapters()

    if len(adapters) == 0:
        print("No adapters found")

    # Query the user to pick an adapter
    print("Please select an adapter:")
    for i, adapter in enumerate(adapters):
        print(f"{i}: {adapter.identifier()} [{adapter.address()}]")

    choice = int(input("Enter choice: "))
    adapter = adapters[choice]

    print(f"Selected adapter: {adapter.identifier()} [{adapter.address()}]")

    adapter.set_callback_on_scan_start(lambda: print("Scan started."))
    adapter.set_callback_on_scan_stop(lambda: print("Scan complete."))
    adapter.set_callback_on_scan_found(lambda peripheral: print(f"Found {peripheral.identifier()} [{peripheral.address()}]"))

    # Scan for 5 seconds
    adapter.scan_for(5000)
    peripherals = adapter.scan_get_results()

    # Query the user to pick a peripheral
    print("Please select a peripheral:")
    for i, peripheral in enumerate(peripherals):
        print(f"{i}: {peripheral.identifier()} [{peripheral.address()}]")

    choice = int(input("Enter choice: "))
    peripheral = peripherals[choice]

    print(f"Connecting to: {peripheral.identifier()} [{peripheral.address()}]")
    peripheral.connect()

    print("Successfully connected, listing services...")
    services = peripheral.services()
    for service in services:
        print(f"Service: {service.uuid()}")
        for characteristic in service.characteristics():
            print(f"    Characteristic: {characteristic.uuid()}")

            capabilities = " ".join(characteristic.capabilities())
            print(f"    Capabilities: {capabilities}")

    peripheral.disconnect()