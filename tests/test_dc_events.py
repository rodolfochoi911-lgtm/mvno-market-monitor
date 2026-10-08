import copy
import base64
import json
import unittest
from unittest.mock import Mock, patch

import requests
from scripts import dc_event_monitor as monitor
from scripts import teams_notifier as teams


def listing(*ids, subject='행사'):
    rows = ''.join(
        f'<tr class="ub-content us-post"><td class="gall_num">{i}</td>'
        f'<td class="gall_subject">{subject}</td><td class="gall_tit">'
        f'<a href="/mgallery/board/view/?id=mvnogallery&no={i}">행사 {i}</a>'
        '</td></tr>' for i in ids)
    return '<table class="gall_list">' + (rows or '<tr class="no_data"><td>없음</td></tr>') + '</table>'


class MemoryStore:
    def __init__(self, state=None):
        self.state = state
        self.saves = []

    def load(self):
        return copy.deepcopy(self.state)

    def save(self, state):
        self.state = copy.deepcopy(state)
        self.saves.append(copy.deepcopy(state))


def store():
    return MemoryStore({'version': 1, 'high_water': 100, 'seen_ids': []})


class EventTests(unittest.TestCase):
    def test_live_dc_new_badge_and_hidden_tooltip(self):
        html = listing(509647).replace('>행사</td>', '>행사🆕<p class="subject_inner" style="display:none">행사🆕️</p></td>')
        self.assertEqual('509647', monitor.parse_list(html)[0]['id'])

    def test_initial_run_never_fetches_details_or_sends(self):
        s = MemoryStore()
        fetch, send = Mock(return_value=listing(103, 102)), Mock()
        monitor.run(s, fetch, send)
        send.assert_not_called()
        self.assertEqual(1, fetch.call_count)
        self.assertEqual(103, s.state['high_water'])

    def test_empty_baseline_is_valid(self):
        s = MemoryStore()
        monitor.run(s, Mock(return_value=listing()), Mock())
        self.assertEqual(0, s.state['high_water'])

    def test_idle_poll_is_one_get_and_no_write(self):
        s, fetch, send = store(), Mock(return_value=listing(100, 99)), Mock()
        monitor.run(s, fetch, send)
        self.assertEqual(1, fetch.call_count)
        self.assertEqual([], s.saves)
        send.assert_not_called()

    def test_bundle_then_duplicate_suppression(self):
        s, send = store(), Mock(return_value=True)
        fetch = Mock(side_effect=[listing(102, 101, 100), '<div class="write_div">월 990원 / 7개월 할인</div>', '<div class="write_div"><img src="x"></div>'])
        monitor.run(s, fetch, send)
        self.assertEqual(1, send.call_count)
        text = send.call_args.args[0]
        self.assertIn('990원', text)
        self.assertIn('이미지 중심', text)
        self.assertIn('no=101', text)
        self.assertIn('no=102', text)
        monitor.run(s, Mock(return_value=listing(102, 101, 100)), send)
        self.assertEqual(1, send.call_count)

    def test_pagination_finds_all_new_ids(self):
        s, send = store(), Mock(return_value=True)
        fetch = Mock(side_effect=[listing(104, 103), listing(103, 102, 101), listing(100), *['<div class="write_div">혜택</div>'] * 4])
        monitor.run(s, fetch, send)
        self.assertEqual(104, s.state['high_water'])
        self.assertEqual(7, fetch.call_count)

    def test_crawl_failures_preserve_state(self):
        for pages in [['blocked'], [listing(102, 101), 'blocked'], [listing(102, 100), '<h1>삭제</h1>']]:
            with self.subTest(pages=pages):
                s = store()
                with self.assertRaises(RuntimeError):
                    monitor.run(s, Mock(side_effect=pages), Mock())
                self.assertEqual([], s.saves)

    def test_all_details_fetched_before_any_notification(self):
        s, send = store(), Mock()
        with self.assertRaises(RuntimeError):
            monitor.run(s, Mock(side_effect=[listing(102, 101, 100), '<div class="write_div">정상</div>', 'blocked']), send)
        send.assert_not_called()
        self.assertEqual([], s.saves)

    def test_send_failure_never_marks_seen(self):
        s = store()
        with self.assertRaises(RuntimeError):
            monitor.run(s, Mock(side_effect=[listing(101, 100), '<div class="write_div">조건</div>']), Mock(side_effect=RuntimeError('failed')))
        self.assertEqual([], s.saves)

    def test_unconfirmed_send_never_marks_seen(self):
        s = store()
        with self.assertRaises(RuntimeError):
            monitor.run(s, Mock(side_effect=[listing(101, 100), '<div class="write_div">조건</div>']), Mock(return_value=None))
        self.assertEqual([], s.saves)

    def test_partial_batches_survive_send_failure_and_resume(self):
        s = store()
        fetch = Mock(side_effect=[listing(106, 105, 104, 103, 102, 101, 100), *['<div class="write_div">조건</div>'] * 6])
        with self.assertRaises(RuntimeError):
            monitor.run(s, fetch, Mock(side_effect=[True, RuntimeError('failed')]))
        self.assertEqual(['101', '102', '103', '104', '105'], s.state['seen_ids'])
        send = Mock(return_value=True)
        monitor.run(s, Mock(side_effect=[listing(106, 105, 104, 103, 102, 101, 100), '<div class="write_div">조건</div>']), send)
        self.assertEqual(1, send.call_count)
        self.assertNotIn('no=105', send.call_args.args[0])
        self.assertEqual(106, s.state['high_water'])

    def test_dry_run_has_no_side_effects(self):
        for s in [store(), MemoryStore()]:
            send = Mock()
            monitor.run(s, Mock(side_effect=[listing(101, 100), '<div class="write_div">조건</div>']), send, dry_run=True)
            self.assertEqual([], s.saves)
            send.assert_not_called()

    def test_page_limit_and_repeated_pages_preserve_state(self):
        for pages in [[listing(102), listing(102)], [listing(102), listing(101)]]:
            s = store()
            with self.assertRaises(RuntimeError):
                monitor.run(s, Mock(side_effect=pages), Mock(), max_pages=2)
            self.assertEqual([], s.saves)

    def test_invalid_list_filter_id_and_sort_rejected(self):
        for html in [listing(101, subject='일반'), listing(101).replace('no=101', 'no=999'), listing(101, 102), listing(101).replace('mvnogallery', 'other'), '<table class="gall_list"></table>']:
            with self.subTest(html=html), self.assertRaises(RuntimeError):
                monitor.parse_list(html)

    def test_corrupt_state_is_not_overwritten(self):
        for state in [{'version': 2}, {'version': 1, 'high_water': -1, 'seen_ids': []}]:
            s = MemoryStore(state)
            with self.assertRaises(RuntimeError):
                monitor.run(s, Mock(return_value=listing(101)), Mock())
            self.assertEqual([], s.saves)

    def test_summary_preserves_facts_and_ignores_scripts(self):
        summary = monitor.summarize('<div class="write_div"><p>행사 안내</p><p>월 990원</p><p>7개월</p><script>bad()</script></div>')
        self.assertIn('990원', summary)
        self.assertIn('7개월', summary)
        self.assertNotIn('bad()', summary)


