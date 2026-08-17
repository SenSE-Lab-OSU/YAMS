# original credit: https://github.com/SenSE-Lab-OSU/MotionSenseHRV4Flash/blob/main/DataExtraction/data_extraction.py
import os
import sys
import struct
import re
import datetime
import traceback
import argparse
import pandas as pd
import numpy as np
import numpy
from datetime import datetime, UTC
import gradio as gr
import zipfile
import tempfile
from glob import glob
import shutil
from tqdm import tqdm

from yams import detect, formats
from yams.detect import Resolution
from yams.extraction_options import (
    AC_FORMAT_CHOICES,
    CONFLICT_CHOICES,
    ECG_FORMAT_CHOICES,
    PPG_FORMAT_CHOICES,
    ExtractionOptions,
    ExtractionOptionsPanel,
)

def get_participant_ids(folder_path):
    prefixes = set()
    for filename in os.listdir(folder_path):
        if not filename.endswith(".bin"):
            continue

        match = re.match(r"(\d*)ppg\d+\.bin$", filename)
        if match:
            prefix = match.group(1)
            if prefix == "":
                prefixes.add('')  
            else:
                prefixes.add(str(prefix))
    return sorted(prefixes, key=lambda x: (x is None, x))

def get_device_version(folder_path):
    uuid_path = os.path.join(folder_path, "uuid.txt")
    if not os.path.exists(uuid_path):
        return (0, 0, 0)
    with open(uuid_path, 'r') as f:
        content = f.read()
    match = re.search(r'Version:\s*(\d+)\.(\d+)\.(\d+)', content)
    if match:
        return tuple(int(x) for x in match.groups())
    return (0, 0, 0)

# ---------------------------------------------------------------------------
# Record layouts and format resolution now live in yams.formats / yams.detect.
# Re-exported here because the packed16 unit tests and external callers import
# these names from this module.
# ---------------------------------------------------------------------------
get_CDCT_init = formats.get_CDCT_init
read_bin = formats.read_bin
decode_ppg_packed16 = formats.decode_ppg_packed16
read_ppg_bin_packed16 = formats.read_ppg_bin_packed16
PPG_PACKED_RECORD_SIZE = formats.PPG_PACKED_RECORD_SIZE
PPG_PACKED_SAMPLE_MASK = formats.PPG_PACKED_SAMPLE_MASK
PPG_PACKED_RESERVED_MASK = formats.PPG_PACKED_RESERVED_MASK


def sniff_ppg_format(filepath, n_probe=2000, threshold=0.9):
    """Detect a PPG file's layout from its contents. None if inconclusive."""
    return detect.sniff_file(filepath, "ppg", threshold=threshold)



def data_extraction_pro_interface():
    in_file = gr.File(file_types=[".zip"])
    opts = ExtractionOptionsPanel()
    out = gr.DownloadButton(label="No data to be downloaded", interactive=False)
    in_file.change(opts.bind(extract_zip), inputs=[in_file] + opts.inputs, outputs=out)

def batch_extract_zips(in_path, options=None):
    zips = glob(os.path.join(in_path, "*.zip"))
    print(zips)
    for z in tqdm(zips):
        extract_zip(z, cli_mode=True, out_dir=os.path.join(in_path, "out"), options=options)

