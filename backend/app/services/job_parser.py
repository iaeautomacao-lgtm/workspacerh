import http.client
import socket
import ssl
import ipaddress
import re
import unicodedata
import json
from urllib.parse import urlsplit, urljoin
from html.parser import HTMLParser

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'): self.skip += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'): self.skip = max(0, self.skip-1)
    def handle_data(self, data):
        if data.strip() and not self.skip: self.result.append(data.strip())
    def get_text(self): return '\n'.join(self.result)

def public_addresses(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None,443):
        raise ValueError('Use uma URL pública HTTPS sem credenciais.')
    addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Endereço privado ou reservado não permitido.')
    return parts, addresses[0][4][0]

def download(url):
    for _ in range(4):
        parts, address = public_addresses(url)
        conn = http.client.HTTPSConnection(parts.hostname, timeout=15)
        # Pin the validated address while keeping certificate verification/SNI.
        raw = socket.create_connection((address,443), timeout=15)
        conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname)
        try:
            conn.request('GET', parts.path + ('?' + parts.query if parts.query else ''), headers={'User-Agent':'DDM-Recruitment/2.0','Accept':'text/html'})
            response = conn.getresponse()
            if response.status in (301,302,303,307,308):
                url = urljoin(url, response.getheader('Location',''))
                continue
            if response.status != 200: raise ValueError('O site da vaga recusou a leitura. Cole a descrição manualmente.')
            if 'html' not in (response.getheader('Content-Type') or ''): raise ValueError('A URL deve apontar para uma página HTML.')
            content = response.read(2_000_001)
            if len(content) > 2_000_000: raise ValueError('Página excede o limite de leitura.')
            return content.decode('utf-8', errors='replace')
        finally:
            conn.close()
    raise ValueError('A URL tem redirecionamentos demais.')

def postings(value):
    if isinstance(value, list):
        for item in value: yield from postings(item)
    if isinstance(value, dict):
        if value.get('@type') == 'JobPosting' or 'JobPosting' in (value.get('@type') or []): yield value
        if '@graph' in value: yield from postings(value['@graph'])

def extract_text_from_url(url):
    html = download(url)
    for raw in re.findall(r'<script[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            for post in postings(json.loads(raw)):
                parser = HTMLTextExtractor(); parser.feed(post.get('description',''))
                count = post.get('totalJobOpenings')
                return f"Título: {post.get('title','')}\n{parser.get_text()}\n" + (f'Quantidade de vagas: {count}' if count else '')
        except (ValueError, TypeError): pass
    parser = HTMLTextExtractor(); parser.feed(html)
    text = parser.get_text()
    if len(text) < 80: raise ValueError('A página não disponibilizou a descrição. Cole o texto da vaga.')
    return text[:40000]

def detect_openings(text):
    patterns = [r'(?:quantidade|número|numero|total)\s*(?:de\s*)?(?:vagas|posições)\s*[:=]?\s*(\d+)', r'\b(\d+)\s+vagas\b']
    counts = {int(n) for pattern in patterns for n in re.findall(pattern,text,re.I) if 1 <= int(n) <= 10000}
    return counts.pop() if len(counts) == 1 else None

# Cabeçalhos de seção não são requisitos: eles apenas mudam a categoria das linhas seguintes.
SECTIONS = {
    'requisitos': 'mandatory', 'requisitos obrigatorios': 'mandatory', 'obrigatorios': 'mandatory',
    'requisitos tecnicos': 'mandatory', 'conhecimentos tecnicos': 'mandatory', 'qualificacoes': 'mandatory',
    'formacao': 'mandatory', 'formacao academica': 'mandatory', 'escolaridade': 'mandatory',
    'desejaveis': 'desirable', 'desejavel': 'desirable', 'diferenciais': 'desirable', 'diferencial': 'desirable',
    'experiencia': 'experience', 'experiencias': 'experience', 'experiencia profissional': 'experience',
    'perfil': 'competency', 'perfil comportamental': 'competency', 'perfil desejado': 'competency',
    'competencias': 'competency', 'competencias comportamentais': 'competency', 'competencias tecnicas': 'mandatory',
    'habilidades': 'competency', 'soft skills': 'competency',
}
IGNORED_SECTIONS = ('responsabilidades', 'atividades', 'atribuicoes', 'beneficios', 'salario', 'sobre a empresa', 'sobre a vaga', 'horario', 'jornada', 'local de trabalho')

def section_key(line):
    key = ''.join(c for c in unicodedata.normalize('NFKD', line.lower()) if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', key.strip(' :.-')).strip()

def structure_job_requirements(text):
    requirements = []
    category = None
    for line in text.splitlines():
        line = line.strip().strip('-• ').strip()
        if not line: continue
        lower = line.lower()
        key = section_key(line)
        if key in SECTIONS: category = SECTIONS[key]; continue
        if key.startswith(IGNORED_SECTIONS): category=None; continue
        explicit = re.match(r'^(obrigatório|desejável|experiência|competência)\s*:\s*(.+)', line, re.I)
        if explicit:
            cat = {'obrigatório':'mandatory','desejável':'desirable','experiência':'experience','competência':'competency'}[explicit[1].lower()]
            requirements.append({'category':cat,'title':explicit[2],'weight':1})
        elif category and len(line)<250 and not lower.startswith(('título:', 'quantidade', 'vaga:', 'descrição:')):
            requirements.append({'category':category,'title':line,'weight':1})
    return requirements[:40]
