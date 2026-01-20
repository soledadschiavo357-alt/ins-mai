import os
import sys
import re
import concurrent.futures
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, unquote
from colorama import init, Fore, Style
from collections import defaultdict

# Initialize colorama
init(autoreset=True)

# --- Configuration & Constants ---

IGNORE_PATHS = {'.git', 'node_modules', '__pycache__', '.vscode', '.idea', 'venv', 'env'}
IGNORE_URL_PREFIXES = ('/go/', 'cdn-cgi', 'javascript:', 'mailto:', 'tel:', '#')
IGNORE_FILES = {'google', '404.html'} # Filenames containing these strings

class Config:
    BASE_URL = ""
    ROOT_DIR = os.getcwd()
    KEYWORDS = []

# --- Helper Functions ---

def is_ignored_path(path):
    parts = path.split(os.sep)
    return any(p in IGNORE_PATHS for p in parts)

def is_ignored_file(filename):
    return any(ignored in filename for ignored in IGNORE_FILES) or not filename.endswith('.html')

def is_external(url):
    return bool(urlparse(url).netloc)

def normalize_local_url(url, current_file_path):
    """
    Resolves relative URLs to absolute path from root.
    Example: 
    - url="../contact", current="/blog/index.html" -> "/contact"
    - url="/about", current="..." -> "/about"
    """
    if url.startswith('/'):
        return url
    
    # Calculate directory of current file relative to root
    rel_dir = os.path.dirname(os.path.relpath(current_file_path, Config.ROOT_DIR))
    
    if rel_dir == '.':
        return '/' + url
    
    # Construct absolute path
    # We use a dummy base for urljoin to handle relative paths correctly
    dummy_base = f"http://dummy.com/{rel_dir}/"
    joined = urljoin(dummy_base, url)
    return urlparse(joined).path

def check_local_file_exists(url_path):
    """
    Checks if a local file exists for the given URL path.
    Mapping Rules:
    /blog/post -> root/blog/post.html OR root/blog/post/index.html
    / -> root/index.html
    """
    # Remove query string and fragment
    url_path = url_path.split('#')[0].split('?')[0]
    
    if url_path.endswith('/'):
        url_path = url_path[:-1] # Remove trailing slash for path construction
    
    # Case 0: Root
    if not url_path:
        return os.path.exists(os.path.join(Config.ROOT_DIR, 'index.html'))

    # Case 1: Direct file mapping (e.g., /about -> about.html)
    path1 = os.path.join(Config.ROOT_DIR, url_path.lstrip('/') + '.html')
    if os.path.exists(path1):
        return True
        
    # Case 2: Directory index mapping (e.g., /blog -> blog/index.html)
    path2 = os.path.join(Config.ROOT_DIR, url_path.lstrip('/'), 'index.html')
    if os.path.exists(path2):
        return True
        
    # Case 3: Exact file match (rare if Clean URLs are used, but for resources)
    # e.g., /images/logo.png
    path3 = os.path.join(Config.ROOT_DIR, url_path.lstrip('/'))
    if os.path.exists(path3) and os.path.isfile(path3):
        return True
        
    return False

# --- Core Modules ---

class AutoConfig:
    @staticmethod
    def load():
        index_path = os.path.join(Config.ROOT_DIR, 'index.html')
        if not os.path.exists(index_path):
            print(f"{Fore.RED}[CRITICAL] index.html not found in {Config.ROOT_DIR}")
            sys.exit(1)
            
        try:
            with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
                soup = BeautifulSoup(f, 'html.parser')
                
                # Extract Base URL
                canonical = soup.find('link', rel='canonical')
                if canonical and canonical.get('href'):
                    Config.BASE_URL = canonical['href'].rstrip('/')
                    print(f"{Fore.BLUE}[INFO] Auto-configured Base URL: {Config.BASE_URL}")
                else:
                    og_url = soup.find('meta', property='og:url')
                    if og_url and og_url.get('content'):
                        Config.BASE_URL = og_url['content'].rstrip('/')
                        print(f"{Fore.YELLOW}[WARN] Base URL from og:url: {Config.BASE_URL}")
                    else:
                        print(f"{Fore.RED}[WARN] Could not determine Base URL. Defaulting to empty.")
                
                # Extract Keywords
                meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
                if meta_keywords and meta_keywords.get('content'):
                    Config.KEYWORDS = [k.strip() for k in meta_keywords['content'].split(',')]
                    print(f"{Fore.BLUE}[INFO] Keywords loaded: {Config.KEYWORDS}")
                    
        except Exception as e:
            print(f"{Fore.RED}[ERROR] Failed to parse index.html: {e}")
            sys.exit(1)

class AuditResult:
    def __init__(self):
        self.score = 100
        self.errors = []
        self.warnings = []
        self.infos = []
        self.inbound_links = defaultdict(int) # url_path -> count
        self.external_links = set()
        self.pages_scanned = 0

    def add_error(self, msg, penalty=0):
        self.errors.append(msg)
        self.score = max(0, self.score - penalty)

    def add_warning(self, msg, penalty=0):
        self.warnings.append(msg)
        self.score = max(0, self.score - penalty)

    def add_info(self, msg):
        self.infos.append(msg)

