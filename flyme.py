#!/usr/bin/python3

# 导入必要的库，包括标准库、第三方库和自定义模块
import os  # 操作系统相关功能
import json  # 处理JSON数据
import time  # 处理时间相关功能
import asyncio  # 异步编程
import schedule  # 定时任务调度
import pyfiglet  # 生成ASCII艺术字
import argparse  # 解析命令行参数
import datetime  # 处理日期时间
import listparser  # 解析OPML格式
import feedparser  # 解析RSS和Atom feeds
from pathlib import Path  # 处理文件路径
from concurrent.futures import ThreadPoolExecutor, as_completed  # 并发执行任务

# 导入自定义模块中的bot和utils
from bot import *
from utils import *

# 禁用requests库中的SSL警告
import requests
requests.packages.urllib3.disable_warnings()

# 获取当前日期，格式为“YYYY-MM-DD”
today = datetime.datetime.now().strftime("%Y-%m-%d")

def update_today(data: list=[]):
    """更新today.md文件和archive文件
    
    参数：
        data (list): 包含文章数据的列表
    """
    # 获取脚本所在目录的绝对路径
    root_path = Path(__file__).absolute().parent
    # 定义临时数据文件路径
    data_path = root_path.joinpath('temp_data.json')
    # 定义今天的markdown文件路径
    today_path = root_path.joinpath('today.md')
    # 定义归档文件路径
    archive_path = root_path.joinpath(f'archive/{today.split("-")[0]}/{today}.md')

    # 如果没有传入data参数，且临时数据文件存在，则读取临时数据
    if not data and data_path.exists():
        with open(data_path, 'r') as f1:
            data = json.load(f1)

    # 确保归档目录存在
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    # 打开today.md和归档文件进行写入
    with open(today_path, 'w+') as f1, open(archive_path, 'w+') as f2:
        # 写入标题
        content = f'# 每日安全资讯（{today}）\n\n'
        # 遍历每个订阅源及其文章
        for item in data:
            (feed, value), = item.items()
            # 写入订阅源名称
            content += f'- {feed}\n'
            # 写入每篇文章的标题和链接
            for title, url in value.items():
                content += f'  - [{title}]({url})\n'
        # 将内容写入today.md
        f1.write(content)
        # 将内容写入归档文件
        f2.write(content)

def update_rss(rss: dict, proxy_url=''):
    """更新订阅源文件
    
    参数：
        rss (dict): 包含订阅源信息的字典
        proxy_url (str): 代理URL，可选
    """
    # 设置代理
    proxy = {'http': proxy_url, 'https': proxy_url} if proxy_url else {'http': None, 'https': None}

    # 解包rss字典，获取订阅源名称和详细信息
    (key, value), = rss.items()
    # 定义订阅源文件路径
    rss_path = root_path.joinpath(f'rss/{value["filename"]}')

    result = None
    # 如果订阅源有URL
    if url := value.get('url'):
        # 请求订阅源URL
        r = requests.get(value['url'], proxies=proxy)
        # 如果请求成功，状态码为200
        if r.status_code == 200:
            # 将响应内容写入订阅源文件
            with open(rss_path, 'w+') as f:
                f.write(r.text)
            print(f'[+] 更新完成：{key}')
            result = {key: rss_path}
        # 如果请求失败，但订阅源文件存在，则使用旧文件
        elif rss_path.exists():
            print(f'[-] 更新失败，使用旧文件：{key}')
            result = {key: rss_path}
        # 如果请求失败且订阅源文件不存在，跳过该订阅源
        else:
            print(f'[-] 更新失败，跳过：{key}')
    # 如果没有URL，则认为是本地文件
    else:
        print(f'[+] 本地文件：{key}')

    return result

