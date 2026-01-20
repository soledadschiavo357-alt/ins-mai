import os
import re
import json
import copy
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
            
            title = soup.title.string if soup.title else filename
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
        
        # Title
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
            # Check if we already injected it (to avoid duplication on re-run)
            # A simple check is looking for the specific title
            already_has = False
            for h3 in article.find_all('h3'):
                if h3.string == "Recommended Reading":
                    already_has = True
                    break
            
            if not already_has:
                # Create Recommendation Module
                rec_section = soup.new_tag('div', attrs={'class': 'mt-12 pt-12 border-t border-white/10'})
                rec_title = soup.new_tag('h3', attrs={'class': 'text-2xl font-bold text-white mb-6'})
                rec_title.string = "Recommended Reading"
                rec_section.append(rec_title)
                
                rec_grid = soup.new_tag('div', attrs={'class': 'grid grid-cols-1 md:grid-cols-2 gap-6'})
                
                # Get other posts
                other_posts = [p for p in posts if p['filename'] != post['filename']]
                
                # Generate HTML for top 2-3 posts
                for p in other_posts[:2]: # Show 2 to fit layout
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
                    # Because BeautifulSoup parses a fragment into <html><body>...</body></html>, we need to extract the content
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
                # Find the grid container
                grid = section.find('div', class_='grid')
                if grid:
                    # Clear existing content
                    grid.clear()
                    # Append new content
                    # Be careful with bs4 fragment parsing
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
        
        updated = False
        
        # Try finding main > grid first (common for blog index)
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
            # Also sync Nav/Footer/Head for blog/index.html
            if blog_index_soup.body:
                 existing_nav = blog_index_soup.body.find('nav')
                 if existing_nav and nav_template: existing_nav.replace_with(copy.copy(nav_template))
                 elif nav_template: blog_index_soup.body.insert(0, copy.copy(nav_template))
                 
                 existing_footer = blog_index_soup.body.find('footer')
                 if existing_footer and footer_template: existing_footer.replace_with(copy.copy(footer_template))
                 elif footer_template: blog_index_soup.body.append(copy.copy(footer_template))
            
            write_file(blog_index_path, str(blog_index_soup))

    print("Build complete!")

if __name__ == '__main__':
    main()
