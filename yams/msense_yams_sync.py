#!/usr/bin/env python3
# %%
"""
Lightweight counter-based clock sync between an MSense CSV and a
YAMS-produced .txt reference file.

Unlike msense_lsl_sync.py, this script does not touch LSL/.xdf/psychopy at
all. The YAMS .txt file already carries a linearized Unix-clock estimate per
packet (t_unixc_lin), so we match rows to the CSV by hardware Counter value
and use t_unixc_lin directly as the anchor timestamp for interpolation.

The user passes the CSV and the YAMS .txt explicitly -- both must come from
the same physical device / recording. Two usage modes:

  1. --csv points at an 'ac.csv' file: the fitted CDCT -> t_unixc_lin
     interpolant is also propagated onto the sibling 'ppg.csv' file next to
     it (found automatically, or given explicitly via --ppg), since AC and
     PPG share the same device clock/counter.
  2. --csv points at anything else (e.g. an ECG file, which carries its own
     Counter + CDCT columns): only that single file is synced, no sibling
     search is attempted.
"""
import argparse
import os
from glob import glob

import gradio as gr
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import interpolate


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description='Sync an MSense CSV to a YAMS .txt reference via Counter matching')
    p.add_argument('--csv', required=True,
                   help='MSense CSV to sync (must have Counter + CDCT columns). '
                        "If this is an 'ac.csv' file, the sibling 'ppg.csv' next to it "
                        'is auto-discovered and synced too; any other file (e.g. ECG) '
                        'is synced alone.')
    p.add_argument('--txt', required=True,
                   help='YAMS .txt file for the same device '
                        '(whitespace-separated: ENMO Counter t_unixc_lin, no header)')
    p.add_argument('--ppg', default=None,
                   help="Explicit sibling PPG CSV to propagate the fitted interpolant onto. "
                        "Only used when --csv is an 'ac.csv' file. If omitted, the sibling "
                        "'ppg.csv' is searched for automatically next to --csv.")
    p.add_argument('--out', default='./out', help='Output directory')
    p.add_argument('--show', action='store_true', default=False,
                   help='Display figures interactively (default: save only)')
    return p.parse_known_args()[0]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_yams_txt(txt_path):
    """Load a YAMS .txt file: whitespace-separated, no header.

    Columns: ENMO, Counter, t_unixc_lin
    """
    df = pd.read_csv(txt_path, sep=r'\s+', header=None,
                     names=['ENMO', 'Counter', 't_unixc_lin'])
    return df


def load_csv(csv_path):
    df = pd.read_csv(csv_path)
    if 'CDCT' not in df.columns:
        df['CDCT'] = df['Timestamp']
    return df


# ---------------------------------------------------------------------------
# AC/PPG sibling discovery
# ---------------------------------------------------------------------------

def is_ac_file(csv_path):
    return os.path.basename(csv_path).lower().endswith('ac.csv')


def find_sibling_ppg(csv_path):
    """Look for a 'ppg.csv' file next to an 'ac.csv' file.

    Tries the exact suffix swap first (…ac.csv -> …ppg.csv), then falls back
    to a glob on the shared prefix in case of naming drift.
    """
    dirname = os.path.dirname(csv_path)
    basename = os.path.basename(csv_path)
    if not basename.lower().endswith('ac.csv'):
        return None

    prefix = basename[:-len('ac.csv')]
    guess = os.path.join(dirname, prefix + 'ppg.csv')
    if os.path.exists(guess):
        return guess

    candidates = sorted(glob(os.path.join(dirname, f'{prefix}*ppg.csv')))
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# Counter matching
# ---------------------------------------------------------------------------

