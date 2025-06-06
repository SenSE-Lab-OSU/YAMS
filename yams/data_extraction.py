# original credit: https://github.com/SenSE-Lab-OSU/MotionSenseHRV4Flash/blob/main/DataExtraction/data_extraction.py
import os
import sys
import struct
import re
import datetime
import traceback
import argparse
import pandas as pd
import re
import numpy as np
import numpy
from datetime import datetime, UTC
import gradio as gr
import zipfile
import tempfile

def data_extraction_pro_interface():
    in_file = gr.File(file_types=[".zip"])
    out = gr.DownloadButton(label="No data to be downloaded", interactive=False)

    in_file.change(extract_zip, inputs=in_file, outputs=out)

    with gr.Accordion(label="Help", open=False):
        gr.Markdown("## Data extraction pro mode")

def extract_zip(zip_path):
    df = get_session_encoding()
    if zip_path is not None:
        with tempfile.TemporaryDirectory() as tmpdir:
            print(zip_path)
            print(tmpdir)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)

            print("Contents:", os.listdir(tmpdir))
            devices = os.listdir(tmpdir)
            for dev in devices:
                in_dir = os.path.join(tmpdir, dev)
                print("Before extraction contents:", os.listdir(in_dir))
        
                main(in_dir, in_dir, legacy_fs=False, df=df, note=dev)
                print("After extraction contents:", os.listdir(in_dir))

            out_zip_path = os.path.join(tempfile.gettempdir(),
                                    os.path.basename(zip_path).replace('.zip', '_extracted.zip'))
            print(f"output will be saved to {out_zip_path}")

            with zipfile.ZipFile(out_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(tmpdir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, start=tmpdir)
                        zipf.write(file_path, arcname)
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

    legacy_fs = gr.Checkbox(False, label="(Uncommon) legacy sampling rate")

    btn = gr.Button("Extract raw data")

    with gr.Accordion("Encoding mapping"):
        df = get_session_encoding()
        dataframe = gr.DataFrame(value=df)

    btn.click(main, inputs=[in_dir, out_dir, legacy_fs, dataframe, note])


class DataExtractor():
    def __init__(self, in_dir, out_dir, legacy_fs=False, df=None, note=""):
        if legacy_fs:
            self.sample_tick = 200
        else:
            self.sample_tick = 320

        self.note = note

        self.df = df

        if self.df is not None:
            self.encoding_alias = self.get_encoding_alias()
        else:
            self.encoding_alias = {}

        print(f"sampling tick set to {self.sample_tick}")

        self.in_dir = in_dir
        self.out_dir = out_dir

        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(self.out_dir, "README.txt"), "w") as file:
            file.write(f"Raw data directory = {self.in_dir}\n")
            file.write(f"Legacy sampling rate = {legacy_fs} (True: 25 Hz, False: 32 Hz)\n")
            file.write(f"\I m-sense with YAMS at https://github.com/SenSE-Lab-OSU/YAMS\n")

        self.ppg_labels = ["ir1", "ir2", "g1", "g2",  "Timestamp", "Counter"]
        self.ppg_formats = ["<i", "<i", "<i", "<i", "<i", "<i"]

        self.acc_labels = ["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ", "ENMO", "Timestamp", "Counter"]
        self.acc_formats = ["<h", "<h", "<h", "<f", "<f", "<f", "<f", "<i", "<i"]

    def get_encoding_alias(self):
        alias_dict = {}
        for i in range(len(self.df.index)):
            curr = self.df.iloc[i]
            alias_dict[f"{curr['encoding']}"] = f"{curr['subject_id']}_{curr['session_id']}_{self.note}_{curr['encoding']}"
        print(alias_dict)
        return alias_dict

    def run(self):
        ids = self.obtain_predix_ids()
        for id in ids:            
            search_prefix = id + "ac"
            file_name = search_prefix + ".csv"
            self.extract_csv(search_prefix, file_name, self.acc_labels, self.acc_formats, id=id)

            search_prefix = id + "ppg"
            file_name = search_prefix + ".csv"
            self.extract_csv(search_prefix, file_name, self.ppg_labels, self.ppg_formats, id=id)

    def extract_csv(self, search_prefix, file_name, labels, formats, id=-1):
        self.generate_csv_for_pattern(self.in_dir, file_name, search_prefix, labels, formats, out_dir=self.out_dir, id=id)

    def generate_csv_for_pattern(self, in_dir, type_prefix: str, search_key: str, labels, formats, out_dir="./", id=-1):
        if str(id) in self.encoding_alias.keys():
            alias = self.encoding_alias[str(id)]
            print('=====', id, alias)
            file_name = f"{type_prefix}".replace(id, alias)
        else:   
            file_name = f"{self.note}{type_prefix}"
        print(type_prefix, search_key)
        data_set = self.collect_all_data_by_prefix(in_dir, search_key, labels, formats)
        if data_set is not None:
            os.makedirs(out_dir, exist_ok=True)
            counter_validity_check(data_set)

            # Datetime str
            dt = [datetime.fromtimestamp(int(t), UTC).strftime("%Y/%m/%d %H:%M:%S") for t in data_set['CDCT']]
            data_set['Datetime'] = dt

            if 'ac' in search_key:
                print("perform unit conversion for IMU")
                data_set = unit_conversion_ac(data_set)

            data_set.to_csv(os.path.join(out_dir, file_name))

    def collect_all_data_by_prefix(self, path, prefix: str, labels: list[str], types: list[str]):
        total_errors = 0

        all_data = []
        for element in range(len(labels)):
            all_data.append([])

        files = gather_files_by_prefix(prefix, path)  

        if len(files) == 0:
            return
        for file in files:
            full_path = os.path.join(path, file)
            print("full path: ", full_path)
            test_file = open(full_path, "rb")
            data = test_file.read()
            if len(data) != 0:
                total_errors += process_data(data, all_data, types)
            else:
                print("Warning: found empty file!")

        full_dict = {}
        for index in range(len(labels)):
            full_dict[labels[index]] = all_data[index]

        dataset = pd.DataFrame(full_dict)
        dataset = get_cdct(dataset, files, fs=self.sample_tick)

        return dataset


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
    

