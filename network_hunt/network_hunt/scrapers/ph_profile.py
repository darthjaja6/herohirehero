"""Product Hunt profile scraper using Playwright."""

import re
import time
from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext


@dataclass
class PHReview:
    post_slug: str
    post_name: str
    rating: int | None
    text: str
    date: str | None


@dataclass
class PHCollection:
    name: str
    slug: str
    posts: list[str]  # post slugs


@dataclass
class PHMakerProduct:
    name: str
    slug: str
    tagline: str | None
    date: str | None


@dataclass
class PHProfile:
    username: str
    name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    website: str | None = None
    twitter: str | None = None
    other_links: dict[str, str] = field(default_factory=dict)

    followers_count: int = 0
    following_count: int = 0
    hunted_count: int = 0
    collections_count: int = 0
    stacks_count: int = 0
    reviews_count: int = 0

    badges: list[str] = field(default_factory=list)
    maker_history: list[PHMakerProduct] = field(default_factory=list)

    # 第二层数据
    following: list[str] = field(default_factory=list)  # usernames
    hunted_posts: list[dict] = field(default_factory=list)  # {name, votes, comments}
    collections: list[PHCollection] = field(default_factory=list)
    reviews: list[PHReview] = field(default_factory=list)


class PHProfileScraper:
    """Scraper for Product Hunt user profiles."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._playwright = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self):
        """Start browser."""
        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = self.browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        self.page = self.context.new_page()

    def close(self):
        """Close browser."""
        if self.browser:
            self.browser.close()
        if self._playwright:
            self._playwright.stop()

    def _wait_for_load(self, timeout: int = 5000):
        """Wait for page to load past Cloudflare."""
        self.page.wait_for_timeout(timeout)
        title = self.page.title()
        if 'Just a moment' in title:
            # Wait longer for Cloudflare
            self.page.wait_for_timeout(10000)
            title = self.page.title()
            if 'Just a moment' in title:
                raise Exception("Blocked by Cloudflare")

    def _extract_count(self, text: str) -> int:
        """Extract number from text like '11,618 followers'."""
        match = re.search(r'([\d,]+)', text)
        if match:
            return int(match.group(1).replace(',', ''))
        return 0

    def scrape_profile_main(self, username: str) -> PHProfile:
        """Scrape main profile page."""
        print(f"Scraping profile: @{username}")

        self.page.goto(f'https://www.producthunt.com/@{username}', timeout=60000)
        self._wait_for_load()

        profile = PHProfile(username=username)

        # Name (h1)
        h1 = self.page.query_selector('h1')
        if h1:
            profile.name = h1.inner_text().strip()

        # Avatar
        avatar = self.page.query_selector(f'img[alt="{profile.name}"]')
        if avatar:
            profile.avatar_url = avatar.get_attribute('src')

        # Bio - 获取 main 区域的文本，找 About 后面的内容
        main = self.page.query_selector('main')
        if main:
            main_text = main.inner_text()
            # Bio 通常在 "About" 之后，"Links" 或 "Badges" 之前
            about_match = re.search(r'About\s*\n(.+?)(?:\nLinks|\nBadges|\nMaker History|\n\d+\s*Hunted)', main_text, re.DOTALL)
            if about_match:
                profile.bio = about_match.group(1).strip()

        # Links section
        links = self.page.query_selector_all('a[href]')
        for link in links:
            href = link.get_attribute('href') or ''
            text = link.inner_text().strip()

            if 'twitter.com/' in href or 'x.com/' in href:
                match = re.search(r'(?:twitter\.com|x\.com)/(\w+)', href)
                if match and not profile.twitter:
                    profile.twitter = match.group(1)
            elif text == 'Website' or (href.startswith('http') and 'producthunt' not in href):
                if text == 'Website':
                    profile.website = href
                elif href.startswith('http') and 'producthunt' not in href and 'twitter' not in href and 'x.com' not in href:
                    profile.other_links[text or 'link'] = href

        # Counts from sidebar links
        count_patterns = [
            (r'([\d,]+)\s*followers', 'followers_count'),
            (r'([\d,]+)\s*following', 'following_count'),
            (r'([\d,]+)\s*Hunted', 'hunted_count'),
            (r'([\d,]+)\s*Collections', 'collections_count'),
            (r'([\d,]+)\s*Stacks', 'stacks_count'),
            (r'([\d,]+)\s*Reviews', 'reviews_count'),
        ]

        page_text = self.page.content()
        for pattern, attr in count_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                setattr(profile, attr, int(match.group(1).replace(',', '')))

        # Badges - 从页面文本中提取
        if main:
            main_text = main.inner_text()
            badges_match = re.search(r'Badges\s*\n(.+?)(?:\nView all badges|\nMaker History|\nForums)', main_text, re.DOTALL)
            if badges_match:
                badges_text = badges_match.group(1).strip()
                # 每行是一个 badge
                for line in badges_text.split('\n'):
                    line = line.strip()
                    if line and len(line) < 50:
                        profile.badges.append(line)

        # Maker History
        maker_links = self.page.query_selector_all('a[href*="/products/"], a[href*="/posts/"]')
        seen_slugs = set()
        for link in maker_links:
            href = link.get_attribute('href') or ''
            name = link.inner_text().strip()

            # Extract slug
            match = re.search(r'/(?:products|posts)/([^/?]+)', href)
            if match and name and len(name) < 100:
                slug = match.group(1)
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    profile.maker_history.append(PHMakerProduct(
                        name=name,
                        slug=slug,
                        tagline=None,
                        date=None,
                    ))

        return profile

    def _scroll_to_load(self, max_scrolls: int = 10, wait_ms: int = 1500) -> int:
        """Scroll to load more content. Returns number of scrolls performed."""
        for i in range(max_scrolls):
            prev_height = self.page.evaluate('document.body.scrollHeight')
            self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            self.page.wait_for_timeout(wait_ms)
            new_height = self.page.evaluate('document.body.scrollHeight')
            if new_height == prev_height:
                return i + 1  # No more content
        return max_scrolls

    def _click_nav_tab(self, text: str) -> bool:
        """Click a navigation tab by text. Returns True if successful."""
        # 找包含指定文字的导航链接
        links = self.page.query_selector_all('a[href]')
        for link in links:
            link_text = link.inner_text().strip()
            if text.lower() in link_text.lower():
                href = link.get_attribute('href') or ''
                # 确保是当前用户的导航链接
                if '/@' in href and ('following' in href or 'submitted' in href or
                                     'collections' in href or 'reviews' in href):
                    link.click()
                    self.page.wait_for_timeout(2000)
                    return True
        return False

    def scrape_following(self, username: str, max_pages: int = 10) -> list[str]:
        """Scrape following list. Assumes already on user's profile page."""
        print(f"Scraping following for @{username}")

        # 尝试点击导航，如果失败则直接访问URL
        if not self._click_nav_tab('following'):
            self.page.goto(f'https://www.producthunt.com/@{username}/following', timeout=60000)
            self._wait_for_load()

        following = []
        seen = set()

        for _ in range(max_pages):
            # 找所有用户链接
            links = self.page.query_selector_all('a[href*="/@"]')

            for link in links:
                href = link.get_attribute('href') or ''
                match = re.search(r'/@(\w+)$', href)
                if match:
                    uname = match.group(1)
                    if uname != username and uname not in seen:
                        seen.add(uname)
                        following.append(uname)

            # 尝试滚动加载更多
            prev_count = len(following)
            self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            self.page.wait_for_timeout(2000)

            # 检查是否有新内容
            links = self.page.query_selector_all('a[href*="/@"]')
            for link in links:
                href = link.get_attribute('href') or ''
                match = re.search(r'/@(\w+)$', href)
                if match:
                    uname = match.group(1)
                    if uname != username and uname not in seen:
                        seen.add(uname)
                        following.append(uname)

            if len(following) == prev_count:
                break  # 没有更多了

        print(f"  Found {len(following)} following")
        return following

    def scrape_hunted(self, username: str, max_items: int = 100, max_scrolls: int = 20) -> list[dict]:
        """Scrape hunted posts. Returns list of {name, tagline, votes, comments}."""
        print(f"Scraping hunted posts for @{username} (max {max_items})")

        # 尝试点击导航，如果失败则直接访问URL
        if not self._click_nav_tab('hunted'):
            self.page.goto(f'https://www.producthunt.com/@{username}/submitted', timeout=60000)
            self._wait_for_load()

        posts = []
        seen = set()

        for scroll in range(max_scrolls):
            # 从页面文本提取产品信息
            main = self.page.query_selector('main')
            if main:
                text = main.inner_text()
                lines = [l.strip() for l in text.split('\n') if l.strip()]

                i = 0
                while i < len(lines) - 3:
                    line = lines[i]
                    # 产品名通常较短且不是纯数字
                    if line and not line.isdigit() and 3 < len(line) < 80:
                        next1 = lines[i+1] if i+1 < len(lines) else ''
                        next2 = lines[i+2] if i+2 < len(lines) else ''
                        next3 = lines[i+3] if i+3 < len(lines) else ''

                        tagline = None
                        nums = []

                        # 模式1: name, tagline, votes, comments
                        if not next1.isdigit() and next2.isdigit() and next3.isdigit():
                            tagline = next1
                            nums = [int(next2), int(next3)]
                        # 模式2: name, votes, comments (无 tagline)
                        elif next1.isdigit() and next2.isdigit():
                            nums = [int(next1), int(next2)]

                        if len(nums) == 2 and line not in seen:
                            skip = ['About', 'Forums', 'Activity', 'Upvotes', 'Collections',
                                    'Stacks', 'Reviews', 'Hunted', 'View more', 'View all',
                                    'Events', 'Meet others online and in-person', 'FAQ',
                                    'Advertise', 'What\'s new', 'Stories']
                            if line not in skip and not line.endswith('followers') and not line.endswith('following'):
                                seen.add(line)
                                if tagline:
                                    seen.add(tagline)
                                posts.append({
                                    'name': line,
                                    'tagline': tagline,
                                    'votes': nums[0],
                                    'comments': nums[1],
                                })
                    i += 1

            # 检查是否达到上限
            if len(posts) >= max_items:
                posts = posts[:max_items]
                break

            # 滚动加载
            prev_height = self.page.evaluate('document.body.scrollHeight')
            self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            self.page.wait_for_timeout(1500)
            new_height = self.page.evaluate('document.body.scrollHeight')

            if new_height == prev_height:
                break  # 没有更多内容了

        print(f"  Found {len(posts)} hunted posts")
        return posts

    def scrape_collections(self, username: str, max_items: int = 100, max_scrolls: int = 20) -> list[PHCollection]:
        """Scrape collections. Returns list of collection names."""
        print(f"Scraping collections for @{username} (max {max_items})")

        # 尝试点击导航，如果失败则直接访问URL
        if not self._click_nav_tab('collections'):
            self.page.goto(f'https://www.producthunt.com/@{username}/collections', timeout=60000)
            self._wait_for_load()

        collections = []
        seen = set()

        for scroll in range(max_scrolls):
            main = self.page.query_selector('main')
            if main:
                text = main.inner_text()
                lines = [l.strip() for l in text.split('\n') if l.strip()]

                i = 0
                while i < len(lines) - 1:
                    line = lines[i]
                    next_line = lines[i + 1] if i + 1 < len(lines) else ''

                    # 检查是否是 "name\nN products" 格式
                    match = re.match(r'(\d+)\s+products?', next_line)
                    if match and line and not line.isdigit() and len(line) < 100:
                        skip = ['About', 'Forums', 'Activity', 'Upvotes', 'Collections',
                                'Stacks', 'Reviews', 'Hunted', 'View more', 'Report']
                        if line not in skip and line not in seen:
                            seen.add(line)
                            slug = line.lower().replace(' ', '-').replace("'", '')
                            collections.append(PHCollection(
                                name=line,
                                slug=slug,
                                posts=[],
                            ))
                    i += 1

            if len(collections) >= max_items:
                collections = collections[:max_items]
                break

            # 滚动加载
            prev_height = self.page.evaluate('document.body.scrollHeight')
            self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            self.page.wait_for_timeout(1500)
            new_height = self.page.evaluate('document.body.scrollHeight')

            if new_height == prev_height:
                break

        print(f"  Found {len(collections)} collections")
        return collections

    def scrape_reviews(self, username: str, max_items: int = 50, max_scrolls: int = 10) -> list[PHReview]:
        """Scrape reviews."""
        print(f"Scraping reviews for @{username} (max {max_items})")

        # 尝试点击导航，如果失败则直接访问URL
        if not self._click_nav_tab('reviews'):
            self.page.goto(f'https://www.producthunt.com/@{username}/reviews', timeout=60000)
            self._wait_for_load()

        reviews = []
        seen = set()

        for scroll in range(max_scrolls):
            # 从页面文本解析 reviews
            # 结构: Username / "used" / 工具名 / "to build" / 产品名 / "(N points)" / "•" / "N reviews" / 评论内容 / Helpful...
            main = self.page.query_selector('main')
            if main:
                text = main.inner_text()
                lines = [l.strip() for l in text.split('\n') if l.strip()]

                i = 0
                while i < len(lines) - 5:
                    if lines[i] == 'used' and i + 3 < len(lines) and lines[i + 2] == 'to build':
                        tool_name = lines[i + 1]
                        product_name = lines[i + 3]

                        j = i + 4
                        while j < len(lines) and ('points' in lines[j] or 'reviews' in lines[j] or lines[j] == '•'):
                            j += 1

                        review_lines = []
                        while j < len(lines):
                            if lines[j] in ['Helpful', 'Share', 'Report'] or 'views' in lines[j] or re.match(r'\d+[dhm]?\s*ago', lines[j]):
                                break
                            review_lines.append(lines[j])
                            j += 1

                        review_text = ' '.join(review_lines).strip()

                        key = (tool_name, product_name)
                        if review_text and key not in seen:
                            seen.add(key)
                            reviews.append(PHReview(
                                post_slug=tool_name.lower().replace(' ', '-'),
                                post_name=f"{tool_name} (for {product_name})",
                                rating=None,
                                text=review_text[:500],
                                date=None,
                            ))
                    i += 1

            if len(reviews) >= max_items:
                reviews = reviews[:max_items]
                break

            # 滚动加载
            prev_height = self.page.evaluate('document.body.scrollHeight')
            self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            self.page.wait_for_timeout(1500)
            new_height = self.page.evaluate('document.body.scrollHeight')

            if new_height == prev_height:
                break

        print(f"  Found {len(reviews)} reviews")
        return reviews

    def scrape_full_profile(
        self,
        username: str,
        max_following: int = 200,
        max_hunted: int = 100,
        max_collections: int = 100,
        max_reviews: int = 50,
    ) -> PHProfile:
        """Scrape complete profile with all second-level data."""
        # 第一层：主页
        profile = self.scrape_profile_main(username)

        # 第二层：following
        if profile.following_count > 0:
            profile.following = self.scrape_following(username, max_pages=max_following // 20 + 1)

        # 第二层：hunted posts
        if profile.hunted_count > 0:
            profile.hunted_posts = self.scrape_hunted(username, max_items=max_hunted)

        # 第二层：collections
        if profile.collections_count > 0:
            profile.collections = self.scrape_collections(username, max_items=max_collections)

        # 第二层：reviews
        if profile.reviews_count > 0:
            profile.reviews = self.scrape_reviews(username, max_items=max_reviews)

        return profile


def scrape_profile(
    username: str,
    headless: bool = False,
    max_following: int = 200,
    max_hunted: int = 100,
    max_collections: int = 100,
    max_reviews: int = 50,
) -> PHProfile:
    """Convenience function to scrape a profile."""
    with PHProfileScraper(headless=headless) as scraper:
        return scraper.scrape_full_profile(
            username,
            max_following=max_following,
            max_hunted=max_hunted,
            max_collections=max_collections,
            max_reviews=max_reviews,
        )
