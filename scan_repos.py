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
    # Handle ssh and https URLs
    m = re.search(r'github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?$', url)
    if m:
        return m.group(1), m.group(2)
    return None, None

def get_cname(repo_path):
    # Check root
    cname_path = os.path.join(repo_path, 'CNAME')
    if os.path.exists(cname_path):
        try:
            with open(cname_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            pass
    # Check docs/CNAME
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
            # Match { name: "Alexa_Songs_Skill",       tag: "ai",     desc: "Alexa..." }
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
        
    # Check CNAME
    cname = get_cname(repo_path)
    
    # Probe pages status
    is_active, final_url = probe_pages_site(owner, repo, cname)
    if not is_active:
        return None
        
    desc = None
    tag = "misc"
    
    # 1. Try parent index
    if dir_name in parent_info:
        desc = parent_info[dir_name].get("desc")
        tag = parent_info[dir_name].get("tag", "misc")
    
    # 2. Try index.html metadata
    html_title, html_desc = get_html_metadata(repo_path)
    if not desc and html_desc:
        desc = html_desc
        
    # 3. Try README
    if not desc:
        desc = get_readme_description(repo_path)
        
    # 4. Fallback
    if not desc:
        desc = f"Static site for {dir_name} on GitHub Pages."
        
    title = html_title or dir_name.replace('_', ' ').replace('-', ' ').title()
    
    # Clean up descriptions for json format safety
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
    
    # Construct JavaScript array
    js_projects = "[\n"
    for item in active_pages:
        js_projects += f"      {{ title: \"{item['title']}\", tag: \"{item['tag']}\", desc: \"{item['desc']}\", github_url: \"{item['github_url']}\", pages_url: \"{item['pages_url']}\" }},\n"
    js_projects += "    ]"

    # HTML page supporting both views and light/dark theme switcher
    html_content = f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Srikanth Nandiraju | GitHub Pages Wiki</title>
  
  <!-- SEO Meta Tags -->
  <meta name="title" content="Srikanth Nandiraju | GitHub Pages Wiki">
  <meta name="description" content="Curated directory of active GitHub Pages websites, portfolios, and projects by Srikanth Nandiraju (nandiraju). Explore live web apps, AI tools, and research pages.">
  <meta name="keywords" content="Srikanth Nandiraju, Nandiraju, GitHub Pages, Wiki, Web Developer, Portfolio, Projects, AI, React, Expo">
  <meta name="author" content="Srikanth Nandiraju">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="https://srikanth.nandiraju.com/wiki/">

  <!-- Open Graph / Facebook -->
  <meta property="og:type" content="profile">
  <meta property="og:url" content="https://srikanth.nandiraju.com/wiki/">
  <meta property="og:title" content="Srikanth Nandiraju | GitHub Pages Wiki">
  <meta property="og:description" content="Explore active GitHub Pages websites, portfolios, and projects by Srikanth Nandiraju.">
  <meta property="og:image" content="https://avatars.githubusercontent.com/u/589121?v=4">
  <meta property="profile:first_name" content="Srikanth">
  <meta property="profile:last_name" content="Nandiraju">
  <meta property="profile:username" content="nandiraju">

  <!-- Twitter -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:url" content="https://srikanth.nandiraju.com/wiki/">
  <meta name="twitter:title" content="Srikanth Nandiraju | GitHub Pages Wiki">
  <meta name="twitter:description" content="Explore active GitHub Pages websites, portfolios, and projects by Srikanth Nandiraju.">
  <meta name="twitter:image" content="https://avatars.githubusercontent.com/u/589121?v=4">

  <!-- Performance Optimizations -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="dns-prefetch" href="https://fonts.googleapis.com">
  <link rel="dns-prefetch" href="https://fonts.gstatic.com">
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --transition-speed: 0.2s;
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

    :root[data-theme="light"] {{
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --card-border: rgba(0, 0, 0, 0.08);
      --card-hover-border: rgba(79, 70, 229, 0.4);
      --text: #0f172a;
      --text-muted: #64748b;
      --accent: #4f46e5;
      --accent-hover: #3730a3;
      --accent-glow: rgba(79, 70, 229, 0.1);
      --th-bg: #f1f5f9;
      --table-border: rgba(0, 0, 0, 0.06);
      --tr-hover: rgba(0, 0, 0, 0.01);
      --btn-bg: #e2e8f0;
      --btn-active-bg: #4f46e5;
      --btn-active-text: #ffffff;
      --input-border: rgba(0, 0, 0, 0.15);
      --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
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
      padding: 3rem 1.5rem;
      min-height: 100vh;
      transition: background-color var(--transition-speed) ease, color var(--transition-speed) ease;
      -webkit-font-smoothing: antialiased;
    }}

    .container {{
      max-width: 1050px;
      margin: 0 auto;
    }}

    header {{
      margin-bottom: 2.5rem;
      text-align: center;
      position: relative;
    }}

    h1 {{
      font-size: 2.25rem;
      font-weight: 700;
      letter-spacing: -0.03em;
      margin-bottom: 0.5rem;
      background: linear-gradient(135deg, var(--text) 30%, var(--accent) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    header p {{
      color: var(--text-muted);
      font-size: 1rem;
      font-weight: 300;
    }}

    .controls-row {{
      display: flex;
      gap: 1rem;
      margin-bottom: 2rem;
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
      background: rgba(255, 255, 255, 0.05);
    }}

    .theme-toggle-btn {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 0.5rem;
      border-radius: 10px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 2.4rem;
      height: 2.4rem;
      box-shadow: var(--shadow);
      transition: all 0.2s ease;
    }}

    .theme-toggle-btn:hover {{
      border-color: var(--accent);
      transform: scale(1.05);
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
      border-radius: 14px;
      padding: 1.5rem;
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
      transform: translateY(-3px);
      border-color: var(--card-hover-border);
      box-shadow: 0 10px 20px -10px var(--accent-glow);
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

    .card-title {{
      font-size: 1.125rem;
      font-weight: 600;
      color: var(--text);
      margin-bottom: 0.5rem;
      letter-spacing: -0.01em;
    }}

    .card-desc {{
      font-size: 0.875rem;
      color: var(--text-muted);
      margin-bottom: 1.5rem;
      line-height: 1.6;
      flex-grow: 1;
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
      font-weight: 600;
      color: var(--text);
    }}

    .table-desc {{
      color: var(--text-muted);
      font-size: 0.85rem;
      max-width: 400px;
    }}

    .sort-indicator {{
      display: inline-block;
      margin-left: 0.25rem;
      font-size: 0.75rem;
      vertical-align: middle;
      transition: transform 0.2s ease;
    }}

    /* General tags and links */
    .tag {{
      font-size: 0.65rem;
      font-weight: 600;
      text-transform: uppercase;
      padding: 0.2rem 0.55rem;
      border-radius: 20px;
      letter-spacing: 0.05em;
      display: inline-block;
    }}

    .tag-web {{ background: rgba(99, 102, 241, 0.12); color: #818cf8; }}
    .tag-mobile {{ background: rgba(34, 197, 94, 0.1); color: #4ade80; }}
    .tag-ai {{ background: rgba(251, 146, 60, 0.1); color: #fb923c; }}
    .tag-api {{ background: rgba(56, 189, 248, 0.1); color: #38bdf8; }}
    .tag-data {{ background: rgba(167, 139, 250, 0.1); color: #a78bfa; }}
    .tag-misc {{ background: rgba(100, 116, 139, 0.1); color: #94a3b8; }}

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
      padding: 0.3rem 0.75rem;
      border-radius: 8px;
      font-size: 0.8rem;
    }}

    .link-visit:hover {{
      background: var(--accent-hover);
    }}

    footer {{
      margin-top: 4rem;
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-muted);
      border-top: 1px solid var(--card-border);
      padding-top: 2rem;
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
    <header>
      <h1>🌐 Git Sites Wiki</h1>
      <p>A directory of active GitHub Pages sites in the workspace</p>
    </header>

    <div class="controls-row">
      <div class="search-box">
        <input type="text" id="searchInput" class="search-input" placeholder="Search projects or descriptions..." oninput="handleSearch(this.value)">
      </div>
      
      <div class="action-buttons">
        <div class="btn-group">
          <button id="viewCardBtn" onclick="changeView('card')" class="control-btn" title="Grid View">
            <svg class="icon" viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
            Cards
          </button>
          <button id="viewTableBtn" onclick="changeView('table')" class="control-btn" title="Table View">
            <svg class="icon" viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
            Table
          </button>
        </div>

        <button id="themeToggleBtn" onclick="toggleTheme()" class="theme-toggle-btn" title="Toggle Theme">
          <!-- Moon Icon (Dark Mode active, clicking turns Light) -->
          <svg id="moonIcon" class="icon" viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
          <!-- Sun Icon (Light Mode active, clicking turns Dark) -->
          <svg id="sunIcon" class="icon hidden" viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
        </button>
      </div>
    </div>

    <div class="stats" id="statsCounter">Loading sites...</div>

    <!-- Cards Container -->
    <div id="cardsGrid" class="grid"></div>

    <!-- Table Container -->
    <div id="tableWrapper" class="table-container hidden">
      <table>
        <thead>
          <tr>
            <th class="sortable" onclick="handleSort('title')">Project Name <span id="sortIndicatorTitle" class="sort-indicator"></span></th>
            <th class="sortable" onclick="handleSort('tag')">Category <span id="sortIndicatorTag" class="sort-indicator"></span></th>
            <th>Description</th>
            <th>Links</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>

    <div id="emptyState" class="empty-state hidden">
      No active sites found matching your search.
    </div>

    <footer>
      Generated automatically by AntiGravity on <span id="genDate"></span>
    </footer>
  </div>

  <script>
    const projects = {js_projects};

    // Application state
    let searchFilter = "";
    let currentView = localStorage.getItem("wiki-view") || "card";
    let currentTheme = localStorage.getItem("wiki-theme") || "light";
    let sortBy = "title";
    let sortOrder = "asc";

    // Set initial date
    document.getElementById('genDate').textContent = new Date().toLocaleDateString('en-US', {{
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }});

    // Initialize layout & theme
    document.documentElement.setAttribute('data-theme', currentTheme);
    updateThemeIcons();

    // Initial draw
    updateUI();

    function toggleTheme() {{
      currentTheme = currentTheme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute('data-theme', currentTheme);
      localStorage.setItem("wiki-theme", currentTheme);
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
      localStorage.setItem("wiki-view", view);
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

    function updateUI() {{
      // Update view toggle button classes
      document.getElementById("viewCardBtn").classList.toggle("active", currentView === "card");
      document.getElementById("viewTableBtn").classList.toggle("active", currentView === "table");

      // Filter
      let filtered = projects.filter(p => 
        p.title.toLowerCase().includes(searchFilter) || 
        p.desc.toLowerCase().includes(searchFilter) || 
        p.tag.toLowerCase().includes(searchFilter)
      );

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
        }} else {{
          document.getElementById("cardsGrid").classList.add("hidden");
          document.getElementById("tableWrapper").classList.remove("hidden");
          renderTable(filtered);
        }}
      }}

      // Update counters
      document.getElementById("statsCounter").textContent = 
        `Showing ${{filtered.length}} of ${{projects.length}} site${{projects.length !== 1 ? 's' : ''}}`;

      // Update sort indicators
      updateSortIndicators();
    }}

    function updateSortIndicators() {{
      const titleInd = document.getElementById("sortIndicatorTitle");
      const tagInd = document.getElementById("sortIndicatorTag");
      
      titleInd.textContent = "";
      tagInd.textContent = "";
      
      const arrow = sortOrder === "asc" ? " ▴" : " ▾";
      if (sortBy === "title") {{
        titleInd.textContent = arrow;
      }} else if (sortBy === "tag") {{
        tagInd.textContent = arrow;
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
            <div class="card-title">${{p.title}}</div>
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
