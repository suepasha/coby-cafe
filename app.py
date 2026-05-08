from flask import Flask, jsonify, send_from_directory, request
import requests
import csv
import io
import re
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

MJ_AUTH = (
    os.environ.get('MAILJET_API_KEY', '3b7ed6fa7e4d7e777bb144c487625b06'),
    os.environ.get('MAILJET_SECRET_KEY', '8a3a0f2e26c51aadaacfcd250b3126cf')
)

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1N1lO3PdUqX9U4chc1sZXpP_zzfHYwXyfzpEXO4BxYWs"
    "/export?format=csv"
)

APPS_SCRIPT_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbzoRuw5zraZ_g-g3BioEbReo-m_e_N_glPikd8eJrGmsCe-Pr__cjR4_UX84ZxudQhR/exec"
)

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
    'dueDate':     ['due date', 'duedate', 'send date', 'senddate'],
}

MJML_OPEN = """<mjml version="4.14.1">
  <mj-head>
    <mj-font href="https://fonts.googleapis.com/css2?family=Josefin%20Sans:wght@300;400;500;700;800;900" name="Josefin Sans, Arial, sans-serif"></mj-font>
    <mj-preview></mj-preview>
    <mj-style>
      @media only screen and (max-width: 480px) {
        .event-title { font-size: 20px !important; line-height: 28px !important; }
        .event-date  { font-size: 15px !important; line-height: 22px !important; }
        .event-desc  { font-size: 14px !important; line-height: 20px !important; }
        .signup-btn  { font-size: 14px !important; padding: 8px 16px !important; }
        .footer-btn  { font-size: 14px !important; }
      }
    </mj-style>
    <mj-attributes>
      <mj-all font-family="'Josefin Sans', Arial, sans-serif"></mj-all>
      <mj-image fluid-on-mobile="true"></mj-image>
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#ffffff" color="#8b94a7" font-family="Josefin Sans, Arial, sans-serif">
    <mj-section background-color="#ffffff" padding="0px">
      <mj-column>
        <mj-image align="center" alt="" border="none" container-background-color="#e0d3c3" height="auto" padding="10px 25px" src="https://sjqzn.mjt.lu/img2/sjqzn/519a4db6-cda9-4e32-8e6f-608386b2fadd/content" width="200px"></mj-image>
      </mj-column>
    </mj-section>"""

MJML_EVENT_SECTION = """
    <mj-section background-color="#f4f4f4" padding="5px 0px">
      <mj-column>
        <mj-text padding="0px" passport-element="html" width="100%">
          <p style="font-family:'Josefin Sans',Arial,sans-serif;font-size:20px;font-weight:bold;text-align:center;color:#000000;line-height:28px;margin:20px 30px 10px 30px;">EVENT_TITLE</p>
        </mj-text>
        <mj-image align="center" alt="" border-radius="10px" border="none" height="auto" padding="10px 25px 15px" src="EVENT_IMAGE" width="320px" fluid-on-mobile="true"></mj-image>
        <mj-text padding="0px" passport-element="html" width="100%">
          <p style="font-family:'Josefin Sans',Arial,sans-serif;font-size:16px;font-weight:bold;text-align:center;color:#000000;line-height:24px;margin:5px 20px;"><strong>EVENT_DATE</strong></p>
          <br>
          <p style="font-family:'Josefin Sans',Arial,sans-serif;font-size:14px;font-weight:normal;text-align:center;color:#000000;line-height:22px;margin:5px 30px;">EVENT_DESCRIPTION</p>
        </mj-text>
        <mj-button href="SIGNUP_LINK1"
          align="center"
          background-color="#FFFFFF"
          color="#000000"
          border="1px solid #000000"
          border-radius="10px"
          font-family="'Josefin Sans',Arial,sans-serif"
          font-size="16px"
          font-weight="bold"
          padding="10px 20px"
          inner-padding="12px 40px"
          width="280px">SIGNUP_TEXT1</mj-button>
        BUTTON2_PLACEHOLDER
        <mj-divider border-color="#E6E6E6" border-style="solid" border-width="2px" padding="10px 25px" width="100%"></mj-divider>
      </mj-column>
    </mj-section>"""