def parseThread(conf: dict, url: str, proxy_url=''):
    """获取文章线程
    
    参数：
        conf (dict): 包含配置的字典
        url (str): RSS feed的URL
        proxy_url (str): 代理URL，可选
    """
    def filter(title: str):
        """过滤文章
        
        参数：
            title (str): 文章标题
        
        返回：
            bool: 是否保留该文章
        """
        # 遍历过滤关键词列表
        for i in conf['exclude']:
            # 如果文章标题包含任意一个过滤关键词，则不保留该文章
            if i in title:
                return False
        return True

    # 设置代理
    proxy = {'http': proxy_url, 'https': proxy_url} if proxy_url else {'http': None, 'https': None}
    # 定义请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    title = ''
    result = {}
    try:
        # 请求RSS feed URL，超时时间为10秒
        r = requests.get(url, timeout=10, headers=headers, verify=False, proxies=proxy)
        # 解析RSS feed
        r = feedparser.parse(r.content)
        # 获取RSS feed的标题
        title = r.feed.title
        # 遍历RSS feed中的每一项
        for entry in r.entries:
            # 获取文章发布时间或更新时间
            d = entry.get('published_parsed') or entry.get('updated_parsed')
            # 获取昨天的日期
            yesterday = datetime.date.today() + datetime.timedelta(-1)
            # 将发布时间转换为日期对象
            pubday = datetime.date(d[0], d[1], d[2])
            # 如果文章是昨天发布的且符合过滤条件
            if pubday == yesterday and filter(entry.title):
                # 创建文章条目
                item = {entry.title: entry.link}
                print(item)
                # 将文章条目添加到结果中
                result |= item
        # 打印RSS feed的处理结果
        console.print(f'[+] {title}\t{url}\t{len(result.values())}/{len(r.entries)}', style='bold green')
    except Exception as e:
        # 如果处理失败，打印错误信息
        console.print(f'[-] failed: {url}', style='bold red')
        print(e)
    return title, result

async def init_bot(conf: dict, proxy_url=''):
    """初始化机器人
    
    参数：
        conf (dict): 包含机器人的配置字典
        proxy_url (str): 代理URL，可选
    """
    bots = []
    # 遍历每个机器人的配置
    for name, v in conf.items():
        # 如果该机器人启用
        if v['enabled']:
            # 获取机器人的密钥
            key = os.getenv(v['secrets']) or v['key']

            # 根据机器人的名称初始化不同类型的机器人
            if name == 'mail':
                # 初始化邮件机器人
                receiver = os.getenv(v['secrets_receiver']) or v['receiver']
                bot = globals()[f'{name}Bot'](v['address'], key, receiver, v['from'], v['server'])
                bots.append(bot)
            elif name == 'qq':
                # 初始化QQ机器人
                bot = globals()[f'{name}Bot'](v['group_id'])
                if await bot.start_server(v['qq_id'], key):
                    bots.append(bot)
            elif name == 'telegram':
                # 初始化Telegram机器人
                bot = globals()[f'{name}Bot'](key, v['chat_id'], proxy_url)
                if await bot.test_connect():
                    bots.append(bot)
            else:
                # 初始化其他类型的机器人
                bot = globals()[f'{name}Bot'](key, proxy_url)
                bots.append(bot)
    return bots

def init_rss(conf: dict, update: bool=False, proxy_url=''):
    """初始化订阅源
    
    参数：
        conf (dict): 包含订阅源配置的字典
        update (bool): 是否更新订阅源文件
        proxy_url (str): 代理URL，可选
    """
    rss_list = []
    # 获取启用的订阅源
    enabled = [{k: v} for k, v in conf.items() if v['enabled']]
    # 遍历每个订阅源
    for rss in enabled:
        if update:
            # 更新订阅源文件
            if rss := update_rss(rss, proxy_url):
                rss_list.append(rss)
        else:
            # 使用本地订阅源文件
            (key, value), = rss.items()
            rss_list.append({key: root_path.joinpath(f'rss/{value["filename"]}')})

    # 合并相同链接
    feeds = []
    for rss in rss_list:
        (_, value), = rss.items()
        try:
            # 解析OPML格式的订阅源文件
            rss = listparser.parse(open(value).read())
            for feed in rss.feeds:
                url = feed.url.strip().rstrip('/')
                short_url = url.split('://')[-1].split('www.')[-1]
                check = [feed for feed in feeds if short_url in feed]
                # 如果链接不重复，则添加到feeds列表中
                if not check:
                    feeds.append(url)
        except Exception as e:
            # 解析失败，打印错误信息
            console.print(f'[-] 解析失败：{value}', style='bold red')
            print(e)

    # 打印解析出的订阅源数量
    console.print(f'[+] {len(feeds)} feeds', style='bold yellow')
    return feeds

