"""YAMS's v1-style controller UI over PLASMA's MSense device methods."""


def _selected_records(existing, scanned, selected):
    """Make the scan selection the enabled MSense set without losing saved labels."""
    by_address = {
        str(record.get("UUID / MAC Address", "")).upper(): dict(record)
        for record in existing
        if str(record.get("UUID / MAC Address", "")).strip()
    }
    selected = set(selected or [])
    for address, device in scanned.items():
        if address not in by_address:
            by_address[address] = {
                "Name": device["name"],
                "Nickname": "",
                "UUID / MAC Address": address,
                "IMU Stream": False,
            }
        by_address[address]["Enabled"] = address in selected
    for address, record in by_address.items():
        record["UUID / MAC Address"] = address
        if address not in scanned:
            record["Enabled"] = False

    # PLASMA 2.2.3 keys wristbands by address, so duplicate advertised names
    # can be kept exactly as the device reports them.
    return list(by_address.values())


def build_controller(ip, device_config):
    """Build the standalone YAMS control flow using PLASMA's live session."""
    import gradio as gr

    from plasma.devices.msense.panels.control import build_control_tab

    scan_state = gr.State({})

    with gr.Accordion("Initialization", open=True):
        bt_search = gr.Button("Search Bluetooth devices 📱")
        available_devices = gr.CheckboxGroup(label="Available devices", scale=6)
        with gr.Row():
            bt_connect = gr.Button("✅ Connect selected")
            btn_disconnect = gr.Button("❌ Disconnect")
        gr.Markdown("Start, Stop, and flash erase apply to the connected wristbands. "
                    "To change the set, select wristbands and press Connect selected again.")
        connection_status = gr.Markdown()

    def _scan():
        from plasma.devices.msense.ble_scan import scan_msense

        try:
            found = scan_msense()
        except Exception as exc:
            return gr.update(choices=[], value=[]), {}, f"Scan failed: {exc}"
        scanned = {dev["address"].upper(): dev for dev in found}
        choices = [(f"{dev['name']} [{address}]", address)
                   for address, dev in scanned.items()]
        status = (f"Found {len(choices)} MSense wristband(s). Select the ones to connect."
                  if choices else "No MSense wristbands found in range.")
        return gr.update(choices=choices, value=list(scanned)), scanned, status

    def _connect(selected, scanned):
        selected = list(dict.fromkeys(selected or []))
        if not selected:
            return "Select at least one wristband from the scan."
        if not scanned or any(address not in scanned for address in selected):
            return "Search for wristbands again before connecting."

        plugin_names = [name for name, plugin in device_config.get_active_table().items()
                        if plugin.id == "msense"]
        if not plugin_names:
            return "MSense is unavailable in the device catalog."
        blob = device_config.get_plugin_config("msense")
        existing = blob.get("devices", []) if isinstance(blob, dict) else []
        records = _selected_records(existing, scanned, selected)
        device_config.update_plugin_config("msense", {"devices": records})
        try:
            ip.init_devices(plugin_names)
        except Exception as exc:
            return f"Connection failed: {exc}"
        driver = next((dev for dev in ip.available_devices
                       if hasattr(dev, "active_devices")), None)
        connected = ([f"{driver.display_name(address)} [{address}]"
                      for address in driver.active_devices]
                     if driver is not None else [])
        if not connected:
            return "No selected wristbands connected. Search again and retry."
        return f"Connected: {', '.join(connected)}"

    def _disconnect():
        ip.init_devices([])
        return "Disconnected."

    bt_search.click(_scan, outputs=[available_devices, scan_state, connection_status])
    bt_connect.click(_connect, inputs=[available_devices, scan_state], outputs=connection_status)
    btn_disconnect.click(_disconnect, outputs=connection_status)

    with gr.Accordion("Device control", open=True):
        default_sub, default_ses = "sub-1000", "ses-00"
        with gr.Row():
            sub_name = gr.Text(default_sub, label="Subject ID", info="Format: sub-XXXX, X is integer")
            ses_name = gr.Text(default_ses, label="Session ID", info="Format: ses-YY, Y is integer")
            subject_enc = gr.Number(
                ip.get_participant_encoding(default_sub, default_ses),
                label="Participant encoding (Read-only)", interactive=False,
                info="Format: XXXXYY",
            )
        sub_name.change(ip.get_participant_encoding, inputs=[sub_name, ses_name], outputs=subject_enc)
        ses_name.change(ip.get_participant_encoding, inputs=[sub_name, ses_name], outputs=subject_enc)
        with gr.Row():
            btn_start = gr.Button("Start▶️")
            btn_stop = gr.Button("Stop🛑")
        btn_start.click(ip.start_collection)
        btn_stop.click(ip.stop_collection)
        record_lsl = gr.Checkbox(
            value=ip.record_lsl, label="📼 Record all LSL streams to XDF")
        record_lsl.change(ip._set_record_lsl, inputs=record_lsl)

    memo = gr.HTML(ip._render_memo())
    gr.Timer(value=1).tick(fn=ip._render_memo, outputs=memo, show_progress="hidden")

    with gr.Accordion("🗒️ Journaler", open=False):
        free_txt = gr.Text(label="Marker text", placeholder="free text")
        with gr.Row():
            btn_send_msg = gr.Button("✍️ Record message")
            btn_flag = gr.Button("🚩 Flag", scale=0)
        btn_send_msg.click(ip._record_journal, inputs=free_txt, outputs=free_txt)
        btn_flag.click(ip._flag_journal)

    # This panel supplies PLASMA's existing code-68 gate, erase call, and
    # reconnect/diagnostic controls for the wristbands connected above.
    build_control_tab(ip)