MJML_BUTTON2 = """<mj-button href="SIGNUP_LINK2"
          align="center"
          background-color="#FFFFFF"
          color="#000000"
          border="1px solid #000000"
          border-radius="10px"
          font-family="'Josefin Sans',Arial,sans-serif"
          font-size="16px"
          font-weight="bold"
          padding="5px 20px"
          inner-padding="12px 40px"
          width="280px">SIGNUP_TEXT2</mj-button>"""

MJML_CLOSE = """
    <mj-section background-color="#e0d3c3" padding="15px 25px 5px">
      <mj-column>
        <mj-text font-family="Verdana, Helvetica, Arial, sans-serif" padding="0px" passport-element="html" width="100%">
          <p style="text-align:center;margin-top:5px;"><a href="mailto:info@cobyscafe.com?subject=An%20idea%20for%20meetups%2Fevents" style="display:inline-block;font-family:'Josefin Sans',sans-serif;font-size:15px;font-weight:bold;text-decoration:none;padding:5px 10px;border-radius:8px;border:1px solid #2D2D2D;color:#2D2D2D;background-color:#ffffff;">Submit an Event Idea</a></p>
          <p style="text-align:center;margin-top:0px;"><a href="https://www.cobyscafe.com/membership" style="display:inline-block;font-family:'Josefin Sans',sans-serif;font-size:15px;font-weight:bold;text-decoration:none;padding:5px 10px;border-radius:8px;border:1px solid #2D2D2D;color:#2D2D2D;background-color:#ffffff;">Become a Member</a></p>
          <p style="text-align:center;margin-top:0px;"><a href="https://www.cobyscafe.com/parties" style="display:inline-block;font-family:'Josefin Sans',sans-serif;font-size:15px;font-weight:bold;text-decoration:none;padding:5px 10px;border-radius:8px;border:1px solid #2D2D2D;color:#2D2D2D;background-color:#ffffff;">Host a Party</a></p>
          <p style="text-align:center;margin-top:0px;"><a href="https://www.google.com/maps/search/?api=1&query=Coby's+Cafe+101+Nickerson+St+Seattle+WA" style="display:inline-block;font-family:'Josefin Sans',sans-serif;font-size:15px;font-weight:bold;text-decoration:none;padding:5px 10px;border-radius:8px;border:1px solid #2D2D2D;color:#2D2D2D;background-color:#ffffff;" target="_blank">Leave a Google Review</a></p>
        </mj-text>
        <mj-social align="center" border-radius="25px" container-background-color="transparent" icon-size="28px" mode="horizontal" text-mode="false">
          <mj-social-element background-color="#3B5998" href="https://www.facebook.com/people/Cobys-Cafe/61553537724188/" name="facebook-noshare" src="https://static.mailjet.com/ico-social/facebook.png"></mj-social-element>
          <mj-social-element background-color="#9585F4" href="https://www.instagram.com/cobys.dog.cafe/" name="instagram-noshare" src="https://static.mailjet.com/ico-social/instagram-colored.png"></mj-social-element>
        </mj-social>
        <mj-text font-family="Verdana, Helvetica, Arial, sans-serif" padding="0px 5px">
          <p style="text-align:center;margin:10px 0;"><span style="font-size:12px;font-family:'Josefin Sans';color:#131B20;">Coby's Cafe<br>101 Nickerson Street Building B Ste 200<br>Seattle, Washington 98109<br>www.cobyscafe.com</span></p>
        </mj-text>
        <mj-text font-family="Verdana, Helvetica, Arial, sans-serif" padding="10px 25px">
          <p style="text-align:center;margin:10px 0;"><span style="font-size:12px;font-family:'Josefin Sans';color:#000000;">If you do not wish to receive further communication like this, </span><a href="[[UNSUB_LINK_EN]]" target="_blank"><span style="font-size:12px;font-family:'Josefin Sans';color:#ffffff;"><u>unsubscribe here</u></span></a></p>
        </mj-text>
      </mj-column>
    </mj-section>
  </mj-body>
</mjml>"""


