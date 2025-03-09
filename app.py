from flask import Flask, jsonify, request
import cloudscraper
from bs4 import BeautifulSoup
import concurrent.futures
import time
import random
import argon2

app = Flask(__name__)
ph = argon2.PasswordHasher()

def get_random_delay():
    return random.uniform(1, 3)

def get_random_user_agent():
    windows_versions = ["10.0"]
    chrome_versions = f"{random.randint(119,129)}.0.0.0"
    user_agent = (
        f"Mozilla/5.0 (Windows NT {random.choice(windows_versions)}; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_versions} Safari/537.36"
    )
    return user_agent

def get_random_referer():
    referers = [
        "https://www.google.com/search?q=%E3%83%8F%E3%83%BC%E3%83%A1%E3%83%AB%E3%83%B3&ie=UTF-8&oe=UTF-8&hl=ja-jp&client=safari",
        "https://syosetu.org/",
        "https://syosetu.org/search/?mode=search",
        "https://syosetu.org/?mode=rank",
        "https://syosetu.org/?mode=favo"
    ]
    return random.choice(referers)

def get_chapter_text(scraper, url, headers, nid, wasuu, retry_count=3):
    for _ in range(retry_count):
        try:
            time.sleep(get_random_delay())
            response = scraper.get(url, headers=headers, cookies={'ETURAN': f'{nid}_{wasuu}', 'over18': 'off'})
            soup = BeautifulSoup(response.text, "html.parser")
            chapter_title_tags = soup.find(id='maind')
            if chapter_title_tags.find('span', class_='alert_color'):
                chapter_title_tag = chapter_title_tags.find_all('span')[2]
            else:
                chapter_title_tag = chapter_title_tags.find_all('span')[1]
            chapter_title_text = chapter_title_tag.decode_contents()
            for tag in ['ruby', 'rb', 'rt', 'rp']:
                chapter_title_text = chapter_title_text.replace(f'<{tag}>', '').replace(f'</{tag}>', '')
            result = [str(part).strip() for part in chapter_title_text.split('<br/>') if part.strip()]
            chapter_title = (
                f'# {result[0]}\n## {result[1]}\n\n' if len(result) == 2 else
                f'## {result[0]}\n\n' if len(result) == 1 else
                ''
            )
            chapter_text = '\n'.join(p.text for p in soup.find(id='honbun').find_all('p'))
            return chapter_title + chapter_text
        except Exception as e:
            print(f"Error fetching {url}: {str(e)}. Retrying...")
            time.sleep(get_random_delay())
    return ""

def get_novel_txt(nid):
    novel_url = f'https://syosetu.org/novel/{nid}/'
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ja-JP,ja;q=0.9",
        "Referer": get_random_referer(),
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive"
    }
    scraper = cloudscraper.create_scraper()
    try:
        time.sleep(get_random_delay())
        response = scraper.get(novel_url, headers=headers, cookies={'over18': 'off'})
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.find('div', class_='ss').find('span', attrs={'itemprop': 'name'}).text
        chapter_count = len(soup.select('a[href^="./"]'))
        txt_data = [None] * chapter_count
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_to_url = {executor.submit(get_chapter_text, scraper, f'{novel_url}{i+1}.html', headers, nid, i+1): i for i in range(chapter_count)}
            for future in concurrent.futures.as_completed(future_to_url):
                chapter_num = future_to_url[future]
                try:
                    chapter_text = future.result()
                    txt_data[chapter_num] = chapter_text
                except Exception as exc:
                    print(f'Chapter {chapter_num} generated an exception: {exc}')
        novel_text = '\n\n'.join(filter(None, txt_data))
        return {'title': title, 'text': novel_text}
    except Exception as e:
        print(f"Error fetching novel: {str(e)}")
        return None

@app.route('/api/novel/<nid>', methods=['GET'])
def get_novel(nid):
    novel_data = get_novel_txt(nid)
    if novel_data:
        return jsonify(novel_data)
    return jsonify({'error': 'Failed to fetch novel'}), 500

if __name__ == '__main__':
    app.run(debug=False)
