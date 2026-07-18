#!/usr/bin/env python3
import os
import re
import urllib.request
import urllib.error
import concurrent.futures
from html.parser import HTMLParser

# Paths
WORKSPACE_DIR = "/Users/srikanthnandiraju/ANTIGRAVITY_WORKSPACE"
WIKI_DIR = os.path.join(WORKSPACE_DIR, "GitSitesKnowledgeWiki")
PARENT_INDEX = os.path.join(WORKSPACE_DIR, "index.html")
OUTPUT_FILE = os.path.join(WIKI_DIR, "index.html")

class HTMLMetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = None
        self.description = None
        self.in_title = False
        
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'title':
            self.in_title = True
        elif tag.lower() == 'meta':
            attrs_dict = {k.lower(): v for k, v in attrs}
            if attrs_dict.get('name') == 'description':
                self.description = attrs_dict.get('content')
            elif attrs_dict.get('property') == 'og:description':
                if not self.description:
                    self.description = attrs_dict.get('content')
                    
    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.in_title = False
            
    def handle_data(self, data):
        if self.in_title:
            if self.title:
                self.title += data
            else:
                self.title = data

def get_git_remote_url(repo_path):
    config_path = os.path.join(repo_path, '.git', 'config')
    if not os.path.exists(config_path):
        return None
    url = None
    try:
        with open(config_path, 'r', encoding='utf-8', errors='ignore') as f:
            in_remote_origin = False
            for line in f:
                line = line.strip()
                if line.startswith('[remote "origin"]'):
                    in_remote_origin = True
                elif line.startswith('[') and in_remote_origin:
                    in_remote_origin = False
                elif in_remote_origin and line.startswith('url ='):
                    url = line.split('=', 1)[1].strip()
                    break
    except Exception:
        pass
    return url

def parse_github_url(url):
    if not url:
        return None, None
    url = url.strip()
    if 'github.com' not in url:
        return None, None
    m = re.search(r'github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?$', url)
    if m:
        return m.group(1), m.group(2)
    return None, None

