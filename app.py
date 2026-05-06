from flask import Flask, jsonify, send_from_directory, request
import requests
import csv
import io
import re
import os
import tempfile
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

MAILJET_API_KEY    = os.environ.get('MAILJET_API_KEY', '3b7ed6fa7e4d7e777bb144c487625b06')
MAILJET_SECRET_KEY = os.environ.get('MAILJET_SECRET_KEY', '8a3a0f2e26c51aadaacfcd250b3126cf')
MJ_AUTH = (MAILJET_API_KEY, MAILJET_SECRET_KEY)
MJ_BASE = "https://api.mailjet.com/v3/REST"
MAILJET_EMAIL    = os.environ.get('MAILJET_EMAIL', 'suepasha@yahoo.com')
MAILJET_PASSWORD = os.environ.get('MAILJET_PASSWORD', 'Suepasha070!')

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1N1lO3PdUqX9U4chc1sZXpP_zzfHYwXyfzpEXO4BxYWs"
    "/export?format=csv"
)
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzoRuw5zraZ_g-g3BioEbReo-m_e_N_glPikd8eJrGmsCe-Pr__cjR4_UX84ZxudQhR/exec"

jobs = {}

ALIASES = {
    'name':        ['event name'],
    'month':       ['month'],
    'date':        ['date'],
    'time':        ['time'],
    'desc':        ['description'],
    'signupText1': ['sign up text 1', 'signup text 1'],
    'signupLink1': ['sign up link 1', 'signup link 1', 'sign up link'],
    'signupText2': ['sign up text 2', 'signup text 2'],
    'signupLink2': ['sign up link 2', 'signup link 2'],
    'status':      ['status'],
    'image':       ['image'],
}

def get_col_index(headers):
    col = {}
    for key, alias_list in ALIASES.items():
        for alias in alias_list:
            if alias in headers:
                col[key] = headers.index(alias)
                break
    return col

def get_cell(row, col, key):
    idx = col.get(key)
    if idx is not None and idx < len(row):
        return row[idx].strip()
    return ''

def parse_csv(text):
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    headers = [h.strip().lower() for h in rows[0]]
    col = get_col_index(headers)
    events = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        events.append({k: get_cell(row, col, k) for k in ALIASES})
    return events

