# Fingerprint + Face + Awake Authentication

My thesis project. A person only gets access if three checks pass, in this order:

1. Fingerprint matches (optical sensor, matched with SourceAFIS)
2. Face matches the enrolled face
3. Eyes are open (awake check)

If the fingerprint fails, the camera step is skipped and access is denied.

The fingerprint and face images are never kept as plain files. They are encrypted into a vault and each one is logged in a small local blockchain, so you can tell if something was tampered with.

## How it works

```
R307 sensor -> ESP32 -> USB serial -> Python (image rebuilt from packets)
                                           |
                       encrypt (AES-256-GCM) -> vault + chain.json
                                           |
                  decrypt to temp folder -> Java SourceAFIS -> score
                                           |
                          score >= 40 ?  no -> ACCESS DENIED
                                           |
                                          yes
                                           |
                  camera -> YOLOv26n face box -> face_recognition
                                           -> EyeCNN + MediaPipe EAR
                                           |
                         face ok and awake ?  -> GRANTED / DENIED
```

- **Fingerprint:** the ESP32 reads the R307 and sends the raw image packets as hex over serial (`IMAGE_START`, hex lines, `IMAGE_END`). Python rebuilds a 256x288 grayscale image, boosts contrast/sharpness, and passes it on.
- **Matching:** done by a small Java program using the SourceAFIS library. Python calls it with `subprocess` and reads the score from stdout. Score >= `MATCH_THRESHOLD` (40) counts as a match.
- **Face:** YOLOv8n (fine-tuned on a face dataset) finds the face, `face_recognition` compares it with the enrolled encodings (tolerance 0.5).
- **Awake:** a small CNN (`EyeCNN`, 24x24 grayscale) says open/closed, and MediaPipe FaceMesh gives the eye aspect ratio (EAR, threshold 0.22). Both have to say open.
- **Vault + blockchain:** images are encrypted with AES-256-GCM, the key comes from your password through PBKDF2-HMAC-SHA256 (390,000 iterations). Every encrypted file gets a block in `chain.json` with SHA-256 hashes (plain image, ciphertext, previous block). `verify_chain()` checks nothing was changed.

## Repository layout

```
.
├── Thesis_fixed_v8.ipynb        main notebook (training, auth, results)
├── README.md
└── SourceAfis/                  Java matcher
    ├── libs/                    SourceAFIS jar + its dependency jars
    ├── FingerprintMatcher.java
    └── FingerprintMatcher.class
```

The Python side creates these at runtime (inside `PROJECT_DIR`):

```
fingerprint_project/
├── fingerImage/                 temporary enrolled.png / probe.png (deleted after encryption)
└── biometric_blockchain/
    ├── chain.json
    ├── encrypted_vault/         *.enc files
    └── temp_decrypted/          wiped after every match
```

Datasets are not in the repo (too big). You need:

- MRL Eye Dataset, split into `train/` and `val/`, each with `awake/` and `sleepy/` folders
- A folder of your own face photos (`my_face/`)
- Optional, for fine-tuning YOLO: the Kaggle "face detection dataset" by fareselmenshawii

## Hardware

- R307 optical fingerprint sensor
- ESP32 connected to the sensor and to the PC over USB
- Webcam

The ESP32 sketch just has to print the serial format above. Default port in the notebook is `COM5` at 115200 baud, change it if yours is different.

## Setup

### 1. Java matcher

Put the SourceAFIS jar and the jars it depends on inside `SourceAfis/libs/`. Then compile from inside the `SourceAfis` folder:

```
javac -cp "libs/*" FingerprintMatcher.java
```

Quick test with two fingerprint images:

```
java -cp ".;libs/*" FingerprintMatcher match enrolled.png probe.png
```

It should print one number (the score) and nothing else. On Linux/Mac use `:` instead of `;`.

The Python code expects the score on the last line of the output, so don't add extra `println` calls in the Java file.

