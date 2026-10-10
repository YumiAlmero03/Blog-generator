from types import SimpleNamespace
from app.services.google_issues_service import ISSUE, add_google_issues, canonical_issue
from app.services import google_issues_service


def page():
    return {'url': 'https://example.com/a', 'result': {'url': 'https://example.com/a', 'stats': {'canonical': '/a'}}}


def inspection(**kwargs):
    data = dict(url='https://example.com/a', status='not-indexed', user_canonical='https://example.com/a', google_canonical='https://example.com/b', coverage_state=ISSUE, last_crawl_time='2026-09-01', detail='')
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_confirmation_uses_google_evidence():
    issue = canonical_issue(page(), inspection())
    assert issue['status'] == 'Confirmed by Google'
    assert any(item['value'] == 'https://example.com/b' for item in issue['evidence'])


def test_missing_data_never_passes():
    assert canonical_issue(page())['status'] == 'Not verified'
    assert canonical_issue(page(), inspection(coverage_state='', google_canonical=''))['status'] == 'Not verified'
    assert canonical_issue(page(), inspection(status='error'))['status'] == 'Not verified'


def test_mismatch_is_not_exact_coverage_confirmation():
    assert canonical_issue(page(), inspection(coverage_state='Other state'))['status'] == 'Canonical mismatch detected'
    assert canonical_issue(page(), inspection(coverage_state='Other state', google_canonical='https://example.com/a'))['status'] == 'Not detected in indexed data'


def test_missing_credentials_and_api_failure_keep_audit(monkeypatch):
    report = {'pages': [page()]}
    add_google_issues(report, enabled=True)
    assert 'credentials are missing' in report['pages'][0]['google_issues'][0]['reason']
    def fail(*args, **kwargs):
        raise ValueError('secret must not be displayed')
    monkeypatch.setattr(google_issues_service, 'inspect_google_index_status_by_url_domain', fail)
    add_google_issues(report, enabled=True, access_token='secret')
    assert 'secret' not in str(report)
    assert report['pages'][0]['result']['stats']['canonical'] == '/a'


def test_inspection_is_attached_to_matching_page(monkeypatch):
    monkeypatch.setattr(google_issues_service, 'inspect_google_index_status_by_url_domain', lambda *a, **k: SimpleNamespace(items=[inspection()]))
    report = {'pages': [page()]}
    add_google_issues(report, enabled=True, access_token='token')
    assert report['pages'][0]['google_issues'][0]['status'] == 'Confirmed by Google'


def test_api_keeps_both_canonical_fields(monkeypatch):
    import json
    from app.services import indexnow_service
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def getcode(self): return 200
        def read(self):
            return json.dumps({'inspectionResult': {'indexStatusResult': {
                'verdict': 'FAIL', 'coverageState': ISSUE,
                'userCanonical': 'https://example.com/a',
                'googleCanonical': 'https://example.com/b',
            }}}).encode()
    monkeypatch.setattr(indexnow_service, 'urlopen', lambda *a, **k: Response())
    item = indexnow_service.inspect_google_index_status(['https://example.com/a'], 'sc-domain:example.com', access_token='test').items[0]
    assert item.user_canonical == 'https://example.com/a'
    assert item.google_canonical == 'https://example.com/b'


def test_group_renders_and_handles_old_history():
    from flask import Flask, render_template
    from pathlib import Path
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
    report = {'pages': [page()]}
    add_google_issues(report)
    with app.app_context():
        html = render_template('_google_issues.html', page=report['pages'][0], result=report)
        assert 'Google issues' in html and 'Not verified' in html
        assert 'How to investigate and fix' in html
        old = render_template('_google_issues.html', page=page(), result={})
        assert 'predates Google issue checks' in old