def cleanup():
    """结束清理工作"""
    qqBot.kill_server()

async def job(args):
    """定时任务
    
    参数：
        args (Namespace): 命令行参数
    """
    # 打印ASCII艺术字和当前日期
    print(f'{pyfiglet.figlet_format("yarb")}\n{today}')

    # 获取脚本所在目录的绝对路径
    global root_path
    root_path = Path(__file__).absolute().parent
    if args.config:
        # 使用指定的配置文件
        config_path = Path(args.config).expanduser().absolute()
    else:
        # 使用默认的配置文件
        config_path = root_path.joinpath('config.json')
    # 读取配置文件
    with open(config_path) as f:
        conf = json.load(f)

    # 初始化RSS订阅源
    proxy_rss = conf['proxy']['url'] if conf['proxy']['rss'] else ''
    feeds = init_rss(conf['rss'], args.update, proxy_rss)

    results = []
    if args.test:
        # 测试模式，生成测试数据
        results.extend({f'test{i}': {Pattern.create(i*500): 'test'}} for i in range(1, 20))
    else:
        # 获取文章
        numb = 0
        tasks = []
        # 创建线程池，最大线程数为100
        with ThreadPoolExecutor(100) as executor:
            # 提交解析RSS feed的任务
            tasks.extend(executor.submit(parseThread, conf['keywords'], url, proxy_rss) for url in feeds)
            for task in as_completed(tasks):
                title, result = task.result()            
                if result:
                    numb += len(result.values())
                    results.append({title: result})
        # 打印解析结果
        console.print(f'[+] {len(results)} feeds, {numb} articles', style='bold yellow')

        # 将解析结果写入临时数据文件
        # temp_path = root_path.joinpath('temp_data.json')
        # with open(temp_path, 'w+') as f:
        #     f.write(json.dumps(results, indent=4, ensure_ascii=False))
        #     console.print(f'[+] temp data: {temp_path}', style='bold yellow')

        # 更新today.md和归档文件
        update_today(results)

    # 初始化机器人
    proxy_bot = conf['proxy']['url'] if conf['proxy']['bot'] else ''
    bots = await init_bot(conf['bot'], proxy_bot)
    for bot in bots:
        # 推送文章
        await bot.send(bot.parse_results(results))

    # 清理工作
    cleanup()

def argument():
    """解析命令行参数"""
    parser = argparse.ArgumentParser()
    # 添加更新RSS配置文件的选项
    parser.add_argument('--update', help='Update RSS config file', action='store_true', required=False)
    # 添加设置定时任务的选项
    parser.add_argument('--cron', help='Execute scheduled tasks every day (eg:"11:00")', type=str, required=False)
    # 添加指定配置文件的选项
    parser.add_argument('--config', help='Use specified config file', type=str, required=False)
    # 添加测试模式的选项
    parser.add_argument('--test', help='Test bot', action='store_true', required=False)
    return parser.parse_args()

async def main():
    """主函数"""
    args = argument()
    if args.cron:
        # 设置定时任务
        schedule.every().day.at(args.cron).do(job, args)
        while True:
            schedule.run_pending()
            await asyncio.sleep(1)
    else:
        # 立即执行一次任务
        await job(args)

# 如果脚本作为主程序运行，执行主函数
if __name__ == '__main__':
    asyncio.run(main())
