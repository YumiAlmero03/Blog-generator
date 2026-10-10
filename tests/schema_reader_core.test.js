const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('../static/assets/js/schema_reader_core.js');
test('all starter blocks parse and pass basic structure checks', () => {
  for (const type of Object.keys(core.templates)) {
    const value = core.add({ '@context': 'https://schema.org', '@graph': [] }, type);
    assert.deepEqual(core.check(core.parse(JSON.stringify(value))).errors, []);
    assert.equal(value['@graph'][0]['@type'], type);
  }
});
test('adding preserves existing nodes, contexts, and graph metadata', () => {
  const original = { '@context': { name: 'https://schema.org/name' }, '@type': 'Organization', name: 'Kept' };
  assert.deepEqual(core.add(original, 'WebSite')['@graph'][0], original);
  const graph = { '@context': 'https://schema.org', '@id': 'https://example.com/graph', '@graph': [original] };
  const added = core.add(graph, 'Brand');
  assert.equal(added['@id'], graph['@id']);
  assert.deepEqual(added['@graph'][0], original);
  assert.equal(graph['@graph'].length, 1);
  assert.equal(core.add([original], 'Person').length, 2);
});
test('syntax and nested structure errors are reported', () => {
  assert.throws(() => core.parse('{"name":}'), SyntaxError);
  for (const value of [null, 42, { '@graph': {} }, { '@type': 42 }, { '@graph': [false] }, { '@type': 'Organization', logo: { '@id': 3 } }]) {
    assert.ok(core.check(value).errors.length);
  }
  assert.throws(() => core.add({ '@graph': {} }, 'Brand'));
});
test('accepts a pasted JSON-LD script and reports missing context', () => {
  assert.equal(core.parse('<script type="application/ld+json">{"@type":"WebPage"}</script>')['@type'], 'WebPage');
  assert.ok(core.check({ '@type': 'WebPage' }).warnings.length);
});
test('domain overrides preserve page paths and queries and resolve images', () => {
  const values = core.replacements({ DOMAIN_URL: 'new.example', PAGE_URL: 'https://old.example/blog/post?q=1#part', META_IMAGE: '/cover.jpg' });
  assert.equal(values.PAGE_URL, 'https://new.example/blog/post?q=1');
  assert.equal(values.DOMAIN_URL, 'https://new.example/');
  assert.equal(values.META_IMAGE, 'https://new.example/cover.jpg');
  assert.equal(core.replacements({ DOMAIN_URL: 'example.org', PAGE_URL: '/about' }).PAGE_URL, 'https://example.org/about');
  assert.throws(() => core.replacements({ PAGE_URL: 'javascript:alert(1)' }));
  assert.throws(() => core.replacements({ PAGE_URL: 'https://user:password@example.org' }));
  assert.throws(() => core.replacements({ PAGE_URL: '/relative' }));
});
test('fills nested placeholders without replacing custom text or mutating templates', () => {
  const value = core.add({ '@graph': [] }, 'BlogPosting', { META_TITLE: 'A "quoted" title', AUTHOR_NAME: 'Jane', PAGE_URL: 'https://example.org/post' });
  assert.equal(value['@graph'][0].headline, 'A "quoted" title');
  assert.equal(value['@graph'][0].author.name, 'Jane');
  assert.equal(core.templates.BlogPosting.headline, 'META_TITLE');
  assert.equal(core.apply({ name: 'Custom title', description: 'META_DESCRIPTION' }, { META_TITLE: 'New', META_DESCRIPTION: 'Actual description' }).name, 'Custom title');
  assert.ok(core.check(value).warnings.some(message => message.includes('DATE_PUBLISHED')));
});