def match_counters(valid_csv, df_txt):
    """
    Match YAMS .txt rows to CSV rows by Counter value using a monotonic
    forward search (each CSV row matched at most once).

    Parameters
    ----------
    valid_csv : (N, 2) array of (CDCT, Counter) from the CSV
    df_txt    : DataFrame with Counter, t_unixc_lin columns

    Returns
    -------
    matched_t_unix : float array, t_unixc_lin per CSV row (nan = unmatched)
    match_stats    : dict of matching statistics
    matched_points : (M, 2) array of matched (CDCT, Counter) coords
    """
    matched_t_unix = np.full(len(valid_csv), np.nan)
    matched_points = []
    curr_idx = 0
    n_matched = 0

    for _, row in df_txt.iterrows():
        hits = np.where(valid_csv[:, 1] == row['Counter'])[0]
        hits = hits[hits >= curr_idx]
        if len(hits):
            idx = hits[0]
            matched_t_unix[idx] = row['t_unixc_lin']
            matched_points.append(valid_csv[idx])
            curr_idx = idx
            n_matched += 1

    n_txt = len(df_txt)
    match_stats = {
        'txt_packets':  n_txt,
        'matched':      n_matched,
        'match_rate_%': round(100 * n_matched / n_txt, 1) if n_txt else 0.0,
    }
    matched_points = np.array(matched_points) if matched_points else np.empty((0, 2))
    return matched_t_unix, match_stats, matched_points


# ---------------------------------------------------------------------------
# Timestamp interpolation
# ---------------------------------------------------------------------------

def interpolate_timestamps(df_csv):
    """
    Fit a linear interpolant CDCT -> t_unixc_lin from matched anchors.
    """
    anchors = df_csv.dropna(subset=['t_unix_anchor'])
    n_total = len(df_csv)

    t_min, t_max = anchors['CDCT'].min(), anchors['CDCT'].max()
    n_extrap = ((df_csv['CDCT'] < t_min) | (df_csv['CDCT'] > t_max)).sum()

    print(f'  anchors:           {len(anchors)}/{n_total}')
    print(f'  extrapolated rows: {n_extrap} ({100 * n_extrap / n_total:.1f}%)')
    if n_extrap / n_total > 0.05:
        print('  [WARNING] >5% of rows outside matched range')

    f = interpolate.interp1d(anchors['CDCT'], anchors['t_unix_anchor'],
                             fill_value='extrapolate')
    return f(df_csv['CDCT']), anchors


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def plot_counter_matching(valid_csv, matched_points, match_stats, out_dir, tag):
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(valid_csv[:, 0], valid_csv[:, 1], color='lightgray', lw=0.8, label='CSV counter')
    if len(matched_points):
        ax.plot(matched_points[:, 0], matched_points[:, 1], 'o', ms=3, color='C0',
                label='matched (YAMS .txt)')
    ax.set_title(f"Counter matching — {tag}\n"
                f"{match_stats['matched']}/{match_stats['txt_packets']} "
                f"({match_stats['match_rate_%']}%)")
    ax.set_xlabel('CDCT')
    ax.set_ylabel('Counter')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f'counter_matching_{tag}.png'), dpi=150)
    return fig


def plot_interpolation_quality(df_csv, anchors, out_dir, tag):
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(df_csv['t_unixc_lin'], lw=0.8, label='interpolated')
    ax.plot(anchors.index, anchors['t_unix_anchor'], 'o', ms=3, label='anchors')
    ax.set_title(f'CDCT -> t_unixc_lin interpolation — {tag}')
    ax.set_xlabel('Row index')
    ax.set_ylabel('t_unixc_lin (s)')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f'interpolation_{tag}.png'), dpi=150)
    return fig


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def save_synced(df_csv, csv_path, out_dir):
    out_path = os.path.join(out_dir, os.path.basename(csv_path).replace('.csv', '_synced.csv'))
    df_csv.to_csv(out_path, index=False)
    print(f'  saved: {os.path.basename(out_path)}')


