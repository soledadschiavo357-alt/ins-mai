import os
import re
import json
import copy
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup, Tag

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, 'index.html')
BLOG_DIR = os.path.join(BASE_DIR, 'blog')
DOMAIN = "https://ins-mai.top"

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def clean_url(url):
    if not url:
        return url
    if url.startswith('http'):
        return url
    # Handle anchor links: if it starts with #, prepend /
    if url.startswith('#'):
        return '/' + url
    # Force root relative for assets if needed, but for links:
    if url.endswith('.html'):
        return url[:-5]
    return url

def clean_nav_footer_links(tag):
    for a in tag.find_all('a'):
        if a.has_attr('href'):
            a['href'] = clean_url(a['href'])
    return tag

def clean_title(title):
    """
    Clean title for Evergreen SEO:
    1. Remove suffix | Ins-mai.top
    2. Remove years (e.g. 2024, 2025, 2026)
    3. Remove leading numbering
    """
    if not title:
        return ""
    
    # Remove suffix | Ins-mai.top (case insensitive)
    title = re.sub(r'\s*\|\s*Ins-mai\.top', '', title, flags=re.IGNORECASE)
    
    # Remove years (2020-2035) to ensure evergreen
    # We don't use \b because in Chinese text, years might be adjacent to characters (e.g. 2026最新)
    title = re.sub(r'20[2-3][0-9]', '', title)
    
    # Remove leading numbering (e.g. "1. ", "01. ")
    title = re.sub(r'^\d+\.\s*', '', title)
    
    return title.strip()

def indent(elem, level=0):
    i = "\n" + level*"    "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "    "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def update_sitemap(posts):
    print("Updating sitemap.xml...")
    sitemap_path = os.path.join(BASE_DIR, 'sitemap.xml')
    if not os.path.exists(sitemap_path):
        print("Sitemap not found, skipping update.")
        return

    try:
        # Register namespace to prevent ns0: prefixes
        ET.register_namespace('', "http://www.sitemaps.org/schemas/sitemap/0.9")
        tree = ET.parse(sitemap_path)
        root = tree.getroot()
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

        updated_count = 0
        
        # Map existing URLs to their elements for easy lookup
        url_map = {}
        for url_elem in root.findall('ns:url', ns):
            loc = url_elem.find('ns:loc', ns)
            if loc is not None and loc.text:
                url_map[loc.text.strip()] = url_elem

        for post in posts:
            full_url = f"{DOMAIN}{post['url']}"
            date_str = post['date']
            
            if full_url in url_map:
                url_elem = url_map[full_url]
                lastmod = url_elem.find('ns:lastmod', ns)
                if lastmod is not None:
                    if lastmod.text != date_str:
                        lastmod.text = date_str
                        updated_count += 1
                else:
                    lastmod = ET.SubElement(url_elem, 'lastmod')
                    lastmod.text = date_str
                    updated_count += 1
            else:
                # Add new URL
                new_url = ET.SubElement(root, 'url')
                loc = ET.SubElement(new_url, 'loc')
                loc.text = full_url
                lastmod = ET.SubElement(new_url, 'lastmod')
                lastmod.text = date_str
                changefreq = ET.SubElement(new_url, 'changefreq')
                changefreq.text = 'weekly'
                priority = ET.SubElement(new_url, 'priority')
                priority.text = '0.8'
                updated_count += 1
                
        # Always indent to ensure clean formatting
        indent(root)
        
        # Always write if we want to fix formatting, even if updated_count is 0
        # But to be safe, we only write if updated or if we suspect formatting issues
        # Let's force write this time to fix the previous mess
        tree.write(sitemap_path, encoding='UTF-8', xml_declaration=True)
        print(f"Updated sitemap.xml with {updated_count} changes (and fixed formatting).")
            
    except Exception as e:
        print(f"Error updating sitemap: {e}")

