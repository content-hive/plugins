import re
import asyncio
import subprocess
import sys
from typing import Optional
from contenthive.models.content import URLParserResult
from contenthive.plugins.base import ContentParserPlugin
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


class Plugin(ContentParserPlugin):
    def on_load(self, context):
        self.context = context
        self.context.logger.info("Twitter Parser Plugin loaded.")
        self.playwright = None
        self.browser = None
        self.browser_context = None
        
        # 自动安装 Chromium 浏览器
        try:
            self.context.logger.info("Checking Playwright browser installation...")
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                capture_output=True,
                text=True
            )
            self.context.logger.info("Playwright Chromium browser ready.")
        except subprocess.CalledProcessError as e:
            self.context.logger.warning(f"Failed to install Playwright browser: {e}")
        except Exception as e:
            self.context.logger.warning(f"Unexpected error during browser installation: {e}")
        
    def on_enable(self):
        self.context.logger.info("Twitter Parser Plugin enabled.")

    def on_disable(self):
        self.context.logger.info("Twitter Parser Plugin disabled.")
        # 清理浏览器资源
        if self.browser_context or self.browser or self.playwright:
            self._run_async(self._cleanup_browser())

    def on_unload(self):
        self.context.logger.info("Twitter Parser Plugin unloaded.")
        # 确保资源被清理
        if self.browser_context or self.browser or self.playwright:
            self._run_async(self._cleanup_browser())
    
    def _run_async(self, coro):
        """安全运行异步协程"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # 如果没有事件循环，创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        
        if loop.is_running():
            # 如果事件循环正在运行，在新线程中运行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            # 如果没有运行，使用 run_until_complete
            return loop.run_until_complete(coro)
    
    async def _cleanup_browser(self):
        """清理浏览器资源"""
        if self.browser_context:
            await self.browser_context.close()
            self.browser_context = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
    
    async def _init_browser(self):
        """初始化浏览器"""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )
            self.browser_context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
            )
            await self.browser_context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
    
    def can_parse(self, url: str) -> bool:
        """
        Check if this plugin can parse the URL.
        Only handles Twitter/X URLs
        """
        return bool(re.match(r'https?://(www\.)?(twitter\.com|x\.com)/.+/status/\d+', url))
    
    def parse(self, url: str) -> Optional[URLParserResult]:
        """
        Parse content from Twitter URL using Playwright.
        """
        self.context.logger.info(f"Parsing Twitter URL: {url}")
        
        try:
            # 安全运行异步抓取
            parsed_data = self._run_async(self._scrape_tweet(url))
            if parsed_data is None:
                raise Exception("无法提取推文数据")
            return URLParserResult(**parsed_data)
        except Exception as e:
            self.context.logger.error(f"Failed to parse Twitter URL: {e}")
            return None
    
    async def _scrape_tweet(self, url: str) -> dict:
        """异步抓取推文数据"""
        await self._init_browser()
        
        page = await self.browser_context.new_page()
        
        try:
            self.context.logger.info(f"Visiting: {url}")
            
            # 访问推文页面
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # 等待主要内容加载
            try:
                await page.wait_for_selector('article[data-testid="tweet"]', timeout=30000)
            except PlaywrightTimeout:
                await page.wait_for_selector('article', timeout=20000)
            
            await page.wait_for_timeout(3000)
            
            # 提取推文数据
            tweet_data = await page.evaluate('''() => {
                const article = document.querySelector('article[data-testid="tweet"]') || 
                               document.querySelector('article[role="article"]') ||
                               document.querySelector('article');
                if (!article) return null;
                
                const data = {
                    text: '',
                    author: {},
                    timestamp: '',
                    images: [],
                    videos: []
                };
                
                // 提取文本内容
                const textElement = article.querySelector('[data-testid="tweetText"]');
                if (textElement) {
                    data.text = textElement.innerText;
                }
                
                // 获取短链接
                const tweetLinks = article.querySelectorAll('a[href^="https://t.co"]');
                const linkTexts = [];
                tweetLinks.forEach(link => {
                    if (link.textContent && link.textContent.includes('t.co')) {
                        linkTexts.push(link.textContent);
                    }
                });
                if (linkTexts.length > 0 && !data.text.includes('t.co')) {
                    data.text += ' ' + linkTexts.join(' ');
                }
                
                // 提取作者信息
                const authorName = article.querySelector('[data-testid="User-Name"] span span');
                const authorHandle = article.querySelector('[data-testid="User-Name"] a[role="link"]');
                if (authorName) {
                    data.author.name = authorName.innerText;
                }
                if (authorHandle) {
                    data.author.userName = authorHandle.href.split('/').pop();
                    data.author.url = authorHandle.href;
                }
                
                // 提取用户ID
                const avatarImg = article.querySelector('img[src*="profile_images"]');
                if (avatarImg && avatarImg.src) {
                    const match = avatarImg.src.match(/profile_images\/(\d+)/);
                    if (match) {
                        data.author.uid = match[1];
                    }
                }
                
                // 提取头像
                const avatar = article.querySelector('img[alt][src*="profile"]');
                if (avatar) {
                    data.author.avatar = avatar.src;
                }
                
                // 提取时间
                const timeElement = article.querySelector('time');
                if (timeElement) {
                    data.timestamp = timeElement.getAttribute('datetime');
                }
                
                // 提取图片（原图）
                const images = article.querySelectorAll('img[src*="media"]');
                images.forEach(img => {
                    if (!img.src.includes('profile')) {
                        let imageUrl = img.src.split('?')[0];
                        if (!imageUrl.match(/\.(jpg|jpeg|png|gif|webp)$/i)) {
                            imageUrl += '.jpg';
                        }
                        if (!imageUrl.endsWith(':orig')) {
                            imageUrl += ':orig';
                        }
                        data.images.push({ url: imageUrl });
                    }
                });
                
                // 提取视频
                const videos = article.querySelectorAll('video');
                videos.forEach(video => {
                    if (video.src || video.poster) {
                        data.videos.push({ url: video.src || video.poster });
                    }
                });
                
                return data;
            }''')
            
            if not tweet_data:
                raise Exception("无法提取推文数据")
            
            # 提取推文ID
            tweet_id_match = re.search(r'/status/(\d+)', url)
            tweet_id = tweet_id_match.group(1) if tweet_id_match else ''
            
            # 转换时间戳
            created_time = 0
            if tweet_data.get('timestamp'):
                try:
                    from datetime import datetime
                    dt_obj = datetime.fromisoformat(tweet_data['timestamp'].replace('Z', '+00:00'))
                    created_time = int(dt_obj.timestamp() * 1000)
                except:
                    pass
            
            # 构建返回数据
            return {
                'pid': tweet_id,
                'url': url,
                'images': tweet_data.get('images', []),
                'videos': tweet_data.get('videos', []),
                'content': tweet_data.get('text', ''),
                'author': {
                    'uid': tweet_data.get('author', {}).get('uid', ''),
                    'name': tweet_data.get('author', {}).get('name', ''),
                    'userName': tweet_data.get('author', {}).get('userName', ''),
                    'avatar': tweet_data.get('author', {}).get('avatar', ''),
                    'url': tweet_data.get('author', {}).get('url', '')
                },
                'createdTime': created_time,
                'parser': 'twitter_parser',
                'state': 'success',
                'platform': {
                    'name': 'X',
                    'code': 'x',
                    'url': 'https://x.com/',
                    'iconUrl': 'https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/d8/88/a7/d888a76a-2b0c-d68a-ab65-83eb09740f43/ProductionAppIcon-0-0-1x_U007emarketing-0-7-0-0-0-85-220.png/512x512bb.jpg'
                }
            }
            
        finally:
            await page.close()