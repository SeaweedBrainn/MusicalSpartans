"""Read-only session diagnostic. Never prints the QR, ID, key or response body."""
import argparse
import getpass
import hashlib
import json
from pathlib import Path

import httpx
from session_qr import SessionReadError, parse_link, read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', help='Local photo or screenshot containing the session QR')
    args = parser.parse_args()
    if args.image:
        from extract import load_image
        from qr_reader import scan_qr
        scan = scan_qr(load_image(Path(args.image).read_bytes()))
        if not scan.payload:
            print(json.dumps({'qr_decoded': False, 'outline_detected': scan.detected, 'multiple_codes': scan.ambiguous}))
            return
        payload = scan.payload
    else:
        payload = getpass.getpass('Paste the complete game QR link (hidden): ').strip()
    link = parse_link(payload)
    if link is None:
        print(json.dumps({'qr_link_valid': False, 'next_step': 'Check exact API origin, session path, and one read-key parameter. Do not paste keys into chat.'}))
        return
    origin, sid, key = link
    output = {'qr_link_valid': True, 'api_origin': origin,
              'session_fingerprint': hashlib.sha256(sid.encode()).hexdigest()[:12]}
    with httpx.Client(base_url=origin, timeout=15, trust_env=False, follow_redirects=False) as client:
        try:
            with client.stream('GET', '/health') as response:
                output['health_http'] = response.status_code
        except httpx.HTTPError:
            output['health_http'] = None
        try:
            data = read(client, f'/v1/sessions/{sid}/runs?after_sequence=0&limit=1', key, 512*1024, stage='list_runs')
            page = json.loads(data)
            output.update(session_http=200, completed_runs_in_first_page=len(page.get('runs', [])), has_more=page.get('has_more'))
        except SessionReadError as error:
            output.update(error.diagnostic())
            output['next_step'] = str(error)
        except (ValueError, AttributeError, TypeError):
            output['next_step'] = 'API returned an invalid listing. Check the deployed session API contract.'
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
