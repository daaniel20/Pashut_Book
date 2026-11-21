"""Check the WhatsApp settings in .env (task 1.1).

Run from the project folder:  python3 server/check_whatsapp.py
It checks that the access token works, that the phone number ID is right,
and that our app is connected to the WhatsApp account (so Meta sends us
messages). If the app isn't connected, it connects it.
It never prints the token.
"""

import json
import sys
import urllib.error
import urllib.request

from settings import ENV_FILE, read_env

DEFAULT_GRAPH_VERSION = "v23.0"


def call(env, method, path):
    version = env.get("WHATSAPP_GRAPH_VERSION") or DEFAULT_GRAPH_VERSION
    request = urllib.request.Request(
        f"https://graph.facebook.com/{version}/{path}",
        headers={"Authorization": f"Bearer {env['WHATSAPP_ACCESS_TOKEN']}"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            message = json.load(error).get("error", {}).get("message", "")
        except ValueError:
            message = ""
        sys.exit(f"❌ Meta answered with error {error.code}: {message}")
    except urllib.error.URLError as error:
        sys.exit(f"❌ Could not reach Meta: {error.reason}")


def main():
    env = read_env()
    if not ENV_FILE.exists():
        sys.exit(f"❌ No .env file at {ENV_FILE}")
    for name in ["WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_BUSINESS_ACCOUNT_ID",
                 "WHATSAPP_ACCESS_TOKEN", "WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN"]:
        if not env.get(name):
            sys.exit(f"❌ {name} is empty in .env")

    number = call(env, "GET", f"{env['WHATSAPP_PHONE_NUMBER_ID']}"
                              "?fields=display_phone_number,verified_name")
    print(f"✅ Token works. Bot number: {number.get('display_phone_number')} "
          f"({number.get('verified_name')})")

    waba = env["WHATSAPP_BUSINESS_ACCOUNT_ID"]
    apps = call(env, "GET", f"{waba}/subscribed_apps").get("data", [])
    if apps:
        print("✅ The app is connected to the WhatsApp account (Meta will send us messages).")
    else:
        call(env, "POST", f"{waba}/subscribed_apps")
        print("✅ The app wasn't connected to the WhatsApp account. Connected it now.")


if __name__ == "__main__":
    main()
