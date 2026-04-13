import urllib.request
import urllib.parse
import urllib.error
import re
import html
import json
from datetime import datetime, timedelta

def fetch_oa_news_until(days_ago: int) -> str:
    """
    Agent 调用的入口函数。
    输入: days_ago (如 1 代表今天，7 代表这周)
    输出: 包含状态和数据的 JSON 字符串
    """
    # 1. 解析天数，转换为我们需要推算的截止日期 (target_date)
    try:
        days = int(days_ago)
        if days < 1:
            days = 1
    except ValueError:
        return json.dumps({
            "status": "error",
            "message": f"传入的天数格式错误: {days_ago}。请传入一个整数（例如 1 或 7）。"
        }, ensure_ascii=False)

    # 如果 days = 1，那就是只看今天（今天 - 0 天）
    # 如果 days = 7，那就是看过去7天（今天 - 6 天）
    target_date = datetime.today().date() - timedelta(days=days - 1)

    url = "http://oa.stu.edu.cn/csweb/list.jsp"
    host_domain = "http://oa.stu.edu.cn"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    pattern = re.compile(
        r'<a[^>]*href=["\']([^"\']*newstemplateprotal\.jsp[^"\']*)["\'][^>]*title=["\']([^"\']+)["\']',
        re.IGNORECASE
    )

    pageindex = 1
    pagesize = 20
    stop_crawling = False
    all_news = []
    
    # 2. 循环翻页
    while not stop_crawling:
        form_data = {'pageindex': str(pageindex), 'pagesize': str(pagesize)}
        data = urllib.parse.urlencode(form_data).encode('ascii')
        
        req = urllib.request.Request(url, data=data, headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                html_bytes = response.read()
                html_content = html_bytes.decode('gbk', errors='ignore')
                
            matches = list(pattern.finditer(html_content))
            
            if not matches:
                # 翻到底了，退出循环
                break
            
            # 3. 遍历提取数据
            for i, match in enumerate(matches):
                link = match.group(1)
                title = match.group(2)
                
                search_start = match.end()
                search_end = matches[i+1].start() if i+1 < len(matches) else search_start + 300
                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', html_content[search_start:search_end])
                
                if not date_match:
                    prev_end = matches[i-1].end() if i > 0 else max(0, match.start() - 300)
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', html_content[prev_end:match.start()])
                
                if date_match:
                    date_str = date_match.group(1).replace('/', '-')
                    try:
                        news_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        news_date = datetime.today().date()
                else:
                    date_str = "未知日期"
                    news_date = datetime.today().date()
                    
                # 4. 判断获取到的通知日期是否已经早于我们推算出的目标日期
                if news_date < target_date:
                    stop_crawling = True
                    break 
                
                # 清理数据
                link = html.unescape(link.strip())
                title = html.unescape(title.strip())
                full_url = host_domain + link if link.startswith('/') else link
                    
                all_news.append({
                    'date': date_str,
                    'title': title,
                    'url': full_url
                })
                
            if not stop_crawling:
                pageindex += 1

        except urllib.error.URLError as e:
            return json.dumps({
                "status": "error",
                "message": f"网络请求失败: {str(e)}"
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"发生未知错误: {str(e)}"
            }, ensure_ascii=False)

    # 5. 整理最终数据，补充 ID（供 Agent 调用下一个 skill 使用）
    formatted_data = []
    for idx, news in enumerate(all_news, 1):
        formatted_data.append({
            "id": str(idx),  # 这就是 Agent 接下来要传给 stu_oa_scraper.py 的 "条目号"
            "date": news['date'],
            "title": news['title'],
        })

    # 6. 返回规范的 JSON 结果
    return json.dumps({
        "status": "success",
        "count": len(formatted_data),
        "data": formatted_data
    }, ensure_ascii=False)

# 本地测试用的代码，如果是 Agent 引入此模块，下面的代码不会执行
if __name__ == '__main__':
    # 模拟 Agent 传参: 查询本周（过去7天）的通知
    test_days = 7 
    result_json = fetch_oa_news_until(test_days)
    print("Agent 将会收到的结果：\n")
    print(result_json)