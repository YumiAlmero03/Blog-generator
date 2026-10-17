"""Convert complete FAQ sections into portable, expandable HTML blocks."""
import html
import re
from html.parser import HTMLParser


class _Blocks(HTMLParser):
    """Locate top-level blocks without reserializing their HTML."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0]
        for match in re.finditer('\n', source):
            self.lines.append(match.end())
        self.stack = []
        self.blocks = []
        self.start = 0
        self.tag = ''
        self.feed(source)

    def source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if not self.stack:
            self.start, self.tag = self.source_offset(), tag
        if tag not in self.VOID:
            self.stack.append(tag)
        elif not self.stack:
            self.blocks.append((tag, self.start, self.source_offset() + len(self.get_starttag_text())))

    def handle_startendtag(self, tag, attrs):
        if not self.stack:
            self.blocks.append((tag, self.source_offset(), self.source_offset() + len(self.get_starttag_text())))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
            if not self.stack:
                end = self.source.find('>', self.source_offset()) + 1
                self.blocks.append((self.tag, self.start, end))


def _text(value):
    return html.unescape(re.sub('<[^>]*>', '', value)).strip()


def _inner(value):
    return re.sub(r'^<[^>]+>|</[^>]+>\s*$', '', value.strip())


def convert_faq_blocks(content):
    """Only convert sections with identifiable questions and nonempty answers.

    Existing blocks and ambiguous sections are left intact. The section ends at
    the next heading of the same or higher level, so later content stays outside.
    """
    content = content or ''
    if re.search(r'<!--\s*/?wp:', content, re.I):
        return content
    blocks = _Blocks(content).blocks
    replacements = []
    index = 0
    while index < len(blocks):
        tag, start, end = blocks[index]
        if not re.fullmatch(r'h[1-6]', tag) or not re.search(r'\b(?:faqs?|frequently\s+asked\s+questions)\b', _text(content[start:end]), re.I):
            index += 1
            continue
        level = int(tag[1])
        stop = index + 1
        while stop < len(blocks):
            next_tag = blocks[stop][0]
            if re.fullmatch(r'h[1-6]', next_tag) and int(next_tag[1]) <= level:
                break
            stop += 1
        questions = []
        for position in range(index + 1, stop):
            child_tag, child_start, child_end = blocks[position]
            source = content[child_start:child_end]
            question = ''
            if child_tag == f'h{level + 1}':
                question = _inner(source)
            elif child_tag == 'p':
                bold = re.fullmatch(r'\s*<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>\s*', _inner(source), re.I | re.S)
                if bold and _text(bold[1]).endswith('?'):
                    question = bold[1]
            if question and _text(question):
                questions.append((child_start, child_end, question))
        if questions:
            section_end = blocks[stop][1] if stop < len(blocks) else len(content)
            items = []
            for number, (_, answer_start, question) in enumerate(questions):
                answer_end = questions[number + 1][0] if number + 1 < len(questions) else section_end
                answer = content[answer_start:answer_end]
                # Do not discard or guess incomplete question-and-answer pairs.
                if not _text(answer) or re.search(r'<(?:details|section)\b|<!--\s*/?wp:', answer, re.I):
                    items = []
                    break
                items.append('<details class="faq-item" open><summary>' + question + '</summary>' + answer + '</details>')
            if items:
                intro = content[end:questions[0][0]]
                replacements.append((start, section_end, '<section class="faq-block" data-faq-block="true">' + content[start:end] + intro + ''.join(items) + '</section>'))
        index = stop
    for start, end, value in reversed(replacements):
        content = content[:start] + value + content[end:]
    return content
