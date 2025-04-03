import hashlib
import hmac
import base64
import json
import re
from http import HTTPStatus
from datetime import datetime, timezone
import aiohttp
import asyncio
import os
from dotenv import load_dotenv

VERB = 'POST'
LOGIN_URL = '/v2/api/login'
CONTROL_URL = '/v2/api/control'
INVERTER_URL = '/v1/api/inverterList'


VERB = 'POST'
LOGIN_URL = '/v2/api/login'
CONTROL_URL = '/v2/api/control'
INVERTER_URL = '/v1/api/inverterList'


def digest(body: str) -> str:
    return base64.b64encode(hashlib.md5(body.encode('utf-8')).digest()).decode('utf-8')


def passwordEncode(password: str) -> str:
    md5Result = hashlib.md5(password.encode('utf-8')).hexdigest()
    return md5Result


def prepare_header(config: dict[str, str], body: str, canonicalized_resource: str) -> dict[str, str]:
    content_md5 = digest(body)
    content_type = 'application/json'

    now = datetime.now(timezone.utc)
    date = now.strftime('%a, %d %b %Y %H:%M:%S GMT')

    encrypt_str = VERB + '\n' + content_md5 + '\n' + content_type + '\n' + date + '\n' + canonicalized_resource
    hmac_obj = hmac.new(config['secret'].encode('utf-8'), msg=encrypt_str.encode('utf-8'), digestmod=hashlib.sha1)
    sign = base64.b64encode(hmac_obj.digest())
    authorization = 'API ' + config['key_id'] + ':' + sign.decode('utf-8')

    header = {'Content-MD5': content_md5, 'Content-Type': content_type, 'Date': date, 'Authorization': authorization}
    return header


async def get_session():
    return aiohttp.ClientSession()


async def login(config):
    session = await get_session()
    body = '{"userInfo":"' + config['username'] + '","password":"' + passwordEncode(config['password']) + '"}'
    header = prepare_header(config, body, LOGIN_URL)
    async with session.post('https://www.soliscloud.com:13333' + LOGIN_URL, data=body, headers=header) as response:
        status = response.status
        result = ''
        r = json.loads(re.sub(r'("(?:\\?.)*?")|,\s*([]}])', r'\1\2', await response.text()))
        if status == HTTPStatus.OK:
            result = r
        else:
            print(f"Warning: {status}")
            result = await response.text()

        await session.close()

        return result['csrfToken']


async def getInverterList(config):
    session = await get_session()
    body = '{"stationId":"' + config['plantId'] + '"}'
    header = prepare_header(config, body, INVERTER_URL)

    async with session.post('https://www.soliscloud.com:13333' + INVERTER_URL, data=body, headers=header) as response:
        inverterList = await response.json()
        inverterId = ''

        for record in inverterList['data']['page']['records']:
            inverterId = record.get('id')

        await session.close()

        return inverterId


def control_battery_charge_body(inverterId, chargeSettings) -> str:
    body = '{"inverterId":"' + inverterId + '", "cid":"103","value":"'
    for index, time in enumerate(chargeSettings):
        body = (
            body
            + str(time['chargeCurrent'])
            + ','
            + str(time['dischargeCurrent'])
            + ','
            + str(time['chargeStartTime'])
            + ','
            + str(time['chargeEndTime'])
            + ','
            + str(time['dischargeStartTime'])
            + ','
            + str(time['dischargeEndTime'])
        )
        if index != 2:
            body = body + ','
    return body + '"}'


async def set_battery_charge_times(token, inverterId: str, config, times):
    session = await get_session()
    body = control_battery_charge_body(inverterId, times)
    headers = prepare_header(config, body, CONTROL_URL)
    headers['token'] = token
    async with session.post('https://www.soliscloud.com:13333' + CONTROL_URL, data=body, headers=headers) as response:
        print(
            'solis_control_battery_charge_v1.py response:'
            + await response.text()
        )

        await session.close()


async def solis_control_battery_charge(hass, config=None, settings=None):
    inverterId = await getInverterList(hass, config)
    token = await login(hass, config)
    await set_battery_charge_times(hass, token, inverterId, config, settings)


def config():
    """
    Load configuration from environment variables and include settings.
    """
    return {
        "key_id": os.getenv("SOLIS_KEY_ID"),
        "secret": os.getenv("SOLIS_SECRET"),
        "username": os.getenv("SOLIS_USERNAME"),
        "password": os.getenv("SOLIS_PASSWORD"),
        "plantId": os.getenv("SOLIS_PLANT_ID")
    }


def settings():
    """
    Load configuration from environment variables and include settings.
    """
    return [
        {
            "chargeCurrent": "50",
            "dischargeCurrent": "50",
            "chargeStartTime": "03:00",
            "chargeEndTime": "04:30",
            "dischargeStartTime": "00:00",
            "dischargeEndTime": "00:00",
        },
        {
            "chargeCurrent": "50",
            "dischargeCurrent": "50",
            "chargeStartTime": "00:00",
            "chargeEndTime": "00:00",
            "dischargeStartTime": "00:00",
            "dischargeEndTime": "00:00",
        },
        {
            "chargeCurrent": "50",
            "dischargeCurrent": "50",
            "chargeStartTime": "00:00",
            "chargeEndTime": "00:00",
            "dischargeStartTime": "00:00",
            "dischargeEndTime": "00:00",
        },
    ]


async def test_solis_set_battery_charge_times(config, settings):
    """
    Test the solis_sync_clock functionality by simulating the process.
    """
    # Ensure all required config values are set
    assert config["key_id"], "SOLIS_KEY_ID environment variable is not set"
    assert config["secret"], "SOLIS_SECRET environment variable is not set"
    assert config["username"], "SOLIS_USERNAME environment variable is not set"
    assert config["password"], "SOLIS_PASSWORD environment variable is not set"
    assert config["plantId"], "SOLIS_PLANT_ID environment variable is not set"

    # Step 1: Get the inverter ID
    inverterId = await getInverterList(config)
    assert inverterId, "Failed to retrieve inverter ID"

    # Step 2: Log in and get the token
    token = await login(config)
    assert token, "Failed to retrieve login token"

    # Step 3: Set the charge times
    await set_battery_charge_times(token, inverterId, config, settings)

    # If no exceptions are raised, the test is considered successful
    print("Test completed successfully.")

def main():
    """
    Main method to execute the test_solis_set_battery_charge_times function.
    """
    # Load environment variables from .env file
    load_dotenv()

    # Get the configuration
    test_config = config()
    test_settings = settings()

    # Run the async test function
    asyncio.run(test_solis_set_battery_charge_times(test_config, test_settings))

if __name__ == "__main__":
    main()
