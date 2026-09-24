from html.parser import HTMLParser
from .contracts import PipelineError


class PublicHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.hidden = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def parse_html(content):
    if len(content) > 2_000_000:
        raise PipelineError('MAX_BYTES_EXCEEDED')
    parser = PublicHTML()
    parser.feed(content.decode('utf-8'))
    return {'text': ' '.join(parser.parts), 'links': parser.links}