def sync_csv_to_yams(csv_path, txt_path, out_dir):
    """Match csv_path against txt_path by Counter, fit the CDCT -> t_unixc_lin
    interpolant, apply it, and save. Returns (df_synced, f_interp) so the
    same interpolant can be propagated onto a sibling file (e.g. PPG).
    """
    tag = os.path.splitext(os.path.basename(csv_path))[0]

    print(f'CSV: {os.path.basename(csv_path)}')
    print(f'TXT: {os.path.basename(txt_path)}')

    df_csv = load_csv(csv_path)
    df_txt = load_yams_txt(txt_path)

    valid_csv = np.column_stack((df_csv['CDCT'].to_numpy(), df_csv['Counter'].to_numpy()))

    # 1. Match counters between CSV and YAMS .txt
    matched_t_unix, match_stats, matched_points = match_counters(valid_csv, df_txt)
    df_csv['t_unix_anchor'] = matched_t_unix

    print('\n  Matching statistics:')
    print(f"    txt_packets={match_stats['txt_packets']}  "
         f"matched={match_stats['matched']}  "
         f"match_rate={match_stats['match_rate_%']}%")
    if match_stats['match_rate_%'] < 50:
        print('  [WARNING] low match rate')

    plot_counter_matching(valid_csv, matched_points, match_stats, out_dir, tag)

    # 2. Build interpolant from matched anchors and apply to every row
    print('\n  Interpolation:')
    df_csv['t_unixc_lin'], anchors = interpolate_timestamps(df_csv)
    plot_interpolation_quality(df_csv, anchors, out_dir, tag)

    f_interp = interpolate.interp1d(anchors['CDCT'], anchors['t_unix_anchor'],
                                    fill_value='extrapolate')

    df_csv = df_csv.drop(columns=['t_unix_anchor'])
    save_synced(df_csv, csv_path, out_dir)

    return df_csv, f_interp


def apply_interp_to_csv(csv_path, f_interp, out_dir):
    """Propagate an already-fitted CDCT -> t_unixc_lin interpolant onto
    another CSV from the same device (e.g. PPG alongside AC).
    """
    print(f'\nPropagating to: {os.path.basename(csv_path)}')
    df_csv = load_csv(csv_path)
    df_csv['t_unixc_lin'] = f_interp(df_csv['CDCT'])
    save_synced(df_csv, csv_path, out_dir)
    return df_csv


# ---------------------------------------------------------------------------
# Gradio interface
# ---------------------------------------------------------------------------

def run_sync(csv_files, txt_file, progress=gr.Progress()):
    """Gradio callback: sync uploaded CSVs against a YAMS .txt reference."""
    import matplotlib
    matplotlib.use('Agg')

    if txt_file is None:
        return "Error: no YAMS .txt file uploaded.", [], gr.DownloadButton(interactive=False)
    if not csv_files:
        return "Error: no CSV files uploaded.", [], gr.DownloadButton(interactive=False)

    import tempfile, zipfile as _zipfile, io as _io
    from contextlib import redirect_stdout

    progress(0, desc="Preparing files...")

    with tempfile.TemporaryDirectory() as out_dir:
        # Gradio passes file paths directly; resolve to local paths.
        txt_path = txt_file
        csv_paths = [f for f in csv_files]

        # Separate AC files from the rest.
        ac_csvs = [p for p in csv_paths if os.path.basename(p).lower().endswith('ac.csv')]
        other_csvs = [p for p in csv_paths if p not in ac_csvs]

        status_lines = []
        plot_paths = []
        processed_as_sibling = set()

        total = len(ac_csvs) + len(other_csvs)
        done = 0

        # --- AC files (+ sibling PPG propagation) ---
        for ac_path in ac_csvs:
            tag = os.path.splitext(os.path.basename(ac_path))[0]
            progress(done / total, desc=f"Syncing {tag}...")
            buf = _io.StringIO()
            try:
                with redirect_stdout(buf):
                    _, f_interp = sync_csv_to_yams(ac_path, txt_path, out_dir)
                status_lines.append(f"[OK] {tag}: {buf.getvalue().strip()}")

                # Find sibling PPG among uploads (same prefix, ends ppg.csv).
                prefix = os.path.basename(ac_path)[:-len('ac.csv')]
                siblings = [p for p in other_csvs
                            if os.path.basename(p).lower() == prefix + 'ppg.csv']
                if not siblings:
                    # Looser match: any uploaded file whose name contains prefix and ends ppg.csv.
                    siblings = [p for p in other_csvs
                                if os.path.basename(p).lower().endswith('ppg.csv')
                                and prefix in os.path.basename(p)]
                if siblings:
                    ppg_path = siblings[0]
                    ppg_tag = os.path.splitext(os.path.basename(ppg_path))[0]
                    buf2 = _io.StringIO()
                    with redirect_stdout(buf2):
                        apply_interp_to_csv(ppg_path, f_interp, out_dir)
                    status_lines.append(f"[OK] {ppg_tag}: propagated from {tag}")
                    processed_as_sibling.add(ppg_path)
                else:
                    status_lines.append(f"[INFO] {tag}: no sibling PPG found among uploads")
            except Exception as e:
                status_lines.append(f"[ERROR] {tag}: {e}")
            done += 1

        # --- Standalone files (ECG, or PPG not tied to an AC) ---
        for csv_path in other_csvs:
            if csv_path in processed_as_sibling:
                continue
            tag = os.path.splitext(os.path.basename(csv_path))[0]
            progress(done / total, desc=f"Syncing {tag}...")
            buf = _io.StringIO()
            try:
                with redirect_stdout(buf):
                    sync_csv_to_yams(csv_path, txt_path, out_dir)
                status_lines.append(f"[OK] {tag}: {buf.getvalue().strip()}")
            except Exception as e:
                status_lines.append(f"[ERROR] {tag}: {e}")
            done += 1

        # Collect plots and read into memory before the temp dir is deleted.
        plot_paths = sorted(glob(os.path.join(out_dir, '*.png')))
        from PIL import Image as _Image
        plot_images = [_Image.open(p).copy() for p in plot_paths]

        # Check we have something to zip.
        synced_csvs = sorted(glob(os.path.join(out_dir, '*_synced.csv')))
        if not synced_csvs:
            return "\n".join(status_lines), plot_images, gr.DownloadButton(
                label="No output to download", interactive=False)

        progress(0.95, desc="Building zip...")
        import time as _time
        zip_path = os.path.join(tempfile.gettempdir(),
                                f"{_time.strftime('%y%m%d%H%M')}_synced.zip")
        with _zipfile.ZipFile(zip_path, 'w', _zipfile.ZIP_DEFLATED) as zf:
            for f in synced_csvs + plot_paths:
                zf.write(f, os.path.basename(f))

        progress(1.0, desc="Done.")
        status = "\n".join(status_lines)
        return status, plot_images, gr.DownloadButton(
            label="🎉 Download synced ZIP", value=zip_path, interactive=True)


