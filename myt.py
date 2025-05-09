import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
from dotenv import load_dotenv
import os
import argparse

# Load environment variables
load_dotenv()

# Router configuration with defaults
ROUTER_USERNAME = os.getenv('ROUTER_USERNAME', 'root')
ROUTER_PASSWORD = os.getenv('ROUTER_PASSWORD', 'YWRtaW4%3D')  # Default: Base64 encoded "admin"
ROUTER_IP = os.getenv('ROUTER_IP', '192.168.100.1')
WAN_USERNAME = os.getenv('WAN_USERNAME')
WAN_PASSWORD = os.getenv('WAN_PASSWORD')
LOG_FILE = os.getenv('LOG_FILE', './myt.log')

def log_public_ip(message="Current public IP"):
    """Get the current public IP address and log it with timestamp."""
    try:
        public_ip = requests.get("https://api.ipify.org", timeout=5).text
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a") as f:
            f.write(f"{current_time} - {message}: {public_ip}\n")
        print(f"{message}: {public_ip}")
        return public_ip
    except Exception as e:
        print(f"Failed to get public IP: {e}")
        return None

def get_router_session():
    """Create and return an authenticated session with the router."""
    session = requests.Session()
    
    # First request to get token
    response = session.post(
        f"http://{ROUTER_IP}/asp/GetRandCount.asp", verify=False, timeout=5
    )

    token = (
        response.text.encode("utf-8")
        .decode("utf-8-sig")
        .strip()
        .replace(" ", "")
        .replace("\n", "")
        .replace("\r", "")
    )
    token = token[:48] if len(token) > 48 else token
    print("Got hwtoken")

    # Login request
    data = f"UserName={ROUTER_USERNAME}&PassWord={ROUTER_PASSWORD}&Language=english&x.X_HW_Token={token}"
    response = session.post(
        f"http://{ROUTER_IP}/login.cgi", data=data, verify=False, timeout=5
    )
    print("Successfully logged in")

    # Get onttoken
    response = session.get(f"http://{ROUTER_IP}/index.asp", verify=False, timeout=5)
    soup = BeautifulSoup(response.text, "html.parser")
    onttoken = soup.find(id="onttoken").get("value")
    print("Got onttoken")
    
    return session, onttoken

def reboot_router(session, onttoken, dry_run=False):
    """Reboot the router."""
    if dry_run:
        print("[DRY RUN] Would reboot router with token:", onttoken)
        return

    reboot_data = f'x.X_HW_Token={onttoken}'
    reboot_url = 'http://192.168.100.1/html/ssmp/accoutcfg/set.cgi?x=InternetGatewayDevice.X_HW_DEBUG.SMP.DM.ResetBoard&RequestFile=html/ssmp/accoutcfg/ontmngt.asp'

    try:
        reboot_response = session.post(reboot_url, data=reboot_data, verify=False, timeout=5)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        print("Success restarting the router")
    except:
        print("Error during reboot")

def reconnect_router(session, onttoken, dry_run=False):
    """Reconnect the router by updating WAN configuration."""
    if dry_run:
        print("[DRY RUN] Would reconnect router with:")
        print(f"  - Username: {WAN_USERNAME}")
        print(f"  - Wrong username: {WAN_USERNAME}0")
        print(f"  - Token: {onttoken}")
        return

    wan_url = f"http://{ROUTER_IP}/html/bbsp/wan/complex.cgi?y=InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1&n=InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.X_HW_IPv6.IPv6Prefix.1&m=InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.X_HW_IPv6.IPv6Address.1&RequestFile=html/bbsp/wan/confirmwancfginfo.html"

    wan_wrong_username = f"{WAN_USERNAME}0"
    wan_wrong_data = (
        f"y.Username={wan_wrong_username}&y.Password={WAN_PASSWORD}&x.X_HW_Token={onttoken}"
    )
    wan_data = (
        f"y.Username={WAN_USERNAME}&y.Password={WAN_PASSWORD}&x.X_HW_Token={onttoken}"
    )

    print("Updating WAN Configuration with wrong username")
    session.post(wan_url, data=wan_wrong_data, verify=False, timeout=5)

    print("Waiting for 10 seconds")
    time.sleep(10)

    print("Updating WAN Configuration with correct username")
    session.post(wan_url, data=wan_data, verify=False, timeout=5)

    print("WAN Configuration updated successfully")

def check_wan_credentials():
    """Check if WAN credentials are properly set in environment variables."""
    if not WAN_USERNAME or not WAN_PASSWORD:
        print("Error: WAN_USERNAME and WAN_PASSWORD must be set in environment variables for reconnection")
        print("Please set these variables in your .env file:")
        print("WAN_USERNAME=your_username")
        print("WAN_PASSWORD=your_password")
        return False
    return True

def main():
    parser = argparse.ArgumentParser(description='Router management script')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--reboot', action='store_true', help='Reboot the router')
    group.add_argument('--reconnect', action='store_true', help='Reconnect the router')
    parser.add_argument('--dry-run', action='store_true', help='Simulate the operation without making changes')
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("Running in dry-run mode - no changes will be made")
    
    # Check WAN credentials if reconnect is chosen
    if args.reconnect and not check_wan_credentials():
        return
    
    # Log initial IP
    log_public_ip("Start IP")
    
    # Get authenticated session
    session, onttoken = get_router_session()
    
    if args.reboot:
        reboot_router(session, onttoken, args.dry_run)
        print("Waiting for 120 seconds before final IP check...")
        time.sleep(120)
    elif args.reconnect:
        reconnect_router(session, onttoken, args.dry_run)
        print("Waiting for 10 seconds before final IP check...")
        time.sleep(10)
    
    # Log final IP
    log_public_ip("End   IP")

if __name__ == "__main__":
    main()