One thing that looks odd in the code: the class is also called `FingerprintMatcher`, same as the SourceAFIS class, so the SourceAFIS one is written with its full name (`com.machinezoo.sourceafis.FingerprintMatcher`). Leave it like that or the compile breaks. Images are read with `dpi(500)`.

### 2. Python

```
pip install opencv-python mediapipe ultralytics scipy torch torchvision face_recognition pyserial pillow cryptography websockets zeroconf scikit-learn pandas matplotlib
```

`face_recognition` needs dlib, which can be annoying on Windows. If it fails, install the CMake and Visual Studio build tools first.

You also need `java` on your PATH.

### 3. Paths and settings

Open the config cell (cell 2) in the notebook and edit:

| Setting | What it is | Default |
|---|---|---|
| `TRAIN_PATH`, `VAL_PATH` | Eye dataset | `E:\Thesis\mrl-eye-dataset\data\...` |
| `MY_FACE_DIR` | Your face photos | `E:\Thesis\mrl-eye-dataset\data\my_face` |
| `PROJECT_DIR` | Vault, chain, temp images | `E:\Thesis\fingerprint_project` |
| `JAVA_PROJECT_DIR` | Folder with `FingerprintMatcher.class` and `libs/` | found automatically, falls back to `D:\fingerprint_project` |
| `PORT`, `BAUD` | ESP32 serial port | `COM5`, `115200` |
| `WIDTH`, `HEIGHT` | R307 image size | `256`, `288` |
| `MATCH_THRESHOLD` | SourceAFIS score needed | `40.0` |
| `AUTH_TRIGGER_MODE` | `"local"` or `"websocket"` | `"local"` |
| `DELETE_ORIGINAL_AFTER_ENCRYPT` | Delete plain images after encrypting | `True` |

Back up your face photos before the first run. With `DELETE_ORIGINAL_AFTER_ENCRYPT = True` the originals are removed once they are encrypted.

## Running it

Run the notebook cells from the top. Roughly:

1. Imports and config
2. Blockchain/vault and fingerprint functions
3. Eye CNN: dataset, model, training (saves `eye_model.pth`). Skip if you already have the file.
4. Face encodings, YOLO loading (optional fine-tuning cell), eye state functions
5. The final auth cell

You'll be asked for the vault password once per session. Use the same one every time, otherwise old records can't be decrypted.

**First run:** no enrolled finger exists yet, so it asks you to place your finger once. That image is encrypted and logged, then used for all later checks. To replace it, set `RE_ENROLL_ON_START = True` (it re-enrolls once per session).

**Local mode:** press Enter, put your finger on the sensor, then look at the camera if the fingerprint passes. A result window shows each check. It then asks "Scan again? (y/n)".

**Websocket mode:** set `AUTH_TRIGGER_MODE = "websocket"`. The laptop listens on port 8080 and advertises itself as `fingerprint-auth.local` over mDNS. A client (for example a phone app) sends `1` to start an attempt and gets back `1` (granted) or `0` (denied). Type `q` + Enter in the notebook to stop the server.

## Results

The cells after the auth part measure:

- Auth response time (face + awake step, and the Java match time)
- Face recognition accuracy, precision, recall, F1, FAR, FRR
- Eye-state model metrics and confusion matrix
- YOLO mAP, precision, recall, FPS
- Overall system FAR / FRR (face + eye only, the fingerprint is not part of this simulation)

Plots are saved to `runs/detect/val`.

## Known limits

- One enrolled finger, one enrolled user.
- No spoof/liveness check on the fingerprint or the face. A good photo or a fake finger is not handled.
- The overall FAR/FRR numbers are built by pairing the face results with the eye results, not from a live test with real people.
- The blockchain is local and private. It shows tampering, but anyone who can rewrite the whole `chain.json` can still rebuild it. For something real you would keep only hashes on a public chain.
- Tested on Windows only.

## Credits

- [SourceAFIS](https://sourceafis.machinezoo.com/) for fingerprint matching
- Ultralytics YOLOv8
- `face_recognition` (dlib)
- MediaPipe
- MRL Eye Dataset