def get_latest_posts_html(posts, limit=3):
    # Generate HTML for Recommended Reading
    html = ""
    for post in posts[:limit]:
        html += f'''
        <a href="{post['url']}" class="group block glass-card rounded-3xl overflow-hidden hover:bg-white/5 transition-all border-t border-white/10">
            <div class="h-48 bg-gradient-to-br from-gray-800 via-black to-gray-900 flex items-center justify-center relative overflow-hidden">
                <div class="absolute top-0 right-0 w-32 h-32 bg-insPurple/20 blur-3xl rounded-full"></div>
                <i data-lucide="file-text" class="w-12 h-12 text-white/20 group-hover:scale-110 transition-transform duration-500"></i>
            </div>
            <div class="p-6">
                <div class="flex items-center gap-3 mb-3">
                    <span class="px-2 py-1 rounded bg-insPurple/20 text-insPurple text-[10px] font-bold uppercase">Article</span>
                    <span class="text-gray-500 text-xs">{post['date']}</span>
                </div>
                <h3 class="text-lg font-bold text-white mb-2 group-hover:text-insPurple transition-colors line-clamp-2">
                    {post['title']}
                </h3>
                <p class="text-sm text-gray-400 line-clamp-2">
                    {post['description']}
                </p>
            </div>
        </a>
        '''
    return html