class TransportTests(unittest.TestCase):
    @patch.dict('os.environ', {'COPILOT_WEBHOOK_URL': 'https://example.invalid/secret'})
    @patch.object(teams.time, 'sleep')
    def test_retry_transient_errors_then_confirm_acceptance(self, sleep):
        with patch.object(teams.requests, 'post', side_effect=[requests.Timeout('secret'), Mock(status_code=429, text=''), Mock(status_code=202, text='')]) as post:
            self.assertTrue(teams.send_teams_message('a\nb', attempts=3))
            self.assertEqual(3, post.call_count)
            self.assertEqual('a\n\nb', post.call_args.kwargs['json']['attachments'][0]['content']['body'][0]['text'])

    @patch.dict('os.environ', {'COPILOT_WEBHOOK_URL': 'https://example.invalid/secret'})
    @patch.object(teams.time, 'sleep')
    def test_permanent_failures_and_error_body_are_rejected(self, sleep):
        for status, body in [(400, 'secret'), (302, ''), (200, 'Webhook message delivery failed. HTTP error 429')]:
            with patch.object(teams.requests, 'post', return_value=Mock(status_code=status, text=body)) as post:
                with self.assertRaisesRegex(RuntimeError, '^팀즈 알림 전송 실패$'):
                    teams.send_teams_message('x', attempts=3)
                self.assertEqual(1, post.call_count)

    @patch.dict('os.environ', {'COPILOT_WEBHOOK_URL': 'https://example.invalid/secret'})
    @patch.object(teams.time, 'sleep')
    def test_exhausted_retries_redact_secret(self, sleep):
        with patch.object(teams.requests, 'post', side_effect=requests.Timeout('secret')) as post:
            with self.assertRaisesRegex(RuntimeError, '^팀즈 알림 전송 실패$'):
                teams.send_teams_message('x', attempts=3)
            self.assertEqual(3, post.call_count)