def sync_interface():
    with gr.Column():
        gr.Markdown("## ⏱️ Clock Sync\nMatch MSense CSV files to a YAMS `.txt` reference by Counter, "
                    "fit a CDCT → Unix-time interpolant, and export timestamped CSVs.")
        with gr.Row():
            txt_input = gr.File(label="YAMS .txt file", file_count="single",
                                file_types=[".txt"])
            csv_input = gr.File(label="MSense CSV file(s)", file_count="multiple",
                                file_types=[".csv"])
        run_btn = gr.Button("Run Sync", variant="primary")

        with gr.Column(visible=False) as result_col:
            status_box = gr.Textbox(label="Status / stats", lines=8, interactive=False)
            gallery = gr.Gallery(label="Plots", columns=2, height=400)
            download_btn = gr.DownloadButton(label="Download synced ZIP", interactive=False)

        def _run(csv_files, txt_file, progress=gr.Progress()):
            status, plots, btn = run_sync(csv_files, txt_file, progress)
            return (
                gr.Column(visible=True),
                status,
                plots,
                btn,
            )

        run_btn.click(
            fn=_run,
            inputs=[csv_input, txt_input],
            outputs=[result_col, status_box, gallery, download_btn],
        )


# %%
if __name__ == '__main__':
    args = parse_args()

    if not args.show:
        import matplotlib
        matplotlib.use('Agg')  # non-interactive: savefig works, no windows appear

    os.makedirs(args.out, exist_ok=True)

    # %%
    df_synced, f_interp = sync_csv_to_yams(args.csv, args.txt, args.out)

    # Mode 1: an AC file -- also propagate onto its sibling PPG file.
    # Mode 2: anything else (e.g. an ECG file) -- sync stands alone.
    if is_ac_file(args.csv):
        ppg_path = args.ppg or find_sibling_ppg(args.csv)
        if ppg_path:
            apply_interp_to_csv(ppg_path, f_interp, args.out)
        else:
            print('\n[INFO] no sibling PPG file found next to the AC CSV -- skipping propagation')
    else:
        print('\n[INFO] input is not an AC file -- synced alone, no PPG propagation attempted')

    if args.show:
        plt.show()
# %%
