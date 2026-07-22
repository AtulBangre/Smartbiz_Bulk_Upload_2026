from playwright.async_api import async_playwright
import requests
from bs4 import BeautifulSoup
import re
import asyncio

def scrape_amazon_bs4(url: str) -> dict:
    details = {
        "name": "Amazon Product",
        "mrp": "1000",
        "selling_price": "800",
        "description": "<ul class=\"a-unordered-list a-vertical a-spacing-mini\"><li class=\"a-spacing-mini\"><span class=\"a-list-item\">High Quality Product</span></li></ul>",
        "images": []
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            title = soup.find(id='productTitle')
            if title:
                details["name"] = title.get_text().strip()[:200]
                
            price = soup.select_one('.priceToPay .a-price-whole, .apexPriceToPay .a-price-whole, #corePrice_feature_div .a-price-whole')
            if price:
                raw_p = re.sub(r'[^\d.]', '', price.get_text())
                if raw_p:
                    details["selling_price"] = str(int(round(float(raw_p))))
                    
            mrp = soup.select_one('.a-text-strike')
            if mrp:
                raw_m = re.sub(r'[^\d.]', '', mrp.get_text())
                if raw_m:
                    details["mrp"] = str(int(round(float(raw_m))))
            
            if not details["mrp"] and details["selling_price"]:
                details["mrp"] = details["selling_price"]

            # Images
            imgs = soup.select('#altImages img, #imgTagWrapperId img, #main-image-container img')
            for img in imgs:
                src = img.get('src', '')
                if src and '.jpg' in src and 'play-button' not in src and 'transparent-pixel' not in src:
                    high_res = re.sub(r'\._.*?_\.jpg', '._SL1080_.jpg', src)
                    if high_res not in details["images"]:
                        details["images"].append(high_res)
                if len(details["images"]) >= 6:
                    break

            # Bullets
            bullets = soup.select('#feature-bullets ul li span.a-list-item')
            if bullets:
                b_html = '<ul class="a-unordered-list a-vertical a-spacing-mini">'
                for b in bullets:
                    txt = b.get_text().strip()
                    if txt:
                        b_html += f'<li class="a-spacing-mini"><span class="a-list-item">{txt}</span></li>'
                b_html += '</ul>'
                if len(b_html) > 50:
                    details["description"] = b_html[:2000]
    except Exception as e:
        print(f"BS4 Scraper fallback exception: {e}")
        
    return details

async def scrape_amazon_product(url: str) -> dict:
    details = {
        "name": "",
        "mrp": "",
        "selling_price": "",
        "description": "",
        "images": []
    }
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=12000)
                
                # Scrape Title
                try:
                    title_elem = await page.query_selector('#productTitle')
                    if title_elem:
                        details["name"] = (await title_elem.inner_text()).strip()[:200]
                except Exception as e:
                    print(f"Error scraping title: {e}")

                # Scrape Selling Price
                try:
                    price_elem = await page.query_selector('.priceToPay .a-price-whole, .apexPriceToPay .a-price-whole, #corePrice_feature_div .a-price-whole')
                    if price_elem:
                        price_text = await price_elem.inner_text()
                        raw_price = re.sub(r'[^\d.]', '', price_text)
                        if raw_price:
                            details["selling_price"] = str(int(round(float(raw_price))))
                except Exception as e:
                    print(f"Error scraping selling price: {e}")

                # Scrape MRP
                try:
                    mrp_elem = await page.query_selector('.a-text-strike')
                    if mrp_elem:
                        mrp_text = await mrp_elem.inner_text()
                        raw_mrp = re.sub(r'[^\d.]', '', mrp_text)
                        if raw_mrp:
                            details["mrp"] = str(int(round(float(raw_mrp))))
                    
                    if not details["mrp"] and details["selling_price"]:
                        details["mrp"] = details["selling_price"]
                except Exception as e:
                    print(f"Error scraping MRP: {e}")

                if not details["mrp"] and not details["selling_price"]:
                    details["mrp"] = "1000"
                    details["selling_price"] = "800"

                # Scrape Images
                try:
                    images = []
                    img_elements = await page.query_selector_all('#altImages img')
                    if not img_elements:
                        img_elements = await page.query_selector_all('#imgTagWrapperId img, #main-image-container img')
                        
                    for img in img_elements:
                        src = await img.get_attribute('src')
                        if src and '.jpg' in src:
                            high_res_url = re.sub(r'\._.*?_\.jpg', '._SL1080_.jpg', src)
                            if high_res_url == src and '._SL1080_' not in high_res_url:
                                high_res_url = src.replace('.jpg', '._SL1080_.jpg')
                                
                            if high_res_url not in images:
                                if "play-button" not in high_res_url and "transparent-pixel" not in high_res_url:
                                    images.append(high_res_url)
                            
                            if len(images) >= 6:
                                break
                    
                    details["images"] = images
                except Exception as e:
                    print(f"Error scraping images: {e}")
                    details["images"] = []

                # Scrape Description
                try:
                    bullet_elems = await page.query_selector_all('#feature-bullets ul li span.a-list-item')
                    desc_html = ""
                    
                    if bullet_elems:
                        desc_html = '<ul class="a-unordered-list a-vertical a-spacing-mini">'
                        for elem in bullet_elems:
                            text = (await elem.inner_text()).strip()
                            if text:
                                addition = f'<li class="a-spacing-mini"><span class="a-list-item">{text}</span></li>'
                                if len(desc_html) + len(addition) + 5 > 2000:
                                    break
                                desc_html += addition
                        desc_html += '</ul>'
                        if desc_html == '<ul class="a-unordered-list a-vertical a-spacing-mini"></ul>':
                            desc_html = ""
                            
                    if not desc_html:
                        desc_elem = await page.query_selector('#productDescription')
                        if desc_elem:
                            desc_text = (await desc_elem.inner_text()).strip()
                            desc_html = desc_text.replace('\n', '<br>')
                            desc_html = desc_html[:2000]
                    
                    details["description"] = desc_html
                except Exception as e:
                    print(f"Error scraping description: {e}")
                    
            except Exception as e:
                print(f"Failed to load page with Playwright {url}: {e}")
            finally:
                await browser.close()
                
    except Exception as pw_err:
        print(f"Playwright unavailable or crashed ({pw_err}). Using BeautifulSoup fallback...")
        return scrape_amazon_bs4(url)

    # If title wasn't found by Playwright, try BS4 fallback
    if not details.get("name"):
        bs4_data = scrape_amazon_bs4(url)
        if bs4_data.get("name"):
            return bs4_data
            
    return details