def extract_zip(zip_path, cli_mode=False, out_dir="./data", options=None):
    options = options or ExtractionOptions()
    df = get_session_encoding()
    if zip_path is not None:
        with tempfile.TemporaryDirectory() as tmpdir:
            print(zip_path)
            print(tmpdir)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)

            devices = os.listdir(tmpdir)
            for dev in devices:
                in_dir = os.path.join(tmpdir, dev)
                main(in_dir, in_dir, df=df, note=dev, gradio=False, options=options)

            out_zip_path = os.path.join(tempfile.gettempdir(),
                                    os.path.basename(zip_path).replace('.zip', '_extracted.zip'))
            
            with zipfile.ZipFile(out_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(tmpdir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, start=tmpdir)
                        zipf.write(file_path, arcname)

            if cli_mode:
                os.makedirs(out_dir, exist_ok=True)
                shutil.copy(out_zip_path, os.path.join(out_dir, os.path.basename(out_zip_path)))
        return gr.DownloadButton(label="🎉Download data", value=out_zip_path, interactive=True)
    else:
        return gr.DownloadButton(label="No data to be downloaded", interactive=False)

def get_session_encoding():
    if os.path.exists("./yams-data/session_table.csv"):
            df = pd.read_csv("./yams-data/session_table.csv")
    else:
        df = pd.DataFrame(data={
            'subject_id': ["sub-Test"],
            "session_id": ["ses-01"],
            "encoding": [123]
        })
    return df

def data_extraction_interface():
    # in_files = gr.File(file_count="multiple")
    in_dir = gr.Text("/path/to/binary/data", label="Input directory")
    out_dir = gr.Text("/path/to/output", label="Output directory")

    note = gr.Text("", label="Note")

    # Extraction is what this tab is for, so the panel starts open here.
    opts = ExtractionOptionsPanel(open=True)

    btn = gr.Button("Extract raw data")

    with gr.Accordion("Encoding mapping"):
        df = get_session_encoding()
        dataframe = gr.DataFrame(value=df)

    gradio_state = gr.State(True)
    btn.click(opts.bind(main),
              inputs=[in_dir, out_dir, dataframe, note, gradio_state] + opts.inputs)

SENSOR_ORDER = ("ac", "ppg", "ecg")


def sensor_of(filename):
    """Which sensor a binary belongs to, by the tag in its name."""
    for sensor in ("ppg", "ecg", "ac"):
        if sensor in filename:
            return sensor
    return None


class DataExtractor():
    def __init__(self, in_dir, out_dir, df=None, note="", options=None):
        options = options or ExtractionOptions()
        self.options = options
        self.in_dir = in_dir
        self.out_dir = out_dir
        self.note = note
        self.df = df
        self.save_format = options.save_format
        self.ignore_id_parsing = options.ignore_id_parsing
        self.strict = options.strict_ppg

        self.device_version = get_device_version(in_dir)
        version_str = ".".join(str(x) for x in self.device_version)
        if self.device_version == (0, 0, 0):
            version_str += " (no uuid.txt)"
        print(f"device version: {version_str}")
        print("record formats: " + ", ".join(
            f"{s}={options.format_for(s)}" for s in SENSOR_ORDER))

        # Format is resolved per file, not per folder: a folder can hold captures
        # from more than one firmware, and the resolution is evidence we keep.
        self.resolutions = []
        self.malformed = 0

        self.encoding_alias = self.get_encoding_alias() if self.df is not None else {}

        if not options.dry_run:
            os.makedirs(out_dir, exist_ok=True)
            self.write_readme_header()

    def write_readme_header(self):
        options = self.options
        with open(os.path.join(self.out_dir, "README.txt"), "w") as file:
            file.write(f"Raw data directory = {self.in_dir}\n")
            file.write(f"Legacy sampling rate = {options.legacy_fs} (no effect; see doc/data_extraction.md)\n")
            file.write(f"Save format = {options.save_format}\n")
            file.write(f"Ignore subject/session ID parsing = {options.ignore_id_parsing}\n")
            for sensor in SENSOR_ORDER:
                file.write(f"{sensor.upper()} record format = {options.format_for(sensor)} (requested)\n")
            file.write(f"Cross-check against uuid.txt = {options.validate_with_uuid}"
                       f" (on conflict: {options.on_format_conflict})\n")
            file.write(f"Strict record validation = {options.strict_ppg}\n")
            file.write(f"Detection threshold = {options.sniff_threshold}\n")
            file.write("I m-sense with YAMS at https://github.com/SenSE-Lab-OSU/YAMS\n")
            uuid_path = os.path.join(self.in_dir, "uuid.txt")
            if os.path.exists(uuid_path):
                file.write("\n--- Device info (uuid.txt) ---\n")
                with open(uuid_path, "r") as uuid_file:
                    file.write(uuid_file.read())

    def get_encoding_alias(self):
        alias_dict = {}
        for i in range(len(self.df.index)):
            curr = self.df.iloc[i]
            alias_dict[f"{curr['encoding']}"] = f"{curr['subject_id']}_{curr['session_id']}_{self.note}_{curr['encoding']}"
        return alias_dict

    def run(self):
        if self.options.dry_run:
            return self.dry_run()

        ids = self.obtain_predix_ids()
        for id in ids:
            for sensor in SENSOR_ORDER:
                search_prefix = id + sensor
                file_name = search_prefix + (".pkl" if self.save_format == "pickle" else ".csv")
                self.extract_csv(search_prefix, file_name, id=id)

        self.write_provenance()

    def dry_run(self):
        """Resolve every binary and report, without decoding or writing anything."""
        for file in sorted(os.listdir(self.in_dir)):
            if not file.endswith(".bin"):
                continue
            sensor = sensor_of(file)
            if sensor is not None:
                self.resolve(os.path.join(self.in_dir, file), sensor)

        print("\n" + Resolution.header())
        for res in self.resolutions:
            print(res.row())
        print(f"\n(dry run — {len(self.resolutions)} file(s) inspected, nothing written)")
        return self.resolutions

    def write_provenance(self):
        """Append the per-file format resolution to README.txt.

        packed16 carries no version number, so for those files this table is the
        only record of how a CSV was decoded.
        """
        if not self.resolutions:
            return
        with open(os.path.join(self.out_dir, "README.txt"), "a") as file:
            file.write("\n--- Format resolution ---\n")
            file.write(Resolution.header() + "\n")
            for res in self.resolutions:
                file.write(res.row() + "\n")
            file.write(f"\nMalformed records dropped = {self.malformed}\n")
            conflicts = [r for r in self.resolutions if r.agrees is False]
            if conflicts:
                file.write(f"uuid.txt conflicts = {len(conflicts)} "
                           f"(content used unless on_format_conflict=trust_uuid)\n")

    def resolve(self, full_path, sensor):
        res = detect.resolve(
            full_path, sensor, self.options.format_for(sensor), self.device_version,
            force_new_format=self.options.force_new_format,
            validate_with_uuid=self.options.validate_with_uuid,
            on_conflict=self.options.on_format_conflict,
            threshold=self.options.sniff_threshold,
        )
        self.resolutions.append(res)
        return res

    def read_file(self, full_path, sensor):
        res = self.resolve(full_path, sensor)
        df, dt = formats.read_bin(full_path, res.spec, strict=self.strict)
        self.malformed += df.attrs.get('malformed_records', 0)
        return df, res

    def extract_csv(self, search_prefix, file_name, id=-1):
        self.generate_csv_for_pattern(self.in_dir, file_name, search_prefix,
                                      out_dir=self.out_dir, id=id)

    def generate_csv_for_pattern(self, in_dir, type_prefix: str, search_key: str, out_dir="./", id=-1):
        # 1. Ignore ID Parsing Handling
        if self.ignore_id_parsing:
            file_name = type_prefix # Defaults to id + "ac.csv" or ".pkl"
        else:
            if str(id) in self.encoding_alias.keys():
                alias = self.encoding_alias[str(id)]
                print('=====', id, alias)
                file_name = f"{type_prefix}".replace(id, alias)
            else:   
                sub_id = str(id)[:-2]
                ses_id = str(id)[-2:]
                alias = f"sub-{sub_id}_ses-{ses_id}_{self.note}_"
                file_name = f"{type_prefix}".replace(id, alias)

        print(type_prefix, search_key, '********')
        data_set, spec = self.collect_all_data_by_prefix(in_dir, search_key)

        if data_set is not None:
            os.makedirs(out_dir, exist_ok=True)
            # Counter semantics come from the layout that was actually decoded.
            counter_validity_check(data_set, spec)

            try:
                dt = [datetime.fromtimestamp(int(t), UTC).strftime("%Y/%m/%d %H:%M:%S") for t in data_set['CDCT']]
            except Exception as e:
                print(str(e))

                dt = -1
            data_set['Datetime'] = dt

            if 'ac' in search_key:
                print("perform unit conversion for IMU")
                data_set = unit_conversion_ac(data_set)

            # 2. Save Format Handling
            out_path = os.path.join(out_dir, file_name)
            if self.save_format == "pickle":
                data_set.to_pickle(out_path)
            else:
                data_set.to_csv(out_path, index=False)

    def collect_all_data_by_prefix(self, path, prefix: str):
        """Concatenate every binary matching `prefix`. Returns (df, spec) or (None, None)."""
        files = gather_files_by_prefix(prefix, path)
        if len(files) == 0:
            return None, None

        all_df, spec = [], None
        for file in files:
            sensor = sensor_of(file)
            if sensor is None:
                continue
            df, res = self.read_file(os.path.join(path, file), sensor)
            all_df.append(df)
            spec = res.spec

        if not all_df:
            return None, None
        return pd.concat(all_df), spec


    def obtain_predix_ids(self):
        all_files = [""]
        files = os.listdir(self.in_dir)
        for file in files:
            if file[0].isdigit():
                id = re.search(r'\d+', file)
                if id is not None:
                    id = id.group()
                    if id not in all_files:
                        all_files.append(id)
        return all_files
    
def file_sort(element1: str):
    numeric_index = element1.find(it_prefix)
    numeric_time = element1[numeric_index + len(it_prefix):len(element1)]
    return int(re.sub("\D", "", numeric_time))

def gather_files_by_prefix(prefix: str, path):
    global it_prefix
    it_prefix = prefix
    all_files = []
    files = os.listdir(path)
    for file in files:
        if file.startswith(prefix) and file.endswith('.bin'):
            all_files.append(file)
    all_files.sort(key=file_sort)
    return all_files

def counter_validity_check(df: pd.DataFrame, spec=None):
    """Report how many counter deltas depart from the layout's expected step.

    The expected step comes from the spec that was actually decoded, so this no
    longer has to guess it from the data or branch on a version flag.
    """
    if spec is None:
        print("pass counter check: N/A (no format resolved)")
        return
    # The readers append CDCT/init_CDCT, so the last column is not the counter.
    counter_columns = df[['Counter']] if 'Counter' in df.columns else df.iloc[:, -1:]
    counter_arr = numpy.array(counter_columns).flatten()
    diff_arr = numpy.diff(counter_arr)
    step = spec.tick_step
    # step: nominal. 2*step: one dropped sample. |d| near the modulus: rollover,
    # in either sign depending on whether the column survived as signed.
    check_array = ((diff_arr == step) | (diff_arr == step * 2)
                   | (numpy.abs(diff_arr) > spec.wrap * 0.9))
    print(f"pass counter check: {numpy.all(check_array)} "
          f"({spec.sensor}/{spec.name}, expected step {step})")
    print("and number of non matching samples: " + str(numpy.count_nonzero(check_array == 0)))

def unit_conversion_ac(data_set):
    for c in ['AccX', 'AccY', 'AccZ']:
        data_set[c] = data_set[c] /(2**16-1)*8
    return data_set

def get_t0(file_list):
    pattern = r'\d*[A-Za-z]+(\d+)\.bin$'
    t = sorted([int(match.group(1)) for filename in file_list if (match := re.search(pattern, filename))])
    return t[0]

def get_cdct(df, bin_list, fs=320, counter_bits=16):
    t0 = get_t0(bin_list)
    counter_diff = np.diff(df['Counter']) % (2 ** counter_bits)
    counter_diff = np.insert(counter_diff, 0, 0)
    df['CDCT'] = t0 + np.cumsum(counter_diff) / fs
    return df

def main(in_dir, out_dir, df=None, note="", gradio=True, options=None):
    extractor = DataExtractor(in_dir, out_dir, df=df, note=note, options=options)
    extractor.run()
    if df is not None: print(df.head())
    if gradio: gr.Info("✅ Extraction completed")
    print("operation completed.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--in_dir', type=str, required=True, help="directory where binary files are located")
    parser.add_argument('-o', '--out_dir', type=str, default="./", help="output directory")
    parser.add_argument('--legacy_fs', action='store_true', default=False, help="Use legacy sampling rate 25Hz for CDCT")
    
    # 3. New Command Line Arguments
    parser.add_argument('--save_format', type=str, choices=['csv', 'pickle'], default='csv', help="Format to save extracted data (csv or pickle)")
    parser.add_argument('--ignore_id', action='store_true', default=False, help="Ignore subject and session ID parsing for file names")
    parser.add_argument('--mode', type=str, choices=['dir', 'batch'], default='dir', help="Run mode: 'dir' for single directory of bins, 'batch' for folder of zips")
    parser.add_argument('--force_new_format', action='store_true', default=False,
                        help="Assume v4.7.0+ when the format has to be guessed from the device "
                             "version (i.e. in 'version' mode, or when detection is inconclusive). "
                             "Does not override content detection.")

    # 4. Record layout, per sensor. 'auto' detects from file contents.
    parser.add_argument('--ppg_format', type=str, choices=PPG_FORMAT_CHOICES, default='auto',
                        help="PPG record layout: 'auto' detects from content (default), "
                             "'version' follows uuid.txt, or name a layout explicitly")
    parser.add_argument('--ac_format', type=str, choices=AC_FORMAT_CHOICES, default='auto',
                        help="IMU record layout: 'auto' detects from content (default)")
    parser.add_argument('--ecg_format', type=str, choices=ECG_FORMAT_CHOICES, default='auto',
                        help="ECG record layout: 'auto' detects from content (default)")
    parser.add_argument('--validate_with_uuid', action='store_true', default=False,
                        help="Cross-check the detected layout against uuid.txt and report disagreements")
    parser.add_argument('--on_format_conflict', type=str, choices=CONFLICT_CHOICES, default='warn',
                        help="What to do when content and uuid.txt disagree (default: warn, content wins)")
    parser.add_argument('--sniff_threshold', type=float, default=0.90,
                        help="Minimum detection score to accept a layout (default: 0.90)")
    parser.add_argument('--dry_run', action='store_true', default=False,
                        help="Report the resolved layout for every binary and exit without writing")
    parser.add_argument('--strict_ppg', action='store_true', default=False,
                        help="Raise on records that fail validation instead of dropping and reporting them")

    args = parser.parse_args()
    options = ExtractionOptions.from_args(args)

    if args.mode == 'batch':
        batch_extract_zips(args.in_dir, options=options)
    else:
        main(args.in_dir, args.out_dir, gradio=False, options=options)