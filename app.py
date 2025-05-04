from flask import Flask, jsonify, request, Response
import cloudscraper
from bs4 import BeautifulSoup
import concurrent.futures
import json, os, random, string, time, re
from collections import OrderedDict
from urllib.parse import urlencode
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
scraper = cloudscraper.create_scraper()

def get_random_delay():
    return random.uniform(3, 5)

def get_random_user_agent():
    windows_versions = ["10.0"]
    chrome_versions = f"{random.randint(119,129)}.0.0.0"
    return (
        f"Mozilla/5.0 (Windows NT {random.choice(windows_versions)}; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_versions} Safari/537.36"
    )

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
    for attempt in range(retry_count):
        try:
            time.sleep(get_random_delay())
            chapter = {'index': wasuu}
            uaid = 'hX1IoWgQQqc79xeVw' + ''.join(random.choices(string.ascii_letters + string.digits, k=3)) + 'Ag=='
            headers = {
                "User-Agent": get_random_user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "ja-JP,ja;q=0.9",
                "Referer": 'https://syosetu.org/novel/{nid}/',
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
                "Connection": "keep-alive"
            }
            response = scraper.get(url, headers=headers, cookies={'ETURAN': f'{nid}_{wasuu}', 'over18': 'off', 'uaid': uaid})
            soup = BeautifulSoup(response.text, "html.parser")
            chapter_title_tags = soup.find('div', id='maind').find_all('span')[1]
            chapter_title_text = chapter_title_tags.decode_contents().replace('<br/>', '\n')
            result = [line.strip() for line in chapter_title_text.split('\n') if line.strip()]
            if len(result) == 2:
                chapter["chap_title"] = result[0]
                chapter["title"] = result[1]
            elif len(result) == 1:
                chapter["title"] = result[0]
            chapter["content"] = '\n'.join(p.text for p in soup.find(id='honbun').find_all('p'))
            return chapter
        except Exception as e:
            print(f"エラー: {url}の取得に失敗しました。試行回数: {attempt + 1}/{retry_count}")
            if attempt == retry_count - 1:
                return {"error": f"チャプター{wasuu}の取得に失敗しました: {str(e)}"}
            time.sleep(get_random_delay())
    return {"error": f"チャプター{wasuu}の取得に失敗しました"}

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
    
    try:
        time.sleep(get_random_delay())
        uaid = 'hX1IoWgQQqc79xeVw' + ''.join(random.choices(string.ascii_letters + string.digits, k=3)) + 'Ag=='
        response = scraper.get(novel_url, headers=headers, cookies={'over18': 'off'})
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.find('div', class_='ss').find('span', attrs={'itemprop': 'name'}).text
        author = soup.find('div', class_='ss').find('span', attrs={'itemprop': 'author'}).text
        chapter_count = len(soup.select('a[href^="./"]'))
        chapters = [None] * chapter_count
        
        max_workers = min(os.cpu_count() or 1, 3)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(get_chapter_text, scraper, f'{novel_url}{i+1}.html', headers, nid, i+1): i 
                for i in range(chapter_count)
            }
            for future in concurrent.futures.as_completed(future_to_url):
                chapter_num = future_to_url[future]
                try:
                    chapters[chapter_num] = future.result()
                except Exception as exc:
                    print(f'チャプター {chapter_num} でエラーが発生しました: {exc}')
                    chapters[chapter_num] = {"error": f"チャプター{chapter_num + 1}の取得に失敗しました"}
        
        result = OrderedDict([
            ('id', int(nid)),
            ('title', title),
            ('author', author),
            ('contents', chapters)
        ])
        return result
    except Exception as e:
        print(f"小説の取得中にエラーが発生しました: {str(e)}")
        return {"error": "小説の取得に失敗しました"}


def parse_novel(novel):
    title = novel.find('a').text
    link = novel.find('a').get('href')
    nid = re.search(r'//syosetu.org/novel/(\d+)/', link).group(1)
    author_info = novel.find_all('div', class_='blo_title_sak')[-1].text.split('\n')
    author = author_info[2][2:]
    parody = author_info[1].replace('原作：','')
    if 'オリジナル：' in parody:
        parody = ['オリジナル', parody.replace('オリジナル：','')]
    else:
        parody = ['原作', parody]
    description = novel.find('div', class_='blo_inword').text
    status = novel.find('div', class_='blo_wasuu_base').find('span').text
    latest = novel.find('a', attrs={'title':'最新話へのリンク'}).text
    updated_day = novel.find('div', attrs={'title':'最終更新日'}).text
    words = novel.find('div', attrs={'title': '総文字数'}).text.split(' ')[1]
    evaluation = novel.find('div', class_='blo_hyouka').text.strip()[5:]
    all_keywords = novel.find('div', class_='all_keyword').find_all('a')
    alert_keywords = [x.text for x in novel.find('div', class_='all_keyword').find('span').find_all('a')]
    keywords = [x.text for x in all_keywords if x.text not in alert_keywords]
    favs = novel.find_all('div', attrs={'style': 'background-color: transparent;'})[-1].text.split('｜')[1][6:]
    
    return OrderedDict([
        ('nid', nid),
        ('title', title),
        ('link', link),
        ('author', author),
        ('parody', parody),
        ('description', description),
        ('status', status),
        ('latest', latest),
        ('updated_day', f'{updated_day[:10]} {updated_day[10:]}'),
        ('words', words),
        ('evaluation', evaluation),
        ('alert_keywords', alert_keywords),
        ('keywords', keywords),
        ('favs', favs)
    ])

