"""PM Surya Ghar registered-vendor browser response collector.

Run locally: python solar_bulk_extractor.py
The site itself constructs encrypted requests. This script never forges them.
IMPORTANT: UI selectors are configurable and MUST be calibrated against the live portal.
"""
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

URL = 'https://pmsuryaghar.gov.in/#/registered-vendors'
ENDPOINT_FRAGMENT = 'registeredVendor/getVendorByStateDistrict'
STATES = ['Andhra Pradesh', 'Telangana']
OUTPUT = Path('output')
PROFILE = Path('chrome_vendor_profile')

# IMPORTANT: Set these after inspecting the real page if auto-discovery fails.
# Supported CSS selectors for native <select> and clickable custom dropdowns.
STATE_SELECTOR = ''
DISTRICT_SELECTOR = ''
RESPONSE_WAIT_SECONDS = 18

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('vendors')


def unwrap_vendor_records(payload):
    """Find vendor-shaped dictionaries in JSON without assuming one response envelope."""
    found = []
    def visit(obj):
        if isinstance(obj, dict):
            if ('vendorId' in obj or 'vendorName' in obj) and ('districtwiseInstallationAndCapacity' in obj or 'statewiseInstallationAndCapacity' in obj):
                found.append(obj)
            else:
                for v in obj.values():
                    visit(v)
        elif isinstance(obj, list):
            for v in obj:
                visit(v)
    visit(payload)
    return found


def count_field(record, key):
    nested = record.get(key)
    return nested.get('installationCount') if isinstance(nested, dict) else None


def dropdown(page, label, override=''):
    """Best-effort locate state/district controls; explicit selector is preferred."""
    if override:
        loc = page.locator(override).first
        if loc.count():
            return loc
        raise RuntimeError(f'{label} selector not found: {override}')
    # Accessible label / role first.
    for loc in [page.get_by_label(re.compile(label, re.I)).first,
                page.get_by_role('combobox', name=re.compile(label, re.I)).first,
                page.locator(f'select[formcontrolname*="{label.lower()}"]').first,
                page.locator(f'[placeholder*="{label}"]').first]:
        try:
            if loc.count() and loc.is_visible(timeout=1500):
                return loc
        except Exception:
            pass
    raise RuntimeError(f'Cannot identify {label} dropdown automatically. Set {label.upper()}_SELECTOR in the script. See output/controls.txt.')


def option_names(page, control):
    tag = control.evaluate('(el) => el.tagName.toLowerCase()')
    if tag == 'select':
        return [x.strip() for x in control.locator('option').all_text_contents() if x.strip() and not re.search('select|choose', x, re.I)]
    control.click()
    page.wait_for_timeout(450)
    # Angular Material, PrimeNG and ARIA option patterns.
    opts = page.locator('[role="option"]:visible, mat-option:visible, .p-dropdown-item:visible, .ng-option:visible')
    names = [x.strip() for x in opts.all_text_contents() if x.strip()]
    page.keyboard.press('Escape')
    if not names:
        raise RuntimeError('Custom dropdown options not discovered; configure selectors based on page DOM.')
    return list(dict.fromkeys(names))


def choose(page, control, name):
    tag = control.evaluate('(el) => el.tagName.toLowerCase()')
    if tag == 'select':
        control.select_option(label=name)
    else:
        control.click()
        page.get_by_role('option', name=name, exact=True).first.click(timeout=5000)


def capture_controls(page):
    OUTPUT.mkdir(exist_ok=True)
    controls = page.locator('select, [role="combobox"], mat-select, .p-dropdown, .ng-select')
    lines = []
    for i in range(controls.count()):
        c = controls.nth(i)
        try:
            lines.append(f'[{i}] {c.evaluate("el => el.outerHTML.slice(0, 1200)")}')
        except Exception:
            pass
    (OUTPUT / 'controls.txt').write_text('\n\n'.join(lines), encoding='utf-8')
    page.screenshot(path=str(OUTPUT / 'portal_screenshot.png'), full_page=True)


