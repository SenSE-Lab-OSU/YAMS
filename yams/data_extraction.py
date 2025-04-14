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

def data_extraction_interface():
    # in_files = gr.File(file_count="multiple")
    in_dir = gr.Text("/path/to/binary/data", label="Input directory")
    out_dir = gr.Text("/path/to/output", label="Output directory")

    legacy_fs = gr.Checkbox(False, label="(Uncommon) legacy sampling rate")

    btn = gr.Button("Extract raw data")
    btn.click(main, inputs=[in_dir, out_dir, legacy_fs])


class DataExtractor():
    def __init__(self, in_dir, out_dir, legacy_fs=False):
        if legacy_fs:
            self.sample_tick = 200
        else:
            self.sample_tick = 320

        print(f"sampling tick set to {self.sample_tick}")

        self.in_dir = in_dir
        self.out_dir = out_dir

        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(self.out_dir, "README.txt"), "w") as file:
            file.write(f"Raw data directory = {self.in_dir}\n")
            file.write(f"Legacy sampling rate = {legacy_fs} (True: 25 Hz, False: 32 Hz)\n")
            file.write(f"\nMore MotionSenSE utility available at https://github.com/SenSE-Lab-OSU/YAMS\n")

        self.ppg_labels = ["ir1", "ir2", "g1", "g2",  "Timestamp", "Counter"]
        self.ppg_formats = ["<i", "<i", "<i", "<i", "<i", "<i"]

        self.acc_labels = ["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ", "ENMO", "Timestamp", "Counter"]
        self.acc_formats = ["<h", "<h", "<h", "<f", "<f", "<f", "<f", "<i", "<i"]

    def run(self):
        ids = self.obtain_predix_ids()
        for id in ids:            
            search_prefix = id + "ac"
            file_name = search_prefix + ".csv"
            self.extract_csv(search_prefix, file_name, self.acc_labels, self.acc_formats)

            search_prefix = id + "ppg"
            file_name = search_prefix + ".csv"
            self.extract_csv(search_prefix, file_name, self.ppg_labels, self.ppg_formats)

    def extract_csv(self, search_prefix, file_name, labels, formats):
        self.generate_csv_for_pattern(self.in_dir, file_name, search_prefix, labels, formats, out_dir=self.out_dir)

    def generate_csv_for_pattern(self, in_dir, type_prefix: str, search_key: str, labels, formats, out_dir="./"):
        file_name = f"{type_prefix}"
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

def main(in_dir, out_dir, legacy_fs=False, gradio=True):
    extractor = DataExtractor(in_dir, out_dir, legacy_fs=legacy_fs)
    extractor.run()

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
    
