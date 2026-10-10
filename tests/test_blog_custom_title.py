import json
from flask import Flask
from app.controllers import blog_controller


def test_custom_title_skips_provider_and_preserves_input(monkeypatch):
    monkeypatch.setattr(blog_controller, 'get_provider', lambda: (_ for _ in ()).throw(AssertionError('AI should not run')))
    app = Flask(__name__)
    state = {}
    with app.test_request_context('/', method='POST', data={'action': 'use_custom_title', 'custom_title': '  My Own Title  ', 'keyword': 'topic', 'supporting_keyword': 'detail'}):
        blog_controller._handle_generate_titles(state)
    assert state['selected_title'] == 'My Own Title'
    assert state['titles'] == ['My Own Title']
    assert state['supporting_keyword'] == 'detail'


def test_empty_custom_title_is_rejected():
    app = Flask(__name__)
    state = {}
    with app.test_request_context('/', method='POST', data={'action': 'use_custom_title', 'custom_title': '  ', 'keyword': 'topic'}):
        blog_controller._handle_generate_titles(state)
    assert state['error'] == 'Please enter a custom title.'


def test_custom_title_reaches_meta_generation(monkeypatch):
    captured = {}
    def generate(provider, **kwargs):
        captured.update(kwargs)
        return [{'text': 'Meta description'}]
    monkeypatch.setattr(blog_controller, 'get_provider', lambda: object())
    monkeypatch.setattr(blog_controller, 'get_brand_context', lambda brand: '')
    monkeypatch.setattr(blog_controller, 'generate_meta_descriptions', generate)
    app = Flask(__name__)
    state = {}
    with app.test_request_context('/', method='POST', data={'action': 'generate_meta_descriptions', 'selected_title': 'My Own Title', 'keyword': 'topic', 'titles_json': json.dumps(['My Own Title'])}):
        blog_controller._handle_generate_content(state)
    assert captured['title'] == 'My Own Title'
    assert state['titles'] == ['My Own Title']
