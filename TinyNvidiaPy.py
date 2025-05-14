import subprocess
import platform
import requests
import os
import sys
import psutil  # For process monitoring

def get_gpu_name():
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip().split('\n')[0]
    except subprocess.CalledProcessError:
        return None

def get_os_info():
    return platform.system(), platform.version(), platform.machine()

def lookup_values(type_id, parent_id=0):
    url = "https://www.nvidia.com/Download/API/lookupValueSearch.aspx"
    params = {
        "TypeID": type_id,
        "ParentID": parent_id,
        "LanguageCode": "en-us"
    }
    response = requests.get(url, params=params)
    return response.json() if response.ok else []

def find_gpu_ids(gpu_name):
    product_types = lookup_values(1)
    geforce_type = next((pt for pt in product_types if 'geforce' in pt['Value'].lower()), None)
    if not geforce_type:
        return None

    series_list = lookup_values(2, geforce_type['ID'])
    matched_series = next((s for s in series_list if s['Value'].lower() in gpu_name.lower()), None)
    if not matched_series:
        matched_series = next((s for s in series_list if 'rtx' in s['Value'].lower()), None)
    if not matched_series:
        return None

    families = lookup_values(5, matched_series['ID'])
    matched_family = next((f for f in families if f['Value'].lower() in gpu_name.lower()), None)
    if not matched_family:
        matched_family = families[0]

    return {
        "psid": matched_series['ParentID'],
        "pfid": matched_family['ID']
    }

def get_os_id():
    os_list = lookup_values(3)
    for os_item in os_list:
        val = os_item['Value'].lower()
        if "windows" in val and "64-bit" in val:
            if "windows 11" in val:
                return os_item['ID']
            elif "windows 10" in val:
                return os_item['ID']
    return None

def download_driver(url, filename="nvidia_driver.exe"):
    print(f"Downloading driver from: {url}")
    r = requests.get(url, stream=True)
    total = int(r.headers.get('content-length', 0))
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Downloaded to: {filename}")
    return filename

def install_driver_silently(installer_path):
    print("Launching silent driver installation...")
    process = subprocess.Popen([installer_path, "/s", "-noreboot", "-clean"])
    
    # Monitor the process until it finishes
    print("Waiting for installation to complete...")
    process.wait()  # Waits for the process to finish
    
    print("Installation complete. Deleting installer...")
    os.remove(installer_path)  # Delete the installer after installation

# === Main Logic ===
gpu = get_gpu_name()
os_system, os_version, os_arch = get_os_info()
gpu_ids = find_gpu_ids(gpu)
osid = get_os_id()
lid = 1  # English
whql = 1  # WHQL-certified only

print(f"Detected GPU: {gpu}")
print(f"Detected OS: {os_system} {os_version} ({os_arch})")

if gpu_ids and osid:
    params = {
        "psid": gpu_ids["psid"],
        "pfid": gpu_ids["pfid"],
        "osid": osid,
        "lid": lid,
        "whql": whql
    }
    res = requests.get("https://www.nvidia.com/Download/processDriverSearch.aspx", params=params)
    if res.ok and res.json():
        driver = res.json()[0]
        download_url = driver['DownloadURL']
        version = driver['Version']
        print(f"Latest driver version: {version}")
        exe_path = download_driver(download_url)

        choice = input("Do you want to install the driver now (silent mode)? [y/N]: ").strip().lower()
        if choice == 'y':
            install_driver_silently(exe_path)
        else:
            print("Driver downloaded but not installed.")
    else:
        print("Could not find a matching driver.")
else:
    print("Failed to detect necessary system info.")