def main():
    OUTPUT.mkdir(exist_ok=True)
    rows, audits = [], []
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), headless=False, channel='chrome',
            viewport={'width': 1440, 'height': 900}, accept_downloads=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        responses = []

        def on_response(response):
            if ENDPOINT_FRAGMENT not in response.url or response.request.method != 'POST':
                return
            try:
                payload = response.json()
                responses.append({'status': response.status, 'payload': payload, 'timestamp': time.time()})
            except Exception as exc:
                log.warning('Vendor response was not readable JSON: %s', exc)

        page.on('response', on_response)
        page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        print('\nIf prompted, complete any normal login/consent in Chrome.')
        input('When the Registered Vendors filters are visible, press ENTER here... ')
        capture_controls(page)

        for state in STATES:
            try:
                state_control = dropdown(page, 'state', STATE_SELECTOR)
                choose(page, state_control, state)
                page.wait_for_timeout(900)
                district_control = dropdown(page, 'district', DISTRICT_SELECTOR)
                districts = option_names(page, district_control)
                log.info('%s: discovered %d district options', state, len(districts))
            except Exception as exc:
                audits.append({'State': state, 'District': '', 'Status': 'DISCOVERY_FAILED', 'Records': None, 'Error': str(exc)})
                log.error('%s discovery failed: %s', state, exc)
                continue

            for district in districts:
                log.info('Fetching %s / %s', state, district)
                try:
                    # Re-select state if portal resets it on district change.
                    state_control = dropdown(page, 'state', STATE_SELECTOR)
                    choose(page, state_control, state)
                    page.wait_for_timeout(400)
                    district_control = dropdown(page, 'district', DISTRICT_SELECTOR)
                    before = len(responses)
                    choose(page, district_control, district)
                    # Some sites require clicking a Search button.
                    for button_name in ('Search', 'Submit', 'View Vendors', 'Get Vendors'):
                        button = page.get_by_role('button', name=button_name, exact=True)
                        if button.count() and button.first.is_visible():
                            button.first.click()
                            break
                    deadline = time.monotonic() + RESPONSE_WAIT_SECONDS
                    while len(responses) == before and time.monotonic() < deadline:
                        page.wait_for_timeout(300)
                    if len(responses) == before:
                        raise TimeoutError('No matching API response observed after district selection')
                    response = responses[-1]
                    if response['status'] != 200:
                        raise RuntimeError(f'HTTP {response["status"]}')
                    vendors = unwrap_vendor_records(response['payload'])
                    if not vendors:
                        raise RuntimeError('No vendor records recognized in response; inspect envelope or portal state')
                    for v in vendors:
                        rows.append({
                            'State': state, 'District': district,
                            'Vendor ID': v.get('vendorId'),
                            'Vendor Name': v.get('vendorName'),
                            'District Installations': count_field(v, 'districtwiseInstallationAndCapacity'),
                            'State Installations': count_field(v, 'statewiseInstallationAndCapacity'),
                            'National Installations': count_field(v, 'nationwiseInstallationAndCapacity'),
                            'Captured At': datetime.now().isoformat(timespec='seconds'),
                        })
                    audits.append({'State': state, 'District': district, 'Status': 'CAPTURED_UNVERIFIED', 'Records': len(vendors), 'Error': ''})
                except Exception as exc:
                    audits.append({'State': state, 'District': district, 'Status': 'FAILED', 'Records': None, 'Error': str(exc)})
                    log.error('%s / %s failed: %s', state, district, exc)
                finally:
                    # Checkpoint so a failed run does not lose successful responses.
                    pd.DataFrame(rows).to_csv(OUTPUT / 'vendors_checkpoint.csv', index=False)
                    pd.DataFrame(audits).to_csv(OUTPUT / 'extraction_audit.csv', index=False)

        context.close()

    df = pd.DataFrame(rows)
    audit = pd.DataFrame(audits)
    if not df.empty:
        df = df.drop_duplicates(subset=['State', 'District', 'Vendor ID'], keep='last')
    with pd.ExcelWriter(OUTPUT / 'AP_Telangana_Vendors.xlsx', engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Vendor Master', index=False)
        audit.to_excel(writer, sheet_name='Extraction Audit', index=False)
    print(f'\nSaved {len(df)} district-vendor records. Check Extraction Audit: CAPTURED_UNVERIFIED is NOT portal-validated.')
    print('If controls failed, inspect output/controls.txt and output/portal_screenshot.png.')


if __name__ == '__main__':
    main()