def parse_csv(text):
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    headers = [h.strip().lower() for h in rows[0]]
    col = {key: next((headers.index(a) for a in aliases if a in headers), None)
           for key, aliases in ALIASES.items()}
    events = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        def g(k):
            i = col.get(k)
            return row[i].strip() if i is not None and i < len(row) else ''
        events.append({k: g(k) for k in ALIASES})
    return events

def format_datetime(date, time_str):
    date = re.sub(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*,?\s*', '', date, flags=re.IGNORECASE).strip()
    return f"{date} | {time_str}" if time_str else date

def fill_event_section(event):
    name  = event['name']
    date  = format_datetime(event['date'], event['time'])
    desc  = event['desc']
    txt1  = event['signupText1'] or 'General Ticket'
    lnk1  = event['signupLink1'] if event['signupLink1'].startswith('http') else '#'
    txt2  = event['signupText2']
    lnk2  = event['signupLink2'] if event['signupLink2'].startswith('http') else ''
    image = event['image'] if event['image'].startswith('http') else 'https://sjqzn.mjt.lu/img2/sjqzn/1ef5c329-24ef-45e8-9010-9d1d6393531e/content'

    btn2 = MJML_BUTTON2.replace('SIGNUP_LINK2', lnk2).replace('SIGNUP_TEXT2', txt2) if txt2 and lnk2 else ''

    return (MJML_EVENT_SECTION
        .replace('EVENT_TITLE', name)
        .replace('EVENT_DATE', date)
        .replace('EVENT_DESCRIPTION', desc)
        .replace('EVENT_IMAGE', image)
        .replace('SIGNUP_LINK1', lnk1)
        .replace('SIGNUP_TEXT1', txt1)
        .replace('BUTTON2_PLACEHOLDER', btn2))

def build_mjml(events):
    sections = ''.join(fill_event_section(e) for e in events)
    return MJML_OPEN + sections + MJML_CLOSE

def mark_done(event_name):
    try:
        requests.post(APPS_SCRIPT_URL, json={'eventName': event_name}, timeout=10)
    except Exception:
        pass

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/api/events')
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
        data = request.json or {}
        selected = data.get('selected', [])

        res = requests.get(SHEET_CSV_URL, timeout=15)
        res.raise_for_status()
        events = parse_csv(res.text)

        # Filter: New events that are selected
        to_process = [e for e in events
                      if e['status'].lower() == 'new' and e['name'] in selected]

        if not to_process:
            return jsonify({'success': True, 'results': [], 'message': 'No events selected.'})

        # Group by Due Date — events with same due date merge into one file
        groups = {}
        for event in to_process:
            due = event['dueDate'].strip() or 'no_due_date'
            groups.setdefault(due, []).append(event)

        results = []
        for due_date, group_events in groups.items():
            try:
                mjml = build_mjml(group_events)

                # Filename: due date if available, else first event name
                if due_date != 'no_due_date':
                    filename = re.sub(r'[^a-zA-Z0-9]+', '_', due_date) + '.mjml'
                    label = f"{due_date} ({len(group_events)} event{'s' if len(group_events) > 1 else ''})"
                else:
                    filename = re.sub(r'[^a-zA-Z0-9]+', '_', group_events[0]['name']) + '.mjml'
                    label = group_events[0]['name']

                # Mark all events in group as Done
                for e in group_events:
                    mark_done(e['name'])

                results.append({
                    'name': label,
                    'events': [e['name'] for e in group_events],
                    'status': 'success',
                    'mjml': mjml,
                    'filename': filename
                })
            except Exception as ex:
                results.append({
                    'name': due_date,
                    'events': [e['name'] for e in group_events],
                    'status': 'error',
                    'error': str(ex)
                })

        return jsonify({'success': True, 'results': results})

    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex)}), 500

if __name__ == '__main__':
    app.run(debug=False)
