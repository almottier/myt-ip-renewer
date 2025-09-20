import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
from dotenv import load_dotenv
import os
import argparse
from croniter import croniter
import signal
import sys

load_dotenv()
ROUTER_USERNAME = os.getenv('ROUTER_USERNAME', 'root')
ROUTER_PASSWORD = os.getenv('ROUTER_PASSWORD', 'YWRtaW4%3D')
ROUTER_IP = os.getenv('ROUTER_IP', '192.168.100.1')
WAN_USERNAME = os.getenv('WAN_USERNAME')
WAN_PASSWORD = os.getenv('WAN_PASSWORD')
LOG_FILE = os.getenv('LOG_FILE', './myt.log')
CRON_SCHEDULE = os.getenv('CRON_SCHEDULE')

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

    data = f"UserName={ROUTER_USERNAME}&PassWord={ROUTER_PASSWORD}&Language=english&x.X_HW_Token={token}"
    response = session.post(
        f"http://{ROUTER_IP}/login.cgi", data=data, verify=False, timeout=5
    )
    print("Successfully logged in")

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

def validate_cron_schedule(cron_expr):
    """Validate a cron expression."""
    try:
        croniter(cron_expr)
        return True
    except Exception as e:
        print(f"Invalid cron expression '{cron_expr}': {e}")
        return False

def get_next_run_time(cron_expr):
    """Get the next run time for a cron expression."""
    try:
        cron = croniter(cron_expr, datetime.now())
        return cron.get_next(datetime)
    except Exception as e:
        print(f"Error calculating next run time: {e}")
        return None

def run_scheduled_task(operation, dry_run=False):
    """Run the specified operation (reboot or reconnect)."""
    print(f"\n{'='*50}")
    print(f"Running scheduled {operation} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    if operation == 'reconnect' and not check_wan_credentials():
        return False
    
    log_public_ip("Start IP")
    
    try:
        session, onttoken = get_router_session()
        
        if operation == 'reboot':
            reboot_router(session, onttoken, dry_run)
            print("Waiting for 120 seconds before final IP check...")
            time.sleep(120)
        elif operation == 'reconnect':
            reconnect_router(session, onttoken, dry_run)
            print("Waiting for 10 seconds before final IP check...")
            time.sleep(10)
        
        log_public_ip("End   IP")
        return True
        
    except Exception as e:
        print(f"Error during scheduled {operation}: {e}")
        return False

def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    print(f"\nReceived signal {signum}. Shutting down gracefully...")
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description='Router management script')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--reboot', action='store_true', help='Reboot the router')
    group.add_argument('--reconnect', action='store_true', help='Reconnect the router')
    group.add_argument('--schedule', action='store_true', help='Run on a schedule defined by CRON_SCHEDULE env var')
    parser.add_argument('--dry-run', action='store_true', help='Simulate the operation without making changes')
    parser.add_argument('--operation', choices=['reboot', 'reconnect'], 
                       help='Operation to perform when using --schedule (default: reconnect)')
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("Running in dry-run mode - no changes will be made")
    
    # Handle schedule mode
    if args.schedule:
        if not CRON_SCHEDULE:
            print("Error: CRON_SCHEDULE environment variable must be set for schedule mode")
            print("Example: CRON_SCHEDULE='0 2 * * *' (runs daily at 2 AM)")
            return
        
        if not validate_cron_schedule(CRON_SCHEDULE):
            return
        
        operation = args.operation or 'reconnect'
        
        if operation == 'reconnect' and not check_wan_credentials():
            return
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print(f"Starting scheduled {operation} mode with cron: {CRON_SCHEDULE}")
        print("Press Ctrl+C to stop")
        
        while True:
            next_run = get_next_run_time(CRON_SCHEDULE)
            if next_run:
                print(f"Next {operation} scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                
                sleep_seconds = (next_run - datetime.now()).total_seconds()
                if sleep_seconds > 0:
                    print(f"Sleeping for {sleep_seconds:.0f} seconds...")
                    time.sleep(sleep_seconds)
                
                run_scheduled_task(operation, args.dry_run)
            else:
                print("Error calculating next run time. Exiting.")
                break
        return
    
    if args.reconnect and not check_wan_credentials():
        return
    
    log_public_ip("Start IP")
    session, onttoken = get_router_session()
    
    if args.reboot:
        reboot_router(session, onttoken, args.dry_run)
        print("Waiting for 120 seconds before final IP check...")
        time.sleep(120)
    elif args.reconnect:
        reconnect_router(session, onttoken, args.dry_run)
        print("Waiting for 10 seconds before final IP check...")
        time.sleep(10)
    
    log_public_ip("End   IP")

if __name__ == "__main__":
    main()