class PageAuditor:
    def __init__(self, file_path, result_obj):
        self.file_path = file_path
        self.rel_path = os.path.relpath(file_path, Config.ROOT_DIR)
        self.result = result_obj
        self.soup = None
        self.content = ""
        
    def run(self):
        try:
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                self.content = f.read()
                self.soup = BeautifulSoup(self.content, 'html.parser')
                
            self.check_h1()
            self.check_schema()
            self.check_breadcrumb()
            self.check_links()
            
            self.result.pages_scanned += 1
            
        except Exception as e:
            self.result.add_error(f"Failed to process {self.rel_path}: {e}")

    def check_h1(self):
        h1s = self.soup.find_all('h1')
        if len(h1s) == 0:
            self.result.add_error(f"Missing H1 tag in {self.rel_path}", penalty=5)
        elif len(h1s) > 1:
            self.result.add_warning(f"Multiple H1 tags ({len(h1s)}) in {self.rel_path}", penalty=0) # Google doesn't strictly penalize multiple H1s anymore, but it's bad practice

    def check_schema(self):
        schemas = self.soup.find_all('script', type='application/ld+json')
        if not schemas:
            self.result.add_warning(f"No Schema (JSON-LD) found in {self.rel_path}", penalty=2)

    def check_breadcrumb(self):
        # Skip index.html for breadcrumb check
        if self.rel_path == 'index.html':
            return
            
        has_breadcrumb = False
        if self.soup.find(attrs={"aria-label": "Breadcrumb"}) or \
           self.soup.find(attrs={"aria-label": "breadcrumb"}) or \
           self.soup.find(class_=re.compile("breadcrumb", re.I)):
            has_breadcrumb = True
            
        if not has_breadcrumb:
            # Check if it's a deep page
            if '/' in self.rel_path.replace('\\', '/'):
                 self.result.add_warning(f"No Breadcrumb found in deep page {self.rel_path}", penalty=0)

    def check_links(self):
        for a in self.soup.find_all('a', href=True):
            raw_href = a['href']
            
            # Skip ignored links
            if raw_href.startswith(IGNORE_URL_PREFIXES):
                continue
                
            # 1. External Links
            if is_external(raw_href):
                # Check for absolute path with own domain (e.g., https://mydomain.com/blog)
                if Config.BASE_URL and raw_href.startswith(Config.BASE_URL):
                    self.result.add_warning(f"Internal link using full URL in {self.rel_path}: {raw_href} -> Should be relative/absolute path", penalty=2)
                    path = raw_href[len(Config.BASE_URL):]
                    if not path: path = "/"
                    self.process_internal_link(path)
                else:
                    self.result.external_links.add(raw_href)
                    # Check rel attributes for external links
                    rel = a.get('rel', [])
                    if 'noopener' not in rel and 'noreferrer' not in rel:
                        # self.result.add_warning(f"External link missing rel='noopener' in {self.rel_path}: {raw_href}")
                        pass # Less critical now, modern browsers handle it
                continue
                
            # 2. Internal Links
            self.process_internal_link(raw_href)

    def process_internal_link(self, raw_href):
        # Clean URL check
        if raw_href.endswith('.html') and not raw_href.split('/')[-1] == 'index.html': # Allowing index.html if explicitly linked, though usually / is preferred
             self.result.add_warning(f"Link with .html extension in {self.rel_path}: {raw_href} -> Should be Clean URL", penalty=2)
        
        # Relative path check (Warning)
        if not raw_href.startswith('/'):
            self.result.add_warning(f"Relative path used in {self.rel_path}: {raw_href} -> Should be absolute path (starts with /)", penalty=2)

        # Resolve to absolute path for existence check
        abs_path = normalize_local_url(raw_href, self.file_path)
        
        # Dead Link Check
        if not check_local_file_exists(abs_path):
            self.result.add_error(f"Dead Internal Link in {self.rel_path}: {raw_href} (Resolves to {abs_path})", penalty=10)
        else:
            # Track inbound links
            # Normalize for counting (remove trailing slash unless root)
            clean_path = abs_path.split('#')[0].split('?')[0]
            if clean_path != '/' and clean_path.endswith('/'):
                clean_path = clean_path[:-1]
            if clean_path == '': clean_path = '/'
            
            self.result.inbound_links[clean_path] += 1

class ExternalLinkChecker:
    @staticmethod
    def check_all(links):
        print(f"\n{Fore.CYAN}[INFO] Checking {len(links)} unique external links asynchronously...")
        dead_links = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {executor.submit(ExternalLinkChecker.check_one, url): url for url in links}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    status, msg = future.result()
                    if status >= 400:
                        dead_links.append((url, status))
                except Exception as exc:
                    dead_links.append((url, str(exc)))
                    
        return dead_links

    @staticmethod
    def check_one(url):
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; SEOAuditBot/1.0)'}
        try:
            r = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
            # If 405 Method Not Allowed, try GET
            if r.status_code == 405:
                r = requests.get(url, headers=headers, timeout=5, stream=True)
            return r.status_code, "OK"
        except requests.exceptions.RequestException as e:
            return 999, str(e)