def process_data_test(data) -> int:
    errors = 0
    check_array = [1, 2, 3, 4, 5, 6]
    for data_byte in range(0, len(data), 2):
        result = struct.unpack("<h", data[data_byte:data_byte + 2])[0]
        # print(result)
        inx = data_byte // 2 % 6
        if (result != check_array[inx]):
            # print("error: got " + str(result[0]) + " expected " + str(check_array[data_byte//2 % 6]))
            errors += 1
    print("errors: " + str(errors))
    return errors


def calculate_file_end(file):
    index = -1
    subtract_length = 0
    while file[index] == 0xff:
        subtract_length += 1
        index -= 1
    return subtract_length


struct_key = {"f": 4,
              "h": 2,
              "I": 4,
              "i": 4,
              "H": 2,
              "Q": 8
              }


def process_data(data, categories: list[list], format: list, use_check=False) -> int:
    # we always assume that the last category is the packet counter
    # assert len(categories) == len(format)
    errors = 0

    skip_code = 1
    counter_value = 1
    current_index = 0
    data_position = 0
    num_of_categories = len(categories)
    end_trim_size = calculate_file_end(data)
    data_length = len(data) - end_trim_size
    while data_position + struct_key[format[current_index][1]] <= data_length:
        try:

            length = struct_key[format[current_index][1]]
            data_byte = data[data_position:data_position + length]
            data_position += length
            result = struct.unpack(format[current_index], data_byte)[0]

            if result == 4294967295:
                continue
            # print(result)
            categories[current_index].append(result)
            current_index += 1
            if current_index >= num_of_categories:
                current_index = 0
                if use_check:
                    # we are on the last category, which means we are looking at the counter
                    if (result != counter_value):
                        print("error: got " + str(result) + " expected " + str(counter_value))
                        errors += 1
                    counter_value += 1


        except Exception as e:
            errors += 1
            print(e)
    
    if len(categories[0]) > len(categories[1]):
        print("0xff-trim issue found, fixing...")
        categories[0].pop()

    resultant_end_trim_workaround(categories)

    if len(categories[0]) > len(categories[1]):
        print("0xff-trim issue found, fixing...")
        categories[0].pop()

    resultant_end_trim_workaround(categories)

    print("errors: " + str(errors))
    return errors


