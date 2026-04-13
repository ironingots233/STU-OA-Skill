import urllib.request
import urllib.parse
import urllib.error
import re
import html
import json

# --- 全局配置 ---
HOST_DOMAIN = "http://oa.stu.edu.cn"
LIST_URL = "http://oa.stu.edu.cn/csweb/list.jsp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded"
}

def fetch_latest_news_list(pagesize=20):
    """抓取最新一页的新闻列表，用于将 Agent 传来的 ID 映射为真实的 URL"""
    form_data = {'pageindex': '1', 'pagesize': str(pagesize)}
    data = urllib.parse.urlencode(form_data).encode('ascii')
    req = urllib.request.Request(LIST_URL, data=data, headers=HEADERS)
    
    all_news = []
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode('gbk', errors='ignore')
            
        pattern = re.compile(
            r'<a[^>]*href=["\']([^"\']*newstemplateprotal\.jsp[^"\']*)["\'][^>]*title=["\']([^"\']+)["\']',
            re.IGNORECASE
        )
        matches = list(pattern.finditer(html_content))
        
        for match in matches:
            link = html.unescape(match.group(1).strip())
            title = html.unescape(match.group(2).strip())
            full_url = HOST_DOMAIN + link if link.startswith('/') else link
            all_news.append({'title': title, 'url': full_url})
            
    except Exception as e:
        # Agent 运行时不应使用 print，错误应向上传递
        raise Exception(f"目录抓取失败: {str(e)}")
        
    return all_news

def fetch_clean_content(url):
    """精准抓取正文并进行深度清洗"""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode('gbk', errors='ignore')
            
        # 1. 寻找核心正文锚点
        main_content_match = re.search(r'<span id="spanContent"[^>]*>(.*?)</span>', html_content, flags=re.IGNORECASE | re.DOTALL)
        if main_content_match:
            target_html = main_content_match.group(1)
        else:
            body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, flags=re.IGNORECASE | re.DOTALL)
            target_html = body_match.group(1) if body_match else html_content

        # 2. 深度清洗元凶
        target_html = re.sub(r'<script[^>]*>.*?</script>', '', target_html, flags=re.IGNORECASE | re.DOTALL)
        target_html = re.sub(r'<style[^>]*>.*?</style>', '', target_html, flags=re.IGNORECASE | re.DOTALL)
        target_html = re.sub(r'<title[^>]*>.*?</title>', '', target_html, flags=re.IGNORECASE | re.DOTALL)
        target_html = re.sub(r'<!--.*?-->', '', target_html, flags=re.IGNORECASE | re.DOTALL)

        # 3. 把排版标签替换为真正的换行符
        target_html = re.sub(r'</?(p|br|div|tr|li)[^>]*>', '\n', target_html, flags=re.IGNORECASE)

        # 4. 剥离所有残余的 HTML 标签
        target_html = re.sub(r'<[^>]+>', '', target_html)

        # 5. 解码 HTML 实体
        text = html.unescape(target_html)

        # 6. 专门干掉 Word 复制粘贴产生的特有乱码/元数据文本
        text = re.sub(r'\d*MicrosoftInternetExplorer.*?Normal0', '', text, flags=re.IGNORECASE)

        # 7. 终极格式整理
        text = text.replace('\xa0', ' ').replace('\u3000', ' ')
        lines = [line.strip() for line in text.split('\n')]
        
        clean_lines = []
        for line in lines:
            if line and "相关附件：" not in line and "隐藏元素库" not in line:
                clean_lines.append(line)
                
        return '\n'.join(clean_lines)

    except Exception as e:
        return f"[获取失败: {str(e)}]"

def scrape_oa_details(item_ids: list) -> str:
    """
    Agent 调用的入口函数。
    输入: item_ids 列表 (如 [1, 3, 5])
    输出: 包含正文内容的 JSON 字符串
    """
    # 1. 校验输入是否为列表
    if not isinstance(item_ids, list) or not item_ids:
        return json.dumps({"status": "error", "message": "未提供有效的条目号数组参数 (item_ids)"}, ensure_ascii=False)
        
    # 提取有效的数字并去重
    valid_choices = []
    for c in item_ids:
        try:
            idx = int(c)
            if idx >= 1 and idx not in valid_choices:
                valid_choices.append(idx)
        except (ValueError, TypeError):
            continue
                
    if not valid_choices:
        return json.dumps({"status": "error", "message": f"无法从输入 {item_ids} 中解析出有效的数字条目号"}, ensure_ascii=False)

    # 2. 计算需要获取的目录深度并抓取目录
    max_idx = max(valid_choices)
    try:
        news_list = fetch_latest_news_list(pagesize=max_idx)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    
    if not news_list:
        return json.dumps({"status": "error", "message": "未能获取到 OA 目录，请检查网络或目标网站状态。"}, ensure_ascii=False)
        
    # 3. 批量抓取并组装结果
    results = []
    for idx in valid_choices:
        if idx > len(news_list):
            results.append({
                "id": str(idx),
                "title": "未知",
                "content": f"[错误] 条目号 {idx} 超出当前最大范围 ({len(news_list)})，已跳过。"
            })
            continue
            
        news_item = news_list[idx - 1]
        content = fetch_clean_content(news_item['url'])
        
        results.append({
            "id": str(idx),
            "title": news_item['title'],
            "content": content
        })

    # 4. 返回标准 JSON
    return json.dumps({
        "status": "success",
        "count": len(results),
        "data": results
    }, ensure_ascii=False)

# 本地测试用的代码，如果是 Agent 引入此模块，下面的代码不会执行
if __name__ == '__main__':
    # 模拟 Agent 传参，现在传入的是 Python List 而不是字符串
    test_ids = [1, 2]
    result_json = scrape_oa_details(test_ids)
    print("Agent 将会收到的结果：\n")
    print(json.dumps(json.loads(result_json), indent=2, ensure_ascii=False))