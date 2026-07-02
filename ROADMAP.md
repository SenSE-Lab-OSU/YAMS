# ROADMAP

## Known Issues / Future Work

### data_extraction.py

- **Filter duplicate counter rows in v4.7.0+ readers** (`read_ppg_bin_v2`, `read_ac_bin_v2`):
  The new format occasionally produces records where the counter did not advance (`diff == 0`), resulting in duplicate timestamps. The old format handled this implicitly via the `-1` sentinel + `dropna`. The fix is one line after `df = pd.DataFrame(arr, columns=labels)` in each v2 reader:
  ```python
  df = df[df['Counter'].diff().ne(0).fillna(True)]
  ```
  Observed counts in sample data: ~3,400 duplicates in PPG, ~10,400 in AC.
