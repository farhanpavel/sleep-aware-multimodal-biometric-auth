import subprocess
import os
import serial
import binascii
import time
from PIL import Image, ImageEnhance

PORT    = 'COM5'
BAUD    = 115200
WIDTH   = 256
HEIGHT  = 288

PROJECT_DIR   = r"D:\fingerprint_project"
LIBS_DIR      = os.path.join(PROJECT_DIR, "libs")
IMAGE_DIR     = os.path.join(PROJECT_DIR, "fingerImage")
os.makedirs(IMAGE_DIR, exist_ok=True)

ENROLLED_PATH = os.path.join(IMAGE_DIR, "enrolled.png")
PROBE_PATH    = os.path.join(IMAGE_DIR, "probe.png")

MATCH_THRESHOLD = 40

def run_java_matcher(enrolled_img, probe_img):
    sep       = ";"
    classpath = f"{PROJECT_DIR}{sep}{LIBS_DIR}\\*"

    cmd = [
        "java",
        "-cp", classpath,
        "FingerprintMatcher",
        "match",
        enrolled_img,
        probe_img
    ]

    print(f"🔧 CMD: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip()
        stderr = result.stderr.strip()

        if stderr:
            print(f"⚠️  Java stderr: {stderr}")

        if not output:
            print("❌ Java gave no output.")
            return False, 0.0

        score   = float(output)
        matched = score >= MATCH_THRESHOLD
        return matched, score

    except subprocess.TimeoutExpired:
        print("❌ Java timed out.")
        return False, 0.0
    except ValueError:
        print(f"❌ Unexpected Java output: '{output}'")
        return False, 0.0
    except FileNotFoundError:
        print("❌ Java not found. Is JDK installed and in PATH?")
        return False, 0.0

def enhance_image(image_path):
    img = Image.open(image_path).convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
    img.save(image_path)
    return img

def extract_image_from_packets(raw_bytes, save_path):
    image_data = bytearray()
    idx = 0
    while idx < len(raw_bytes) - 9:
        if raw_bytes[idx:idx+6] == b'\xef\x01\xff\xff\xff\xff':
            pid         = raw_bytes[idx+6]
            length      = (raw_bytes[idx+7] << 8) | raw_bytes[idx+8]
            payload_len = length - 2
            if pid in (0x02, 0x08):
                if idx + 9 + payload_len <= len(raw_bytes):
                    payload = raw_bytes[idx+9 : idx+9+payload_len]
                    for b in payload:
                        image_data.append((b >> 4) * 17)
                        image_data.append((b & 0x0F) * 17)
            idx += 9 + length
        else:
            idx += 1

    expected = WIDTH * HEIGHT
    if len(image_data) >= expected:
        img = Image.frombytes('L', (WIDTH, HEIGHT), bytes(image_data[:expected]))
        img.save(save_path)
        enhance_image(save_path)
        print(f"✅ Image saved: {save_path}")
        return True
    else:
        print(f"❌ Not enough pixels: {len(image_data)} / {expected}")
        return False

def do_scan(save_path, prompt):
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        print(f"✅ Connected to {PORT}")
        print(prompt)

        hex_data   = ""
        receiving  = False
        scan_start = None

        while True:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not line:
                continue

            if line == "IMAGE_START":
                print("📡 Receiving data...")
                receiving  = True
                hex_data   = ""
                scan_start = time.time()

            elif line == "IMAGE_END":
                receiving = False
                print(f"⏱️  Got data in {time.time() - scan_start:.2f}s")
                raw = binascii.unhexlify(hex_data)
                return extract_image_from_packets(raw, save_path)

            elif receiving:
                hex_data += line

    except serial.SerialException as e:
        print(f"❌ Serial error: {e}")
        return False
    except KeyboardInterrupt:
        print("Stopped.")
        return False
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("🔌 Serial closed.")

def main():
    print("=" * 50)
    print("  SourceAFIS Fingerprint Auth (Java backend)")
    print("=" * 50)

    if os.path.exists(ENROLLED_PATH):
        choice = input("\n⚠️  Enrolled print found. Re-enroll? (y/n): ").strip().lower()
        if choice == 'y':
            os.remove(ENROLLED_PATH)
            print("🗑️  Old enrollment deleted.")

    if not os.path.exists(ENROLLED_PATH):
        print("\n[ENROLLMENT]")
        if not do_scan(ENROLLED_PATH, "👆 Place finger to ENROLL..."):
            print("❌ Enrollment failed. Exiting.")
            return
        print("✅ Finger enrolled!\n")
        time.sleep(2)
    else:
        print("✅ Using existing enrolled fingerprint.\n")

    print("\n[VERIFICATION]")
    if not do_scan(PROBE_PATH, "👆 Place finger to VERIFY..."):
        print("❌ Scan failed. Exiting.")
        return

    print("\n🔄 Running SourceAFIS matcher (Java)...")
    matched, score = run_java_matcher(ENROLLED_PATH, PROBE_PATH)

    print("\n" + "=" * 50)
    if matched:
        print(f"  ✅ SUCCESS — Fingerprint matched!")
        print(f"  Score: {score:.1f}  |  Threshold: {MATCH_THRESHOLD}")
    else:
        print(f"  ❌ FAILED  — Fingerprint NOT matched.")
        print(f"  Score: {score:.1f}  |  Threshold: {MATCH_THRESHOLD}")
    print("=" * 50)


if __name__ == "__main__":
    main()