class StateTests(unittest.TestCase):
    @patch.dict('os.environ', {'GITHUB_REPOSITORY': 'o/r', 'GITHUB_TOKEN': 'secret', 'GITHUB_SHA': 'head'})
    def test_bootstrap_creates_dedicated_branch_then_state(self):
        s = monitor.GitHubState()
        responses = [Mock(status_code=404), Mock(status_code=201), Mock(status_code=201)]
        responses[-1].json.return_value = {'content': {'sha': 'checkpoint'}}
        with patch.object(s, 'request', side_effect=responses) as request:
            s.save(store().state)
            self.assertEqual('refs/heads/dc-event-state', request.call_args_list[1].kwargs['json']['ref'])
            self.assertEqual('dc-event-state', request.call_args_list[2].kwargs['json']['branch'])
            self.assertEqual('checkpoint', s.sha)

    @patch.dict('os.environ', {'GITHUB_REPOSITORY': 'o/r', 'GITHUB_TOKEN': 'secret', 'GITHUB_SHA': 'head'})
    def test_state_roundtrip_keeps_partial_delivery_ids(self):
        state = {'version': 1, 'high_water': 100, 'seen_ids': ['101']}
        response = Mock(status_code=200)
        response.json.return_value = {'sha': 'checkpoint', 'content': base64.b64encode(json.dumps(state).encode()).decode()}
        s = monitor.GitHubState()
        with patch.object(s, 'request', return_value=response):
            self.assertEqual(state, s.load())
            self.assertEqual('checkpoint', s.sha)

    @patch.dict('os.environ', {'GITHUB_REPOSITORY': 'o/r', 'GITHUB_TOKEN': 'secret', 'GITHUB_SHA': 'head'})
    def test_sha_conflict_is_fatal_and_never_force_overwrites(self):
        s = monitor.GitHubState()
        s.sha = 'previous'
        with patch.object(s, 'request', return_value=Mock(status_code=409)) as request:
            with self.assertRaises(RuntimeError):
                s.save(store().state)
            self.assertEqual('previous', request.call_args.kwargs['json']['sha'])
            self.assertEqual(1, request.call_count)

    @patch.dict('os.environ', {'GITHUB_REPOSITORY': 'o/r', 'GITHUB_TOKEN': 'secret', 'GITHUB_SHA': 'head'})
    def test_state_read_error_is_not_first_run(self):
        s = monitor.GitHubState()
        with patch.object(s, 'request', return_value=Mock(status_code=500)):
            with self.assertRaises(RuntimeError):
                s.load()


if __name__ == '__main__':
    unittest.main()
