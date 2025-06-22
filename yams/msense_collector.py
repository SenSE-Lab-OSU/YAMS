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
from pylsl import StreamInfo, StreamOutlet, cf_double64
import os, sys
import numpy as np
import logging
import re
from yams.config import __version__

yams_dir = "yams-data"

def session_manager_interface():
    sub_list = gr.Text("sub-Test")
    ses_list = gr.Text("ses-Demo")

def participant_encoding_legacy(sub, ses):
    name = f"{sub}_{ses}"

    hash_object = hashlib.sha256(name.encode())
    hex_digest = hash_object.hexdigest()
    integer_representation = int(hex_digest, 16) % 32000
    return integer_representation

def participant_encoding_default(sub, ses):
    sub_number = re.search(r'\d+', sub)
    if sub_number:
        sub_number = sub_number.group()
    else:
        sub_number = 0

    ses_number = re.search(r'\d+', ses)
    if ses_number:
        ses_number = ses_number.group()
    else:
        ses_number = 0

    integer_representation = int(sub_number) * 100 + int(ses_number)
    # print(sub_number, ses_number, integer_representation)

    return integer_representation

class MsenseOutlet(StreamOutlet):
    def __init__(self, name, peripheral, chunk_size=32, max_buffered=360, use_lsl=True):
        self.name = name.replace(':', '-')
        self.use_lsl = use_lsl

        lsl_status = "OK" if self.use_lsl else "disabled"
        self.msg = f"📻 {self.tic()} LSL {lsl_status}. Ready to start..."
        self.msg_fun = f"📻 {self.tic()} LSL {lsl_status}. Ready to start..."

        if self.use_lsl:
            info = StreamInfo(name, "MotionSenSE", 3, 2, cf_double64, peripheral.address())
            super().__init__(info, chunk_size, max_buffered)

        self.log_dir = os.path.join(yams_dir, "default")


    def tic(self):
        now = datetime.datetime.now()
        return now.strftime("%H:%M:%S")

    def save_data(self, data):
        self.log_path = os.path.join(self.log_dir, f"{self.name}.txt")
        # Ensure the file exists
        if not os.path.exists(self.log_path):
            with open(self.log_path, 'w') as f: pass

        # Append NumPy array as a line
        with open(self.log_path, 'a') as f:
            np.savetxt(f, [data], fmt='%s')

    def push_sample(self, x):
        if self.use_lsl:
            formatted = '\t'.join(str(num) for num in x)
            self.msg = f"📻 {self.tic()} last LSL pushed: {formatted}"
            
            fun_msg = "".join(["✅" for i in range(int(time.time())%10)])
            self.msg_fun = f"📻 {self.tic()} {fun_msg}"

            x.append(time.time())
            super().push_sample(x)

        self.save_data(x)