def main():
    print("Starting build process...")
    
    # 1. Parse index.html
    print("Phase 1: Smart Extraction from index.html")
    index_content = read_file(INDEX_PATH)
    index_soup = BeautifulSoup(index_content, 'html.parser')
    
    # Extract Nav and Footer
    nav_template = index_soup.find('nav')
    footer_template = index_soup.find('footer')
    
    if nav_template:
        nav_template = clean_nav_footer_links(copy.copy(nav_template))
    if footer_template:
        footer_template = clean_nav_footer_links(copy.copy(footer_template))
        
    # Extract Favicons
    favicons = []
    for link in index_soup.find_all('link'):
        rel = link.get('rel', [])
        if isinstance(rel, list):
            rel = " ".join(rel)
        if 'icon' in rel:
            new_link = copy.copy(link)
            href = new_link.get('href', '')
            if href and not href.startswith('/') and not href.startswith('http'):
                 new_link['href'] = '/' + href
            favicons.append(new_link)
            
    # 2. Scan Blog Posts
    print("Scanning blog posts...")
    posts = []
    if os.path.exists(BLOG_DIR):
        blog_files = [f for f in os.listdir(BLOG_DIR) if f.endswith('.html') and f != 'index.html']
        
        for filename in blog_files:
            path = os.path.join(BLOG_DIR, filename)
            soup = BeautifulSoup(read_file(path), 'html.parser')
            
            raw_title = soup.title.string if soup.title else filename
            # Clean title immediately
            title = clean_title(raw_title)
            
            desc = ""
            desc_meta = soup.find('meta', attrs={'name': 'description'})
            if desc_meta:
                desc = desc_meta.get('content', '')
                
            date_str = "2026-01-01" # Default
            json_ld = soup.find('script', type='application/ld+json')
            if json_ld and json_ld.string:
                try:
                    data = json.loads(json_ld.string)
                    if 'datePublished' in data:
                        date_str = data['datePublished']
                except:
                    pass
                    
            posts.append({
                'title': title,
                'description': desc,
                'date': date_str,
                'url': f'/blog/{filename.replace(".html", "")}',
                'filename': filename,
                'path': path
            })
            
        # Sort posts by date (newest first)
        posts.sort(key=lambda x: x['date'], reverse=True)
    
    # 3. Process Each Blog Post
    print("Phase 2 & 3: Processing blog posts...")
    for post in posts:
        print(f"Processing {post['filename']}...")
        soup = BeautifulSoup(read_file(post['path']), 'html.parser')
        
        # --- Phase 2: Head Reconstruction ---
        original_head = soup.head
        new_head = soup.new_tag('head')
        
        # Group A: Basic Metadata
        new_head.append(soup.new_tag('meta', charset='utf-8'))
        new_head.append(soup.new_tag('meta', attrs={'content': 'width=device-width, initial-scale=1.0', 'name': 'viewport'}))
        
        # Title (Use Cleaned Title)
        title_tag = soup.new_tag('title')
        title_tag.string = post['title']
        new_head.append(title_tag)
        
        # Group B: SEO Core
        if post['description']:
            new_head.append(soup.new_tag('meta', attrs={'content': post['description'], 'name': 'description'}))
        
        keywords = ""
        kw_meta = original_head.find('meta', attrs={'name': 'keywords'})
        if kw_meta:
            keywords = kw_meta.get('content', '')
        if keywords:
            new_head.append(soup.new_tag('meta', attrs={'content': keywords, 'name': 'keywords'}))
            
        new_head.append(soup.new_tag('link', rel='canonical', href=f"{DOMAIN}{post['url']}"))
        
        # Group C: Indexing & Geo
        new_head.append(soup.new_tag('meta', attrs={'content': 'index, follow', 'name': 'robots'}))
        new_head.append(soup.new_tag('meta', attrs={'http-equiv': 'content-language', 'content': 'zh-cn'}))
        
        # Hreflang
        new_head.append(soup.new_tag('link', rel='alternate', hreflang='zh', href=f"{DOMAIN}{post['url']}"))
        new_head.append(soup.new_tag('link', rel='alternate', hreflang='zh-CN', href=f"{DOMAIN}{post['url']}"))
        new_head.append(soup.new_tag('link', rel='alternate', hreflang='x-default', href=f"{DOMAIN}{post['url']}"))
        
        # Group D: Branding & Resources
        for icon in favicons:
            new_head.append(copy.copy(icon))
            
        # Preserve Scripts/Styles (Tailwind, Fonts, Custom Styles)
        for tag in original_head.find_all(['script', 'link', 'style']):
            # Skip favicon links as we added them
            rel = tag.get('rel', [])
            if isinstance(rel, list): rel = " ".join(rel)
            if 'icon' in rel:
                continue
            if tag.name == 'link' and 'canonical' in rel:
                continue
            if tag.name == 'link' and 'alternate' in rel:
                continue
                
            new_head.append(copy.copy(tag))
            
        # Group E: Structured Data
        if json_ld:
            new_head.append(copy.copy(json_ld))
            
        # Replace Head
        if soup.head:
            soup.head.replace_with(new_head)
        else:
            soup.insert(0, new_head)
            
        # --- Phase 3: Content Injection ---
        
        # 1. Layout Sync (Nav/Footer)
        if soup.body:
            # Replace Nav
            existing_nav = soup.body.find('nav')
            if existing_nav and nav_template:
                existing_nav.replace_with(copy.copy(nav_template))
            elif nav_template:
                soup.body.insert(0, copy.copy(nav_template))
                
            # Replace Footer
            existing_footer = soup.body.find('footer')
            
            # Remove old Recommended Reading
            for section in soup.find_all('section'):
                h2 = section.find('h2')
                if h2 and 'Recommended Reading' in h2.get_text():
                    section.decompose()
            
            if existing_footer and footer_template:
                existing_footer.replace_with(copy.copy(footer_template))
            elif footer_template:
                soup.body.append(copy.copy(footer_template))
                
        # 3. Smart Recommendation
        article = soup.find('article')
        if article:
            # Remove existing Recommended Reading to ensure we can update it
            for div in article.find_all('div', class_='mt-12 pt-12 border-t border-white/10'):
                h3 = div.find('h3')
                if h3 and h3.string == "Recommended Reading":
                    div.decompose()
            
            # Create Recommendation Module
            rec_section = soup.new_tag('div', attrs={'class': 'mt-12 pt-12 border-t border-white/10'})
            rec_title = soup.new_tag('h3', attrs={'class': 'text-2xl font-bold text-white mb-6'})
            rec_title.string = "Recommended Reading"
            rec_section.append(rec_title)
            
            rec_grid = soup.new_tag('div', attrs={'class': 'grid grid-cols-1 md:grid-cols-2 gap-6'})
            
            # Get other posts
            other_posts = [p for p in posts if p['filename'] != post['filename']]
            
            # Generate HTML for top 4 posts
            for p in other_posts[:4]: 
                card_html = f'''
                <a href="{p['url']}" class="group block glass-card rounded-2xl overflow-hidden hover:bg-white/5 transition-all border border-white/5">
                    <div class="p-5">
                        <div class="flex items-center gap-2 mb-2">
                            <span class="text-xs text-insPurple font-bold">Read</span>
                            <span class="text-xs text-gray-500">{p['date']}</span>
                        </div>
                        <h4 class="text-white font-bold mb-2 group-hover:text-insPurple transition-colors line-clamp-1">
                            {p['title']}
                        </h4>
                    </div>
                </a>
                '''
                card = BeautifulSoup(card_html, 'html.parser')
                if card.body and card.body.contents:
                    for child in card.body.contents:
                        if child.name:
                            rec_grid.append(child)
                elif card.contents:
                     for child in card.contents:
                        if child.name:
                            rec_grid.append(child)
                
            rec_section.append(rec_grid)
            article.append(rec_section)
            
        # Save
        output_html = str(soup)
        if not output_html.startswith('<!DOCTYPE html>'):
            output_html = '<!DOCTYPE html>\n' + output_html
            
        write_file(post['path'], output_html)
        
    # --- Phase 4: Global Update (Sync Homepage & Aggregation) ---
    print("Phase 4: Global Update...")
    
    # Generate HTML for latest 3 articles
    latest_html = get_latest_posts_html(posts, limit=3)
    latest_soup_fragment = BeautifulSoup(latest_html, 'html.parser')
    
    # Update index.html
    if index_soup.body:
        # Find the "Latest Articles" section
        for section in index_soup.find_all('section'):
            h2 = section.find('h2')
            if h2 and 'Latest Articles' in h2.get_text():
                grid = section.find('div', class_='grid')
                if grid:
                    grid.clear()
                    if latest_soup_fragment.body:
                         for child in latest_soup_fragment.body.contents:
                            if child.name: grid.append(copy.copy(child))
                    else:
                         for child in latest_soup_fragment.contents:
                            if child.name: grid.append(copy.copy(child))
                    print("Updated Latest Articles in index.html")
                    break
        
        write_file(INDEX_PATH, str(index_soup))
        
    # Update blog/index.html if it exists
    blog_index_path = os.path.join(BLOG_DIR, 'index.html')
    if os.path.exists(blog_index_path):
        print("Updating blog/index.html...")
        blog_index_content = read_file(blog_index_path)
        blog_index_soup = BeautifulSoup(blog_index_content, 'html.parser')
        
        # --- Update JSON-LD for Breadcrumb & ItemList ---
        json_ld_tag = blog_index_soup.find('script', type='application/ld+json')
        current_data = {}
        if json_ld_tag and json_ld_tag.string:
            try:
                current_data = json.loads(json_ld_tag.string)
            except:
                pass
        
        # Ensure basic structure
        if '@context' not in current_data: current_data['@context'] = "https://schema.org"
        if '@type' not in current_data: current_data['@type'] = "CollectionPage"
        if 'url' not in current_data: current_data['url'] = f"{DOMAIN}/blog/"
        if 'name' not in current_data: current_data['name'] = "INS-Mai 博客"
        
        # Update Breadcrumb
        current_data['breadcrumb'] = {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "首页",
                    "item": f"{DOMAIN}/"
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": "博客",
                    "item": f"{DOMAIN}/blog/"
                }
            ]
        }
        
        # Update ItemList (Article List)
        item_list_elements = []
        for i, post in enumerate(posts, 1):
            item_list_elements.append({
                "@type": "ListItem",
                "position": i,
                "url": f"{DOMAIN}{post['url']}",
                "name": post['title']
            })
            
        current_data['mainEntity'] = {
            "@type": "ItemList",
            "itemListElement": item_list_elements
        }
        
        # Write back JSON-LD
        if json_ld_tag:
            json_ld_tag.string = json.dumps(current_data, indent=2, ensure_ascii=False)
        else:
            new_script = blog_index_soup.new_tag('script', type='application/ld+json')
            new_script.string = json.dumps(current_data, indent=2, ensure_ascii=False)
            if blog_index_soup.head:
                blog_index_soup.head.append(new_script)
            else:
                # Fallback if no head (unlikely)
                blog_index_soup.insert(0, new_script)

        updated = False
        
        # Try finding main > grid first
        main_tag = blog_index_soup.find('main')
        if main_tag:
            grid = main_tag.find('div', class_='grid')
            if grid:
                 all_posts_html = get_latest_posts_html(posts, limit=100)
                 all_posts_soup = BeautifulSoup(all_posts_html, 'html.parser')
                 grid.clear()
                 if all_posts_soup.body:
                     for child in all_posts_soup.body.contents:
                         if child.name: grid.append(copy.copy(child))
                 else:
                     for child in all_posts_soup.contents:
                         if child.name: grid.append(copy.copy(child))
                 updated = True
                 print("Updated article list in blog/index.html (via main > grid)")
        
        if not updated:
            for section in blog_index_soup.find_all('section'):
                 h2 = section.find('h2')
                 if h2 and ('Latest' in h2.get_text() or 'Articles' in h2.get_text()):
                     grid = section.find('div', class_='grid')
                     if grid:
                         all_posts_html = get_latest_posts_html(posts, limit=100)
                         all_posts_soup = BeautifulSoup(all_posts_html, 'html.parser')
                         grid.clear()
                         if all_posts_soup.body:
                             for child in all_posts_soup.body.contents:
                                 if child.name: grid.append(copy.copy(child))
                         else:
                             for child in all_posts_soup.contents:
                                 if child.name: grid.append(copy.copy(child))
                         updated = True
                         print("Updated article list in blog/index.html")
                         break
        
        if updated:
            # Also sync Nav/Footer
            if blog_index_soup.body:
                 existing_nav = blog_index_soup.body.find('nav')
                 if existing_nav and nav_template: existing_nav.replace_with(copy.copy(nav_template))
                 elif nav_template: blog_index_soup.body.insert(0, copy.copy(nav_template))
                 
                 existing_footer = blog_index_soup.body.find('footer')
                 if existing_footer and footer_template: existing_footer.replace_with(copy.copy(footer_template))
                 elif footer_template: blog_index_soup.body.append(copy.copy(footer_template))
            
            write_file(blog_index_path, str(blog_index_soup))
            
    # Phase 4.5: Process Static Pages
    print("Phase 4.5: Processing static pages...")
    static_pages = [
        {
            'filename': 'about.html',
            'type': 'AboutPage',
            'name': '关于我们',
            'url': '/about',
            'desc': 'INS-Mai.TOP 致力于为全球品牌和个人创作者提供高质量的 Instagram 账号资源。了解我们的故事和使命。'
        },
        {
            'filename': 'contact.html',
            'type': 'ContactPage',
            'name': '联系我们',
            'url': '/contact',
            'desc': '联系 INS-Mai.TOP 客服团队。我们提供 7x24 小时在线支持，解决您的任何问题。'
        },
        {
            'filename': 'terms.html',
            'type': 'WebPage',
            'name': '服务条款',
            'url': '/terms',
            'desc': 'INS-Mai.TOP 服务条款。使用我们服务前请阅读本协议。'
        },
        {
            'filename': 'privacy.html',
            'type': 'WebPage',
            'name': '隐私政策',
            'url': '/privacy',
            'desc': 'INS-Mai.TOP 隐私政策。我们如何收集、使用和保护您的个人信息。'
        }
    ]

    for page in static_pages:
        path = os.path.join(BASE_DIR, page['filename'])
        if os.path.exists(path):
            print(f"Updating {page['filename']}...")
            content = read_file(path)
            soup = BeautifulSoup(content, 'html.parser')
            
            # 1. Sync Nav/Footer
            if soup.body:
                existing_nav = soup.body.find('nav')
                if existing_nav and nav_template:
                    existing_nav.replace_with(copy.copy(nav_template))
                elif nav_template:
                    soup.body.insert(0, copy.copy(nav_template))
                    
                existing_footer = soup.body.find('footer')
                if existing_footer and footer_template:
                    existing_footer.replace_with(copy.copy(footer_template))
                elif footer_template:
                    soup.body.append(copy.copy(footer_template))

            # 2. Inject JSON-LD
            json_ld_tag = soup.find('script', type='application/ld+json')
            data = {}
            
            # Basic info
            data['@context'] = "https://schema.org"
            data['@type'] = page['type']
            data['name'] = page['name']
            data['description'] = page['desc']
            data['url'] = f"{DOMAIN}{page['url']}"
            data['publisher'] = {
                "@type": "Organization",
                "name": "INS-Mai",
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{DOMAIN}/favicon.svg"
                }
            }
            
            # Breadcrumb
            data['breadcrumb'] = {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "首页",
                        "item": f"{DOMAIN}/"
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": page['name'],
                        "item": f"{DOMAIN}{page['url']}"
                    }
                ]
            }

            if json_ld_tag:
                json_ld_tag.string = json.dumps(data, indent=2, ensure_ascii=False)
            else:
                new_script = soup.new_tag('script', type='application/ld+json')
                new_script.string = json.dumps(data, indent=2, ensure_ascii=False)
                if soup.head:
                    soup.head.append(new_script)
                else:
                    soup.insert(0, new_script)
            
            # Save
            output_html = str(soup)
            if not output_html.startswith('<!DOCTYPE html>'):
                output_html = '<!DOCTYPE html>\n' + output_html
            write_file(path, output_html)

    # Phase 5: Update Sitemap
    update_sitemap(posts)

    print("Build complete!")

if __name__ == '__main__':
    main()
