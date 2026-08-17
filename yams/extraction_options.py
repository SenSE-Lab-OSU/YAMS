"""Extraction options shared by every tab that can run an extraction.

Three surfaces run the same extraction — the Data extractor tab, the Data
extractor pro tab, and the File downloader's "Extract data after download" — so
the controls live here once instead of drifting apart in three interface
functions.

`ExtractionOptions` is what the extraction code consumes; `ExtractionOptionsPanel`
is the Gradio accordion that produces one. Gradio components must be built inside
the Blocks context that renders them, so the panel is constructed per tab; what is
shared is the control definitions and the component <-> field ordering, which is
declared in `ExtractionOptionsPanel.FIELDS` and nowhere else.

Fields marked `metadata={"panel": False}` are CLI-only and are skipped by the
panel, so the dataclass stays the single source of the field list.
"""
from dataclasses import dataclass, field, fields

import gradio as gr

from yams.formats import spec_names


def format_choices(sensor):
    """Selector vocabulary for one sensor: modes first, then explicit layouts."""
    return ["auto", "version"] + list(spec_names(sensor))


PPG_FORMAT_CHOICES = format_choices("ppg") + ["sniff"]   # "sniff" = deprecated alias for auto
AC_FORMAT_CHOICES = format_choices("ac")
ECG_FORMAT_CHOICES = format_choices("ecg")
CONFLICT_CHOICES = ["warn", "raise", "trust_uuid"]

FORMAT_HELP = """### Record format

Every layout is detected from file contents by default — `uuid.txt` is not
needed, and where the two disagree the contents win.

| Choice | Meaning |
|---|---|
| `auto` | Detect from content, per file. Falls back to the device version if inconclusive. **Default.** |
| `version` | Follow `uuid.txt` only (v4.7.0+ → `v2`, otherwise `legacy`). The pre-1.6 behaviour. |
| `legacy` / `v2` / `packed16` / `framed` | Force that layout. |

| Sensor | Layouts |
|---|---|
| PPG | `legacy` 24 B · `v2` 20 B · `packed16` 16 B (no version tie) |
| IMU | `legacy` 30 B · `v2` 26 B |
| ECG | `framed` 12 B |

**Cross-check against uuid.txt** reports when detection and the version file
disagree. It is off by default and does not override detection: use
*On conflict → trust_uuid* for that.

**Strict record validation**: raise on a record that fails its integrity check
(packed16 reserved bits, ECG CRC, a partial trailing record) instead of dropping
it and reporting a count.
"""


@dataclass
class ExtractionOptions:
    """Everything that changes how binaries are decoded and written out.

    Deliberately excludes per-run metadata (input/output paths, note, encoding
    table): those differ per surface, while these must not.
    """
    legacy_fs: bool = False
    save_format: str = "csv"
    ignore_id_parsing: bool = False
    ppg_format: str = "auto"
    ac_format: str = "auto"
    ecg_format: str = "auto"
    validate_with_uuid: bool = False
    on_format_conflict: str = "warn"
    strict_ppg: bool = False
    force_new_format: bool = False
    sniff_threshold: float = field(default=0.90, metadata={"panel": False})
    dry_run: bool = field(default=False, metadata={"panel": False})

    def __post_init__(self):
        # "sniff" was the 1.5 name for what "auto" now does.
        if self.ppg_format == "sniff":
            self.ppg_format = "auto"

    def format_for(self, sensor):
        return getattr(self, f"{sensor}_format")

    @classmethod
    def from_args(cls, args):
        """Build from the argparse namespace of yams.data_extraction."""
        return cls(
            legacy_fs=args.legacy_fs,
            save_format=args.save_format,
            ignore_id_parsing=args.ignore_id,
            ppg_format=args.ppg_format,
            ac_format=args.ac_format,
            ecg_format=args.ecg_format,
            validate_with_uuid=args.validate_with_uuid,
            on_format_conflict=args.on_format_conflict,
            strict_ppg=args.strict_ppg,
            force_new_format=args.force_new_format,
            sniff_threshold=args.sniff_threshold,
            dry_run=args.dry_run,
        )


class ExtractionOptionsPanel:
    """The advanced-options accordion. Build one inside each Blocks context.

    Usage:

        opts = ExtractionOptionsPanel(open=True)
        btn.click(opts.bind(main), inputs=[in_dir, out_dir, df, note] + opts.inputs)

    `bind` hands the wrapped function an `options=ExtractionOptions(...)` keyword
    instead of one trailing positional per control, so adding a control means
    editing the dataclass and the constructor here — no call site changes.
    """

    FIELDS = tuple(f.name for f in fields(ExtractionOptions)
                   if f.metadata.get("panel", True))

    def __init__(self, open=False, visible=True):
        with gr.Accordion("⚙️ Advanced extraction options", open=open, visible=visible) as accordion:
            self.accordion = accordion
            with gr.Row():
                self.legacy_fs = gr.Checkbox(False, label="(Uncommon) legacy sampling rate")
                self.save_format = gr.Radio(["csv", "pickle"], value="csv", label="Save format")
                self.ignore_id_parsing = gr.Checkbox(False, label="Ignore subject/session ID parsing")
            with gr.Row():
                self.ppg_format = gr.Dropdown(
                    PPG_FORMAT_CHOICES, value="auto", label="PPG record format",
                    info="auto = detect from content")
                self.ac_format = gr.Dropdown(
                    AC_FORMAT_CHOICES, value="auto", label="IMU record format",
                    info="auto = detect from content")
                self.ecg_format = gr.Dropdown(
                    ECG_FORMAT_CHOICES, value="auto", label="ECG record format",
                    info="auto = detect from content")
            with gr.Row():
                self.validate_with_uuid = gr.Checkbox(
                    False, label="Cross-check against uuid.txt")
                self.on_format_conflict = gr.Radio(
                    CONFLICT_CHOICES, value="warn", label="On conflict",
                    info="Content wins unless trust_uuid")
                self.strict_ppg = gr.Checkbox(False, label="Strict record validation")
                self.force_new_format = gr.Checkbox(
                    False, label="Assume v4.7.0+ (fallback only)")
            with gr.Accordion("Help", open=False):
                gr.Markdown(FORMAT_HELP)

    @property
    def inputs(self):
        """Append to any `inputs=` list; pairs with `bind` on the same panel."""
        return [getattr(self, name) for name in self.FIELDS]

    def bind(self, fn):
        """Wrap `fn` so the trailing option components arrive as `options=`."""
        n = len(self.FIELDS)

        def wrapper(*args):
            fixed, values = args[:-n], args[-n:]
            return fn(*fixed, options=ExtractionOptions(**dict(zip(self.FIELDS, values))))

        return wrapper

    def gate_on(self, checkbox):
        """Show the accordion only while `checkbox` is ticked (File downloader)."""
        checkbox.change(lambda on: gr.Accordion(visible=bool(on)),
                        inputs=checkbox, outputs=self.accordion)
