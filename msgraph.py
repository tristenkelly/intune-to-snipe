import requests
import os
from dotenv import load_dotenv
import time

scope = ['https://graph.microsoft.com/.default']
BASE_URL = "https://graph.microsoft.com/v1.0"
access_token = None


def create_variables(): #grab variables from .env
    load_dotenv('.env')
    global client_id, client_secret, tenant_id, snipe_token, snipe_tenant, snipeheaders
    client_id = os.environ.get('CLIENT-ID')
    client_secret = os.environ.get('CLIENT-SECRET')
    tenant_id = os.environ.get('TENANT-ID')
    snipe_token = os.environ.get('SNIPE-API')
    snipe_tenant = os.environ.get('SNIPE-TENANT')
    if not client_id or not client_secret or not tenant_id or not snipe_token:
        raise ValueError("Environment variables for client_id, client_secret, tenant_id, snipe_token, snipe_tenant or snipeheaders are not set or invalid.")
    snipeheaders = {
        "Authorization": f"Bearer {snipe_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
def get_access_token(): #convert client creds to usable access token
    url = f"https://login.microsoft.com/{tenant_id}/oauth2/v2.0/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": " ".join(scope)
    }
    
    response = requests.post(url, headers=headers, data=data)
    
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        response.raise_for_status() 

def get_devices(): #get devices from msgraph
    global access_token 
    if not access_token: 
        access_token = get_access_token()

    url = (f"{BASE_URL}/deviceManagement/managedDevices")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('value', [])
    else:
        response.raise_for_status()

def get_snipe_devices(): #accurate list of pre-existing snipe devices
    url = f"{snipe_tenant}/hardware"
    headers = snipeheaders
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('rows', [])
    else:
        response.raise_for_status()
        
def get_models():
    url = f"{snipe_tenant}/models"
    headers = snipeheaders
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        models = response.json().get('rows', [])
        name_map = {model['name']: model['id'] for model in models if model.get('name')}
        number_map = {model['model_number']: model['id'] for model in models if model.get('model_number')}
        return name_map, number_map
    else:
        response.raise_for_status()
        
def get_users():
    url = f"{snipe_tenant}/users"
    headers = snipeheaders
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        users = response.json().get('rows', [])
        user_map = {user['email']: user['id'] for user in users if user.get('email')}
        return user_map
    else:
        response.raise_for_status()
        
def push_devices(): #push grabbed devices to Snipe
    url = f"{snipe_tenant}/hardware"
    headers = snipeheaders 

    devices = get_devices()
    name_map, number_map = get_models()
    snipe_devices = get_snipe_devices()
    snipe_serial_map = {dev.get('serial', '').strip(): dev for dev in snipe_devices if dev.get('serial')}
    user_map = get_users()
    for device in devices:
        model_name = device.get('model', 'Unknown Model')
        model_id = name_map.get(model_name)
        user_email = device.get('emailAddress', 'Unknown User')
        user_id = user_map.get(user_email)
        #If not found by name try model number
        if not isinstance(model_id, int):
            model_id = number_map.get(model_name)
            if isinstance(model_id, int):
                print(f"Model '{model_name}' matched by model number.")
            else:
                print(f"Model '{model_name}' not found by name or model number. Skipping device {device.get('deviceName')}.")
                continue

        serial = device.get('serialNumber', '').strip()
        data = {
            "name": device.get('deviceName', 'Unknown Device'),
            "serial": serial,
            "asset_tag": device.get('deviceName', None),
            "status_id": 2, 
            "manufacturer": device.get('manufacturer', 'Unknown Manufacturer'),
            "model_id": model_id,
            "last_audit_date": device.get('lastUpdatedDateTime', None),
            "checkout_to_type": "user",
            "assigned_user": user_id,
        }
        if serial and serial in snipe_serial_map:
            snipe_id = snipe_serial_map[serial].get('id')
            patch_url = f"{url}/{snipe_id}"
            response = requests.patch(patch_url, headers=headers, json=data)
            action = "updated"
        else:
            response = requests.post(url, headers=headers, json=data)
            action = "created"
        time.sleep(1) #added to avoid ratelimit

        if response.status_code in (200, 201):
            try:
                response_data = response.json()
                status = response_data.get('status', '').lower()
                if status == 'success':
                    print(f"Successfully {action} device {device['deviceName']} (status: success)")
                elif status == 'error':
                    print(f"Device {device['deviceName']} {action} error: {response_data}")
                else:
                    print(f"Device {device['deviceName']} {action} returned unknown status: {status}")
            except Exception as ex:
                print(f"Device {device['deviceName']} {action} (201/200) but could not parse status: {ex}")
        else:
            print(f"Failed to {action} device {device['deviceName']}: {response.status_code} - {response.text}")
            
if __name__ == "__main__":
    try:
        create_variables()
        devices = get_devices()
        if devices:
            print(f"Found {len(devices)} devices.")
            push_devices()
        else:
            print("No devices found.")
    except Exception as e:
        print(f"An error occurred: {e}")