# --- Main Execution ---

def main():
    print(f"{Fore.CYAN}=== Starting SEO Audit ==={Style.RESET_ALL}")
    
    # 1. Auto Config
    AutoConfig.load()
    
    audit_result = AuditResult()
    
    # 2. Walk Directory
    html_files = []
    for root, dirs, files in os.walk(Config.ROOT_DIR):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if not is_ignored_path(os.path.join(root, d))]
        
        for file in files:
            if file.endswith('.html') and not is_ignored_file(file):
                html_files.append(os.path.join(root, file))
                
    print(f"{Fore.BLUE}[INFO] Found {len(html_files)} HTML files to scan.")
    
    # 3. Audit Pages
    for file_path in html_files:
        auditor = PageAuditor(file_path, audit_result)
        auditor.run()
        
    # 4. Orphan Page Check
    # Convert file paths to expected URL paths for comparison
    for file_path in html_files:
        rel_path = os.path.relpath(file_path, Config.ROOT_DIR)
        
        # Skip index.html from orphan check
        if rel_path == 'index.html':
            continue
            
        # Determine likely URL path(s) for this file
        # e.g., blog/post.html -> /blog/post
        # e.g., blog/index.html -> /blog
        url_paths = []
        
        if rel_path.endswith('index.html'):
            url_paths.append('/' + os.path.dirname(rel_path))
            if url_paths[0] == '/.': url_paths[0] = '/' # Handle root index
        else:
            url_paths.append('/' + rel_path[:-5]) # remove .html
            
        # Normalize paths (ensure leading slash, no trailing slash unless root)
        normalized_paths = []
        for p in url_paths:
            p = p.replace('\\', '/')
            if p != '/' and p.endswith('/'): p = p[:-1]
            normalized_paths.append(p)
            
        # Check if any of these possible URLs have inbound links
        is_orphan = True
        for p in normalized_paths:
            if audit_result.inbound_links.get(p, 0) > 0:
                is_orphan = False
                break
                
        # Also check exact file match in inbound links (in case of .html links)
        # e.g. /about.html
        raw_file_url = '/' + rel_path.replace('\\', '/')
        if audit_result.inbound_links.get(raw_file_url, 0) > 0:
            is_orphan = False
            
        if is_orphan:
            audit_result.add_warning(f"Orphan Page (No inbound links): {rel_path}", penalty=5)

    # 5. External Link Check
    if audit_result.external_links:
        dead_external = ExternalLinkChecker.check_all(audit_result.external_links)
        for url, status in dead_external:
            audit_result.add_error(f"Dead External Link: {url} (Status: {status})", penalty=5)

    # --- Report Generation ---
    print(f"\n{Fore.CYAN}=== Audit Report ==={Style.RESET_ALL}")
    
    # Top Pages
    print(f"\n{Fore.MAGENTA}Top 10 Linked Pages:{Style.RESET_ALL}")
    sorted_links = sorted(audit_result.inbound_links.items(), key=lambda x: x[1], reverse=True)[:10]
    for url, count in sorted_links:
        print(f"  {count} refs: {url}")
        
    # Issues
    if audit_result.errors:
        print(f"\n{Fore.RED}Errors ({len(audit_result.errors)}):{Style.RESET_ALL}")
        for err in audit_result.errors:
            print(f"  - {err}")
            
    if audit_result.warnings:
        print(f"\n{Fore.YELLOW}Warnings ({len(audit_result.warnings)}):{Style.RESET_ALL}")
        # Limit warnings output if too many
        if len(audit_result.warnings) > 20:
             print(f"  (Showing first 20 of {len(audit_result.warnings)})")
             for warn in audit_result.warnings[:20]:
                print(f"  - {warn}")
        else:
            for warn in audit_result.warnings:
                print(f"  - {warn}")

    # Final Score
    score_color = Fore.GREEN
    if audit_result.score < 80: score_color = Fore.YELLOW
    if audit_result.score < 50: score_color = Fore.RED
    
    print(f"\n{Style.BRIGHT}Final Score: {score_color}{audit_result.score}/100{Style.RESET_ALL}")
    
    if audit_result.score < 100:
        print(f"\n{Fore.BLUE}Actionable Advice:{Style.RESET_ALL}")
        if any("Dead Internal Link" in e for e in audit_result.errors):
            print("- Fix broken internal links immediately. They are bad for SEO and UX.")
        if any("Missing H1" in e for e in audit_result.errors):
            print("- Ensure every page has exactly one H1 tag describing the content.")
        if any("Orphan Page" in w for w in audit_result.warnings):
            print("- Link to orphan pages from other parts of your site (e.g., Blog Index, Sitemap).")
        if any("Link with .html extension" in w for w in audit_result.warnings):
            print("- Update internal links to use Clean URLs (remove .html suffix) to match server routing.")

if __name__ == "__main__":
    main()