def search_result(search_url, scraper):
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ja-JP,ja;q=0.9",
        "Referer": get_random_referer(),
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        uaid = 'hX1IoWgQQqc79xeVw' + ''.join(random.choices(string.ascii_letters + string.digits, k=3)) + 'Ag=='
        response = scraper.get(search_url, headers=headers, cookies={'over18': 'off', 'uaid': uaid, 'list_num':'50'})
        soup = BeautifulSoup(response.text, "html.parser")
        novels = soup.find_all('div', class_='section3')
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_index = {executor.submit(parse_novel, novel): i for i, novel in enumerate(novels)}
            results = [None] * len(novels)
                
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                results[index] = future.result()
        
        result_data = json.dumps(results, ensure_ascii=False, indent=2)
        return Response(
            result_data,
            mimetype='application/json; charset=utf-8',
            headers={'Content-Type': 'application/json; charset=utf-8'}
        )

    except Exception as e:
        return {'error': str(e)}

            
@app.route('/api/novel/<nid>', methods=['GET'])
def get_novel(nid):
    novel_data = get_novel_txt(nid)
    if novel_data and "error" not in novel_data:
        response_data = json.dumps(novel_data, ensure_ascii=False, indent=2)
        return Response(
            response_data,
            mimetype='application/json; charset=utf-8',
            headers={'Content-Type': 'application/json; charset=utf-8'}
        )
    return jsonify({'error': '小説の取得に失敗しました'}), 500

@app.route('/api/search', methods=['GET'])
def search_novel():
    search_mode = request.form.get('mode', 'search')
    word = request.form.get('word', '')
    parody = request.form.get('parody', '')
    type_value = request.form.get('type', '0')

    filter_params = ['rensai_s1', 'rensai_s2', 'rensai_s4', 'mozi2', 'mozi1', 'mozi2_all', 'mozi1_all', 'rate2', 'rate1', 
                     'soupt2', 'soupt1', 'f2', 'f1', 're2', 're1', 'v2', 'v1', 
                     'r2', 'r1', 't2', 't1', 'd2', 'd1']

    url_params = {
        'mode': search_mode,
        'word': word,
        'gensaku': parody,
        'type': type_value
    }

    for param in filter_params:
        value = request.form.get(param)
        if value:
            url_params[param] = value

    search_url = f"https://syosetu.org/search/?{urlencode(url_params)}"
    
    try:
        return search_result(search_url, scraper)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/about/<nid>', methods=['GET'])
def get_about(nid):
    search_url = f"https://syosetu.org/novel/{nid}/"
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ja-JP,ja;q=0.9",
        "Referer": get_random_referer(),
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        uaid = 'hX1IoWgQQqc79xeVw' + ''.join(random.choices(string.ascii_letters + string.digits, k=3)) + 'Ag=='
        response = scraper.get(search_url, headers=headers, cookies={'over18': 'off', 'uaid': uaid})
        soup = BeautifulSoup(response.text, "html.parser")
        chapters_table = soup.find_all('div', class_='ss')[2].find('table')
        chapters_table_rows = chapters_table.find_all('tr')
        chapters = dict()
        chapters_list = []
        current_chapter = "dasqan-8myfpa-nytdUw"
        
        for row in chapters_table_rows:
            if len(row.find_all('td')) == 1:
                current_chapter = row.find('td').text
                chapters[current_chapter] = []
                chapters_list.append(current_chapter)
            if len(row.find_all('td')) == 2:
                if current_chapter not in chapters:
                    chapters[current_chapter] = []
                    chapters_list.append(current_chapter)
                chapters[current_chapter].append(row.find_all('td')[0].text.replace('\u3000', '')[1:])
        
        result = OrderedDict([
            (chapter, chapters[chapter]) for chapter in chapters_list
        ])
        response_data = json.dumps(result, ensure_ascii=False, indent=2)
        return Response(
            response_data,
            mimetype='application/json; charset=utf-8',
            headers={'Content-Type': 'application/json; charset=utf-8'}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False)
