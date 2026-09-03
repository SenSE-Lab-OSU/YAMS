"""YAMS 2.x — a thin MSense-only front-end over PLASMA.

Every panel here is PLASMA's (`plasma.devices.msense.panels.*` + the shared
`IntegratedPanel`); YAMS only picks the tab layout, the branding and the
MSense-only device set. The v1 tab structure is preserved.

`configure()` MUST run before any `plasma.*` import that builds a singleton off
`app_context()` (notably `plasma.config`), so every PLASMA import in this module
is deferred into the functions below.
"""


def _configure():
    from plasma.app_context import configure
    from yams import config as ycfg

    configure(
        app_name=ycfg.APP_NAME,
        journal_stream=ycfg.JOURNAL_STREAM,
        data_dir_name=ycfg.DATA_DIR_NAME,
        config_filename=ycfg.CONFIG_FILENAME,
        gyro_bias_filename=ycfg.GYRO_BIAS_FILENAME,
    )


def _msense_only(device_config, plugins):
    """Lock the enabled-device set to the MSense plugin (YAMS is single-sensor)."""
    names = [p.display_name for p in plugins.all_plugins() if p.id == "msense"]
    device_config._active = names
    return names


def build():
    """The YAMS Gradio app. Assumes `_configure()` has already run."""
    import gradio as gr

    from plasma import plugins
    from plasma.config import device_config
    from plasma.integrated_panel import IntegratedPanel
    from plasma.devices.msense.config import config_section as msense_config_section
    from plasma.devices.msense.panels.clocksync import build_clocksync
    from plasma.devices.msense.panels.control import build_control_tab
    from plasma.devices.msense.panels.downloader import build_downloader
    from plasma.devices.msense.panels.extractor import build_extractor, build_extractor_pro
    from plasma.devices.msense.panels.imu import build_imu_tab
    from plasma.devices.msense.panels.sqc import build_sqc_tab
    from plasma.devices.msense.panels.uuid_tools import build_device_manager, build_uuid_extractor
    from plasma.devices.msense.panels.viewer import build_viewer
    from yams.config import __version__

    plugins.load_plugins()
    device_config.refresh_defaults()
    _msense_only(device_config, plugins)

    ip = IntegratedPanel()

    with gr.Blocks(title="YAMS") as demo:
        with gr.Tab("⌚️ MotionSenSE controller"):
            with gr.Accordion("🔍 Wristband setup — scan / list / device_info.json", open=False):
                msense_config_section(device_config)
            ip.interface()
            build_control_tab(ip)

        with gr.Tab("📡 Signal quality"):
            build_sqc_tab(ip)
        with gr.Tab("🧭 IMU / Orientation"):
            build_imu_tab(ip)
        with gr.Tab("📈 Signal visualizer"):
            ip.visualizer_interface()

        with gr.Tab("📂 File downloader"):
            build_downloader(ip)
        with gr.Tab("📋 UUID extractor"):
            build_uuid_extractor(ip)
        with gr.Tab("📊 Data viewer"):
            build_viewer(ip)
        with gr.Tab("🛠️ Data extractor"):
            build_extractor(ip)
        with gr.Tab("🛠️ Data extractor pro"):
            build_extractor_pro(ip)
        with gr.Tab("⏱️ Clock Sync"):
            build_clocksync(ip)
        with gr.Tab("📒 Extensions"):
            with gr.Accordion(label="📒 Device manager"):
                build_device_manager(ip)

        gr.Markdown(
            f"[YAMS](https://github.com/SenSE-Lab-OSU/YAMS) v{__version__}: "
            "Yet Another MotionSenSE Service utility — powered by "
            "[PLASMA](https://github.com/YuyiChang/PLASMA)",
            elem_id="footer",
        )

    return demo


def main():
    _configure()
    from yams.config import favicon_path

    demo = build()
    demo.queue()
    demo.launch(inbrowser=True, favicon_path=favicon_path())


if __name__ == "__main__":
    main()