def resultant_end_trim_workaround(categories):
    length_array = []
    for element in categories:
        length_array.append(len(element))

    max_diff = numpy.max(length_array) - numpy.min(length_array)
    if max_diff == 0:
        return
    if max_diff == 1:
        print("warning: end length of array differs by 1. Implementing fix.")
        print("mismatch array: " + str(length_array))
        max_value = max(length_array)
        for element in categories:
            if max_value == len(element):
                element.pop()
    elif max_diff > 1:
        print("error: end lengths of array differs by too much. Data is potentially corrupt.")
        print("mismatch array: " + str(length_array))


    max_diff = numpy.max(length_array) - numpy.min(length_array)
    if max_diff == 0:
        return
    if max_diff == 1:
        print("warning: end length of array differs by 1. Implementing fix.")
        print("mismatch array: " + str(length_array))
        max_value = max(length_array)
        for element in categories:
            if max_value == len(element):
                element.pop()
    elif max_diff > 1:
        print("error: end lengths of array differs by too much. Data is potentially corrupt.")
        print("mismatch array: " + str(length_array))

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


def counter_validity_check(df: pd.DataFrame):
    counter_columns = df.iloc[:, -1:]
    counter_arr = numpy.array(counter_columns).flatten()
    diff_arr = numpy.diff(counter_arr)
    check_array = (diff_arr == 5) | (diff_arr == 10) | (diff_arr < -65000)
    print("pass counter check: " + str(numpy.all(check_array)))
    print("and number of non matching samples: " + str(numpy.count_nonzero(check_array == 0)))


def unit_conversion_ac(data_set):
    for c in ['AccX', 'AccY', 'AccZ']:
        data_set[c] = data_set[c] /(2**16-1)*8
    return data_set

# get init time
def get_t0(file_list):
    pattern = r'\d*[A-Za-z]+(\d+)\.bin$'
    t = sorted([int(match.group(1)) for filename in file_list if (match := re.search(pattern, filename))])
    return t[0]

# CDCT: calculated data collection time
def get_cdct(df, bin_list, fs=320):
    t0 = get_t0(bin_list)

    # fs = 10*32 if 'ac' in bin_list[0] else 5*64
    counter_diff = np.diff(df['Counter']) % (2^16 - 1)
    counter_diff = np.insert(counter_diff, 0, 0)

    df['CDCT'] = t0 + np.cumsum(counter_diff) / fs

    return df

def main(in_dir, out_dir, legacy_fs=False, df=None, note="", gradio=True):
    extractor = DataExtractor(in_dir, out_dir, legacy_fs=legacy_fs, df=df, note=note)
    extractor.run()

    if df is not None: print(df.head())

    if gradio: gr.Info("✅ Extraction completed")
    print("operation completed.")
    # except Exception as e:
    #     # gr.Error(str(e)) if gradio else print(str(e))
    #     print(str(e))
    #     print("operation completed with error")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--in_dir', type=str, help="directory where binary files are located")
    parser.add_argument('-o', '--out_dir', type=str, default="./", help="output directory")
    parser.add_argument('--legacy_fs', action='store_true', default=False, help="Use legacy sampling rate 25Hz for CDCT")

    args = parser.parse_args()

    main(args.in_dir, args.out_dir, legacy_fs=args.legacy_fs, gradio=False)
    