class MsenseController():
    def __init__(self):
        # current YYMMDD
        now = datetime.datetime.now()
        date = now.strftime("%Y-%m-%d")
    
        # init logger
        self.logger = logging.getLogger(__name__)
        os.makedirs(yams_dir, exist_ok=True)
        logging.basicConfig(level=logging.INFO, 
                            format='%(asctime)s [%(levelname)s] %(message)s',
                            handlers=[
                                logging.FileHandler(os.path.join(yams_dir, f"{date}_yams_session.log")),
                                logging.StreamHandler()
                            ])
        self.logger.info(f"Begin YAMS v{__version__} session log")
    
        self.auto_reconnect = True
        self.devices = {}
        self.device_name = self.get_dev_dict()
        self.init_adapter()
        self.active_devices = {}
        self.active_outlets = {}

        self.scheduler = BackgroundScheduler()

        self.update_encoding_mode("Default")

    def get_dev_dict(self):
        try:
            with open("device_info.json", 'r') as file:
                device_name = json.load(file)
                device_name = {value: key for key, value in device_name.items()}
        except:
            device_name = {}

        print(device_name)
        return device_name

    def init_adapter(self):
        adapters = simplepyble.Adapter.get_adapters()
        assert len(adapters) > 0, "No BT adapter found"
        
        self.adapter = adapters[0]
        # print(f"Selected adapter: {self.adapter.identifier()} [{self.adapter.address()}]")
        self.logger.info(f"Selected adapter: {self.adapter.identifier()} [{self.adapter.address()}]")

    def get_available_devices_checkbox(self, filter_name="MSense"):
        self.scan_devices(filter_name=filter_name)
        return gr.CheckboxGroup(choices=list(self.devices.keys()), 
                                value=list(self.devices.keys()),
                                label="Available devices")

    def scan_devices(self, filter_name="MSense"):
        print("start scanning devices")
        self.logger.info("start device scanning")
        self.ctl_state = "Start device scanning"
        self.adapter.scan_for(5000)
        peripherals = self.adapter.scan_get_results()

        self.devices = {}
        for i, peripheral in enumerate(peripherals):
            if filter_name in peripheral.identifier():
                self.logger.info(f"{i}: {peripheral.identifier()} [{peripheral.address()}]")
                # try to look up device alias
                addr = peripheral.address().upper()
                if addr in self.device_name.keys():
                    alias = self.device_name[addr]
                    name = f"{alias} ({peripheral.identifier()}) [{peripheral.address()}]"
                else:
                    name = f"{peripheral.identifier()} [{peripheral.address()}]"

                self.devices[name] = peripheral

        self.ctl_state = "Device scanning completed"

    def connect_devices(self, names):
        del(self.active_devices)
        self.active_devices = {}
        del(self.active_outlets)
        self.active_outlets = {}
        self.ctl_state = "Start device connection"

        self.logger.info(f"Start connecting to devices: {names}")
        for n in names:
            gr.Info(f"Connecting to devices: {n}")
            print(f'==== {n}')
            p = self.devices[n]
            print(f"=== {p.identifier()} at {p.address()}")
            p.set_callback_on_connected(lambda: self.logger.info(f"{n} {p.identifier()} is connected"))
            p.set_callback_on_disconnected(lambda: self.logger.info(f"{n} {p.identifier()} is disconnected"))
            p.connect()
            self.active_devices[n] = p
            self.active_outlets[n] = MsenseOutlet(n, p, use_lsl=self.use_lsl)

        self.ctl_state = "Device(s) connected"

    def disconnect_all(self):
        self.ctl_state = "Start device disconnection"
        for dev in self.active_devices.values():
            try:
                dev.disconnect()
            except Exception as e:
                print(str(e))
        gr.Warning(f"All devices disconnected")
        self.logger.info("All devices disconnected")
        self.ctl_state = "Device(s) disconnected"

    def tic(self):
        return datetime.datetime.now()
    
    def log(self, msg):
        print(f"{self.tic()}: {msg}")

    def interface(self):
        with gr.Accordion("Initialization"):
            bt_search = gr.Button("Search Bluetooth devices 📱")
            available_devices = gr.CheckboxGroup(label="Available devices", scale=6)
            with gr.Row():
                bt_connect = gr.Button("✅ Connect selected")
                btn_disconnect = gr.Button("❌ Disconnect")

        
        bt_connect.click(self.connect_devices, inputs=available_devices)            
        btn_disconnect.click(self.disconnect_all)

        with gr.Accordion(label="Device control", open=True):
            default_sub = "sub-1000"
            default_ses = "ses-00"

            with gr.Row():
                sub_name = gr.Text(default_sub, label="Subject ID", info="Format: sub-XXXX, X is integer")
                ses_name = gr.Text(default_ses, label="Session ID", info="Format: ses-YY, Y is integer")
                subject_enc = gr.Number(self.get_participant_encoding(default_sub, default_ses), label='Participant encoding (Read-only)', interactive=False,
                                        info="Format: XXXXYY")
                sub_name.change(self.get_participant_encoding, inputs=[sub_name, ses_name], outputs=subject_enc)
                ses_name.change(self.get_participant_encoding, inputs=[sub_name, ses_name], outputs=subject_enc)
        
            with gr.Row():
                self.btn_start = gr.Button("Start▶️")
                self.btn_stop = gr.Button("Stop🛑")
                                
            self.btn_start.click(self.start_collection)
            self.btn_stop.click(self.end_collection)

        self.params = {}
        self.ctl_state = "Welcome! Press 'Search bluetooth devices' to start"
        params = gr.ParamViewer(self.params)
        timer = gr.Timer(value=1)
        timer.tick(fn=self.update_params, outputs=params)

        # erase control
        with gr.Accordion(label="🚨🚨🚨Danger zone🚨🚨🚨", open=False):
            erase_passcode = gr.Number(label="Erase code")
            erase_enable = gr.Checkbox(label="Enable erase feature")
            
            erase_btn = gr.Button("Erase flash data", interactive=False)
            erase_btn.click(self.erase_flash_data, 
                            outputs=[erase_passcode, erase_enable, erase_btn])

            erase_enable.change(self.set_erase_feature, inputs=[erase_enable, erase_passcode], outputs=[erase_btn])

        with gr.Accordion(label="Advanced options", open=False):
            use_lsl = gr.Checkbox(True, label="Enable LSL")
            self.use_lsl = True
            use_lsl.change(self.update_lsl_setting, inputs=use_lsl)

            text = gr.Text("MSense", label="Device filter", scale=2)

            auto_reconnect = gr.Checkbox(True, label="Auto reconnect")
            auto_reconnect.change(self.set_auto_reconnect, inputs=auto_reconnect)

            btn_reconnect = gr.Button("Reconnect")
            btn_reconnect.click(self.reconnect)

            btn_service = gr.Button("Get available services")
            btn_service.click(self.get_selected_device_services, inputs=available_devices)
            with gr.Row():
                btn_monitor_start = gr.Button("Start device monitor")
                btn_monitor_stop = gr.Button("Stop device monitor")

                btn_monitor_start.click(self.start_device_monitor)
                btn_monitor_stop.click(self.stop_device_monitor)

            with gr.Accordion(label="Participant encoding", open=False):
                with gr.Row():
                    manual_encoding = gr.Number(12345)
                    enc_mode = gr.Radio(["Default", "Legacy (hash-based)"], value="Default", label="Encoding mode")
                with gr.Row():
                    btn_write_enc = gr.Button("write enc")
                    btn_read_enc = gr.Button("read enc")

                enc_mode.change(self.update_encoding_mode, inputs=enc_mode)
                btn_write_enc.click(self.write_enc, inputs=manual_encoding)

        bt_search.click(self.get_available_devices_checkbox, inputs=text, outputs=available_devices)    

    def write_enc(self, enc):
        for name, peripheral in self.active_devices.items():
            peripheral.write_request("da39c930-1d81-48e2-9c68-d0ae4bbd351f",
                                     "da39c933-1d81-48e2-9c68-d0ae4bbd351f", 
                                       struct.pack("<I", int(enc)))
            
            data = peripheral.read("da39c930-1d81-48e2-9c68-d0ae4bbd351f",
                                     "da39c933-1d81-48e2-9c68-d0ae4bbd351f", 
                                    )
            # print(name, data, f"enc = {str(data)}")
            print(name, data, struct.unpack("<I", data))

    def update_encoding_mode(self, enc_mode):
        print(enc_mode)
        if enc_mode == "Legacy (hash-based)":
            self.encode_participant = participant_encoding_legacy
        elif enc_mode == "Default":
            self.encode_participant = participant_encoding_default

    def update_lsl_setting(self, enable):
        self.use_lsl = enable

    def update_params(self):
        self.params = {"Memo": {
            'type': self.ctl_state,
        }}
        for name, device in self.active_devices.items():
            connection_status = "✅ Connected" if device.is_connected() else "🚫 Disconnected"
            try:
                msg_fun = self.active_outlets[name].msg_fun
            except Exception as e:
                msg_fun = "LSL outlet unavailable"

            try:
                msg = self.active_outlets[name].msg
            except Exception as e:
                msg = str(e)

            self.params[name] = {
                'type': f"{connection_status} | {msg_fun}",
                'description': msg
            }

        return self.params

    def set_auto_reconnect(self, status):
        self.auto_reconnect = status

    def start_collection(self):
        timestamp = time.strftime("%y%m%d_%H%M")
        # create log dir
        self.log_dir = os.path.join(yams_dir, 
                                    self.session_info['sub_id'], 
                                    self.session_info['ses_id'], 
                                    f"{self.session_info['participant_enc']}_{timestamp}")
        print(f"create log dir {self.log_dir}")
        os.makedirs(self.log_dir, exist_ok=True)

        gr.Info("▶️ Start data collection...")
        self.logger.info(f"Start data collection with out dir = {self.log_dir}")
        self.logger.info(f"Subject ID = {self.session_info['sub_id']}")
        self.logger.info(f"Session ID = {self.session_info['ses_id']}")
        self.logger.info(f"Participant encoding = {self.session_info['participant_enc']}")

        for name, p in self.active_devices.items():
            print(name, p.is_connected(), p.is_connectable())
            self.collection_ctl(name, True)
            self.active_outlets[name].log_dir = self.log_dir

        self.ctl_state = "Collection in progress"

    def end_collection(self):
        gr.Info("🛑 Stop data collection...")
        self.logger.info("Data collection stopped")
        for name, p in self.active_devices.items():
            print(name, p.is_connected(), p.is_connectable())
            self.collection_ctl(name, False)

        self.ctl_state = "Collection stopped"
    
    def collection_ctl(self, name, start=True):
        peripheral = self.active_devices[name]

        # if starting, do the initialization
        if start:
            # write unix time
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

        self.register_enmo(peripheral, name)

        # 
        if start and self.auto_reconnect:
            self.start_device_monitor()
        elif not start:
            self.stop_device_monitor()
            

    def register_enmo(self, peripheral, name):
        # ENMO 
        service_uuid = "da39c950-1d81-48e2-9c68-d0ae4bbd351f"
        characteristic_uuid = "da39c951-1d81-48e2-9c68-d0ae4bbd351f"
        contents = peripheral.notify(service_uuid, characteristic_uuid, lambda data: self.enmo_handler(data, peripheral, name))

    def get_battery_status(self, names):
        for n in names:
            peripheral = self.devices[n]

            service_uuid = "0000180f-0000-1000-8000-00805f9b34fb"
            characteristic_uuid = "00002a19-0000-1000-8000-00805f9b34fb"
            contents = peripheral.read(service_uuid, characteristic_uuid)
            print(n, f"battery = {str(contents[0])}")

    def enmo_handler(self, data, peripheral, name):
        # print(peripheral.identifier(), data)
        packet_counter = data[4:6]
        ENMO = struct.unpack("<f", data[0:4])
        
        packet_counter = struct.unpack("<H", packet_counter)
        horizontal_array = [ENMO[0], packet_counter[0]]
        print(f"{name}: package counter", horizontal_array)

        self.active_outlets[name].push_sample([ENMO[0], packet_counter[0]])
        

    def get_selected_device_services(self, names):
        for n in names:
            p = self.devices[n]
            print(f'======== Services of device {n}')
            self.get_services(p)
        self.get_battery_status(names)

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
                    self.register_enmo(p, name)
                except Exception as e:
                    print(str(e))

    ######
    def check_and_reconnect_devices(self):
        for name, device in self.active_devices.items():
            try:
                if not device.is_connected():
                    self.logger.warning(f"{name} {device.identifier()} disconnected. Attempting to reconnect..")
                    device.connect()
                    if device.is_connected():
                        self.logger.info(f"Reconnected to {name} {device.identifier()}")
                        self.register_enmo(device, name)
                    else:
                        self.logger.warning(f"Failed to reconnect to {name} {device.identifier()}")
                else:
                    self.logger.debug(f"{name} {device.identifier()} is still connected.")
            except Exception as e:
                self.logger.error(f"Error checking device {device.identifier()}: {e}")

    def start_device_monitor(self, interval_seconds=10):
        if not self.scheduler.running:
            self.scheduler.start()
        if not self.scheduler.get_job("device_monitor"):
            self.scheduler.add_job(self.check_and_reconnect_devices, "interval", seconds=interval_seconds, id="device_monitor")
            self.logger.info("Started device monitor job")

    def stop_device_monitor(self):
        job = self.scheduler.get_job("device_monitor")
        if job:
            job.remove()
            self.logger.info("Stopped device monitor job")

    def get_participant_encoding(self, sub, ses):
        integer_representation = self.encode_participant(sub, ses)

        # print(name, integer_representation)
        self.participant_byte = struct.pack("<I", integer_representation)
        self.session_info = {
            'sub_id': sub,
            'ses_id': ses,
            'participant_enc': integer_representation
        }
        return integer_representation


    def set_erase_feature(self, erase_enable, erase_passcode):
        if erase_enable:
            if erase_passcode == 68:
                gr.Warning("Erase feature is enabled!")
                self.ctl_state = f"{self.ctl_state} | Erase feature active"
                return gr.Button("Erase flash data", interactive=True)
            else:
                gr.Warning("Incorrect password")
                return gr.Button("Erase flash data", interactive=False)
        else:
            gr.Info("Erase feature disabled")
            self.ctl_state.replace(" | Erase feature active", "")
            return gr.Button("Erase flash data", interactive=False)
        
    def erase_flash_data(self):
        gr.Info("Erasing flash data...")
        self.ctl_state = "Erase in progress"
        self.logger.info("Erasing flash data...")

        service_uuid = "da39c930-1d81-48e2-9c68-d0ae4bbd351f"
        rst_char = "da39c934-1d81-48e2-9c68-d0ae4bbd351f"

        for name, p in self.active_devices.items():
            try:
                p.write_request(service_uuid, rst_char, struct.pack("<I", int(68)))
            except Exception as e:
                self.logger.error(str(e))
                gr.Error(f"⚠️{str(e)}")
        self.logger.info("Erase completed")

        del(self.active_devices)
        self.active_devices = {}
        del(self.active_outlets)
        self.active_outlets = {}

        self.ctl_state = "Wait for device lights out and press 'Search bluetooth devices' to restart"
        return gr.Number(value=None, label="Erase code"), gr.Checkbox(label="Enable erase feature", value=False), gr.Button("Erase flash data", interactive=False)
