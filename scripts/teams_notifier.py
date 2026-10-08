"""Shared Teams transport extracted from monitor_crawler.send_slack_message."""
import os
import time
import requests


def adaptive_card(message):
    return {
        'type': 'message',
        'attachments': [{
            'contentType': 'application/vnd.microsoft.card.adaptive',
            'content': {
                '$schema': 'http://adaptivecards.io/schemas/adaptive-card.json',
                'type': 'AdaptiveCard', 'version': '1.2',
                'body': [{'type': 'TextBlock', 'text': message.replace('\n', '\n\n'),
                          'wrap': True}],
            },
        }],
    }


def send_teams_message(message, attempts=1):
    """Return True only after webhook acceptance; never expose URL/body in errors.

    The daily caller retains one attempt. Event alerts opt into bounded retries.
    HTTP acceptance cannot prove downstream Teams delivery for async Workflows.
    """
    url = os.environ.get('COPILOT_WEBHOOK_URL')
    if not url:
        raise RuntimeError('COPILOT_WEBHOOK_URL이 설정되지 않았습니다.')
    for attempt in range(attempts):
        retryable = True
        try:
            response = requests.post(url, json=adaptive_card(message), timeout=20,
                                     allow_redirects=False)
            # Legacy webhooks can return an error string with HTTP 200.
            body = response.text.strip().lower()
            if 200 <= response.status_code < 300 and not (
                body.startswith(('error', 'invalid', 'bad', 'webhook message delivery failed'))
                or 'http error' in body
            ):
                return True
            retryable = response.status_code == 429 or response.status_code >= 500
        except requests.RequestException:
            pass
        if not retryable or attempt + 1 == attempts:
            raise RuntimeError('팀즈 알림 전송 실패') from None
        time.sleep(2 ** attempt)
    raise ValueError('attempts must be positive')
