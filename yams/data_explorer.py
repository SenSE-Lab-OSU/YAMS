import gradio as gr
import pandas as pd
import plotly.express as px

# Default X window on load/reset, in the units of the X column (CDCT is
# unix-seconds, so this is 60 seconds of a recording) rather than the whole
# file — full-resolution, undecimated rendering of a multi-million-row export
# needs a bounded window to stay both correct-looking and fast.
DEFAULT_WINDOW = 60


class DataExplorer():
    """CSV plot viewer: drop a YAMS-extracted CSV, pick x/y columns, get an
    interactive chart with axis ranges that default to the actual data
    instead of empty sliders. The chart itself is a Plotly figure so the
    standard Plotly toolbar (drag-to-box-zoom, a pan-mode toggle, scroll
    zoom in/out, double-click to reset) is always available — the X/Y
    from/to boxes are for jumping to a precise numeric window, not the only
    way to navigate.
    """

    def interface(self):
        file = gr.File(file_types=['.csv'], label="Drop a CSV")
        # Per-browser-session data, not an instance attribute: two people
        # using this tab on the same running server must not see each
        # other's file.
        state = gr.State()

        with gr.Row():
            x_to_plot = gr.Dropdown(label="X axis")
            y_to_plot = gr.CheckboxGroup(label="Y axis (one or more)")

        with gr.Row():
            x_start = gr.Number(label="X from")
            x_end = gr.Number(label="X to")
            y_start = gr.Number(label="Y from")
            y_end = gr.Number(label="Y to")
            reset_btn = gr.Button("↺ Reset zoom", scale=0)

        summary = gr.Markdown()
        plot = gr.Plot(show_label=False)

        range_inputs = [x_to_plot, y_to_plot, x_start, x_end, y_start, y_end]

        file.change(self.load_file, inputs=file,
                    outputs=[state, x_to_plot, y_to_plot, summary])
        x_to_plot.change(self.default_x_window, inputs=[state, x_to_plot],
                         outputs=[x_start, x_end]) \
                 .then(self.autorange_y, inputs=[state, y_to_plot, x_to_plot, x_start, x_end],
                       outputs=[y_start, y_end])
        y_to_plot.change(self.autorange_y, inputs=[state, y_to_plot, x_to_plot, x_start, x_end],
                         outputs=[y_start, y_end])
        for comp in range_inputs:
            comp.change(self.render, inputs=[state] + range_inputs, outputs=plot)
        reset_btn.click(self.default_x_window, inputs=[state, x_to_plot], outputs=[x_start, x_end]) \
                 .then(self.autorange_y, inputs=[state, y_to_plot, x_to_plot, x_start, x_end],
                       outputs=[y_start, y_end]) \
                 .then(self.render, inputs=[state] + range_inputs, outputs=plot)

    def load_file(self, file):
        if file is None:
            return None, gr.Dropdown(choices=[], value=None), gr.CheckboxGroup(choices=[], value=[]), ""

        df = pd.read_csv(file)
        columns = list(df.columns)
        numeric = [c for c in columns if pd.api.types.is_numeric_dtype(df[c])]

        # CDCT (cumulative data-clock time, unix seconds) is the natural time
        # axis for every YAMS export; default to it when present.
        default_x = "CDCT" if "CDCT" in columns else (numeric[0] if numeric else columns[0])
        y_candidates = [c for c in numeric if c != default_x]
        default_y = y_candidates[:1]

        summary = f"**{len(df):,} rows** loaded, {len(columns)} columns."
        return (df,
                gr.Dropdown(choices=columns, value=default_x, label="X axis"),
                gr.CheckboxGroup(choices=y_candidates, value=default_y, label="Y axis (one or more)"),
                summary)

    def default_x_window(self, df, x_col):
        """First DEFAULT_WINDOW units of the file, not the whole span — with
        decimation off, the whole span of a multi-million-row file is both
        slow and unreadable as one render.
        """
        if df is None or not x_col or not pd.api.types.is_numeric_dtype(df[x_col]):
            return None, None
        lo, hi = float(df[x_col].min()), float(df[x_col].max())
        return lo, min(hi, lo + DEFAULT_WINDOW)

    def autorange_y(self, df, y_cols, x_col=None, x_start=None, x_end=None):
        """Y range for whatever is actually visible in [x_start, x_end], not
        the whole file — an outlier elsewhere in the recording shouldn't
        flatten the default view of the current window.
        """
        if df is None or not y_cols:
            return None, None
        view = df
        if (x_col and x_start is not None and x_end is not None
                and pd.api.types.is_numeric_dtype(df[x_col])):
            windowed = view[(view[x_col] >= x_start) & (view[x_col] <= x_end)]
            if not windowed.empty:
                view = windowed
        s = view[list(y_cols)]
        lo, hi = float(s.min().min()), float(s.max().max())
        pad = (hi - lo) * 0.05 or (abs(hi) * 0.05 or 1.0)
        return lo - pad, hi + pad

    def render(self, df, x_col, y_cols, x_start, x_end, y_start, y_end):
        if df is None or not x_col or not y_cols:
            return None

        y_cols = list(y_cols)
        view = df[[x_col] + y_cols]
        if (x_start is not None and x_end is not None and x_end > x_start
                and pd.api.types.is_numeric_dtype(view[x_col])):
            view = view[(view[x_col] >= x_start) & (view[x_col] <= x_end)]

        long_df = view.melt(id_vars=x_col, value_vars=y_cols,
                            var_name="channel", value_name="value")

        fig = px.line(long_df, x=x_col, y="value", color="channel")
        fig.update_layout(
            height=420,
            margin=dict(l=50, r=20, t=20, b=40),
            legend_title_text="",
            xaxis_title=x_col,
            yaxis_title=None,
            dragmode="zoom",           # click-drag = box zoom; toolbar toggles to pan
        )
        if y_start is not None and y_end is not None and y_end > y_start:
            fig.update_yaxes(range=[y_start, y_end])
        return fig
