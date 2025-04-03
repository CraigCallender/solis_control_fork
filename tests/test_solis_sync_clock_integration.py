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


def control_time_body(inverterId: str, currentTime: datetime) -> str:
    body = (
        '{"inverterId":"' + inverterId + '", "cid":"56", "value":"' + currentTime.strftime('%Y-%m-%d %H:%M:%S') + '"}'
    )
    return body


async def set_updated_time(token, inverterId: str, config, currentTime: datetime):
    session = await get_session()
    body = control_time_body(inverterId, currentTime)
    headers = prepare_header(config, body, CONTROL_URL)
    headers['token'] = token
    async with session.post('https://www.soliscloud.com:13333' + CONTROL_URL, data=body, headers=headers) as response:
        print(
            'solis_sync_clock.py response:'
            + await response.text()
        )

        await session.close()


async def solis_sync_clock(config=None):
    inverterId = await getInverterList(config)
    token = await login(config)
    await set_updated_time(token, inverterId, config, datetime.now())


def config():
    """
    Load configuration from environment variables.
    """
    return {
        "key_id": os.getenv("SOLIS_KEY_ID"),
        "secret": os.getenv("SOLIS_SECRET"),
        "username": os.getenv("SOLIS_USERNAME"),
        "password": os.getenv("SOLIS_PASSWORD"),
        "plantId": os.getenv("SOLIS_PLANT_ID"),
    }


async def test_solis_sync_clock(config):
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

    # Step 3: Set the updated time
    current_time = datetime.now()
    await set_updated_time(token, inverterId, config, current_time)

    # If no exceptions are raised, the test is considered successful
    print("Test completed successfully.")

def main():
    """
    Main method to execute the test_solis_sync_clock function.
    """
    # Load environment variables from .env file
    load_dotenv()

    # Get the configuration
    test_config = config()

    # Run the async test function
    asyncio.run(test_solis_sync_clock(test_config))

if __name__ == "__main__":
    main()