def format_datetime(date, time_str):
    date = re.sub(r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*', '', date, flags=re.IGNORECASE).strip()
    return f"{date} | {time_str}" if time_str else date

def get_base_html():
    res = requests.get(f"{MJ_BASE}/template?Limit=100", auth=MJ_AUTH)
    templates = res.json().get('Data', [])
    base = next((t for t in templates if 'cobysbasetemplate' in t['Name'].lower()), None)
    if not base:
        return None, 'CobysBaseTemplate not found.'
    res2 = requests.get(f"{MJ_BASE}/template/{base['ID']}/detailcontent", auth=MJ_AUTH)
    content = res2.json()
    if 'Data' not in content or not content['Data']:
        return None, 'CobysBaseTemplate has no HTML content.'
    return content['Data'][0].get('Html-part', ''), None

def fill_template(html, event):
    out = html
    out = out.replace('{{var:event_name}}', event['name'])
    out = out.replace('{{var:date}}', format_datetime(event['date'], event['time']))
    out = out.replace('{{var:description}}', event['desc'])
    out = out.replace('{{var:signup_text1}}', event['signupText1'] or 'General Ticket')
    out = out.replace('{{var:signup_link1}}', event['signupLink1'] if event['signupLink1'].startswith('http') else '#')
    out = out.replace('{{var:signup_text2}}', event['signupText2'] or '')
    out = out.replace('{{var:signup_link2}}', event['signupLink2'] if event['signupLink2'].startswith('http') else '#')
    if event['image'] and event['image'].startswith('http'):
        out = out.replace('{{var:image}}', event['image'])
    return out

def mark_done(event_name):
    try:
        requests.post(APPS_SCRIPT_URL, json={'eventName': event_name}, timeout=10)
    except:
        pass

def playwright_import(event_name, html_content, job_id):
    log = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage'
                ]
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800},
                locale='en-US'
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()
            try:
                log.append('Opening Mailjet login...')
                page.goto('https://app.mailjet.com/signin', timeout=30000)
                page.wait_for_load_state('domcontentloaded', timeout=30000)
                page.wait_for_timeout(3000)
                log.append(f'Login page: {page.url} | {page.title()}')

                # Accept cookie popup by clicking Allow All (button index 3)
                try:
                    buttons = page.query_selector_all('button')
                    for btn in buttons:
                        txt = btn.inner_text().strip()
                        if txt in ['Allow All', 'Accept Cookies', 'Accept all', 'Accept']:
                            btn.click()
                            log.append(f'Clicked cookie button: {txt}')
                            page.wait_for_timeout(2000)
                            break
                except Exception as ce:
                    log.append(f'Cookie click error: {ce}')

                # Now fill email - look for visible inputs
                page.wait_for_timeout(1000)
                all_inputs = page.query_selector_all('input:visible')
                log.append(f'Visible inputs: {len(all_inputs)}')
                for idx, inp in enumerate(all_inputs):
                    t = inp.get_attribute('type') or 'text'
                    n = inp.get_attribute('name') or ''
                    log.append(f'Input {idx}: type={t} name={n}')

                # Fill email
                email_done = False
                for sel in ['input[type="email"]', 'input[name="email"]', 'input[name="_username"]', '#email']:
                    try:
                        page.fill(sel, MAILJET_EMAIL, timeout=3000)
                        log.append(f'Email: {sel}')
                        email_done = True
                        break
                    except:
                        continue
                if not email_done and all_inputs:
                    all_inputs[0].fill(MAILJET_EMAIL)
                    log.append('Email via first input')

                # Fill password
                for sel in ['input[type="password"]', 'input[name="password"]', 'input[name="_password"]']:
                    try:
                        page.fill(sel, MAILJET_PASSWORD, timeout=3000)
                        log.append(f'Password: {sel}')
                        break
                    except:
                        continue

                # Click login button
                page.wait_for_timeout(500)
                login_clicked = False
                for sel in ['text=Log in to Mailjet', 'button[type="submit"]', 'input[type="submit"]']:
                    try:
                        page.click(sel, timeout=5000)
                        log.append(f'Clicked: {sel}')
                        login_clicked = True
                        break
                    except:
                        continue

                page.wait_for_load_state('networkidle', timeout=30000)
                log.append(f'After login: {page.url}')

                if 'signin' in page.url:
                    raise Exception(f'Login failed - still on signin page. Check credentials.')

                                # Go to templates
                page.goto('https://app.mailjet.com/templates/marketing', timeout=30000)
                page.wait_for_load_state('networkidle', timeout=30000)
                log.append(f'Templates page: {page.title()}')

                page.click('text=Create a template', timeout=15000)
                page.wait_for_load_state('networkidle', timeout=30000)
                log.append('Clicked Create template')

                page.click('text=By coding it in HTML', timeout=15000)
                page.wait_for_load_state('networkidle', timeout=30000)
                log.append('Clicked HTML option')

                page.click('text=Import HTML from a file', timeout=15000)
                page.wait_for_load_state('networkidle', timeout=30000)
                log.append('Clicked Import from file')

                with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w') as f:
                    f.write(html_content)
                    tmp_path = f.name

                page.set_input_files('input[type="file"]', tmp_path, timeout=15000)
                os.unlink(tmp_path)
                log.append('File uploaded')

                name_input = page.query_selector('input[placeholder*="name" i], input[name*="name"], #template-name')
                if name_input:
                    name_input.fill(event_name)
                    log.append('Name entered')

                page.click('text=Continue', timeout=10000)
                page.wait_for_load_state('networkidle', timeout=30000)
                log.append('Done!')
                browser.close()

                mark_done(event_name)
                jobs[job_id]['results'].append({'name': event_name, 'status': 'success', 'log': ' | '.join(log)})

            except Exception as e:
                log.append(f'ERROR: {str(e)}')
                try: browser.close()
                except: pass
                jobs[job_id]['results'].append({'name': event_name, 'status': 'error', 'error': ' | '.join(log)})

    except Exception as e:
        jobs[job_id]['results'].append({'name': event_name, 'status': 'error', 'error': str(e)})

def run_job(job_id, new_events, base_html):
    jobs[job_id]['status'] = 'running'
    for event in new_events:
        filled = fill_template(base_html, event)
        playwright_import(event['name'], filled, job_id)
    jobs[job_id]['status'] = 'done'

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        res = requests.get(SHEET_CSV_URL, timeout=15)
        res.raise_for_status()
        return jsonify({'success': True, 'events': parse_csv(res.text)})
    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex)}), 500

@app.route('/api/run', methods=['POST'])
def run_automation():
    try:
        res = requests.get(SHEET_CSV_URL, timeout=15)
        res.raise_for_status()
        events = parse_csv(res.text)
        new_events = [e for e in events if e['status'].lower() == 'new']

        if not new_events:
            return jsonify({'success': True, 'job_id': None, 'message': 'No new events found.'})

        base_html, error = get_base_html()
        if error:
            return jsonify({'success': False, 'error': error}), 500

        job_id = str(int(time.time()))
        jobs[job_id] = {'status': 'queued', 'results': [], 'total': len(new_events)}

        t = threading.Thread(target=run_job, args=(job_id, new_events, base_html))
        t.daemon = True
        t.start()

        return jsonify({'success': True, 'job_id': job_id, 'total': len(new_events)})

    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex)}), 500

@app.route('/api/status/<job_id>', methods=['GET'])
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404
    return jsonify({'success': True, **job})

@app.route('/api/test', methods=['GET'])
def test_playwright():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage'
                ]
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800},
                locale='en-US'
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()
            page.goto('https://example.com')
            title = page.title()
            browser.close()
            return jsonify({'success': True, 'title': title})
    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex)})

if __name__ == '__main__':
    app.run(debug=False)