def get_cname(repo_path):
    cname_path = os.path.join(repo_path, 'CNAME')
    if os.path.exists(cname_path):
        try:
            with open(cname_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            pass
    docs_cname_path = os.path.join(repo_path, 'docs', 'CNAME')
    if os.path.exists(docs_cname_path):
        try:
            with open(docs_cname_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            pass
    return None

def get_html_metadata(repo_path):
    index_paths = [
        os.path.join(repo_path, 'index.html'),
        os.path.join(repo_path, 'docs', 'index.html')
    ]
    for path in index_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                parser = HTMLMetaParser()
                parser.feed(content)
                title = parser.title.strip() if parser.title else None
                desc = parser.description.strip() if parser.description else None
                if title or desc:
                    return title, desc
            except Exception:
                pass
    return None, None

def get_readme_description(repo_path):
    readme_names = ['README.md', 'readme.md', 'README.markdown', 'README']
    for name in readme_names:
        path = os.path.join(repo_path, name)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                desc_lines = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith('#'):
                        continue
                    if line.startswith('!['):
                        continue
                    if line.startswith('[') and ']:' in line:
                        continue
                    cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line)
                    cleaned = re.sub(r'[*_`~]', '', cleaned)
                    desc_lines.append(cleaned)
                    if len(desc_lines) >= 3:
                        break
                if desc_lines:
                    return ' '.join(desc_lines)[:200]
            except Exception:
                pass
    return None

def load_parent_project_info():
    info = {}
    if os.path.exists(PARENT_INDEX):
        try:
            with open(PARENT_INDEX, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            pattern = r'\{\s*name:\s*"([^"]+)",\s*tag:\s*"([^"]+)",\s*desc:\s*"([^"]+)"\s*\}'
            matches = re.findall(pattern, content)
            for name, tag, desc in matches:
                info[name] = {"tag": tag, "desc": desc}
        except Exception as e:
            print(f"Error reading parent index: {e}")
    return info

def probe_pages_site(owner, repo, cname=None):
    urls_to_try = []
    if cname:
        if cname.startswith('http://') or cname.startswith('https://'):
            urls_to_try.append(cname)
        else:
            urls_to_try.append(f'https://{cname}/')
            urls_to_try.append(f'http://{cname}/')
            
    if repo.lower() == f'{owner.lower()}.github.io':
        urls_to_try.append(f'https://{owner}.github.io/')
    else:
        urls_to_try.append(f'https://{owner}.github.io/{repo}/')
        
    for url in urls_to_try:
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    return True, response.url
        except urllib.error.HTTPError as e:
            if e.code in [301, 302, 303, 307, 308]:
                location = e.headers.get('Location')
                if location:
                    return True, location
            elif e.code in [401, 403]:
                return True, url
        except Exception:
            pass
    return False, None

def process_repo(dir_name, parent_info):
    repo_path = os.path.join(WORKSPACE_DIR, dir_name)
    if not os.path.isdir(repo_path) or dir_name == "GitSitesKnowledgeWiki":
        return None
        
    remote_url = get_git_remote_url(repo_path)
    if not remote_url:
        return None
        
    owner, repo = parse_github_url(remote_url)
    if not owner or not repo:
        return None
        
    cname = get_cname(repo_path)
    
    is_active, final_url = probe_pages_site(owner, repo, cname)
    if not is_active:
        return None
        
    desc = None
    tag = "misc"
    
    if dir_name in parent_info:
        desc = parent_info[dir_name].get("desc")
        tag = parent_info[dir_name].get("tag", "misc")
    
    html_title, html_desc = get_html_metadata(repo_path)
    if not desc and html_desc:
        desc = html_desc
        
    if not desc:
        desc = get_readme_description(repo_path)
        
    if not desc:
        desc = f"Static site for {dir_name} on GitHub Pages."
        
    title = html_title or dir_name.replace('_', ' ').replace('-', ' ').title()
    desc = desc.replace('"', '\\"').replace('\n', ' ')
    
    return {
        "name": dir_name,
        "title": title,
        "owner": owner,
        "repo": repo,
        "tag": tag,
        "github_url": f"https://github.com/{owner}/{repo}",
        "pages_url": final_url or f"https://{owner}.github.io/{repo}/",
        "desc": desc
    }

def main():
    print("Scanning workspaces for Git repositories...")
    parent_info = load_parent_project_info()
    dirs = [d for d in os.listdir(WORKSPACE_DIR) if os.path.isdir(os.path.join(WORKSPACE_DIR, d))]
    active_pages = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_repo, d, parent_info): d for d in dirs}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                print(f"Found active GitHub Pages: {res['name']} -> {res['pages_url']}")
                active_pages.append(res)
                
    active_pages.sort(key=lambda x: x["title"])
    
    print(f"Generating HTML wiki with {len(active_pages)} active sites...")
    
    js_projects = "[\n"
    for item in active_pages:
        js_projects += f"      {{ title: \"{item['title']}\", tag: \"{item['tag']}\", desc: \"{item['desc']}\", github_url: \"{item['github_url']}\", pages_url: \"{item['pages_url']}\" }},\n"
    js_projects += "    ]"

    html_content = f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Srikanth Nandiraju | GitHub Pages Landing Page</title>
  
  <!-- SEO Meta Tags -->
  <meta name="title" content="Srikanth Nandiraju | GitHub Pages Landing Page">
  <meta name="description" content="Curated landing page of active GitHub Pages websites, portfolios, and projects by Srikanth Nandiraju (nandiraju). Explore live web apps, AI tools, and research pages.">
  <meta name="keywords" content="Srikanth Nandiraju, Nandiraju, GitHub Pages, Wiki, Landing Page, Web Developer, Portfolio, Projects, AI, React, Expo">
  <meta name="author" content="Srikanth Nandiraju">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="https://srikanth.nandiraju.com/wiki/">

  <!-- Open Graph / Facebook -->
  <meta property="og:type" content="profile">
  <meta property="og:url" content="https://srikanth.nandiraju.com/wiki/">
  <meta property="og:title" content="Srikanth Nandiraju | GitHub Pages Landing Page">
  <meta property="og:description" content="Explore active GitHub Pages websites, portfolios, and projects by Srikanth Nandiraju.">
  <meta property="og:image" content="https://avatars.githubusercontent.com/u/589121?v=4">
  <meta property="profile:first_name" content="Srikanth">
  <meta property="profile:last_name" content="Nandiraju">
  <meta property="profile:username" content="nandiraju">

  <!-- Twitter -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:url" content="https://srikanth.nandiraju.com/wiki/">
  <meta name="twitter:title" content="Srikanth Nandiraju | GitHub Pages Landing Page">
  <meta name="twitter:description" content="Explore active GitHub Pages websites, portfolios, and projects by Srikanth Nandiraju.">
  <meta name="twitter:image" content="https://avatars.githubusercontent.com/u/589121?v=4">

  <!-- Performance Optimizations -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="dns-prefetch" href="https://fonts.googleapis.com">
  <link rel="dns-prefetch" href="https://fonts.gstatic.com">
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  
  <!-- Ionicons -->
  <script type="module" src="https://unpkg.com/ionicons@7.1.0/dist/ionicons/ionicons.esm.js"></script>
  <script nomodule src="https://unpkg.com/ionicons@7.1.0/dist/ionicons/ionicons.js"></script>

  <!-- GSAP -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
  <style>
    :root {{
      --transition-speed: 0.2s;
      --bg: #ffffff;
      --card-bg: #fafbfc;
      --card-border: rgba(15, 23, 42, 0.08);
      --card-hover-border: rgba(99, 102, 241, 0.4);
      --text: #0f172a;
      --text-muted: #64748b;
      --accent: #7c3aed;
      --accent-hover: #5b21b6;
      --accent-glow: rgba(124, 58, 237, 0.08);
      --th-bg: #f1f5f9;
      --table-border: rgba(15, 23, 42, 0.06);
      --tr-hover: rgba(15, 23, 42, 0.02);
      --btn-bg: #f1f5f9;
      --btn-active-bg: #7c3aed;
      --btn-active-text: #ffffff;
      --input-border: rgba(15, 23, 42, 0.12);
      --shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.04), 0 8px 10px -6px rgba(15, 23, 42, 0.04);
    }}

    :root[data-theme="dark"] {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: rgba(255, 255, 255, 0.08);
      --card-hover-border: rgba(99, 102, 241, 0.4);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --accent: #6366f1;
      --accent-hover: #4f46e5;
      --accent-glow: rgba(99, 102, 241, 0.15);
      --th-bg: #1f2937;
      --table-border: rgba(255, 255, 255, 0.06);
      --tr-hover: rgba(255, 255, 255, 0.02);
      --btn-bg: #1f2937;
      --btn-active-bg: #6366f1;
      --btn-active-text: #ffffff;
      --input-border: rgba(255, 255, 255, 0.1);
      --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: 'Outfit', sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 0;
      min-height: 100vh;
      transition: background-color var(--transition-speed) ease, color var(--transition-speed) ease;
      -webkit-font-smoothing: antialiased;
    }}

    .container {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 0 1.5rem;
    }}

    /* Header Nav */
    header.main-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1.5rem 0;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 3.5rem;
    }}
    
    header.main-header .logo {{
      font-weight: 800;
      font-size: 1.35rem;
      letter-spacing: -0.03em;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}

    header.main-header .logo span {{
      color: var(--accent);
    }}

    /* Theme Toggle */
    .theme-toggle-btn {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 0.5rem;
      border-radius: 50%;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 2.3rem;
      height: 2.3rem;
      box-shadow: var(--shadow);
      transition: all 0.2s ease;
    }}

    .theme-toggle-btn:hover {{
      border-color: var(--accent);
      transform: scale(1.05);
    }}

    /* Hero Section */
    .hero-section {{
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 3rem;
      align-items: center;
      margin-bottom: 6rem;
    }}

    @media (max-width: 900px) {{
      .hero-section {{
        grid-template-columns: 1fr;
        gap: 3rem;
        text-align: center;
      }}
      .hero-ctas {{
        justify-content: center;
      }}
      .hero-social-proof {{
        justify-content: center;
      }}
    }}

    .hero-badge {{
      display: inline-block;
      font-size: 0.78rem;
      font-weight: 600;
      color: #b8296a;
      background: #fdf2f8;
      padding: 0.35rem 0.85rem;
      border-radius: 20px;
      margin-bottom: 1.25rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    :root[data-theme="dark"] .hero-badge {{
      background: rgba(220, 38, 38, 0.15);
      color: #f472b6;
    }}

    .hero-title {{
      font-size: 3.25rem;
      font-weight: 800;
      line-height: 1.1;
      letter-spacing: -0.04em;
      color: var(--text);
      margin-bottom: 1.25rem;
    }}

    .hero-title span {{
      color: var(--accent);
      background: linear-gradient(135deg, var(--accent) 0%, #db2777 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    .hero-text {{
      font-size: 1.1rem;
      color: var(--text-muted);
      font-weight: 300;
      margin-bottom: 2rem;
      max-width: 520px;
      line-height: 1.6;
    }}

    @media (max-width: 900px) {{
      .hero-text {{
        margin-left: auto;
        margin-right: auto;
      }}
    }}

    .hero-ctas {{
      display: flex;
      gap: 1rem;
      margin-bottom: 2.5rem;
      flex-wrap: wrap;
    }}

    .cta-btn {{
      display: inline-flex;
      align-items: center;
      padding: 0.75rem 1.5rem;
      border-radius: 24px;
      font-size: 0.9rem;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.2s ease;
      box-shadow: var(--shadow);
    }}

    .cta-primary {{
      background: var(--text);
      color: var(--bg);
    }}

    .cta-primary:hover {{
      opacity: 0.9;
      transform: translateY(-1px);
    }}

    .cta-secondary {{
      background: var(--card-bg);
      color: var(--text);
      border: 1px solid var(--card-border);
    }}

    .cta-secondary:hover {{
      border-color: var(--accent);
      transform: translateY(-1px);
    }}

    .hero-social-proof {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}

    .avatar-stack {{
      display: flex;
    }}

    .avatar {{
      width: 28px;
      height: 28px;
      border-radius: 50%;
      border: 2px solid var(--bg);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 0.65rem;
      font-weight: 700;
      margin-left: -8px;
    }}

    .avatar:first-child {{
      margin-left: 0;
    }}

    .social-proof-text {{
      font-size: 0.82rem;
      color: var(--text-muted);
      font-weight: 400;
    }}

    /* Dashboard Mockup styles */
    .dashboard-mockup {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 20px 40px -15px rgba(0,0,0,0.1);
      aspect-ratio: 4 / 3;
      display: flex;
      flex-direction: column;
    }}

    .mockup-header {{
      background: rgba(0,0,0,0.01);
      border-bottom: 1px solid var(--card-border);
      padding: 0.6rem 1rem;
      display: flex;
      align-items: center;
      gap: 0.4rem;
    }}

    .mockup-dot {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
    }}

    .mockup-dot.red {{ background-color: #f87171; }}
    .mockup-dot.yellow {{ background-color: #fbbf24; }}
    .mockup-dot.green {{ background-color: #34d399; }}

    .mockup-title {{
      font-size: 0.7rem;
      color: var(--text-muted);
      margin-left: auto;
      margin-right: auto;
      font-weight: 500;
      font-family: monospace;
      opacity: 0.7;
    }}

    .mockup-content {{
      display: flex;
      flex-grow: 1;
    }}

    .mockup-sidebar {{
      width: 50px;
      border-right: 1px solid var(--card-border);
      background: rgba(0,0,0,0.01);
      padding: 1rem 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.85rem;
    }}

    .sidebar-item {{
      width: 24px;
      height: 24px;
      border-radius: 6px;
      background: var(--btn-bg);
      opacity: 0.4;
    }}

    .sidebar-item.active {{
      background: var(--accent);
      opacity: 1;
    }}

    .mockup-main {{
      flex-grow: 1;
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }}

    .mockup-card {{
      background: #f8fafc;
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 0.85rem;
      display: flex;
      flex-direction: column;
    }}

    :root[data-theme="dark"] .mockup-card {{
      background: rgba(255, 255, 255, 0.02);
    }}

    .stat-label {{
      font-size: 0.68rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.25rem;
      font-weight: 500;
    }}

    .stat-value-row {{
      display: flex;
      align-items: baseline;
      gap: 0.5rem;
    }}

    .stat-value {{
      font-size: 1.8rem;
      font-weight: 700;
    }}

    .growth-badge {{
      font-size: 0.65rem;
      color: #10b981;
      background: rgba(16, 185, 129, 0.1);
      padding: 0.15rem 0.4rem;
      border-radius: 10px;
      font-weight: 600;
    }}

    .mini-bar-chart {{
      display: flex;
      align-items: flex-end;
      gap: 6px;
      height: 36px;
      margin-top: 0.5rem;
    }}

    .bar {{
      flex-grow: 1;
      background: var(--accent);
      opacity: 0.15;
      border-radius: 3px 3px 0 0;
      transition: opacity 0.3s;
    }}

    .bar:last-child {{
      opacity: 0.85;
    }}

    .mockup-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }}

    .stat-value-sub {{
      font-size: 1.1rem;
      font-weight: 600;
    }}

    .status-indicator {{
      font-size: 0.72rem;
      color: #10b981;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      margin-top: 0.25rem;
    }}

    .status-indicator::before {{
      content: '';
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #10b981;
      display: inline-block;
      box-shadow: 0 0 8px #10b981;
    }}

    /* Categories Features Grid */
    .categories-section {{
      margin-bottom: 6rem;
      text-align: center;
    }}

    .section-title {{
      font-size: 2rem;
      font-weight: 800;
      line-height: 1.25;
      letter-spacing: -0.03em;
      margin-bottom: 3.5rem;
      color: var(--text);
    }}

    .section-title span {{
      color: var(--accent);
      background: linear-gradient(135deg, var(--accent) 0%, #db2777 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    .categories-grid {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 1.5rem;
    }}

    @media (max-width: 1024px) {{
      .categories-grid {{
        grid-template-columns: repeat(3, 1fr);
      }}
    }}

    @media (max-width: 640px) {{
      .categories-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    .category-item {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 1.5rem 1.25rem;
      text-align: center;
      transition: all 0.2s ease;
      box-shadow: var(--shadow);
    }}

    .category-item:hover {{
      transform: translateY(-2px);
      border-color: var(--card-hover-border);
    }}

    .category-icon-wrapper {{
      width: 48px;
      height: 48px;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 1.25rem;
    }}

    .category-icon-wrapper.web {{ background-color: #f0fdf4; color: #16a34a; }}
    .category-icon-wrapper.mobile {{ background-color: #f5f3ff; color: #7c3aed; }}
    .category-icon-wrapper.ai {{ background-color: #fff7ed; color: #ea580c; }}
    .category-icon-wrapper.data {{ background-color: #f0f9ff; color: #0284c7; }}
    .category-icon-wrapper.misc {{ background-color: #fdf2f8; color: #db2777; }}

    :root[data-theme="dark"] .category-icon-wrapper {{
      background-color: rgba(255, 255, 255, 0.05) !important;
    }}
    :root[data-theme="dark"] .category-icon-wrapper.web {{ color: #4ade80; }}
    :root[data-theme="dark"] .category-icon-wrapper.mobile {{ color: #a78bfa; }}
    :root[data-theme="dark"] .category-icon-wrapper.ai {{ color: #f97316; }}
    :root[data-theme="dark"] .category-icon-wrapper.data {{ color: #38bdf8; }}
    :root[data-theme="dark"] .category-icon-wrapper.misc {{ color: #f472b6; }}

    .category-item h4 {{
      font-size: 0.95rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
      color: var(--text);
    }}

    .category-item p {{
      font-size: 0.8rem;
      color: var(--text-muted);
      line-height: 1.5;
      font-weight: 300;
    }}

    /* Secondary Hero */
    .sec-hero-section {{
      margin-bottom: 6rem;
    }}

    .sec-hero-card {{
      background: rgba(124, 58, 237, 0.015);
      border: 1px solid var(--card-border);
      border-radius: 24px;
      padding: 3.5rem 3rem;
      display: grid;
      grid-template-columns: 1.2fr 1fr 0.8fr;
      gap: 2.5rem;
      align-items: center;
      box-shadow: var(--shadow);
    }}

    @media (max-width: 1024px) {{
      .sec-hero-card {{
        grid-template-columns: 1.2fr 1fr;
      }}
      .sec-hero-right {{
        grid-column: 1 / -1;
        display: flex !important;
        flex-direction: row !important;
        justify-content: space-between;
        gap: 1.5rem;
      }}
    }}

    @media (max-width: 768px) {{
      .sec-hero-card {{
        grid-template-columns: 1fr;
        padding: 2.5rem 1.5rem;
        text-align: center;
      }}
      .sec-hero-center {{
        display: none;
      }}
      .sec-hero-right {{
        flex-direction: column !important;
      }}
      .inline-cta {{
        margin-left: auto;
        margin-right: auto;
      }}
    }}

    .badge-accent {{
      display: inline-block;
      font-size: 0.72rem;
      font-weight: 600;
      color: #7c3aed;
      background: #f5f3ff;
      padding: 0.3rem 0.75rem;
      border-radius: 20px;
      margin-bottom: 1rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    :root[data-theme="dark"] .badge-accent {{
      background: rgba(124, 58, 237, 0.2);
      color: #c084fc;
    }}

    .sec-hero-left h3 {{
      font-size: 2rem;
      font-weight: 800;
      line-height: 1.2;
      letter-spacing: -0.03em;
      margin-bottom: 1rem;
      color: var(--text);
    }}

    .sec-hero-left h3 span {{
      color: var(--accent);
      background: linear-gradient(135deg, var(--accent) 0%, #db2777 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    .sec-hero-left p {{
      font-size: 0.95rem;
      color: var(--text-muted);
      font-weight: 300;
      margin-bottom: 1.75rem;
      line-height: 1.6;
    }}

    .inline-cta {{
      display: inline-flex;
      font-size: 0.85rem;
      padding: 0.65rem 1.3rem;
    }}

    /* Device mock */
    .mock-device {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      overflow: hidden;
      aspect-ratio: 4 / 3;
      box-shadow: 0 15px 30px rgba(0,0,0,0.05);
      display: flex;
      flex-direction: column;
    }}

    .mock-device-header {{
      background: rgba(0,0,0,0.01);
      border-bottom: 1px solid var(--card-border);
      padding: 0.5rem;
      display: flex;
      gap: 0.35rem;
    }}

    .mock-device-header .dot {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--card-border);
    }}

    .mock-device-screen {{
      flex-grow: 1;
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      background: var(--bg);
    }}

    .osakhi-logo {{
      font-weight: 800;
      font-size: 0.95rem;
      color: #6366f1;
    }}

    .screen-stat-row {{
      display: flex;
      gap: 0.5rem;
    }}

    .screen-stat {{
      flex-grow: 1;
      height: 30px;
      border-radius: 6px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
    }}

    .screen-chart-placeholder {{
      flex-grow: 1;
      border-radius: 6px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      position: relative;
      overflow: hidden;
    }}

    .screen-chart-placeholder::after {{
      content: '';
      position: absolute;
      bottom: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: linear-gradient(180deg, transparent 50%, var(--accent-glow) 100%);
    }}

    /* Right side stats badges */
    .sec-hero-right {{
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }}

    .stat-badge-item {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 1rem;
      box-shadow: var(--shadow);
    }}

    .stat-badge-item.violet {{ border-left: 3px solid #7c3aed; }}
    .stat-badge-item.peach {{ border-left: 3px solid #f97316; }}
    .stat-badge-item.green {{ border-left: 3px solid #10b981; }}

    .stat-badge-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.25rem;
    }}

    .badge-num {{
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--text);
    }}

    .badge-icon {{
      font-size: 1.1rem;
    }}

    .badge-label {{
      font-size: 0.75rem;
      color: var(--text-muted);
      font-weight: 400;
    }}

    /* Directory Controls Section */
    .controls-row {{
      display: flex;
      gap: 1rem;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
      align-items: center;
    }}

    .search-box {{
      flex-grow: 1;
      min-width: 250px;
    }}

    .search-input {{
      width: 100%;
      background: var(--card-bg);
      border: 1px solid var(--input-border);
      border-radius: 12px;
      padding: 0.75rem 1.25rem;
      color: var(--text);
      font-size: 0.95rem;
      font-family: inherit;
      outline: none;
      transition: all 0.2s ease;
      box-shadow: var(--shadow);
    }}

    .search-input:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-glow);
    }}

    .search-input::placeholder {{
      color: var(--text-muted);
      opacity: 0.6;
    }}

    .action-buttons {{
      display: flex;
      gap: 0.75rem;
      align-items: center;
    }}

    .btn-group {{
      display: flex;
      background: var(--btn-bg);
      padding: 0.25rem;
      border-radius: 10px;
      box-shadow: var(--shadow);
    }}

    .control-btn {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 0.5rem 1rem;
      font-size: 0.85rem;
      font-weight: 500;
      border-radius: 8px;
      cursor: pointer;
      font-family: inherit;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.2s ease;
    }}

    .control-btn.active {{
      background: var(--btn-active-bg);
      color: var(--btn-active-text);
    }}

    .control-btn:hover:not(.active) {{
      color: var(--text);
      background: rgba(0, 0, 0, 0.03);
    }}

    .category-filters-wrapper {{
      margin-bottom: 2.25rem;
    }}

    .category-filters {{
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
      justify-content: flex-start;
    }}

    .filter-pill {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 0.4rem 1rem;
      font-size: 0.8rem;
      font-weight: 500;
      border-radius: 20px;
      cursor: pointer;
      font-family: inherit;
      transition: all 0.2s ease;
      box-shadow: var(--shadow);
    }}

    .filter-pill.active {{
      background: var(--btn-active-bg);
      color: var(--btn-active-text);
      border-color: var(--accent);
    }}

    .filter-pill:hover:not(.active) {{
      color: var(--text);
      border-color: var(--card-hover-border);
    }}

    .stats {{
      font-size: 0.875rem;
      color: var(--text-muted);
      margin-bottom: 1.25rem;
      font-weight: 400;
    }}

    /* Card View Layout */
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
      gap: 1.25rem;
    }}

    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 18px;
      padding: 1.75rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      overflow: hidden;
      box-shadow: var(--shadow);
      content-visibility: auto;
      contain-intrinsic-size: auto 150px;
    }}

    .card:hover {{
      transform: translateY(-4px);
      border-color: var(--card-hover-border);
      box-shadow: 0 15px 30px -10px var(--accent-glow);
    }}

    .card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 2px;
      background: linear-gradient(90deg, transparent, var(--accent), transparent);
      transform: translateX(-100%);
      transition: transform 0.5s ease;
    }}

    .card:hover::before {{
      transform: translateX(100%);
    }}

    .card-title-row {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 0.85rem;
    }}

    .card-icon {{
      width: 32px;
      height: 32px;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }}

    .card-icon.tag-web {{ background-color: #f0fdf4; color: #16a34a; }}
    .card-icon.tag-mobile {{ background-color: #f5f3ff; color: #7c3aed; }}
    .card-icon.tag-ai {{ background-color: #fff7ed; color: #ea580c; }}
    .card-icon.tag-data {{ background-color: #f0f9ff; color: #0284c7; }}
    .card-icon.tag-api {{ background-color: #e0f2fe; color: #0369a1; }}
    .card-icon.tag-misc {{ background-color: #fdf2f8; color: #db2777; }}

    :root[data-theme="dark"] .card-icon {{
      background-color: rgba(255, 255, 255, 0.05) !important;
    }}
    :root[data-theme="dark"] .card-icon.tag-web {{ color: #4ade80; }}
    :root[data-theme="dark"] .card-icon.tag-mobile {{ color: #a78bfa; }}
    :root[data-theme="dark"] .card-icon.tag-ai {{ color: #f97316; }}
    :root[data-theme="dark"] .card-icon.tag-data {{ color: #38bdf8; }}
    :root[data-theme="dark"] .card-icon.tag-api {{ color: #38bdf8; }}
    :root[data-theme="dark"] .card-icon.tag-misc {{ color: #f472b6; }}

    .card-title {{
      font-size: 1.15rem;
      font-weight: 700;
      color: var(--text);
      letter-spacing: -0.02em;
    }}

    .card-desc {{
      font-size: 0.88rem;
      color: var(--text-muted);
      margin-bottom: 1.5rem;
      line-height: 1.6;
      flex-grow: 1;
      font-weight: 300;
    }}

    .card-meta {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: auto;
      border-top: 1px solid var(--table-border);
      padding-top: 1rem;
    }}

    /* Table View Layout */
    .table-container {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      overflow-x: auto;
      box-shadow: var(--shadow);
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.9rem;
    }}

    th {{
      background-color: var(--th-bg);
      padding: 0.9rem 1.25rem;
      font-weight: 600;
      color: var(--text);
      border-bottom: 1px solid var(--table-border);
      user-select: none;
      vertical-align: middle;
    }}

    th.sortable {{
      cursor: pointer;
    }}

    th.sortable:hover {{
      color: var(--accent);
    }}

    td {{
      padding: 0.9rem 1.25rem;
      border-bottom: 1px solid var(--table-border);
      color: var(--text);
      line-height: 1.5;
    }}

    tr:last-child td {{
      border-bottom: none;
    }}

    tr {{
      transition: background-color 0.15s ease;
    }}

    tr:hover td {{
      background-color: var(--tr-hover);
    }}

    .table-title {{
      font-weight: 700;
      color: var(--text);
      font-size: 0.95rem;
    }}

    .table-desc {{
      color: var(--text-muted);
      font-size: 0.85rem;
      max-width: 400px;
      font-weight: 300;
    }}

    .sort-indicator {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--accent);
      width: 12px;
      height: 12px;
      transition: transform 0.2s ease;
    }}

    .th-content {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      vertical-align: middle;
    }}

    /* Tags and links */
    .tag {{
      font-size: 0.65rem;
      font-weight: 600;
      text-transform: uppercase;
      padding: 0.2rem 0.55rem;
      border-radius: 20px;
      letter-spacing: 0.05em;
      display: inline-block;
    }}

    .tag-web {{ background: rgba(16, 185, 129, 0.1); color: #10b981; }}
    .tag-mobile {{ background: rgba(124, 58, 237, 0.1); color: #7c3aed; }}
    .tag-ai {{ background: rgba(249, 115, 22, 0.1); color: #f97316; }}
    .tag-api {{ background: rgba(14, 165, 233, 0.1); color: #0ea5e9; }}
    .tag-data {{ background: rgba(59, 130, 246, 0.1); color: #3b82f6; }}
    .tag-misc {{ background: rgba(236, 72, 153, 0.1); color: #ec4899; }}

    .links {{
      display: flex;
      gap: 0.85rem;
      align-items: center;
    }}

    .link {{
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.875rem;
      font-weight: 500;
      transition: color 0.15s ease;
    }}

    .link:hover {{
      color: var(--accent);
    }}

    .link-visit {{
      background: var(--accent);
      color: #ffffff !important;
      padding: 0.35rem 0.85rem;
      border-radius: 20px;
      font-size: 0.8rem;
    }}

    .link-visit:hover {{
      background: var(--accent-hover);
    }}

    /* Bottom Green Banner */
    .footer-cta-section {{
      margin-top: 6rem;
      margin-bottom: 2rem;
    }}

    .footer-cta-card {{
      background: #f0fdf4;
      border: 1px solid rgba(16, 185, 129, 0.15);
      border-radius: 20px;
      padding: 2.5rem 3rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 2rem;
      box-shadow: var(--shadow);
    }}

    :root[data-theme="dark"] .footer-cta-card {{
      background: rgba(16, 185, 129, 0.04);
      border-color: rgba(16, 185, 129, 0.2);
    }}

    .footer-cta-left h3 {{
      font-size: 1.8rem;
      font-weight: 800;
      color: #0f172a;
      letter-spacing: -0.03em;
      margin-bottom: 0.25rem;
    }}

    :root[data-theme="dark"] .footer-cta-left h3 {{
      color: #ffffff;
    }}

    .footer-cta-left h3 span {{
      color: #10b981;
    }}

    .footer-cta-left p {{
      color: #374151;
      font-size: 0.95rem;
      font-weight: 350;
    }}

    :root[data-theme="dark"] .footer-cta-left p {{
      color: #9ca3af;
    }}

    @media (max-width: 640px) {{
      .footer-cta-card {{
        flex-direction: column;
        text-align: center;
        padding: 2rem 1.5rem;
      }}
    }}

    footer.main-footer {{
      margin-top: 4rem;
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-muted);
      border-top: 1px solid var(--card-border);
      padding: 2rem 0;
      opacity: 0.7;
    }}

    .empty-state {{
      text-align: center;
      padding: 4rem 2rem;
      color: var(--text-muted);
      font-size: 1rem;
      grid-column: 1 / -1;
      width: 100%;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
    }}

    .hidden {{
      display: none !important;
    }}
    
    .icon {{
      vertical-align: middle;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header class="main-header">
      <div class="logo"><ion-icon name="globe-outline" style="font-size: 1.25rem; margin-right: 6px; color: var(--accent); vertical-align: middle;"></ion-icon>srikanth<span>nandiraju</span></div>
      <button id="themeToggleBtn" onclick="toggleTheme()" class="theme-toggle-btn" title="Toggle Theme" style="display: flex; align-items: center; justify-content: center;">
        <ion-icon id="moonIcon" name="moon-outline" style="font-size: 1.25rem;"></ion-icon>
        <ion-icon id="sunIcon" name="sunny-outline" class="hidden" style="font-size: 1.25rem;"></ion-icon>
      </button>
    </header>

    <!-- Hero Section -->
    <section class="hero-section">
      <div class="hero-left">
        <span class="hero-badge">Workspace Directory</span>
        <h2 class="hero-title">Build a Space That <br><span>Scales Without You.</span></h2>
        <p class="hero-text">
          Explore 32 active portfolios, web applications, and data visualization platforms developed by Srikanth Nandiraju. Hosted live on GitHub Pages with clean, open-source codebases.
        </p>
        <div class="hero-ctas">
          <a href="#catalog" class="cta-btn cta-primary">Explore All Sites</a>
          <a href="https://github.com/nandiraju" target="_blank" rel="noopener noreferrer" class="cta-btn cta-secondary" style="display: inline-flex; align-items: center;">
            GitHub Profile
            <ion-icon name="arrow-forward-outline" style="font-size: 1rem; margin-left: 6px;"></ion-icon>
          </a>
        </div>
        <div class="hero-social-proof">
          <div class="avatar-stack">
            <span class="avatar" style="background-color: #f0fdf4; color: #16a34a;">WB</span>
            <span class="avatar" style="background-color: #f5f3ff; color: #7c3aed;">MB</span>
            <span class="avatar" style="background-color: #fff7ed; color: #ea580c;">AI</span>
            <span class="avatar" style="background-color: #f0f9ff; color: #0284c7;">DT</span>
          </div>
          <span class="social-proof-text">Serving 32 live projects across 7 categories</span>
        </div>
      </div>
      <div class="hero-right">
        <!-- Dashboard Mockup Graphic -->
        <div class="dashboard-mockup">
          <div class="mockup-header">
            <span class="mockup-dot red"></span>
            <span class="mockup-dot yellow"></span>
            <span class="mockup-dot green"></span>
            <span class="mockup-title">nandiraju.github.io/wiki</span>
          </div>
          <div class="mockup-content">
            <div class="mockup-sidebar">
              <div class="sidebar-item active"></div>
              <div class="sidebar-item"></div>
              <div class="sidebar-item"></div>
              <div class="sidebar-item"></div>
            </div>
            <div class="mockup-main">
              <div class="mockup-card stat-card wide">
                <span class="stat-label">Active Workspace Sites</span>
                <div class="stat-value-row">
                  <span class="stat-value">32</span>
                  <span class="growth-badge">+100%</span>
                </div>
                <div class="mini-bar-chart">
                  <span class="bar" style="height: 30%;"></span>
                  <span class="bar" style="height: 45%;"></span>
                  <span class="bar" style="height: 35%;"></span>
                  <span class="bar" style="height: 60%;"></span>
                  <span class="bar" style="height: 50%;"></span>
                  <span class="bar" style="height: 80%;"></span>
                  <span class="bar" style="height: 95%;"></span>
                </div>
              </div>
              <div class="mockup-grid">
                <div class="mockup-card">
                  <span class="stat-label">Primary Stack</span>
                  <span class="stat-value-sub">Web (60%)</span>
                </div>
                <div class="mockup-card">
                  <span class="stat-label">Status</span>
                  <span class="status-indicator">Active</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Categories Section -->
    <section class="categories-section">
      <h3 class="section-title">Everything You Need to Build a Profitable, <br><span>Automated Business</span></h3>
      <div class="categories-grid">
        <!-- Web Apps -->
        <div class="category-item">
          <div class="category-icon-wrapper web" style="display: flex; align-items: center; justify-content: center;">
            <ion-icon name="globe-outline" style="font-size: 1.25rem;"></ion-icon>
          </div>
          <h4>Web Apps</h4>
          <p>Clean SPA systems built with Vite, React, and Next.js.</p>
        </div>
        <!-- Mobile -->
        <div class="category-item">
          <div class="category-icon-wrapper mobile" style="display: flex; align-items: center; justify-content: center;">
            <ion-icon name="phone-portrait-outline" style="font-size: 1.25rem;"></ion-icon>
          </div>
          <h4>Mobile Clients</h4>
          <p>Cross-platform apps built using Expo and Firebase.</p>
        </div>
        <!-- AI -->
        <div class="category-item">
          <div class="category-icon-wrapper ai" style="display: flex; align-items: center; justify-content: center;">
            <ion-icon name="hardware-chip-outline" style="font-size: 1.25rem;"></ion-icon>
          </div>
          <h4>AI Solutions</h4>
          <p>Gemini Live real-time audio systems and RAG pipelines.</p>
        </div>
        <!-- Data -->
        <div class="category-item">
          <div class="category-icon-wrapper data" style="display: flex; align-items: center; justify-content: center;">
            <ion-icon name="bar-chart-outline" style="font-size: 1.25rem;"></ion-icon>
          </div>
          <h4>Data Visualizations</h4>
          <p>Interactive D3 force graphs, timelines, and Gauges.</p>
        </div>
        <!-- Misc -->
        <div class="category-item">
          <div class="category-icon-wrapper misc" style="display: flex; align-items: center; justify-content: center;">
            <ion-icon name="cube-outline" style="font-size: 1.25rem;"></ion-icon>
          </div>
          <h4>Utility Decks</h4>
          <p>Draw.io system diagrams and Marp presentation slides.</p>
        </div>
      </div>
    </section>

    <!-- Secondary Hero Section -->
    <section class="sec-hero-section">
      <div class="sec-hero-card">
        <div class="sec-hero-left">
          <span class="badge-accent">Workspace Engineering</span>
          <h3>Built by an Engineer <br><span>Who Gets It.</span></h3>
          <p>
            This directory compiles functional static platforms rather than templates. From oncology portals to interactive dashboards, all components are production-ready, responsive, and open-source.
          </p>
          <a href="https://github.com/nandiraju" target="_blank" rel="noopener noreferrer" class="cta-btn cta-primary inline-cta">Explore the Repositories</a>
        </div>
        <div class="sec-hero-center">
          <div class="mock-device">
            <div class="mock-device-header">
              <span class="dot"></span><span class="dot"></span><span class="dot"></span>
            </div>
            <div class="mock-device-screen">
              <div class="osakhi-logo">OSakhi</div>
              <div class="screen-stat-row">
                <div class="screen-stat"></div>
                <div class="screen-stat"></div>
              </div>
              <div class="screen-chart-placeholder"></div>
            </div>
          </div>
        </div>
        <div class="sec-hero-right">
          <div class="stat-badge-item violet">
            <div class="stat-badge-top">
              <span class="badge-num">32+</span>
              <span class="badge-icon" style="display: flex; align-items: center; justify-content: center;"><ion-icon name="globe-outline" style="font-size: 1.5rem;"></ion-icon></span>
            </div>
            <p class="badge-label">Active Sites Live</p>
          </div>
          <div class="stat-badge-item peach">
            <div class="stat-badge-top">
              <span class="badge-num">60+</span>
              <span class="badge-icon" style="display: flex; align-items: center; justify-content: center;"><ion-icon name="folder-open-outline" style="font-size: 1.5rem;"></ion-icon></span>
            </div>
            <p class="badge-label">Local Git Repos</p>
          </div>
          <div class="stat-badge-item green">
            <div class="stat-badge-top">
              <span class="badge-num">100%</span>
              <span class="badge-icon" style="display: flex; align-items: center; justify-content: center;"><ion-icon name="flash-outline" style="font-size: 1.5rem;"></ion-icon></span>
            </div>
            <p class="badge-label">Fast & Responsive</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Catalog Listing -->
    <section id="catalog" class="catalog-section" style="padding-top: 2rem;">
      <div class="catalog-header" style="text-align: center; margin-bottom: 3.5rem;">
        <h3 class="section-title">Explore the <span>Workspace Directory</span></h3>
        <p style="color: var(--text-muted); font-size: 0.95rem; font-weight: 300; max-width: 600px; margin: -2.5rem auto 0;">
          Explore and filter all 32 active sites by category. View repository code or visit the live pages instantly.
        </p>
      </div>

      <div class="controls-row">
        <div class="search-box">
          <input type="text" id="searchInput" class="search-input" placeholder="Search projects or descriptions..." oninput="handleSearch(this.value)">
        </div>
        
        <div class="action-buttons">
          <div class="btn-group">
            <button id="viewCardBtn" onclick="changeView('card')" class="control-btn" title="Grid View" style="display: inline-flex; align-items: center; gap: 4px;">
              <ion-icon name="grid-outline" style="font-size: 1rem;"></ion-icon>
              Cards
            </button>
            <button id="viewTableBtn" onclick="changeView('table')" class="control-btn" title="Table View" style="display: inline-flex; align-items: center; gap: 4px;">
              <ion-icon name="list-outline" style="font-size: 1rem;"></ion-icon>
              Table
            </button>
          </div>
        </div>
      </div>

      <!-- Categories Filter Pills -->
      <div class="category-filters-wrapper">
        <div class="category-filters" id="categoryFilters"></div>
      </div>

      <div class="stats" id="statsCounter">Loading sites...</div>

      <!-- Cards Container -->
      <div id="cardsGrid" class="grid"></div>

      <!-- Table Container -->
      <div id="tableWrapper" class="table-container hidden">
        <table>
          <thead>
            <tr>
              <th class="sortable" onclick="handleSort('title')">
                <span class="th-content">Project Name <span id="sortIndicatorTitle" class="sort-indicator"></span></span>
              </th>
              <th class="sortable" onclick="handleSort('tag')">
                <span class="th-content">Category <span id="sortIndicatorTag" class="sort-indicator"></span></span>
              </th>
              <th><span class="th-content">Description</span></th>
              <th><span class="th-content">Links</span></th>
            </tr>
          </thead>
          <tbody id="tableBody"></tbody>
        </table>
      </div>

      <div id="emptyState" class="empty-state hidden">
        No active sites found matching your search.
      </div>
    </section>

    <!-- Bottom Green Banner -->
    <section class="footer-cta-section">
      <div class="footer-cta-card">
        <div class="footer-cta-left">
          <h3>Your Dev Wiki Starts <span>Now.</span></h3>
          <p>Explore 32 fully active deployed codebases and interfaces.</p>
        </div>
        <div class="footer-cta-right">
          <a href="https://github.com/nandiraju" target="_blank" rel="noopener noreferrer" class="cta-btn cta-primary">View GitHub Profile</a>
        </div>
      </div>
    </section>

    <footer class="main-footer">
      Built with love by <a href="https://srikanth.nandiraju.com" target="_blank" rel="noopener noreferrer" style="color: var(--accent); text-decoration: none; font-weight: 600;">Srikanth</a> <ion-icon name="heart" style="color: #ef4444; vertical-align: middle; font-size: 0.95rem;"></ion-icon>
    </footer>
  </div>

  <script>
    const projects = {js_projects};

    // Application state
    let searchFilter = "";
    let currentView = localStorage.getItem("wiki-view-v2") || "card";
    let currentTheme = localStorage.getItem("wiki-theme-v2") || "light";
    let currentTagFilter = "all";
    let sortBy = "title";
    let sortOrder = "asc";

    const TAGS = ["all", "web", "mobile", "ai", "api", "data", "misc"];

    // Initialize layout, filters, & theme
    document.documentElement.setAttribute('data-theme', currentTheme);
    updateThemeIcons();
    buildTagFilters();

    // Initial draw
    updateUI();

    // Run premium animations
    runIntroAnimations();
    setupScrollAnimations();

    function runIntroAnimations() {{
      const tl = gsap.timeline({{ defaults: {{ ease: "power3.out" }} }});
      
      tl.from(".main-header", {{ y: -30, opacity: 0, duration: 0.8 }});
      tl.from(".hero-badge", {{ y: 20, opacity: 0, duration: 0.5 }}, "-=0.4");
      tl.from(".hero-title", {{ y: 30, opacity: 0, duration: 0.7 }}, "-=0.4");
      tl.from(".hero-text", {{ y: 20, opacity: 0, duration: 0.7 }}, "-=0.5");
      tl.from(".hero-ctas", {{ y: 15, opacity: 0, duration: 0.7 }}, "-=0.5");
      tl.from(".hero-social-proof", {{ y: 12, opacity: 0, duration: 0.7 }}, "-=0.5");
      
      tl.from(".dashboard-mockup", {{ 
        scale: 0.96, 
        opacity: 0, 
        y: 25,
        duration: 1, 
        ease: "back.out(1.1)" 
      }}, "-=0.8");
      
      tl.from(".mini-bar-chart .bar", {{
        scaleY: 0,
        transformOrigin: "bottom",
        duration: 0.7,
        stagger: 0.06
      }}, "-=0.6");
      
      tl.from(".category-item", {{
        y: 30,
        opacity: 0,
        duration: 0.6,
        stagger: 0.08
      }}, "-=0.5");
    }}

    function setupScrollAnimations() {{
      const observer = new IntersectionObserver((entries) => {{
        entries.forEach(entry => {{
          if (entry.isIntersecting) {{
            if (entry.target.classList.contains("sec-hero-card")) {{
              gsap.fromTo(entry.target.querySelectorAll(".sec-hero-left > *"), 
                {{ y: 35, opacity: 0 }}, 
                {{ y: 0, opacity: 1, duration: 0.8, stagger: 0.08, ease: "power2.out" }}
              );
              gsap.fromTo(entry.target.querySelector(".sec-hero-center"), 
                {{ scale: 0.94, opacity: 0 }}, 
                {{ scale: 1, opacity: 1, duration: 0.9, ease: "back.out(1.15)" }}
              );
              gsap.fromTo(entry.target.querySelectorAll(".sec-hero-right .stat-badge-item"), 
                {{ x: 30, opacity: 0 }}, 
                {{ x: 0, opacity: 1, duration: 0.8, stagger: 0.08, ease: "power2.out" }}
              );
            }} else if (entry.target.classList.contains("footer-cta-card")) {{
              gsap.fromTo(entry.target, 
                {{ scale: 0.96, opacity: 0, y: 20 }}, 
                {{ scale: 1, opacity: 1, y: 0, duration: 0.8, ease: "power3.out" }}
              );
            }}
            observer.unobserve(entry.target);
          }}
        }});
      }}, {{ threshold: 0.12 }});

      document.querySelectorAll(".sec-hero-card, .footer-cta-card").forEach(el => observer.observe(el));
    }}

    function toggleTheme() {{
      currentTheme = currentTheme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute('data-theme', currentTheme);
      localStorage.setItem("wiki-theme-v2", currentTheme);
      updateThemeIcons();
    }}

    function updateThemeIcons() {{
      const moon = document.getElementById("moonIcon");
      const sun = document.getElementById("sunIcon");
      if (currentTheme === "dark") {{
        moon.classList.remove("hidden");
        sun.classList.add("hidden");
      }} else {{
        moon.classList.add("hidden");
        sun.classList.remove("hidden");
      }}
    }}

    function changeView(view) {{
      currentView = view;
      localStorage.setItem("wiki-view-v2", view);
      updateUI();
    }}

    function handleSearch(val) {{
      searchFilter = val.toLowerCase().trim();
      updateUI();
    }}

    function handleSort(column) {{
      if (sortBy === column) {{
        sortOrder = sortOrder === "asc" ? "desc" : "asc";
      }} else {{
        sortBy = column;
        sortOrder = "asc";
      }}
      updateUI();
    }}

    function getTagClass(tag) {{
      return `tag-${{tag.toLowerCase()}}`;
    }}

    function buildTagFilters() {{
      const tf = document.getElementById("categoryFilters");
      tf.innerHTML = "";
      TAGS.forEach(t => {{
        const btn = document.createElement("button");
        btn.className = "filter-pill" + (t === "all" ? " active" : "");
        btn.textContent = t === "all" ? "All Projects" : t.toUpperCase();
        btn.dataset.tag = t;
        btn.onclick = () => {{
          currentTagFilter = t;
          document.querySelectorAll(".filter-pill").forEach(b => b.classList.toggle("active", b.dataset.tag === t));
          updateUI();
        }};
        tf.appendChild(btn);
      }});
    }}

    function updateUI() {{
      // Update view toggle button classes
      document.getElementById("viewCardBtn").classList.toggle("active", currentView === "card");
      document.getElementById("viewTableBtn").classList.toggle("active", currentView === "table");

      // Filter by search AND tag filter pill
      let filtered = projects.filter(p => {{
        const matchesSearch = p.title.toLowerCase().includes(searchFilter) || 
                              p.desc.toLowerCase().includes(searchFilter) || 
                              p.tag.toLowerCase().includes(searchFilter);
        const matchesTag = currentTagFilter === "all" || p.tag.toLowerCase() === currentTagFilter;
        return matchesSearch && matchesTag;
      }});

      // Sort
      filtered.sort((a, b) => {{
        let valA = a[sortBy].toLowerCase();
        let valB = b[sortBy].toLowerCase();
        if (valA < valB) return sortOrder === "asc" ? -1 : 1;
        if (valA > valB) return sortOrder === "asc" ? 1 : -1;
        return 0;
      }});

      // Show/Hide Empty State
      const emptyState = document.getElementById("emptyState");
      if (filtered.length === 0) {{
        emptyState.classList.remove("hidden");
        document.getElementById("cardsGrid").classList.add("hidden");
        document.getElementById("tableWrapper").classList.add("hidden");
      }} else {{
        emptyState.classList.add("hidden");
        if (currentView === "card") {{
          document.getElementById("cardsGrid").classList.remove("hidden");
          document.getElementById("tableWrapper").classList.add("hidden");
          renderCards(filtered);
          gsap.fromTo("#cardsGrid .card", 
            {{ y: 15, opacity: 0 }}, 
            {{ y: 0, opacity: 1, duration: 0.4, stagger: 0.03, ease: "power2.out", overwrite: "auto" }}
          );
        }} else {{
          document.getElementById("cardsGrid").classList.add("hidden");
          document.getElementById("tableWrapper").classList.remove("hidden");
          renderTable(filtered);
          gsap.fromTo("#tableBody tr", 
            {{ y: 10, opacity: 0 }}, 
            {{ y: 0, opacity: 1, duration: 0.4, stagger: 0.02, ease: "power2.out", overwrite: "auto" }}
          );
        }}
      }}

      // Update counters
      document.getElementById("statsCounter").textContent = 
        `Showing ${{filtered.length}} of ${{projects.length}} site${{projects.length !== 1 ? 's' : ''}}`;

      // Update sort indicators
      updateSortIndicators();
    }}

    const arrowAsc = `<ion-icon name="chevron-up-outline" style="font-size: 0.75rem; vertical-align: middle;"></ion-icon>`;
    const arrowDesc = `<ion-icon name="chevron-down-outline" style="font-size: 0.75rem; vertical-align: middle;"></ion-icon>`;

    function updateSortIndicators() {{
      const titleInd = document.getElementById("sortIndicatorTitle");
      const tagInd = document.getElementById("sortIndicatorTag");
      
      titleInd.innerHTML = "";
      tagInd.innerHTML = "";
      
      const arrowHtml = sortOrder === "asc" ? arrowAsc : arrowDesc;
      if (sortBy === "title") {{
        titleInd.innerHTML = arrowHtml;
      }} else if (sortBy === "tag") {{
        tagInd.innerHTML = arrowHtml;
      }}
    }}

    function getTagIcon(tag) {{
      tag = tag.toLowerCase();
      if (tag === 'web') {{
        return `<ion-icon name="globe-outline" style="font-size: 1.05rem;"></ion-icon>`;
      }} else if (tag === 'mobile') {{
        return `<ion-icon name="phone-portrait-outline" style="font-size: 1.05rem;"></ion-icon>`;
      }} else if (tag === 'ai') {{
        return `<ion-icon name="hardware-chip-outline" style="font-size: 1.05rem;"></ion-icon>`;
      }} else if (tag === 'data') {{
        return `<ion-icon name="bar-chart-outline" style="font-size: 1.05rem;"></ion-icon>`;
      }} else if (tag === 'api') {{
        return `<ion-icon name="code-working-outline" style="font-size: 1.05rem;"></ion-icon>`;
      }} else {{
        return `<ion-icon name="cube-outline" style="font-size: 1.05rem;"></ion-icon>`;
      }}
    }}

    function renderCards(data) {{
      const grid = document.getElementById("cardsGrid");
      grid.innerHTML = "";
      data.forEach(p => {{
        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `
          <div>
            <div class="card-title-row">
              <div class="card-icon ${{getTagClass(p.tag)}}">
                ${{getTagIcon(p.tag)}}
              </div>
              <div class="card-title">${{p.title}}</div>
            </div>
            <div class="card-desc">${{p.desc}}</div>
          </div>
          <div class="card-meta">
            <span class="tag ${{getTagClass(p.tag)}}">${{p.tag.toUpperCase()}}</span>
            <div class="links">
              <a href="${{p.github_url}}" class="link" target="_blank" rel="noopener noreferrer">Code</a>
              <a href="${{p.pages_url}}" class="link link-visit" target="_blank" rel="noopener noreferrer">Visit</a>
            </div>
          </div>
        `;
        grid.appendChild(card);
      }});
    }}

    function renderTable(data) {{
      const tbody = document.getElementById("tableBody");
      tbody.innerHTML = "";
      data.forEach(p => {{
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="table-title">${{p.title}}</td>
          <td><span class="tag ${{getTagClass(p.tag)}}">${{p.tag.toUpperCase()}}</span></td>
          <td class="table-desc">${{p.desc}}</td>
          <td>
            <div class="links">
              <a href="${{p.github_url}}" class="link" target="_blank" rel="noopener noreferrer">Code</a>
              <a href="${{p.pages_url}}" class="link link-visit" target="_blank" rel="noopener noreferrer">Visit</a>
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      }});
    }}
  </script>
</body>
</html>
"""
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    print(f"Wiki generated successfully at {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
