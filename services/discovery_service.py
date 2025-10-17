import socket
import uuid

def discover_onvif_cameras(nvr_ip):
    """Scans the network using a manual UDP probe for ONVIF cameras."""
    print(f"Starting manual ONVIF discovery on IP: {nvr_ip}...")
    
    probe_message = f"""
    <s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing">
        <s:Header><a:Action s:mustUnderstand="1">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action><a:MessageID>uuid:{uuid.uuid4()}</a:MessageID><a:ReplyTo><a:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:Address></a:ReplyTo><a:To s:mustUnderstand="1">urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To></s:Header>
        <s:Body><Probe xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery"><d:Types xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dp0="http://www.onvif.org/ver10/network/wsdl">dp0:NetworkVideoTransmitter</d:Types></Probe></s:Body>
    </s:Envelope>
    """.strip().encode('utf-8')

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(3.0)
        sock.bind((nvr_ip, 0))
        sock.sendto(probe_message, ('239.255.255.250', 3702))

        discovered_ips = set()
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                ip_address = addr[0]
                discovered_ips.add(ip_address)
            except socket.timeout:
                break 
        
        sock.close()
        
        discovered_cameras = [{'ip': ip} for ip in discovered_ips]
        print(f"Discovery finished. Found {len(discovered_cameras)} device(s).")
        return discovered_cameras
    except Exception as e:
        print(f"An error occurred during manual discovery: {e}")
        return []