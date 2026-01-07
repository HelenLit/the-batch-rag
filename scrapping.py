import os
import json
import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Config
BASE_URL = "https://www.deeplearning.ai"
SECTIONS = {
    "hardware": "https://www.deeplearning.ai/the-batch/tag/hardware/",
    "ai-careers": "https://www.deeplearning.ai/the-batch/tag/ai-careers/",
    "science": "https://www.deeplearning.ai/the-batch/tag/science/",
    "culture": "https://www.deeplearning.ai/the-batch/tag/culture/",
    "letters": "https://www.deeplearning.ai/the-batch/tag/letters/",
    "data-points": "https://www.deeplearning.ai/the-batch/tag/data-points/",
    "research": "https://www.deeplearning.ai/the-batch/tag/research/",
    "business": "https://www.deeplearning.ai/the-batch/tag/business/",
}

TEXT_DIR = "data/scraped_texts"
IMG_DIR = "data/scraped_images"
os.makedirs(TEXT_DIR, exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)

_context = None

def reset_context(browser, navigation_timeout=30000):
    global _context
    if _context is not None:
        try:
            _context.close()
        except Exception:
            pass  # context may already be closed

    _context = browser.new_context()
    page = _context.new_page()
    page.set_default_navigation_timeout(navigation_timeout)
    return page

def get_all_slugs(page, section_name, start_url):
    print(f"--- Collecting slugs for: {section_name} ---")
    slugs = set()
    page.goto(start_url)

    if section_name == "letters":
        current_page = 1
        while True:
            target_url = start_url if current_page == 1 else f"{start_url}page/{current_page}/"
            print(f"Fetching page {current_page}: {target_url}")

            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector("article", timeout=5000)
                links = page.locator("article a").evaluate_all("list => list.map(a => a.href)")
                new_slugs = [l.strip("/").split("/")[-1] for l in links if "/the-batch/" in l and "/tag/" not in l]
                if not new_slugs:
                    print(f"No articles found on page {current_page}. Finishing.")
                    break
                slugs.update(new_slugs)
                current_page += 1
                time.sleep(1)
            except Exception:
                # This catches the TimeoutError when page 23 has no <article> tags
                print(f"Reached end of section or page empty at page {current_page}")
                break
    else:
        # Handle "Load more" div sections
        while True:
            load_more = page.locator("div:has-text('Load More')").last
            if load_more.is_visible():
                print(f"Clicking Load More... (Unique slugs so far: {len(slugs)})")
                load_more.scroll_into_view_if_needed()
                load_more.click()
                time.sleep(2)
                links = page.locator("article a").evaluate_all("list => list.map(a => a.href)")
                slugs.update([l.strip("/").split("/")[-1] for l in links if "/the-batch/" in l and "/tag/" not in l])
            else:
                # Final grab of everything once all pages are loaded
                links = page.locator("article a").evaluate_all("list => list.map(a => a.href)")
                slugs.update([l.strip("/").split("/")[-1] for l in links if "/the-batch/" in l and "/tag/" not in l])
                break

    print(f"Found {len(slugs)} slugs for {section_name}\n")
    return list(slugs)


def scrape_full_article(page, slug):
    article_url = f"{BASE_URL}/the-batch/{slug}/"
    page.goto(article_url)
    page.wait_for_load_state("domcontentloaded")
    # Extract data from the __NEXT_DATA__ script tag
    try:
        json_content = page.locator("script#__NEXT_DATA__").inner_text()
        json_data = json.loads(json_content)
        post_data = json_data['props']['pageProps']['post']
        # Save Text
        html_content = post_data.get('html', '')
        soup = BeautifulSoup(html_content, "html.parser")
        clean_text = soup.get_text(separator="\n")
        filepath = os.path.join(TEXT_DIR, f"{slug}.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Title: {post_data.get('title')}\n")
            f.write(f"Published: {post_data.get('published_at')}\n\n")
            f.write(clean_text)
        # Save Image
        img_url = post_data.get('feature_image')
        if img_url:
            ext = img_url.split(".")[-1].split("?")[0]
            # Ensure extension is clean (e.g., 'jpg', 'webp')
            if len(ext) > 4: ext = "jpg"
            img_res = requests.get(img_url, timeout=10)
            img_path = os.path.join(IMG_DIR, f"{slug}.{ext}")
            with open(img_path, "wb") as f:
                f.write(img_res.content)
        print(f"Successfully scraped: {slug}")
    except Exception as e:
        print(f"Failed to parse JSON for {slug}: {e}")


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        all_target_slugs = []
        for name, url in SECTIONS.items():
            try:
                page = reset_context(browser)
                section_slugs = get_all_slugs(page, name, url)
                all_target_slugs.extend(section_slugs)
            except Exception as e:
                print(f"Error collecting slugs in {name}: {e}")

        unique_slugs = list(set(all_target_slugs))
        print(f"--- Total unique articles found: {len(unique_slugs)} ---")

        page = reset_context(browser)
        # Process each article, skipping already scraped ones
        for i, slug in enumerate(unique_slugs):
            if not os.path.exists(os.path.join(TEXT_DIR, f"{slug}.txt")):
                print(f"[{i + 1}/{len(unique_slugs)}] ", end="")
                scrape_full_article(page, slug)
                time.sleep(1)
            else:
                pass  # Already scraped

        browser.close()


if __name__ == "__main__":
    run()