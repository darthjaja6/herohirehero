"""Product Hunt profile scraper using Playwright."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

# 导航元素，用于过滤
NAV_SKIP = {'About', 'Forums', 'Activity', 'Upvotes', 'Collections', 'Stacks',
            'Reviews', 'Hunted', 'View more', 'View all', 'Report', 'Events',
            'Meet others online and in-person', 'FAQ', 'Advertise', "What's new", 'Stories'}


@dataclass
class PHReview:
    tool_name: str
    product_name: str
    text: str


@dataclass
class PHCollection:
    name: str


@dataclass
class PHMakerProduct:
    name: str
    slug: str


@dataclass
class PHProfile:
    username: str
    name: str | None = None
    headline: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    links: list[str] = field(default_factory=list)  # list of URLs

    followers_count: int = 0
    following_count: int = 0
    hunted_count: int = 0
    collections_count: int = 0
    reviews_count: int = 0

    badges: list[str] = field(default_factory=list)

    # 第二层数据
    following: list[str] = field(default_factory=list)
    hunted_posts: list[dict] = field(default_factory=list)
    collections: list[PHCollection] = field(default_factory=list)
    reviews: list[PHReview] = field(default_factory=list)


class PHProfileScraper:
    """Scraper for Product Hunt user profiles."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser: Browser | None = None
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
        context = self.browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        self.page = context.new_page()

    def close(self):
        """Close browser."""
        if self.browser:
            self.browser.close()
        if self._playwright:
            self._playwright.stop()

    def _wait_for_load(self):
        """Wait for page to load past Cloudflare."""
        self.page.wait_for_timeout(5000)
        if 'Just a moment' in self.page.title():
            self.page.wait_for_timeout(10000)
            if 'Just a moment' in self.page.title():
                raise Exception("Blocked by Cloudflare")

    def _scroll_once(self) -> bool:
        """Scroll to bottom. Returns True if page height changed."""
        prev = self.page.evaluate('document.body.scrollHeight')
        self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        self.page.wait_for_timeout(1500)
        return self.page.evaluate('document.body.scrollHeight') != prev

    def _get_lines(self) -> list[str]:
        """Get non-empty lines from main content."""
        main = self.page.query_selector('main')
        if not main:
            return []
        return [l.strip() for l in main.inner_text().split('\n') if l.strip()]

    def scrape_profile_main(self, username: str) -> PHProfile:
        """Scrape main profile page."""
        print(f"Scraping profile: @{username}")

        self.page.goto(f'https://www.producthunt.com/@{username}', timeout=60000)
        self._wait_for_load()

        profile = PHProfile(username=username)

        # Name and Headline - usually h1 followed by headline text
        h1 = self.page.query_selector('h1')
        if h1:
            profile.name = h1.inner_text().strip()
            # Headline is in the grandparent element of h1
            # Structure: name -> badge -> headline -> stats
            header = h1.evaluate_handle('el => el.parentElement.parentElement')
            if header:
                header_text = header.as_element().inner_text()
                lines = [l.strip() for l in header_text.split('\n') if l.strip()]
                # First line is name, collect headline lines after it
                if len(lines) >= 2 and lines[0] == profile.name:
                    headline_parts = []
                    for line in lines[1:]:
                        # Stop at stats (starts with # or digit, or contains "followers")
                        if re.match(r'^[#\d]', line) or 'followers' in line.lower():
                            break
                        # Skip very long lines or navigation elements
                        if len(line) > 100:
                            break
                        # Skip emoji-only lines or stacked products
                        if 'stacked products' in line.lower():
                            break
                        headline_parts.append(line)
                    if headline_parts:
                        profile.headline = ' | '.join(headline_parts)

        # Avatar
        avatar = self.page.query_selector(f'img[alt="{profile.name}"]')
        if avatar:
            profile.avatar_url = avatar.get_attribute('src')

        # Bio and badges from main text
        main = self.page.query_selector('main')
        if main:
            main_text = main.inner_text()
            # Bio
            about = re.search(r'About\s*\n(.+?)(?:\nLinks|\nBadges|\nMaker History|\n\d+\s*Hunted)', main_text, re.DOTALL)
            if about:
                profile.bio = about.group(1).strip()
            # Badges
            badges = re.search(r'Badges\s*\n(.+?)(?:\nView all badges|\nMaker History|\nForums)', main_text, re.DOTALL)
            if badges:
                profile.badges = [l.strip() for l in badges.group(1).split('\n') if l.strip() and len(l) < 50]

        # Links - collect external URLs (exclude producthunt-related links)
        seen_urls = set()
        for link in self.page.query_selector_all('a[href]'):
            href = link.get_attribute('href') or ''
            # Only external links
            if not href.startswith('http'):
                continue
            # Extract domain for filtering (ignore query params)
            domain = urlparse(href).netloc.lower()
            # Skip producthunt-related domains
            if 'producthunt' in domain:
                continue
            # Skip links to PH events or PH social accounts
            if domain == 'lu.ma' and 'producthunt' in href.lower():
                continue
            if (domain in ('x.com', 'twitter.com') and
                href.lower().rstrip('/').endswith('/producthunt')):
                continue
            if (domain == 'www.linkedin.com' and
                '/company/producthunt' in href.lower()):
                continue
            if href not in seen_urls:
                seen_urls.add(href)
                profile.links.append(href)

        # Counts
        page_text = self.page.content()
        for pattern, attr in [
            (r'([\d,]+)\s*followers', 'followers_count'),
            (r'([\d,]+)\s*following', 'following_count'),
            (r'([\d,]+)\s*Hunted', 'hunted_count'),
            (r'([\d,]+)\s*Collections', 'collections_count'),
            (r'([\d,]+)\s*Reviews', 'reviews_count'),
        ]:
            m = re.search(pattern, page_text, re.IGNORECASE)
            if m:
                setattr(profile, attr, int(m.group(1).replace(',', '')))

        return profile

    def _goto_tab(self, username: str, tab: str):
        """Navigate to a profile tab."""
        self.page.goto(f'https://www.producthunt.com/@{username}/{tab}', timeout=60000)
        self._wait_for_load()

    def scrape_following(self, username: str, max_items: int = 200) -> list[str]:
        """Scrape following list."""
        print(f"Scraping following for @{username} (max {max_items})")
        self._goto_tab(username, 'following')

        following = set()
        for _ in range(max_items // 20 + 1):
            for link in self.page.query_selector_all('a[href*="/@"]'):
                href = link.get_attribute('href') or ''
                m = re.search(r'/@(\w+)$', href)
                if m and m.group(1) != username:
                    following.add(m.group(1))

            if len(following) >= max_items or not self._scroll_once():
                break

        result = list(following)[:max_items]
        print(f"  Found {len(result)} following")
        return result

    def scrape_hunted(self, username: str, max_items: int = 100) -> list[dict]:
        """Scrape hunted posts. Returns list of {name, tagline, votes, comments}."""
        print(f"Scraping hunted posts for @{username} (max {max_items})")
        self._goto_tab(username, 'submitted')

        posts = []
        seen = set()

        for _ in range(max_items // 5 + 1):
            lines = self._get_lines()
            i = 0
            while i < len(lines) - 3:
                line = lines[i]
                if line and not line.isdigit() and 3 < len(line) < 80:
                    n1, n2, n3 = lines[i+1], lines[i+2], lines[i+3]
                    tagline, nums = None, []

                    if not n1.isdigit() and n2.isdigit() and n3.isdigit():
                        tagline, nums = n1, [int(n2), int(n3)]
                    elif n1.isdigit() and n2.isdigit():
                        nums = [int(n1), int(n2)]

                    if nums and line not in seen and line not in NAV_SKIP:
                        if not line.endswith('followers') and not line.endswith('following'):
                            seen.add(line)
                            if tagline:
                                seen.add(tagline)
                            posts.append({'name': line, 'tagline': tagline, 'votes': nums[0], 'comments': nums[1]})
                i += 1

            if len(posts) >= max_items or not self._scroll_once():
                break

        result = posts[:max_items]
        print(f"  Found {len(result)} hunted posts")
        return result

    def scrape_collections(self, username: str, max_items: int = 100) -> list[PHCollection]:
        """Scrape collections."""
        print(f"Scraping collections for @{username} (max {max_items})")
        self._goto_tab(username, 'collections')

        collections = []
        seen = set()

        for _ in range(max_items // 5 + 1):
            lines = self._get_lines()
            for i, line in enumerate(lines[:-1]):
                next_line = lines[i + 1]
                if re.match(r'\d+\s+products?', next_line) and line not in seen and line not in NAV_SKIP:
                    if line and not line.isdigit() and len(line) < 100:
                        seen.add(line)
                        collections.append(PHCollection(name=line))

            if len(collections) >= max_items or not self._scroll_once():
                break

        result = collections[:max_items]
        print(f"  Found {len(result)} collections")
        return result

    def scrape_reviews(self, username: str, max_items: int = 50) -> list[PHReview]:
        """Scrape reviews."""
        print(f"Scraping reviews for @{username} (max {max_items})")
        self._goto_tab(username, 'reviews')

        reviews = []
        seen = set()

        for _ in range(max_items // 5 + 1):
            lines = self._get_lines()
            i = 0
            while i < len(lines) - 5:
                # 格式: "used" / 工具名 / "to build" / 产品名 / ... / 评论内容 / Helpful
                if lines[i] == 'used' and lines[i + 2] == 'to build':
                    tool, product = lines[i + 1], lines[i + 3]

                    # 跳过 points/reviews 行，找评论内容
                    j = i + 4
                    while j < len(lines) and ('points' in lines[j] or 'reviews' in lines[j] or lines[j] == '•'):
                        j += 1

                    # 收集到 Helpful/Share/Report 为止
                    text_parts = []
                    while j < len(lines) and lines[j] not in ['Helpful', 'Share', 'Report']:
                        if 'views' not in lines[j] and not re.match(r'\d+[dhm]?\s*ago', lines[j]):
                            text_parts.append(lines[j])
                        else:
                            break
                        j += 1

                    text = ' '.join(text_parts).strip()
                    key = (tool, product)
                    if text and key not in seen:
                        seen.add(key)
                        reviews.append(PHReview(tool_name=tool, product_name=product, text=text[:500]))
                i += 1

            if len(reviews) >= max_items or not self._scroll_once():
                break

        result = reviews[:max_items]
        print(f"  Found {len(result)} reviews")
        return result

    def scrape_full_profile(
        self, username: str,
        max_following: int = 200, max_hunted: int = 100,
        max_collections: int = 100, max_reviews: int = 50,
    ) -> PHProfile:
        """Scrape complete profile with all second-level data."""
        profile = self.scrape_profile_main(username)

        if profile.following_count > 0:
            profile.following = self.scrape_following(username, max_following)
        if profile.hunted_count > 0:
            profile.hunted_posts = self.scrape_hunted(username, max_hunted)
        if profile.collections_count > 0:
            profile.collections = self.scrape_collections(username, max_collections)
        if profile.reviews_count > 0:
            profile.reviews = self.scrape_reviews(username, max_reviews)

        return profile


    def scrape_post_people(self, slug: str) -> list[str]:
        """Scrape makers/hunters from a post page. Returns list of usernames."""
        print(f"Scraping post: {slug}")
        self.page.goto(f'https://www.producthunt.com/posts/{slug}', timeout=60000)
        self._wait_for_load()

        makers = []
        seen = set()
        lines = self._get_lines()

        # 策略1: 找 "Maker" 标签前面的用户名
        # 页面结构: "用户名" / "公司名" / "Maker" / 评论内容...
        for i, line in enumerate(lines):
            if line == 'Maker' and i >= 2:
                # 往前找用户名 - 通常是前2行之一
                for j in range(1, 4):
                    if i - j >= 0:
                        candidate = lines[i - j]
                        # 用户名通常短，不含特殊字符
                        if candidate and len(candidate) < 50 and candidate not in seen:
                            # 验证是否真的是用户链接
                            for link in self.page.query_selector_all('a[href*="/@"]'):
                                link_text = link.inner_text().strip()
                                if link_text == candidate:
                                    href = link.get_attribute('href') or ''
                                    m = re.search(r'/@(\w+)$', href)
                                    if m:
                                        seen.add(candidate)
                                        makers.append(m.group(1))
                                    break

        # 策略2: 如果没找到，看 "Launch Team" 区域的链接
        if not makers:
            in_launch_team = False
            for i, line in enumerate(lines):
                if line == 'Launch Team':
                    in_launch_team = True
                elif in_launch_team and line in ('Promoted', 'What do you think', 'Login to comment'):
                    break
                elif in_launch_team:
                    # 在 Launch Team 区域内找用户链接
                    for link in self.page.query_selector_all('a[href*="/@"]'):
                        href = link.get_attribute('href') or ''
                        m = re.search(r'/@(\w+)$', href)
                        if m and m.group(1) not in seen:
                            seen.add(m.group(1))
                            makers.append(m.group(1))
                    break

        print(f"  Found {len(makers)} makers")
        return makers


def scrape_profile(username: str, headless: bool = False, **kwargs) -> PHProfile:
    """Convenience function to scrape a profile."""
    with PHProfileScraper(headless=headless) as scraper:
        return scraper.scrape_full_profile(username, **kwargs)


def scrape_post_people(slug: str, headless: bool = False) -> list[str]:
    """Convenience function to scrape usernames from a post."""
    with PHProfileScraper(headless=headless) as scraper:
        return scraper.scrape_post_people(slug)
