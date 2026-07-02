# Migration: `GyroX/Y/Z` → `QuatX/Y/Z`

## What changed

The IMU CSV column names `GyroX`, `GyroY`, `GyroZ` have been renamed to `QuatX`, `QuatY`, `QuatZ` across all firmware versions.

Any analysis pipeline that reads the accelerometer CSV output from YAMS and references `GyroX`, `GyroY`, or `GyroZ` by name will break and must be updated.

## Why

The three `float32` fields following the accelerometer axes were always output by the device firmware as the **vector part of a unit quaternion** (x, y, z), not as gyroscope angular velocity. This was confirmed by inspecting the sensor readings:

- Values are bounded in the range `[-1, 1]`
- The vector magnitude `sqrt(x² + y² + z²)` is always `≤ 1`
- The reconstructed scalar component `w = sqrt(1 - x² - y² - z²)` is always `≥ 0`

None of these properties are consistent with gyroscope output (angular velocity in rad/s or deg/s), which is unbounded. The original column name `GyroX/Y/Z` was a firmware labelling convention that did not reflect the actual data.

## What the data actually is

The device runs an AHRS filter internally and stores the **compressed unit quaternion** — only the vector part (x, y, z) — to save storage space. The scalar component `w` is omitted because it is fully recoverable from the other three:

```python
import numpy as np

w = np.sqrt(np.clip(1 - df['QuatX']**2 - df['QuatY']**2 - df['QuatZ']**2, 0, None))
```

This holds exactly because AHRS always produces a unit quaternion and the firmware enforces `w ≥ 0` (rotation angle ≤ 180°).

## How to update your analysis

### Rename on load

The minimal fix — rename the columns when loading existing CSVs so downstream code continues to work:

```python
df = pd.read_csv("ac.csv", index_col=0)
df = df.rename(columns={"GyroX": "QuatX", "GyroY": "QuatY", "GyroZ": "QuatZ"})
```

### Re-extract from binary

If you have the original `.bin` files, re-running YAMS data extraction will produce CSVs with the correct `QuatX/Y/Z` column names directly.

## What you can do with QuatX/Y/Z

### Reconstruct the full quaternion

```python
w = np.sqrt(np.clip(1 - df['QuatX']**2 - df['QuatY']**2 - df['QuatZ']**2, 0, None))
# full quaternion: (w, QuatX, QuatY, QuatZ)
```

### Convert to Euler angles (pitch, roll, yaw)

```python
x, y, z = df['QuatX'], df['QuatY'], df['QuatZ']
w = np.sqrt(np.clip(1 - x**2 - y**2 - z**2, 0, None))

roll  = np.arctan2(2*(w*x + y*z), 1 - 2*(x**2 + y**2))   # rotation around X
pitch = np.arcsin(np.clip(2*(w*y - z*x), -1, 1))           # rotation around Y
yaw   = np.arctan2(2*(w*z + x*y), 1 - 2*(y**2 + z**2))    # rotation around Z

# convert to degrees if needed
roll_deg  = np.degrees(roll)
pitch_deg = np.degrees(pitch)
yaw_deg   = np.degrees(yaw)
```

### Remove gravity from accelerometer

Rotating the accelerometer reading into the world frame removes the tilt artifact:

```python
# Gravity vector in world frame (m/s²)
g_world = np.array([0, 0, 9.81])

# For each sample, rotate g_world back to sensor frame using q* (conjugate)
# then subtract from measured acceleration
# (simplest approach: use scipy.spatial.transform.Rotation)
from scipy.spatial.transform import Rotation

quats = np.column_stack([w, x, y, z])  # scalar-first convention
R = Rotation.from_quat(np.column_stack([x, y, z, w]))  # scipy uses scalar-last
acc_world = R.apply(df[['AccX', 'AccY', 'AccZ']].values)
linear_acc = acc_world - g_world
```

## What is no longer possible

Raw gyroscope (angular velocity) data is not available from any version of this firmware. Algorithms that require raw gyro — such as running a custom AHRS filter (Madgwick, Mahony, Kalman) — cannot be applied to this dataset.
